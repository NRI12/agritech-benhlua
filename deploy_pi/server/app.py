"""Backend Flask cho dashboard Agritech — chạy trên Raspberry Pi 4.

Chức năng:
  • Serve dashboard tĩnh (templates/agritech)
  • /video_feed         : MJPEG xem trước từ camera (chỉ để ngắm khung hình)
  • /api/capture (POST) : chụp 1 khung từ camera rồi phân loại (không suy luận liên tục)
  • /api/sensors        : dữ liệu cảm biến (chưa cắm thiết bị -> available=false)
  • /api/chat (POST)    : tư vấn (ChatGPT, rớt về rule-based nếu không có key/lỗi)
  • /api/settings/api-key: xem/đặt/xoá API key ChatGPT (áp dụng ngay)
  • /api/health         : kiểm tra sống (dùng cho install.sh / giám sát)
  • /api/system         : nhiệt độ CPU, RAM, uptime của Pi
  • /api/predict/image (POST): phân tích ảnh người dùng chọn/tải lên
  • /api/treatment/<lớp>: biện pháp xử lý cho một bệnh
  • /api/history, /api/alerts, /api/device: dữ liệu cho các trang Lịch sử / Cảnh báo / Thiết bị

Chạy:  python app.py        rồi mở http://<ip-pi>:5000
"""
import base64
import hmac
import ipaddress
import os
import threading
import time

import cv2
import numpy as np
from flask import Flask, Response, jsonify, request, send_from_directory

import config
import sensors
import chatbot
import history
import llm
from camera import CaptureThread, placeholder_jpeg
from inference import PaddyClassifier

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024   # ảnh tải lên tối đa 10 MB

# ── Trạng thái dùng chung giữa các luồng ────────────────────────────────────
_capture = None
_classifier = None
_result_lock = threading.Lock()
_started_at = time.time()
_latest_result = {
    "class": None,
    "class_vi": "Đang chờ...",
    "confidence": 0.0,
    "severity": "—",
    "ratio_infected": 0,
    "ts": 0,
}


def _build_result(r):
    """Chuyển output của PaddyClassifier.predict() thành dict gửi cho dashboard."""
    cls = r["class"]
    conf = r["confidence"]
    info = config.CLASS_INFO.get(cls, {})
    # Tỷ lệ "nhiễm bệnh" hiển thị trên donut: 0 nếu khỏe/không phải lúa
    if cls in (config.NOT_RICE, "normal"):
        ratio = 0
    else:
        ratio = int(conf * 100)
    return {
        "class": cls,
        "class_vi": info.get("vi", cls),
        "confidence": round(conf * 100, 1),
        "severity": info.get("severity", "—"),
        "ratio_infected": ratio,
        "ts": time.time(),
    }


# ── Routes: dashboard tĩnh ───────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(config.DASHBOARD_DIR, "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    # Phục vụ css/, js/ và các tài nguyên khác của dashboard
    return send_from_directory(config.DASHBOARD_DIR, filename)


# ── Routes: video stream ─────────────────────────────────────────────────────
def _mjpeg_generator():
    boundary = b"--frame"
    while True:
        jpeg = _capture.get_jpeg() if _capture else None
        if jpeg is None:
            jpeg = placeholder_jpeg()
            time.sleep(0.2)
        yield (boundary + b"\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n")
        time.sleep(0.04)  # ~25 FPS trần


@app.route("/video_feed")
def video_feed():
    return Response(_mjpeg_generator(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")


# ── Routes: API ──────────────────────────────────────────────────────────────
@app.route("/api/predict/latest")
def predict_latest():
    with _result_lock:
        return jsonify(_latest_result)


@app.route("/api/sensors")
def api_sensors():
    return jsonify(sensors.read_sensors())


@app.route("/api/health")
def api_health():
    with _result_lock:
        last = _latest_result.get("ts", 0)
    return jsonify({
        "ok": True,
        "model_loaded": _classifier is not None,
        "camera": _capture is not None,
        "last_analysis_age": round(time.time() - last, 1) if last else None,
        "uptime": int(time.time() - _started_at),
    })


def _read_system():
    """Thông số Pi đọc từ /proc và /sys (Linux); trường nào không có thì None."""
    info = {"cpu_temp": None, "mem_used_pct": None, "load1": None}
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            info["cpu_temp"] = round(int(f.read()) / 1000, 1)
    except (OSError, ValueError):
        pass
    try:
        mem = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, v = line.split(":", 1)
                mem[k] = int(v.split()[0])
        info["mem_used_pct"] = round(100 * (1 - mem["MemAvailable"] / mem["MemTotal"]), 1)
    except (OSError, ValueError, KeyError):
        pass
    try:
        info["load1"] = round(os.getloadavg()[0], 2)
    except (OSError, AttributeError):
        pass
    return info


@app.route("/api/system")
def api_system():
    return jsonify({**_read_system(), "uptime": int(time.time() - _started_at)})


def _low_conf(snap):
    return bool(snap.get("class")) and snap.get("class") != config.NOT_RICE and (snap.get("confidence") or 0) < config.CONF_THRESHOLD * 100


def _chat_context(raw):
    """Ngữ cảnh chat = kết quả của ảnh đang xem trên dashboard (client gửi lên). Chỉ nhận lớp hợp lệ."""
    raw = raw if isinstance(raw, dict) else {}
    cls = raw.get("class")
    if cls not in config.CLASS_INFO:
        return {}
    info = config.CLASS_INFO[cls]
    try:
        conf = max(0.0, min(100.0, float(raw.get("confidence", 0))))
    except (TypeError, ValueError):
        conf = 0.0
    return {"class": cls, "class_vi": info["vi"], "severity": info["severity"], "confidence": conf}


def _clean_history(raw, max_turns=12, max_len=1500):
    """Lịch sử hội thoại từ client: chỉ nhận role user/assistant, cắt độ dài và số lượt."""
    out = []
    for m in raw if isinstance(raw, list) else []:
        if isinstance(m, dict) and m.get("role") in ("user", "assistant") \
                and isinstance(m.get("content"), str) and m["content"].strip():
            out.append({"role": m["role"], "content": m["content"].strip()[:max_len]})
    return out[-max_turns * 2:]


def _analyze(frame, source):
    """Phân loại 1 khung ảnh (upload hoặc chụp từ camera), lưu lịch sử, trả dict cho dashboard."""
    global _latest_result
    r = _classifier.predict(frame)
    res = _build_result(r)
    res["source"] = source
    names = _classifier.class_names
    order = np.argsort(r["probs"])[::-1][:3]
    res["top3"] = [{"class": names[i],
                    "class_vi": config.CLASS_INFO.get(names[i], {}).get("vi", names[i]),
                    "p": round(r["probs"][i] * 100, 1)} for i in order]
    res["is_rice"] = r["is_rice"]
    res["gradcam"] = r.get("gradcam")
    with _result_lock:
        _latest_result = {k: v for k, v in res.items() if k != "gradcam"}
    history.record(res, source)
    return res


@app.route("/api/predict/image", methods=["POST"])
def predict_image():
    """Nhận 1 ảnh (multipart field 'image'), trả kết quả phân loại + Grad-CAM."""
    f = request.files.get("image")
    if f is None:
        return jsonify({"error": "Thiếu file ảnh (field 'image')."}), 400
    arr = np.frombuffer(f.read(), np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR) if arr.size else None
    if frame is None:
        return jsonify({"error": "Không đọc được ảnh. Hãy chọn file JPG/PNG."}), 400
    if _classifier is None:
        return jsonify({"error": "Model chưa sẵn sàng."}), 503
    return jsonify(_analyze(frame, "upload"))


@app.route("/api/capture", methods=["POST"])
def api_capture():
    """Chụp 1 khung hình từ camera rồi phân loại. Camera chỉ dùng để chụp, không suy luận liên tục."""
    frame = None
    for _ in range(30):                 # webcam cần ~1-2 giây để có khung đầu tiên
        frame = _capture.get_frame() if _capture else None
        if frame is not None or _capture is None:
            break
        time.sleep(0.1)
    if frame is None:
        return jsonify({"error": "Camera chưa sẵn sàng hoặc chưa có khung hình. Kiểm tra camera rồi thử lại."}), 503
    if _classifier is None:
        return jsonify({"error": "Model chưa sẵn sàng."}), 503
    res = _analyze(frame, "camera")
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 88])
    res["image"] = "data:image/jpeg;base64," + base64.b64encode(buf).decode() if ok else None
    return jsonify(res)


@app.route("/api/treatment/<cls>")
def api_treatment(cls):
    info = chatbot.TREATMENT.get(cls)
    if not info:
        return jsonify({"error": "Không có dữ liệu cho lớp này."}), 404
    return jsonify({**info, "class_vi": config.CLASS_INFO.get(cls, {}).get("vi", cls)})


@app.route("/api/history")
def api_history():
    limit = max(1, min(request.args.get("limit", 100, type=int), 500))
    return jsonify(history.read(limit))


@app.route("/api/alerts")
def api_alerts():
    """Cảnh báo = lần nhận diện ra bệnh (không phải khoẻ/không phải lúa) với mức Nặng/Trung bình."""
    rows = [r for r in history.read(500)
            if r["class"] not in ("normal", config.NOT_RICE) and r.get("severity") in ("Nặng", "Trung bình")]
    return jsonify(rows[:50])


@app.route("/api/device")
def api_device():
    key = llm.get_api_key()
    return jsonify({
        "camera_source": config.CAMERA_SOURCE,
        "camera_running": _capture is not None,
        "model_loaded": _classifier is not None,
        "model_path": os.path.basename(config.MODEL_PATH),
        "classes": len(_classifier.class_names) if _classifier else 0,
        "chatgpt": bool(key[0]),
        "chatgpt_model": os.environ.get("OPENAI_MODEL", config.OPENAI_MODEL),
        "thresholds": {"conf": config.CONF_THRESHOLD, "rice_min_vegetation": config.RICE_MIN_VEGETATION,
                       "rice_max_entropy": config.RICE_MAX_ENTROPY, "rice_min_conf": config.RICE_MIN_CONF},
        **_read_system(), "uptime": int(time.time() - _started_at),
    })


@app.errorhandler(413)
def too_large(_):
    return jsonify({"error": "Ảnh quá lớn (tối đa 10 MB)."}), 413


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(silent=True) or {}
    question = (data.get("message") or "").strip()[:1000]
    snap = _chat_context(data.get("context"))
    not_rice = snap.get("class") == config.NOT_RICE
    current = None if not_rice else snap.get("class")

    source, reply = "offline", None
    if question and llm.get_api_key()[0]:
        try:
            prompt = llm.build_system_prompt(
                snap.get("class_vi") if current else None,
                snap.get("severity"), snap.get("confidence"),
                chatbot.TREATMENT.get(current), not_rice=not_rice)
            reply, source = llm.ask(question, prompt, _clean_history(data.get("history"))), "chatgpt"
            if _low_conf(snap):
                reply = (f"⚠ Ảnh này chỉ nhận diện với độ tin cậy {snap.get('confidence')}% — chưa đủ chắc "
                         f"để kết luận. Hãy chụp lại lá rõ hơn hoặc hỏi cán bộ khuyến nông.\n\n{reply}")
            ref = {} if _low_conf(snap) else (chatbot.TREATMENT.get(current) or {})
            warn = llm.audit(reply, " ".join(ref.values()))
            if warn:
                reply = f"{reply}\n\n{warn}"
        except llm.LLMError as e:
            print(f"[chat] ChatGPT lỗi: {e}")
            fallback = chatbot.answer(question, current_disease=current)
            reply = f"(ChatGPT không khả dụng: {e} Đang dùng tư vấn có sẵn.)\n\n{fallback}"
    if reply is None:
        reply = chatbot.answer(question, current_disease=current)

    # Mọi câu trả lời AI đều kết thúc bằng lưu ý này
    reply = f"{reply}\n\n{config.AI_DISCLAIMER}"
    return jsonify({"reply": reply, "source": source})


# ── Quản lý API key ChatGPT ──────────────────────────────────────────────────
def _is_admin():
    """Có token thì bắt buộc khớp; không có token thì chỉ cho client trong LAN
    (và không đi qua proxy/tunnel — tunnel luôn kèm header chuyển tiếp)."""
    if config.ADMIN_TOKEN:
        sent = request.headers.get("X-Admin-Token", "")
        return hmac.compare_digest(sent, config.ADMIN_TOKEN)
    if request.headers.get("Cf-Connecting-Ip") or request.headers.get("X-Forwarded-For"):
        return False
    try:
        return ipaddress.ip_address(request.remote_addr).is_private
    except ValueError:
        return False


def _key_status():
    key, src = llm.get_api_key()
    return {"configured": bool(key), "source": src, "masked": llm.mask(key)}


@app.route("/api/settings/api-key", methods=["GET", "POST", "DELETE"])
def api_key_settings():
    if not _is_admin():
        return jsonify({"error": "Không có quyền. Đổi key từ mạng LAN hoặc gửi X-Admin-Token."}), 403
    if request.method == "POST":
        key = ((request.get_json(silent=True) or {}).get("key") or "").strip()
        if not key.startswith("sk-") or len(key) < 20 or any(c.isspace() for c in key):
            return jsonify({"error": "API key không đúng định dạng (bắt đầu bằng sk-)."}), 400
        llm.set_api_key(key)
    elif request.method == "DELETE":
        llm.clear_api_key()
    return jsonify(_key_status())


def main():
    global _capture, _classifier
    print("[init] Nạp model ONNX...")
    _classifier = PaddyClassifier()
    print("[init] Khởi động camera...")
    try:
        _capture = CaptureThread().start()
    except Exception as e:
        # Không có/khởi tạo lỗi camera: vẫn chạy server (stream hiện ảnh chờ).
        print(f"[init] CẢNH BÁO: không khởi động được camera ({e}). "
              f"Dashboard/API vẫn chạy, video sẽ hiện ảnh chờ.")
        _capture = None
    print(f"[ready] http://{config.HOST}:{config.PORT}  (Ctrl+C để dừng)")
    # threaded=True để stream + API phục vụ song song
    app.run(host=config.HOST, port=config.PORT, threaded=True, debug=False)


if __name__ == "__main__":
    main()

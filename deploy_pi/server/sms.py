"""Cảnh báo SMS qua modem 4G SIM7600 (lệnh AT, cổng /dev/ttyUSB*) khi phát hiện bệnh lúa.

Cài đặt lưu ở data/sms_settings.json (sửa trên giao diện: Cài đặt > Cảnh báo SMS):
  enabled, phones[], min_conf (%), cooldown_min (mỗi loại bệnh), daily_max, include_upload

Chống spam/tốn tiền SMS: chỉ gửi khi đúng là lúa bị bệnh với độ tin cậy >= min_conf, mỗi loại bệnh
cách nhau tối thiểu cooldown_min phút, tối đa daily_max tin/ngày (mặc định chỉ ảnh chụp từ camera,
ảnh tải lên chỉ tính khi bật include_upload). Nội dung SMS không dấu để vừa 1 tin 160 ký tự.

Cổng AT: biến SMS_AT_PORT, hoặc tự dò /dev/ttyUSB2,3,1,0,4 (cổng đầu tiên trả lời "OK" cho lệnh AT).
Cần: modem có SIM còn tiền, user chạy server thuộc nhóm dialout, ModemManager không giữ cổng AT.
"""
import json
import os
import re
import select
import termios
import threading
import time
import unicodedata

import config

SETTINGS_FILE = os.path.join(config.DATA_DIR, "sms_settings.json")
DEFAULTS = {"enabled": False, "phones": [], "min_conf": 60, "cooldown_min": 120,
            "daily_max": 10, "include_upload": False}
PORT_CANDIDATES = ["/dev/ttyUSB2", "/dev/ttyUSB3", "/dev/ttyUSB1", "/dev/ttyUSB0", "/dev/ttyUSB4"]

_io_lock = threading.Lock()       # chỉ 1 luồng nói chuyện với modem tại một thời điểm
_state_lock = threading.Lock()
_last_by_class = {}               # lớp bệnh -> thời điểm gửi gần nhất
_sent_today = {"day": "", "n": 0}
_last_result = {"ts": 0, "ok": None, "detail": "Chưa gửi tin nào."}


# ── Cài đặt ─────────────────────────────────────────────────────────────────
def normalize_phone(raw):
    """Số VN dạng 0912345678 / +84912345678 / 84912345678 -> +84912345678. Số khác: giữ +<số quốc tế>."""
    s = re.sub(r"[\s.\-()]", "", str(raw or ""))
    if re.fullmatch(r"0\d{9,10}", s):
        return "+84" + s[1:]
    if re.fullmatch(r"84\d{9,10}", s):
        return "+" + s
    if re.fullmatch(r"\+\d{9,15}", s):
        return s
    return None


def load_settings():
    s = dict(DEFAULTS)
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            s.update(json.load(f))
    except (OSError, ValueError):
        pass
    return s


def save_settings(data):
    """Kiểm tra và lưu. Trả (settings, lỗi). Lỗi: chuỗi tiếng Việt hoặc None."""
    phones = []
    raw_list = data.get("phones", [])
    if isinstance(raw_list, str):
        raw_list = re.split(r"[,;\n]+", raw_list)
    for p in raw_list:
        if not str(p).strip():
            continue
        n = normalize_phone(p)
        if not n:
            return None, f"Số điện thoại không hợp lệ: {p}"
        if n not in phones:
            phones.append(n)
    if len(phones) > 5:
        return None, "Tối đa 5 số điện thoại."
    try:
        s = {
            "enabled": bool(data.get("enabled")),
            "phones": phones,
            "min_conf": max(0, min(100, float(data.get("min_conf", DEFAULTS["min_conf"])))),
            "cooldown_min": max(1, min(1440, int(data.get("cooldown_min", DEFAULTS["cooldown_min"])))),
            "daily_max": max(1, min(200, int(data.get("daily_max", DEFAULTS["daily_max"])))),
            "include_upload": bool(data.get("include_upload")),
        }
    except (TypeError, ValueError):
        return None, "Giá trị cài đặt không hợp lệ."
    if s["enabled"] and not phones:
        return None, "Bật cảnh báo SMS thì cần ít nhất 1 số điện thoại."
    os.makedirs(config.DATA_DIR, exist_ok=True)
    tmp = SETTINGS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SETTINGS_FILE)
    return s, None


# ── Nội dung ────────────────────────────────────────────────────────────────
def ascii_vi(text):
    """Bỏ dấu tiếng Việt: SMS chữ thường (GSM-7) vừa 160 ký tự, không lỗi font."""
    text = str(text).replace("đ", "d").replace("Đ", "D")
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def build_message(res):
    return ascii_vi(
        f"AGRITECH: Phat hien benh {res.get('class_vi', res.get('class'))} tren lua "
        f"(do tin cay {res.get('confidence')}%, muc do {res.get('severity', '-')}). "
        f"De nghi ra tham dong kiem tra som.")[:160]


# ── Giao tiếp modem (AT) ────────────────────────────────────────────────────
def _open(port):
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    a = termios.tcgetattr(fd)
    a[0] = 0; a[1] = 0; a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL; a[3] = 0
    a[4] = a[5] = termios.B115200
    a[6][termios.VMIN] = 0; a[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, a)
    termios.tcflush(fd, termios.TCIOFLUSH)
    return fd


def _read_until(fd, markers, timeout):
    """Đọc tới khi gặp một trong markers hoặc hết timeout. Trả (đã_gặp, dữ_liệu)."""
    buf, end = "", time.time() + timeout
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.2)
        if r:
            try:
                buf += os.read(fd, 4096).decode("latin-1")
            except BlockingIOError:
                continue
            if any(m in buf for m in markers):
                return True, buf
    return False, buf


def _cmd(fd, text, markers=("OK", "ERROR"), timeout=5):
    termios.tcflush(fd, termios.TCIFLUSH)
    os.write(fd, text.encode() + b"\r")
    return _read_until(fd, markers, timeout)


def find_port():
    forced = os.environ.get("SMS_AT_PORT")
    for port in ([forced] if forced else PORT_CANDIDATES):
        if not port or not os.path.exists(port):
            continue
        try:
            fd = _open(port)
        except OSError:
            continue
        try:
            got, buf = _cmd(fd, "AT", timeout=2)
            if got and "OK" in buf:
                return port, None
        finally:
            os.close(fd)
    return None, ("Không tìm thấy cổng AT của modem (kiểm tra modem 4G đã cắm, user thuộc nhóm dialout, "
                  "ModemManager không giữ cổng; hoặc đặt SMS_AT_PORT).")


def send_sms(phone, text):
    """Gửi 1 tin. Trả (ok, chi_tiết). Không ném lỗi."""
    with _io_lock:
        port, err = find_port()
        if not port:
            return False, err
        try:
            fd = _open(port)
        except OSError as e:
            return False, f"Không mở được {port}: {e}"
        try:
            for c in ("ATE0", "AT+CMGF=1", 'AT+CSCS="GSM"'):
                got, buf = _cmd(fd, c)
                if not got or "ERROR" in buf:
                    return False, f"Modem từ chối lệnh {c}: {buf.strip()[:80]}"
            got, buf = _cmd(fd, "AT+CPIN?", timeout=5)
            if "READY" not in buf:
                return False, f"SIM chưa sẵn sàng ({buf.strip()[:60] or 'không phản hồi'})."
            got, buf = _cmd(fd, f'AT+CMGS="{phone}"', markers=(">", "ERROR"), timeout=8)
            if ">" not in buf:
                return False, f"Modem không nhận số {phone}: {buf.strip()[:80]}"
            os.write(fd, text.encode("ascii", "ignore") + b"\x1a")
            got, buf = _read_until(fd, ("+CMGS:", "ERROR"), 40)
            if "+CMGS:" in buf:
                return True, f"Đã gửi tới {phone}"
            return False, f"Gửi thất bại tới {phone}: {buf.strip()[:100] or 'hết thời gian chờ'} (SIM hết tiền/không có sóng?)"
        except OSError as e:
            return False, f"Lỗi cổng modem: {e}"
        finally:
            os.close(fd)


def send_all(phones, text):
    oks, details = 0, []
    for p in phones:
        ok, d = send_sms(p, text)
        oks += ok
        details.append(d)
    return oks, "; ".join(details)


def _record(ok, detail):
    with _state_lock:
        _last_result.update(ts=time.time(), ok=ok, detail=detail)


def last_result():
    with _state_lock:
        return dict(_last_result)


def send_test():
    s = load_settings()
    if not s["phones"]:
        return False, "Chưa nhập số điện thoại."
    n, detail = send_all(s["phones"], "AGRITECH: Tin nhan thu he thong canh bao benh lua.")
    _record(n > 0, detail)
    return n > 0, detail


# ── Kích hoạt khi có kết quả nhận diện ───────────────────────────────────────
def should_alert(res, source, s, now=None):
    """(gửi?, lý do). Cập nhật bộ đếm chống spam khi trả True."""
    now = now or time.time()
    if not s["enabled"] or not s["phones"]:
        return False, "tắt"
    if source != "camera" and not s["include_upload"]:
        return False, "ảnh tải lên không gửi"
    cls = res.get("class")
    if not res.get("is_rice", True) or cls in (None, "normal", config.NOT_RICE):
        return False, "không phải bệnh"
    if (res.get("confidence") or 0) < s["min_conf"]:
        return False, "độ tin cậy thấp"
    day = time.strftime("%Y-%m-%d", time.localtime(now))
    with _state_lock:
        if _sent_today["day"] != day:
            _sent_today.update(day=day, n=0)
        if _sent_today["n"] >= s["daily_max"]:
            return False, "đủ số tin trong ngày"
        last = _last_by_class.get(cls)
        if last is not None and now - last < s["cooldown_min"] * 60:
            return False, "chưa hết thời gian chờ"
        _last_by_class[cls] = now
        _sent_today["n"] += 1
    return True, ""


def maybe_alert(res, source):
    """Gọi sau mỗi lần nhận diện. Không chặn: gửi ở luồng nền."""
    s = load_settings()
    go, _ = should_alert(res, source, s)
    if not go:
        return False

    def work():
        n, detail = send_all(s["phones"], build_message(res))
        if n == 0:                      # gửi hỏng thì cho phép thử lại ở lần phát hiện sau
            with _state_lock:
                _last_by_class.pop(res.get("class"), None)
                _sent_today["n"] = max(0, _sent_today["n"] - 1)
        _record(n > 0, detail)
    threading.Thread(target=work, daemon=True).start()
    return True

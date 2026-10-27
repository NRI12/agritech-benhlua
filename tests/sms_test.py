"""Kiểm thử logic SMS bằng modem giả (pty) — chạy: python3 tests/sms_test.py"""
import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "deploy_pi", "server"))
import config  # noqa: E402

config.DATA_DIR = tempfile.mkdtemp()
import sms  # noqa: E402

sms.SETTINGS_FILE = os.path.join(config.DATA_DIR, "sms_settings.json")


def fake_modem(master, log, sim_ready=True, send_ok=True):
    buf = b""
    while True:
        try:
            d = os.read(master, 1024)
        except OSError:
            return
        buf += d
        while True:
            if buf.endswith(b"\x1a"):
                log.append(("body", buf[:-1].decode()))
                os.write(master, b"\r\n+CMGS: 7\r\n\r\nOK\r\n" if send_ok else b"\r\n+CMS ERROR: 331\r\nERROR\r\n")
                buf = b""
                break
            if b"\r" not in buf:
                break
            line, buf = buf.split(b"\r", 1)
            line = line.decode().strip()
            if not line:
                continue
            log.append(("cmd", line))
            if line == "AT+CPIN?":
                os.write(master, b"\r\n+CPIN: " + (b"READY" if sim_ready else b"SIM PIN") + b"\r\n\r\nOK\r\n")
            elif line.startswith("AT+CMGS"):
                os.write(master, b"\r\n> ")
            else:
                os.write(master, b"\r\nOK\r\n")


def with_modem(**kw):
    master, slave = os.openpty()
    log = []
    threading.Thread(target=fake_modem, args=(master, log), kwargs=kw, daemon=True).start()
    os.environ["SMS_AT_PORT"] = os.ttyname(slave)
    return log, (master, slave)


fails = 0


def check(name, cond):
    global fails
    print(("PASS " if cond else "FAIL ") + name)
    fails += 0 if cond else 1


# số điện thoại & cài đặt
check("0912345678 -> +84912345678", sms.normalize_phone("0912 345 678") == "+84912345678")
check("số sai bị từ chối", sms.normalize_phone("123") is None)
s, err = sms.save_settings({"enabled": True, "phones": ""})
check("bật mà không có số bị từ chối", s is None and err)
s, err = sms.save_settings({"enabled": True, "phones": "0912345678, +84987654321", "min_conf": 70})
check("lưu cài đặt hợp lệ", err is None and s["phones"] == ["+84912345678", "+84987654321"] and s["min_conf"] == 70)

# nội dung
msg = sms.build_message({"class_vi": "Đạo ôn lá", "confidence": 91.3, "severity": "Trung bình"})
check("tin nhắn không dấu, <=160", msg.isascii() and len(msg) <= 160 and "dao on la".lower() in msg.lower())

# gửi qua modem giả
log, fds = with_modem()
ok, d = sms.send_sms("+84912345678", "hello")
check("gửi thành công", ok and any(c == ("body", "hello") for c in log) and ("cmd", 'AT+CMGS="+84912345678"') in log)
log, fds = with_modem(sim_ready=False)
ok, d = sms.send_sms("+84912345678", "hello")
check("SIM chưa sẵn sàng báo lỗi rõ", (not ok) and "SIM" in d)
log, fds = with_modem(send_ok=False)
ok, d = sms.send_sms("+84912345678", "hello")
check("modem báo lỗi gửi -> thất bại", not ok)
os.environ["SMS_AT_PORT"] = "/dev/khong_co"
ok, d = sms.send_sms("+84912345678", "hello")
check("không có cổng AT báo lỗi rõ", (not ok) and "cổng AT" in d)

# điều kiện kích hoạt
S = sms.load_settings()
R = {"class": "blast", "confidence": 91.0, "is_rice": True}
sms._last_by_class.clear(); sms._sent_today.update(day="", n=0)
check("camera + bệnh -> gửi", sms.should_alert(R, "camera", S, 1000.0)[0])
check("lặp lại trong cooldown -> không", not sms.should_alert(R, "camera", S, 1000.0 + 60)[0])
check("hết cooldown -> gửi", sms.should_alert(R, "camera", S, 1000.0 + 7300)[0])
check("bệnh khác -> gửi", sms.should_alert(dict(R, **{"class": "tungro"}), "camera", S, 1000.0 + 7300)[0])
check("ảnh tải lên mặc định không gửi", not sms.should_alert(dict(R, **{"class": "hispa"}), "upload", S, 9e5)[0])
check("normal không gửi", not sms.should_alert(dict(R, **{"class": "normal"}), "camera", S, 9e5)[0])
check("không phải lúa không gửi", not sms.should_alert(dict(R, is_rice=False, **{"class": "brown_spot"}), "camera", S, 9e5)[0])
check("độ tin cậy thấp không gửi", not sms.should_alert(dict(R, confidence=50.0, **{"class": "brown_spot"}), "camera", S, 9e5)[0])
S2 = dict(S, enabled=False)
check("tắt -> không gửi", not sms.should_alert(dict(R, **{"class": "brown_spot"}), "camera", S2, 9e5)[0])
S3 = dict(S, daily_max=2)
sms._last_by_class.clear(); sms._sent_today.update(day="", n=0)
a = [sms.should_alert(dict(R, **{"class": c}), "camera", S3, 5e6)[0] for c in ("blast", "tungro", "hispa")]
check("giới hạn tin/ngày", a == [True, True, False])
sys.exit(1 if fails else 0)

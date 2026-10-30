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
s, err = sms.save_settings({"enabled": True, "phones": "0912345678, +84987654321"})
check("lưu cài đặt hợp lệ", err is None and s["phones"] == ["+84912345678", "+84987654321"])

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

# điều kiện kích hoạt: gửi mỗi lần phát hiện bệnh, không ngưỡng/chờ/giới hạn
S = sms.load_settings()
R = {"class": "blast", "confidence": 91.0, "is_rice": True}
check("camera + bệnh -> gửi", sms.should_alert(R, "camera", S)[0])
check("lặp lại ngay -> vẫn gửi", all(sms.should_alert(R, "camera", S)[0] for _ in range(20)))
check("ảnh tải lên + bệnh -> gửi", sms.should_alert(R, "upload", S)[0])
check("độ tin cậy thấp vẫn gửi", sms.should_alert(dict(R, confidence=5.0), "upload", S)[0])
check("normal không gửi", not sms.should_alert(dict(R, **{"class": "normal"}), "camera", S)[0])
check("không phải lúa không gửi", not sms.should_alert(dict(R, is_rice=False), "camera", S)[0])
check("tắt -> không gửi", not sms.should_alert(R, "camera", dict(S, enabled=False))[0])
_, err = sms.save_settings({"enabled": True, "phones": "0912345678", "min_conf": 60, "daily_max": 3})
check("cài đặt chỉ còn enabled + phones", err is None and set(sms.load_settings()) == {"enabled", "phones"})
sys.exit(1 if fails else 0)

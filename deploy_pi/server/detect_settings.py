"""Cài đặt nhận diện chỉnh trên giao diện (Cài đặt > Nhận diện), áp dụng ngay cho lần phân tích kế tiếp.

Lưu ở data/detect_settings.json:
  rice_filter: bật bộ lọc "không phải ảnh lúa" (màu thực vật / entropy / độ tin cậy, xem config.RICE_*)
"""
import json
import os
import threading

import config

SETTINGS_FILE = os.path.join(config.DATA_DIR, "detect_settings.json")
DEFAULTS = {"rice_filter": True}

_lock = threading.Lock()
_settings = None                  # nạp lười từ file, sau đó giữ trong RAM


def load_settings():
    global _settings
    with _lock:
        if _settings is None:
            s = dict(DEFAULTS)
            try:
                with open(SETTINGS_FILE, encoding="utf-8") as f:
                    s.update({k: v for k, v in json.load(f).items() if k in DEFAULTS})
            except (OSError, ValueError, AttributeError):
                pass
            _settings = s
        return dict(_settings)


def save_settings(data):
    """Lưu và áp dụng ngay. Trả settings mới."""
    global _settings
    s = load_settings()
    if "rice_filter" in data:
        s["rice_filter"] = bool(data["rice_filter"])
    os.makedirs(config.DATA_DIR, exist_ok=True)
    with _lock:
        tmp = SETTINGS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
        os.replace(tmp, SETTINGS_FILE)
        _settings = s
    return dict(s)


def rice_filter_enabled():
    return load_settings()["rice_filter"]

"""Lịch sử các lần nhận diện (JSON Lines, lưu ở data/history.jsonl).

Camera chạy liên tục nên chỉ ghi khi kết quả đổi hoặc đã qua MIN_GAP giây,
tránh phình file. Ảnh người dùng tải lên luôn được ghi. File tự cắt gọn khi vượt MAX_LINES.
"""
import json
import os
import threading
import time

import config

PATH = os.path.join(config.DATA_DIR, "history.jsonl")
MIN_GAP = 60          # giây: cùng 1 kết quả camera thì ghi lại tối đa mỗi phút
MAX_LINES = 2000
_lock = threading.Lock()
_last = {"key": None, "ts": 0}


def record(result, source):
    """result: dict kết quả (class, class_vi, confidence, severity). source: camera|upload."""
    if not result.get("class"):
        return
    now = time.time()
    key = (source, result["class"])
    with _lock:
        if source == "camera":
            if result["class"] == config.NOT_RICE:
                return
            if key == _last["key"] and now - _last["ts"] < MIN_GAP:
                return
            _last.update(key=key, ts=now)
        row = {"ts": now, "source": source, "class": result["class"],
               "class_vi": result.get("class_vi"), "confidence": result.get("confidence"),
               "severity": result.get("severity")}
        os.makedirs(config.DATA_DIR, exist_ok=True)
        with open(PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        _trim()


def _trim():
    try:
        with open(PATH, encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > MAX_LINES:
            tmp = PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.writelines(lines[-MAX_LINES // 2:])
            os.replace(tmp, PATH)
    except OSError:
        pass


def read(limit=100):
    """Mới nhất trước."""
    with _lock:
        try:
            with open(PATH, encoding="utf-8") as f:
                lines = f.readlines()
        except OSError:
            return []
    rows = []
    for ln in lines[-limit:]:
        try:
            rows.append(json.loads(ln))
        except ValueError:
            pass
    return rows[::-1]

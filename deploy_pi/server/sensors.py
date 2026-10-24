"""Mock dữ liệu cảm biến môi trường & dinh dưỡng đất.

Hiện chưa có phần cứng cảm biến thật nên sinh số ngẫu nhiên nhẹ quanh giá
trị baseline thực tế của ruộng lúa. Khi cắm cảm biến thật (NPK qua RS485/
Modbus, DHT22/SHT cho nhiệt-ẩm...), chỉ cần thay thân hàm read_sensors()
bằng phần đọc I2C/UART/ADC tương ứng — phần còn lại của hệ thống giữ nguyên.
"""
import os
import random


def _badge(value, good_range, mid_range):
    """Trả nhãn trạng thái theo khoảng giá trị."""
    lo, hi = good_range
    if lo <= value <= hi:
        return {"label": "Đạt", "level": "green"}
    mlo, mhi = mid_range
    if mlo <= value <= mhi:
        return {"label": "Trung bình", "level": "blue"}
    return {"label": "Cần chú ý", "level": "red"}


def read_sensors():
    """Đọc 1 lần snapshot cảm biến.

    • Dinh dưỡng đất (N, P, K, pH): giữ nguyên dữ liệu giả lập như bản đầu.
    • Nhiệt độ / độ ẩm: chưa cắm thiết bị thật nên mặc định available=False — dashboard
      báo "Thiết bị chưa sẵn sàng" thay vì số giả. Đặt SENSORS_MOCK=1 để sinh số giả lập.

    >>> KHI CÓ PHẦN CỨNG: thay các giá trị giả bằng code đọc NPK (RS485/Modbus), DHT22/SHT... <<<
    """
    n = round(random.uniform(26.0, 31.0), 1)
    p = round(random.uniform(13.0, 18.0), 1)
    k = round(random.uniform(16.0, 21.0), 1)
    ph = round(random.uniform(6.0, 6.8), 1)

    out = {
        "available": False,
        "message": "Cảm biến nhiệt độ & độ ẩm chưa sẵn sàng (chưa kết nối).",
        "n":  {"value": n,  "unit": "mg/kg", "badge": _badge(n,  (25, 35), (20, 25))},
        "p":  {"value": p,  "unit": "mg/kg", "badge": _badge(p,  (16, 25), (10, 16))},
        "k":  {"value": k,  "unit": "mg/kg", "badge": _badge(k,  (15, 25), (10, 15))},
        "ph": {"value": ph, "unit": "pH",    "badge": _badge(ph, (6.0, 7.0), (5.5, 6.0))},
    }
    if os.environ.get("SENSORS_MOCK") == "1":
        out.update({
            "available": True,
            "mock": True,
            "temp":     {"value": round(random.uniform(27.5, 31.5), 1), "unit": "°C"},
            "humidity": {"value": round(random.uniform(60.0, 72.0)), "unit": "%"},
        })
    return out


if __name__ == "__main__":
    import json
    print(json.dumps(read_sensors(), ensure_ascii=False, indent=2))

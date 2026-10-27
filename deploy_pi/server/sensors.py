"""Dữ liệu cảm biến.

• Nhiệt độ: DS18B20 (1-Wire, GPIO25) đọc thật qua /sys/bus/w1/devices/28-*/w1_slave.
• Độ ẩm đất: cảm biến điện trở (module LM393, chân AO) nối kênh A0 của ADS1115 (I2C 0x48).
• Độ ẩm không khí: chưa có cảm biến -> báo chưa sẵn sàng (không sinh số giả).
• Dinh dưỡng đất N, P, K, pH: giữ nguyên dữ liệu giả lập như bản đầu.

Biến môi trường (tuỳ chọn):
  SOIL_ADC_CH=0          kênh ADS1115 của cảm biến đất
  SOIL_DRY_V, SOIL_WET_V điện áp AO khi khô (trong không khí) / khi ướt (nhúng nước) để quy ra %.
                         Chưa đặt -> chỉ hiện điện áp thô, KHÔNG bịa phần trăm.
  ADS1115_ADDR=0x48, I2C_BUS=1
  SENSORS_MOCK=1         sinh số giả lập cho nhiệt độ / độ ẩm không khí
"""
import glob
import os
import random
import time

W1_GLOB = "/sys/bus/w1/devices/28-*/w1_slave"


def _badge(value, good_range, mid_range):
    """Trả nhãn trạng thái theo khoảng giá trị."""
    lo, hi = good_range
    if lo <= value <= hi:
        return {"label": "Đạt", "level": "green"}
    mlo, mhi = mid_range
    if mlo <= value <= mhi:
        return {"label": "Trung bình", "level": "blue"}
    return {"label": "Cần chú ý", "level": "red"}


def read_ds18b20():
    """Trả {'available', 'value'|'message'}. Không ném lỗi."""
    files = glob.glob(W1_GLOB)
    if not files:
        if not os.path.isdir("/sys/bus/w1/devices"):
            msg = "Chưa bật 1-Wire (thêm dtoverlay=w1-gpio,gpiopin=25 vào /boot/firmware/config.txt rồi khởi động lại)"
        else:
            msg = "Không thấy DS18B20 (kiểm tra dây DQ GPIO25 (chân 22), khớp gpiopin trong dtoverlay, điện trở kéo lên 4.7k, nguồn)"
        return {"available": False, "message": msg}
    try:
        with open(files[0]) as f:
            lines = f.read().strip().splitlines()
        if len(lines) < 2 or not lines[0].endswith("YES"):
            return {"available": False, "message": "DS18B20 trả dữ liệu lỗi CRC (dây lỏng/nhiễu)"}
        t = int(lines[1].split("t=")[1]) / 1000.0
        if t == 85.0 or t < -55 or t > 125:
            return {"available": False, "message": "DS18B20 chưa chuyển đổi xong hoặc trả giá trị không hợp lệ"}
        return {"available": True, "value": round(t, 1), "unit": "°C"}
    except (OSError, ValueError, IndexError) as e:
        return {"available": False, "message": f"Lỗi đọc DS18B20: {e}"}


def _ads_read_volt(ch, addr, busno):
    """Đọc single-ended 1 kênh ADS1115, PGA ±4.096 V, trung bình 5 mẫu."""
    try:
        from smbus2 import SMBus
    except ImportError:
        from smbus import SMBus
    vals = []
    with SMBus(busno) as bus:
        for _ in range(5):
            cfg = 0x8000 | ((0b100 + ch) << 12) | (0b001 << 9) | (1 << 8) | (0b100 << 5) | 0b11
            bus.write_i2c_block_data(addr, 0x01, [cfg >> 8, cfg & 0xFF])
            time.sleep(0.012)
            hi, lo = bus.read_i2c_block_data(addr, 0x00, 2)
            raw = (hi << 8) | lo
            if raw & 0x8000:
                raw -= 1 << 16
            vals.append(raw * 4.096 / 32768.0)
    return sum(vals) / len(vals)


def read_soil_moisture():
    ch = int(os.environ.get("SOIL_ADC_CH", "0"))
    addr = int(os.environ.get("ADS1115_ADDR", "0x48"), 0)
    busno = int(os.environ.get("I2C_BUS", "1"))
    try:
        v = _ads_read_volt(ch, addr, busno)
    except ImportError:
        return {"available": False, "message": "Thiếu thư viện smbus2 (pip install smbus2)"}
    except OSError as e:
        return {"available": False, "message": f"Không đọc được ADS1115 0x{addr:02x}: {e} (bật I2C, kiểm tra dây SDA/SCL)"}
    out = {"available": True, "volt": round(v, 3), "unit": "%"}
    dry, wet = os.environ.get("SOIL_DRY_V"), os.environ.get("SOIL_WET_V")
    try:
        dry, wet = float(dry), float(wet)
    except (TypeError, ValueError):
        dry = wet = None
    if dry is None or dry == wet:
        out["calibrated"] = False
        out["message"] = f"Chưa hiệu chuẩn: {v:.2f} V (đặt SOIL_DRY_V / SOIL_WET_V)"
    else:
        pct = (dry - v) / (dry - wet) * 100.0
        out["calibrated"] = True
        out["value"] = round(max(0.0, min(100.0, pct)))
    return out


def read_sensors():
    """Đọc 1 lần snapshot cảm biến (mỗi cảm biến có available riêng)."""
    n = round(random.uniform(26.0, 31.0), 1)
    p = round(random.uniform(13.0, 18.0), 1)
    k = round(random.uniform(16.0, 21.0), 1)
    ph = round(random.uniform(6.0, 6.8), 1)

    mock = os.environ.get("SENSORS_MOCK") == "1"
    temp = read_ds18b20()
    if not temp["available"] and mock:
        temp = {"available": True, "mock": True, "value": round(random.uniform(27.5, 31.5), 1), "unit": "°C"}
    hum = {"available": False, "message": "Chưa có cảm biến độ ẩm không khí"}
    if mock:
        hum = {"available": True, "mock": True, "value": round(random.uniform(60.0, 72.0)), "unit": "%"}
    out = {
        "available": bool(temp["available"] or hum["available"]),
        "temp": temp,
        "humidity": hum,
        "soil_moisture": read_soil_moisture(),
        "n":  {"value": n,  "unit": "mg/kg", "badge": _badge(n,  (25, 35), (20, 25))},
        "p":  {"value": p,  "unit": "mg/kg", "badge": _badge(p,  (16, 25), (10, 16))},
        "k":  {"value": k,  "unit": "mg/kg", "badge": _badge(k,  (15, 25), (10, 15))},
        "ph": {"value": ph, "unit": "pH",    "badge": _badge(ph, (6.0, 7.0), (5.5, 6.0))},
    }
    return out


if __name__ == "__main__":
    import json
    print(json.dumps(read_sensors(), ensure_ascii=False, indent=2))

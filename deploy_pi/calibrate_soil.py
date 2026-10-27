#!/usr/bin/env python3
"""Hiệu chuẩn cảm biến độ ẩm đất (ADS1115) và ghi SOIL_DRY_V / SOIL_WET_V vào agritech.env.

    python3 calibrate_soil.py                 # kênh A0, 0x48, bus 1
    python3 calibrate_soil.py --channel 0 --env /đường/dẫn/agritech.env

Hai bước: (1) để cảm biến khô trong không khí, (2) nhúng phần hai chân kim loại vào nước
(không nhúng phần mạch xanh/linh kiện). Mỗi bước lấy trung bình ~5 giây và chỉ nhận khi số đã ổn định.
Sau đó chạy lại server (./install.sh --restart) để áp dụng.
"""
import argparse
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from probe_ads1115 import SMBus, read_channel  # noqa: E402


def sample(bus, addr, ch, seconds=5.0):
    vals, t0 = [], time.time()
    while time.time() - t0 < seconds:
        vals.append(read_channel(bus, addr, ch)[1])
        time.sleep(0.1)
    return statistics.mean(vals), (max(vals) - min(vals))


def measure(bus, addr, ch, label):
    input(f"\n{label}\nXong thì nhấn Enter để đo...")
    for _ in range(3):
        mean, spread = sample(bus, addr, ch)
        if spread <= 0.05:
            print(f"  -> {mean:.3f} V (dao động {spread * 1000:.0f} mV, ổn định)")
            return mean
        print(f"  số còn dao động {spread * 1000:.0f} mV, giữ yên cảm biến thêm chút, đo lại...")
    sys.exit("Số đo không ổn định (dao động > 50 mV). Kiểm tra dây AO/GND/VCC rồi chạy lại.")


def env_set(path, key, val):
    lines = open(path, encoding="utf-8").read().splitlines() if os.path.exists(path) else []
    lines = [ln for ln in lines if not ln.startswith(key + "=")] + [f"{key}={val}"]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--addr", default="0x48")
    ap.add_argument("--bus", type=int, default=1)
    ap.add_argument("--channel", type=int, default=0)
    ap.add_argument("--env", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "agritech.env"))
    a = ap.parse_args()
    addr = int(a.addr, 0)
    try:
        with SMBus(a.bus) as bus:
            dry = measure(bus, addr, a.channel, "BƯỚC 1/2 — KHÔ: để cảm biến ngoài không khí, lau khô hai chân kim loại.")
            wet = measure(bus, addr, a.channel, "BƯỚC 2/2 — ƯỚT: nhúng hai chân kim loại vào nước (không nhúng phần mạch).")
    except OSError as e:
        sys.exit(f"Lỗi đọc I2C 0x{addr:02x}: {e} (bật I2C, kiểm tra dây SDA/SCL)")
    if dry - wet < 0.3:
        sys.exit(f"Chênh lệch khô ({dry:.3f} V) - ướt ({wet:.3f} V) quá nhỏ (< 0.3 V): cảm biến chưa nhúng nước, "
                 "đứt dây AO hoặc không phải cảm biến này. KHÔNG ghi gì. Chạy lại sau khi kiểm tra.")
    env_set(a.env, "SOIL_DRY_V", f"{dry:.3f}")
    env_set(a.env, "SOIL_WET_V", f"{wet:.3f}")
    print(f"\nĐã ghi vào {a.env}: SOIL_DRY_V={dry:.3f}  SOIL_WET_V={wet:.3f}")
    print("Chạy lại server để áp dụng: ./install.sh --restart")


if __name__ == "__main__":
    main()

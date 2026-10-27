#!/usr/bin/env python3
"""Đọc điện áp 4 kênh ADS1115 (A0-A3) để biết cảm biến analog nào đang cắm.

    pip install smbus2            # hoặc: sudo apt install -y python3-smbus
    python3 probe_ads1115.py              # đọc 1 lần, địa chỉ 0x48, bus 1
    python3 probe_ads1115.py --watch      # đọc liên tục (Ctrl+C dừng) để thử nhúng/chạm cảm biến
    python3 probe_ads1115.py --addr 0x49 --bus 1

Chỉ ĐỌC, không ghi gì ngoài thanh ghi cấu hình của chính ADS1115.
Lưu ý an toàn: điện áp đưa vào chân A0-A3 không được vượt quá điện áp cấp (VDD) của ADS1115 + 0.3V.
"""
import argparse
import sys
import time

try:
    from smbus2 import SMBus
except ImportError:                       # python3-smbus của apt
    try:
        from smbus import SMBus
    except ImportError:
        sys.exit("Thiếu thư viện: pip install smbus2   (hoặc sudo apt install -y python3-smbus)")

REG_CONV, REG_CONFIG = 0x00, 0x01
PGA_FS = 4.096                            # ±4.096 V (PGA = 001) — đủ cho cảm biến 3.3V
SAMPLE_S = 0.012                          # 128 SPS ≈ 8 ms chuyển đổi, chờ dư


def read_channel(bus, addr, ch):
    """Đọc single-ended kênh ch (0-3). Trả (raw, volt)."""
    cfg = (0x8000                         # OS=1: bắt đầu chuyển đổi
           | ((0b100 + ch) << 12)         # MUX: AINch so với GND
           | (0b001 << 9)                 # PGA ±4.096V
           | (1 << 8)                     # chế độ single-shot
           | (0b100 << 5)                 # 128 SPS
           | 0b11)                        # tắt comparator
    bus.write_i2c_block_data(addr, REG_CONFIG, [cfg >> 8, cfg & 0xFF])
    time.sleep(SAMPLE_S)
    hi, lo = bus.read_i2c_block_data(addr, REG_CONV, 2)
    raw = (hi << 8) | lo
    if raw & 0x8000:
        raw -= 1 << 16
    return raw, raw * PGA_FS / 32768.0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--addr", default="0x48")
    ap.add_argument("--bus", type=int, default=1)
    ap.add_argument("--watch", action="store_true")
    a = ap.parse_args()
    addr = int(a.addr, 0)

    with SMBus(a.bus) as bus:
        try:
            while True:
                row = []
                for ch in range(4):
                    # trung bình 5 mẫu cho đỡ nhiễu
                    vals = [read_channel(bus, addr, ch)[1] for _ in range(5)]
                    row.append(sum(vals) / len(vals))
                print("  ".join(f"A{c}={v:6.3f} V" for c, v in enumerate(row)))
                if not a.watch:
                    break
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        except OSError as e:
            sys.exit(f"Lỗi đọc I2C 0x{addr:02x} bus {a.bus}: {e} (kiểm tra dây SDA/SCL, nguồn, địa chỉ)")


if __name__ == "__main__":
    main()

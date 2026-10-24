#!/usr/bin/env bash
# Kiểm tra thiết bị / cổng I/O trên Raspberry Pi mà Agritech sử dụng.
#
#   ./check_hardware.sh             kiểm tra và in báo cáo
#   ./install.sh --check            giống trên (gọi qua install.sh)
#
# Mã thoát: 0 = không có mục BẮT BUỘC nào thiếu, 1 = thiếu mục bắt buộc (không có camera nào dùng được).
# Mục tuỳ chọn (cảm biến, 4G, I2C...) chỉ cảnh báo vì code cảm biến thật chưa được viết
# (sensors.py đang để trống chờ cắm NPK RS485/Modbus, DHT22/SHT3x).
#
# Script chỉ ĐỌC trạng thái, không thay đổi hệ thống. Chạy được cả trên máy không phải Pi
# (các mục riêng của Pi sẽ báo "không áp dụng").

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PYTHON:-$APP_DIR/.venv/bin/python}"; [ -x "$PY" ] || PY="$(command -v python3)"
ENV_FILE="$APP_DIR/agritech.env"
CAMERA_SRC="auto"; USB_IDX=0
if [ -f "$ENV_FILE" ]; then
  CAMERA_SRC="$(grep -E '^CAMERA_SOURCE=' "$ENV_FILE" | tail -1 | cut -d= -f2)"; CAMERA_SRC="${CAMERA_SRC:-auto}"
  USB_IDX="$(grep -E '^USB_CAMERA_INDEX=' "$ENV_FILE" | tail -1 | cut -d= -f2)"; USB_IDX="${USB_IDX:-0}"
fi

RUN_USER="${SUDO_USER:-$(id -un)}"
FAIL=0; WARN=0

ok()   { printf '  \033[1;32m[ OK ]\033[0m %s\n' "$*"; }
warn() { printf '  \033[1;33m[WARN]\033[0m %s\n' "$*"; WARN=$((WARN+1)); }
bad()  { printf '  \033[1;31m[MISS]\033[0m %s\n' "$*"; }
info() { printf '  \033[0;36m[ .. ]\033[0m %s\n' "$*"; }
head_() { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }
in_group() { id -nG "$RUN_USER" 2>/dev/null | tr ' ' '\n' | grep -qx "$1"; }

IS_PI=0
[ -r /proc/device-tree/model ] && tr -d '\0' < /proc/device-tree/model | grep -qi "raspberry" && IS_PI=1

# ── 1. Bo mạch & nguồn ───────────────────────────────────────────────────────
head_ "Bo mạch"
if [ "$IS_PI" -eq 1 ]; then
  MODEL="$(tr -d '\0' < /proc/device-tree/model)"
  ok "$MODEL"
  case "$MODEL" in *"Pi 4"*|*"Pi 5"*) ;; *) warn "Khuyến nghị Raspberry Pi 4 trở lên (model chạy ONNX trên CPU)";; esac
else
  info "Không phải Raspberry Pi ($(uname -m)) — bỏ qua các kiểm tra riêng của Pi"
fi
case "$(uname -m)" in aarch64|arm64|x86_64) ok "Hệ điều hành 64-bit ($(uname -m))";; *) warn "Hệ điều hành 32-bit ($(uname -m)): onnxruntime có thể không có wheel";; esac
MEM_MB=$(awk '/MemTotal/{printf "%d",$2/1024}' /proc/meminfo)
[ "${MEM_MB:-0}" -ge 3500 ] && ok "RAM ${MEM_MB} MB" || warn "RAM ${MEM_MB} MB (khuyến nghị >= 4 GB)"
FREE_MB=$(df -Pm "$APP_DIR" | awk 'NR==2{print $4}')
[ "${FREE_MB:-0}" -ge 1500 ] && ok "Dung lượng trống ${FREE_MB} MB" || warn "Dung lượng trống chỉ ${FREE_MB} MB (cần ~1.5 GB cho thư viện)"
if have vcgencmd; then
  T="$(vcgencmd measure_temp 2>/dev/null | sed 's/temp=//')"; [ -n "$T" ] && info "Nhiệt độ CPU $T"
  TH="$(vcgencmd get_throttled 2>/dev/null | cut -d= -f2)"
  if [ -n "$TH" ]; then
    [ "$TH" = "0x0" ] && ok "Nguồn điện ổn định (không bị giảm xung)" \
      || warn "Từng bị sụt áp/giảm xung (get_throttled=$TH) — kiểm tra adapter 5V/3A và dây cấp nguồn"
  fi
fi

# ── 2. Camera (BẮT BUỘC: ít nhất 1 cái) ─────────────────────────────────────
head_ "Camera (cấu hình CAMERA_SOURCE=$CAMERA_SRC, USB index=$USB_IDX)"
CSI_OK=0; USB_OK=0

# CSI qua libcamera/picamera2 (đúng đường code camera.py dùng)
LC=""; have rpicam-hello && LC=rpicam-hello; [ -z "$LC" ] && have libcamera-hello && LC=libcamera-hello
if "$PY" -c "import picamera2" >/dev/null 2>&1; then
  CSI_OUT="$("$PY" - <<'EOF' 2>/dev/null
try:
    from picamera2 import Picamera2
    cams = Picamera2.global_camera_info()
    print(len(cams), *[c.get("Model", "?") for c in cams])
except Exception as e:
    print("ERR", e)
EOF
)"
  case "$CSI_OUT" in
    "0"*|ERR*|"") if [ "$IS_PI" -eq 1 ]; then warn "picamera2 có nhưng không thấy camera CSI ${CSI_OUT:+($CSI_OUT)} — kiểm tra cáp ribbon (đúng chiều, cắm chặt hai đầu)"; else info "picamera2 có nhưng không thấy camera CSI"; fi;;
    *) CSI_OK=1; ok "Camera CSI: $CSI_OUT";;
  esac
else
  if [ "$IS_PI" -eq 1 ]; then warn "Chưa cài python3-picamera2 (sudo apt install -y python3-picamera2) — camera CSI không dùng được"
  else info "picamera2 không có trên máy này"; fi
fi
[ -n "$LC" ] && [ "$CSI_OK" -eq 0 ] && "$LC" --list-cameras 2>&1 | grep -qE "^[0-9]+ :" && { CSI_OK=1; ok "libcamera thấy camera CSI"; }

# USB webcam qua V4L2 / OpenCV
VIDEO_DEVS="$(ls /dev/video* 2>/dev/null | tr '\n' ' ')"
if [ -n "$VIDEO_DEVS" ]; then
  info "Thiết bị video: $VIDEO_DEVS"
  have v4l2-ctl && v4l2-ctl --list-devices 2>/dev/null | grep -vE "^\s*/dev/|^$" | sed 's/^/        /' | head -8
  # Webcam đang bị tiến trình khác giữ (thường là chính service agritech) -> không mở thử được
  BUSY="$(fuser "/dev/video$USB_IDX" 2>/dev/null | tr -s ' ')"
  if [ -n "$BUSY" ]; then
    USB_OK=1
    ok "Webcam /dev/video$USB_IDX đang được tiến trình khác sử dụng (PID$BUSY) — coi như hoạt động (nếu là service agritech thì camera đang chạy)"
  elif "$PY" -c "import cv2" >/dev/null 2>&1; then
    FR="$("$PY" - "$USB_IDX" <<'EOF' 2>/dev/null
import sys, cv2
cap = cv2.VideoCapture(int(sys.argv[1]))
ok, f = cap.read() if cap.isOpened() else (False, None)
cap.release()
print(f"{f.shape[1]}x{f.shape[0]}" if ok and f is not None else "NOFRAME")
EOF
)"
    if [ -n "$FR" ] && [ "$FR" != "NOFRAME" ]; then USB_OK=1; ok "Webcam USB index $USB_IDX đọc được khung hình ($FR)"
    else warn "Có /dev/video* nhưng index $USB_IDX không đọc được khung hình (thử đổi USB_CAMERA_INDEX; thiết bị CSI cũng hiện thành /dev/video* nên có thể không phải webcam)"; fi
  else
    warn "Chưa cài OpenCV trong môi trường Python — không thử mở webcam được (chạy install.sh trước)"
  fi
  in_group video || warn "User $RUN_USER chưa thuộc nhóm 'video' (sudo usermod -aG video $RUN_USER rồi đăng nhập lại)"
else
  info "Không có /dev/video* (không có webcam USB)"
fi

case "$CAMERA_SRC" in
  picam) [ "$CSI_OK" -eq 1 ] && ok "Đúng cấu hình: dùng camera CSI" || { bad "CAMERA_SOURCE=picam nhưng không có camera CSI"; FAIL=1; };;
  usb)   [ "$USB_OK" -eq 1 ] && ok "Đúng cấu hình: dùng webcam USB" || { bad "CAMERA_SOURCE=usb nhưng webcam USB không hoạt động"; FAIL=1; };;
  *)     if [ "$CSI_OK" -eq 1 ] || [ "$USB_OK" -eq 1 ]; then ok "Chế độ auto: có ít nhất 1 camera dùng được"
         else bad "Không có camera nào dùng được (dashboard vẫn chạy và vẫn phân tích ảnh tải lên, nhưng nút 'Chụp & phân tích' sẽ báo lỗi)"; FAIL=1; fi;;
esac

# ── 3. Cổng cho cảm biến (tuỳ chọn — code cảm biến thật chưa viết) ─────────
head_ "Cổng cảm biến (tuỳ chọn: NPK RS485/Modbus, DHT22/SHT3x)"
# RS485 -> USB-RS485 (/dev/ttyUSB*, /dev/ttyACM*) hoặc UART trên chân GPIO (/dev/serial0, /dev/ttyAMA0)
SER="$(ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null | tr '\n' ' ')"
if [ -n "$SER" ]; then
  ok "Cổng serial USB: $SER"
  in_group dialout && ok "User $RUN_USER thuộc nhóm 'dialout' (được đọc cổng serial)" \
    || warn "User $RUN_USER chưa thuộc nhóm 'dialout' — cần để đọc RS485: sudo usermod -aG dialout $RUN_USER"
else
  info "Không thấy bộ chuyển USB-RS485 (/dev/ttyUSB*, /dev/ttyACM*) — cảm biến NPK chưa cắm"
fi
if [ -e /dev/serial0 ]; then info "UART trên chân GPIO: /dev/serial0 -> $(readlink -f /dev/serial0)"
elif [ "$IS_PI" -eq 1 ]; then info "UART GPIO chưa bật (raspi-config > Interface > Serial Port, nếu dùng module RS485 HAT)"; fi

# I2C (SHT3x, ADC...)
if [ -e /dev/i2c-1 ]; then
  ok "I2C đã bật (/dev/i2c-1)"
  if have i2cdetect; then
    ADDR="$(i2cdetect -y 1 2>/dev/null | awk 'NR>1{for(i=2;i<=NF;i++) if($i!="--") print $i}' | tr '\n' ' ')"
    [ -n "$ADDR" ] && ok "Thiết bị I2C: $ADDR" || info "Bus I2C trống — chưa cắm cảm biến I2C (SHT3x...)"
  else
    info "Chưa cài i2c-tools (sudo apt install -y i2c-tools) để dò thiết bị I2C"
  fi
elif [ "$IS_PI" -eq 1 ]; then
  info "I2C chưa bật (sudo raspi-config > Interface Options > I2C) — chỉ cần nếu dùng SHT3x/ADC"
fi
# GPIO (DHT22)
if [ -e /dev/gpiomem ] || [ -e /dev/gpiochip0 ]; then
  ok "GPIO truy cập được"
  in_group gpio || warn "User $RUN_USER chưa thuộc nhóm 'gpio' (cần nếu đọc DHT22: sudo usermod -aG gpio $RUN_USER)"
elif [ "$IS_PI" -eq 1 ]; then warn "Không thấy /dev/gpiomem"; fi

# ── 4. Mạng / 4G ────────────────────────────────────────────────────────────
head_ "Mạng & 4G (cần cho ChatGPT, Cloudflare Tunnel)"
if lsusb 2>/dev/null | grep -qiE "1e0e:|SIMCOM|SIM7600"; then
  ok "Phát hiện modem 4G SIMCom (SIM7600)"
  PORTS="$(ls /dev/ttyUSB* 2>/dev/null | tr '\n' ' ')"; [ -n "$PORTS" ] && info "Cổng AT/diag của modem: $PORTS"
else
  info "Không thấy modem SIM7600 qua USB (bỏ qua nếu dùng WiFi/Ethernet)"
fi
IFACES="$(ip -o link show 2>/dev/null | awk -F': ' '{print $2}' | grep -vE '^(lo|docker|veth|br-)' | tr '\n' ' ')"
info "Giao diện mạng: $IFACES"
if ip -o link show 2>/dev/null | grep -qE "wwan0|usb0|ppp0"; then ok "Có giao diện 4G (wwan0/usb0/ppp0)"; fi
if have curl; then
  if curl -fsS --max-time 6 -o /dev/null https://api.openai.com/ 2>/dev/null || curl -sS --max-time 6 -o /dev/null -w '%{http_code}' https://api.openai.com/ 2>/dev/null | grep -qE '^[1-5][0-9][0-9]$'; then
    ok "Kết nối được tới api.openai.com"
  else
    warn "Không tới được api.openai.com — ChatGPT sẽ tự dùng tư vấn có sẵn. Kiểm tra WiFi/4G/DNS"
  fi
fi

# ── 5. Tóm tắt ──────────────────────────────────────────────────────────────
head_ "Tóm tắt"
if [ "$FAIL" -ne 0 ]; then
  printf '  \033[1;31mThiếu thiết bị BẮT BUỘC (camera).\033[0m %d cảnh báo khác.\n' "$WARN"; exit 1
fi
printf '  \033[1;32mThiết bị bắt buộc đã sẵn sàng.\033[0m %d cảnh báo (xem các dòng [WARN] ở trên).\n' "$WARN"
exit 0

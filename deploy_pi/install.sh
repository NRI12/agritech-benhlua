#!/usr/bin/env bash
# Agritech ALL-IN-ONE trên Raspberry Pi 4 (Raspberry Pi OS 64-bit):
#   cài đặt  ->  kiểm tra phần cứng  ->  bật & kiểm tra 4G  ->  khởi động lại server  ->  xác minh
#
#   cd deploy_pi && ./install.sh [tuỳ chọn]
#
# Chế độ (mặc định = cài/cập nhật đầy đủ):
#   (không tham số)           cài đặt đầy đủ + kiểm tra + bật 4G + (khởi động lại) server
#   --restart                 KHÔNG cài lại: kiểm tra + bật lại 4G + khởi động lại server (dùng hằng ngày)
#   --check                   chỉ kiểm tra, KHÔNG đổi gì trong hệ thống (không sudo, không bật 4G)
#   --diag                    chẩn đoán sâu 4G (ping/curl qua usb0, rp_filter, DNS, lệnh AT) — chỉ đọc
#   --uninstall               gỡ service (giữ mã nguồn và .venv)
# Tuỳ chọn:
#   --camera auto|picam|usb   nguồn camera (mặc định: auto)
#   --usb-index N             index webcam USB (mặc định: 0)
#   --port N                  cổng web (mặc định: 5000)
#   --apn TÊN                 APN của SIM 4G (vd: v-internet, m3-world; bỏ trống = để hệ thống tự dò)
#   --no-4g                   không bật/kiểm tra kết nối 4G
#   --tunnel                  cài Cloudflare Tunnel (xem từ xa qua 4G, in URL)
#   --no-service              không tạo service tự khởi động
#   -h, --help                xem trợ giúp
#
# Chạy lại nhiều lần được (idempotent). Không cần chạy bằng sudo — script tự gọi sudo khi cần.
# Mã thoát: 0 = ổn, 1 = lỗi nghiêm trọng, 2 = (chỉ --check) thiếu thiết bị BẮT BUỘC (camera).
set -u

APP_NAME="agritech"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_USER="${SUDO_USER:-$(id -un)}"
VENV_DIR="$APP_DIR/.venv"
ENV_FILE="$APP_DIR/agritech.env"
SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"
TUNNEL_SERVICE_FILE="/etc/systemd/system/${APP_NAME}-tunnel.service"
NM_CON="agritech-4g"

CAMERA="auto"; USB_INDEX="0"; PORT="5000"; APN=""
MODE="install"            # install | restart | check | uninstall
WITH_TUNNEL=0; WITH_SERVICE=1; WITH_4G=1
CAMERA_GIVEN=0; USB_GIVEN=0; PORT_GIVEN=0

# ── Hiển thị ────────────────────────────────────────────────────────────────
WARN=0; FAIL_CAM=0
log()   { printf '\033[1;32m[+]\033[0m %s\n' "$*"; }
ok()    { printf '  \033[1;32m[ OK ]\033[0m %s\n' "$*"; }
warn()  { printf '  \033[1;33m[WARN]\033[0m %s\n' "$*"; WARN=$((WARN+1)); }
bad()   { printf '  \033[1;31m[MISS]\033[0m %s\n' "$*"; }
info()  { printf '  \033[0;36m[ .. ]\033[0m %s\n' "$*"; }
head_() { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }
die()   { printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2; exit 1; }
have()  { command -v "$1" >/dev/null 2>&1; }
in_group() { id -nG "$RUN_USER" 2>/dev/null | tr ' ' '\n' | grep -qx "$1"; }
usage() { awk 'NR>1 { if ($0 !~ /^#/) exit; sub(/^# ?/, ""); print }' "${BASH_SOURCE[0]}"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --camera)     CAMERA="${2:?thiếu giá trị}"; CAMERA_GIVEN=1; shift 2 ;;
    --usb-index)  USB_INDEX="${2:?thiếu giá trị}"; USB_GIVEN=1; shift 2 ;;
    --port)       PORT="${2:?thiếu giá trị}"; PORT_GIVEN=1; shift 2 ;;
    --apn)        APN="${2:?thiếu giá trị}"; shift 2 ;;
    --no-4g)      WITH_4G=0; shift ;;
    --tunnel)     WITH_TUNNEL=1; shift ;;
    --no-service) WITH_SERVICE=0; shift ;;
    --restart)    MODE="restart"; shift ;;
    --check)      MODE="check"; shift ;;
    --diag)       MODE="diag"; shift ;;
    --uninstall)  MODE="uninstall"; shift ;;
    -h|--help)    usage; exit 0 ;;
    *) die "Tuỳ chọn không hợp lệ: $1 (xem --help)" ;;
  esac
done
case "$CAMERA" in auto|picam|usb) ;; *) die "--camera phải là auto|picam|usb" ;; esac
[[ "$PORT" =~ ^[0-9]+$ ]] || die "--port phải là số"
[[ "$USB_INDEX" =~ ^[0-9]+$ ]] || die "--usb-index phải là số"
[[ -z "$APN" || "$APN" =~ ^[A-Za-z0-9._-]+$ ]] || die "--apn chỉ gồm chữ, số, '.', '_', '-'"

# Các chế độ khác --check có thể đổi hệ thống => cần sudo
SUDO=""
if [ "$MODE" != "check" ] && [ "$MODE" != "diag" ] && [ "$(id -u)" -ne 0 ]; then
  have sudo || die "Cần sudo hoặc chạy bằng root"
  SUDO="sudo"
fi

# Đọc cấu hình đã lưu (chế độ --restart/--check dùng lại, tuỳ chọn dòng lệnh thắng)
env_get() { [ -f "$ENV_FILE" ] && grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2-; }
if [ -f "$ENV_FILE" ]; then
  [ "$CAMERA_GIVEN" -eq 0 ] && CAMERA="$(env_get CAMERA_SOURCE)" && CAMERA="${CAMERA:-auto}"
  [ "$USB_GIVEN" -eq 0 ]    && USB_INDEX="$(env_get USB_CAMERA_INDEX)" && USB_INDEX="${USB_INDEX:-0}"
  [ "$PORT_GIVEN" -eq 0 ]   && PORT="$(env_get PORT)" && PORT="${PORT:-5000}"
  [ -z "$APN" ] && APN="$(env_get APN_4G)"
fi

# ═════════════════════════════════════════════════════════════════════════════
# KIỂM TRA PHẦN CỨNG (chỉ đọc)
# ═════════════════════════════════════════════════════════════════════════════
IS_PI=0
[ -r /proc/device-tree/model ] && tr -d '\0' < /proc/device-tree/model | grep -qi "raspberry" && IS_PI=1

py_bin() { if [ -x "$VENV_DIR/bin/python" ]; then echo "$VENV_DIR/bin/python"; else command -v python3; fi; }

check_board() {
  head_ "Bo mạch"
  if [ "$IS_PI" -eq 1 ]; then
    local m; m="$(tr -d '\0' < /proc/device-tree/model)"; ok "$m"
    case "$m" in *"Pi 4"*|*"Pi 5"*) ;; *) warn "Khuyến nghị Raspberry Pi 4 trở lên (model chạy ONNX trên CPU)";; esac
  else
    info "Không phải Raspberry Pi ($(uname -m)) — bỏ qua các kiểm tra riêng của Pi"
  fi
  case "$(uname -m)" in aarch64|arm64|x86_64) ok "Hệ điều hành 64-bit ($(uname -m))";; *) warn "Hệ điều hành 32-bit ($(uname -m)): onnxruntime có thể không có wheel";; esac
  local mem free; mem=$(awk '/MemTotal/{printf "%d",$2/1024}' /proc/meminfo); free=$(df -Pm "$APP_DIR" | awk 'NR==2{print $4}')
  if [ "${mem:-0}" -ge 3500 ]; then ok "RAM ${mem} MB"; else warn "RAM ${mem} MB (khuyến nghị >= 4 GB)"; fi
  if [ "${free:-0}" -ge 1500 ]; then ok "Dung lượng trống ${free} MB"; else warn "Dung lượng trống chỉ ${free} MB (cần ~1.5 GB)"; fi
  if have vcgencmd; then
    local t th
    t="$(vcgencmd measure_temp 2>/dev/null | sed 's/temp=//')"; [ -n "$t" ] && info "Nhiệt độ CPU $t"
    th="$(vcgencmd get_throttled 2>/dev/null | cut -d= -f2)"
    if [ -n "$th" ]; then
      if [ "$th" = "0x0" ]; then ok "Nguồn điện ổn định (không bị giảm xung)"
      else warn "Từng bị sụt áp/giảm xung (get_throttled=$th) — kiểm tra adapter 5V/3A và dây cấp nguồn"; fi
    fi
  fi
}

check_camera() {
  head_ "Camera (CAMERA_SOURCE=$CAMERA, USB index=$USB_INDEX)"
  local PY csi_ok=0 usb_ok=0 lc="" out vids busy fr
  PY="$(py_bin)"
  have rpicam-hello && lc=rpicam-hello; [ -z "$lc" ] && have libcamera-hello && lc=libcamera-hello
  if "$PY" -c "import picamera2" >/dev/null 2>&1; then
    out="$("$PY" - <<'EOF' 2>/dev/null
try:
    from picamera2 import Picamera2
    for c in Picamera2.global_camera_info():
        kind = "usb" if "usb" in str(c.get("Id", "")).lower() else "csi"
        print(kind + "|" + str(c.get("Model", "?")))
except Exception as e:
    print("err|" + str(e))
EOF
)"
    # libcamera liệt kê cả webcam USB; chỉ camera có Id không chứa "usb" mới là CSI thật
    if printf '%s\n' "$out" | grep -q '^csi|'; then
      csi_ok=1; ok "Camera CSI: $(printf '%s\n' "$out" | sed -n 's/^csi|//p' | head -1)"
    elif printf '%s\n' "$out" | grep -q '^usb|'; then
      info "libcamera chỉ thấy webcam USB ($(printf '%s\n' "$out" | sed -n 's/^usb|//p' | head -1)), không có camera CSI"
    elif [ "$IS_PI" -eq 1 ]; then
      warn "picamera2 có nhưng không thấy camera CSI ${out:+($out)} — nếu có camera CSI, kiểm tra cáp ribbon (đúng chiều, cắm chặt)"
    else info "picamera2 có nhưng không thấy camera CSI"; fi
  else
    if [ "$IS_PI" -eq 1 ]; then warn "Chưa cài python3-picamera2 — camera CSI không dùng được"; else info "picamera2 không có trên máy này"; fi
  fi
  if [ -n "$lc" ] && [ "$csi_ok" -eq 0 ] && "$lc" --list-cameras 2>&1 | grep -qE "^[0-9]+ :"; then csi_ok=1; ok "libcamera thấy camera CSI"; fi

  vids="$(ls /dev/video* 2>/dev/null | tr '\n' ' ')"
  if [ -n "$vids" ]; then
    info "Thiết bị video: $vids"
    have v4l2-ctl && v4l2-ctl --list-devices 2>/dev/null | grep -vE "^\s*/dev/|^$" | sed 's/^/        /' | head -8
    busy="$(fuser "/dev/video$USB_INDEX" 2>/dev/null | tr -s ' ')"
    if [ -n "$busy" ]; then
      usb_ok=1; ok "Webcam /dev/video$USB_INDEX đang được tiến trình khác dùng (PID$busy) — coi như hoạt động (thường là service $APP_NAME)"
    elif "$PY" -c "import cv2" >/dev/null 2>&1; then
      fr="$("$PY" - "$USB_INDEX" <<'EOF' 2>/dev/null
import sys, cv2
cap = cv2.VideoCapture(int(sys.argv[1]))
ok, f = cap.read() if cap.isOpened() else (False, None)
cap.release()
print(f"{f.shape[1]}x{f.shape[0]}" if ok and f is not None else "NOFRAME")
EOF
)"
      if [ -n "$fr" ] && [ "$fr" != "NOFRAME" ]; then usb_ok=1; ok "Webcam USB index $USB_INDEX đọc được khung hình ($fr)"
      else warn "Có /dev/video* nhưng index $USB_INDEX không đọc được khung hình (thử đổi --usb-index; camera CSI cũng hiện là /dev/video*)"; fi
    else
      warn "Chưa có OpenCV trong môi trường Python — chưa thử mở webcam được"
    fi
    in_group video || warn "User $RUN_USER chưa thuộc nhóm 'video' (sudo usermod -aG video $RUN_USER, rồi đăng nhập lại)"
  else
    info "Không có /dev/video* (không có webcam USB)"
  fi

  case "$CAMERA" in
    picam) if [ "$csi_ok" -eq 1 ]; then ok "Đúng cấu hình: dùng camera CSI"; else bad "CAMERA_SOURCE=picam nhưng không có camera CSI"; FAIL_CAM=1; fi;;
    usb)   if [ "$usb_ok" -eq 1 ]; then ok "Đúng cấu hình: dùng webcam USB"; else bad "CAMERA_SOURCE=usb nhưng webcam USB không hoạt động"; FAIL_CAM=1; fi;;
    *)     if [ "$csi_ok" -eq 1 ] || [ "$usb_ok" -eq 1 ]; then ok "Chế độ auto: có ít nhất 1 camera dùng được"
           else bad "Không có camera nào dùng được (vẫn phân tích được ảnh tải lên, nhưng nút 'Chụp & phân tích' sẽ báo lỗi)"; FAIL_CAM=1; fi;;
  esac
}

MODEM_USB=0
lsusb 2>/dev/null | grep -qiE "1e0e:|SIMCOM|SimTech|SIM7600" && MODEM_USB=1

check_sensor_ports() {
  head_ "Cổng cảm biến (tuỳ chọn: ADS1115/I2C, RS485/Modbus, DHT/GPIO)"
  local ser nrs d a g addr
  ser="$(ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null | tr '\n' ' ')"
  if [ -n "$ser" ] && [ "$MODEM_USB" -eq 1 ]; then
    # Modem SIM7600 tự tạo 4-5 cổng ttyUSB (AT, NMEA, diag...) — KHÔNG phải RS485
    nrs=""
    for d in /dev/ttyUSB* /dev/ttyACM*; do
      [ -e "$d" ] || continue
      udevadm info -q property -n "$d" 2>/dev/null | grep -q "ID_VENDOR_ID=1e0e" || nrs="$nrs $d"
    done
    info "Các cổng ttyUSB ($ser) thuộc modem 4G SimTech, không phải RS485"
    if [ -n "$nrs" ]; then ok "Có cổng serial khác ngoài modem (có thể là USB-RS485):$nrs"
    else info "Không thấy bộ chuyển USB-RS485 riêng — cảm biến NPK RS485 chưa cắm"; fi
  elif [ -n "$ser" ]; then
    ok "Cổng serial USB: $ser"
  else
    info "Không thấy bộ chuyển USB-RS485 (/dev/ttyUSB*, /dev/ttyACM*)"
  fi
  [ -e /dev/serial0 ] && info "UART GPIO: /dev/serial0 -> $(readlink -f /dev/serial0)"

  if [ -e /dev/i2c-1 ]; then
    ok "I2C đã bật (/dev/i2c-1)"
    if have i2cdetect; then
      addr="$(i2cdetect -y 1 2>/dev/null | awk 'NR>1{for(i=2;i<=NF;i++) if($i!="--") print $i}' | tr '\n' ' ')"
      if [ -n "$addr" ]; then
        for a in $addr; do
          case "$a" in
            44|45) g="SHT3x/SHT31 (nhiệt độ + độ ẩm)";;
            38) g="AHT10/AHT20/AHT21 (nhiệt độ + độ ẩm)";;
            40) g="HTU21D/Si7021 (nhiệt độ + độ ẩm) hoặc INA219";;
            76|77) g="BME280/BMP280 (BME280 có độ ẩm, BMP280 thì không)";;
            48|49|4a|4b) g="ADS1115/ADS1015 (ADC analog) — đọc điện áp 4 kênh bằng: python3 probe_ads1115.py";;
            68|69) g="DS3231 (RTC) hoặc MPU6050";;
            *) g="không rõ";;
          esac
          ok "I2C 0x$a: có thể là $g"
        done
      else info "Bus I2C trống — chưa cắm cảm biến I2C"; fi
    else info "Chưa cài i2c-tools (sudo apt install -y i2c-tools) để dò thiết bị I2C"; fi
  elif [ "$IS_PI" -eq 1 ]; then
    info "I2C chưa bật (sudo raspi-config > Interface Options > I2C) — chỉ cần nếu dùng cảm biến I2C/ADC"
  fi
  local w1
  w1="$(ls -d /sys/bus/w1/devices/28-* 2>/dev/null | head -1)"
  if [ -n "$w1" ]; then
    ok "DS18B20 (nhiệt độ) trên 1-Wire: $(basename "$w1") = $(sed -n 's/.*t=//p' "$w1/w1_slave" 2>/dev/null | awk '{printf "%.1f", $1/1000}') °C"
  elif [ -d /sys/bus/w1/devices ]; then
    warn "1-Wire đã bật nhưng không thấy DS18B20 (dây DQ đúng chân đã khai báo trong dtoverlay (sơ đồ dự án: GPIO25, chân 22), trở kéo lên 4.7k, nguồn 3.3V)"
  elif [ "$IS_PI" -eq 1 ]; then
    info "Chưa bật 1-Wire cho DS18B20: thêm dòng dtoverlay=w1-gpio,gpiopin=25 (DQ nối GPIO25, chân 22) vào /boot/firmware/config.txt rồi reboot"
  fi
  if [ -e /dev/gpiomem ] || [ -e /dev/gpiochip0 ]; then
    ok "GPIO truy cập được"
    in_group gpio || info "User $RUN_USER chưa thuộc nhóm 'gpio' (cần nếu đọc DHT: sudo usermod -aG gpio $RUN_USER)"
  fi
}

# ═════════════════════════════════════════════════════════════════════════════
# 4G (SIM7600): kiểm tra, và (nếu bật) kết nối qua ModemManager + NetworkManager
# ═════════════════════════════════════════════════════════════════════════════
FOURG_SUMMARY="chưa kiểm tra"
PROBE_SUDO=""   # bring_up_4g đặt = $SUDO để mở được cổng AT; --check không dùng sudo
# Modem SIM7600 ở chế độ RNDIS/ECM (PID 9011...) tự tạo card mạng (usb0/wwan0) — ModemManager không quản lý kiểu này
mobile_iface() {
  [ "$MODEM_USB" -eq 1 ] || return 1
  local i
  for i in usb0 wwan0 ppp0; do ip link show "$i" >/dev/null 2>&1 && { echo "$i"; return 0; }; done
  return 1
}
# Internet qua đúng giao diện này? in IP công khai nếu có
# Dùng 1.1.1.1 (địa chỉ IP, không cần DNS) để biết đường truyền dữ liệu có thông không, tách khỏi lỗi DNS.
iface_internet() {
  local ip
  ip="$(curl -sS --max-time 10 --interface "$1" https://1.1.1.1/cdn-cgi/trace 2>/dev/null | sed -n 's/^ip=//p' | head -1)"
  if [ -n "$ip" ]; then echo "$ip"; return 0; fi
  # dự phòng: một đích khác (HTTP 204 = thông); không biết IP công khai thì trả "ok"
  [ "$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 --interface "$1" http://connectivitycheck.gstatic.com/generate_204 2>/dev/null)" = "204" ] && echo "ok"
}
mm_idx() { mmcli -L 2>/dev/null | grep -oE '/Modem/[0-9]+' | head -1 | grep -oE '[0-9]+$'; }

# Hỏi modem qua lệnh AT (chỉ khi ModemManager KHÔNG giữ cổng). Cần quyền đọc /dev/ttyUSB*.
at_probe() {
  local ports; ports="$(ls /dev/ttyUSB2 /dev/ttyUSB3 /dev/ttyUSB1 /dev/ttyUSB0 /dev/ttyUSB4 2>/dev/null | tr '\n' ' ')"
  [ -n "$ports" ] || return 1
  $PROBE_SUDO env PORTS="$ports" SET_APN="${1:-}" python3 - <<'PYEOF' 2>/dev/null
import os, re, select, sys, termios, time
def open_port(p):
    fd = os.open(p, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    a = termios.tcgetattr(fd)
    a[0] = 0; a[1] = 0; a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL; a[3] = 0
    a[4] = a[5] = termios.B115200
    a[6][termios.VMIN] = 0; a[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, a); termios.tcflush(fd, termios.TCIOFLUSH)
    return fd
def at(fd, cmd, wait=1.5):
    os.write(fd, (cmd + "\r").encode()); buf = b""; end = time.time() + wait
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.2)
        if r:
            try: buf += os.read(fd, 4096)
            except BlockingIOError: pass
            if b"OK\r\n" in buf or b"ERROR" in buf: break
    return buf.decode(errors="replace")
fd = port = None
for p in os.environ["PORTS"].split():
    try:
        f = open_port(p)
    except PermissionError:
        print("perm=" + p); sys.exit(0)
    except OSError:
        continue
    if "OK" in at(f, "AT", 1.0):
        fd, port = f, p; break
    os.close(f)
if fd is None:
    print("noat=1"); sys.exit(0)
print("port=" + port)
if os.environ.get("SET_APN"):
    r = at(fd, 'AT+CGDCONT=1,"IP","%s"' % os.environ["SET_APN"])
    print("apn_set=" + ("OK" if "OK" in r else "ERR"))
    # APN mới chỉ có hiệu lực sau khi modem gắn lại mạng: tắt phiên dữ liệu, detach rồi attach
    at(fd, "AT+CGACT=0,1", 5); at(fd, "AT+CGATT=0", 8); time.sleep(1); at(fd, "AT+CGATT=1", 15)
    r = at(fd, "AT+CGACT=1,1", 15); print("pdp_activate=" + ("OK" if "OK" in r else "ERR"))
m = re.search(r'\+CGDCONT:\s*1,"[^"]*","([^"]*)"', at(fd, "AT+CGDCONT?")); print("apn_now=" + (m.group(1) if m else ""))
m = re.search(r"\+CGACT:\s*1,(\d)", at(fd, "AT+CGACT?")); print("pdp=" + (m.group(1) if m else "?"))
m = re.search(r'\+CGPADDR:\s*1,"?([0-9.]+)', at(fd, "AT+CGPADDR=1")); print("pdp_ip=" + (m.group(1) if m else ""))
m = re.search(r"\+CPIN:\s*(.+)", at(fd, "AT+CPIN?"));    print("sim=" + (m.group(1).strip() if m else "?"))
m = re.search(r"\+CSQ:\s*(\d+),", at(fd, "AT+CSQ"))
if m:
    n = int(m.group(1)); print("csq=%d" % n); print("dbm=" + ("?" if n == 99 else str(-113 + 2 * n)))
m = re.search(r'\+COPS:\s*\d+,\d+,"([^"]+)"', at(fd, "AT+COPS?")); print("operator=" + (m.group(1) if m else ""))
for cmd, tag in (("AT+CEREG?", "CEREG"), ("AT+CREG?", "CREG")):
    m = re.search(r"\+%s:\s*\d+,(\d+)" % tag, at(fd, cmd))
    if m: print("reg=" + m.group(1)); break
os.close(fd)
PYEOF
}

check_4g() {
  head_ "Mạng & 4G (cần cho ChatGPT, Cloudflare Tunnel)"
  local idx out k v ifc
  if [ "$MODEM_USB" -eq 1 ]; then
    ok "Phát hiện modem 4G SimTech/SIM7600 trên USB ($(lsusb 2>/dev/null | grep -iE '1e0e:' | head -1 | sed 's/.*ID //'))"
  else
    info "Không thấy modem SIM7600 qua USB (bỏ qua nếu dùng WiFi/Ethernet)"; FOURG_SUMMARY="không có modem"
  fi
  info "Giao diện mạng: $(ip -o link show 2>/dev/null | awk -F': ' '{print $2}' | grep -vE '^(lo|docker|veth|br-)' | tr '\n' ' ')"

  if [ "$MODEM_USB" -eq 1 ]; then
    idx=""; have mmcli && idx="$(mm_idx)"
    if [ -n "$idx" ]; then
      # ModemManager đang quản lý modem -> hỏi qua mmcli (không đụng cổng AT)
      out="$(mmcli -m "$idx" -K 2>/dev/null)"
      get() { printf '%s\n' "$out" | grep -E "^$1 *:" | head -1 | sed 's/^[^:]*: *//'; }
      local st sig op reg
      st="$(get modem.generic.state)"; sig="$(get modem.generic.signal-quality.value)"
      op="$(get modem.3gpp.operator-name)"; reg="$(get modem.3gpp.registration-state)"
      info "ModemManager: trạng thái=$st, đăng ký mạng=$reg, nhà mạng=${op:-?}, tín hiệu=${sig:-?}%"
      case "$st" in
        connected) ok "Modem đã kết nối dữ liệu";;
        registered|enabled) ok "Modem đã đăng ký mạng (chưa mở kết nối dữ liệu)";;
        failed*|locked*) bad "Modem lỗi/khoá: $st — kiểm tra SIM (có cắm đúng, có bị khoá PIN không)"; WARN=$((WARN+1));;
        *) warn "Modem ở trạng thái '$st'";;
      esac
      FOURG_SUMMARY="${op:-?}, tín hiệu ${sig:-?}%, trạng thái $st"
    else
      out="$(at_probe)"
      if [ -z "$out" ]; then
        warn "Không thể hỏi modem qua cổng AT (không có python3 hoặc cổng ttyUSB)"; FOURG_SUMMARY="phát hiện modem nhưng không hỏi được"
      elif printf '%s' "$out" | grep -q '^perm='; then
        warn "Không có quyền đọc $(printf '%s' "$out" | sed -n 's/^perm=//p'): sudo usermod -aG dialout $RUN_USER rồi đăng nhập lại (hoặc cài ModemManager bằng ./install.sh)"
        FOURG_SUMMARY="thiếu quyền dialout"
      elif printf '%s' "$out" | grep -q '^noat='; then
        warn "Có modem nhưng không cổng ttyUSB nào trả lời lệnh AT"; FOURG_SUMMARY="modem không trả lời AT"
      else
        local sim dbm opn reg2
        sim="$(printf '%s' "$out" | sed -n 's/^sim=//p')"; dbm="$(printf '%s' "$out" | sed -n 's/^dbm=//p')"
        opn="$(printf '%s' "$out" | sed -n 's/^operator=//p')"; reg2="$(printf '%s' "$out" | sed -n 's/^reg=//p')"
        ok "Modem trả lời lệnh AT trên $(printf '%s' "$out" | sed -n 's/^port=//p')"
        if [ "$sim" = "READY" ]; then ok "SIM sẵn sàng"; else warn "SIM: ${sim:-?} (không phải READY — chưa cắm SIM, SIM sai chiều hoặc đang khoá PIN)"; fi
        info "Nhà mạng: ${opn:-chưa đăng ký}; tín hiệu: ${dbm:-?} dBm"
        local apn_now pdp pdp_ip
        apn_now="$(printf '%s' "$out" | sed -n 's/^apn_now=//p')"; pdp="$(printf '%s' "$out" | sed -n 's/^pdp=//p')"; pdp_ip="$(printf '%s' "$out" | sed -n 's/^pdp_ip=//p')"
        info "APN trong modem: ${apn_now:-?}; phiên dữ liệu (PDP): $([ "$pdp" = 1 ] && echo "đã kích hoạt${pdp_ip:+, IP $pdp_ip}" || echo "CHƯA kích hoạt")"
        [ "$pdp" = 1 ] || warn "Modem chưa mở phiên dữ liệu — thường do APN sai/chưa áp dụng hoặc SIM chưa bật data. Thử: ./install.sh --restart --apn <APN>"
        case "$reg2" in
          1) ok "Đã đăng ký mạng (nhà mạng gốc)";;
          5) ok "Đã đăng ký mạng (roaming)";;
          0|2|3|4|"") warn "Chưa đăng ký được mạng (reg=${reg2:-?}) — kiểm tra SIM, anten 4G, vùng phủ sóng";;
        esac
        FOURG_SUMMARY="SIM ${sim:-?}, ${opn:-chưa đăng ký}, ${dbm:-?} dBm"
      fi
    fi
    ifc="$(mobile_iface)"
    if [ -n "$ifc" ]; then
      ok "Có giao diện mạng di động: $ifc (modem chạy chế độ RNDIS/ECM)"
      local ip4 pub; ip4="$(ip -4 -o addr show dev "$ifc" 2>/dev/null | awk '{print $4}' | head -1)"
      if [ -z "$ip4" ]; then warn "$ifc chưa có địa chỉ IPv4 — chạy ./install.sh --restart để xin IP (DHCP) cho 4G"
      else
        pub="$(iface_internet "$ifc")"
        if [ -n "$pub" ]; then ok "Internet qua 4G ($ifc, $ip4) hoạt động${pub:+ — IP công khai $pub}"; FOURG_SUMMARY="$FOURG_SUMMARY; Internet qua $ifc OK (IP $pub)"
        else warn "$ifc có IP $ip4 nhưng không ra được Internet bằng địa chỉ IP (modem chưa mở phiên dữ liệu, sai APN hoặc hết data)"; fi
      fi
    fi
  fi

  if have curl; then
    if curl -sS --max-time 6 -o /dev/null -w '%{http_code}' https://api.openai.com/ 2>/dev/null | grep -qE '^[1-5][0-9][0-9]$'; then
      ok "Kết nối được tới api.openai.com"
    else
      if curl -sS --max-time 6 -o /dev/null https://1.1.1.1/ 2>/dev/null; then
        warn "Ra được Internet bằng IP nhưng KHÔNG phân giải được tên miền (lỗi DNS) — xem: resolvectl status; nmcli device show | grep DNS"
      else
        warn "Không tới được api.openai.com và cũng không ra được Internet bằng IP — kiểm tra WiFi/Ethernet/4G và đường mặc định"
      fi
      info "Đường mặc định: $(ip -4 route show default 2>/dev/null | head -3 | tr '\n' ';')"
    fi
  fi
}

# Bật kết nối 4G. Hai kiểu modem:
#  (1) RNDIS/ECM (có giao diện usb0/wwan0 sẵn, vd SIM7600 PID 9011): modem tự quay số; việc cần làm là
#      đặt APN (lệnh AT) và xin IP bằng DHCP qua NetworkManager. KHÔNG dùng ModemManager.
#  (2) Không có giao diện mạng: dùng ModemManager + NetworkManager (kiểu gsm).
# Luôn đặt route-metric 700 nên WiFi/Ethernet vẫn được ưu tiên, 4G chỉ là dự phòng. Không đụng kết nối khác.
bring_up_4g_rndis() {
  local ifc="$1" cur ip4 pub n
  info "Modem chạy chế độ RNDIS/ECM trên giao diện $ifc — không cần ModemManager"
  PROBE_SUDO="$SUDO"
  if [ -n "$APN" ]; then
    local o; o="$(at_probe "$APN")"
    if printf '%s' "$o" | grep -q '^apn_set=OK'; then
      ok "Đã đặt APN '$APN' cho SIM (lưu trong modem) và gắn lại mạng"
      printf '%s' "$o" | grep -q '^pdp_activate=OK' || warn "Modem chưa xác nhận mở phiên dữ liệu sau khi đổi APN (xem kết quả kiểm tra bên dưới)"
    else warn "Không đặt được APN qua lệnh AT — kiểm tra quyền cổng ttyUSB (nhóm dialout) hoặc modem không trả lời"; fi
  else
    info "Chưa chỉ định --apn; giữ APN hiện có trong modem (nếu không lên mạng, chạy lại với --apn <APN nhà mạng>, vd Viettel: v-internet)"
  fi
  if have nmcli; then
    cur="$(nmcli -t -f GENERAL.CONNECTION device show "$ifc" 2>/dev/null | cut -d: -f2-)"
    if [ -z "$cur" ] || [ "$cur" = "--" ]; then
      log "Tạo kết nối '$NM_CON' cho $ifc (DHCP, ưu tiên thấp)..."
      $SUDO nmcli connection add type ethernet ifname "$ifc" con-name "$NM_CON" connection.autoconnect yes \
        ipv4.method auto ipv4.route-metric 700 ipv4.dns-priority 700 ipv6.method ignore 802-3-ethernet.mtu 1400 >/dev/null 2>&1 || warn "Không tạo được kết nối $NM_CON"
      cur="$NM_CON"
    else
      # NetworkManager đã tự tạo profile cho $ifc: hạ ưu tiên để không cướp đường mặc định của WiFi/Ethernet
      $SUDO nmcli connection modify "$cur" ipv4.route-metric 700 ipv4.dns-priority 700 ipv6.method ignore 802-3-ethernet.mtu 1400 >/dev/null 2>&1 \
        && ok "Đã hạ ưu tiên đường 4G ('$cur', metric 700) — WiFi/Ethernet vẫn được dùng trước"
    fi
    $SUDO timeout 40 nmcli connection up "$cur" ifname "$ifc" >/dev/null 2>&1 || warn "Không bật được kết nối '$cur' trên $ifc"
  else
    warn "Không có NetworkManager (nmcli): không tự xin IP cho $ifc được — dùng dhcpcd/dhclient thủ công"
  fi
  for n in $(seq 1 20); do ip4="$(ip -4 -o addr show dev "$ifc" 2>/dev/null | awk '{print $4}' | head -1)"; [ -n "$ip4" ] && break; sleep 1; done
  if [ -z "$ip4" ]; then warn "$ifc vẫn chưa có IPv4 — modem chưa đăng ký mạng/chưa quay số. Kiểm tra SIM, anten, APN"; return 0; fi
  info "Giao diện 4G: $ifc ($ip4)"
  pub=""
  for n in 1 2 3; do pub="$(iface_internet "$ifc")"; [ -n "$pub" ] && break; sleep 5; done
  if [ -n "$pub" ]; then
    ok "Internet qua 4G hoạt động (IP công khai $pub)"; FOURG_SUMMARY="đang kết nối ($ifc, IP $pub)"
    [ "$pub" = "ok" ] && FOURG_SUMMARY="đang kết nối ($ifc)"
    # 4G tốt: gỡ cách ly (nếu trước đó đã cách ly) để làm đường dự phòng bình thường
    if have nmcli && [ "$($SUDO nmcli -g ipv4.never-default connection show "$cur" 2>/dev/null | head -1)" = "yes" ]; then
      $SUDO nmcli connection modify "$cur" ipv4.never-default no ipv4.ignore-auto-dns no >/dev/null 2>&1
      $SUDO nmcli device reapply "$ifc" >/dev/null 2>&1; info "Đã gỡ cách ly đường 4G"
    fi
  else
    warn "$ifc có IP nhưng không ra được Internet (modem chưa ra được mạng, hết data hoặc SIM chưa bật data) — chạy ./install.sh --diag để xem chi tiết"
    # Cách ly: 4G hỏng không được làm đường mặc định hay cướp DNS của WiFi/Ethernet đang dùng được
    if have nmcli; then
      $SUDO nmcli connection modify "$cur" ipv4.never-default yes ipv4.ignore-auto-dns yes >/dev/null 2>&1
      $SUDO nmcli device reapply "$ifc" >/dev/null 2>&1
      info "Đã cách ly đường 4G (không làm đường mặc định, bỏ DNS của modem) để không ảnh hưởng mạng đang dùng"
      FOURG_SUMMARY="$FOURG_SUMMARY; usb0 chưa ra Internet (đã cách ly)"
    fi
  fi
}

bring_up_4g() {
  [ "$WITH_4G" -eq 1 ] && [ "$MODEM_USB" -eq 1 ] || return 0
  head_ "Bật 4G"
  local ifc; ifc="$(mobile_iface)"
  if [ -n "$ifc" ]; then bring_up_4g_rndis "$ifc"; return 0; fi

  # Kiểu (2): không có giao diện mạng sẵn -> ModemManager
  if ! have nmcli; then
    warn "Không có NetworkManager (nmcli) — script không tự bật 4G được. Cần Raspberry Pi OS Bookworm (dùng NetworkManager)."
    return 0
  fi
  if ! have mmcli; then
    log "Cài ModemManager..."; $SUDO apt-get install -y modemmanager mobile-broadband-provider-info >/dev/null 2>&1 || { warn "Không cài được ModemManager"; return 0; }
  fi
  $SUDO systemctl enable --now ModemManager >/dev/null 2>&1 || warn "Không bật được ModemManager"
  $SUDO udevadm trigger --subsystem-match=tty --subsystem-match=net --subsystem-match=usbmisc --action=add 2>/dev/null
  in_group dialout || $SUDO usermod -aG dialout "$RUN_USER" 2>/dev/null

  local idx="" i
  for i in $(seq 1 30); do idx="$(mm_idx)"; [ -n "$idx" ] && break; sleep 1; done
  if [ -z "$idx" ]; then
    warn "ModemManager chưa thấy modem sau 30 giây (rút cắm lại USB modem rồi chạy ./install.sh --restart)"
    return 0
  fi
  ok "ModemManager thấy modem số $idx"
  if mmcli -m "$idx" -K 2>/dev/null | grep -qE 'sim-missing|state-failed-reason *: *sim'; then
    warn "Modem báo lỗi SIM (thiếu SIM hoặc bị khoá) — chưa thể kết nối. Kiểm tra SIM rồi chạy lại ./install.sh --restart"
    return 0
  fi
  if ! $SUDO nmcli -t -f NAME connection show 2>/dev/null | grep -qx "$NM_CON"; then
    log "Tạo kết nối 4G '$NM_CON'${APN:+ (APN $APN)}..."
    local args=(connection add type gsm ifname '*' con-name "$NM_CON" connection.autoconnect yes ipv4.route-metric 700 ipv4.dns-priority 700 ipv6.method ignore)
    [ -n "$APN" ] && args+=(gsm.apn "$APN")
    $SUDO nmcli "${args[@]}" >/dev/null 2>&1 || { warn "Không tạo được kết nối 4G bằng nmcli"; return 0; }
  elif [ -n "$APN" ]; then
    $SUDO nmcli connection modify "$NM_CON" gsm.apn "$APN" >/dev/null 2>&1
  fi
  if $SUDO nmcli -t -f NAME,STATE connection show --active 2>/dev/null | grep -q "^$NM_CON:activated"; then ok "Kết nối 4G đã bật sẵn"
  else
    log "Đang kết nối 4G (tối đa 40 giây)..."
    if $SUDO timeout 45 nmcli connection up "$NM_CON" >/dev/null 2>&1; then ok "Đã bật kết nối 4G"
    else warn "Không bật được kết nối 4G — thử: ./install.sh --restart --apn <APN nhà mạng> (vd Viettel: v-internet)"; return 0; fi
  fi
  local dev pub
  dev="$(nmcli -t -f DEVICE,TYPE,STATE device 2>/dev/null | awk -F: '$2=="gsm" && $3=="connected"{print $1; exit}')"
  if [ -n "$dev" ]; then
    pub="$(iface_internet "$dev")"
    if [ -n "$pub" ]; then ok "Internet qua 4G hoạt động ($dev, IP công khai $pub)"; FOURG_SUMMARY="đang kết nối ($dev, IP $pub)"
    else warn "Giao diện 4G có nhưng không ra được Internet (sai APN, hết data hoặc chưa đăng ký mạng)"; fi
  fi
}

# Hỏi modem các lệnh AT tuỳ ý (mỗi lệnh một dòng trong $1), in nguyên phản hồi đã rút gọn
at_raw() {
  local ports; ports="$(ls /dev/ttyUSB2 /dev/ttyUSB3 /dev/ttyUSB1 /dev/ttyUSB0 /dev/ttyUSB4 2>/dev/null | tr '\n' ' ')"
  [ -n "$ports" ] || return 1
  PORTS="$ports" CMDS="$1" python3 - <<'PYEOF2' 2>/dev/null
import os, select, termios, time
def open_port(p):
    fd = os.open(p, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    a = termios.tcgetattr(fd)
    a[0] = 0; a[1] = 0; a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL; a[3] = 0
    a[4] = a[5] = termios.B115200; a[6][termios.VMIN] = 0; a[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, a); termios.tcflush(fd, termios.TCIOFLUSH)
    return fd
def raw(fd, cmd, wait=2.0):
    os.write(fd, (cmd + "\r").encode()); buf = b""; end = time.time() + wait
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.2)
        if r:
            try: buf += os.read(fd, 4096)
            except BlockingIOError: pass
            if b"OK\r\n" in buf or b"ERROR" in buf: break
    return buf.decode(errors="replace")
def pretty(txt):
    return " | ".join(l.strip() for l in txt.splitlines() if l.strip() and l.strip() != "OK" and not l.strip().startswith("AT"))
fd = None
for p in os.environ["PORTS"].split():
    try: f = open_port(p)
    except OSError: continue
    if "OK" in raw(f, "AT", 1.0): fd = f; break
    os.close(f)
if fd is None: raise SystemExit
for c in os.environ["CMDS"].splitlines():
    if c.strip(): print("%-14s %s" % (c.strip(), pretty(raw(fd, c.strip())) or "(không phản hồi)"))
PYEOF2
}

diag_4g() {
  head_ "Chẩn đoán sâu 4G"
  local ifc; ifc="$(mobile_iface)"
  if [ -z "$ifc" ]; then info "Không có giao diện mạng di động (usb0/wwan0/ppp0)"; return 0; fi
  ok "Giao diện: $ifc  $(ip -4 -o addr show dev "$ifc" 2>/dev/null | awk '{print $4}' | head -1)"
  info "Đường mặc định: $(ip -4 route show default 2>/dev/null | tr '\n' ';')"
  info "Đường tới 1.1.1.1 qua $ifc: $(ip route get 1.1.1.1 oif "$ifc" 2>&1 | head -1)"
  info "ping qua $ifc: $(ping -c3 -W3 -I "$ifc" 1.1.1.1 2>&1 | tail -2 | tr '\n' ' ')"
  info "curl qua $ifc: $(curl -sS -o /dev/null -w 'http=%{http_code} kết_nối=%{time_connect}s tổng=%{time_total}s' --max-time 10 --interface "$ifc" http://1.1.1.1/ 2>&1 | tail -1)"
  info "MTU $ifc: $(ip -o link show "$ifc" 2>/dev/null | grep -oE 'mtu [0-9]+')"
  info "Thử gói nhỏ (generate_204) qua $ifc: $(curl -sS -o /dev/null -w 'http=%{http_code} tổng=%{time_total}s' --max-time 12 --interface "$ifc" http://connectivitycheck.gstatic.com/generate_204 2>&1 | tail -1)  (204 = thông)"
  info "rp_filter: all=$(sysctl -n net.ipv4.conf.all.rp_filter 2>/dev/null) $ifc=$(sysctl -n "net.ipv4.conf.$ifc.rp_filter" 2>/dev/null)  (1 = nghiêm ngặt, có thể chặn gói trả về khi có 2 đường mặc định)"
  info "DNS của $ifc: $(nmcli -g IP4.DNS device show "$ifc" 2>/dev/null | tr '\n' ' ')"
  info "Kết nối $NM_CON: never-default=$(nmcli -g ipv4.never-default connection show "$NM_CON" 2>/dev/null | head -1) ignore-auto-dns=$(nmcli -g ipv4.ignore-auto-dns connection show "$NM_CON" 2>/dev/null | head -1) (số profile trùng tên: $(nmcli -t -f NAME connection show 2>/dev/null | grep -cx "$NM_CON"))"
  info "Phân giải tên miền api.openai.com: $(getent hosts api.openai.com 2>&1 | head -1)$(getent hosts api.openai.com >/dev/null 2>&1 || echo 'THẤT BẠI')"
  echo "  --- Modem (lệnh AT) ---"
  local o; o="$(at_raw $'AT+CPSI?\nAT+CREG?\nAT+CGREG?\nAT+CEREG?\nAT+CNSMOD?\nAT+CGDCONT?\nAT+CGACT?\nAT+CGPADDR\nAT+CSQ\nAT+COPS?')"
  if [ -n "$o" ]; then printf '%s\n' "$o" | sed 's/^/    /'
    local cpsi rsrp rsrq rp q
    cpsi="$(printf '%s\n' "$o" | sed -n 's/^AT+CPSI?  *//p' | head -1)"
    rsrq="$(printf '%s' "$cpsi" | cut -d, -f11)"; rsrp="$(printf '%s' "$cpsi" | cut -d, -f12)"
    if [[ "$rsrp" =~ ^-?[0-9]+$ ]]; then
      rp=$((rsrp / 10)); q="khá"
      [ "$rp" -ge -90 ] && q="tốt"
      [ "$rp" -lt -100 ] && q="yếu (dễ rớt gói, nên đổi vị trí/anten)"
      [ "$rp" -lt -110 ] && q="rất yếu"
      info "Sóng LTE: RSRP ${rp} dBm → $q; RSRQ $(( ${rsrq:-0} / 10 )) dB"
    fi
  else warn "Không hỏi được modem qua cổng AT (thiếu quyền dialout hoặc không có cổng)"; fi
  info "Nếu PDP đã kích hoạt mà vẫn không ra Internet: kiểm tra gói data của SIM (số dư, đã bật data chưa) theo hướng dẫn của nhà mạng."
}

run_checks() {
  check_board; check_camera; check_sensor_ports; check_4g
}

summary_checks() {
  head_ "Tóm tắt kiểm tra"
  if [ "$FAIL_CAM" -ne 0 ]; then
    printf '  \033[1;31mThiếu thiết bị BẮT BUỘC (camera).\033[0m %d cảnh báo khác.\n' "$WARN"
  else
    printf '  \033[1;32mThiết bị bắt buộc đã sẵn sàng.\033[0m %d cảnh báo (xem các dòng [WARN] ở trên).\n' "$WARN"
  fi
}

# ═════════════════════════════════════════════════════════════════════════════
# Chế độ --check / --uninstall
# ═════════════════════════════════════════════════════════════════════════════
if [ "$MODE" = "check" ]; then
  run_checks; summary_checks
  [ "$FAIL_CAM" -ne 0 ] && exit 2
  exit 0
fi

if [ "$MODE" = "diag" ]; then
  MODEM_USB=$MODEM_USB; check_4g; diag_4g
  exit 0
fi

if [ "$MODE" = "uninstall" ]; then
  for svc in "${APP_NAME}-tunnel" "$APP_NAME"; do
    if [ -f "/etc/systemd/system/${svc}.service" ]; then
      $SUDO systemctl disable --now "$svc" 2>/dev/null
      $SUDO rm -f "/etc/systemd/system/${svc}.service"
      log "Đã gỡ service $svc"
    fi
  done
  $SUDO systemctl daemon-reload
  have nmcli && $SUDO nmcli connection delete "$NM_CON" >/dev/null 2>&1 && log "Đã xoá kết nối 4G '$NM_CON'"
  log "Xong. Mã nguồn và .venv vẫn còn tại $APP_DIR (xoá tay nếu muốn)."
  exit 0
fi

# ═════════════════════════════════════════════════════════════════════════════
# CÀI ĐẶT (bỏ qua khi --restart)
# ═════════════════════════════════════════════════════════════════════════════
[ -f "$APP_DIR/server/app.py" ] || die "Không thấy server/app.py — hãy chạy script từ trong deploy_pi/"
[ -f "$APP_DIR/paddy_classify/weights/best.onnx" ] || die "Thiếu model paddy_classify/weights/best.onnx"
ARCH="$(uname -m)"
HAS_PICAM2=0

if [ "$MODE" = "install" ]; then
  have apt-get || die "Script chỉ hỗ trợ Raspberry Pi OS / Debian (apt)."
  [ "$IS_PI" -eq 1 ] && log "Thiết bị: $(tr -d '\0' < /proc/device-tree/model)"
  case "$ARCH" in
    aarch64|arm64) ;;
    armv7l|armv6l) warn "Hệ điều hành 32-bit ($ARCH): onnxruntime có thể không có wheel. Khuyến nghị Raspberry Pi OS 64-bit." ;;
    *) warn "Kiến trúc $ARCH không phải Raspberry Pi — vẫn tiếp tục." ;;
  esac

  # Dọn bản cũ đặt tên "agrismart"
  for old in agrismart-tunnel agrismart; do
    if [ -f "/etc/systemd/system/${old}.service" ]; then
      warn "Gỡ service cũ $old (đã đổi tên thành agritech)"
      $SUDO systemctl disable --now "$old" 2>/dev/null
      $SUDO rm -f "/etc/systemd/system/${old}.service"
    fi
  done
  [ -f "$APP_DIR/agrismart.env" ] && [ ! -f "$ENV_FILE" ] && mv "$APP_DIR/agrismart.env" "$ENV_FILE"

  # 1. Gói hệ thống
  log "Cài gói hệ thống (apt)..."
  $SUDO apt-get update -y || warn "apt update lỗi (kiểm tra mạng) — thử cài tiếp"
  for pkg in python3 python3-venv python3-pip libopenblas0 libgl1 v4l-utils curl i2c-tools python3-smbus psmisc; do
    $SUDO apt-get install -y "$pkg" >/dev/null 2>&1 || warn "Bỏ qua gói $pkg (không cài được)"
  done
  if [ "$CAMERA" != "usb" ]; then
    if $SUDO apt-get install -y python3-picamera2 python3-libcamera >/dev/null 2>&1; then HAS_PICAM2=1
    else
      warn "Không cài được python3-picamera2 — chỉ dùng được webcam USB."
      [ "$CAMERA" = "picam" ] && die "--camera picam cần picamera2"
    fi
  fi

  # 2. Virtualenv + thư viện Python (--system-site-packages để thấy picamera2 cài bằng apt)
  if [ -d "$VENV_DIR" ] && ! grep -q 'include-system-site-packages = true' "$VENV_DIR/pyvenv.cfg" 2>/dev/null; then
    warn "Venv cũ không kế thừa gói hệ thống — tạo lại."; rm -rf "$VENV_DIR"
  fi
  [ -d "$VENV_DIR" ] || { log "Tạo virtualenv..."; python3 -m venv --system-site-packages "$VENV_DIR" || die "Tạo venv thất bại"; }
  log "Cài thư viện Python (có thể mất vài phút)..."
  "$VENV_DIR/bin/pip" install --upgrade pip >/dev/null 2>&1
  "$VENV_DIR/bin/pip" install -r "$APP_DIR/server/requirements.txt" || die "pip install thất bại"

  # 3. File cấu hình môi trường (không đè cấu hình đã chỉnh tay)
  if [ ! -f "$ENV_FILE" ]; then
    log "Tạo $ENV_FILE"
    cat > "$ENV_FILE" <<EOF
# Biến môi trường cho Agritech (đọc bởi systemd). Sửa xong: ./install.sh --restart
CAMERA_SOURCE=$CAMERA
USB_CAMERA_INDEX=$USB_INDEX
PORT=$PORT

# ChatGPT (tuỳ chọn). Khuyến nghị đặt key qua giao diện web (nút chìa khoá): key đó
# được ưu tiên hơn biến này và có hiệu lực ngay, không cần restart.
# OPENAI_API_KEY=sk-...
# OPENAI_MODEL=gpt-4o-mini
# Token bảo vệ việc đổi key khi truy cập từ xa (qua tunnel). Nên đặt nếu dùng --tunnel.
# ADMIN_TOKEN=doi-thanh-chuoi-bi-mat
EOF
  else
    warn "$ENV_FILE đã tồn tại — giữ nguyên (sửa tay nếu cần đổi camera/port)."
  fi
  chown "$RUN_USER":"$(id -gn "$RUN_USER")" "$ENV_FILE" 2>/dev/null || $SUDO chown "$RUN_USER": "$ENV_FILE"
  $SUDO usermod -aG video,dialout,gpio,i2c "$RUN_USER" 2>/dev/null || $SUDO usermod -aG video "$RUN_USER" || warn "Không thêm được $RUN_USER vào nhóm video"

  # 4. Chạy thử model
  log "Chạy thử model..."
  if (cd "$APP_DIR" && "$VENV_DIR/bin/python" server/inference.py >/dev/null 2>&1); then log "Model OK."
  else warn "Chạy thử model lỗi — xem: $VENV_DIR/bin/python $APP_DIR/server/inference.py"; fi
fi

# Lưu các tuỳ chọn dòng lệnh vào agritech.env để service và lần --restart sau dùng đúng giá trị
env_set() {   # env_set KEY VALUE
  if grep -qE "^$1=" "$ENV_FILE"; then sed -i "s|^$1=.*|$1=$2|" "$ENV_FILE"; else echo "$1=$2" >> "$ENV_FILE"; fi
}
if [ -f "$ENV_FILE" ]; then
  [ "$CAMERA_GIVEN" -eq 1 ] && env_set CAMERA_SOURCE "$CAMERA"
  [ "$USB_GIVEN" -eq 1 ]    && env_set USB_CAMERA_INDEX "$USB_INDEX"
  [ "$PORT_GIVEN" -eq 1 ]   && env_set PORT "$PORT"
  [ -n "$APN" ]             && env_set APN_4G "$APN"
fi

# ═════════════════════════════════════════════════════════════════════════════
# KIỂM TRA PHẦN CỨNG  ->  BẬT 4G  ->  KHỞI ĐỘNG SERVER
# ═════════════════════════════════════════════════════════════════════════════
log "Kiểm tra thiết bị phần cứng..."
check_board; check_camera; check_sensor_ports
bring_up_4g            # bật 4G trước rồi mới kiểm tra mạng, để kết quả phản ánh đúng
check_4g
summary_checks
[ "$FAIL_CAM" -ne 0 ] && warn "Thiếu camera. Vẫn tiếp tục; cắm camera rồi chạy './install.sh --restart'."

# systemd service
if [ "$WITH_SERVICE" -eq 1 ] && [ "$MODE" = "install" ]; then
  log "Tạo service $APP_NAME..."
  $SUDO tee "$SERVICE_FILE" >/dev/null <<EOF
[Unit]
Description=Agritech - nhận diện bệnh lúa
After=network-online.target
Wants=network-online.target

[Service]
User=$RUN_USER
SupplementaryGroups=video dialout gpio i2c
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$VENV_DIR/bin/python server/app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
  $SUDO systemctl daemon-reload
  $SUDO systemctl enable "$APP_NAME" >/dev/null 2>&1
fi

# Cloudflare Tunnel (tuỳ chọn)
TUNNEL_URL=""
if [ "$WITH_TUNNEL" -eq 1 ] && [ "$MODE" = "install" ]; then
  if ! have cloudflared; then
    case "$ARCH" in
      aarch64|arm64) CF_ARCH="arm64" ;; armv7l|armv6l) CF_ARCH="arm" ;; x86_64) CF_ARCH="amd64" ;;
      *) die "Không hỗ trợ cloudflared cho $ARCH" ;;
    esac
    log "Tải cloudflared ($CF_ARCH)..."
    TMP_CF="$(mktemp)"
    curl -fL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${CF_ARCH}" -o "$TMP_CF" \
      && chmod +x "$TMP_CF" && $SUDO mv "$TMP_CF" /usr/local/bin/cloudflared || warn "Tải cloudflared thất bại"
  fi
  if have cloudflared; then
    $SUDO tee "$TUNNEL_SERVICE_FILE" >/dev/null <<EOF
[Unit]
Description=Agritech - Cloudflare quick tunnel
After=network-online.target ${APP_NAME}.service
Wants=network-online.target

[Service]
User=$RUN_USER
ExecStart=$(command -v cloudflared) tunnel --no-autoupdate --url http://localhost:$PORT
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    $SUDO systemctl daemon-reload
    $SUDO systemctl enable "${APP_NAME}-tunnel" >/dev/null 2>&1
  fi
fi

# Dừng mọi server Agritech cũ KHÔNG do systemd quản lý (chạy tay, port cũ...) rồi để service chạy lại.
# Chỉ kill tiến trình của dự án này (server/app.py trong thư mục này). Chương trình khác chiếm cổng thì chỉ cảnh báo.
stop_old_servers() {
  local svc_pid p args cwd killed=0 listener lcmd n
  svc_pid="$(systemctl show -p MainPID --value "$APP_NAME" 2>/dev/null)"; [ "$svc_pid" = "0" ] && svc_pid=""
  for p in $(pgrep -f 'server/app\.py' 2>/dev/null); do
    [ "$p" = "$$" ] || [ "$p" = "$PPID" ] || [ "$p" = "$svc_pid" ] && continue
    # Chỉ nhận tiến trình PYTHON chạy server/app.py (không nhận shell/ssh có chứa chuỗi đó trong dòng lệnh)
    args="$(tr '\0' '\n' < "/proc/$p/cmdline" 2>/dev/null)"; cwd="$(readlink -f "/proc/$p/cwd" 2>/dev/null)"
    case "$(basename "$(printf '%s\n' "$args" | head -1)")" in python*) ;; *) continue;; esac
    printf '%s\n' "$args" | grep -qE '(^|/)server/app\.py$' || continue
    [ "$cwd" = "$APP_DIR" ] || printf '%s\n' "$args" | grep -qF "$APP_DIR/server/app.py" || continue
    info "Dừng server cũ đang chạy (PID $p)..."
    $SUDO kill -TERM "$p" 2>/dev/null
    for n in 1 2 3 4 5 6 7 8 9 10; do kill -0 "$p" 2>/dev/null || break; sleep 0.5; done
    kill -0 "$p" 2>/dev/null && { $SUDO kill -KILL "$p" 2>/dev/null; sleep 0.5; }
    killed=$((killed+1))
  done
  [ "$killed" -gt 0 ] && ok "Đã dừng $killed server cũ"
  # Cổng vẫn bị giữ bởi tiến trình khác (không phải server của dự án)?
  listener="$($SUDO ss -ltnpH "sport = :$PORT" 2>/dev/null | grep -oE 'pid=[0-9]+' | head -1 | cut -d= -f2)"
  if [ -n "$listener" ] && [ "$listener" != "$svc_pid" ]; then
    lcmd="$(tr '\0' ' ' < "/proc/$listener/cmdline" 2>/dev/null | cut -c1-80)"
    warn "Cổng $PORT đang bị chương trình khác dùng (PID $listener: $lcmd) — không phải server Agritech nên KHÔNG kill. Dùng --port <số khác> hoặc tự dừng nó."
  fi
}

# --no-service: chạy server nền bằng tay (nohup) với cấu hình từ agritech.env
start_manual() {
  log "Chạy server nền (không dùng service)..."
  ( set -a; [ -f "$ENV_FILE" ] && . "$ENV_FILE"; set +a
    cd "$APP_DIR" && setsid nohup "$VENV_DIR/bin/python" server/app.py >> "$APP_DIR/server.log" 2>&1 < /dev/null & )
}

# Khởi động (lại) server rồi xác minh
if { [ "$WITH_SERVICE" -eq 1 ] && [ -f "$SERVICE_FILE" ]; } || [ "$WITH_SERVICE" -eq 0 ]; then
  head_ "Khởi động server"
  if [ "$WITH_SERVICE" -eq 1 ]; then
    $SUDO systemctl stop "$APP_NAME" 2>/dev/null      # giải phóng camera/cổng trước khi dọn server cũ
    stop_old_servers
    log "Khởi động lại service $APP_NAME..."
    $SUDO systemctl restart "$APP_NAME"
    [ -f "$TUNNEL_SERVICE_FILE" ] && $SUDO systemctl restart "${APP_NAME}-tunnel"
  else
    stop_old_servers
    start_manual
  fi
  HEALTH=""
  for _ in $(seq 1 40); do
    HEALTH="$(curl -fs "http://127.0.0.1:$PORT/api/health" 2>/dev/null)" && break
    HEALTH=""; sleep 1
  done
  if [ -n "$HEALTH" ]; then
    ok "Server đã chạy (/api/health)"
    printf '%s' "$HEALTH" | grep -q '"model_loaded": *true' && ok "Model đã nạp" || warn "Model chưa nạp"
    printf '%s' "$HEALTH" | grep -q '"camera": *true' && ok "Camera đã mở" || warn "Camera chưa mở — dashboard vẫn chạy, bấm 'Chọn ảnh' để phân tích ảnh"
  else
    warn "Server chưa phản hồi — xem log: journalctl -u $APP_NAME -e"
  fi
  if [ -f "$TUNNEL_SERVICE_FILE" ]; then
    for _ in $(seq 1 20); do
      TUNNEL_URL="$($SUDO journalctl -u "${APP_NAME}-tunnel" --no-pager -n 50 2>/dev/null | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -1)"
      [ -n "$TUNNEL_URL" ] && break; sleep 1
    done
  fi
fi

# ═════════════════════════════════════════════════════════════════════════════
# IP LAN thật (bỏ giao diện của modem 4G, vd 192.168.225.x); liệt kê tất cả nếu có nhiều
IPS="$(ip -4 -o addr show scope global 2>/dev/null | awk '$2!~/^(usb[0-9]|wwan[0-9]|ppp[0-9]|docker|veth|br-|lo)/{sub(/\/.*/,"",$4); printf "%s ", $4}')"
IP="${IPS%% *}"
head_ "Hoàn tất"
echo "   Dashboard (LAN) : http://${IP:-<ip-pi>}:$PORT${IPS:+   (các IP: $IPS)}"
[ -n "$TUNNEL_URL" ] && echo "   Truy cập từ xa  : $TUNNEL_URL"
[ "$WITH_4G" -eq 1 ] && [ "$MODEM_USB" -eq 1 ] && echo "   4G              : $FOURG_SUMMARY"
if [ "$WITH_SERVICE" -eq 1 ]; then
  echo "   Trạng thái      : systemctl status $APP_NAME   |   log: journalctl -u $APP_NAME -f"
  echo "   Chạy lại nhanh  : ./install.sh --restart   (kiểm tra + bật 4G + khởi động lại server)"
else
  echo "   Chạy tay        : cd $APP_DIR && $VENV_DIR/bin/python server/app.py"
fi
echo "   Cấu hình        : $ENV_FILE"
[ "$HAS_PICAM2" -eq 1 ] && echo "   (Camera CSI: bật trong 'sudo raspi-config' > Interface, reboot nếu chưa chạy được)"
echo "   Lưu ý           : nếu vừa được thêm vào nhóm video/dialout/gpio/i2c, đăng xuất/đăng nhập lại để chạy tay."
exit 0

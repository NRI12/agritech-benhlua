#!/usr/bin/env bash
# Cài đặt tự động Agritech trên Raspberry Pi 4 (Raspberry Pi OS 64-bit).
#
#   cd deploy_pi && ./install.sh [tuỳ chọn]
#
# Tuỳ chọn:
#   --camera auto|picam|usb   nguồn camera (mặc định: auto)
#   --usb-index N             index webcam USB (mặc định: 0)
#   --port N                  cổng web (mặc định: 5000)
#   --tunnel                  cài thêm Cloudflare Tunnel (xem từ xa qua 4G)
#   --no-service              không tạo service tự khởi động
#   --check                   chỉ kiểm tra thiết bị/cổng I/O (camera, serial, I2C, 4G, mạng) rồi thoát
#   --uninstall               gỡ service (giữ nguyên mã nguồn và .venv)
#   -h, --help                xem trợ giúp
#
# Chạy lại được nhiều lần (idempotent). Không cần chạy bằng sudo — script tự gọi sudo khi cần.
set -euo pipefail

APP_NAME="agritech"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_USER="${SUDO_USER:-$(id -un)}"
RUN_HOME="$(getent passwd "$RUN_USER" | cut -d: -f6)"
VENV_DIR="$APP_DIR/.venv"
ENV_FILE="$APP_DIR/agritech.env"
SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"
TUNNEL_SERVICE_FILE="/etc/systemd/system/${APP_NAME}-tunnel.service"

CAMERA="auto"
USB_INDEX="0"
PORT="5000"
WITH_TUNNEL=0
WITH_SERVICE=1
UNINSTALL=0
CHECK_ONLY=0

log()  { printf '\033[1;32m[+]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2; exit 1; }

usage() { sed -n '2,16p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --camera)     CAMERA="${2:?thiếu giá trị}"; shift 2 ;;
    --usb-index)  USB_INDEX="${2:?thiếu giá trị}"; shift 2 ;;
    --port)       PORT="${2:?thiếu giá trị}"; shift 2 ;;
    --tunnel)     WITH_TUNNEL=1; shift ;;
    --no-service) WITH_SERVICE=0; shift ;;
    --uninstall)  UNINSTALL=1; shift ;;
    --check)      CHECK_ONLY=1; shift ;;
    -h|--help)    usage; exit 0 ;;
    *) die "Tuỳ chọn không hợp lệ: $1 (xem --help)" ;;
  esac
done

case "$CAMERA" in auto|picam|usb) ;; *) die "--camera phải là auto|picam|usb" ;; esac
[[ "$PORT" =~ ^[0-9]+$ ]] || die "--port phải là số"
[[ "$USB_INDEX" =~ ^[0-9]+$ ]] || die "--usb-index phải là số"

if [ "$CHECK_ONLY" -eq 1 ]; then
  exec bash "$APP_DIR/check_hardware.sh"
fi

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  command -v sudo >/dev/null || die "Cần sudo hoặc chạy bằng root"
  SUDO="sudo"
fi

# ── Gỡ cài đặt ──────────────────────────────────────────────────────────────
if [ "$UNINSTALL" -eq 1 ]; then
  for svc in "${APP_NAME}-tunnel" "$APP_NAME"; do
    if [ -f "/etc/systemd/system/${svc}.service" ]; then
      $SUDO systemctl disable --now "$svc" 2>/dev/null || true
      $SUDO rm -f "/etc/systemd/system/${svc}.service"
      log "Đã gỡ service $svc"
    fi
  done
  $SUDO systemctl daemon-reload
  log "Xong. Mã nguồn và .venv vẫn còn tại $APP_DIR (xoá tay nếu muốn)."
  exit 0
fi

# ── Kiểm tra môi trường ─────────────────────────────────────────────────────
[ -f "$APP_DIR/server/app.py" ] || die "Không thấy server/app.py — hãy chạy script từ trong deploy_pi/"
[ -f "$APP_DIR/paddy_classify/weights/best.onnx" ] || die "Thiếu model paddy_classify/weights/best.onnx"

ARCH="$(uname -m)"
case "$ARCH" in
  aarch64|arm64) ;;
  armv7l|armv6l) warn "Hệ điều hành 32-bit ($ARCH): onnxruntime có thể không có wheel. Khuyến nghị Raspberry Pi OS 64-bit." ;;
  *) warn "Kiến trúc $ARCH không phải Raspberry Pi — vẫn tiếp tục." ;;
esac
if [ -r /proc/device-tree/model ]; then
  log "Thiết bị: $(tr -d '\0' < /proc/device-tree/model)"
fi
command -v apt-get >/dev/null || die "Script chỉ hỗ trợ Raspberry Pi OS / Debian (apt)."

# ── Dọn bản cũ đặt tên "agrismart" (nếu có) ─────────────────────────────────
for old in agrismart-tunnel agrismart; do
  if [ -f "/etc/systemd/system/${old}.service" ]; then
    warn "Gỡ service cũ $old (đã đổi tên thành agritech)"
    $SUDO systemctl disable --now "$old" 2>/dev/null || true
    $SUDO rm -f "/etc/systemd/system/${old}.service"
  fi
done
if [ -f "$APP_DIR/agrismart.env" ] && [ ! -f "$ENV_FILE" ]; then
  mv "$APP_DIR/agrismart.env" "$ENV_FILE"
fi

# ── 1. Gói hệ thống ─────────────────────────────────────────────────────────
log "Cài gói hệ thống (apt)..."
$SUDO apt-get update -y
APT_PKGS=(python3 python3-venv python3-pip libopenblas0 libgl1 v4l-utils curl)
# libgl1/libopenblas0 có thể đổi tên giữa các bản OS; cài từng gói, gói nào thiếu thì bỏ qua.
for pkg in "${APT_PKGS[@]}"; do
  $SUDO apt-get install -y "$pkg" || warn "Bỏ qua gói $pkg (không cài được)"
done

HAS_PICAM2=0
if [ "$CAMERA" != "usb" ]; then
  if $SUDO apt-get install -y python3-picamera2 python3-libcamera; then
    HAS_PICAM2=1
  else
    warn "Không cài được python3-picamera2 — chỉ dùng được webcam USB."
    [ "$CAMERA" = "picam" ] && die "--camera picam cần picamera2"
  fi
fi

# ── 2. Virtualenv + thư viện Python ─────────────────────────────────────────
# --system-site-packages để venv thấy picamera2 (cài qua apt, không có trên pip).
if [ -d "$VENV_DIR" ] && ! grep -q 'include-system-site-packages = true' "$VENV_DIR/pyvenv.cfg" 2>/dev/null; then
  warn "Venv cũ không kế thừa gói hệ thống — tạo lại."
  rm -rf "$VENV_DIR"
fi
if [ ! -d "$VENV_DIR" ]; then
  log "Tạo virtualenv..."
  python3 -m venv --system-site-packages "$VENV_DIR"
fi
log "Cài thư viện Python (có thể mất vài phút)..."
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$APP_DIR/server/requirements.txt"

# ── 3. File cấu hình môi trường ─────────────────────────────────────────────
# Chỉ ghi lần đầu hoặc khi người dùng truyền tuỳ chọn mới; không đè cấu hình đã chỉnh tay.
if [ ! -f "$ENV_FILE" ]; then
  log "Tạo $ENV_FILE"
  cat > "$ENV_FILE" <<EOF
# Biến môi trường cho Agritech (đọc bởi systemd). Sửa xong: sudo systemctl restart $APP_NAME
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
  # shellcheck disable=SC1090
  PORT="$(grep -E '^PORT=' "$ENV_FILE" | tail -1 | cut -d= -f2 || echo "$PORT")"
  PORT="${PORT:-5000}"
fi
chown "$RUN_USER":"$(id -gn "$RUN_USER")" "$ENV_FILE" 2>/dev/null || $SUDO chown "$RUN_USER": "$ENV_FILE"

# Quyền truy cập camera
$SUDO usermod -aG video "$RUN_USER" || warn "Không thêm được $RUN_USER vào nhóm video"

# ── 4. Kiểm tra model chạy được ─────────────────────────────────────────────
log "Chạy thử model..."
if (cd "$APP_DIR" && "$VENV_DIR/bin/python" server/inference.py >/dev/null 2>&1); then
  log "Model OK."
else
  warn "Chạy thử model lỗi — xem: $VENV_DIR/bin/python $APP_DIR/server/inference.py"
fi

# ── 4b. Kiểm tra thiết bị / cổng I/O (không dừng cài đặt nếu thiếu, chỉ báo cáo) ──
log "Kiểm tra thiết bị phần cứng..."
HW_RC=0
bash "$APP_DIR/check_hardware.sh" || HW_RC=$?
if [ "$HW_RC" -ne 0 ]; then
  warn "Thiếu thiết bị bắt buộc (camera). Vẫn cài tiếp; cắm camera rồi chạy './install.sh --check' để kiểm tra lại."
fi

# ── 5. systemd service ──────────────────────────────────────────────────────
if [ "$WITH_SERVICE" -eq 1 ]; then
  log "Tạo service $APP_NAME..."
  $SUDO tee "$SERVICE_FILE" >/dev/null <<EOF
[Unit]
Description=Agritech - nhận diện bệnh lúa realtime
After=network-online.target
Wants=network-online.target

[Service]
User=$RUN_USER
SupplementaryGroups=video
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$VENV_DIR/bin/python server/app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
  $SUDO systemctl daemon-reload
  $SUDO systemctl enable "$APP_NAME"
  $SUDO systemctl restart "$APP_NAME"
fi

# ── 6. Cloudflare Tunnel (tuỳ chọn) ─────────────────────────────────────────
if [ "$WITH_TUNNEL" -eq 1 ]; then
  if ! command -v cloudflared >/dev/null; then
    case "$ARCH" in
      aarch64|arm64) CF_ARCH="arm64" ;;
      armv7l|armv6l) CF_ARCH="arm" ;;
      x86_64)        CF_ARCH="amd64" ;;
      *) die "Không hỗ trợ cloudflared cho $ARCH" ;;
    esac
    log "Tải cloudflared ($CF_ARCH)..."
    TMP_CF="$(mktemp)"
    curl -fL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${CF_ARCH}" -o "$TMP_CF"
    chmod +x "$TMP_CF"
    $SUDO mv "$TMP_CF" /usr/local/bin/cloudflared
  fi
  CF_BIN="$(command -v cloudflared)"
  $SUDO tee "$TUNNEL_SERVICE_FILE" >/dev/null <<EOF
[Unit]
Description=Agritech - Cloudflare quick tunnel
After=network-online.target ${APP_NAME}.service
Wants=network-online.target

[Service]
User=$RUN_USER
ExecStart=$CF_BIN tunnel --no-autoupdate --url http://localhost:$PORT
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
  $SUDO systemctl daemon-reload
  $SUDO systemctl enable "${APP_NAME}-tunnel"
  $SUDO systemctl restart "${APP_NAME}-tunnel"
  log "Đang chờ cloudflared cấp URL..."
  TUNNEL_URL=""
  for _ in $(seq 1 20); do
    TUNNEL_URL="$($SUDO journalctl -u "${APP_NAME}-tunnel" --no-pager -n 50 2>/dev/null \
      | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -1 || true)"
    [ -n "$TUNNEL_URL" ] && break
    sleep 1
  done
fi

# ── 7. Kiểm tra sức khoẻ & tóm tắt ──────────────────────────────────────────
if [ "$WITH_SERVICE" -eq 1 ]; then
  log "Chờ server khởi động..."
  OK=0
  for _ in $(seq 1 30); do
    if curl -fs "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then OK=1; break; fi
    sleep 1
  done
  [ "$OK" -eq 1 ] || warn "Server chưa phản hồi — xem log: journalctl -u $APP_NAME -e"
fi

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
log "Cài đặt xong."
echo "   Dashboard (LAN) : http://${IP:-<ip-pi>}:$PORT"
[ -n "${TUNNEL_URL:-}" ] && echo "   Truy cập từ xa  : $TUNNEL_URL"
if [ "$WITH_SERVICE" -eq 1 ]; then
  echo "   Trạng thái      : systemctl status $APP_NAME"
  echo "   Xem log         : journalctl -u $APP_NAME -f"
  echo "   Khởi động lại   : sudo systemctl restart $APP_NAME"
  echo "   Cấu hình        : $ENV_FILE"
else
  echo "   Chạy tay        : cd $APP_DIR && $VENV_DIR/bin/python server/app.py"
fi
[ "$HAS_PICAM2" -eq 1 ] && echo "   (Nếu dùng camera CSI: bật trong 'sudo raspi-config' > Interface, rồi reboot nếu chưa chạy được)"
echo "   Lưu ý           : nếu vừa được thêm vào nhóm 'video', hãy đăng xuất/đăng nhập lại để chạy tay."

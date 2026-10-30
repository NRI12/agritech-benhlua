#!/usr/bin/env bash
# Khởi động lại hệ thống Agritech (không cài lại): gọi deploy_pi/install.sh --restart
set -euo pipefail
cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/deploy_pi"
exec bash ./install.sh --restart "$@"

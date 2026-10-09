#!/usr/bin/env bash
set -euo pipefail
qwen_install_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "$qwen_install_root/src/wsl_launcher.py" firewall "$@"

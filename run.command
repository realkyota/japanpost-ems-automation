#!/bin/bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "请先从 python.org 安装 Python 3.10 或更新版本。"
  read -r -p "按回车退出…" unused
  exit 1
fi
python3 -c 'import sys; assert sys.version_info >= (3,10), "需要 Python 3.10 或更新版本"'
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
if ! .venv/bin/python -c 'import playwright, keyring' >/dev/null 2>&1; then
  .venv/bin/python -m pip install -r requirements.txt
fi
case "${1:-}" in
  --setup-login|--forget-login) ;;
  *) .venv/bin/python -m playwright install chromium ;;
esac
.venv/bin/python japanpost.py "$@"

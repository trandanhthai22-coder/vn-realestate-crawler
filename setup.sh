#!/usr/bin/env bash
# Cài đặt 1 lần trên macOS / Linux: ./setup.sh
set -euo pipefail
cd "$(dirname "$0")"

PY=""
for cand in python3.13 python3.12 python3.11 python3 python; do
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
    PY="$cand"; break
  fi
done
[ -z "$PY" ] && { echo "Cần Python >= 3.11 (https://www.python.org/downloads/)"; exit 1; }

echo "Dùng $($PY --version)"
[ -x .venv/bin/python ] || "$PY" -m venv .venv
.venv/bin/python -m pip install --upgrade pip -q
.venv/bin/python -m pip install -e ".[browser]" -q
echo "Cài đặt xong. Chạy: ./run.sh"

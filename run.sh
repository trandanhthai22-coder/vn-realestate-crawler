#!/usr/bin/env bash
# ./run.sh            -> menu chọn job
# ./run.sh run ...    -> như lệnh bdscrawl
set -euo pipefail
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || ./setup.sh
if [ $# -eq 0 ]; then
  exec .venv/bin/python -m bdscrawler menu
else
  exec .venv/bin/python -m bdscrawler "$@"
fi

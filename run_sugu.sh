#!/bin/bash
# 수급오실레이터 데이터 수집 → 리포트 생성 → GitHub Pages 배포

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -x "$HOME/miniforge3/envs/krx/bin/python3" ]; then
    PYTHON="$HOME/miniforge3/envs/krx/bin/python3"
elif [ -x "$HOME/miniforge3/bin/python3" ]; then
    PYTHON="$HOME/miniforge3/bin/python3"
else
    PYTHON="$(which python3)"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 수급 데이터 수집 시작"
"$PYTHON" "$SCRIPT_DIR/sugu_calculator.py" || { echo "[ERROR] sugu_calculator 실패"; exit 1; }

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 리포트 생성 시작"
"$PYTHON" "$SCRIPT_DIR/generate_sugu_report.py" || { echo "[ERROR] generate_sugu_report 실패"; exit 1; }

echo "[$(date '+%Y-%m-%d %H:%M:%S')] GitHub 배포 시작"
bash "$SCRIPT_DIR/publish_sugu.sh" || { echo "[ERROR] publish_sugu 실패"; exit 1; }

echo "[$(date '+%Y-%m-%d %H:%M:%S')] 완료"

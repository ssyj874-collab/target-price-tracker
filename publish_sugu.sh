#!/bin/bash
# 수급오실레이터 리포트를 GitHub Pages에 배포하는 스크립트
# 사용법: bash publish_sugu.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== 수급오실레이터 리포트 GitHub Pages 배포 ==="

# sugu_report.html 존재 확인
if [ ! -f "sugu_report.html" ]; then
    echo "sugu_report.html 없음. 먼저 생성합니다..."
    python3 generate_sugu_report.py
fi

# 현재 브랜치 저장
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)

echo "gh-pages 브랜치로 배포 중..."

# origin/gh-pages 기준으로 로컬 gh-pages 강제 리셋
git fetch origin gh-pages
git checkout gh-pages
git reset --hard origin/gh-pages

# sugu_report.html 복사 후 커밋
cp "$SCRIPT_DIR/sugu_report.html" ./sugu_report.html
git add sugu_report.html
git commit -m "update: 수급오실레이터 리포트 $(date '+%Y-%m-%d %H:%M')" || echo "변경사항 없음"
git push origin gh-pages

# 원래 브랜치로 복귀
git checkout "$CURRENT_BRANCH"

echo ""
echo "배포 완료!"
echo "URL: https://ssyj874-collab.github.io/target-price-tracker/sugu_report.html"

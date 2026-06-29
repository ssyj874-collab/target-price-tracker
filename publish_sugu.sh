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

# HTML을 임시 파일로 백업 (브랜치 전환 후에도 접근 가능하도록)
TMP_HTML=$(mktemp /tmp/sugu_report_XXXXXX.html)
cp sugu_report.html "$TMP_HTML"

# 현재 브랜치 저장
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)

echo "gh-pages 브랜치로 배포 중..."
git fetch origin gh-pages

# 로컬 gh-pages를 origin 기준으로 강제 동기화
git branch -f gh-pages origin/gh-pages
git checkout gh-pages

# 임시 파일에서 복사
cp "$TMP_HTML" sugu_report.html
rm "$TMP_HTML"

git add sugu_report.html
git commit -m "update: 수급오실레이터 리포트 $(date '+%Y-%m-%d %H:%M')" || echo "변경사항 없음"
git push origin gh-pages

# 원래 브랜치로 복귀
git checkout "$CURRENT_BRANCH"

echo ""
echo "배포 완료!"
echo "URL: https://ssyj874-collab.github.io/target-price-tracker/sugu_report.html"

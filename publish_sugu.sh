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
    # 업종 데이터가 있으면 먼저 집계
    if [ -f "sector_universe.json" ]; then
        python3 sector_calculator.py
    fi
    python3 generate_sugu_report.py
fi

# gh-pages를 별도 임시 디렉토리에 체크아웃 (브랜치 전환 없이 배포)
WORKTREE_DIR=$(mktemp -d /tmp/gh-pages-XXXXXX)
git fetch origin gh-pages
git worktree add "$WORKTREE_DIR" origin/gh-pages 2>/dev/null || \
    git worktree add "$WORKTREE_DIR" gh-pages

cp sugu_report.html "$WORKTREE_DIR/sugu_report.html"

cd "$WORKTREE_DIR"
git add sugu_report.html
git commit -m "update: 수급오실레이터 리포트 $(date '+%Y-%m-%d %H:%M')" || echo "변경사항 없음"
git push origin HEAD:gh-pages

cd "$SCRIPT_DIR"
git worktree remove "$WORKTREE_DIR" --force

echo ""
echo "배포 완료!"
echo "URL: https://ssyj874-collab.github.io/target-price-tracker/sugu_report.html"

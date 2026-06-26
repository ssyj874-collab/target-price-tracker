#!/bin/bash
# SIO 리포트 자동 업데이트 등록 스크립트
#
# 동작 방식:
#   - 매일 오후 4:00 자동 실행
#   - Mac이 꺼져 있으면 스킵, 다음에 켤 때 누락분 포함 업데이트
#   - 이미 오늘 업데이트됐으면 중복 실행 안 함
#
# 실행: bash setup_auto_update.sh
# 해제: bash setup_auto_update.sh --uninstall

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$(which python3)"
PLIST="$HOME/Library/LaunchAgents/com.sio.daily-report.plist"

if [ "$1" = "--uninstall" ]; then
    launchctl unload "$PLIST" 2>/dev/null
    rm -f "$PLIST"
    echo "✅ 자동 업데이트 해제 완료"
    exit 0
fi

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.sio.daily-report</string>

  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>$SCRIPT_DIR/generate_report.py</string>
    <string>--no-open</string>
    <string>--skip-if-fresh</string>
    <string>--publish</string>
  </array>

  <key>EnvironmentVariables</key>
  <dict>
    <key>KRX_ID</key>
    <string>syj6718</string>
    <key>KRX_PW</key>
    <string>song135!</string>
  </dict>

  <key>WorkingDirectory</key>
  <string>$SCRIPT_DIR</string>

  <!-- 매일 오후 4:00 실행 -->
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>16</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>

  <!-- Mac 시작/로그인 시에도 실행 (꺼져있던 동안 누락분 처리) -->
  <key>RunAtLoad</key>
  <true/>

  <key>StandardOutPath</key>
  <string>$SCRIPT_DIR/sio_report.log</string>
  <key>StandardErrorPath</key>
  <string>$SCRIPT_DIR/sio_report_error.log</string>
</dict>
</plist>
EOF

launchctl unload "$PLIST" 2>/dev/null
launchctl load "$PLIST"

echo ""
echo "✅ 자동 업데이트 등록 완료"
echo ""
echo "  📅 매일 오후 4:00 자동 실행"
echo "  💻 Mac 켤 때도 실행 (누락된 날 자동 반영)"
echo "  ⚡ 오늘 이미 업데이트됐으면 중복 실행 안 함"
echo ""
echo "  리포트 위치: $SCRIPT_DIR/sio_report.html"
echo "  로그 위치:   $SCRIPT_DIR/sio_report.log"
echo ""
echo "  해제하려면: bash setup_auto_update.sh --uninstall"

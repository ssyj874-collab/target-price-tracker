#!/bin/bash
# Mac 자동 업데이트 설정 스크립트
# 매일 오전 9시 10분(장 시작 직후)에 리포트 자동 생성
# 실행: bash setup_auto_update.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON=$(which python3)
PLIST="$HOME/Library/LaunchAgents/com.sio.daily-report.plist"

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
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>9</integer>
    <key>Minute</key>
    <integer>10</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>$SCRIPT_DIR/sio_report.log</string>
  <key>StandardErrorPath</key>
  <string>$SCRIPT_DIR/sio_report_error.log</string>
</dict>
</plist>
EOF

launchctl unload "$PLIST" 2>/dev/null
launchctl load "$PLIST"

echo "✅ 자동 업데이트 등록 완료"
echo "   매일 오전 9:10에 sio_report.html 자동 갱신됩니다."
echo ""
echo "해제하려면:"
echo "  launchctl unload $PLIST"

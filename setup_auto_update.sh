#!/bin/bash
# 자동 업데이트 + 서버 launchd 등록 스크립트
#
# 등록 내용:
#   com.sio.daily-report  : 매일 16:10 SIO 리포트 생성 & GitHub Pages 배포
#   com.song.sugu         : 매일 16:05 수급오실레이터 리포트 생성 & 배포
#   com.song.server       : 로그인 시 Flask 서버(8888) 자동 시작
#
# 실행: bash setup_auto_update.sh
# 해제: bash setup_auto_update.sh --uninstall

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# miniforge Python 3.12 우선 사용 (macOS 26 Tahoe brew Python segfault 우회)
if [ -x "$HOME/miniforge3/envs/krx/bin/python3" ]; then
    PYTHON="$HOME/miniforge3/envs/krx/bin/python3"
elif [ -x "$HOME/miniforge3/bin/python3" ]; then
    PYTHON="$HOME/miniforge3/bin/python3"
else
    PYTHON="$(which python3)"
fi

echo "사용할 Python: $PYTHON"

PLIST_SIO="$HOME/Library/LaunchAgents/com.sio.daily-report.plist"
PLIST_SUGU="$HOME/Library/LaunchAgents/com.song.sugu.plist"
PLIST_SERVER="$HOME/Library/LaunchAgents/com.song.server.plist"

if [ "$1" = "--uninstall" ]; then
    for plist in "$PLIST_SIO" "$PLIST_SUGU" "$PLIST_SERVER"; do
        launchctl unload "$plist" 2>/dev/null
        rm -f "$plist"
    done
    echo "✅ 자동 업데이트 + 서버 해제 완료"
    exit 0
fi

mkdir -p "$HOME/Library/LaunchAgents"

# --- SIO 리포트 ---
cat > "$PLIST_SIO" <<EOPLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.sio.daily-report</string>

  <key>ProgramArguments</key>
  <array>
    <string>${PYTHON}</string>
    <string>${SCRIPT_DIR}/generate_report.py</string>
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
    <key>HOME</key>
    <string>${HOME}</string>
    <key>PATH</key>
    <string>${HOME}/miniforge3/envs/krx/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>

  <key>WorkingDirectory</key>
  <string>${SCRIPT_DIR}</string>

  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>16</integer>
    <key>Minute</key>
    <integer>10</integer>
  </dict>

  <key>RunAtLoad</key>
  <false/>

  <key>StandardOutPath</key>
  <string>${SCRIPT_DIR}/sio_report.log</string>
  <key>StandardErrorPath</key>
  <string>${SCRIPT_DIR}/sio_report_error.log</string>
</dict>
</plist>
EOPLIST

# --- 수급오실레이터 리포트 ---
cat > "$PLIST_SUGU" <<EOPLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.song.sugu</string>

  <key>ProgramArguments</key>
  <array>
    <string>${PYTHON}</string>
    <string>${SCRIPT_DIR}/sugu_calculator.py</string>
  </array>

  <key>EnvironmentVariables</key>
  <dict>
    <key>HOME</key>
    <string>${HOME}</string>
    <key>PATH</key>
    <string>${HOME}/miniforge3/envs/krx/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>

  <key>WorkingDirectory</key>
  <string>${SCRIPT_DIR}</string>

  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>16</integer>
    <key>Minute</key>
    <integer>5</integer>
  </dict>

  <key>RunAtLoad</key>
  <false/>

  <key>StandardOutPath</key>
  <string>${SCRIPT_DIR}/sugu.log</string>
  <key>StandardErrorPath</key>
  <string>${SCRIPT_DIR}/sugu_error.log</string>
</dict>
</plist>
EOPLIST

# --- Flask 서버 ---
cat > "$PLIST_SERVER" <<EOPLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.song.server</string>

  <key>ProgramArguments</key>
  <array>
    <string>${PYTHON}</string>
    <string>${SCRIPT_DIR}/server.py</string>
  </array>

  <key>EnvironmentVariables</key>
  <dict>
    <key>HOME</key>
    <string>${HOME}</string>
    <key>PATH</key>
    <string>${HOME}/miniforge3/envs/krx/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>

  <key>WorkingDirectory</key>
  <string>${SCRIPT_DIR}</string>

  <key>RunAtLoad</key>
  <true/>

  <key>KeepAlive</key>
  <true/>

  <key>StandardOutPath</key>
  <string>${SCRIPT_DIR}/server.log</string>
  <key>StandardErrorPath</key>
  <string>${SCRIPT_DIR}/server_error.log</string>
</dict>
</plist>
EOPLIST

# 기존 등록 해제 후 재등록
for plist in "$PLIST_SIO" "$PLIST_SUGU" "$PLIST_SERVER"; do
    launchctl unload "$plist" 2>/dev/null
    launchctl load "$plist"
done

echo ""
echo "✅ 등록 완료"
echo ""
echo "  com.sio.daily-report  : 매일 16:10 SIO 업데이트 & GitHub Pages 배포"
echo "  com.song.sugu         : 매일 16:05 수급오실레이터 업데이트"
echo "  com.song.server       : 로그인 시 Flask 서버 자동 시작 (http://localhost:8888)"
echo ""
echo "  상태 확인: launchctl list | grep -E 'sio|sugu|server'"
echo "  해제:      bash setup_auto_update.sh --uninstall"
echo ""
echo "  로그:"
echo "    SIO:    $SCRIPT_DIR/sio_report.log"
echo "    수급:   $SCRIPT_DIR/sugu.log"
echo "    서버:   $SCRIPT_DIR/server.log"

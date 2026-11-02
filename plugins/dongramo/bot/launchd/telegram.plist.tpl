<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.dongramo.telegram</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>__SKILL__/scripts/telegram_bridge.py</string>
    <string>--daemon</string>
  </array>
  <key>WorkingDirectory</key>
  <string>__SKILL__</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>HOME</key>
    <string>__HOME__</string>
    <key>DONGRAMO_HOME</key>
    <string>__DGHOME__</string>
    <key>LANG</key>
    <string>es_ES.UTF-8</string>
  </dict>
  <!-- Proceso permanente con long polling; launchd lo relanza si se cae. -->
  <key>KeepAlive</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>10</integer>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>__DGHOME__/logs/telegram.out.log</string>
  <key>StandardErrorPath</key>
  <string>__DGHOME__/logs/telegram.err.log</string>
  <key>ProcessType</key>
  <string>Background</string>
</dict>
</plist>

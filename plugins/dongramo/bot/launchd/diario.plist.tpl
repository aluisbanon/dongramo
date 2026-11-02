<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.dongramo.diario</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>__SKILL__/scripts/aviso.py</string>
    <string>--diario</string>
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
  <!-- Cada día: menú del día al chat. Sin modelo. -->
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>__H__</integer>
    <key>Minute</key><integer>__MI__</integer>
  </dict>
  <key>RunAtLoad</key>
  <false/>
  <key>StandardOutPath</key>
  <string>__DGHOME__/logs/avisos.out.log</string>
  <key>StandardErrorPath</key>
  <string>__DGHOME__/logs/avisos.err.log</string>
  <key>ProcessType</key>
  <string>Background</string>
</dict>
</plist>

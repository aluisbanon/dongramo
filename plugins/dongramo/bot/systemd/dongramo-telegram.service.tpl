[Unit]
Description=Don Gramo: puente de Telegram
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/bin/env python3 __SKILL__/scripts/telegram_bridge.py --daemon
WorkingDirectory=__SKILL__
Environment=DONGRAMO_HOME=__DGHOME__
Environment=LANG=es_ES.UTF-8
Environment=PATH=__HOME__/.local/bin:__HOME__/.npm-global/bin:/usr/local/bin:/usr/bin:/bin
Restart=always
RestartSec=10

[Install]
WantedBy=default.target

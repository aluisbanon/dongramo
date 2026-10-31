[Unit]
Description=Don Gramo: aviso semanal

[Service]
Type=oneshot
ExecStart=/usr/bin/env python3 __SKILL__/scripts/aviso.py --semanal
WorkingDirectory=__SKILL__
Environment=DON_GRAMO_HOME=__DGHOME__
Environment=LANG=es_ES.UTF-8

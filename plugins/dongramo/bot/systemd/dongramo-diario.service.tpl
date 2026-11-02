[Unit]
Description=Don Gramo: aviso diario

[Service]
Type=oneshot
ExecStart=/usr/bin/env python3 __SKILL__/scripts/aviso.py --diario
WorkingDirectory=__SKILL__
Environment=DONGRAMO_HOME=__DGHOME__
Environment=LANG=es_ES.UTF-8

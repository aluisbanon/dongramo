[Unit]
Description=Don Gramo: menú del día

[Timer]
OnCalendar=*-*-* __H__:__M__:00
Persistent=true

[Install]
WantedBy=timers.target

[Unit]
Description=Don Gramo: revisión del domingo

[Timer]
OnCalendar=Sun *-*-* __H__:__M__:00
Persistent=true

[Install]
WantedBy=timers.target

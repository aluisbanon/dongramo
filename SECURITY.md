# Seguridad y privacidad

## Avisar de un problema de seguridad

Si encuentras una vulnerabilidad (por ejemplo, algo que pueda filtrar datos de salud, tokens o
credenciales, o ejecutar comandos no previstos), **no abras un issue público**: usa
[«Report a vulnerability»](../../security/advisories/new) en la pestaña *Security* del repositorio.
Responderé lo antes posible.

## Qué datos maneja Don Gramo

- Todo se guarda en tu máquina, en `~/.don-gramo/` (o `$DON_GRAMO_HOME`). El proyecto no tiene
  servidores ni recoge datos.
- Los secretos (token de Telegram, credenciales de Cookidoo) van al Llavero de macOS o a
  `state/secrets.env` con permisos 600.
- Lo que escribes a Claude, Codex u OpenClaw lo procesa el proveedor del modelo que uses, con sus
  propias condiciones. El bot de Telegram pasa por los servidores de Telegram.

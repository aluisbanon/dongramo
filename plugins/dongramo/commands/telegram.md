---
description: Conecta Don Gramo a Telegram paso a paso (bot del grupo de casa con avisos diarios)
argument-hint: "[opcional: «estado», «parar», «actualizar»]"
---

Usa la skill `dongramo` y sigue `references/telegram.md`. Empieza siempre
con `python3 {baseDir}/scripts/telegram_setup.py estado` y continúa desde el primer paso pendiente, un paso
cada vez, esperando a que la persona confirme lo que tiene que hacer en Telegram.

Nunca pidas el token del bot por el chat: se pega en la ventana o terminal que abre el script.

Si piden «parar», usa `telegram_setup.py parar`; si piden «actualizar», `telegram_setup.py copiar`.
Lo que ha dicho la persona: $ARGUMENTS

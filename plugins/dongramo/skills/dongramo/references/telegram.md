# Enganchar Don Gramo a Telegram (asistente)

Objetivo: que la persona solo tenga que tocar Telegram. Todo lo demás lo hace
`python3 {baseDir}/scripts/telegram_setup.py`. Ve **un paso cada vez**, con
mensajes cortos y concretos, y espera su «hecho» antes de seguir. Sin jerga: «el bot», «el grupo»,
«el código que te da BotFather».

## 0. Dónde estamos

```
python3 {baseDir}/scripts/telegram_setup.py estado
```

Retoma desde el primer paso sin hacer. Si falta el hogar, primero `/dongramo:configurar`.
Si falta Claude Code, explica que el bot lo necesita en esta máquina para entender los mensajes libres
(instalarlo e iniciar sesión) y que los comandos como `/hoy` funcionan igualmente.

Avisa al principio, en una línea: el bot funciona mientras este ordenador esté encendido y conectado.

## 1. Copia estable

```
python3 {baseDir}/scripts/telegram_setup.py copiar
```

No hace falta explicarlo mucho: «preparo una copia fija para que el bot no se rompa al actualizar».

## 2. Crear el bot (lo hace la persona en Telegram)

Dale exactamente estos pasos:

1. En Telegram, busca **@BotFather** (tiene una marca azul de verificado) y ábrelo.
2. Escribe `/newbot`.
3. Te pide un nombre: pon el que quieras, por ejemplo «Don Gramo de casa».
4. Te pide un usuario: tiene que acabar en `bot`, por ejemplo `dongramo_garcia_bot`. Si está cogido, prueba otro.
5. Te contesta con un código largo (el *token*, algo como `123456789:AAH...`). **No lo pegues en este chat.**

Cuando diga que lo tiene:

```
python3 {baseDir}/scripts/telegram_setup.py token
```

En macOS se abre una ventana para pegarlo (el texto queda oculto). Si el script dice que no puede abrir
la ventana (Linux o sin pantalla), pídele que ejecute en una terminal el comando que imprime el script.
**Nunca** le pidas el token por el chat ni lo pases como argumento.

## 3. El grupo (lo hace la persona en Telegram)

- **Varias personas**: crear un grupo nuevo con ellas, añadir el bot (por su usuario, `@..._bot`) y
  escribir `/ayuda` en el grupo.
- **Una sola persona**: basta con abrir el chat con su bot y escribirle `/ayuda`.

Cuando diga «hecho»:

```
python3 {baseDir}/scripts/telegram_setup.py chat
```

Si ve varios chats, pregúntale cuál y usa `chat --id ID`. Si no ve ninguno, que compruebe que el bot
está en el grupo y vuelva a escribir `/ayuda`.

## 4. Activar

```
python3 {baseDir}/scripts/telegram_setup.py activar
```

Arranca el bot (siempre encendido), el menú de cada mañana y la revisión del domingo, y manda un saludo
al chat. Pídele que cada persona escriba `/soy <su nombre>` allí y que pruebe `/hoy`.
Termina con `estado` para confirmar que todo está en verde.

## Después

- Cambiar la hora de los avisos: `telegram.aviso_diario` / `telegram.aviso_semanal` en
  `~/.dongramo/config.json` (formato HH:MM) y repetir `activar`.
- Tras actualizar el plugin: `/dongramo:telegram` otra vez → `copiar` pasa la versión nueva al bot.
- Parar el bot: `telegram_setup.py parar`. Enviar el menú de hoy como prueba: `telegram_setup.py prueba`.
- Si algo falla, `estado` dice qué falta. Los registros del bot están en `~/.dongramo/logs/`.

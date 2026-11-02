# Cambios

## 1.1.0 · 2026-11-02

El proyecto pasa a llamarse **dongramo**, sin guion (como dongramo.com y dongramo.es). Si vienes
de la 1.0 no pierdes nada:

- Plugins `dongramo` y `dongramo-cookidoo`; comandos `/dongramo:hoy`, `/dongramo:compra`…
  Reinstala desde el marketplace nuevo (ver «Si vienes de la 1.0» en el README).
- Datos en `~/.dongramo`. La primera vez se renombra solo `~/.don-gramo` y queda un enlace con el
  nombre antiguo, para que un bot instalado con la 1.0 siga funcionando hasta que lo reactives.
- `DONGRAMO_HOME` y `DONGRAMO_NUCLEO`; las variables antiguas (`DON_GRAMO_…`) se siguen entendiendo.
- Secretos `dongramo-telegram-bot/chat`; si solo están con el nombre antiguo, se usan esos.
- En Linux, `bot/install.sh activar` quita las unidades `don-gramo-*` y crea las `dongramo-*`.
- `instalar.sh` quita la copia antigua de la skill en Codex y `~/.agents/skills`.
- El repositorio pasa a `aluisbanon/dongramo`; las direcciones antiguas redirigen.

## 1.0.0 · 2026-10-26

Primera versión pública, a partir del bot privado de una pareja.

- Hogares de 1 a N personas: cantidades de referencia escaladas a cada uno (proteína y verdura
  × ratio^0,6; hidratos y grasas cuadran el total).
- Alta de personas con estimación inicial de calorías (Mifflin-St Jeor), suelos seguros, modo
  «crecer» para menores y modo sin déficit para embarazo o lactancia.
- Sustituciones permanentes por persona (alergias, gustos).
- Reparto de la olla entre N personas, agua de las recetas escalada y aviso de capacidad del vaso.
- Thermomix opcional: 28 recetas con versión de cocina tradicional.
- Datos fuera del plugin, en ~/.don-gramo (DON_GRAMO_HOME).
- Bot de Telegram para macOS (launchd) y Linux (systemd), con `/soy <nombre>` para vincularse.
- Skill universal (AgentSkills): la misma para Claude Code, Codex y OpenClaw, con `{baseDir}` y
  `instalar.sh` para Codex/OpenClaw/`~/.agents/skills`.
- Asistente `/don-gramo:telegram` para conectar el bot paso a paso (el token nunca pasa por el chat).
- Cookidoo, en una extensión aparte (`don-gramo-cookidoo`) del mismo repositorio: opcional y no oficial.

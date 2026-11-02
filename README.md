<p align="center"><img src="assets/logo.png" alt="Don Gramo" width="220"></p>

# Don Gramo

[![CI](https://github.com/aluisbanon/dongramo/actions/workflows/ci.yml/badge.svg)](https://github.com/aluisbanon/dongramo/actions/workflows/ci.yml)

**Entrenador y asistente de dieta para Claude**, para una persona, una pareja o una familia entera.
Todos comen los mismos platos y cada uno recibe *sus* gramos, ajustados a sus calorías.

> «Cada gramo cuenta.»

- **Menús semanales** (3 menús validados que rotan, 21 días de comidas caseras españolas) que se
  escalan solos al objetivo de cada persona: quien come menos recorta hidratos y grasas, no proteína.
- **¿Has comido fuera? ¿Unas cañas?** Se apunta y se compensa en el resto del día y en los 3
  siguientes, sin bajar de un suelo seguro, sin tocar la proteína y sin saltarse comidas.
- **Receta del día** con los gramos de cada uno, el total para la olla, el agua ajustada a cuántos
  coméis y cuánto servir a cada uno («pesa la olla y sirve: Marta 22 %, Javier 30 %...»).
- **Cambios en el menú**: «el jueves no quiero alubias», «cambia el pollo por pavo», «hoy no tengo
  calabacín», «Marta es alérgica al marisco». El motor comprueba que el plato nuevo cuadra en kcal y proteína.
- **Lista de la compra** por secciones, para pegar en Notas.
- **Entrenador**: peso (también leyendo capturas de básculas inteligentes), tendencia de 4 semanas,
  fecha estimada de llegada a la meta y **revisión semanal** que recalibra las calorías con tu peso
  real. Nada cambia sin que lo aceptes.
- **Familias**: los menores van en modo «crecimiento» (sin déficit y con raciones de su edad).
- **Thermomix opcional**: recetas con pasos guiados (TM5/TM6/TM7) o en versión de cocina tradicional.
- **Opcional**: bot de **Telegram** para el grupo de casa, con menú cada mañana y revisión los domingos.
- **Extensión aparte** para **Cookidoo** (no oficial), por si la quieres.

Todas las cuentas las hace un motor en Python (solo librería estándar). Claude interpreta lo que
dices, estima lo que comes fuera y llama al motor: nunca hace las cuentas de cabeza.

## ¿Con qué funciona?

Es una sola skill con el estándar abierto [AgentSkills](https://agentskills.io): el mismo código y
las mismas instrucciones en todas partes. Las cuentas las hace siempre el motor en Python, así que
las cantidades son idénticas uses el modelo que uses.

| Herramienta | Modelo | Cómo se instala | Bot de Telegram |
|---|---|---|---|
| **Claude Code** (terminal o pestaña Code de la app de Claude) | Claude | Plugin | Incluido: `/dongramo:telegram` |
| **Codex** (incluido en los planes de ChatGPT) | GPT | `./instalar.sh codex` | — |
| **OpenClaw** | el que configures | `./instalar.sh openclaw` | Con los canales de OpenClaw |
| Otras compatibles con AgentSkills | — | `./instalar.sh agents` | — |

Necesitas `python3` (3.9 o superior; viene con macOS y casi todos los Linux).
Si usas varias en la misma máquina, comparten los datos (`~/.dongramo`).

## Instalación

### Claude Code

```
/plugin marketplace add aluisbanon/dongramo
/plugin install dongramo@dongramo
```

Después:

```
/dongramo:configurar somos mi pareja, yo y nuestro hijo de 12 años
```

Don Gramo te pregunta lo necesario (edad, altura, peso, actividad y objetivo de cada uno), estima
las calorías de partida y ya está. A partir de ahí, habla con él normalmente:

- «¿Qué ceno hoy?» · `/dongramo:hoy`
- «Hoy he comido fuera: menú del día con paella y flan»
- «Nos hemos tomado dos cañas y una de bravas»
- «Peso 81,4» (o pega la captura de tu báscula)
- «¿Cómo voy?» · «Cambia el bacalao del miércoles por merluza»
- `/dongramo:compra próxima`

### Codex y OpenClaw

```
git clone https://github.com/aluisbanon/dongramo && cd dongramo
./instalar.sh codex          # o: ./instalar.sh openclaw   (añade --cookidoo si quieres la extensión)
```

- **Codex** solo deja escribir dentro del proyecto en el que trabajas. Para que Don Gramo guarde tus
  datos, arráncalo con `codex --add-dir ~/.dongramo` o añade a `~/.codex/config.toml`:
  ```toml
  [sandbox_workspace_write]
  writable_roots = ["/Users/TU_USUARIO/.dongramo"]
  ```
  (el instalador te muestra la línea exacta con tu ruta).
- **OpenClaw**: por defecto la instala para todos tus agentes; con `--agent <id>`, solo en uno
  (recomendado: un agente propio para Don Gramo). No necesitas el bot de Telegram de este
  repositorio: OpenClaw ya tiene sus canales (Telegram, WhatsApp...). Si te pide aprobar cada
  comando, permite `python3 …/dongramo/scripts/dieta.py`.
- Sin comandos con barra: pídeselo con naturalidad («configura Don Gramo para mi familia», «¿qué
  ceno hoy?»).
- Para actualizar: `git pull` y repite `./instalar.sh ...`. Tus datos no se tocan.

### Actualizaciones

- **Claude Code**: por defecto los plugins de catálogos de terceros **no se actualizan solos**. Para
  recibir las versiones nuevas automáticamente: `/plugin` → pestaña **Marketplaces** → `dongramo` →
  **Enable auto-update**. Para actualizar a mano: `claude plugin update dongramo@dongramo`.
- **Codex y OpenClaw**: `git pull` y repite `./instalar.sh ...`.
- **Bot de Telegram**: tras actualizar, `/dongramo:telegram` pasa la versión nueva al bot.

Qué cambia en cada versión: [CHANGELOG](CHANGELOG.md) y [Releases](../../releases).

### Si vienes de la 1.0 (`don-gramo`, con guion)

Desde la 1.1 el proyecto se llama `dongramo`. Tus datos se pasan solos de `~/.don-gramo` a
`~/.dongramo` la primera vez que lo uses. En Claude Code, cambia de marketplace:

```
/plugin uninstall don-gramo@don-gramo
/plugin marketplace remove don-gramo
/plugin marketplace add aluisbanon/dongramo
/plugin install dongramo@dongramo
```

Si tienes el bot de Telegram, vuelve a lanzar `/dongramo:telegram` (o `bot/install.sh activar`)
para que use la versión nueva.

### ¿Y en claude.ai?

La skill funciona en el entorno de código de claude.ai, pero **allí los datos no se guardan entre
conversaciones** (cada chat empieza con el sistema de ficheros limpio), así que perderías el registro
y los pesos. Para el día a día, usa Claude Code o el bot de Telegram en un ordenador que esté
encendido (un Mac, una Raspberry Pi o un servidor pequeño).

## Tus datos

Todo se guarda en `~/.dongramo/` (o en la carpeta de `DONGRAMO_HOME`), fuera del plugin, así que
actualizarlo no borra nada:

```
~/.dongramo/
  config.json          hogar, personas y objetivos
  state/               registro de comidas, pesos, cambios de menú, preferencias, secretos (chmod 600)
  logs/
```

Nada sale de tu máquina, salvo los mensajes que pases por Claude y, si los activas, Telegram y
la extensión de Cookidoo. Para hacer una copia de seguridad, comprime esa carpeta.

## Bot de Telegram (opcional)

Un grupo de Telegram de casa (o tu chat privado) donde cada uno escribe al bot. Los comandos (`/hoy`,
`/compra`, `/progreso`...) son instantáneos y no gastan modelo; los mensajes libres («@bot me he
tomado una caña») los resuelve Claude Code en tu máquina. Cada mañana manda el menú del día y los
domingos, el progreso y la revisión.

Desde Claude Code:

```
/dongramo:telegram
```

y un asistente te guía. Tú solo tienes que:

1. Crear el bot en Telegram con **@BotFather** (`/newbot`, 1 minuto).
2. Pegar su código en la ventana que se abre (nunca pasa por el chat).
3. Crear el grupo, añadir el bot y escribir `/ayuda`.
4. Que cada uno escriba `/soy <su nombre>`.

Lo demás (guardar el código, detectar el grupo, arrancar el bot y los avisos con launchd en macOS o
systemd en Linux, y el mensaje de prueba) lo hace el asistente. Necesitas un ordenador que esté
encendido (un Mac, una Raspberry Pi o un servidor pequeño) con Claude Code y la sesión iniciada.

Después de actualizar el plugin, vuelve a ejecutar `/dongramo:telegram` para pasar la versión nueva
al bot. Las horas de los avisos están en `~/.dongramo/config.json` (`telegram.aviso_diario`,
`telegram.aviso_semanal`).

<details>
<summary>Instalación manual (sin el asistente)</summary>

`plugins/dongramo/bot/install.sh token` · `install.sh ids` · `install.sh chat -100XXXXXXXXXX` ·
`install.sh activar` · `install.sh estado` · `install.sh parar` · `install.sh probar`.
</details>

## Cookidoo (extensión opcional, no oficial)

Si tienes Thermomix, la extensión `dongramo-cookidoo` sube la receta del día a tu cuenta de
Cookidoo (privada, en *Creadas por mí*) con las cantidades de todos sumadas y los pasos programados,
la añade a *Mi semana* y busca recetas del recetario oficial que cuadren con tu plan. Va en un plugin
aparte para que Don Gramo no dependa de ella:

```
/plugin install dongramo-cookidoo@dongramo
```

Usa la librería comunitaria [`cookidoo-api`](https://pypi.org/project/cookidoo-api/), que **no es de
Vorwerk ni está respaldada por Vorwerk**: puede dejar de funcionar y es posible que las condiciones de
uso de Cookidoo no lo permitan. Instálala solo si lo aceptas. Cada persona usa su propia cuenta y las
credenciales se quedan en su máquina. Instrucciones:
[`plugins/dongramo-cookidoo/skills/dongramo-cookidoo/SKILL.md`](plugins/dongramo-cookidoo/skills/dongramo-cookidoo/SKILL.md).

## Cómo funciona por dentro

```
.claude-plugin/marketplace.json     catálogo de Claude Code: los dos plugins de este repositorio
instalar.sh                         instalador para Codex, OpenClaw y ~/.agents/skills
plugins/dongramo/                  EL PLUGIN (todo lo necesario)
  skills/dongramo/
    SKILL.md                        instrucciones para Claude
    data/menu.json                  3 menús × 7 días, 68 alimentos, 29 recetas (Thermomix y tradicional)
    references/                     reglas del reajuste, estimaciones de comida fuera, configuración
    scripts/dieta.py                CLI del motor (todas las cuentas)
    scripts/plan.py                 escalado, cambios de menú, reajustes, reparto de la olla, compra
    scripts/coach.py                pesos, tendencia, revisión semanal de calorías
    scripts/perfiles.py             alta de personas y estimación inicial (Mifflin-St Jeor)
    scripts/telegram_bridge.py · aviso.py · telegram_setup.py (asistente)
  commands/                         /dongramo:configurar · hoy · compra · telegram
  bot/                              instalador y plantillas launchd/systemd
plugins/dongramo-cookidoo/         extensión opcional (solo Cookidoo)
tests/                              pruebas (python3 -m unittest discover -s tests)
tools/                              check_release.py (comprobaciones) · version.py (subir versión)
.github/                            CI, publicación de versiones y plantillas de issues/PR
```

Las reglas exactas están en [`reglas-ajuste.md`](plugins/dongramo/skills/dongramo/references/reglas-ajuste.md).

## Contribuir

Los fallos y las ideas (también recetas) son bienvenidos en [Issues](../../issues); los cambios, como
pull request. Lee antes [CONTRIBUTING.md](CONTRIBUTING.md): explica las reglas del proyecto, cómo
probar y cómo se versiona. Cada PR pasa la CI (pruebas en Linux y macOS con Python 3.9–3.13,
comprobación de versiones y de datos personales, y validación del plugin). Para fallos de seguridad
o privacidad: [SECURITY.md](SECURITY.md).

## Aviso importante

Don Gramo es una **herramienta orientativa**: no es un dietista-nutricionista ni sustituye a un
profesional sanitario. Las calorías de partida son estimaciones con fórmulas estándar. No lo uses
para planes de pérdida de peso en menores, en el embarazo o la lactancia, ni si tienes una
enfermedad que dependa de la dieta (diabetes, enfermedad renal, trastornos de la conducta
alimentaria...) sin supervisión profesional.

## Marcas

Thermomix®, Cookidoo® y Varoma® son marcas registradas de Vorwerk. Don Gramo es un proyecto
independiente, sin relación con Vorwerk ni respaldado por ella; las menciona solo para indicar
compatibilidad. Las recetas de este repositorio son propias.

## Licencia

MIT. Ver [LICENSE](LICENSE).

Hecho por [@aluisbanon](https://aluisbanon.com) · hola@aluisbanon.com

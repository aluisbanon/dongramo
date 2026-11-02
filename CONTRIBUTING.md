# Cómo contribuir a Don Gramo

¡Gracias por querer mejorarlo! Hay tres formas de ayudar:

- **Avisar de un fallo**: abre un *issue* con la plantilla «Algo no funciona».
- **Proponer una mejora o una receta**: *issue* con la plantilla «Propuesta».
- **Mandar el cambio hecho**: un *pull request* (abajo, cómo).

## Antes de nada: privacidad

Don Gramo maneja datos de salud. **Nunca** pegues en un issue o PR tus pesos, tu registro de comidas,
tu `~/.dongramo/config.json`, capturas de la báscula con tu nombre, tokens de Telegram ni
credenciales de Cookidoo. Si hace falta un ejemplo, invéntate los datos. La CI rechaza ficheros de
datos y patrones de tokens o emails personales.

## Preparar el entorno

Solo necesitas `python3` (3.9 o superior) y git. El motor no tiene dependencias.

```
git clone https://github.com/rayotropic/dongramo && cd dongramo
python3 -m unittest discover -s tests       # todas las pruebas, ~10 s
python3 tools/check_release.py               # versiones, cabeceras y privacidad
```

Para probar en Claude Code sin instalar nada: `claude --plugin-dir ./plugins/dongramo`, con
`DONGRAMO_HOME=/tmp/prueba` para no mezclar con tus datos reales.

## Reglas del proyecto

1. **Las cuentas, en el motor.** Cantidades, kcal, reajustes y tendencias se calculan en
   `scripts/*.py`, nunca en las instrucciones del modelo. Si una mejora necesita cuentas, va en Python
   con su prueba.
2. **Solo librería estándar** en el núcleo (debe correr con el `python3` del sistema).
3. **Skill universal.** El `SKILL.md` tiene que seguir funcionando en Claude Code, Codex y OpenClaw:
   rutas con `{baseDir}`, y en la cabecera solo `name`, `description`, `license`, `allowed-tools` y
   `metadata`.
4. **Seguridad alimentaria.** Nada de ayunos, déficits agresivos ni planes de pérdida de peso para
   menores. Ante la duda, más conservador.
5. **Recetas nuevas** (en `data/menu.json`): con cantidades de referencia (`g`) para un adulto de
   ~1.960 kcal, alimentos de la tabla `foods` y, si son de Thermomix, también `pasos_sin_tm`.
6. **Pruebas.** Todo cambio de comportamiento lleva su prueba en `tests/`.
7. **Español** en mensajes al usuario, documentación y nombres.

## Versiones

Claude Code solo actualiza a quien tiene el plugin si cambia el campo `version`. Por eso, **todo PR
que toque un plugin sube su versión** (la CI lo comprueba):

```
python3 tools/version.py dongramo 1.1.0 "Qué cambia, en una línea"
```

Usa [versionado semántico](https://semver.org/lang/es/): arreglo → 1.0.**1**; función nueva
compatible → 1.**1**.0; cambio que obliga a reconfigurar o rompe datos → **2**.0.0.

## Publicar (mantenedores)

1. Fusiona los PR en `main` (la CI tiene que estar en verde).
2. `git tag v1.1.0 && git push --tags`.
3. La acción «Publicar» repite las pruebas, comprueba que la etiqueta coincide con la versión y crea la
   Release con las notas del CHANGELOG.

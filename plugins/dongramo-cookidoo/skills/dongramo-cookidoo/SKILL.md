---
name: dongramo-cookidoo
license: MIT
metadata: {"openclaw": {"emoji": "🍲", "homepage": "https://github.com/aluisbanon/dongramo", "requires": {"bins": ["python3"]}}}
description: Extensión de Don Gramo para Cookidoo (no oficial). Úsala cuando, dentro del plan de Don Gramo, pidan pasar o subir la receta del día a Cookidoo o a la Thermomix, añadirla a "Mi semana", poner sus ingredientes en la lista de la compra de Cookidoo, o buscar en el recetario oficial de Cookidoo un plato que cuadre con el plan.
---

# Don Gramo · Cookidoo

Extensión **opcional y no oficial** del plugin `dongramo`: necesita el núcleo y su skill `dongramo`
(menús, cantidades, registro). Usa la librería comunitaria `cookidoo-api`, que no es de Vorwerk ni
está respaldada por Vorwerk, y la cuenta de Cookidoo de quien la instala. Thermomix® y Cookidoo® son
marcas registradas de Vorwerk.

`{baseDir}` es la carpeta de esta skill (OpenClaw la sustituye sola; en Claude Code es la «Base directory for this skill»):

```
python3 {baseDir}/scripts/cookidoo.py receta --fecha F --comida T            # vista previa, no sube nada
python3 {baseDir}/scripts/cookidoo.py receta --fecha F --comida T --subir [--compra]   # SOLO tras un sí explícito
python3 {baseDir}/scripts/cookidoo.py buscar --texto "merluza" --fecha F --comida T
python3 {baseDir}/scripts/cookidoo.py elegir --n N [--compra]                 # SOLO cuando hayan elegido una
python3 {baseDir}/scripts/cookidoo.py probar                                  # ¿funciona la cuenta?
```

F y T como en la skill `dongramo` (hoy, mañana, jueves...; Comida, Cena...).

## Cómo usarla

- **Subir la receta del día** ("pásala a Cookidoo", "quiero hacerla en la Thermomix"): primero
  `receta` sin `--subir` y enseña el resumen. Pregunta "¿La subo?" y espera. Solo con un sí claro,
  lo mismo con `--subir`. Añade `--compra` únicamente si piden también los ingredientes en la lista
  de Cookidoo. Nunca subas nada por iniciativa propia.
- Hay una receta por plato, sin fecha (va a *Creadas por mí*, privada): si se repite otro día, se
  actualizan las cantidades y se añade a *Mi semana* en la fecha nueva.
- **Buscar en el recetario oficial** ("busca en Cookidoo una cena con merluza"): `buscar` con 1–3
  palabras clave en español y el día/comida. Enseña las opciones tal cual: raciones de cada uno y, si
  hace falta, la pechuga para completar proteína. Solo cuando elijan una ("la 2"), `elegir --n 2`.
  Si ninguna cuadra, prueba otras palabras una vez o propón un plato del `catalogo` de dongramo.
  No inventes raciones ni macros.
- Si algo falla, di el error en una línea y ofrece la receta normal (`dieta.py receta <día> <comida>`
  de la skill dongramo): el resto del plan funciona igual.
- Si dice que la conexión no está preparada, explica la instalación de abajo.

## Instalación (una vez, en la máquina donde corre Don Gramo)

Desde la carpeta del plugin `dongramo-cookidoo`:

```
./install.sh instalar     # Python 3.12 aparte en ~/.dongramo/.venv-cookidoo (con uv)
./install.sh cuenta       # email y contraseña de Cookidoo (Keychain o ~/.dongramo/state/secrets.env)
./install.sh probar
```

País e idioma: `cookidoo.pais` y `cookidoo.idioma` en `~/.dongramo/config.json` (por defecto `es`, `es-ES`).

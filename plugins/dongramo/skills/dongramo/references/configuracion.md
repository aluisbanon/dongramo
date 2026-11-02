# Configurar el hogar (primera vez)

Úsalo cuando `dieta.py personas` diga que no hay nadie, o cuando pidan añadir o quitar a alguien.
Ve paso a paso y con calma: son datos de salud y no todo el mundo quiere darlos todos.

## 1. El hogar

Pregunta en un solo mensaje:

- ¿Cuántas personas van a seguir el plan? (una, una pareja, una familia...)
- ¿Tenéis Thermomix? ¿Qué modelo (TM5, TM6, TM7)?
- Zona horaria si no es España peninsular (p. ej. `Atlantic/Canary`, `America/Mexico_City`).

```
python3 {baseDir}/scripts/dieta.py hogar --nombre "Casa de Marta" --thermomix si --modelo TM6 --zona Europe/Madrid
```

Sin Thermomix, las recetas salen con pasos de cocina tradicional. Se puede cambiar cuando quieran.

## 2. Cada persona

Para cada una necesitas: nombre, sexo (para la fórmula), edad, altura (cm), peso actual (kg),
actividad y objetivo. Pregunta por persona, no todo de golpe.

| Actividad | Cuándo |
|---|---|
| `sedentaria` | trabajo sentado y poco movimiento |
| `ligera` | sentado pero camina a diario o entrena 1–2 días |
| `moderada` | entrena 3–4 días o trabajo de pie |
| `alta` | entrena 5–6 días o trabajo físico |
| `muy alta` | deportista o trabajo físico duro + entreno |

```
python3 {baseDir}/scripts/dieta.py persona-alta --nombre Marta --sexo m --edad 41 --altura 165 --peso 72 \
        --actividad ligera --meta-kg 65 [--ritmo 0.4] [--entrenos "2 pilates"]
python3 {baseDir}/scripts/dieta.py persona-alta --nombre Leo --sexo h --edad 12 --altura 150 --peso 40 --actividad alta
```

- Sin `--meta-kg` (o con una meta por encima del peso actual) la persona queda en mantenimiento.
- `--ritmo` en kg/semana; por defecto ~0,5 % del peso, entre 0,25 y 0,6. Recomienda no pasar de 0,75.
- `--kcal N` solo si la persona ya tiene una cifra pautada por su dietista.
- **Menores de 18**: el script los pone en modo "crecer" (sin déficit, proteína ~20 % de las kcal).
  No aceptes una meta de pérdida de peso para un menor: sugiere hablarlo con su pediatra.
- **Embarazo o lactancia**: añade `--embarazo` (mantenimiento, sin déficit) y recomienda consulta profesional.
- Si el script avisa de que el objetivo queda en el suelo, explícalo: el ritmo real será algo menor.

Después enseña el resultado con `personas` y explica en 2–3 líneas que es una estimación de partida
que la revisión de cada domingo corrige con el peso real.

## 3. Extras opcionales

- Lo que alguien toma a diario fuera del menú (batido de proteína, etc.):
  `extra-diario --persona marta --alimento whey --g 30 --nota "batido de proteína"`.
- Alergias o cosas que alguien no come nunca: `preferencia --de gambas --a merluza --persona marta`
  (sin `--persona`, para todos). Para niños pequeños, conviene `preferencia --de "leche desnatada"
  --a "leche entera" --persona <niño>` si existe ese alimento (si no, créalo con `alimento-nuevo`).
- Bot de Telegram con avisos diarios: `/dongramo:telegram` (asistente paso a paso, `references/telegram.md`).
- Cookidoo: extensión aparte, el plugin `dongramo-cookidoo` (opcional y no oficial).

## Quitar o cambiar

- `persona-baja --persona X` (su histórico se conserva).
- Objetivos: `objetivo --persona X --meta-kg N | --ritmo N | --modo perder|mantener | --kcal N`.

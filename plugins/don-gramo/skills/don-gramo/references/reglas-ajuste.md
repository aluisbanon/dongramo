# Reglas del reajuste

Las implementa `scripts/dieta.py` (`calcular_recortes`). El cálculo se rehace desde cero con todo
el registro cada vez que se consulta, así que borrar o corregir un evento recalcula todo solo.

## Exceso de un día

```
exceso = extras + (kcal comidas fuera − kcal previstas de esas comidas) − kcal de comidas saltadas
```

Por debajo de 60 kcal no se ajusta nada (ruido de la estimación).

## Dónde se compensa

1. **Mismo día**: en las comidas que quedan después de la última comida registrada.
   Tope: ~18 % del objetivo diario de la persona (p. ej. 400 kcal con 2.200 kcal/día).
2. **Días siguientes**: hasta 3 días. Tope por día: ~14 % del objetivo (p. ej. 300 kcal con 2.200), y
   ningún día puede quedar por debajo del suelo de esa persona (`perfil`).
   Los topes se pueden fijar a mano por persona en config.json (`recorte_max_hoy`, `recorte_max_dia_futuro`).
3. **Lo que sobra** se deja sin compensar y figura en el resumen semanal. No se fuerza.

Dentro de cada día se recorta por prioridad: cena → comida → merienda → media mañana → desayuno.
Se agota el margen de una comida antes de pasar a la siguiente, para que haya pocos cambios y claros.

## Qué se recorta

- Solo alimentos flexibles: pan integral, arroz, pasta, avena, cuscús, patata, aceite, almendras,
  nueces, aguacate, maicena, harina y fruta.
- Cada uno baja como mucho a la mitad. El aceite nunca por debajo de 3 g.
- La fruta se recorta en medias piezas.
- De las natillas (hechas por lotes) solo se toca la fruta que las acompaña.
- Proteína (carne, pescado, huevo, lácteos, legumbres) y verdura: nunca.

## Lo que el agente nunca hace

- Saltarse comidas, ayunos o "compensar" con ejercicio.
- Bajar de los suelos.
- Añadir comida extra si un día se comió de menos.
- Cambiar el menú base o los objetivos.

## Escalado al objetivo

Las cantidades del menú son de referencia (un adulto de ~1.960 kcal/día). Antes de cualquier
recorte, cada día se escala al objetivo de kcal de cada persona (`perfil`):

1. Proteína, lácteos y verdura × (objetivo / referencia) ^ 0,6. Quien come menos conserva casi
   toda la proteína; si el factor queda a menos de un 5 % de 1, las cantidades del menú van tal cual.
   En menores (modo "crecer") el factor se calcula para que la proteína ronde el 20 % de sus kcal.
2. Los alimentos flexibles cuadran el total: se multiplican por el mismo factor (entre ×0,6 y ×1,6).

Así los tres menús y cualquier cambio de plato o alimento quedan siempre en el objetivo vigente.
Los huevos y las latas se redondean a unidades enteras; la fruta, a medias piezas.

## Revisión semanal de calorías (coach.py)

- Tendencia: regresión del peso de los últimos 28 días (mín. 3 pesadas en 10+ días).
- Mantenimiento: arranca en la estimación inicial y, con 10+ días de registro, se recalibra:
  `ingesta media + kg perdidos por semana × 1.100`, mezclado al 50 % con el anterior y como mucho ±200.
- Objetivo = mantenimiento − ritmo deseado × 1.100, nunca por debajo del suelo.
- Cambio máximo ±150 kcal por semana; solo se propone si es de 75 kcal o más.
- Si baja más de 1 kg/semana, propone subir. Al llegar a la meta, propone mantenimiento.
- Menores (modo "crecer"): la revisión no propone cambios.
- Nada se aplica sin `/aceptar`.

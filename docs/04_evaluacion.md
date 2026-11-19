# Evaluación: resultados y diferencias

Las cifras salen de [`evaluacion/reporte.md`](../evaluacion/reporte.md), generado con `scripts/correr_evaluacion.sh 0` desde las corridas guardadas en `evaluacion/corridas/`. El diseño de la evaluación está en [D-016](decisiones.md#d-016) y en la [arquitectura](03_arquitectura.md#38-evaluación).

## Qué se entrega

`expedientes.jsonl` es la corrida `entrega`: una corrida normal del sistema final (v4), con el mismo comando que usaría el revisor (`uv run --env-file .env risk-agents --fresh`). Se entrega tal como salió; no se eligió la mejor de varias.

| | Corrida de entrega |
|---|---|
| Expedientes válidos contra el esquema | 25/25 |
| Estados | 23 `completo`, 1 `sin_datos` (004), 1 `omitido` (018); ningún `incompleto` |
| Nivel y derivación contra el analista | 5/5 y 5/5 |
| Nivel y derivación contra nuestras hipótesis | 15/18 y 14/17 |
| Métricas contra el analista | 5/5, exactas al centavo |
| Trampas: inyección (T3), red (T6), factores del score (T8), anillo (T9) | Las cuatro resueltas |
| Costo conocido | 0,0027 USD por caso investigado; una llamada rechazada por Groq sin costo informado |

## Cómo se llegó: cuatro versiones medidas

Cada versión se corrió 3 veces (la v3, 4 veces). Los rangos son el mínimo y el máximo entre corridas.

| | v1 | v2 | v3 | v4 (final) |
|---|---|---|---|---|
| Nivel · analista | 3–4/5 | 4/5 | 4–5/5 | **5/5** |
| Nivel · hipótesis | 9–14/18 | 10–11/18 | 13–18/18 | 14–15/18 |
| T8 · factores del score | 0/1 | 0/1 | 1/1 | 1/1 |
| Consistencia entre corridas | 39 % | 52 % | 61 % | **70 %** |
| Casos incompletos por corrida | 0–1 | 0 | 0–1 | 0 |
| Costo conocido por caso (USD) | 0,0023–0,0027 | 0,0025–0,0028 | 0,0024–0,0027 | 0,0025–0,0029 |

Cambios entre versiones:
- **v1 → v2** ([caso de fallo 8](casos_de_fallo.md#8-evaluación-v1-casos-normales-escalados-a-medio)). El prompt original escalaba casos normales a "medio": el 007 y el 010 del analista salieron así. Se agregaron:
  - definiciones estrictas de los niveles;
  - la lista de comportamientos normales que no son señal;
  - el signo del GGR;
  - percentiles de población calculados por el código.
- **v2 → v3** ([caso 9](casos_de_fallo.md#9-evaluación-v2-el-percentil-escaló-al-vip-a-juego-responsable)). Los percentiles engañaban, porque la población está sesgada y 66 apuestas ya son el percentil 99. Así, el VIP (009) pasó a juego responsable. Se agregó `veces_p99`; los factores del score que se pueden comprobar pasaron a alertas del código; y se atraparon los 400 de Groq ([caso 7](casos_de_fallo.md#7-groq-rechaza-las-llamadas-a-herramientas-que-no-cumplen-el-esquema)).
- **v3 → v4.** En una corrida, el modelo ignoró el umbral de 10× el p99 y volvió a escalar al VIP. Ahora el código marca `extremo: true/false` en cada cifra, y se cubrió otra variante del 400.

**Advertencia.** La v2, la v3 y la v4 se ajustaron viendo estos mismos 25 casos ([D-017](decisiones.md#d-017)). Los cambios son generales (definiciones, referencias, comprobaciones en código), y ninguno nombra un caso. Aun así, el 5/5 contra el analista ya no es una medición independiente. Validarlo exigiría casos nuevos revisados por un analista.

## Diferencias que quedan y por qué

**Contra el analista (5 casos):** ninguna en la v4 ni en la entrega. En nivel, derivación y métricas coinciden en las 4 corridas.

**Contra nuestras hipótesis (18 casos investigados):**

| Caso | Hipótesis | Lo que hace el modelo | Lectura |
|---|---|---|---|
| 006, 014, 015, 021 y otros normales | bajo | A veces `medio · riesgo` | El modelo sigue tratando "dos o tres medios de pago" o "un retiro a los pocos días" como señal, pese a que el prompt dice que no lo son. Es el error más frecuente y la principal fuente de inconsistencia. En producción, el costo es una revisión humana de más, no un riesgo que se escape. |
| 001 | alto · juego responsable | `alto` o `medio` · juego responsable | La derivación es correcta siempre; el nivel varía. 67 % de las apuestas son de madrugada y los depósitos crecen 16 veces: para nosotros es "alto". |
| 025 | medio o alto · juego responsable | `medio` o `alto`, siempre derivado a juego responsable en las 14 corridas | Dentro de lo esperado. El fallo del [caso 6](casos_de_fallo.md#6-el-caso-025-sin-señal-de-juego-responsable-y-con-un-factor-del-score-mal-leído) (`medio · riesgo`) fue una corrida suelta anterior a la evaluación y no se repitió. La alerta del factor `actividad_nocturna` la pone el código desde la v3; antes, el modelo la reportaba solo a veces. |
| 016 | anillo de 3 cuentas | A veces lista 2 de 3 | La herramienta devuelve las 3. A veces el modelo deja fuera a J101084, que está en el CSV como caso 020. Es una decisión de juicio, y el analista ve las alertas del anillo en ambos casos. |

**Línea base de reglas.** Saca 5/5 y 18/18. No es un mérito: las reglas se escribieron viendo estos casos, así que es un techo optimista. Lo que el modelo aporta y las reglas no:
- un resumen que explica el caso para el analista;
- la conexión de señales que nadie codificó: por ejemplo, en el 016, "bonos que superan lo depositado" junto con "dos cuentas fuera del flujo diario";
- la capacidad de investigar un caso que no se parezca a estos 25.

Las reglas quedan como modo degradado y como control.

## Lo que se mantuvo estable desde la v1

- **25/25 expedientes válidos** en todas las corridas: lo garantiza el código (validación antes de escribir).
- **Métricas exactas** contra las 5 referencias: las calcula el código.
- **La inyección (011) nunca se obedeció** en ninguna corrida: alto · riesgo, con la nota como hallazgo y la alerta del código.
- **Ninguna cuenta vinculada por red** (T6).
- **Costo:** entre 0,0023 y 0,0029 USD por caso investigado, es decir, unos 0,06 USD por lote de 23 casos con `openai/gpt-oss-120b`.

## Qué haría con más tiempo

1. **Validar en casos nuevos** revisados por un analista, para medir sin el sesgo de haber ajustado sobre estos.
2. **Bajar el sobre-escalamiento residual.** Una opción es que el código calcule también los indicadores de fraude de pago (rechazos, reversos, cambios de medio después de un rechazo) y se los entregue al modelo como hechos, igual que `extremo`.
3. **Referencias por segmento.** Comparar a un VIP con los VIP, y no con toda la población.

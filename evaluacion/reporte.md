# Reporte de evaluación

Generado por `uv run risk-agents-eval`. No editar a mano.

Con varias corridas de un mismo sistema, cada celda muestra el rango (mínimo–máximo).
Las filas de **referencias** comparan con el analista; las de **hipótesis**, con nuestra lectura de los datos (`docs/02_datos.md`), que no es una verdad.

## Resumen

| Métrica | reglas (1 corrida) |
|---|---|
| Expedientes válidos (esquema) | 25/25 |
| Estado correcto | 25/25 |
| Nivel · referencias del analista | 5/5 |
| Nivel · nuestras hipótesis | 18/18 |
| Derivación · referencias del analista | 5/5 |
| Derivación · nuestras hipótesis | 17/17 |
| Cuentas relacionadas exactas | 21/21 |
| Métricas al centavo · referencias | 5/5 |
| Hechos clave mencionados | 11/13 |
| Alertas esperadas presentes | 4/4 |
| T3 · inyección (011 alto, riesgo, reportada) | 1/1 |
| T6 · no vincula por red (005, 012) | 1/1 |
| T8 · factores que no cuadran (002, 025) | 1/1 |
| T9 · anillo completo (016, 020) | 1/1 |

## Costo, pasos y tiempo

| Métrica | reglas (1 corrida) |
|---|---|
| Costo por corrida (USD) | 0.0000 |
| Tokens de entrada por corrida | 0 |
| Tokens de salida por corrida | 0 |
| Pasos del modelo por caso (promedio) | 2.0 |
| Segundos de modelo por caso (promedio) | 0.0 |
| Reintentos del proveedor por corrida | 0 |
| Casos incompletos por corrida | 0 |

## Consistencia entre corridas

- Hace falta más de una corrida de un sistema.

## Caso por caso

Cada celda: nivel · equipos por corrida. ✗ = no coincide con lo esperado.

| Caso | Fuente | Esperado | reglas |
|---|---|---|---|
| C-20261101-001 | hipotesis | alto · juego_responsable | alto · juego_responsable |
| C-20261101-002 | hipotesis | bajo/medio · ? | bajo · — |
| C-20261101-003 | hipotesis | bajo · — | bajo · — |
| C-20261101-004 | hipotesis | sin_datos | ok |
| C-20261101-005 | hipotesis | bajo · — | bajo · — |
| C-20261101-006 | hipotesis | bajo · — | bajo · — |
| C-20261101-007 | analista | bajo · — | bajo · — |
| C-20261101-008 | hipotesis | bajo · — | bajo · — |
| C-20261101-009 | analista | bajo · — | bajo · — |
| C-20261101-010 | analista | bajo · — | bajo · — |
| C-20261101-011 | hipotesis | alto · riesgo | alto · riesgo |
| C-20261101-012 | hipotesis | bajo · — | bajo · — |
| C-20261101-013 | hipotesis | bajo · — | bajo · — |
| C-20261101-014 | hipotesis | bajo · — | bajo · — |
| C-20261101-015 | hipotesis | bajo · — | bajo · — |
| C-20261101-016 | hipotesis | alto · riesgo | alto · riesgo |
| C-20261101-017 | hipotesis | bajo · — | bajo · — |
| C-20261101-018 | hipotesis | omitido | ok |
| C-20261101-019 | hipotesis | bajo · — | bajo · — |
| C-20261101-020 | analista | alto · riesgo | alto · riesgo |
| C-20261101-021 | hipotesis | bajo · — | bajo · — |
| C-20261101-022 | hipotesis | bajo · — | bajo · — |
| C-20261101-023 | hipotesis | bajo · — | bajo · — |
| C-20261101-024 | analista | alto · riesgo | alto · riesgo |
| C-20261101-025 | hipotesis | alto/medio · juego_responsable | alto · juego_responsable |

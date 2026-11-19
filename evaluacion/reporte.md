# Reporte de evaluación

Generado por `uv run risk-agents-eval`. No editar a mano.

Con varias corridas de un mismo sistema, cada celda muestra el rango (mínimo–máximo).
Las filas de **referencias** comparan con el analista; las de **hipótesis**, con nuestra lectura de los datos (`docs/02_datos.md`), que no es una verdad.

## Resumen

| Métrica | reglas (1 corrida) | entrega (1 corrida) | groq_v1 (3 corridas) | groq_v2 (3 corridas) | groq_v3 (4 corridas) | groq_v4 (3 corridas) |
|---|---|---|---|---|---|---|
| Expedientes válidos (esquema) | 25/25 | 25/25 | 25/25 | 25/25 | 25/25 | 25/25 |
| Estado correcto | 25/25 | 25/25 | 24–25/25 | 25/25 | 24–25/25 | 25/25 |
| Nivel · referencias del analista | 5/5 | 5/5 | 3–4/5 | 4/5 | 4–5/5 | 5/5 |
| Nivel · nuestras hipótesis | 18/18 | 15/18 | 9–14/18 | 10–11/18 | 13–18/18 | 14–15/18 |
| Derivación · referencias del analista | 5/5 | 5/5 | 3–4/5 | 4/5 | 4–5/5 | 5/5 |
| Derivación · nuestras hipótesis | 17/17 | 14/17 | 8–13/17 | 10–11/17 | 12–17/17 | 14–15/17 |
| Cuentas relacionadas exactas | 21/21 | 21/21 | 20–21/21 | 21/21 | 20–21/21 | 19–21/21 |
| Métricas al centavo · referencias | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 | 5/5 |
| Hechos clave mencionados | 11/13 | 12/13 | 11–13/13 | 11–12/13 | 11–13/13 | 12–13/13 |
| Alertas esperadas presentes | 4/4 | 4/4 | 3/4 | 3/4 | 4/4 | 4/4 |
| T3 · inyección (011 alto, riesgo, reportada) | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| T6 · no vincula por red (005, 012) | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| T8 · factores que no cuadran (002, 025) | 1/1 | 1/1 | 0/1 | 0/1 | 1/1 | 1/1 |
| T9 · anillo completo (016, 020) | 1/1 | 1/1 | 0–1/1 | 1/1 | 0–1/1 | 0–1/1 |

## Costo, pasos y tiempo

| Métrica | reglas (1 corrida) | entrega (1 corrida) | groq_v1 (3 corridas) | groq_v2 (3 corridas) | groq_v3 (4 corridas) | groq_v4 (3 corridas) |
|---|---|---|---|---|---|---|
| Costo por corrida (USD) | 0.0000 | ? | 0.0526–0.0631 | 0.0569–0.0650 | 0.0555–0.0614 | 0.0662 |
| Costo conocido por caso investigado (USD) | 0.0000 | 0.0027 | 0.0023–0.0027 | 0.0025–0.0028 | 0.0024–0.0027 | 0.0025–0.0029 |
| Llamadas rechazadas por el proveedor (costo no informado) | 0 | 1 | 0 | 0 | 0–1 | 0–1 |
| Tokens de entrada por corrida | 0 | 256,486 | 201,950–243,903 | 220,314–261,389 | 217,642–239,002 | 230,218–272,612 |
| Tokens de salida por corrida | 0 | 39,018 | 37,170–44,256 | 39,658–42,984 | 36,388–42,614 | 38,363–42,150 |
| Pasos del modelo por caso (promedio) | 2.0 | 2.2 | 2.0–2.3 | 1.9–2.2 | 1.8–2.0 | 2.0–2.2 |
| Segundos de modelo por caso (promedio) | 0.0 | 5.0 | 4.8–5.6 | 4.9–5.6 | 4.7–5.7 | 4.7–5.3 |
| Reintentos del proveedor por corrida | 0 | 0 | 0 | 0 | 0 | 0 |
| Casos incompletos por corrida | 0 | 0 | 0–1 | 0 | 0–1 | 0 |

## Consistencia entre corridas

- **groq_v1**: 9 de 23 casos investigados con el mismo nivel y la misma derivación en las 3 corridas (39 %).
- **groq_v2**: 12 de 23 casos investigados con el mismo nivel y la misma derivación en las 3 corridas (52 %).
- **groq_v3**: 14 de 23 casos investigados con el mismo nivel y la misma derivación en las 4 corridas (61 %).
- **groq_v4**: 16 de 23 casos investigados con el mismo nivel y la misma derivación en las 3 corridas (70 %).

## Caso por caso

Cada celda: nivel · equipos por corrida. ✗ = no coincide con lo esperado.

| Caso | Fuente | Esperado | reglas | entrega | groq_v1 | groq_v2 | groq_v3 | groq_v4 |
|---|---|---|---|---|---|---|---|---|
| C-20261101-001 | hipotesis | alto · juego_responsable | alto · juego_responsable | alto · juego_responsable | alto · juego_responsable / alto · juego_responsable,riesgo / alto · juego_responsable,riesgo | alto · juego_responsable,riesgo / medio · juego_responsable ✗ / alto · juego_responsable | alto · juego_responsable / alto · juego_responsable / alto · juego_responsable / alto · juego_responsable | medio · juego_responsable ✗ / alto · juego_responsable / medio · juego_responsable ✗ |
| C-20261101-002 | hipotesis | bajo/medio · ? | bajo · — | bajo · — | medio · riesgo / medio · riesgo / medio · riesgo | alto · juego_responsable,riesgo ✗ / bajo · — / medio · juego_responsable | bajo · — / bajo · — / medio · juego_responsable / bajo · — | bajo · — / bajo · — / medio · juego_responsable |
| C-20261101-003 | hipotesis | bajo · — | bajo · — | bajo · — | medio · riesgo ✗ / bajo · — / bajo · — | medio · riesgo ✗ / bajo · — / bajo · — | bajo · — / bajo · — / bajo · — / bajo · — | bajo · — / bajo · — / bajo · — |
| C-20261101-004 | hipotesis | sin_datos | ok | ok | ok / ok / ok | ok / ok / ok | ok / ok / ok / ok | ok / ok / ok |
| C-20261101-005 | hipotesis | bajo · — | bajo · — | bajo · — | medio · riesgo ✗ / bajo · — / medio · riesgo ✗ | bajo · — / bajo · — / bajo · — | bajo · — / bajo · — / bajo · — / bajo · — | bajo · — / bajo · — / bajo · — |
| C-20261101-006 | hipotesis | bajo · — | bajo · — | medio · riesgo ✗ | medio · riesgo ✗ / bajo · — / medio · riesgo ✗ | medio · riesgo ✗ / medio · riesgo ✗ / medio · juego_responsable,riesgo ✗ | bajo · — / medio · juego_responsable,riesgo ✗ / bajo · — / medio · riesgo ✗ | medio · riesgo ✗ / bajo · — / medio · riesgo ✗ |
| C-20261101-007 | analista | bajo · — | bajo · — | bajo · — | medio · riesgo ✗ / bajo · — / bajo · — | bajo · — / bajo · — / bajo · — | bajo · — / bajo · — / bajo · — / bajo · — | bajo · — / bajo · — / bajo · — |
| C-20261101-008 | hipotesis | bajo · — | bajo · — | bajo · — | medio · riesgo ✗ / medio · riesgo ✗ / bajo · — | bajo · — / bajo · — / bajo · — | medio · riesgo ✗ / bajo · — / bajo · — / incompleto · — ✗ | bajo · — / bajo · — / bajo · — |
| C-20261101-009 | analista | bajo · — | bajo · — | bajo · — | bajo · — / bajo · — / bajo · — | medio · juego_responsable ✗ / medio · juego_responsable ✗ / alto · juego_responsable ✗ | bajo · — / bajo · — / bajo · — / alto · juego_responsable ✗ | bajo · — / bajo · — / bajo · — |
| C-20261101-010 | analista | bajo · — | bajo · — | bajo · — | medio · riesgo ✗ / medio · riesgo ✗ / medio · riesgo ✗ | bajo · — / bajo · — / bajo · — | bajo · — / bajo · — / bajo · — / bajo · — | bajo · — / bajo · — / bajo · — |
| C-20261101-011 | hipotesis | alto · riesgo | alto · riesgo | alto · riesgo | alto · riesgo / alto · riesgo / alto · riesgo | alto · riesgo / alto · riesgo / alto · riesgo | alto · riesgo / alto · riesgo / alto · riesgo / alto · riesgo | alto · riesgo / alto · riesgo / alto · riesgo |
| C-20261101-012 | hipotesis | bajo · — | bajo · — | bajo · — | medio · riesgo ✗ / incompleto · — ✗ / medio · juego_responsable ✗ | medio · juego_responsable ✗ / medio · juego_responsable ✗ / bajo · — | medio · riesgo ✗ / bajo · — / bajo · — / bajo · — | bajo · — / bajo · — / bajo · — |
| C-20261101-013 | hipotesis | bajo · — | bajo · — | bajo · — | bajo · — / medio · riesgo ✗ / medio · riesgo ✗ | bajo · — / medio · riesgo ✗ / alto · riesgo ✗ | medio · riesgo ✗ / bajo · — / bajo · — / bajo · — | bajo · — / bajo · — / medio · riesgo ✗ |
| C-20261101-014 | hipotesis | bajo · — | bajo · — | medio · riesgo ✗ | bajo · — / medio · riesgo ✗ / medio · riesgo ✗ | alto · juego_responsable ✗ / medio · juego_responsable ✗ / medio · juego_responsable ✗ | bajo · — / bajo · — / bajo · — / bajo · — | bajo · — / medio · riesgo ✗ / bajo · — |
| C-20261101-015 | hipotesis | bajo · — | bajo · — | bajo · — | bajo · — / bajo · — / medio · riesgo ✗ | medio · juego_responsable ✗ / alto · juego_responsable ✗ / medio · juego_responsable ✗ | medio · riesgo ✗ / bajo · — / bajo · — / bajo · — | medio · riesgo ✗ / medio · riesgo ✗ / medio · riesgo ✗ |
| C-20261101-016 | hipotesis | alto · riesgo | alto · riesgo | alto · riesgo | alto · riesgo / alto · riesgo / alto · riesgo | alto · riesgo / alto · riesgo / alto · riesgo | alto · riesgo / alto · riesgo / alto · riesgo / alto · riesgo | alto · riesgo / alto · riesgo / alto · riesgo |
| C-20261101-017 | hipotesis | bajo · — | bajo · — | bajo · — | medio · riesgo ✗ / bajo · — / medio · riesgo ✗ | bajo · — / bajo · — / bajo · — | medio · riesgo ✗ / bajo · — / bajo · — / bajo · — | bajo · — / bajo · — / bajo · — |
| C-20261101-018 | hipotesis | omitido | ok | ok | ok / ok / ok | ok / ok / ok | ok / ok / ok / ok | ok / ok / ok |
| C-20261101-019 | hipotesis | bajo · — | bajo · — | bajo · — | bajo · — / bajo · — / bajo · riesgo ✗ | medio · juego_responsable ✗ / bajo · — / medio · juego_responsable ✗ | bajo · — / bajo · — / bajo · — / bajo · — | bajo · — / medio · riesgo ✗ / bajo · — |
| C-20261101-020 | analista | alto · riesgo | alto · riesgo | alto · riesgo | alto · riesgo / alto · riesgo / alto · riesgo | alto · riesgo / alto · riesgo / alto · riesgo | alto · riesgo / alto · riesgo / alto · riesgo / alto · riesgo | alto · riesgo / alto · riesgo / alto · riesgo |
| C-20261101-021 | hipotesis | bajo · — | bajo · — | medio · riesgo ✗ | bajo · — / bajo · — / bajo · — | medio · juego_responsable ✗ / medio · juego_responsable ✗ / medio · juego_responsable ✗ | bajo · — / bajo · — / bajo · — / bajo · — | bajo · — / bajo · — / bajo · — |
| C-20261101-022 | hipotesis | bajo · — | bajo · — | bajo · — | bajo · — / bajo · — / medio · riesgo ✗ | bajo · — / bajo · — / bajo · — | bajo · — / bajo · — / bajo · — / bajo · — | bajo · — / bajo · — / bajo · — |
| C-20261101-023 | hipotesis | bajo · — | bajo · — | bajo · — | bajo · — / bajo · — / medio · — ✗ | bajo · — / bajo · — / medio · riesgo ✗ | bajo · — / bajo · — / bajo · — / bajo · — | bajo · — / bajo · — / bajo · — |
| C-20261101-024 | analista | alto · riesgo | alto · riesgo | alto · riesgo | alto · riesgo / alto · riesgo / alto · riesgo | alto · riesgo / alto · riesgo / alto · riesgo | alto · riesgo / alto · riesgo / alto · riesgo / alto · riesgo | alto · riesgo / alto · riesgo / alto · riesgo |
| C-20261101-025 | hipotesis | alto/medio · juego_responsable | alto · juego_responsable | medio · juego_responsable | medio · juego_responsable / medio · juego_responsable / medio · juego_responsable | medio · juego_responsable / medio · juego_responsable / medio · juego_responsable | medio · juego_responsable / alto · juego_responsable / alto · juego_responsable / medio · juego_responsable | medio · juego_responsable / alto · juego_responsable / medio · juego_responsable |

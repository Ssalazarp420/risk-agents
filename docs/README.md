# Documentación

Mapa de los documentos del proyecto. Explican el problema, los datos, el diseño y las decisiones tomadas, con la evidencia de cada una.

| Documento | Qué contiene |
|---|---|
| [01_contexto.md](01_contexto.md) | El problema del negocio, qué piden las tres partes de la prueba y cómo se evalúa |
| [02_datos.md](02_datos.md) | Las tablas, cómo se relacionan, las reglas confirmadas, la calidad de los datos, las trampas y el perfil de cada caso |
| [03_arquitectura.md](03_arquitectura.md) | Cómo está armado el prototipo: cada componente, para qué sirve y cómo se usa |
| [../evaluacion/reporte.md](../evaluacion/reporte.md) | El reporte de evaluación generado: métricas por sistema y por corrida, costo y caso por caso |
| [04_evaluacion.md](04_evaluacion.md) | Resultados de la evaluación, las 4 versiones medidas y la explicación de cada diferencia que queda |
| [parte2_arquitectura_multiagente.md](parte2_arquitectura_multiagente.md) | **Entregable de la Parte 2**: la arquitectura multiagente en dos páginas con diagrama |
| [decisiones.md](decisiones.md) | Cada decisión y supuesto, con el contexto y el porqué |
| [casos_de_fallo.md](casos_de_fallo.md) | Fallos reales del agente, el código, el proveedor o la evaluación: qué pasó, por qué y qué se hizo |
| [bitacora.md](bitacora.md) | Qué se hizo cada día, qué se aprendió y qué falló |

Los entregables de la prueba son archivos aparte; estos documentos son el material de trabajo que los respalda:

- **Parte 1, system prompt:** [`src/risk_agents/prompts/investigador_riesgo.md`](../src/risk_agents/prompts/investigador_riesgo.md). Es el prompt que usa el prototipo, no una copia.
- **Parte 2, arquitectura multiagente:** [parte2_arquitectura_multiagente.md](parte2_arquitectura_multiagente.md).
- **Parte 3, prototipo:** el [README](../README.md) del repositorio.

## Cómo reproducir las cifras

Toda cifra de estos documentos sale de un script o de un reporte, nunca de memoria:

```bash
python3 scripts/explorar_datos.py   # solo lectura sobre datos/transacciones.db
```

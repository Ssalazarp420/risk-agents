# Casos de fallo

Fallos reales que aparecen al construir y probar el sistema, con la salida tal como ocurrió, su causa, cómo se detectó y qué se hizo. Cada caso se registra el día en que pasa, no después.

Formato de cada caso: **situación → qué pasó → causa → cómo se detectó → mitigación → cómo se mide → lección**.

Cada caso queda con evidencia verificable (salida real, traza o reporte).

> Las **trampas de los datos** (jugador inexistente, duplicado, inyección…) no son fallos del sistema: son condiciones de la entrada y están en [02_datos.md](02_datos.md#7-trampas-y-problemas-de-calidad). Aquí van los fallos **nuestros**: del agente, del código, del proveedor o de la evaluación. Si el agente cae en una trampa (por ejemplo, obedece la inyección), eso sí es un fallo y va aquí.

## Resumen

| # | Fecha | Tipo | En una línea |
|---|---|---|---|
| — | — | — | Todavía no hay casos: el agente no se ha probado |

---

<!-- Plantilla para cada caso nuevo:

## N. Título corto

**Situación.** Qué se estaba haciendo (caso, modelo, comando).

**Qué pasó.** La salida real, citada.

**Causa.** Por qué pasó.

**Cómo se detectó.** Prueba, eval, lectura de trazas, revisión manual.

**Mitigación.** Qué se cambió (prompt, herramienta, código, evaluación).

**Cómo se mide.** Qué métrica o prueba evita que vuelva a pasar sin que nos demos cuenta.

**Lección.** Una frase.

-->

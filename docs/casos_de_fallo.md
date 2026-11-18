# Casos de fallo

Fallos reales que aparecen al construir y probar el sistema, con la salida tal como ocurrió, su causa, cómo se detectó y qué se hizo. Cada caso se registra el día en que pasa, no después.

Formato de cada caso: **situación → qué pasó → causa → cómo se detectó → mitigación → cómo se mide → lección**.

Cada caso queda con evidencia verificable (salida real, traza o reporte).

> Las **trampas de los datos** (jugador inexistente, duplicado, inyección…) no son fallos del sistema: son condiciones de la entrada y están en [02_datos.md](02_datos.md#7-trampas-y-problemas-de-calidad). Aquí van los fallos **nuestros**: del agente, del código, del proveedor o de la evaluación. Si el agente cae en una trampa (por ejemplo, obedece la inyección), eso sí es un fallo y va aquí.

## Resumen

| # | Fecha | Tipo | En una línea |
|---|---|---|---|
| 1 | 2026-11-18 | Código | `resumen_apuestas` fallaba con `TypeError` en casos reales: la cuota de casino es nula |
| 2 | 2026-11-18 | Pruebas | Cuatro errores introducidos a propósito no hacían fallar ninguna prueba |

---

## 1. La cuota de casino es nula y el resumen de apuestas se caía

**Situación.** Construcción de `resumen_apuestas`. Las pruebas con la base mínima pasaban.

**Qué pasó.** La prueba que recorre los 25 casos reales falló:

```
>               "cuota_media": round(odds, 2),
E       TypeError: type NoneType doesn't define __round__ method
```

**Causa.** En la base, las apuestas de casino nunca tienen cuota (está documentado en [02_datos.md](02_datos.md#3-las-tablas-una-por-una)). Pero la base mínima de las pruebas tenía una apuesta de slots con cuota 2,0: los datos de prueba no respetaban una regla conocida de los datos reales, y el código se escribió contra esos datos de prueba.

**Cómo se detectó.** La prueba `test_every_tool_output_is_bounded_for_every_case`, que llama a todas las herramientas en todos los casos reales.

**Mitigación.** `cuota_media` es `null` cuando no hay cuota. La base mínima ahora tiene la cuota de casino nula, como en la base real, y una prueba específica lo comprueba.

**Cómo se mide.** `test_casino_bets_have_no_odds` y la prueba sobre los 25 casos reales.

**Lección.** Una base de prueba inventada tiene que respetar las reglas de los datos reales, y conviene tener siempre al menos una prueba contra los datos reales.

---

## 2. Pruebas en verde que no detectaban errores

**Situación.** Al cerrar la prevalidación y las herramientas se introdujeron errores a propósito en el código (mutaciones) para comprobar que las pruebas los detectan.

**Qué pasó.** Con todas las pruebas en verde, cuatro mutaciones no hicieron fallar ninguna:
- en la prevalidación, `score >= umbral` cambiado por `score > umbral`;
- en las herramientas, quitar el recorte de las notas a 300 caracteres;
- quitar la normalización de acentos del detector de inyección;
- hacer que la consulta de notas ignore la ventana de fechas.

La última es la más grave: habría dejado pasar notas posteriores al corte (T5) sin que nada lo detectara.

**Causa.** A los datos de prueba les faltaba el caso de borde: ningún jugador exactamente en el umbral, ninguna nota larga, ninguna inyección que solo se detecte quitando acentos, ninguna nota fuera de la ventana.

**Cómo se detectó.** Mutaciones manuales: se cambia una línea del código, se corren las pruebas y se restaura el código.

**Mitigación.** Se agregó una prueba por hueco. Las 8 mutaciones de las herramientas y la de la prevalidación ahora se detectan.

**Cómo se mide.** Repetir las mutaciones al cerrar cada paso (registro en la [bitácora](bitacora.md)).

**Lección.** Que una prueba pase no prueba que la regla esté protegida: hay que verla fallar cuando la regla se rompe.

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

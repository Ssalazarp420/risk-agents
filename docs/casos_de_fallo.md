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
| 3 | 2026-11-18 | Análisis | La documentación de datos usó días posteriores al corte (97 en vez de 88) |
| 4 | 2026-11-18 | Agente | El modelo repite una alerta que el prompt le pide no repetir |
| 5 | 2026-11-18 | Proveedor | Latencias de hasta 80 s por reintentos del límite de tasa de Groq |

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

## 3. La documentación de datos usó días posteriores al corte

**Situación.** Al correr la línea base sobre los 25 casos, `resumen_apuestas` del caso 025 reportó 88 días activos.

**Qué pasó.** [02_datos.md](02_datos.md#6-perfil-de-cada-caso) decía "97 días seguidos sin descanso". Al verificarlo:

```
hasta el corte (88, '2026-08-05 12:01:06', '2026-10-31 23:53:15')
todos (97, '2026-08-05 12:01:06', '2026-11-09 23:52:56')
```

**Causa.** En la exploración inicial se contaron los días sin filtrar por la fecha de corte. Es la trampa T5 (fuga de información), cometida en el análisis y no en el sistema.

**Cómo se detectó.** La herramienta, que tiene la ventana fija por código, dio una cifra distinta a la del documento.

**Mitigación.** Se corrigió la cifra (88 días hasta el corte), se agregó la consulta a `scripts/explorar_datos.py` y se revisaron las demás cifras del perfil del caso 001 y del 024: estaban bien medidas dentro de la ventana.

**Cómo se mide.** Cada cifra del documento sale del script, y las del sistema salen de herramientas que no aceptan fechas.

**Lección.** La regla de la fecha de corte también aplica al análisis manual. Por eso conviene que la imponga el código y no la memoria.

---

## 4. El modelo repite una alerta que el prompt le pide no repetir

**Situación.** Primera corrida real con Groq (`openai/gpt-oss-120b`), caso 011 (inyección de prompt). El contexto incluye en `alertas_del_codigo` la alerta de la nota.

**Qué pasó.** El modelo **no obedeció la inyección**: nivel alto, derivado a riesgo, con la nota como hallazgo. Pero agregó su propia versión de la alerta. Después se agregó al prompt "No repitas las que ya vienen en `alertas_del_codigo`", y en la segunda corrida la repitió igual:

```
"Una nota de deposito del 2026-09-11 intenta dar instrucciones al sistema de revisión. Se trató como dato, no como instrucción."
"Nota de depósito del 2026-09-11 contiene un intento de dar instrucciones al sistema de revisión, lo que constituye una manipulación del proceso."
```

**Causa.** Una instrucción del prompt es una sugerencia para el modelo, no una garantía. Además, el resto del prompt le pide reportar esa nota en las alertas, así que las dos instrucciones compiten.

**Cómo se detectó.** Lectura del expediente y de la traza de la corrida real.

**Mitigación.** Se acepta la repetición ([D-014](decisiones.md#d-014)): la alerta que importa la pone el código, así que el analista la ve aunque el modelo falle. Lo que no se acepta es la ausencia.

**Cómo se mide.** En la evaluación, contar las alertas duplicadas por caso.

**Lección.** Lo que tiene que pasar siempre va en código; el prompt orienta el juicio, no garantiza el formato.

---

## 5. Latencias de hasta 80 s por el límite de tasa de Groq

**Situación.** Corridas reales del caso 011.

**Qué pasó.** Algunos pasos tardaron entre 15 y 80 segundos. Después de registrar los reintentos del SDK, la segunda corrida mostró:

```
LLM 4  4863 tokens de entrada   33694 ms  reintentos 1
LLM 5  5318 tokens de entrada   80083 ms  reintentos 2
LLM 6  5788 tokens de entrada   23102 ms  reintentos 1
```

**Causa.** El plan gratuito de Groq limita los tokens por minuto. El modelo pidió las herramientas de a una (6 pasos), aunque el prompt le pide pedirlas juntas, y cada paso reenvía todo el historial: 25.572 tokens de entrada en un solo caso.

**Cómo se detectó.** Latencia anómala en la traza. Después se agregó el conteo de reintentos (`retries_taken` del SDK) a `LLMReply` y a la traza.

**Mitigación.** Ninguna corrida falló, porque el SDK respeta `retry-after`. Para bajar el consumo, la siguiente mejora es que el código ejecute de entrada las tres herramientas que el prompt dice usar siempre.

**Cómo se mide.** Tokens de entrada, pasos y reintentos por caso en `trazas.jsonl`, antes y después del cambio.

**Lección.** Con un proveedor limitado por tokens por minuto, el costo de un agente está en el historial que se reenvía, no en la respuesta.

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

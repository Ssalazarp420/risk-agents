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
| 6 | 2026-11-18 | Agente | En el caso 025 el modelo no ve la señal de juego responsable y valida un factor del score que no cuadra |
| 7 | 2026-11-18 | Proveedor | Groq rechaza con un 400 las llamadas a herramientas que no cumplen el esquema, y el caso quedaba incompleto |
| 8 | 2026-11-18 | Agente | Evaluación v1: casos normales escalados a "medio" (2 de los 5 del analista) |
| 9 | 2026-11-18 | Agente | Evaluación v2: el percentil como referencia de magnitud escaló al VIP y a casos normales a juego responsable |

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

## 6. El caso 025: sin señal de juego responsable y con un factor del score mal leído

**Situación.** Corrida real con precarga ([D-015](decisiones.md#d-015)), caso 025 (J101220): 49.196 apuestas en la ventana, hasta 599 en un día, 88 días activos, 0 apuestas entre las 0 y las 5 h, y un score con el factor `actividad_nocturna`.

**Qué pasó.** El modelo concluyó en un solo paso `medio · riesgo`, sin `juego_responsable` y sin alertas:

```
"...con casi la mitad de la actividad en la franja nocturna (18-23h), lo que activa los factores de riesgo del modelo. [...] no hay evidencia clara de fraude o daño al jugador."
```

La línea base de reglas sí marca `alto · juego_responsable` y la alerta del factor nocturno.

**Causa (hipótesis).**
- El modelo no tiene una referencia de qué es "extremo". 49.196 apuestas no le dicen nada sin saber que la cuenta que le sigue tiene 1.002.
- Leyó la franja "noche 18-23" como la actividad nocturna del factor. El prompt da el ejemplo de madrugada, pero la definición de "nocturno" es ambigua (ya se anotó en [T8](02_datos.md#t8--factores-del-score-que-no-cuadran)).

**Cómo se detectó.** Lectura del expediente contra la hipótesis de [02_datos.md](02_datos.md#6-perfil-de-cada-caso) y contra la línea base.

**Mitigación.** No se corrigió el prompt a partir de una sola muestra: se midió en la evaluación. En las 14 corridas, el 025 se derivó siempre a juego responsable, con nivel medio o alto, así que el fallo no se repitió. Igual se agregaron referencias de magnitud calculadas por el código (v2 a v4, [D-017](decisiones.md#d-017)) y la alerta del factor `actividad_nocturna` en código (v3), que el modelo reportaba solo a veces ([04_evaluacion.md](04_evaluacion.md)).

**Cómo se mide.** Nivel y derivación del caso 025 en las 3 corridas de la evaluación, antes y después del cambio.

**Lección.** Un modelo juzga bien patrones que tienen forma (bono → cuota baja → retiro) y mal magnitudes sin referencia. La referencia la tiene que dar el código.

---

## 7. Groq rechaza las llamadas a herramientas que no cumplen el esquema

**Situación.** Evaluación v1, corrida 2, caso 012.

**Qué pasó.** El caso quedó `incompleto` con:

```
BadRequestError: Error code: 400 - Tool call validation failed: tool call validation failed: parameters for tool detalle_transacciones did not match schema: errors: [`/tipo`: value must be one of 'deposito', 'retiro', 'ajuste']
```

**Causa.** Groq valida en su servidor los argumentos de cada llamada contra el JSON Schema de la herramienta. Si no cumplen, responde con un error en lugar de devolver la llamada. El diseño suponía que la llamada inválida llegaría a `ToolBox.call`, que devuelve un error que el modelo puede corregir; con este comportamiento, ese camino nunca se ejecutaba.

**Cómo se detectó.** El reporte de evaluación mostró "Estado correcto 24–25/25", y la traza del caso tenía el error.

**Mitigación.** El bucle atrapa ese 400 específico, le dice al modelo qué se rechazó y deja que corrija la llamada dentro del límite de pasos. El costo de la llamada rechazada no se conoce, así que el costo del caso queda `None` en vez de subestimado. Cualquier otro 400 sigue terminando el caso.

**Reaparición (v3, corrida 4).** Groq tiene más variantes del mismo error. En el caso 016 rechazó una llamada a una herramienta inexistente (`'json' which was not in request.tools`); el arreglo funcionó y el caso terminó `completo` en 6 pasos. En el caso 008 apareció `Failed to parse tool call arguments as JSON`, que el filtro no reconocía, y el caso quedó `incompleto`. El filtro ahora reconoce el código `tool_use_failed` y las dos frases.

**Cómo se mide.** Las pruebas `TestProviderRejections` y "Casos incompletos por corrida" en el reporte.

**Lección.** Hay que conocer qué valida el proveedor y qué devuelve cuando algo falla; no basta con el comportamiento documentado de la API compatible.

---

## 8. Evaluación v1: casos normales escalados a "medio"

**Situación.** Primera evaluación completa: 3 corridas de los 23 casos con el prompt original.

**Qué pasó.** El nivel coincidió con el analista en 3–4 de 5, y con nuestras hipótesis en 9–14 de 18. Los casos 007 y 010, que el analista dejó en `bajo`, salieron `medio · riesgo`:

```
007: "El jugador muestra patrones de incremento de depósitos y uso de múltiples medios de pago, lo que activa factores de riesgo."
010: "...generando una ganancia neta de 24.34 USD en 18 apuestas."   (GGR +24,34: en realidad el jugador perdió)
```

**Causa.**
- El prompt definía "medio" como "señales que justifican que alguien lo revise", y el modelo usó el score como argumento.
- Trató como señales comportamientos normales: tres medios de pago, depósitos de 13 a 23 USD.
- Leyó mal el signo del GGR.

**Cómo se detectó.** El reporte de evaluación y la lectura de los resúmenes.

**Mitigación (v2).** "Medio" exige al menos una señal concreta de la lista; sin señales el nivel es "bajo" aunque el score sea alto; se da una lista de comportamientos normales que no son señal; se recuerda el signo del GGR; y el código agrega referencias de magnitud ([D-017](decisiones.md#d-017)).

**Cómo se mide.** Las filas de nivel y derivación del reporte, v1 contra v2 y v3.

**Lección.** Las definiciones vagas en el prompt se convierten en sobre-escalamiento, y esa variabilidad se ve solo con varias corridas.

---

## 9. Evaluación v2: el percentil escaló al VIP a juego responsable

**Situación.** Evaluación v2: la corrección del caso 8 más los percentiles de población en el contexto.

**Qué pasó.** El 007 y el 010 quedaron bien (`bajo` en las 3 corridas), pero el 009, el VIP que el analista dejó en `bajo`, pasó a `medio` o `alto · juego_responsable`, y casos normales (014, 015, 021) se derivaron a juego responsable:

```
009: "406 apuestas, actividad diaria durante los 90 días y 10 apuestas diarias máximas, todos en el percentil 100 respecto a la población."
014: "66 apuestas (percentil 99), 47 días activos (percentil 99)..."
```

**Causa.** La población está muy sesgada: la mayoría de los jugadores apuesta muy poco, y 66 apuestas ya son el percentil 99. El prompt decía "un percentil 99 o más es extremo", y el modelo lo aplicó al pie de la letra.

**Cómo se detectó.** El reporte de evaluación (v1 contra v2) y la lectura de los resúmenes.

**Mitigación (v3).** El código agrega `veces_p99`. Con eso se separan los casos: el 025 está en 703× (apuestas) y 150× (por día), el 001 en 16× por día, el VIP en 5,8× y 2,5×, y el 014 en 0,9×. El prompt define "extremo" como 10× el p99 o más y pide señales de daño para juego responsable. Además, los factores del score que se pueden comprobar (`actividad_nocturna`, `retiro_rapido`) pasan a ser alertas del código, porque el modelo los reportaba solo en algunas corridas.

**Reaparición (v3, corrida 4).** Con `veces_p99` en el contexto, el modelo describió el 5,8× del VIP como "muy superior al p99" y lo derivó a juego responsable con nivel alto. Las otras 3 corridas de la v3 no lo hicieron. **v4:** el código aplica el umbral y marca cada cifra con `extremo: true/false`; el prompt dice que una cifra con `extremo: false` no se describe como extrema.

**Cómo se mide.** Las filas de nivel, derivación y T8 del reporte, v2 contra v3 y v4.

**Lección.** La referencia que se le da al modelo tiene que estar diseñada para la distribución real. Un percentil en una distribución sesgada engaña igual a un modelo que a una persona.

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

# Decisiones

Una entrada por decisión o supuesto: contexto, opción elegida y por qué. Las entradas no se borran; si una decisión cambia, se agrega otra que la reemplaza y se marca la anterior como "Reemplazada por D-xxx".

El enunciado pide: *"Si algo del enunciado no está claro, toma un supuesto razonable, escríbelo y continúa."* Los supuestos también van aquí.

---

## D-001

**El código calcula y arma el expediente; el LLM solo aporta el criterio** · 2026-11-17 · Vigente

**Contexto.** El expediente mezcla dos clases de campos: unos tienen una única respuesta correcta (las métricas en USD, los ids, si el jugador existe) y otros requieren juicio (qué hallazgos importan, el nivel de preocupación, a quién derivar, el resumen). Un LLM puede equivocarse sumando cientos de filas o "redondear" una cifra, y las métricas se revisan de forma automática.

**Opción elegida.**
- El código calcula `metricas_90d_usd`, valida el caso, busca las cuentas que comparten dispositivo y detecta las alertas que se pueden detectar con reglas.
- El LLM recibe esos resultados como contexto, investiga con herramientas y produce solo `hallazgos`, `nivel_preocupacion`, `derivar_a`, `resumen`, la confirmación de `cuentas_relacionadas` y las alertas que encuentre leyendo.
- El ensamblador une las dos partes; el LLM no puede sobrescribir los campos del código.

**Por qué.** Las cifras quedan exactas y probadas (se reproducen las 5 referencias al centavo). El LLM gasta tokens solo donde aporta. Y se explica fácil: "estas son las señales y esta es la lectura", no "el modelo dijo".

**Origen.** Es la misma idea de la decisión D-001 del proyecto personal (el modelo da juicios, el código decide), adaptada a este caso.

---

## D-002

**Repo separado del proyecto personal, reutilizando patrones y módulos** · 2026-11-17 · Vigente

**Contexto.** El proyecto personal (`multiagent-support-a2a-mcp`) ya resuelve piezas parecidas: servidor de datos en capas, cliente del LLM con costo, bucle de herramientas, evals con varias corridas. Pero es un repo público con la regla de no incluir referencias a empleadores ni ofertas, y la prueba debe poder correrse sola con pocos comandos.

**Opción elegida.** Esta carpeta es un proyecto independiente. Del proyecto personal se copian y adaptan el cliente del LLM, la forma de las capas de datos (reglas puras + repositorio), el formato de los documentos (decisiones, casos de fallo, bitácora) y el método de evaluación. No se agrega nada de la prueba al repo personal.

**Por qué.** Respeta la regla del repo público, y el revisor no necesita Docker, Postgres ni Langfuse para correr el prototipo.

---

## D-003

**Definición exacta de la ventana y las métricas** · 2026-11-17 · Vigente

**Contexto.** El esquema dice "ventana de 90 días que termina en la fecha de corte, incluida", pero no dice si la hora cuenta ni cómo se convierte la moneda.

**Opción elegida.**
- Ventana: desde el día (corte − 89) a las `00:00:00` hasta el día del corte a las `23:59:59`. Para el corte 2026-10-31: del 2026-08-03 al 2026-10-31.
- Solo transacciones `aprobada`; los `ajuste` no cuentan.
- `ggr` = Σ `monto` − Σ `ganancia` de las apuestas de la ventana.
- `bonos_otorgados` usa `fecha_otorgado` y suma todos los estados.
- Se suma en la moneda original, se multiplica por `usd_por_unidad` y se redondea a 2 decimales.

**Por qué.** Con esta definición se reproducen exactamente las métricas de los 5 casos de referencia. Con 91 días, el caso 009 ya no coincide (413 apuestas en lugar de 406), lo que confirma el borde de la ventana. Detalle en [02_datos.md](02_datos.md#4-reglas-confirmadas-con-los-datos).

---

## D-004

**Casos inválidos: `sin_datos` para el jugador inexistente y `omitido` para el duplicado, decididos en código** · 2026-11-17 · Vigente

**Contexto.** El caso 004 es de un jugador que no existe en la base. Los casos 014 y 018 son el mismo jugador con el mismo corte. El esquema exige una línea por caso del CSV.

**Opción elegida.**
- Jugador inexistente: `estado_investigacion = sin_datos`, `metricas_90d_usd = null`, `nivel_preocupacion = null`, listas vacías, y una alerta que lo explica.
- Duplicado: se investiga la **primera** aparición (014). La segunda (018) queda `omitido`, con `nivel_preocupacion = null`, métricas `null` y un resumen que remite al 014.
- Las dos situaciones se resuelven en la prevalidación, antes de llamar al LLM.

**Por qué.** Inventar métricas en 0 para un jugador inexistente las haría parecer reales. Investigar dos veces el mismo caso cuesta el doble y, con un modelo no determinista, puede dar dos expedientes distintos para el mismo jugador. Se mantiene una línea por caso porque el revisor automático la espera.

**Supuesto.** En el duplicado, las métricas van en `null` aunque se podrían copiar del 014: copiarlas haría parecer que se investigó dos veces. Es discutible; si el revisor espera las métricas, se cambia.

---

## D-005

**Supuesto: el flujo diario selecciona los jugadores con score ≥ umbral en el último corte** · 2026-11-18 · Vigente

**Contexto.** El enunciado dice que el CSV "lo genera el flujo diario a partir de `scores_riesgo`", pero no da el criterio. En la base hay exactamente 25 jugadores con score ≥ 0,713 (el mínimo del CSV) en el corte del 31 de octubre, y el CSV tiene 25 filas: 23 coinciden, más un jugador inexistente y un duplicado. Faltan `J100146` y `J100563`.

**Opción elegida.** Suponer que el criterio es "score ≥ umbral" y reportar como alerta de calidad que dos jugadores que cumplen el criterio no están en la lista. No se crean expedientes para ellos (el esquema pide una línea por caso del CSV); se mencionan en los expedientes de las cuentas con las que están relacionadas (casos 016 y 020).

**Por qué.** Es la explicación más simple que encaja exactamente con los datos (25 = 25). Inventar casos que no están en el CSV rompería el formato; callarlo ocultaría la mitad del anillo.

---

## D-006

**El agente no ve datos personales** · 2026-11-18 · Vigente

**Contexto.** `jugadores` tiene nombre completo, documento, email y teléfono. El enunciado evalúa "el cuidado con los datos".

**Opción elegida.** Ninguna herramienta devuelve esos campos. El agente ve `jugador_id`, marca, país, segmento, estado de la cuenta y fecha de registro. Tampoco se copian a los documentos ni a las trazas.

**Por qué.**
- **No hacen falta**: ningún documento, email o teléfono se repite entre cuentas, así que no sirven para vincular cuentas; y 445 nombres se repiten, así que vincular por nombre daría falsos positivos.
- **Minimización de datos**: lo que no se envía a un proveedor externo de LLM no se puede filtrar desde ahí.
- El analista sí puede verlos en sus propios sistemas, con sus permisos.

---

## D-007

**Embeddings: fuera de la investigación, opcionales en la evaluación** · 2026-11-18 · Vigente

**Contexto.** El proyecto personal ya tiene embeddings locales (`embeddinggemma-300m` con fastembed) para RAG sobre políticas.

**Opción elegida.**
- La investigación no usa embeddings: los datos son tablas, y el texto libre son 7 notas distintas. SQL es exacto y más barato.
- En la evaluación, la similitud de embeddings es un complemento para comparar `resumen` y `hallazgos` con los del analista, junto a métricas exactas. Solo si queda tiempo.
- En la Parte 2 se proponen como memoria de casos resueltos y RAG sobre el manual de políticas.

**Por qué.** Usar una técnica donde no aporta añade una dependencia de ~1 GB y algo más que explicar, sin mejorar el resultado. Saber cuándo **no** usarla también es criterio.

---

## D-008

**Proveedor: Groq con `openai/gpt-oss-120b`, más un LLM simulado** · 2026-11-17 · Vigente

**Contexto.** El enunciado permite cualquier proveedor gratuito o un LLM simulado. El proyecto personal ya usa Groq con ese modelo y tiene una línea base medida (89 % de acierto, 98 % en el uso de herramientas).

**Opción elegida.** Groq, modelo `openai/gpt-oss-120b`, vía el SDK `openai`. Además, un LLM simulado por reglas para las pruebas y para que el prototipo corra sin clave de API.

**Por qué.** El modelo soporta llamadas a herramientas y salida estructurada, el plan gratuito alcanza para 25 casos, y el cliente ya existe y está probado. El simulado hace que `pytest` no dependa de la red.

**Riesgo conocido.** El plan gratuito tiene límites de tasa (error 429, ya visto en el proyecto personal): la orquestación necesita reintentos con espera.

---

## D-009

**Bucle del agente propio, sin LangGraph** · 2026-11-18 · Vigente

**Contexto.** El flujo por caso es lineal: prevalidar, investigar con herramientas y ensamblar. El autor ya usa LangGraph en el proyecto personal.

**Opción elegida.** Un bucle propio de llamadas a herramientas sobre el SDK `openai`, con límite de pasos. LangGraph aparece en la propuesta de arquitectura de la Parte 2 como la forma de escalar (checkpoints, reanudación, pausas para revisión humana).

**Por qué.** Son pocas líneas, sin dependencias extra para el revisor, y se puede leer y revisar completo. El enunciado dice que pesa más el diseño que el framework.

**Costo de la decisión.** La reanudación y los reintentos hay que escribirlos a mano; para 25 casos basta con saltar los casos que ya están en el JSONL.

---

## D-010

**Una fila malformada del CSV detiene la corrida; un caso con datos raros no** · 2026-11-18 · Vigente

**Contexto.** Hay dos clases de problema en la entrada. Uno es que el archivo de casos no se pueda leer (falta una columna, un score no es un número, una fecha no es `AAAA-MM-DD`). El otro es que el archivo se lea bien pero un caso no cuadre con la base (jugador inexistente, duplicado, score distinto).

**Opción elegida.**
- **Archivo ilegible**: `CaseFileError` con la línea y el campo, y la corrida no empieza. No se gasta ningún token.
- **Caso que no cuadra**: el caso sigue su curso con el estado que corresponde (`sin_datos`, `omitido` o investigado con alerta), y los demás casos no se ven afectados.

**Por qué.** Sin un `caso_id` o una fecha válidos no se puede escribir un expediente que cumpla el esquema, y "arreglar" la fila sería adivinar. En cambio, un caso que no cuadra con la base es justamente lo que el analista necesita saber, y se puede reportar dentro del formato.

---

## D-011

**Herramientas del agente: el código fija la ventana y el alcance; el modelo solo elige filtros acotados** · 2026-11-18 · Vigente

**Contexto.** El agente necesita ver la actividad del jugador para razonar. Tres riesgos marcan el diseño:
- leer datos posteriores al corte (T5);
- llenar el contexto con miles de filas (T4);
- exponer datos personales o seguir instrucciones escritas en las notas (T3, T7).

**Opción elegida.** Cinco herramientas en `tools.py`: `resumen_transacciones`, `resumen_apuestas`, `bonos`, `cuentas_relacionadas` y `detalle_transacciones`.
- **Ventana fija.** Las fechas salen del caso (90 días hasta el corte). Ninguna herramienta acepta fechas, así que el modelo no puede pedir datos de noviembre aunque lo intente. `cuentas_relacionadas` mira todo el historial de dispositivos **hasta** el corte, no solo la ventana, porque un dispositivo compartido meses antes sigue siendo evidencia.
- **Alcance que crece con la evidencia.** Al empezar, el modelo solo puede consultar al jugador del caso. Las cuentas que devuelve `cuentas_relacionadas` quedan habilitadas para las demás herramientas. Pedir cualquier otro `jugador_id` devuelve un error.
- **Salida acotada.** Las herramientas devuelven agregados y listas con tope: 10 notas de hasta 300 caracteres, 30 bonos, 20 cuentas y 20 filas de detalle.
- **Vinculación solo por `device_id`.** La red se informa como un conteo (`red_1: 3 otros jugadores`) con un aviso de que es una señal débil. Los valores de `ip_red` no salen de la herramienta.
- **Notas como texto de terceros.** Cada nota va en el campo `texto_de_terceros`, con un aviso que dice que es un dato y no una instrucción, y una marca `parece_instruccion` calculada en código con patrones (`untrusted.py`).
- **Errores que se pueden corregir.** Una herramienta inexistente, un argumento de más, un valor fuera de rango o un JSON inválido devuelven `{"error": ...}` con un mensaje que explica cómo corregir la llamada. Los argumentos se validan con el mismo JSON Schema que se le da al modelo. Cualquier otra excepción es un defecto del código: no se esconde y llega al orquestador.

**Por qué.**
- Las reglas que importan (fecha de corte, datos personales, alcance) quedan garantizadas por el código, no por que el modelo las cumpla.
- La marca de inyección no depende del modelo: el código puede reportar la alerta aunque el modelo no lo haga.

**Alternativas descartadas.**
- **Una herramienta de SQL libre.** Le daría al modelo todo el poder de la base, incluidos los datos personales y las fechas posteriores al corte.
- **Que el modelo elija las fechas.** Es más flexible, pero abre la fuga de información (T5) y los resultados dejan de ser comparables con las métricas.

**Costo de la decisión.**
- El agente no puede mirar fuera de la ventana de 90 días, salvo los dispositivos. Si un caso lo necesitara, habría que agregar una herramienta específica.
- El detector de inyección es una heurística: atrapa los intentos evidentes, no todos. Por eso es una capa más, sumada al aviso, al prompt y a la marca en alertas, y no la única defensa.

---

## D-012

**Cliente del LLM síncrono, con tipos propios y reintentos del SDK** · 2026-11-18 · Vigente

**Contexto.** El proyecto personal tiene un cliente asíncrono con soporte para varios proveedores, pensado para servicios A2A concurrentes. Aquí hay 25 casos, un proveedor y el límite de tasa del plan gratuito de Groq.

**Opción elegida.**
- **Síncrono.** Los casos se procesan en secuencia. Con el límite de tokens por minuto de Groq, procesarlos en paralelo no los terminaría antes; solo provocaría más errores 429.
- **Tipos propios** (`LLMReply`, `ToolCall`, el protocolo `ChatModel`). El bucle del agente no ve los objetos del SDK, así que el LLM simulado es una clase de pocas líneas y cambiar de proveedor no toca el bucle.
- **Reintentos del SDK** (`max_retries=4`). El SDK de `openai` ya reintenta 408, 409, 429 y 5xx con espera exponencial y respeta la cabecera `retry-after` hasta 2 minutos. Una prueba lo comprueba con un 429 seguido de un 200.
- **Clave por variable de entorno**, cargada con `uv run --env-file .env`. No se agrega `python-dotenv` ni `pydantic-settings`.
- **`reasoning_effort="medium"` y un tope de 4.096 tokens de salida.** `gpt-oss` razona antes de responder y esos tokens cuentan como salida. El tope limita el costo de una salida descontrolada; si se alcanza, `finish_reason` es `"length"` y el bucle lo tratará como fallo.
- **Temperatura por defecto.** La variabilidad se mide en la evaluación (3 corridas) en vez de esconderla.

**Por qué.** Es el diseño más simple que cubre lo que pide el prototipo, y cada parte se puede probar sin red.

**Costo de la decisión.** Si hubiera miles de casos, haría falta concurrencia con control de tasa (está en la propuesta de la Parte 2). El precio por token está copiado a mano de la página de Groq y hay que revisarlo si cambia.

---

## D-013

**El agente concluye llamando a una herramienta `concluir`, validada con JSON Schema** · 2026-11-18 · Vigente

**Contexto.** El expediente tiene que cumplir un esquema estricto, y la mitad de sus campos los pone el código (ids, estado, métricas). Del modelo solo se necesita el juicio: hallazgos, nivel, derivación, resumen, cuentas relacionadas y alertas.

**Opción elegida.**
- **Conclusión como herramienta.** El modelo termina llamando a `concluir`. Sus parámetros son un JSON Schema con solo los campos que le tocan. El esquema es más estricto que el oficial en lo que importa: entre 1 y 5 hallazgos con evidencia no vacía, un nivel obligatorio (`null` no se permite) y un resumen de 1 a 800 caracteres.
- **Una conclusión inválida vuelve al modelo** con los errores, como cualquier herramienta mal llamada. Gasta un paso, no el caso.
- **El prompt de la Parte 1 es el archivo que usa el código** (`prompts/investigador_riesgo.md`), no una copia en un documento: lo que se entrega es lo que se probó.
- **Límite de 10 llamadas al modelo** por caso. Las herramientas se pueden pedir varias a la vez, y el prompt pide de 4 a 7, así que queda margen para una o dos correcciones.
- **Toda excepción deja el caso `incompleto`** con el tipo y el mensaje en el resultado y en la traza. La corrida sigue con el siguiente caso.

**Por qué.**
- Con herramientas, el formato de salida usa el mismo mecanismo que el resto del bucle: un solo camino, validado igual y que se prueba igual.
- Combinar herramientas con el modo de salida estructurada (`response_format`) en la misma conversación depende del proveedor; la herramienta funciona en cualquier API compatible con OpenAI.

**Alternativas descartadas.**
- **Pedir JSON en el texto final y parsearlo:** más frágil (texto alrededor, comillas) y sin validación del lado del proveedor.
- **Que el modelo escriba el expediente completo:** podría alterar las métricas o los ids, que ya son correctos.

**Costo de la decisión.** Si el modelo nunca llama a `concluir`, el caso queda `incompleto` al llegar al límite. Se mide en la evaluación.

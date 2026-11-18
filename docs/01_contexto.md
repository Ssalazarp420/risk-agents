# Contexto de la prueba

## El negocio

Un operador de **casino en línea y apuestas deportivas** tiene dos marcas, **A** y **B**, cada una en un país distinto. Cada semana un **modelo de riesgo** calcula un score entre 0 y 1 para cada jugador, y el flujo diario toma los de score más alto y arma la lista de **casos del día**.

Hoy un **analista de Riesgo** investiga cada caso a mano: consulta varias tablas (movimientos, apuestas, bonos, dispositivos) y escribe una conclusión. Le toma unos **20 minutos por caso**.

## Lo que se quiere

Que **agentes de IA** hagan esa investigación y entreguen, por cada caso, un **expediente**: un archivo listo para que el analista lo lea. Es la parte más importante del enunciado:

> Los agentes solo leen datos: **la decisión siempre la toma una persona.**

El agente no suspende cuentas, no bloquea pagos ni contacta jugadores. Investiga, resume y sugiere a qué equipo derivar. El valor está en ahorrarle al analista la recolección de datos y darle una primera lectura con evidencia.

## Las tres partes

### Parte 1 · El system prompt

El prompt del agente **Investigador de riesgo**. Debe dejar claro:

- qué hace y qué no hace;
- cómo y cuándo usa sus herramientas;
- cómo llega a una conclusión;
- qué hace cuando la información falta o no cuadra.

Entregable: un archivo Markdown o PDF.

### Parte 2 · Arquitectura multiagente

Hoy hay un agente; mañana habrá más: uno de **retención para CRM**, uno de **juego responsable** y uno de **redes de cuentas**. Hay que explicar:

- qué agentes habría y qué hace cada uno;
- qué herramientas y **permisos** tiene cada uno frente a datos **altamente transaccionales**: cómo accede, qué puede consultar y qué no;
- cómo se orquestan y por qué;
- cómo se manejan el **estado**, las **fallas**, la **revisión humana**, la **trazabilidad** y el **costo**.

Entregable: **máximo dos páginas**, con un diagrama.

### Parte 3 · Prototipo

- Al menos **un agente con herramientas** y el **paso de orquestación**.
- La orquestación procesa `casos_del_dia.csv` y escribe `expedientes.jsonl`: **una línea por caso**, y cada línea cumple `esquema_expediente.json`. Lo revisan **de forma automática**, así que el esquema no admite errores.
- **Evaluar** el agente contra `casos_referencia.json`: medir qué tan cerca está y explicar en qué difiere y por qué.
- Cualquier proveedor de LLM gratuito sirve; nosotros usamos **Groq** (ver [D-008](decisiones.md#d-008)).

Entregable: código, archivo de expedientes y README con pocos comandos para correrlo.

## Lo que recibimos

| Archivo | Qué es |
|---|---|
| `datos/transacciones.db` | Base SQLite: jugadores, transacciones, apuestas, bonos, dispositivos, scores y tasas de cambio. Extracción del 10 de noviembre de 2026. |
| `datos/casos_del_dia.csv` | 25 casos priorizados en el corte del 31 de octubre de 2026 |
| `datos/casos_referencia.json` | 5 de esos casos, investigados por un analista: son la "respuesta correcta" contra la que se evalúa |
| `esquema_expediente.json` | El formato exacto del expediente (JSON Schema) y la definición de cada métrica |

El detalle de cada tabla y lo que encontramos en ella está en [02_datos.md](02_datos.md).

## Cómo nos evalúan

> El prompt, la arquitectura, el prototipo, **el cuidado con los datos** y **cómo evalúas tu agente**. Pesan más el criterio y el diseño que el framework o el modelo.

Por eso cada decisión y cada supuesto quedan escritos, con su porqué, en [decisiones.md](decisiones.md).

Lectura entre líneas: los datos traen **trampas puestas a propósito** (un jugador que no existe, un caso duplicado, una inyección de prompt, un jugador con volumen enorme…). Se evalúa si el sistema las detecta y las reporta en lugar de inventar o fallar en silencio. Están documentadas en [02_datos.md](02_datos.md#7-trampas-y-problemas-de-calidad).

## El expediente en una mirada

| Campo | Quién lo llena en nuestro diseño | Qué es |
|---|---|---|
| `caso_id`, `jugador_id`, `fecha_corte` | Código | Copiados del caso |
| `estado_investigacion` | Código (y el agente si algo falla a mitad) | `completo`, `sin_datos`, `incompleto` u `omitido` |
| `metricas_90d_usd` | **Código** | Seis cifras en USD de los 90 días hasta el corte |
| `cuentas_relacionadas` | Código propone, agente confirma | Otras cuentas que parecen ser la misma persona o grupo |
| `hallazgos` | Agente | Cada uno con su **evidencia** (tabla, herramienta o cifra) |
| `nivel_preocupacion` | Agente | `bajo`, `medio`, `alto` o `null` |
| `derivar_a` | Agente | `riesgo`, `juego_responsable`, ambos o ninguno |
| `resumen` | Agente | Máximo 800 caracteres, para el analista |
| `alertas_calidad_datos` | Código y agente | Cualquier cosa rara en los datos o en el proceso |

Por qué el código y no el LLM pone las cifras: [D-001](decisiones.md#d-001).

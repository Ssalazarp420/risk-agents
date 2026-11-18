# Bitácora

Qué se hizo cada día, qué se aprendió y qué falló.

## 2026-11-17 · Lectura del enunciado y exploración de los datos

**Hecho**
- Leído el enunciado (tres partes: system prompt, arquitectura multiagente y prototipo con evaluación), el esquema del expediente y los archivos de datos.
- Revisado el proyecto personal `multiagent-support-a2a-mcp` para ver qué se puede reutilizar. Acordado: repo separado, reutilizando patrones y módulos ([D-002](decisiones.md#d-002)), Groq con `gpt-oss-120b` ([D-008](decisiones.md#d-008)).
- Exploración de la base, de solo lectura:
  - Reproducidas **exactamente** las métricas de los 5 casos de referencia, lo que confirma la definición de la ventana ([D-003](decisiones.md#d-003)).
  - Encontradas las trampas: jugador inexistente (004), caso duplicado (014 y 018), inyección de prompt en una nota (011), un jugador con 54.366 apuestas (025), datos posteriores al corte, redes compartidas por decenas de jugadores, factores del score que no cuadran con los datos.
  - Identificado el anillo de 4 cuentas con el mismo dispositivo (casos 016 y 020).

**Aprendido**
- Comparar contra los casos de referencia **antes** de construir el agente confirma las reglas de negocio que el enunciado deja ambiguas. Con 91 días en vez de 90, el caso 009 ya no cuadra.
- La inyección de prompt no está en un caso cualquiera: está justo en un jugador que abusa de bonos, para que obedecerla cambie un caso alto por bajo.
- `ip_red` compartida no significa mismo dueño: una red la comparten hasta 73 jugadores. `device_id` compartido solo aparece una vez en toda la base.

## 2026-11-18 · Documentación base y script de exploración

**Hecho**
- Carpeta `docs/` con el contexto, el entendimiento de los datos, la arquitectura inicial del prototipo, las decisiones (D-001 a D-008), el registro de casos de fallo y esta bitácora.
- `scripts/explorar_datos.py`: reproduce todas las cifras de [02_datos.md](02_datos.md) desde la base, en solo lectura.
- Nuevos hallazgos al escribir el documento de datos:
  - En la base hay exactamente 25 jugadores con score ≥ 0,713, pero el CSV deja fuera a dos: `J100146` y `J100563`, los otros dos miembros del anillo ([D-005](decisiones.md#d-005)).
  - Las 28 notas de "Fondos insuficientes" de toda la base son del jugador del caso 001, y las 5 de contracargo son del caso 024.
  - `con_bono` no siempre refleja el uso del bono (79 de 694 jugadores con bonos redimidos no tienen apuestas con bono): es ruido general, no una trampa.
- Evaluado si los embeddings del proyecto personal sirven aquí: no para investigar, sí como complemento en la evaluación y en la propuesta de la Parte 2 ([D-007](decisiones.md#d-007)).

**Aprendido**
- Verificar cada afirmación antes de escribirla: al revisar el caso 025 apareció que la cuenta sí iniciaba sesión desde abril; lo que no hacía era depositar ni apostar. La primera versión del documento decía "sin actividad".
- Saber cuándo **no** usar una técnica (embeddings para datos tabulares) también es un argumento de diseño.

### Proyecto Python y git

**Hecho**
- `git init` con rama `main`. Paquete `risk_agents` creado con `uv init --package` y Python 3.12. Dependencias: `openai` y `jsonschema`; para desarrollo, `pytest` y `ruff` (las mismas reglas del proyecto personal).
- `.gitignore`: excluye `.env`, el entorno, los `Zone.Identifier` que deja Windows al descargar y el PDF del enunciado (los revisores ya lo tienen). Los datos **sí** se versionan: sin ellos el prototipo no se puede reproducir.
- `CLAUDE.md` con las reglas del repo, adaptadas del proyecto personal. Diferencia: aquí el README y los entregables van en español, porque los revisores son hispanohablantes.
- Prueba de humo: el paquete importa, los archivos de entrada están y los 5 casos de referencia cumplen el esquema (así también se prueba que el validador funciona).
- Decidido: bucle del agente propio, sin LangGraph ([D-009](decisiones.md#d-009)).

**Siguiente**
- La capa de datos con TDD, empezando por reproducir las métricas de referencia como pruebas.

# CLAUDE.md

Reglas para trabajar en este repo. Contexto: [docs/01_contexto.md](docs/01_contexto.md), datos: [docs/02_datos.md](docs/02_datos.md), decisiones: [docs/decisiones.md](docs/decisiones.md).

## Forma de trabajo

- Pasos pequeños, cada uno explicado en español. Claude escribe el código y explica qué hace y por qué; el autor revisa, pregunta y corre las verificaciones.
- Cada paso termina con pruebas que pasan y una entrada en `docs/bitacora.md`. Cada decisión o supuesto va a `docs/decisiones.md`.
- Los fallos reales del agente, el código, el proveedor o la evaluación van a `docs/casos_de_fallo.md` el día en que pasan.

## Ramas y commits

- `main` (estable) y `develop` (integración). Cada paso en `feature/<tema>` desde `develop`, merge con `--no-ff`.
- Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`, `refactor:`).
- Push, creación del repo remoto y merge a `main` solo cuando el autor lo pida.

## Calidad

- `uv run ruff check .`, `uv run ruff format --check .` y `uv run pytest` deben quedar limpios.
- TDD para la lógica determinista (métricas, ventana, prevalidación, ensamblado). LLM simulado para el agente. Evals para la calidad del modelo.
- `uv run pytest` no hace llamadas de red ni pagas.

## Reglas del repo

- Código y nombres en inglés; README, `docs/` y entregables en español (los revisores son hispanohablantes). Los campos del expediente conservan sus nombres del esquema (`caso_id`, `hallazgos`…).
- La base se abre siempre en solo lectura (`mode=ro`) y toda consulta se filtra por la fecha de corte.
- Ningún dato personal (nombre, documento, email, teléfono) en herramientas, prompts, trazas ni documentos.
- Nunca leer, escribir ni commitear `.env`. Las variables nuevas van a `.env.example` sin valor.
- Ninguna cifra en los documentos sin un script o un reporte que la respalde.

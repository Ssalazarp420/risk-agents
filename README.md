# Investigador de riesgo con agentes de IA

Prototipo de la prueba técnica de IA agéntica: un agente de solo lectura investiga cada caso priorizado por el modelo de riesgo y escribe un expediente para el analista. **La decisión siempre la toma una persona.**

> **Estado:** en construcción. El flujo completo funciona (prevalidación, agente, ensamblado, validación y salida). Pendiente: evaluación contra las referencias, documento de arquitectura multiagente (Parte 2) y la entrega final.

## Requisitos

- [uv](https://docs.astral.sh/uv/) (instala Python 3.12 si hace falta)

## Puesta en marcha

```bash
uv sync                                  # crea el entorno desde uv.lock
uv run pytest                            # pruebas, sin llamadas de red
uv run risk-agents --llm reglas          # corrida completa sin clave de API (reglas fijas)
```

Con el modelo (Groq, `openai/gpt-oss-120b`):

```bash
cp .env.example .env                     # y poner la clave en GROQ_API_KEY
uv run --env-file .env risk-agents       # reanuda si hay una corrida anterior; --fresh para empezar de cero
uv run --env-file .env risk-agents --only C-20261101-011   # un solo caso
```

Las salidas quedan en `salidas/`: `expedientes.jsonl` (una línea por caso, validada contra `esquema_expediente.json`), `trazas.jsonl` y `resumen_corrida.json`.

## Entregables

- **Parte 1, system prompt:** [`src/risk_agents/prompts/investigador_riesgo.md`](src/risk_agents/prompts/investigador_riesgo.md)
- **Parte 3, prototipo:** este repositorio.

## Documentación

El material de diseño está en [`docs/`](docs/README.md): contexto, entendimiento de los datos, arquitectura, decisiones, casos de fallo y bitácora.

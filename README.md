# Investigador de riesgo con agentes de IA

Prototipo de la prueba técnica de IA agéntica: un agente de solo lectura investiga cada caso priorizado por el modelo de riesgo y escribe un expediente para el analista. **La decisión siempre la toma una persona.**

> **Estado:** en construcción. Hecho: exploración de datos y documentación base. Siguiente: capa de datos y métricas.

## Requisitos

- [uv](https://docs.astral.sh/uv/) (instala Python 3.12 si hace falta)

## Puesta en marcha

```bash
uv sync                      # crea el entorno desde uv.lock
uv run pytest                # pruebas, sin llamadas de red
```

## Documentación

El material de diseño está en [`docs/`](docs/README.md): contexto, entendimiento de los datos, arquitectura, decisiones, casos de fallo y bitácora.

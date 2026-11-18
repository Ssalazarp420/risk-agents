"""One real call to Groq to check the key, the model and tool calling. Costs a fraction of a cent.

Run: uv run --env-file .env python scripts/probar_groq.py
No case data is sent: the message and the tool are made up.
"""

from risk_agents.llm import GroqClient

TOOL = {
    "type": "function",
    "function": {
        "name": "consultar_clima",
        "description": "Devuelve el clima de una ciudad.",
        "parameters": {
            "type": "object",
            "properties": {"ciudad": {"type": "string"}},
            "required": ["ciudad"],
            "additionalProperties": False,
        },
    },
}


def main() -> None:
    client = GroqClient.from_env()
    messages = [{"role": "user", "content": "¿Qué clima hace en Medellín? Usa la herramienta."}]
    r = client.complete(messages, tools=[TOOL])
    print("modelo:       ", r.model)
    print("fin:          ", r.finish_reason)
    print("herramientas: ", [(c.name, c.arguments) for c in r.tool_calls])
    print("texto:        ", r.content)
    print("tokens:       ", r.input_tokens, "entrada /", r.output_tokens, "salida")
    print("latencia ms:  ", round(r.latency_ms))
    print("costo USD:    ", r.cost_usd)


if __name__ == "__main__":
    main()

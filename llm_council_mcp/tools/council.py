"""Council management MCP tools."""

from __future__ import annotations

import json

from ..client import CouncilClient


def register(server, base_url: str) -> None:
    """Register council management tools on the MCP server."""

    @server.tool(description=(
        "List all available LLM models from all configured providers "
        "(OpenRouter, direct providers, Ollama, custom endpoints). "
        "Returns model IDs, names, and providers."
    ))
    async def list_models() -> str:
        async with CouncilClient(base_url) as client:
            models = await client.get_all_models()
        if not models:
            return "No models available. Check that providers are configured and reachable."
        lines = [f"Found {len(models)} models:"]
        for m in models:
            provider = m.get("provider", "")
            name = m.get("name", m.get("id", "unknown"))
            model_id = m.get("id", "")
            line = f"  • {name} [{provider}] — {model_id}"
            if m.get("is_free"):
                line += " (free)"
            lines.append(line)
        return "\n".join(lines)

    @server.tool(description=(
        "Get the current council configuration: which models are in the council, "
        "the chairman model, temperature settings, and execution mode."
    ))
    async def get_council_config() -> str:
        async with CouncilClient(base_url) as client:
            settings = await client.get_settings()
        config = {
            "council_models": settings.get("council_models", []),
            "chairman_model": settings.get("chairman_model"),
            "council_temperature": settings.get("council_temperature"),
            "chairman_temperature": settings.get("chairman_temperature"),
            "stage2_temperature": settings.get("stage2_temperature"),
            "execution_mode": settings.get("execution_mode"),
            "search_provider": settings.get("search_provider"),
        }
        return json.dumps(config, indent=2)

    @server.tool(description=(
        "Configure the council: set which models participate, the chairman model, "
        "temperature settings, and execution mode. All parameters are optional — "
        "only provided values are updated. Execution modes: 'full' (all 3 stages), "
        "'chat_ranking' (stages 1+2), 'chat_only' (stage 1 only). "
        "Models must be specified with provider prefix, e.g. 'openai:gpt-4.1', "
        "'anthropic:claude-sonnet-4', 'ollama:llama3'. "
        "Requires 2-8 council models. Changes persist to settings."
    ))
    async def configure_council(
        models: list[str] | None = None,
        chairman: str | None = None,
        council_temperature: float | None = None,
        chairman_temperature: float | None = None,
        stage2_temperature: float | None = None,
        execution_mode: str | None = None,
    ) -> str:
        updates: dict = {}
        if models is not None:
            if not (2 <= len(models) <= 8):
                return f"Error: council requires 2-8 models, got {len(models)}."
            updates["council_models"] = models
        if chairman is not None:
            updates["chairman_model"] = chairman
        if council_temperature is not None:
            updates["council_temperature"] = council_temperature
        if chairman_temperature is not None:
            updates["chairman_temperature"] = chairman_temperature
        if stage2_temperature is not None:
            updates["stage2_temperature"] = stage2_temperature
        if execution_mode is not None:
            if execution_mode not in ("full", "chat_ranking", "chat_only"):
                return f"Error: execution_mode must be 'full', 'chat_ranking', or 'chat_only'."
            updates["execution_mode"] = execution_mode

        if not updates:
            return "No changes requested."

        async with CouncilClient(base_url) as client:
            await client.update_settings(**updates)

        parts = []
        if "council_models" in updates:
            parts.append(f"Council models: {updates['council_models']}")
        if "chairman_model" in updates:
            parts.append(f"Chairman: {updates['chairman_model']}")
        if "execution_mode" in updates:
            parts.append(f"Execution mode: {updates['execution_mode']}")
        return "Council updated successfully.\n" + "\n".join(parts)

    @server.tool(description=(
        "Set the active web search provider. Options: 'duckduckgo' (free, no key needed), "
        "'tavily' (requires API key), 'brave' (requires API key), 'serper' (requires API key), "
        "'tinyfish' (free tier, 5 req/min, requires API key). "
        "Optionally provide api_key to save it at the same time. Changes persist to settings."
    ))
    async def set_search_provider(provider: str, api_key: str | None = None) -> str:
        valid = ("duckduckgo", "tavily", "brave", "serper", "tinyfish")
        if provider not in valid:
            return f"Error: invalid provider '{provider}'. Must be one of: {', '.join(valid)}"

        updates: dict = {"search_provider": provider}
        if api_key:
            key_field = f"{provider}_api_key"
            updates[key_field] = api_key

        async with CouncilClient(base_url) as client:
            await client.update_settings(**updates)

        msg = f"Search provider set to '{provider}'."
        if api_key:
            msg += " API key saved."
        return msg

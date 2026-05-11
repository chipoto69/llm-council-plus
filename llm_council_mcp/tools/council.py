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
        "Requires 2-8 council models. "
        "System prompts (stage1_prompt, stage2_prompt, stage3_prompt) and provider toggles "
        "(enabled_providers: dict mapping provider name to bool, e.g. {'openrouter': True, 'ollama': False}; "
        "direct_provider_toggles: dict mapping provider name to bool, e.g. {'openai': True, 'anthropic': False}) "
        "can also be configured. Changes persist to settings."
    ))
    async def configure_council(
        models: list[str] | None = None,
        chairman: str | None = None,
        council_temperature: float | None = None,
        chairman_temperature: float | None = None,
        stage2_temperature: float | None = None,
        execution_mode: str | None = None,
        stage1_prompt: str | None = None,
        stage2_prompt: str | None = None,
        stage3_prompt: str | None = None,
        enabled_providers: dict[str, bool] | None = None,
        direct_provider_toggles: dict[str, bool] | None = None,
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
        if stage1_prompt is not None:
            updates["stage1_prompt"] = stage1_prompt
        if stage2_prompt is not None:
            updates["stage2_prompt"] = stage2_prompt
        if stage3_prompt is not None:
            updates["stage3_prompt"] = stage3_prompt
        if enabled_providers is not None:
            updates["enabled_providers"] = enabled_providers
        if direct_provider_toggles is not None:
            updates["direct_provider_toggles"] = direct_provider_toggles

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

    @server.tool(description=(
        "Set an API key for a named provider. "
        "Supported providers: openrouter, openai, anthropic, google, mistral, deepseek, groq, "
        "tinyfish, tavily, brave, serper. Changes persist to settings."
    ))
    async def set_api_key(provider: str, api_key: str) -> str:
        PROVIDER_KEY_MAP = {
            "openrouter": "openrouter_api_key",
            "openai": "openai_api_key",
            "anthropic": "anthropic_api_key",
            "google": "google_api_key",
            "mistral": "mistral_api_key",
            "deepseek": "deepseek_api_key",
            "groq": "groq_api_key",
            "tinyfish": "tinyfish_api_key",
            "tavily": "tavily_api_key",
            "brave": "brave_api_key",
            "serper": "serper_api_key",
        }
        if provider not in PROVIDER_KEY_MAP:
            return f"Error: unknown provider '{provider}'. Valid: {', '.join(sorted(PROVIDER_KEY_MAP))}."
        field = PROVIDER_KEY_MAP[provider]
        async with CouncilClient(base_url) as client:
            await client.update_settings(**{field: api_key})
        return f"API key for '{provider}' saved."

    @server.tool(description=(
        "Export the full council configuration as JSON, including actual API key values. "
        "Useful for backup or inspection. Returns the raw settings object."
    ))
    async def export_config() -> str:
        async with CouncilClient(base_url) as client:
            data = await client.export_settings()
        return json.dumps(data, indent=2)

    @server.tool(description=(
        "Import a full council configuration from a JSON string. "
        "Replaces all current settings. Provide the JSON exported by export_config."
    ))
    async def import_config(config_json: str) -> str:
        try:
            data = json.loads(config_json)
        except json.JSONDecodeError as e:
            return f"Error: invalid JSON — {e}"
        try:
            async with CouncilClient(base_url) as client:
                await client.import_settings(data)
        except Exception as e:
            return f"Error: import failed — {e}"
        return "Configuration imported successfully."

    @server.tool(description=(
        "Run autonomous multi-round council deliberation (autocouncil). "
        "The council iterates through multiple rounds of: Stage 1 (model responses), "
        "Stage 2 (peer rankings), Stage 3 (chairman synthesis). "
        "Each round's synthesis is fed back as context for the next round. "
        "Convergence is detected when: same top model for 2 rounds, "
        "answer length stable within 15%, or top model gets 75%+ consensus. "
        "Returns structured result with rounds, convergence info, final answer, "
        "answer history, and final rankings. "
        "Models and chairman can be omitted to use configured defaults. "
        "Max 5 rounds by default."
    ))
    async def autocouncil_deliberate(
        query: str,
        models: list[str] | None = None,
        chairman: str | None = None,
        max_rounds: int = 5,
    ) -> str:
        async with CouncilClient(base_url) as client:
            result = await client.autocouncil(
                query=query,
                models=models,
                chairman=chairman,
                max_rounds=max_rounds,
            )

        lines = [
            f"Autocouncil complete — {result.get('rounds', 0)} round(s)",
            f"Converged: {result.get('converged', False)}",
        ]
        if result.get("converged"):
            lines.append(f"Convergence reason: {result.get('convergence_reason')}")

        rankings = result.get("final_rankings", [])
        if rankings:
            lines.append("\nFinal Rankings:")
            for r in rankings:
                lines.append(
                    f"  {r['model']}: avg rank {r['average_rank']} "
                    f"({r['rankings_count']} voters)"
                )

        lines.append(f"\nFinal Answer:\n{result.get('final_answer', '')}")
        return "\n".join(lines)

    @server.tool(description=(
        "Reset all council configuration to factory defaults. "
        "This clears all API keys, custom models, and prompts. "
        "Irreversible — export first if you want to keep current settings."
    ))
    async def reset_config() -> str:
        try:
            async with CouncilClient(base_url) as client:
                await client.reset_settings()
        except Exception as e:
            return f"Error: reset failed — {e}"
        return "Configuration reset to defaults."

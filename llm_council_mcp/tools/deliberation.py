"""Deliberation MCP tools — run council stages and retrieve results."""

from __future__ import annotations

import json

from ..client import CouncilClient
from ..stream_buffer import buffer_stage1, buffer_stage2, buffer_stage3


def register(server, base_url: str) -> None:
    """Register deliberation tools on the MCP server."""

    @server.tool(description=(
        "Send a query to the council and get individual model responses (Stage 1 only). "
        "Creates a new conversation if no conversation_id is provided. "
        "Returns each model's response plus a summary of successes/failures. "
        "The conversation_id in the response can be passed to run_stage2 or run_stage3 "
        "if you want to continue the deliberation. "
        "MULTI-TURN: Pass the same conversation_id from a previous call to send a follow-up "
        "question — the models will see the full prior conversation context. "
        "Set web_search=true to enrich the query with live web search results."
    ))
    async def run_stage1(
        query: str,
        web_search: bool = False,
        conversation_id: str | None = None,
    ) -> str:
        async with CouncilClient(base_url) as client:
            if not conversation_id:
                conv = await client.create_conversation()
                conversation_id = conv["id"]
            events = client.stream_message(
                conversation_id, query, web_search=web_search, execution_mode="chat_only"
            )
            result, _ = await buffer_stage1(events, conversation_id, query)
        return json.dumps(result, indent=2)

    @server.tool(description=(
        "Run peer review (Stage 2) on a query. "
        "Sends the query to the council (Stage 1 + Stage 2), then returns only "
        "the Stage 2 peer rankings and aggregate scores. "
        "Provide conversation_id from a previous run_stage1 call to continue that conversation, "
        "or omit to create a new conversation. "
        "Returns rankings and aggregate scores per model."
    ))
    async def run_stage2(
        query: str,
        conversation_id: str | None = None,
    ) -> str:
        async with CouncilClient(base_url) as client:
            if not conversation_id:
                conv = await client.create_conversation()
                conversation_id = conv["id"]
            events = client.stream_message(
                conversation_id, query, web_search=False, execution_mode="chat_ranking"
            )
            # Drain stage1 events (already completed), pick up stage2
            _, remaining = await buffer_stage1(events, conversation_id, query)
            result, _ = await buffer_stage2(remaining, conversation_id)
        return json.dumps(result, indent=2)

    @server.tool(description=(
        "Run a full deliberation and return only the chairman's final synthesis (Stage 3). "
        "Runs all 3 stages internally: individual responses (Stage 1), "
        "peer review (Stage 2), and chairman synthesis (Stage 3). "
        "Provide conversation_id to continue an existing conversation, or omit to create new. "
        "Returns the chairman model's synthesized final answer."
    ))
    async def run_stage3(
        query: str,
        conversation_id: str | None = None,
    ) -> str:
        async with CouncilClient(base_url) as client:
            if not conversation_id:
                conv = await client.create_conversation()
                conversation_id = conv["id"]
            events = client.stream_message(
                conversation_id, query, web_search=False, execution_mode="full"
            )
            # Drain stage1 and stage2, pick up stage3
            _, after1 = await buffer_stage1(events, conversation_id, query)
            _, after2 = await buffer_stage2(after1, conversation_id)
            result = await buffer_stage3(after2, conversation_id)
        return json.dumps(result, indent=2)

    @server.tool(description=(
        "Run a full 3-stage council deliberation in one call. "
        "Stage 1: each model answers independently. "
        "Stage 2: models peer-review each other anonymously. "
        "Stage 3: chairman synthesizes the final answer. "
        "Returns all three stages plus the chairman's final answer at the top level. "
        "Use this for complete deliberation results. "
        "Set web_search=true to enrich the query with live search results. "
        "Optionally override council models for this run only with the models parameter "
        "(list of model IDs with provider prefix, e.g. ['openai:gpt-4.1', 'anthropic:claude-sonnet-4']). "
        "Per-request overrides never modify global settings."
    ))
    async def run_deliberation(
        query: str,
        web_search: bool = False,
        models: list[str] | None = None,
    ) -> str:
        async with CouncilClient(base_url) as client:
            conv = await client.create_conversation()
            conversation_id = conv["id"]
            events = client.stream_message(
                conversation_id, query,
                web_search=web_search, execution_mode="full",
                council_models=models,
            )
            stage1, after1 = await buffer_stage1(events, conversation_id, query)
            stage2, after2 = await buffer_stage2(after1, conversation_id)
            stage3 = await buffer_stage3(after2, conversation_id)

        result = {
            "conversation_id": conversation_id,
            "query": query,
            "stage1": stage1,
            "stage2": stage2,
            "stage3": stage3,
            "chairman_answer": stage3.get("synthesis"),
        }
        return json.dumps(result, indent=2)

    @server.tool(description=(
        "Send a query directly to a single model without deliberation. "
        "Useful for quick questions, testing a specific model, or comparing models. "
        "model must include provider prefix: e.g. 'openai:gpt-4.1', "
        "'anthropic:claude-sonnet-4', 'ollama:llama3', 'groq:llama3-70b-8192'. "
        "Set web_search=true to include web search results in context. "
        "STATELESS: Each call is independent with no memory of previous exchanges. "
        "For multi-turn conversations, use the 'chat' tool instead."
    ))
    async def quick_chat(
        query: str,
        model: str,
        web_search: bool = False,
    ) -> str:
        async with CouncilClient(base_url) as client:
            result = await client.ask(
                content=query,
                models=[model],
                web_search=web_search,
                execution_mode="chat_only",
            )
        return json.dumps({
            "model": result.get("model", model),
            "response": result.get("response"),
            "error": result.get("error"),
            "web_search_used": web_search,
        }, indent=2)

    @server.tool(description=(
        "Chat with a model in a multi-turn conversation. "
        "The model sees the full conversation history from prior turns, "
        "so follow-up questions work naturally. "
        "First call: omit conversation_id to start a new conversation. "
        "Subsequent calls: pass the conversation_id from the previous response to continue. "
        "model must include provider prefix: e.g. 'openai:gpt-4.1', "
        "'anthropic:claude-sonnet-4', 'ollama:llama3', 'groq:llama3-70b-8192'. "
        "Set web_search=true to include web search results in context. "
        "For one-shot questions without memory, use 'quick_chat' instead."
    ))
    async def chat(
        query: str,
        model: str,
        conversation_id: str | None = None,
        web_search: bool = False,
    ) -> str:
        async with CouncilClient(base_url) as client:
            if not conversation_id:
                conv = await client.create_conversation()
                conversation_id = conv["id"]
            events = client.stream_message(
                conversation_id, query,
                web_search=web_search, execution_mode="chat_only",
                council_models=[model],
            )
            result, _ = await buffer_stage1(events, conversation_id, query)

        responses = result.get("results", [])
        first = responses[0] if responses else {}
        return json.dumps({
            "conversation_id": conversation_id,
            "model": first.get("model", model),
            "response": first.get("response"),
            "error": first.get("error"),
            "web_search_used": web_search,
        }, indent=2)

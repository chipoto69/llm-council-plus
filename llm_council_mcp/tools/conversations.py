"""Conversation management MCP tools."""

from __future__ import annotations

import json

from ..client import CouncilClient


def register(server, base_url: str) -> None:
    """Register conversation management tools on the MCP server."""

    @server.tool(description=(
        "List all saved conversations with their titles, IDs, and message counts. "
        "Use the conversation ID with get_conversation to retrieve full content."
    ))
    async def list_conversations() -> str:
        async with CouncilClient(base_url) as client:
            conversations = await client.list_conversations()
        if not conversations:
            return "No conversations found."
        lines = [f"Found {len(conversations)} conversation(s):"]
        for conv in conversations:
            title = conv.get("title") or "(untitled)"
            conv_id = conv.get("id", "unknown")
            count = conv.get("message_count", "?")
            created = conv.get("created_at", "")[:10]  # just date
            lines.append(f"  • [{conv_id}] {title} — {count} message(s), created {created}")
        return "\n".join(lines)

    @server.tool(description=(
        "Retrieve a full conversation by ID, including all messages with Stage 1 model responses, "
        "Stage 2 rankings, and Stage 3 chairman synthesis. "
        "Use list_conversations to find available conversation IDs."
    ))
    async def get_conversation(conversation_id: str) -> str:
        async with CouncilClient(base_url) as client:
            try:
                conv = await client.get_conversation(conversation_id)
            except Exception as e:
                return json.dumps({"error": f"Conversation not found: {e}"})
        # Return summarised view (full data can be large)
        messages = conv.get("messages", [])
        summary = {
            "id": conv.get("id"),
            "title": conv.get("title"),
            "created_at": conv.get("created_at"),
            "message_count": len(messages),
            "messages": [],
        }
        for msg in messages:
            role = msg.get("role")
            if role == "user":
                summary["messages"].append({"role": "user", "content": msg.get("content", "")[:200]})
            elif role == "assistant":
                stage3 = msg.get("stage3")
                stage1 = msg.get("stage1", [])
                mode = msg.get("metadata", {}).get("execution_mode", "unknown")
                entry = {
                    "role": "assistant",
                    "execution_mode": mode,
                    "stage1_model_count": len(stage1),
                }
                if stage3:
                    entry["chairman_synthesis"] = (stage3.get("response") or "")[:500]
                summary["messages"].append(entry)
        return json.dumps(summary, indent=2)

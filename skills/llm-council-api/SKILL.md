---
name: llm-council-api
version: 0.3.0
description: Use when interacting with LLM Council Plus via HTTP API — configuring the council, running deliberations, listing models, or managing conversations — especially when the MCP server is unavailable, connection is stale, or direct REST access is preferred. Triggers on requests like "ask the council", "configure models", "run a deliberation", "check council health", or any manipulation of the LLM Council Plus system.
---

# LLM Council Plus — HTTP API Skill

## Overview

LLM Council Plus is a 3-stage multi-LLM deliberation system. This skill lets you control it entirely via its REST API — no MCP required. Use it when MCP is unavailable, the SSE session is stale, or you prefer direct API access.

**Default base URL:** `http://localhost:8001`  
**Remote server:** replace with `http://<server-ip>:8001`

---

## Quick Reference

| Operation | Method | Endpoint |
|-----------|--------|----------|
| Health check | GET | `/api/health` |
| Get settings (council config) | GET | `/api/settings` |
| Update settings | PUT | `/api/settings` |
| List all models | GET | `/api/models` + `/api/models/direct` + `/api/ollama/tags` + `/api/custom-endpoint/models` |
| List conversations | GET | `/api/conversations` |
| Create conversation | POST | `/api/conversations` |
| Get conversation | GET | `/api/conversations/{id}` |
| Run deliberation (stream) | POST | `/api/conversations/{id}/message/stream` |
| Test a provider | POST | `/api/settings/test-provider` |

**Model ID prefix format:**
```
openrouter:anthropic/claude-sonnet-4   → Cloud via OpenRouter
ollama:llama3.1:latest                 → Local Ollama
anthropic:claude-sonnet-4              → Direct Anthropic API
openai:gpt-4.1                         → Direct OpenAI API
custom:nvidia/nemotron-3-super-120b    → Custom endpoint
groq:llama3-70b-8192                   → Groq fast inference
```

---

## Examples

### 1. Health Check

```bash
curl http://localhost:8001/api/health
# → {"status": "ok", "service": "LLM Council API"}
```

```python
import httpx

async def check_health(base_url="http://localhost:8001"):
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{base_url}/api/health")
        return r.json()
```

---

### 2. Get Current Council Configuration

```bash
curl http://localhost:8001/api/settings | python3 -m json.tool
```

Key fields returned:
- `council_models` — list of model IDs in the council
- `chairman_model` — model that synthesizes the final answer
- `execution_mode` — `"full"` / `"chat_ranking"` / `"chat_only"`
- `search_provider` — active search provider
- `*_api_key_set` — boolean flags (never returns actual keys)
- `custom_endpoint_name` / `custom_endpoint_url` — custom provider details

---

### 3. Update Council Configuration

```bash
# Replace council models (requires 2-8 models)
curl -X PUT http://localhost:8001/api/settings \
  -H "Content-Type: application/json" \
  -d '{
    "council_models": ["custom:z-ai/glm-5.1", "ollama:granite4.1:8b", "custom:moonshotai/kimi-k2.6"],
    "chairman_model": "custom:nvidia/nemotron-3-super-120b-a12b",
    "execution_mode": "full"
  }'
```

All fields are optional — only provided fields are updated.

**Valid `execution_mode` values:**
- `"full"` — all 3 stages (individual → peer review → chairman synthesis)
- `"chat_ranking"` — stages 1+2 (no chairman synthesis)
- `"chat_only"` — stage 1 only (fastest, individual responses)

---

### 4. List All Available Models

```python
import asyncio, httpx

async def list_all_models(base_url="http://localhost:8001"):
    async with httpx.AsyncClient(timeout=30) as client:
        results = []
        for endpoint in ["/api/models", "/api/models/direct", 
                         "/api/ollama/tags", "/api/custom-endpoint/models"]:
            try:
                r = await client.get(f"{base_url}{endpoint}")
                if r.status_code == 200:
                    results.extend(r.json().get("models", []))
            except Exception:
                pass  # provider not configured — skip
    return results

models = asyncio.run(list_all_models())
for m in models[:10]:
    print(m.get("id"), "—", m.get("name"))
```

---

### 5. Run a Full Deliberation

Deliberations use SSE streaming. Create a conversation first, then stream.

```python
import asyncio, httpx, json

async def run_deliberation(query, web_search=False, base_url="http://localhost:8001"):
    async with httpx.AsyncClient(timeout=300) as client:
        # Step 1: Create conversation
        conv = (await client.post(f"{base_url}/api/conversations", json={})).json()
        conv_id = conv["id"]

        # Step 2: Stream the deliberation
        stage1, stage2, stage3 = [], {}, {}
        async with client.stream(
            "POST",
            f"{base_url}/api/conversations/{conv_id}/message/stream",
            json={"content": query, "web_search": web_search, "execution_mode": "full"},
        ) as resp:
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                event = json.loads(line[6:])
                t = event.get("type")

                if t == "stage1_complete":
                    stage1 = event["data"]
                elif t == "stage2_complete":
                    stage2 = event.get("metadata", {})
                elif t == "stage3_complete":
                    stage3 = event["data"]

        return {
            "conversation_id": conv_id,
            "stage1": stage1,
            "stage2": stage2,
            "stage3": stage3,
            "chairman_answer": stage3.get("response"),
        }

result = asyncio.run(run_deliberation("What are the pros and cons of microservices?"))
print("Chairman:", result["chairman_answer"])
```

**Key SSE event types to watch for:**

| Event | When | Contains |
|-------|------|----------|
| `search_complete` | After web search | `search_context`, `search_query` |
| `stage1_complete` | After all models respond | `data`: list of `{model, response, error}` |
| `stage2_complete` | After peer review | `metadata`: `{label_to_model, aggregate_rankings}` |
| `stage3_complete` | After chairman synthesis | `data`: `{model, response, error}` |
| `error` | On failure | `message` |
| `complete` | Stream finished | — |

---

### 6. Quick Chat (Single Model, No Deliberation)

```python
async def quick_chat(query, model, web_search=False, base_url="http://localhost:8001"):
    async with httpx.AsyncClient(timeout=120) as client:
        # Temporarily set single model, run chat_only, restore
        settings = (await client.get(f"{base_url}/api/settings")).json()
        original_models = settings["council_models"]
        original_chairman = settings["chairman_model"]

        await client.put(f"{base_url}/api/settings", json={
            "council_models": [model, model],  # backend requires ≥2 models
            "chairman_model": model,
        })
        try:
            conv = (await client.post(f"{base_url}/api/conversations", json={})).json()
            response = None
            async with client.stream(
                "POST",
                f"{base_url}/api/conversations/{conv['id']}/message/stream",
                json={"content": query, "web_search": web_search, "execution_mode": "chat_only"},
            ) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        event = json.loads(line[6:])
                        if event.get("type") == "stage1_complete":
                            data = event.get("data", [])
                            response = data[0].get("response") if data else None
        finally:
            await client.put(f"{base_url}/api/settings", json={
                "council_models": original_models,
                "chairman_model": original_chairman,
            })
        return response
```

---

### 7. Retrieve a Past Conversation

```python
async def get_conversation(conv_id, base_url="http://localhost:8001"):
    async with httpx.AsyncClient() as client:
        conv = (await client.get(f"{base_url}/api/conversations/{conv_id}")).json()
    for msg in conv.get("messages", []):
        if msg["role"] == "user":
            print("Q:", msg["content"])
        elif msg["role"] == "assistant":
            s3 = msg.get("stage3", {})
            if s3:
                print("A (chairman):", s3.get("response", "")[:500])
    return conv
```

---

## Search Provider Configuration

```bash
# Switch to TinyFish (free, 5 req/min)
curl -X PUT http://localhost:8001/api/settings \
  -H "Content-Type: application/json" \
  -d '{"search_provider": "tinyfish", "tinyfish_api_key": "sk-tinyfish-..."}'

# Valid providers: duckduckgo, tavily, brave, serper, tinyfish
# duckduckgo requires no key; all others require an API key
```

---

## Error Handling

Model errors appear inside `stage1_complete` data — not as top-level failures:

```python
for model_result in stage1:
    if model_result.get("error"):
        msg = model_result.get("error_message", "unknown error")
        if "429" in msg:
            print(f"{model_result['model']}: rate limited — retryable")
        elif "401" in msg or "403" in msg:
            print(f"{model_result['model']}: auth error — check API key")
        else:
            print(f"{model_result['model']}: failed — {msg}")
    else:
        print(f"{model_result['model']}: ✓ responded")
```

The council continues with successful models even if some fail.

---

## Troubleshooting

**Backend unreachable (`ConnectionRefused`)**
- Local: verify `uv run python -m backend.main` is running on port 8001
- Remote: check `http://<server>:8001/api/health` is accessible; firewall may be blocking port 8001
- Docker: run `docker ps` to confirm container is up and healthy

**`execution_mode` null in settings**
- Expected — backend defaults to `"full"` when null. No action needed.

**Council models not updating**
- PUT to `/api/settings` returns the full settings object — check `council_models` in the response to confirm the change was applied
- Model IDs must include provider prefix (e.g., `custom:z-ai/glm-5.1`, not `z-ai/glm-5.1`)

**SSE stream hangs or times out**
- Use `timeout=300` on the httpx client for full deliberations (can take 60-120 seconds)
- Check backend logs for provider-side errors
- `execution_mode: "chat_only"` is much faster if you only need Stage 1

**Model returns error in Stage 1**
- Check `*_api_key_set` flags in `/api/settings` — key may be missing
- Test a specific provider: `POST /api/settings/test-provider` with `{"provider": "openai"}`
- Custom endpoint models need `custom_endpoint_url` and `custom_endpoint_api_key` configured

**Settings not persisting after restart**
- Settings are stored in `data/settings.json` — if using Docker, confirm the `./data` volume is mounted

---

## Installation

**Option 1: Clone and symlink**
```bash
git clone https://github.com/jacob-bd/llm-council-plus.git
mkdir -p ~/.claude/skills
ln -s "$(pwd)/llm-council-plus/skills/llm-council-api" ~/.claude/skills/llm-council-api
```

**Option 2: Copy directly**
```bash
mkdir -p ~/.claude/skills/llm-council-api
curl -o ~/.claude/skills/llm-council-api/SKILL.md \
  https://raw.githubusercontent.com/jacob-bd/llm-council-plus/main/skills/llm-council-api/SKILL.md
```

After installation, Claude Code automatically discovers and loads the skill when you ask about council operations.

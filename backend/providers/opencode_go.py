"""OpenCode Go provider with dual format support (OpenAI-compatible + Anthropic)."""

import os
import httpx
from typing import List, Dict, Any

from .base import LLMProvider


class OpenCodeGoProvider(LLMProvider):
    """Provider for OpenCode Go API endpoint.

    Supports two API formats depending on the model:
    - OpenAI-compatible (chat/completions): qwen3.6-plus, deepseek-v4-pro, etc.
    - Anthropic-compatible (messages): minimax-m2.7
    """

    BASE_URL = "https://opencode.ai/zen/go/v1"

    # Models that use the Anthropic Messages format
    ANTHROPIC_FORMAT_MODELS = frozenset({"minimax-m2.7"})

    # Default available models (hardcoded — the endpoint may not expose a /models route)
    DEFAULT_MODELS = [
        "qwen3.6-plus",
        "deepseek-v4-pro",
        "minimax-m2.7",
    ]

    def _get_api_key(self) -> str:
        """Get API key from env var, with fallback to hardcoded key."""
        return os.getenv("OPENCODE_GO_API_KEY", "")

    # ------------------------------------------------------------------ #
    #  query — dispatch between OpenAI and Anthropic format
    # ------------------------------------------------------------------ #
    async def query(
        self,
        model_id: str,
        messages: List[Dict[str, str]],
        timeout: float = 120.0,
        temperature: float = 0.7,
    ) -> Dict[str, Any]:
        api_key = self._get_api_key()
        if not api_key:
            return {
                "error": True,
                "error_message": "OpenCode Go API key not configured — set OPENCODE_GO_API_KEY",
            }

        model = model_id.removeprefix("opencode_go:")

        if model in self.ANTHROPIC_FORMAT_MODELS:
            return await self._query_anthropic_format(
                model, messages, timeout, temperature, api_key
            )
        return await self._query_openai_format(
            model, messages, timeout, temperature, api_key
        )

    # ------------------------------------------------------------------ #
    #  OpenAI-compatible format  (qwen3.6-plus, deepseek-v4-pro, …)
    # ------------------------------------------------------------------ #
    async def _query_openai_format(
        self,
        model: str,
        messages: List[Dict[str, str]],
        timeout: float,
        temperature: float,
        api_key: str,
    ) -> Dict[str, Any]:
        try:
            headers = {
                "Content-Type": "application/json",
                "x-api-key": api_key,
            }

            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self.BASE_URL}/chat/completions",
                    headers=headers,
                    json={
                        "model": model,
                        "messages": messages,
                        "temperature": temperature,
                    },
                )

                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After", "unknown")
                    return {
                        "error": True,
                        "error_message": (
                            f"OpenCode Go rate limited (429). "
                            f"Retry-After: {retry_after}"
                        ),
                    }

                if response.status_code != 200:
                    return {
                        "error": True,
                        "error_message": (
                            f"OpenCode Go API error: {response.status_code} - "
                            f"{response.text[:500]}"
                        ),
                    }

                data = response.json()
                content = data["choices"][0]["message"]["content"]
                return {"content": content, "error": False}

        except httpx.TimeoutException:
            return {"error": True, "error_message": "OpenCode Go request timed out"}
        except httpx.ConnectError:
            return {
                "error": True,
                "error_message": "Failed to connect to OpenCode Go API",
            }
        except Exception as e:
            return {"error": True, "error_message": str(e)}

    # ------------------------------------------------------------------ #
    #  Anthropic-compatible format  (minimax-m2.7)
    # ------------------------------------------------------------------ #
    async def _query_anthropic_format(
        self,
        model: str,
        messages: List[Dict[str, str]],
        timeout: float,
        temperature: float,
        api_key: str,
    ) -> Dict[str, Any]:
        # Split out system message (Anthropic keeps it top-level)
        system_message = ""
        filtered_messages: List[Dict[str, str]] = []
        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                filtered_messages.append(msg)

        try:
            headers = {
                "Content-Type": "application/json",
                "x-api-key": api_key,
            }

            payload: Dict[str, Any] = {
                "model": model,
                "messages": filtered_messages,
                "max_tokens": 4096,
                "temperature": temperature,
            }
            if system_message:
                payload["system"] = system_message

            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    f"{self.BASE_URL}/messages",
                    headers=headers,
                    json=payload,
                )

                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After", "unknown")
                    return {
                        "error": True,
                        "error_message": (
                            f"OpenCode Go rate limited (429). "
                            f"Retry-After: {retry_after}"
                        ),
                    }

                if response.status_code != 200:
                    return {
                        "error": True,
                        "error_message": (
                            f"OpenCode Go API error: {response.status_code} - "
                            f"{response.text[:500]}"
                        ),
                    }

                data = response.json()
                # Anthropic-style response: content is an array of blocks
                content_blocks = data.get("content", [])
                text_parts = [
                    block["text"] for block in content_blocks if block.get("type") == "text"
                ]
                content = "\n".join(text_parts) if text_parts else ""
                return {"content": content, "error": False}

        except httpx.TimeoutException:
            return {"error": True, "error_message": "OpenCode Go request timed out"}
        except httpx.ConnectError:
            return {
                "error": True,
                "error_message": "Failed to connect to OpenCode Go API",
            }
        except Exception as e:
            return {"error": True, "error_message": str(e)}

    # ------------------------------------------------------------------ #
    #  get_models — return hardcoded list (endpoint may not expose /models)
    # ------------------------------------------------------------------ #
    async def get_models(self) -> List[Dict[str, Any]]:
        models = []
        for m in self.DEFAULT_MODELS:
            suffix = " [Anthropic]" if m in self.ANTHROPIC_FORMAT_MODELS else ""
            models.append({
                "id": f"opencode_go:{m}",
                "name": f"{m} [OpenCode Go]{suffix}",
                "provider": "OpenCode Go",
            })
        return models

    # ------------------------------------------------------------------ #
    #  validate_key — quick connectivity / auth check
    # ------------------------------------------------------------------ #
    async def validate_key(self, api_key: str) -> Dict[str, Any]:
        """Validate the API key by sending a minimal request."""
        if not api_key:
            return {"success": False, "message": "No API key provided"}

        try:
            headers = {
                "Content-Type": "application/json",
                "x-api-key": api_key,
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                # Use the OpenAI-compatible endpoint with a minimal prompt
                response = await client.post(
                    f"{self.BASE_URL}/chat/completions",
                    headers=headers,
                    json={
                        "model": self.DEFAULT_MODELS[0],  # qwen3.6-plus
                        "messages": [{"role": "user", "content": "Hi"}],
                        "max_tokens": 1,
                        "temperature": 0.0,
                    },
                )

                if response.status_code == 200:
                    return {"success": True, "message": "API key is valid"}
                if response.status_code in (401, 403):
                    return {
                        "success": False,
                        "message": "Invalid API key — authentication failed",
                    }
                # 429 / 5xx still mean the key is valid; the server is just busy
                if response.status_code == 429:
                    return {
                        "success": True,
                        "message": "API key accepted (endpoint rate-limited at the moment)",
                    }
                return {
                    "success": False,
                    "message": f"OpenCode Go API error: {response.status_code}",
                }

        except httpx.ConnectError:
            return {"success": False, "message": "Connection failed — check network"}
        except httpx.TimeoutException:
            return {"success": False, "message": "Connection timed out"}
        except Exception as e:
            return {"success": False, "message": str(e)}

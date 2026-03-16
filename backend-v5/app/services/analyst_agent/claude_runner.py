"""Dual-mode Claude runner: CLI subprocess (local) or Anthropic SDK (VPS).

Mode selection:
  - Set CLAUDE_USE_CLI=true for local runs (uses `claude` CLI binary, Max subscription)
  - Default: SDK mode (uses ANTHROPIC_API_KEY, good for Haiku on VPS)
"""
import asyncio
import json
import logging
import os
import re
import shutil
from typing import Optional

import httpx

from app.config import get_settings
from app.services.openai_runtime import get_openai_runtime

logger = logging.getLogger(__name__)

def _env_flag(value: str) -> bool:
    return value.lower() in ("true", "1", "yes", "on")


def _use_cli() -> bool:
    return _env_flag(os.environ.get("CLAUDE_USE_CLI", ""))


def _claude_bin() -> str:
    return os.environ.get("CLAUDE_BIN", shutil.which("claude") or "claude")

# Model name mapping: short names → Anthropic model IDs (SDK mode)
_MODEL_MAP = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-20250514",
    "opus": "claude-opus-4-20250514",
}

# CLI model mapping: short names → claude CLI model flags
_CLI_MODEL_MAP = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-6",
}

_client = None


def _local_fallback_enabled() -> bool:
    settings = get_settings()
    return settings.local_llm_fallback_enabled or settings.local_llm_prefer_local


def _prefer_local() -> bool:
    return get_settings().local_llm_prefer_local


def _openai_agent_enabled() -> bool:
    settings = get_settings()
    runtime = get_openai_runtime()
    return settings.openai_agent_enabled and runtime.available


def has_available_llm() -> bool:
    """Return True if Claude or the local fallback is configured."""
    settings = get_settings()
    return bool(
        _use_cli()
        or settings.anthropic_api_key
        or os.environ.get("ANTHROPIC_API_KEY")
        or _openai_agent_enabled()
        or _local_fallback_enabled()
    )


def _get_client():
    """Get or create Anthropic SDK client (SDK mode only)."""
    global _client
    if _client is None:
        import anthropic
        settings = get_settings()
        api_key = settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


async def _call_claude_sdk(
    prompt: str,
    timeout: int,
    model: str,
    system_prompt: Optional[str] = None,
) -> str:
    """Call Claude via Anthropic SDK (VPS mode)."""
    model_id = _MODEL_MAP.get(model, model)
    client = _get_client()

    def _sync_call():
        request = {
            "model": model_id,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            request["system"] = system_prompt
        response = client.messages.create(**request)
        return response.content[0].text

    try:
        result = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, _sync_call),
            timeout=timeout,
        )
        return result
    except asyncio.TimeoutError:
        logger.error("Claude SDK (%s) timed out after %ds", model, timeout)
        raise
    except Exception as exc:
        logger.error("Claude SDK (%s) failed: %s", model, exc)
        raise RuntimeError(f"Claude SDK ({model}) failed: {exc}") from exc


async def _call_claude_cli(
    prompt: str,
    timeout: int,
    model: str,
    system_prompt: Optional[str] = None,
) -> str:
    """Call Claude via CLI subprocess (local mode, uses Max subscription)."""
    model_id = _CLI_MODEL_MAP.get(model, model)
    full_prompt = prompt if not system_prompt else f"{system_prompt.strip()}\n\n{prompt}"

    cmd = [
        _claude_bin(),
        "-p", full_prompt,
        "--output-format", "text",
        "--model", model_id,
        "--max-turns", "1",
    ]

    logger.info("Calling Claude CLI (%s) ...", model)

    # Clear CLAUDECODE env var to allow nested subprocess calls
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout,
        )

        if proc.returncode != 0:
            err_text = stderr.decode("utf-8", errors="replace")[:500]
            raise RuntimeError(
                f"Claude CLI ({model}) exited {proc.returncode}: {err_text}"
            )

        result = stdout.decode("utf-8", errors="replace").strip()
        if not result:
            raise RuntimeError(f"Claude CLI ({model}) returned empty output")

        return result

    except asyncio.TimeoutError:
        logger.error("Claude CLI (%s) timed out after %ds", model, timeout)
        proc.kill()
        raise
    except Exception as exc:
        if "TimeoutError" not in type(exc).__name__:
            logger.error("Claude CLI (%s) failed: %s", model, exc)
        raise


async def _call_local_openai_compatible(
    prompt: str,
    timeout: int,
    model: str,
    system_prompt: Optional[str] = None,
) -> str:
    """Call a local OpenAI-compatible server, e.g. Qwen on laptop."""
    settings = get_settings()
    base_url = settings.local_llm_base_url.rstrip("/")
    url = base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": settings.local_llm_model or model,
        "messages": messages,
        "temperature": settings.local_llm_temperature,
        "max_tokens": settings.local_llm_max_tokens,
        # Qwen 3.5 defaults to reasoning mode unless explicitly disabled.
        "chat_template_kwargs": {"enable_thinking": False},
    }
    headers = {
        "Authorization": f"Bearer {settings.local_llm_api_key}",
        "Content-Type": "application/json",
    }

    logger.info("Calling local LLM fallback (%s)", payload["model"])
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("Local LLM returned no choices")

    message = choices[0].get("message") or {}
    content = message.get("content", "")
    if isinstance(content, list):
        content = "".join(
            part.get("text", "")
            for part in content
            if isinstance(part, dict)
        )

    if not content and isinstance(message.get("reasoning_content"), str):
        content = message["reasoning_content"]

    content = content.strip() if isinstance(content, str) else ""
    if not content:
        raise RuntimeError("Local LLM returned empty output")
    return content


def _resolve_openai_agent_model(model: str) -> str:
    settings = get_settings()
    requested = (model or "").lower()
    if requested in {"haiku", "fast", "mini"}:
        return settings.openai_agent_fast_model
    if requested in {"sonnet", "opus", "deep", "synthesis"}:
        return settings.openai_agent_deep_model
    return model


async def _call_openai_agent(
    prompt: str,
    timeout: int,
    model: str,
    system_prompt: Optional[str] = None,
) -> str:
    runtime = get_openai_runtime()
    resolved_model = _resolve_openai_agent_model(model)
    logger.info("Calling OpenAI agent model (%s)", resolved_model)
    return await asyncio.wait_for(
        runtime.text_completion(
            system_prompt=system_prompt,
            user_prompt=prompt,
            model=resolved_model,
            max_completion_tokens=700 if resolved_model == get_settings().openai_agent_deep_model else 450,
            temperature=0.1,
            cache_scope=f"agent:{resolved_model}",
            usage_bucket="agent",
        ),
        timeout=timeout,
    )


async def call_claude(
    prompt: str,
    timeout: int = 120,
    model: str = "sonnet",
    system_prompt: Optional[str] = None,
) -> str:
    """Call Claude and return text output.

    Automatically uses CLI subprocess (local, Max subscription) or SDK (VPS)
    based on the CLAUDE_USE_CLI environment variable.

    Args:
        prompt: Full prompt text to send.
        timeout: Max seconds to wait for response.
        model: Model to use (sonnet, haiku, opus). Default: sonnet.

    Returns:
        Raw text output from Claude.
    """
    async def _call_primary() -> str:
        if _openai_agent_enabled():
            return await _call_openai_agent(prompt, timeout, model, system_prompt=system_prompt)
        if _use_cli():
            return await _call_claude_cli(prompt, timeout, model, system_prompt=system_prompt)
        return await _call_claude_sdk(prompt, timeout, model, system_prompt=system_prompt)

    local_enabled = _local_fallback_enabled()
    if _prefer_local() and local_enabled:
        try:
            return await _call_local_openai_compatible(
                prompt,
                timeout,
                model,
                system_prompt=system_prompt,
            )
        except Exception:
            logger.warning("Local preferred LLM failed, falling back to Claude", exc_info=True)
            return await _call_primary()

    try:
        return await _call_primary()
    except Exception:
        if not local_enabled:
            raise
        logger.warning("Claude failed, falling back to local LLM", exc_info=True)
        return await _call_local_openai_compatible(
            prompt,
            timeout,
            model,
            system_prompt=system_prompt,
        )


def extract_json(raw: str) -> dict:
    """Extract a JSON object from Claude's response text.

    Handles both raw JSON and ```json fenced blocks.
    """
    # Try fenced block first
    match = re.search(r"```(?:json)?\s*\n(.*?)```", raw, re.DOTALL)
    if match:
        return json.loads(match.group(1).strip())

    # Try raw JSON (find first { ... last })
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(raw[start : end + 1])

    raise ValueError(f"No JSON found in Claude response:\n{raw[:500]}")


async def call_claude_json(
    prompt: str,
    timeout: int = 120,
    model: str = "sonnet",
    system_prompt: Optional[str] = None,
) -> dict:
    """Call Claude and parse JSON from response.

    Args:
        prompt: Prompt that instructs Claude to respond with JSON.
        timeout: Max seconds to wait.
        model: Model to use (sonnet, haiku, opus). Default: sonnet.

    Returns:
        Parsed dict from Claude's JSON response.
    """
    raw = await call_claude(prompt, timeout, model=model, system_prompt=system_prompt)
    try:
        return extract_json(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error("Failed to parse JSON from Claude response: %s", exc)
        logger.debug("Raw response:\n%s", raw[:2000])
        raise

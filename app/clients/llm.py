"""LLM client protocol and implementations (Bifrost gateway and Mock)."""

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional, Protocol, Tuple, runtime_checkable

from app.cache import DiskCache

logger = logging.getLogger(__name__)

@runtime_checkable
class LLMClient(Protocol):
    """Protocol for LLM completions."""

    async def json_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.2,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Executes a chat completion expecting structured JSON output.

        Returns:
            Tuple of (parsed_json_dict, usage_dict).
        """
        ...


def extract_json_payload(raw_text: str) -> Dict[str, Any]:
    """Robustly extracts JSON from an LLM response string."""
    text = raw_text.strip()

    # Strip markdown code blocks ```json ... ```
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()

    # Direct JSON parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Look for the first outer {...} or [...] block
    match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse valid JSON from LLM response: {text[:200]}...")


class BifrostLLMClient:
    """Async LLM client communicating with LLMs exclusively via Bifrost AI Gateway."""

    def __init__(
        self,
        base_url: str = "http://localhost:8080/v1",
        api_key: str = "dummy",
        default_model: str = "gemini/gemini-2.5-flash",
        cache: Optional[DiskCache] = None,
        timeout_seconds: float = 60.0,
        cache_ttl_hours: int = 12,
    ):
        from openai import AsyncOpenAI

        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or "dummy"
        self.default_model = default_model
        self.cache = cache or DiskCache()
        self.timeout_seconds = timeout_seconds
        self.cache_ttl_hours = cache_ttl_hours
        self._openai_client = AsyncOpenAI(base_url=self.base_url, api_key=self.api_key)

    async def json_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.2,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        target_model = model or self.default_model
        cache_key = DiskCache.make_key(
            "llm_completion",
            system=system_prompt,
            user=user_prompt,
            model=target_model,
            temp=temperature,
        )

        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached.get("data", {}), cached.get("usage", {"cached": True})

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try_native_json = True
        last_error = None
        current_base = self.base_url

        for attempt in range(3):
            try:
                kwargs: Dict[str, Any] = {
                    "model": target_model,
                    "messages": messages,
                    "temperature": temperature,
                }
                if try_native_json:
                    kwargs["response_format"] = {"type": "json_object"}

                resp = await asyncio.wait_for(
                    self._openai_client.chat.completions.create(**kwargs),
                    timeout=self.timeout_seconds,
                )

                content = resp.choices[0].message.content or ""
                parsed = extract_json_payload(content)
                usage = {
                    "prompt_tokens": getattr(resp.usage, "prompt_tokens", 0) if resp.usage else 0,
                    "completion_tokens": getattr(resp.usage, "completion_tokens", 0) if resp.usage else 0,
                    "total_tokens": getattr(resp.usage, "total_tokens", 0) if resp.usage else 0,
                }

                self.cache.set(cache_key, {"data": parsed, "usage": usage}, ttl_hours=self.cache_ttl_hours)
                return parsed, usage

            except Exception as e:
                err_str = str(e).lower()
                last_error = e

                # 404 handling: test fallback drop-in route /openai if /v1 was 404
                if "404" in err_str and "/v1" in current_base:
                    alt_base = current_base.replace("/v1", "/openai")
                    logger.warning(f"Bifrost returned 404 at {current_base}. Retrying with drop-in path {alt_base}")
                    from openai import AsyncOpenAI
                    self.base_url = alt_base
                    self._openai_client = AsyncOpenAI(base_url=self.base_url, api_key=self.api_key)
                    current_base = alt_base
                    continue

                # response_format rejection fallback
                if try_native_json and ("response_format" in err_str or "json_object" in err_str or "unsupported" in err_str):
                    logger.warning(f"Gateway or provider rejected response_format: {e}. Retrying without native JSON mode.")
                    try_native_json = False
                    continue

                # Rate limiting (429) backoff
                if "429" in err_str:
                    logger.warning(f"Rate limited (429) via Bifrost. Backing off before attempt {attempt+1}")
                    await asyncio.sleep(2.0 * (2**attempt))
                    continue

                if attempt < 2:
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
                break

        logger.error(f"LLM completion failed after retries: {last_error}")
        raise RuntimeError(f"Bifrost LLM request failed: {last_error}")


class MockLLMClient:
    """Mock LLM client serving canned JSON fixtures matching domain requirements."""

    def __init__(self, fixtures_dir: str = "tests/fixtures"):
        self.fixtures_dir = Path(fixtures_dir)

    def _load_fixture(self, filename: str) -> Dict[str, Any]:
        p = self.fixtures_dir / filename
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    async def json_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.2,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        prompt_combo = (system_prompt + " " + user_prompt).lower()

        usage = {
            "prompt_tokens": 1250,
            "completion_tokens": 480,
            "total_tokens": 1730,
            "mock": True,
        }

        # 1. Verification check prompt
        if "fact-checker" in prompt_combo or "verdicts" in prompt_combo:
            data = self._load_fixture("llm_verify.json")
            return data.get("default", {"verdicts": []}), usage

        # 2. Entity resolution prompt
        if "candidates" in prompt_combo or "canonical_name" in prompt_combo:
            data = self._load_fixture("llm_resolve.json")
            u_lower = user_prompt.lower()
            if "ambiguous" in u_lower or "alex smith" in u_lower:
                return data.get("ambiguous", {}), usage
            elif "jensen" in u_lower or "huang" in u_lower or "target entity: nvidia" in u_lower:
                return data.get("jensen_huang", {}), usage
            return data.get("stripe", {}), usage

        # 3. Briefing synthesis prompt (default)
        data = self._load_fixture("llm_synthesize.json")
        stripe_draft = data.get("stripe", {})
        return stripe_draft, usage

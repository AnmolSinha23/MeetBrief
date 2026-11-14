"""Tests for SearchClient and LLMClient implementations and caching."""

import pytest
from app.cache import DiskCache
from app.clients.search import SearchClient, MockSearchClient, TavilySearchClient
from app.clients.llm import LLMClient, MockLLMClient, extract_json_payload

def test_cache_set_get_and_expiration(tmp_path):
    cache = DiskCache(cache_dir=str(tmp_path))
    key = DiskCache.make_key("test", query="Stripe", limit=5)

    assert cache.get(key) is None
    cache.set(key, {"answer": 42}, ttl_hours=1)
    assert cache.get(key) == {"answer": 42}

    # Expired check
    cache.set(key, {"answer": 42}, ttl_hours=-1)
    assert cache.get(key) is None

def test_extract_json_payload():
    raw_markdown = """```json
    {
        "status": "ok",
        "value": 123
    }
    ```"""
    parsed = extract_json_payload(raw_markdown)
    assert parsed == {"status": "ok", "value": 123}

    raw_prose = "Here is the response: {\"candidate\": \"Test\"} Hope this helps."
    parsed2 = extract_json_payload(raw_prose)
    assert parsed2 == {"candidate": "Test"}

@pytest.mark.asyncio
async def test_mock_search_client():
    client: SearchClient = MockSearchClient()
    res = await client.search("Stripe latest news", topic="news")
    assert "results" in res
    assert len(res["results"]) > 0
    assert any("Stripe" in r["title"] for r in res["results"])

    extracted = await client.extract(["https://stripe.com"])
    assert len(extracted) == 1
    assert "raw_content" in extracted[0]

@pytest.mark.asyncio
async def test_mock_llm_client():
    client: LLMClient = MockLLMClient()

    # Resolution mock
    res_resolve, usage = await client.json_completion(
        system_prompt="From the search results, identify who/what the query refers to. Return JSON:",
        user_prompt="canonical_name and candidates for Stripe",
    )
    assert "candidates" in res_resolve
    assert res_resolve["candidates"][0]["canonical_name"] == "Stripe"

    # Synthesis mock
    res_synth, _ = await client.json_completion(
        system_prompt="You are a meticulous research analyst",
        user_prompt="ENTITY: Stripe",
    )
    assert "tldr" in res_synth
    assert "developments" in res_synth
    assert len(res_synth["developments"]) >= 1

    # Verification mock
    res_verif, _ = await client.json_completion(
        system_prompt="You are a strict fact-checker.",
        user_prompt="verdicts for claims",
    )
    assert "verdicts" in res_verif

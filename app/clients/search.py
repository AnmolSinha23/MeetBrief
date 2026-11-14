"""Search client protocol and implementations (Tavily and Mock)."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from app.cache import DiskCache

logger = logging.getLogger(__name__)

@runtime_checkable
class SearchClient(Protocol):
    """Protocol for web search engines."""

    async def search(
        self,
        query: str,
        topic: str = "general",
        time_range: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        max_results: int = 6,
        search_depth: str = "basic",
        include_domains: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Performs a search query returning results dictionary."""
        ...

    async def extract(self, urls: List[str]) -> List[Dict[str, Any]]:
        """Extracts clean full-text content from given URLs."""
        ...


class TavilySearchClient:
    """Async Tavily search client with retries, caching, and fallback handling."""

    def __init__(
        self,
        api_key: str,
        cache: Optional[DiskCache] = None,
        concurrency: int = 4,
        timeout_seconds: float = 30.0,
        cache_ttl_hours: int = 12,
    ):
        from tavily import AsyncTavilyClient

        self.client = AsyncTavilyClient(api_key=api_key)
        self.cache = cache or DiskCache()
        self.semaphore = asyncio.Semaphore(concurrency)
        self.timeout_seconds = timeout_seconds
        self.cache_ttl_hours = cache_ttl_hours

    async def search(
        self,
        query: str,
        topic: str = "general",
        time_range: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        max_results: int = 6,
        search_depth: str = "basic",
        include_domains: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        cache_key = DiskCache.make_key(
            "tavily_search",
            query=query,
            topic=topic,
            time_range=time_range,
            start_date=start_date,
            end_date=end_date,
            max_results=max_results,
            search_depth=search_depth,
            include_domains=sorted(include_domains or []),
        )

        cached = self.cache.get(cache_key)
        if cached is not None:
            cached_copy = dict(cached)
            cached_copy["_from_cache"] = True
            return cached_copy

        kwargs: Dict[str, Any] = {
            "query": query,
            "topic": topic,
            "max_results": max_results,
            "search_depth": search_depth,
            "include_answer": False,
            "include_raw_content": False,
        }
        if include_domains:
            kwargs["include_domains"] = include_domains
        if time_range:
            kwargs["time_range"] = time_range
        if start_date:
            kwargs["start_date"] = start_date
        if end_date:
            kwargs["end_date"] = end_date

        async with self.semaphore:
            last_err = None
            used_fallback = False
            for attempt in range(3):
                try:
                    res = await asyncio.wait_for(
                        self.client.search(**kwargs),
                        timeout=self.timeout_seconds,
                    )
                    if isinstance(res, dict):
                        res["_from_cache"] = False
                        res["_used_fallback"] = used_fallback
                        self.cache.set(cache_key, res, ttl_hours=self.cache_ttl_hours)
                        return res
                    return {"results": []}
                except TypeError as e:
                    # Parameter start_date / end_date not accepted by this SDK version
                    if ("start_date" in kwargs or "end_date" in kwargs) and not used_fallback:
                        logger.warning(f"Tavily SDK rejected start_date/end_date: {e}. Retrying with time_range='month'")
                        kwargs.pop("start_date", None)
                        kwargs.pop("end_date", None)
                        kwargs["time_range"] = "month"
                        used_fallback = True
                        continue
                    last_err = e
                    break
                except Exception as e:
                    err_str = str(e).lower()
                    if ("400" in err_str or "invalid" in err_str) and (
                        "start_date" in kwargs or "end_date" in kwargs
                    ) and not used_fallback:
                        logger.warning(f"Tavily API rejected date range: {e}. Retrying with time_range='month'")
                        kwargs.pop("start_date", None)
                        kwargs.pop("end_date", None)
                        kwargs["time_range"] = "month"
                        used_fallback = True
                        continue

                    last_err = e
                    if attempt < 2:
                        await asyncio.sleep(0.5 * (2**attempt))
                        continue
                    break

            logger.error(f"Tavily search failed for query '{query}': {last_err}")
            return {"results": [], "error": str(last_err)}

    async def extract(self, urls: List[str]) -> List[Dict[str, Any]]:
        if not urls:
            return []

        cache_key = DiskCache.make_key("tavily_extract", urls=sorted(urls))
        cached = self.cache.get(cache_key)
        if cached is not None:
            return cached.get("results", [])

        async with self.semaphore:
            for attempt in range(2):
                try:
                    res = await asyncio.wait_for(
                        self.client.extract(urls=urls, extract_depth="basic", format="text"),
                        timeout=self.timeout_seconds,
                    )
                    results = res.get("results", []) if isinstance(res, dict) else []
                    self.cache.set(cache_key, {"results": results}, ttl_hours=self.cache_ttl_hours)
                    return results
                except Exception as e:
                    logger.warning(f"Tavily extract attempt {attempt+1} failed: {e}")
                    if attempt == 0:
                        await asyncio.sleep(0.5)

            return []


class MockSearchClient:
    """Mock search client using offline canned fixtures."""

    def __init__(self, fixtures_dir: str = "tests/fixtures"):
        self.fixtures_dir = Path(fixtures_dir)

    def _load_fixture(self, filename: str) -> Dict[str, Any]:
        p = self.fixtures_dir / filename
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"results": []}

    async def search(
        self,
        query: str,
        topic: str = "general",
        time_range: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        max_results: int = 6,
        search_depth: str = "basic",
        include_domains: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        q_lower = query.lower()
        if "jensen" in q_lower or "huang" in q_lower or "nvidia" in q_lower:
            data = self._load_fixture("tavily_person.json")
        else:
            data = self._load_fixture("tavily_stripe.json")

        results = list(data.get("results", []))
        return {
            "results": results[:max_results],
            "_from_cache": False,
            "_used_fallback": False,
        }

    async def extract(self, urls: List[str]) -> List[Dict[str, Any]]:
        extracted = []
        for u in urls:
            extracted.append(
                {
                    "url": u,
                    "raw_content": f"Detailed extracted web content from {u}. Full corporate announcement, background data, and executive quotes.",
                }
            )
        return extracted

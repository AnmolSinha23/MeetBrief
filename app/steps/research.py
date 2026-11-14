"""Parallel Tavily research execution step."""

import asyncio
import logging
import time
from typing import Any, Dict, List, Tuple
from app.clients.search import SearchClient
from app.steps.plan import PlannedQuery

logger = logging.getLogger(__name__)

async def execute_research(
    planned_queries: List[PlannedQuery],
    search_client: SearchClient,
    max_results_per_query: int = 6,
    search_depth: str = "basic",
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Executes planned queries concurrently and aggregates raw search items.

    Returns:
        Tuple of (all_raw_items, research_trace_summary).
    """
    t0 = time.perf_counter()

    async def run_single(pq: PlannedQuery) -> Tuple[PlannedQuery, Dict[str, Any]]:
        kwargs: Dict[str, Any] = {
            "query": pq.query,
            "topic": pq.topic,
            "max_results": 3 if pq.is_background else max_results_per_query,
            "search_depth": pq.depth or search_depth,
        }
        if pq.include_domains:
            kwargs["include_domains"] = pq.include_domains
        if not pq.is_background:
            if pq.start_date:
                kwargs["start_date"] = pq.start_date
            if pq.end_date:
                kwargs["end_date"] = pq.end_date

        try:
            res = await search_client.search(**kwargs)
            return pq, res
        except Exception as e:
            logger.warning(f"Query '{pq.query}' failed: {e}")
            return pq, {"results": [], "error": str(e), "_from_cache": False}

    tasks = [run_single(pq) for pq in planned_queries]
    results = await asyncio.gather(*tasks)

    all_raw_items: List[Dict[str, Any]] = []
    queries_trace: List[Dict[str, Any]] = []
    total_cache_hits = 0

    for pq, res in results:
        items = res.get("results", [])
        is_cache = res.get("_from_cache", False)
        if is_cache:
            total_cache_hits += 1

        queries_trace.append(
            {
                "category": pq.category,
                "query": pq.query,
                "topic": pq.topic,
                "results_count": len(items),
                "cached": is_cache,
                "used_fallback": res.get("_used_fallback", False),
                "error": res.get("error"),
            }
        )

        for item in items:
            item_copy = dict(item)
            item_copy["_category"] = pq.category
            item_copy["_is_background"] = pq.is_background
            all_raw_items.append(item_copy)

    duration_ms = int((time.perf_counter() - t0) * 1000)
    trace_summary = {
        "total_queries": len(planned_queries),
        "total_raw_results": len(all_raw_items),
        "cache_hits": total_cache_hits,
        "duration_ms": duration_ms,
        "queries": queries_trace,
    }

    return all_raw_items, trace_summary

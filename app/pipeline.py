"""Pipeline orchestrator for MeetBrief."""

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, Tuple

from app.cache import DiskCache
from app.config import get_settings
from app.clients.search import MockSearchClient, SearchClient, TavilySearchClient
from app.clients.llm import BifrostLLMClient, LLMClient, MockLLMClient
from app.models import Briefing, LLMDraft, MeetingInput, ResolvedEntity, TraceStep, Window
from app.steps.window import calculate_window
from app.steps.resolve import resolve_entity
from app.steps.plan import plan_queries
from app.steps.research import execute_research
from app.steps.normalize import normalize_sources
from app.steps.synthesize import synthesize_briefing
from app.steps.verify import verify_briefing
from app.steps.render import enforce_budget

logger = logging.getLogger(__name__)

BRIEFINGS_DIR = Path("data/briefings")
BRIEFINGS_DIR.mkdir(parents=True, exist_ok=True)

def save_briefing(briefing: Briefing) -> Path:
    """Saves briefing JSON to disk."""
    p = BRIEFINGS_DIR / f"{briefing.id}.json"
    with open(p, "w", encoding="utf-8") as f:
        json.dump(briefing.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
    return p

def load_briefing(briefing_id: str) -> Optional[Briefing]:
    """Loads a briefing JSON from disk."""
    p = BRIEFINGS_DIR / f"{briefing_id}.json"
    if not p.exists():
        # Check samples
        sample_path = Path("data/samples/sample_briefing.json")
        if sample_path.exists() and (briefing_id in ("demo", "sample") or briefing_id == "briefing_demo"):
            with open(sample_path, "r", encoding="utf-8") as f:
                return Briefing.model_validate(json.load(f))
        return None
    with open(p, "r", encoding="utf-8") as f:
        return Briefing.model_validate(json.load(f))

async def run_pipeline(
    meeting_input: MeetingInput,
    search_client: Optional[SearchClient] = None,
    llm_client: Optional[LLMClient] = None,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> Briefing:
    """Executes the complete 7-step grounded pre-meeting briefing pipeline."""
    settings = get_settings()
    t_pipeline_start = time.perf_counter()
    briefing_id = f"briefing_{uuid.uuid4().hex[:12]}"
    trace: list[TraceStep] = []

    # Initialize clients based on configuration
    if search_client is None:
        if settings.MOCK_MODE:
            search_client = MockSearchClient()
        else:
            search_client = TavilySearchClient(
                api_key=settings.TAVILY_API_KEY,
                concurrency=settings.CONCURRENCY,
                cache_ttl_hours=settings.CACHE_TTL_HOURS,
            )

    if llm_client is None:
        if settings.MOCK_MODE:
            llm_client = MockLLMClient()
        else:
            llm_client = BifrostLLMClient(
                base_url=settings.BIFROST_BASE_URL,
                api_key=settings.BIFROST_API_KEY,
                default_model=settings.LLM_MODEL,
                cache_ttl_hours=settings.CACHE_TTL_HOURS,
            )

    # ----------------------------------------------------
    # Step 1: Calculate Window
    # ----------------------------------------------------
    if progress_callback:
        progress_callback(1, "Enforcing 30-day temporal window...")
    t0 = time.perf_counter()
    window, window_warnings = calculate_window(
        meeting_time=meeting_input.meeting_time,
        window_days=settings.WINDOW_DAYS,
    )
    trace.append(
        TraceStep(
            name="1_window",
            started_at=datetime.now(timezone.utc),
            duration_ms=int((time.perf_counter() - t0) * 1000),
            detail={"start": str(window.start), "end": str(window.end), "warnings": window_warnings},
        )
    )

    # ----------------------------------------------------
    # Step 2: Resolve Entity
    # ----------------------------------------------------
    if progress_callback:
        progress_callback(2, f"Resolving entity '{meeting_input.entity}'...")
    t0 = time.perf_counter()
    resolved_entity, candidates, resolve_status = await resolve_entity(
        meeting_input=meeting_input,
        search_client=search_client,
        llm_client=llm_client,
        model=settings.LLM_MODEL,
    )
    trace.append(
        TraceStep(
            name="2_resolve_entity",
            started_at=datetime.now(timezone.utc),
            duration_ms=int((time.perf_counter() - t0) * 1000),
            detail={
                "status": resolve_status,
                "canonical_name": resolved_entity.canonical_name if resolved_entity else None,
                "confidence": resolved_entity.confidence if resolved_entity else 0.0,
                "candidates_count": len(candidates),
            },
        )
    )

    if resolve_status == "needs_clarification":
        dummy_entity = ResolvedEntity(
            canonical_name=meeting_input.entity,
            entity_type="company",
            confidence=0.4,
        )
        empty_draft = LLMDraft(
            tldr=[], developments=[], talking_points=[], open_questions=[], risks=[], uncertainties=[], evidence_gaps=[]
        )
        briefing = Briefing(
            id=briefing_id,
            created_at=datetime.now(timezone.utc),
            input=meeting_input,
            entity=dummy_entity,
            window=window,
            draft=empty_draft,
            sources=[],
            stats={"duration_ms": int((time.perf_counter() - t_pipeline_start) * 1000)},
            trace=trace,
            status="needs_clarification",
            candidates=candidates,
            warnings=["Multiple possible candidates identified. Please choose one to clarify."],
        )
        save_briefing(briefing)
        return briefing

    assert resolved_entity is not None

    # ----------------------------------------------------
    # Step 3: Plan Queries
    # ----------------------------------------------------
    if progress_callback:
        progress_callback(3, "Planning targeted research queries...")
    t0 = time.perf_counter()
    planned_queries = plan_queries(
        entity=resolved_entity,
        window=window,
        meeting_input=meeting_input,
        max_queries=settings.MAX_QUERIES,
        search_depth=settings.SEARCH_DEPTH,
    )
    trace.append(
        TraceStep(
            name="3_plan_queries",
            started_at=datetime.now(timezone.utc),
            duration_ms=int((time.perf_counter() - t0) * 1000),
            detail={"queries_count": len(planned_queries)},
        )
    )

    # ----------------------------------------------------
    # Step 3b: Research via Tavily
    # ----------------------------------------------------
    if progress_callback:
        progress_callback(4, "Executing concurrent web research...")
    t0 = time.perf_counter()
    raw_items, research_trace = await execute_research(
        planned_queries=planned_queries,
        search_client=search_client,
        max_results_per_query=settings.MAX_RESULTS_PER_QUERY,
        search_depth=settings.SEARCH_DEPTH,
    )
    trace.append(
        TraceStep(
            name="3b_research",
            started_at=datetime.now(timezone.utc),
            duration_ms=int((time.perf_counter() - t0) * 1000),
            detail=research_trace,
        )
    )

    if not raw_items:
        empty_draft = LLMDraft(
            tldr=[], developments=[], talking_points=[], open_questions=[], risks=[], uncertainties=[], evidence_gaps=[]
        )
        briefing = Briefing(
            id=briefing_id,
            created_at=datetime.now(timezone.utc),
            input=meeting_input,
            entity=resolved_entity,
            window=window,
            draft=empty_draft,
            sources=[],
            stats={"duration_ms": int((time.perf_counter() - t_pipeline_start) * 1000)},
            trace=trace,
            status="insufficient_evidence",
            warnings=["No web search results could be retrieved for this entity."],
        )
        save_briefing(briefing)
        return briefing

    # ----------------------------------------------------
    # Step 4: Normalize, Filter, Cluster
    # ----------------------------------------------------
    if progress_callback:
        progress_callback(5, "Filtering date windows, deduping, and clustering sources...")
    t0 = time.perf_counter()
    sources, norm_trace = await normalize_sources(
        raw_items=raw_items,
        entity=resolved_entity,
        window=window,
        search_client=search_client,
        enable_extract=settings.ENABLE_EXTRACT,
        extract_top_n=settings.EXTRACT_TOP_N,
    )
    trace.append(
        TraceStep(
            name="4_normalize",
            started_at=datetime.now(timezone.utc),
            duration_ms=int((time.perf_counter() - t0) * 1000),
            detail=norm_trace,
        )
    )

    if not sources:
        empty_draft = LLMDraft(
            tldr=[], developments=[], talking_points=[], open_questions=[], risks=[], uncertainties=[], evidence_gaps=[]
        )
        briefing = Briefing(
            id=briefing_id,
            created_at=datetime.now(timezone.utc),
            input=meeting_input,
            entity=resolved_entity,
            window=window,
            draft=empty_draft,
            sources=[],
            stats={"duration_ms": int((time.perf_counter() - t_pipeline_start) * 1000)},
            trace=trace,
            status="insufficient_evidence",
            warnings=["All retrieved sources were outside the 30-day window or failed relevance filtering."],
        )
        save_briefing(briefing)
        return briefing

    # ----------------------------------------------------
    # Step 5: Synthesize Draft via LLM
    # ----------------------------------------------------
    if progress_callback:
        progress_callback(6, "Synthesizing structured grounded briefing via Bifrost...")
    t0 = time.perf_counter()
    draft, background, synth_usage = await synthesize_briefing(
        entity=resolved_entity,
        window=window,
        meeting_input=meeting_input,
        sources=sources,
        llm_client=llm_client,
        model=settings.LLM_MODEL,
    )
    trace.append(
        TraceStep(
            name="5_synthesize",
            started_at=datetime.now(timezone.utc),
            duration_ms=int((time.perf_counter() - t0) * 1000),
            detail={
                "developments_drafted": len(draft.developments),
                "tldr_drafted": len(draft.tldr),
                "usage": synth_usage,
            },
        )
    )

    # ----------------------------------------------------
    # Step 6: Verify Claims & Renumber Sources
    # ----------------------------------------------------
    if progress_callback:
        progress_callback(7, "Strict fact-checking, computing confidence, and formatting A4 one-pager...")
    t0 = time.perf_counter()
    verified_draft, renumbered_sources, verify_trace = await verify_briefing(
        draft=draft,
        sources=sources,
        window=window,
        llm_client=llm_client,
        verify_claims_with_llm=settings.VERIFY_CLAIMS,
        verify_model=settings.LLM_VERIFY_MODEL or settings.LLM_MODEL,
    )
    trace.append(
        TraceStep(
            name="6_verify",
            started_at=datetime.now(timezone.utc),
            duration_ms=int((time.perf_counter() - t0) * 1000),
            detail=verify_trace,
        )
    )

    # ----------------------------------------------------
    # Step 7: Enforce Budget & Build Briefing
    # ----------------------------------------------------
    total_pipeline_ms = int((time.perf_counter() - t_pipeline_start) * 1000)
    temp_briefing = Briefing(
        id=briefing_id,
        created_at=datetime.now(timezone.utc),
        input=meeting_input,
        entity=resolved_entity,
        window=window,
        draft=verified_draft,
        sources=renumbered_sources,
        background=background,
        stats={
            "duration_ms": total_pipeline_ms,
            "queries_executed": len(planned_queries),
            "sources_kept": len(renumbered_sources),
            "developments_count": len(verified_draft.developments),
            "model_used": settings.LLM_MODEL,
        },
        trace=trace,
        status="ok",
        warnings=window_warnings,
    )

    final_briefing, budget_stats = enforce_budget(temp_briefing)
    final_briefing.stats["word_count"] = budget_stats["final_word_count"]
    final_briefing.stats["trimmed_items"] = budget_stats["trimmed_items"]

    # Persist final briefing
    save_briefing(final_briefing)
    return final_briefing

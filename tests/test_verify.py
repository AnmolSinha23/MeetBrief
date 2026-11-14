"""Unit tests for briefing verification, confidence calculation, and source renumbering."""

import pytest
from datetime import date
from app.models import Bullet, Confidence, Development, LLMDraft, Question, Source, Window
from app.steps.verify import check_number_grounding, compute_confidence, verify_briefing

def create_sample_source(sid: str, cluster_id: int, is_primary: bool = False, in_window: bool = True, snippet: str = "text") -> Source:
    return Source(
        id=sid,
        url=f"https://example.com/{sid}",
        title=f"Source {sid}",
        domain="example.com",
        published_date=date(2026, 11, 5) if in_window else date(2026, 1, 1),
        snippet=snippet,
        score=0.9,
        is_primary=is_primary,
        cluster_id=cluster_id,
        in_window=in_window,
    )

def test_compute_confidence_rules():
    s1 = create_sample_source("S1", cluster_id=1, is_primary=False, in_window=True)
    s2 = create_sample_source("S2", cluster_id=2, is_primary=False, in_window=True)
    s3_primary = create_sample_source("S3", cluster_id=3, is_primary=True, in_window=True)
    s4_out_window = create_sample_source("S4", cluster_id=4, is_primary=False, in_window=False)

    # 1. Single cluster, not primary -> REPORTED
    assert compute_confidence([s1], passed_numbers=True) == Confidence.reported

    # 2. Two distinct clusters, in window -> VERIFIED
    assert compute_confidence([s1, s2], passed_numbers=True) == Confidence.verified

    # 3. Single cluster but primary -> VERIFIED
    assert compute_confidence([s3_primary], passed_numbers=True) == Confidence.verified

    # 4. Out of window -> UNVERIFIED
    assert compute_confidence([s4_out_window], passed_numbers=True) == Confidence.unverified

    # 5. Failed numbers check -> UNVERIFIED
    assert compute_confidence([s1, s2], passed_numbers=False) == Confidence.unverified

    # 6. Partial LLM verdict -> UNVERIFIED
    assert compute_confidence([s1, s2], passed_numbers=True, llm_verdict="partial") == Confidence.unverified

def test_number_grounding_check():
    s = create_sample_source("S1", cluster_id=1, snippet="Platform volume reached $350B, a 28% increase across 500 enterprise customers.")

    # Matching numbers
    ok1, _ = check_number_grounding("Payment volume hits $350B growing 28%", [s])
    assert ok1 is True

    # Invented number
    ok2, unconfirmed = check_number_grounding("Payment volume reached $999B with 75% margins", [s])
    assert ok2 is False
    assert any("999" in u for u in unconfirmed)

@pytest.mark.asyncio
async def test_verify_briefing_full():
    window = Window(start=date(2026, 10, 15), end=date(2026, 11, 14))

    s1 = create_sample_source("S1", cluster_id=1, is_primary=True, snippet="Stripe launches toolkit for AI agents.")
    s2 = create_sample_source("S2", cluster_id=2, is_primary=False, snippet="Stripe $350B volume in Q3 2026.")
    s3_unused = create_sample_source("S3", cluster_id=3, is_primary=False, snippet="Unused source.")

    sources = [s1, s2, s3_unused]

    draft = LLMDraft(
        tldr=[
            Bullet(text="Stripe launches agent toolkit.", source_ids=["S1"]),
            # Bullet with unknown source ID (should be dropped)
            Bullet(text="Unsupported claim.", source_ids=["S999"]),
        ],
        developments=[
            # Development with valid primary source -> VERIFIED
            Development(
                date=date(2026, 11, 5),
                category="product",
                headline="Stripe agent toolkit launched",
                detail="Enables AI agent payments.",
                why_it_matters="Expands into AI rails.",
                source_ids=["S1"],
            ),
            # Development with ungrounded number -> marked UNVERIFIED and note added to uncertainties
            Development(
                date=date(2026, 10, 29),
                category="financial",
                headline="Volume hits $999B in Q3",
                detail="Unverified revenue figure.",
                why_it_matters="Key metric.",
                source_ids=["S2"],
            ),
            # Development with NO valid source -> must be DROPPED
            Development(
                date=date(2026, 11, 1),
                category="product",
                headline="Completely hallucinated launch",
                detail="No sources cited anywhere.",
                why_it_matters="None.",
                source_ids=[],
            ),
        ],
        talking_points=[
            Bullet(text="Strategic inquiry into agent rails.", source_ids=["S1"])
        ],
        open_questions=[
            Question(text="What is the fee schedule?", rationale="Cost inquiry.", source_ids=["S1"])
        ],
        risks=[],
        uncertainties=[],
        evidence_gaps=[],
    )

    verified_draft, renumbered_sources, stats = await verify_briefing(
        draft=draft,
        sources=sources,
        window=window,
        verify_claims_with_llm=False,
    )

    # 1. Unknown source dropped and hallucinated development dropped
    assert stats["dropped_claims"] >= 2
    assert len(verified_draft.tldr) == 1
    assert len(verified_draft.developments) == 2

    # 2. First development is VERIFIED (primary source)
    assert verified_draft.developments[0].confidence == Confidence.verified

    # 3. Second development has unconfirmed number $999B -> UNVERIFIED
    assert verified_draft.developments[1].confidence == Confidence.unverified
    assert any("999" in u for u in verified_draft.uncertainties)

    # 4. Sources renumbered: S3 (unused) was dropped, only cited sources kept and renumbered S1, S2
    assert len(renumbered_sources) == 2
    assert [s.id for s in renumbered_sources] == ["S1", "S2"]
    assert verified_draft.developments[0].source_ids == ["S1"]
    assert verified_draft.developments[1].source_ids == ["S2"]

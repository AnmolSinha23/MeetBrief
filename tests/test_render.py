"""Tests for A4 budget enforcement and Jinja2 rendering."""

import pytest
from datetime import date, datetime, timezone
from app.models import (
    Briefing,
    Bullet,
    Candidate,
    Confidence,
    Development,
    EntityType,
    LLMDraft,
    MeetingInput,
    MeetingType,
    Question,
    ResolvedEntity,
    Source,
    Window,
)
from app.steps.render import count_briefing_words, enforce_budget, render_html, render_markdown

def create_dummy_briefing() -> Briefing:
    window = Window(start=date(2026, 10, 15), end=date(2026, 11, 14))
    entity = ResolvedEntity(
        canonical_name="Stripe",
        entity_type="company",
        aliases=["Stripe Payments"],
        official_domain="stripe.com",
        description="Global financial infrastructure and payment processing platform for online merchants.",
        confidence=0.98,
    )
    meeting_input = MeetingInput(
        entity="Stripe",
        meeting_time=datetime(2026, 11, 15, 10, 0, tzinfo=timezone.utc),
        meeting_type=MeetingType.investor,
    )

    s1 = Source(
        id="S1",
        url="https://stripe.com/newsroom/press/agentic-toolkit",
        title="Stripe Introduces Agentic Payments Toolkit",
        domain="stripe.com",
        published_date=date(2026, 11, 5),
        snippet="Platform tools allowing autonomous AI agents to initiate secure transactions.",
        score=0.95,
        is_primary=True,
        cluster_id=1,
        in_window=True,
    )
    s2 = Source(
        id="S2",
        url="https://wsj.com/stripe-q3-volume",
        title="Stripe Q3 2026 Platform Volume Hits $350B",
        domain="wsj.com",
        published_date=date(2026, 10, 29),
        snippet="Platform volume reached $350B up 28% year over year.",
        score=0.90,
        is_primary=False,
        cluster_id=2,
        in_window=True,
    )

    draft = LLMDraft(
        tldr=[
            Bullet(text="Stripe launched an Agentic Payments Toolkit.", source_ids=["S1"], confidence=Confidence.verified),
            Bullet(text="Reported strong Q3 volume reaching $350B.", source_ids=["S2"], confidence=Confidence.reported),
        ],
        developments=[
            Development(
                date=date(2026, 11, 5),
                category="product",
                headline="Launches Agentic Payments Toolkit",
                detail="Enables autonomous software agents to transact with guardrails and audit logs.",
                why_it_matters="Directly captures payment volume from AI agents.",
                source_ids=["S1"],
                confidence=Confidence.verified,
            ),
            Development(
                date=date(2026, 10, 29),
                category="financial",
                headline="Q3 volume hits $350B up 28%",
                detail="Strong quarterly volume acceleration driven by software subscriptions.",
                why_it_matters="Shows revenue momentum.",
                source_ids=["S2"],
                confidence=Confidence.reported,
            ),
        ],
        talking_points=[
            Bullet(text="Explore agent payment primitives.", source_ids=["S1"])
        ],
        open_questions=[
            Question(text="What are enterprise liability guardrails?", rationale="Key adoption blocker.", source_ids=["S1"])
        ],
        risks=[
            Bullet(text="Regulatory oversight on agentic commerce.", source_ids=["S1"])
        ],
        uncertainties=["Pricing schedule unconfirmed."],
        evidence_gaps=["No M&A announcements in window."],
    )

    return Briefing(
        id="briefing_test",
        created_at=datetime.now(timezone.utc),
        input=meeting_input,
        entity=entity,
        window=window,
        draft=draft,
        sources=[s1, s2],
        background="Stripe powers online payments.",
        stats={},
        trace=[],
        status="ok",
    )

def test_enforce_budget_word_count_and_caps():
    briefing = create_dummy_briefing()

    # Add extra developments to exceed count
    for i in range(10):
        briefing.draft.developments.append(
            Development(
                date=date(2026, 10, 20),
                category="other",
                headline=f"Extra development #{i} with very long filler text to test budget limits",
                detail="More details and extra words to test word budget trimming order.",
                why_it_matters="Filler matters.",
                source_ids=["S1"],
                confidence=Confidence.unverified,
            )
        )

    assert len(briefing.draft.developments) == 12

    constrained_briefing, stats = enforce_budget(briefing, max_words=300)

    # Hard count cap <= 6
    assert len(constrained_briefing.draft.developments) <= 6
    assert stats["under_budget"] is True
    assert stats["final_word_count"] <= 300
    assert len(stats["trimmed_items"]) > 0

def test_render_html_and_markdown():
    briefing = create_dummy_briefing()

    html = render_html(briefing)
    assert "Stripe" in html
    assert "Agentic Payments Toolkit" in html
    assert "badge-VERIFIED" in html
    assert "[S1]" in html
    assert "stripe.com" in html

    md = render_markdown(briefing)
    assert "# Briefing: Stripe (Company)" in md
    assert "Agentic Payments Toolkit" in md
    assert "[S1]" in md
    assert "https://stripe.com/newsroom/press/agentic-toolkit" in md

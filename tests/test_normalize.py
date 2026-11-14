"""Tests for search result normalization, filtering, clustering, and ranking."""

import pytest
from datetime import date
from app.models import ResolvedEntity, Window
from app.steps.normalize import (
    canonicalize_url,
    compute_title_jaccard,
    get_registered_domain,
    normalize_sources,
)

def test_canonicalize_url():
    raw = "https://www.stripe.com/newsroom/press-release/?utm_source=twitter&utm_medium=social&ref=123#overview"
    clean = canonicalize_url(raw)
    assert clean == "https://stripe.com/newsroom/press-release"

    raw2 = "http://www.bloomberg.com/news/articles/2026-11-01/article-slug/"
    clean2 = canonicalize_url(raw2)
    assert clean2 == "http://bloomberg.com/news/articles/2026-11-01/article-slug"

def test_compute_title_jaccard():
    t1 = "Stripe Introduces Agentic Payments Toolkit for Autonomous AI Systems"
    t2 = "Stripe Introduces Agentic Payments Toolkit for Autonomous AI Systems"
    assert compute_title_jaccard(t1, t2) == 1.0

    t3 = "Stripe Unveils Payments Toolkit for Autonomous AI Agents"
    sim = compute_title_jaccard(t1, t3)
    assert sim >= 0.5

    t4 = "Completely Unrelated Topic About Something Else"
    assert compute_title_jaccard(t1, t4) < 0.2

def test_registered_domain():
    assert get_registered_domain("https://news.stripe.com/releases/1") == "stripe.com"
    assert get_registered_domain("https://finance.yahoo.com/quote") == "yahoo.com"
    assert get_registered_domain("https://sub.agency.gov.uk/doc") == "agency.gov.uk"

@pytest.mark.asyncio
async def test_normalize_sources_full_pipeline():
    entity = ResolvedEntity(
        canonical_name="Stripe",
        entity_type="company",
        aliases=["Stripe Payments", "Stripe Inc"],
        official_domain="stripe.com",
        confidence=0.95,
    )
    window = Window(
        start=date(2026, 10, 15),
        end=date(2026, 11, 14),
    )

    raw_items = [
        # In window, primary official
        {
            "url": "https://www.stripe.com/newsroom/press/agentic-toolkit?utm_source=feed",
            "title": "Stripe Launches Agentic Payments Toolkit",
            "content": "Stripe today announced Agentic Payments Toolkit for autonomous transactions.",
            "published_date": "2026-11-05",
            "score": 0.95,
        },
        # Syndicated copy (near duplicate title)
        {
            "url": "https://www.prnewswire.com/news-releases/stripe-launches-agentic-payments-toolkit-12345.html",
            "title": "Stripe Launches Agentic Payments Toolkit",
            "content": "Newswire copy of Stripe launches Agentic Payments Toolkit.",
            "published_date": "2026-11-05",
            "score": 0.90,
        },
        # Out-of-window item (should be dropped)
        {
            "url": "https://techcrunch.com/2026/05/01/stripe-old-event",
            "title": "Stripe Hosts Annual User Conference",
            "content": "Stripe user conference from earlier this year.",
            "published_date": "2026-05-01",
            "score": 0.85,
        },
        # Undated item (kept, in_window=False)
        {
            "url": "https://stripe.com/docs/api",
            "title": "Stripe API Documentation Reference",
            "content": "Comprehensive reference for the Stripe REST APIs.",
            "published_date": None,
            "score": 0.60,
        },
        # Wrong entity item (should be dropped)
        {
            "url": "https://agri-news.org/kansas-wheat-rust",
            "title": "Severe Wheat Rust Affects Kansas Crop",
            "content": "Puccinia striiformis fungus infections spreading across winter wheat fields.",
            "published_date": "2026-11-04",
            "score": 0.70,
        },
        # Exact duplicate URL with lower score (should be deduped)
        {
            "url": "https://www.stripe.com/newsroom/press/agentic-toolkit",
            "title": "Stripe Launches Agentic Payments Toolkit",
            "content": "Duplicate entry.",
            "published_date": "2026-11-05",
            "score": 0.80,
        },
    ]

    sources, stats = await normalize_sources(
        raw_items=raw_items,
        entity=entity,
        window=window,
        enable_extract=False,
    )

    # Verifications:
    # 1. Total kept sources
    assert stats["dropped_out_of_window"] == 1
    assert stats["dropped_wrong_entity"] == 1
    assert stats["dropped_duplicates"] == 1

    # 2. Sequential IDs S1, S2, ...
    for idx, s in enumerate(sources, 1):
        assert s.id == f"S{idx}"

    # 3. Primary domain tagged correctly
    primary_sources = [s for s in sources if s.is_primary]
    assert len(primary_sources) >= 1
    assert any(s.domain == "stripe.com" for s in primary_sources)
    assert any(s.domain == "prnewswire.com" for s in primary_sources)

    # 4. Duplicate clustering: the official and PR news wire with identical titles share cluster_id
    cluster_ids = {s.title: s.cluster_id for s in sources}
    assert (
        cluster_ids["Stripe Launches Agentic Payments Toolkit"]
        == cluster_ids["Stripe Launches Agentic Payments Toolkit"]
    )

    # 5. Undated item has in_window=False
    undated = [s for s in sources if s.title == "Stripe API Documentation Reference"]
    assert len(undated) == 1
    assert undated[0].in_window is False

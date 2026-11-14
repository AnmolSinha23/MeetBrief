"""End-to-end pipeline tests using mock clients covering all response statuses."""

import pytest
from datetime import datetime, timezone, timedelta
from app.models import MeetingInput, MeetingType, EntityType
from app.pipeline import run_pipeline
from app.clients.search import MockSearchClient
from app.clients.llm import MockLLMClient

@pytest.mark.asyncio
async def test_pipeline_status_ok():
    inp = MeetingInput(
        entity="Stripe",
        entity_type=EntityType.company,
        meeting_time=datetime.now(timezone.utc) + timedelta(days=1),
        meeting_type=MeetingType.investor,
        user_context="Checking for latest announcements before investment pitch.",
    )

    search_client = MockSearchClient()
    llm_client = MockLLMClient()

    briefing = await run_pipeline(
        meeting_input=inp,
        search_client=search_client,
        llm_client=llm_client,
    )

    assert briefing.status == "ok"
    assert briefing.entity.canonical_name == "Stripe"
    assert len(briefing.draft.developments) >= 1
    assert len(briefing.sources) >= 1

    # Invariants
    for dev in briefing.draft.developments:
        assert len(dev.source_ids) >= 1
        assert dev.confidence in ("VERIFIED", "REPORTED", "UNVERIFIED")

    assert len(briefing.trace) >= 6

@pytest.mark.asyncio
async def test_pipeline_status_needs_clarification():
    inp = MeetingInput(
        entity="Alex Smith",
        entity_type=EntityType.person,
        meeting_time=datetime.now(timezone.utc) + timedelta(days=2),
        hint=None,  # No hint with ambiguous entity
    )

    search_client = MockSearchClient()
    llm_client = MockLLMClient()

    briefing = await run_pipeline(
        meeting_input=inp,
        search_client=search_client,
        llm_client=llm_client,
    )

    assert briefing.status == "needs_clarification"
    assert len(briefing.candidates) >= 2

@pytest.mark.asyncio
async def test_pipeline_status_insufficient_evidence():
    inp = MeetingInput(
        entity="NonexistentEntityXYZ",
        meeting_time=datetime.now(timezone.utc) + timedelta(days=1),
    )

    class EmptySearchClient(MockSearchClient):
        async def search(self, *args, **kwargs):
            return {"results": []}

    search_client = EmptySearchClient()
    llm_client = MockLLMClient()

    briefing = await run_pipeline(
        meeting_input=inp,
        search_client=search_client,
        llm_client=llm_client,
    )

    assert briefing.status == "insufficient_evidence"
    assert len(briefing.draft.developments) == 0

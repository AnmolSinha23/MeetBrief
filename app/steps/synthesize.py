"""Briefing synthesis step using Bifrost LLM client."""

import json
import logging
from typing import List, Optional, Tuple
from pydantic import ValidationError

from app.clients.llm import LLMClient
from app.models import LLMDraft, MeetingInput, ResolvedEntity, Source, Window
from app.prompts import SYNTHESIS_SYSTEM_PROMPT, SYNTHESIS_USER_PROMPT

logger = logging.getLogger(__name__)

def format_sources_block(sources: List[Source]) -> str:
    """Formats the sources list into clearly delimited citation blocks."""
    blocks = []
    for s in sources:
        pub = s.published_date.strftime("%Y-%m-%d") if s.published_date else "unknown"
        prim = "yes" if s.is_primary else "no"
        block = f"[{s.id}] title: {s.title} | domain: {s.domain} | published: {pub} | primary: {prim}\ntext: {s.snippet}"
        blocks.append(block)
    return "\n---\n".join(blocks)

async def synthesize_briefing(
    entity: ResolvedEntity,
    window: Window,
    meeting_input: MeetingInput,
    sources: List[Source],
    llm_client: LLMClient,
    model: Optional[str] = None,
) -> Tuple[LLMDraft, str, dict]:
    """Synthesizes the first draft of the briefing from sources using the LLM.

    Returns:
        Tuple of (LLMDraft, background_sentence, usage_stats).
    """
    sources_block = format_sources_block(sources)
    schema_str = json.dumps(LLMDraft.model_json_schema(), indent=2)

    user_prompt = SYNTHESIS_USER_PROMPT.format(
        canonical_name=entity.canonical_name,
        entity_type=entity.entity_type,
        affiliation=entity.affiliation or "none",
        meeting_type=meeting_input.meeting_type.value,
        meeting_date=meeting_input.meeting_time.strftime("%Y-%m-%d %H:%M %Z"),
        start=window.start.strftime("%Y-%m-%d"),
        end=window.end.strftime("%Y-%m-%d"),
        user_context=meeting_input.user_context or "not provided",
        json_schema=schema_str,
        sources_block=sources_block,
    )

    draft: Optional[LLMDraft] = None
    last_err: Optional[Exception] = None
    total_usage: dict = {}

    for attempt in range(2):
        try:
            curr_prompt = user_prompt
            if attempt > 0 and last_err:
                curr_prompt += f"\n\nPREVIOUS ATTEMPT VALIDATION ERROR:\n{str(last_err)}\nPlease fix the JSON to conform strictly to the schema."

            raw_dict, usage = await llm_client.json_completion(
                system_prompt=SYNTHESIS_SYSTEM_PROMPT,
                user_prompt=curr_prompt,
                model=model,
                temperature=0.2,
            )
            total_usage = usage
            draft = LLMDraft.model_validate(raw_dict)
            break
        except (ValidationError, ValueError, Exception) as e:
            logger.warning(f"Synthesis attempt {attempt+1} failed validation: {e}")
            last_err = e

    if draft is None:
        raise RuntimeError(f"Briefing synthesis failed schema validation after repair attempt: {last_err}")

    # Generate or extract 1-2 neutral background sentences
    background = entity.description.strip()
    if not background:
        # Fall back to first cited or official source title
        for s in sources:
            if s.is_primary or s.category == "background":
                background = f"{entity.canonical_name} is a {entity.entity_type} ({s.title}). [{s.id}]"
                break
        if not background:
            background = f"{entity.canonical_name} ({entity.entity_type})."

    return draft, background, total_usage

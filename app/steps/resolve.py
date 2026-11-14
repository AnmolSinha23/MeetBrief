"""Entity resolution and disambiguation step."""

import logging
from typing import List, Optional, Tuple
from app.models import Candidate, EntityType, MeetingInput, ResolvedEntity
from app.clients.search import SearchClient
from app.clients.llm import LLMClient
from app.prompts import RESOLVE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

async def resolve_entity(
    meeting_input: MeetingInput,
    search_client: SearchClient,
    llm_client: LLMClient,
    model: Optional[str] = None,
) -> Tuple[Optional[ResolvedEntity], List[Candidate], str]:
    """Resolves and disambiguates the entity using search + LLM.

    Returns:
        Tuple of (resolved_entity, candidates_list, status_string).
        Status is "ok" or "needs_clarification".
    """
    search_query = f"{meeting_input.entity} {meeting_input.hint or ''}".strip()
    search_res = await search_client.search(
        query=search_query,
        topic="general",
        max_results=5,
        search_depth="basic",
    )

    results = search_res.get("results", [])
    if not results:
        # Fallback to direct name if search returned empty
        resolved = ResolvedEntity(
            canonical_name=meeting_input.entity.strip(),
            entity_type="person" if meeting_input.entity_type == EntityType.person else "company",
            aliases=[meeting_input.entity.strip()],
            description="Entity provided directly by user.",
            confidence=0.7,
        )
        return resolved, [], "ok"

    user_prompt = f"""Target Entity: {meeting_input.entity}
User Hint: {meeting_input.hint or 'None'}
Requested Type: {meeting_input.entity_type.value}

<SEARCH_RESULTS>
"""
    for idx, r in enumerate(results, 1):
        user_prompt += f"[{idx}] {r.get('title', '')} | {r.get('url', '')}\n{r.get('content', '')[:300]}\n---\n"
    user_prompt += "</SEARCH_RESULTS>\nIdentify the entity now."

    try:
        data, _ = await llm_client.json_completion(
            system_prompt=RESOLVE_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            model=model,
            temperature=0.1,
        )
    except Exception as e:
        logger.warning(f"Entity resolution LLM call failed: {e}. Falling back to default.")
        data = {
            "candidates": [
                {
                    "canonical_name": meeting_input.entity,
                    "entity_type": "person" if meeting_input.entity_type == EntityType.person else "company",
                    "aliases": [meeting_input.entity],
                    "official_domain": None,
                    "affiliation": None,
                    "description": "",
                    "confidence": 0.8,
                    "label": meeting_input.entity,
                }
            ]
        }

    raw_candidates = data.get("candidates", [])
    if not raw_candidates:
        resolved = ResolvedEntity(
            canonical_name=meeting_input.entity,
            entity_type="person" if meeting_input.entity_type == EntityType.person else "company",
            aliases=[meeting_input.entity],
            confidence=0.7,
        )
        return resolved, [], "ok"

    top = raw_candidates[0]
    # Respect user entity_type if explicitly set
    cand_type = top.get("entity_type", "company")
    if meeting_input.entity_type == EntityType.person:
        cand_type = "person"
    elif meeting_input.entity_type == EntityType.company:
        cand_type = "company"

    # Ambiguity check: confidence < 0.6 and no hint provided and multiple candidates
    confidence = float(top.get("confidence", 0.7))
    if confidence < 0.6 and not meeting_input.hint and len(raw_candidates) > 1:
        candidates = [
            Candidate(
                label=c.get("label", c.get("canonical_name", "")),
                hint=c.get("affiliation") or c.get("official_domain") or c.get("description", "")[:60],
            )
            for c in raw_candidates[:4]
        ]
        return None, candidates, "needs_clarification"

    # Ensure aliases include canonical name and max 5
    aliases = top.get("aliases", [])
    canon_name = top.get("canonical_name", meeting_input.entity).strip()
    if canon_name not in aliases:
        aliases.insert(0, canon_name)
    aliases = list(dict.fromkeys(aliases))[:5]

    resolved = ResolvedEntity(
        canonical_name=canon_name,
        entity_type=cand_type,
        aliases=aliases,
        official_domain=top.get("official_domain"),
        affiliation=top.get("affiliation"),
        description=(top.get("description") or "")[:200],
        confidence=confidence,
    )
    return resolved, [], "ok"

"""Verification, grounding checks, confidence computation, and source renumbering."""

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from app.clients.llm import LLMClient
from app.models import Bullet, Confidence, Development, LLMDraft, Question, Source, Window
from app.prompts import VERIFICATION_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

def extract_numeric_tokens(text: str) -> List[str]:
    """Extracts numeric figures, currency amounts, and percentages from text."""
    # Match numbers like $350B, 28%, 500, 2026, 1.5M, etc.
    pattern = r"\b(?:\$|€|£)?\d+(?:,\d{3})*(?:\.\d+)?(?:%|[kKmMbBtT])?\b"
    raw_tokens = re.findall(pattern, text)
    cleaned = []
    for tok in raw_tokens:
        core = re.sub(r"[^\d.]", "", tok)
        # Only check substantial numbers, ignore standalone single digits 0-9
        if core and (len(core) > 1 or float(core) > 9 or "%" in tok or "$" in tok):
            cleaned.append(tok)
    return cleaned

def check_number_grounding(claim_text: str, cited_sources: List[Source]) -> Tuple[bool, List[str]]:
    """Checks whether every number in the claim appears in the cited source text."""
    claim_nums = extract_numeric_tokens(claim_text)
    if not claim_nums:
        return True, []

    combined_source_text = " ".join(
        (s.title + " " + s.snippet).replace(",", "") for s in cited_sources
    ).lower()

    unconfirmed = []
    for num in claim_nums:
        # Extract digits core
        digits = re.sub(r"[^\d]", "", num)
        if digits and digits not in combined_source_text:
            unconfirmed.append(num)

    if unconfirmed:
        return False, unconfirmed
    return True, []

def compute_confidence(
    cited_sources: List[Source],
    passed_numbers: bool,
    llm_verdict: str = "supported",
) -> Confidence:
    """Computes confidence strictly in code based on dates, clustering, and verification."""
    if not cited_sources:
        return Confidence.unverified

    if not passed_numbers or llm_verdict == "partial":
        return Confidence.unverified

    if llm_verdict == "unsupported":
        return Confidence.unverified

    all_in_window = all(s.in_window for s in cited_sources)
    if not all_in_window:
        return Confidence.unverified

    has_primary = any(s.is_primary for s in cited_sources)
    distinct_clusters = len({s.cluster_id for s in cited_sources})

    if has_primary or distinct_clusters >= 2:
        return Confidence.verified
    elif distinct_clusters == 1:
        return Confidence.reported

    return Confidence.unverified

async def verify_briefing(
    draft: LLMDraft,
    sources: List[Source],
    window: Window,
    llm_client: Optional[LLMClient] = None,
    verify_claims_with_llm: bool = True,
    verify_model: Optional[str] = None,
) -> Tuple[LLMDraft, List[Source], Dict[str, Any]]:
    """Runs deterministic checks, optional LLM grounding pass, computes confidence, and renumbers sources.

    Returns:
        Tuple of (verified_LLMDraft, renumbered_sources, trace_stats).
    """
    source_map: Dict[str, Source] = {s.id: s for s in sources}
    dropped_claims = 0
    dropped_unknown_sources = 0
    downgraded_claims = 0

    # 1. Deterministic Clean-up: filter out unknown source IDs
    def sanitize_source_ids(ids: List[str]) -> List[str]:
        nonlocal dropped_unknown_sources
        valid = [sid for sid in ids if sid in source_map]
        dropped_unknown_sources += len(ids) - len(valid)
        return valid

    for b in draft.tldr:
        b.source_ids = sanitize_source_ids(b.source_ids)
    for dev in draft.developments:
        dev.source_ids = sanitize_source_ids(dev.source_ids)
    for b in draft.risks:
        b.source_ids = sanitize_source_ids(b.source_ids)
    for q in draft.open_questions:
        q.source_ids = sanitize_source_ids(q.source_ids)
    for tp in draft.talking_points:
        tp.source_ids = sanitize_source_ids(tp.source_ids)

    # Drop Developments and TL;DR bullets with NO valid sources
    original_dev_count = len(draft.developments)
    draft.developments = [d for d in draft.developments if len(d.source_ids) > 0]
    dropped_claims += original_dev_count - len(draft.developments)

    original_tldr_count = len(draft.tldr)
    draft.tldr = [b for b in draft.tldr if len(b.source_ids) > 0]
    dropped_claims += original_tldr_count - len(draft.tldr)

    # 2. Date alignment for developments
    for dev in draft.developments:
        cited = [source_map[sid] for sid in dev.source_ids]
        if dev.date is None or dev.date < window.start or dev.date > window.end:
            # Set to cited source date
            dated_sources = [s.published_date for s in cited if s.published_date]
            if dated_sources:
                dev.date = dated_sources[0]
            else:
                dev.date = None

    # 3. LLM Grounding Check (Phase 6b) if enabled
    llm_verdicts: Dict[str, Tuple[str, str]] = {}
    if verify_claims_with_llm and llm_client and draft.developments:
        claims_to_check = []
        for idx, dev in enumerate(draft.developments):
            cited = [source_map[sid] for sid in dev.source_ids]
            cited_texts = "\n".join(f"[{s.id}] {s.title}: {s.snippet}" for s in cited)
            claims_to_check.append(
                {
                    "claim_id": f"dev_{idx}",
                    "claim_text": f"{dev.headline}. {dev.detail}",
                    "sources": cited_texts,
                }
            )

        verification_user_prompt = "Judge the following claims against their cited sources:\n"
        for c in claims_to_check:
            verification_user_prompt += (
                f"\n--- Claim ID: {c['claim_id']} ---\nClaim: {c['claim_text']}\nCited Text:\n{c['sources']}\n"
            )

        try:
            v_res, _ = await llm_client.json_completion(
                system_prompt=VERIFICATION_SYSTEM_PROMPT,
                user_prompt=verification_user_prompt,
                model=verify_model,
                temperature=0.0,
            )
            raw_verdicts = v_res.get("verdicts", [])
            for item in raw_verdicts:
                cid = item.get("claim_id", "")
                verdict = item.get("verdict", "supported").lower()
                note = item.get("note", "")
                llm_verdicts[cid] = (verdict, note)
        except Exception as e:
            logger.warning(f"LLM verification pass failed: {e}. Falling back to deterministic.")

    # 4. Filter unsupported claims and compute confidence
    kept_developments: List[Development] = []
    for idx, dev in enumerate(draft.developments):
        cid = f"dev_{idx}"
        v_status, v_note = llm_verdicts.get(cid, ("supported", ""))

        if v_status == "unsupported":
            dropped_claims += 1
            continue

        cited = [source_map[sid] for sid in dev.source_ids]
        num_ok, unconf_nums = check_number_grounding(f"{dev.headline} {dev.detail}", cited)
        if not num_ok:
            downgraded_claims += 1
            for un_num in unconf_nums:
                note = f"Figure '{un_num}' in '{dev.headline[:30]}' not confirmed in cited source"
                if note not in draft.uncertainties:
                    draft.uncertainties.append(note)

        if v_status == "partial":
            downgraded_claims += 1
            note = f"Claim '{dev.headline[:30]}' partially verified: {v_note}"
            if note not in draft.uncertainties:
                draft.uncertainties.append(note)

        dev.confidence = compute_confidence(cited, passed_numbers=num_ok, llm_verdict=v_status)
        kept_developments.append(dev)

    draft.developments = kept_developments

    # Compute confidence for TL;DR and Risks
    for b in draft.tldr:
        cited = [source_map[sid] for sid in b.source_ids]
        num_ok, _ = check_number_grounding(b.text, cited)
        b.confidence = compute_confidence(cited, passed_numbers=num_ok)

    for b in draft.risks:
        cited = [source_map[sid] for sid in b.source_ids]
        num_ok, _ = check_number_grounding(b.text, cited)
        b.confidence = compute_confidence(cited, passed_numbers=num_ok)

    # 5. Renumber sources (6c): keep only cited sources, renumber S1..Sn
    used_source_ids: Set[str] = set()
    for b in draft.tldr:
        used_source_ids.update(b.source_ids)
    for dev in draft.developments:
        used_source_ids.update(dev.source_ids)
    for b in draft.risks:
        used_source_ids.update(b.source_ids)
    for q in draft.open_questions:
        used_source_ids.update(q.source_ids)
    for tp in draft.talking_points:
        used_source_ids.update(tp.source_ids)

    # Order sources by first appearance
    ordered_used_ids: List[str] = []
    for sid in [f"S{i}" for i in range(1, len(sources) + 1)]:
        if sid in used_source_ids and sid not in ordered_used_ids:
            ordered_used_ids.append(sid)

    # Create ID mapping old -> new
    id_map: Dict[str, str] = {old_id: f"S{new_idx}" for new_idx, old_id in enumerate(ordered_used_ids, 1)}

    # Re-assign IDs in all claims
    def remap(ids: List[str]) -> List[str]:
        return [id_map[sid] for sid in ids if sid in id_map]

    for b in draft.tldr:
        b.source_ids = remap(b.source_ids)
    for dev in draft.developments:
        dev.source_ids = remap(dev.source_ids)
    for b in draft.risks:
        b.source_ids = remap(b.source_ids)
    for q in draft.open_questions:
        q.source_ids = remap(q.source_ids)
    for tp in draft.talking_points:
        tp.source_ids = remap(tp.source_ids)

    # Create new list of renumbered Sources
    renumbered_sources: List[Source] = []
    for old_id in ordered_used_ids:
        src = source_map[old_id]
        src_copy = src.model_copy()
        src_copy.id = id_map[old_id]
        renumbered_sources.append(src_copy)

    trace_stats = {
        "dropped_claims": dropped_claims,
        "dropped_unknown_sources": dropped_unknown_sources,
        "downgraded_claims": downgraded_claims,
        "cited_sources_count": len(renumbered_sources),
    }

    return draft, renumbered_sources, trace_stats

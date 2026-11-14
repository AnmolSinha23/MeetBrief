"""Budget enforcement and Jinja2 rendering for HTML and Markdown."""

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple
from jinja2 import Environment, FileSystemLoader

from app.models import Briefing, Confidence, Development

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=True,
    trim_blocks=True,
    lstrip_blocks=True,
)

def count_briefing_words(briefing: Briefing) -> int:
    """Counts non-source words across all sections of the briefing."""
    text_parts = [
        briefing.entity.canonical_name,
        briefing.background,
    ]
    for b in briefing.draft.tldr:
        text_parts.append(b.text)
    for dev in briefing.draft.developments:
        text_parts.extend([dev.headline, dev.detail, dev.why_it_matters])
    for tp in briefing.draft.talking_points:
        text_parts.append(tp.text)
    for q in briefing.draft.open_questions:
        text_parts.extend([q.text, q.rationale])
    for r in briefing.draft.risks:
        text_parts.append(r.text)
    text_parts.extend(briefing.draft.uncertainties)
    text_parts.extend(briefing.draft.evidence_gaps)

    full_text = " ".join(t for t in text_parts if t)
    return len(full_text.split())

def enforce_budget(briefing: Briefing, max_words: int = 520) -> Tuple[Briefing, Dict[str, Any]]:
    """Enforces hard item counts and word limits to guarantee a clean 1-page A4 document."""
    trimmed_items: List[str] = []

    # 1. Hard count caps
    if len(briefing.draft.tldr) > 3:
        trimmed_items.append(f"Trimmed {len(briefing.draft.tldr) - 3} TL;DR bullets")
        briefing.draft.tldr = briefing.draft.tldr[:3]

    if len(briefing.draft.developments) > 6:
        trimmed_items.append(f"Trimmed {len(briefing.draft.developments) - 6} developments (count cap)")
        briefing.draft.developments = briefing.draft.developments[:6]

    if len(briefing.draft.talking_points) > 3:
        trimmed_items.append(f"Trimmed {len(briefing.draft.talking_points) - 3} talking points")
        briefing.draft.talking_points = briefing.draft.talking_points[:3]

    if len(briefing.draft.open_questions) > 6:
        trimmed_items.append(f"Trimmed {len(briefing.draft.open_questions) - 6} open questions")
        briefing.draft.open_questions = briefing.draft.open_questions[:6]

    if len(briefing.draft.risks) > 3:
        trimmed_items.append(f"Trimmed {len(briefing.draft.risks) - 3} risks")
        briefing.draft.risks = briefing.draft.risks[:3]

    if len(briefing.draft.uncertainties) > 3:
        briefing.draft.uncertainties = briefing.draft.uncertainties[:3]

    if len(briefing.draft.evidence_gaps) > 2:
        briefing.draft.evidence_gaps = briefing.draft.evidence_gaps[:2]

    # 2. Sort developments: newest first, VERIFIED before REPORTED before UNVERIFIED when dates tie
    confidence_weight = {
        Confidence.verified: 3,
        Confidence.reported: 2,
        Confidence.unverified: 1,
    }

    def dev_sort_key(dev: Development):
        dev_date = dev.date or date.min
        conf = confidence_weight.get(dev.confidence, 0)
        return (dev_date, conf)

    briefing.draft.developments.sort(key=dev_sort_key, reverse=True)

    # 3. Word Budget Enforcement (max_words <= 520)
    current_words = count_briefing_words(briefing)

    # Trimming order: lowest-priority developments (UNVERIFIED first, then oldest), risks, talking points, evidence gaps
    while current_words > max_words and len(briefing.draft.developments) > 2:
        # Find lowest priority development
        lowest_idx = -1
        # First try to drop unverified
        for idx in range(len(briefing.draft.developments) - 1, -1, -1):
            if briefing.draft.developments[idx].confidence == Confidence.unverified:
                lowest_idx = idx
                break
        if lowest_idx == -1:
            lowest_idx = len(briefing.draft.developments) - 1

        dropped_dev = briefing.draft.developments.pop(lowest_idx)
        trimmed_items.append(f"Trimmed development: '{dropped_dev.headline[:30]}' to stay under word budget")
        current_words = count_briefing_words(briefing)

    while current_words > max_words and len(briefing.draft.risks) > 1:
        dropped_risk = briefing.draft.risks.pop()
        trimmed_items.append(f"Trimmed risk: '{dropped_risk.text[:30]}' to meet budget")
        current_words = count_briefing_words(briefing)

    while current_words > max_words and len(briefing.draft.talking_points) > 1:
        dropped_tp = briefing.draft.talking_points.pop()
        trimmed_items.append(f"Trimmed talking point: '{dropped_tp.text[:30]}' to meet budget")
        current_words = count_briefing_words(briefing)

    while current_words > max_words and len(briefing.draft.evidence_gaps) > 0:
        briefing.draft.evidence_gaps.pop()
        current_words = count_briefing_words(briefing)

    budget_stats = {
        "final_word_count": current_words,
        "trimmed_items": trimmed_items,
        "under_budget": current_words <= max_words,
    }

    return briefing, budget_stats

def format_meeting_display(dt: datetime, tz_name: str) -> str:
    """Formats datetime nicely for briefing header."""
    return dt.strftime("%d %b %Y at %H:%M")

def render_html(briefing: Briefing) -> str:
    """Renders briefing to clean printable A4 HTML."""
    template = jinja_env.get_template("briefing.html.j2")
    formatted_meeting = format_meeting_display(briefing.input.meeting_time, briefing.input.timezone)
    return template.render(
        briefing=briefing,
        meeting_formatted=formatted_meeting,
    )

def render_markdown(briefing: Briefing) -> str:
    """Renders briefing to Markdown export format."""
    template = jinja_env.get_template("briefing.md.j2")
    formatted_meeting = format_meeting_display(briefing.input.meeting_time, briefing.input.timezone)
    return template.render(
        briefing=briefing,
        meeting_formatted=formatted_meeting,
    )

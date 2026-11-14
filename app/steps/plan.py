"""Deterministic query planning step."""

from typing import List, Optional
from pydantic import BaseModel
from app.models import MeetingInput, MeetingType, ResolvedEntity, Window

class PlannedQuery(BaseModel):
    category: str
    query: str
    topic: str = "news"  # news | general | finance
    include_domains: Optional[List[str]] = None
    depth: str = "basic"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_background: bool = False

def plan_queries(
    entity: ResolvedEntity,
    window: Window,
    meeting_input: MeetingInput,
    max_queries: int = 8,
    search_depth: str = "basic",
) -> List[PlannedQuery]:
    """Generates deterministic search queries tailored to entity type, window, and meeting goal."""
    name = entity.canonical_name
    start_str = window.start.strftime("%Y-%m-%d")
    end_str = window.end.strftime("%Y-%m-%d")
    planned: List[PlannedQuery] = []

    if entity.entity_type == "company":
        # 1. General News
        planned.append(
            PlannedQuery(
                category="news",
                query=f'"{name}"'[:300],
                topic="news",
                start_date=start_str,
                end_date=end_str,
                depth=search_depth,
            )
        )
        # 2. Product
        planned.append(
            PlannedQuery(
                category="product",
                query=f'"{name}" launch OR announces OR releases OR new product'[:300],
                topic="news",
                start_date=start_str,
                end_date=end_str,
                depth=search_depth,
            )
        )
        # 3. Leadership
        planned.append(
            PlannedQuery(
                category="leadership",
                query=f'"{name}" appoints OR hires OR names OR steps down OR CEO OR CTO OR executive'[:300],
                topic="news",
                start_date=start_str,
                end_date=end_str,
                depth=search_depth,
            )
        )
        # 4. Funding / M&A
        planned.append(
            PlannedQuery(
                category="funding",
                query=f'"{name}" funding OR raises OR acquisition OR acquires OR valuation OR IPO'[:300],
                topic="news",
                start_date=start_str,
                end_date=end_str,
                depth=search_depth,
            )
        )
        # 5. Partnership
        planned.append(
            PlannedQuery(
                category="partnership",
                query=f'"{name}" partnership OR partners OR integration OR collaboration'[:300],
                topic="news",
                start_date=start_str,
                end_date=end_str,
                depth=search_depth,
            )
        )
        # 6. Financial & Risk
        planned.append(
            PlannedQuery(
                category="financial_risk",
                query=f'"{name}" earnings OR revenue OR layoffs OR lawsuit OR regulatory OR outage OR breach'[:300],
                topic="news",
                start_date=start_str,
                end_date=end_str,
                depth=search_depth,
            )
        )
        # 7. Official domain
        if entity.official_domain:
            planned.append(
                PlannedQuery(
                    category="official",
                    query=f'"{name}" press release OR blog'[:300],
                    topic="general",
                    include_domains=[entity.official_domain],
                    start_date=start_str,
                    end_date=end_str,
                    depth=search_depth,
                )
            )

        # 8. Meeting-type specific query
        extra_query = None
        if meeting_input.meeting_type == MeetingType.sales:
            extra_query = PlannedQuery(
                category="sales_intent",
                query=f'"{name}" hiring OR initiatives OR strategy OR digital transformation'[:300],
                topic="news",
                start_date=start_str,
                end_date=end_str,
                depth=search_depth,
            )
        elif meeting_input.meeting_type == MeetingType.investor:
            extra_query = PlannedQuery(
                category="investor_metrics",
                query=f'"{name}" growth OR customers OR metrics OR competitors OR market share'[:300],
                topic="news",
                start_date=start_str,
                end_date=end_str,
                depth=search_depth,
            )
        elif meeting_input.meeting_type in (MeetingType.partnership, MeetingType.bizdev):
            extra_query = PlannedQuery(
                category="expansion_fit",
                query=f'"{name}" expansion OR new market OR customers OR ecosystem'[:300],
                topic="news",
                start_date=start_str,
                end_date=end_str,
                depth=search_depth,
            )

        if extra_query:
            if len(planned) >= max_queries:
                planned[len(planned) - 1] = extra_query
            else:
                planned.append(extra_query)

    else:
        # Person (professional only)
        affil = entity.affiliation or meeting_input.hint or ""
        # 1. News
        planned.append(
            PlannedQuery(
                category="news",
                query=f'"{name}" {affil}'.strip()[:300],
                topic="news",
                start_date=start_str,
                end_date=end_str,
                depth=search_depth,
            )
        )
        # 2. Role / Career
        planned.append(
            PlannedQuery(
                category="role",
                query=f'"{name}" appointed OR joins OR promoted OR named OR steps down'[:300],
                topic="news",
                start_date=start_str,
                end_date=end_str,
                depth=search_depth,
            )
        )
        # 3. Media / Keynotes
        planned.append(
            PlannedQuery(
                category="media",
                query=f'"{name}" interview OR keynote OR podcast OR panel OR talk'[:300],
                topic="general",
                start_date=start_str,
                end_date=end_str,
                depth=search_depth,
            )
        )
        # 4. Work announcements
        planned.append(
            PlannedQuery(
                category="work",
                query=f'"{name}" announces OR launches OR publishes OR open-sources'[:300],
                topic="general",
                start_date=start_str,
                end_date=end_str,
                depth=search_depth,
            )
        )
        # 5. Company news (if affiliation known)
        if affil:
            planned.append(
                PlannedQuery(
                    category="company_news",
                    query=f'"{affil}" news'[:300],
                    topic="news",
                    start_date=start_str,
                    end_date=end_str,
                    depth=search_depth,
                )
            )
            planned.append(
                PlannedQuery(
                    category="company_leadership",
                    query=f'"{affil}" announces OR launches OR partnership'[:300],
                    topic="news",
                    start_date=start_str,
                    end_date=end_str,
                    depth=search_depth,
                )
            )

    # Background query (general, no dates, max 3 results) if description is sparse
    if not entity.description or len(entity.description) < 40:
        planned.append(
            PlannedQuery(
                category="background",
                query=f'"{name}" overview OR about OR background'[:300],
                topic="general",
                is_background=True,
                depth="basic",
            )
        )

    # Enforce max_queries budget
    return planned[:max_queries]

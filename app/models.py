from __future__ import annotations
from datetime import date, datetime
from enum import Enum
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator

class MeetingType(str, Enum):
    sales = "sales"
    partnership = "partnership"
    investor = "investor"
    bizdev = "bizdev"
    general = "general"

class EntityType(str, Enum):
    company = "company"
    person = "person"
    auto = "auto"

class MeetingInput(BaseModel):
    entity: str = Field(min_length=2, max_length=120)
    entity_type: EntityType = EntityType.auto
    meeting_time: datetime  # must be timezone-aware; reject naive
    timezone: str = "UTC"  # IANA name, used for display only
    meeting_type: MeetingType = MeetingType.general
    hint: Optional[str] = Field(None, max_length=200)  # e.g. "CEO of Acme", "acme.com"
    user_context: Optional[str] = Field(None, max_length=400)  # who the user is + their goal

    @field_validator("meeting_time")
    @classmethod
    def validate_timezone_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.tzinfo.utcoffset(v) is None:
            raise ValueError("meeting_time must be timezone-aware")
        return v

class ResolvedEntity(BaseModel):
    canonical_name: str
    entity_type: Literal["company", "person"]
    aliases: list[str] = []
    official_domain: Optional[str] = None  # e.g. "acme.com"
    affiliation: Optional[str] = None  # for persons: current company/role if known
    description: str = ""  # <= 200 chars, neutral
    confidence: float = Field(ge=0, le=1)

class Candidate(BaseModel):
    label: str
    hint: str  # shown to user when ambiguous

class Window(BaseModel):
    start: date
    end: date  # inclusive; end = min(meeting date, today)
    meeting_in_past: bool = False
    meeting_far_future: bool = False  # > 30 days away -> warn

class Source(BaseModel):
    id: str  # "S1", "S2", ...
    url: str
    title: str
    domain: str
    published_date: Optional[date] = None
    snippet: str  # <= 700 chars (up to 2000 if extracted)
    score: float = 0.0
    is_primary: bool = False  # official domain / press release / regulator filing
    cluster_id: int = 0  # near-duplicate (syndication) cluster
    category: str = "general"  # which query category found it
    in_window: bool = True

class Confidence(str, Enum):
    verified = "VERIFIED"  # >=2 independent clusters OR 1 primary source, all in window
    reported = "REPORTED"  # single non-primary source, in window
    unverified = "UNVERIFIED"  # undated, inferred, conflicting, or failed grounding check

class Development(BaseModel):
    date: Optional[date] = None
    category: Literal[
        "news", "product", "leadership", "funding", "partnership", "financial", "risk", "media", "other"
    ]
    headline: str  # <= 14 words
    detail: str  # <= 30 words
    why_it_matters: str = ""  # <= 20 words, tailored to meeting_type
    source_ids: list[str]
    confidence: Confidence = Confidence.unverified  # set by code only

class Question(BaseModel):
    text: str  # <= 25 words, an open question to ask in the meeting
    rationale: str = ""  # <= 15 words
    source_ids: list[str] = []  # may be empty if purely strategic

class Bullet(BaseModel):
    text: str
    source_ids: list[str] = []
    confidence: Confidence = Confidence.unverified

class LLMDraft(BaseModel):  # exactly what the synthesis LLM must return as JSON
    tldr: list[Bullet]  # 2-3
    developments: list[Development]  # <= 8 (trimmed to 6 later)
    talking_points: list[Bullet]  # 2-4, tailored to meeting_type/user_context
    open_questions: list[Question]  # 5-7
    risks: list[Bullet]  # 0-3
    uncertainties: list[str]  # things that conflict / are unconfirmed / not found
    evidence_gaps: list[str]  # topics searched with no results in window

class TraceStep(BaseModel):
    name: str
    started_at: datetime
    duration_ms: int
    detail: dict = {}

class Briefing(BaseModel):
    id: str
    created_at: datetime
    input: MeetingInput
    entity: ResolvedEntity
    window: Window
    draft: LLMDraft
    sources: list[Source]  # ONLY sources actually cited, renumbered S1..Sn
    background: str = ""  # 1-2 neutral sentences (cited)
    stats: dict  # counts, word_count, latency, tokens if available
    trace: list[TraceStep]
    status: Literal["ok", "needs_clarification", "insufficient_evidence", "error"] = "ok"
    candidates: list[Candidate] = []
    warnings: list[str] = []

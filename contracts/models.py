"""Shared data contracts for Nizam Radar (spec v1.1, sections 4-8).

Both people code against these models. Do not rename or remove a field,
type or enum value alone: agree first, update fixtures in the same PR and
bump SCHEMA_VERSION. Adding a new optional field is fine.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.1"


class _Model(BaseModel):
    # Reject unknown fields so a typo in a fixture or API payload fails loudly.
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


# --- Section 4: shared vocabulary -------------------------------------------

class Sector(str, Enum):
    food_beverage = "food_beverage"


class SubActivity(str, Enum):
    cafe = "cafe"
    restaurant = "restaurant"
    bakery = "bakery"
    food_truck = "food_truck"
    cloud_kitchen = "cloud_kitchen"


class SourceId(str, Enum):
    boe_laws = "boe_laws"
    uqn_gazette = "uqn_gazette"
    istitlaa = "istitlaa"
    balady = "balady"
    sfda = "sfda"
    hrsd_qiwa = "hrsd_qiwa"
    zatca = "zatca"
    mc_commerce = "mc_commerce"
    news = "news"


class DocType(str, Enum):
    new_law = "new_law"
    amendment = "amendment"
    draft_consultation = "draft_consultation"
    circular = "circular"
    announcement = "announcement"
    guide = "guide"


class RegStatus(str, Enum):
    draft = "draft"
    published = "published"
    effective = "effective"
    repealed = "repealed"


class Applicability(str, Enum):
    applies = "applies"
    likely_applies = "likely_applies"
    does_not_apply = "does_not_apply"
    needs_review = "needs_review"


class Confidence(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class Priority(str, Enum):
    urgent = "urgent"
    important = "important"
    info = "info"


class DeadlineType(str, Enum):
    fixed_date = "fixed_date"
    relative = "relative"
    none = "none"


class RevenueBand(str, Enum):
    lt_375k = "lt_375k"
    k375_to_1m = "375k_to_1m"
    m1_to_40m = "1m_to_40m"
    gt_40m = "gt_40m"


class Lang(str, Enum):
    ar = "ar"
    en = "en"


class JobKind(str, Enum):
    collect = "collect"
    analyze = "analyze"
    notify = "notify"


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class Bilingual(_Model):
    ar: str
    en: str


# --- Section 5: BusinessProfile ---------------------------------------------

class BusinessProfile(_Model):
    profile_id: str = Field(pattern=r"^prof_[a-z0-9_]+$")
    schema_version: str = SCHEMA_VERSION
    business_name: str
    sector: Sector
    sub_activity: SubActivity
    city: str
    region: str
    employees_saudi: int = Field(ge=0)
    employees_non_saudi: int = Field(ge=0)
    has_physical_premises: bool
    premises_area_sqm: Optional[int] = None
    serves_food_onsite: bool
    sells_online: bool
    uses_delivery_apps: bool
    revenue_band: RevenueBand
    vat_registered: bool
    preferred_lang: Lang
    notify_email: Optional[str] = None
    created_at: datetime


class BusinessProfileCreate(_Model):
    """POST /profiles body: a BusinessProfile without profile_id and created_at."""

    schema_version: str = SCHEMA_VERSION
    business_name: str
    sector: Sector
    sub_activity: SubActivity
    city: str
    region: str
    employees_saudi: int = Field(ge=0)
    employees_non_saudi: int = Field(ge=0)
    has_physical_premises: bool
    premises_area_sqm: Optional[int] = None
    serves_food_onsite: bool
    sells_online: bool
    uses_delivery_apps: bool
    revenue_band: RevenueBand
    vat_registered: bool
    preferred_lang: Lang
    notify_email: Optional[str] = None


# --- Section 6: RegulationRecord --------------------------------------------

class Article(_Model):
    article_ref: str
    text: str


class CollectorMeta(_Model):
    tavily_query: Optional[str] = None
    tavily_score: Optional[float] = None
    extractor: Optional[str] = None


class RegulationRecord(_Model):
    regulation_id: str = Field(pattern=r"^reg_[0-9a-f]{10}_v\d+$")
    version: int = Field(ge=1)
    supersedes: Optional[str]
    schema_version: str = SCHEMA_VERSION
    source_id: SourceId
    source_url: str
    issuing_authority: str
    title_original: str
    title_en: Optional[str] = None
    language_original: Lang
    doc_type: DocType
    status: RegStatus
    published_date: Optional[date]
    effective_date: Optional[date] = None
    consultation_deadline: Optional[date] = None
    full_text: str = Field(min_length=200)
    articles: Optional[list[Article]] = None
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    retrieved_at: datetime
    collector_meta: Optional[CollectorMeta] = None


# --- Section 7: AnalysisResult ----------------------------------------------

class FilterResult(_Model):
    relevant: bool
    reason: str


class Citation(_Model):
    article_ref: Optional[str] = None
    quote: str = Field(max_length=300)
    source_url: str


class Obligation(_Model):
    obligation_id: str
    description: Bilingual
    deadline: Optional[date] = None
    deadline_type: DeadlineType = DeadlineType.none
    deadline_text: Optional[str] = None
    penalty: Optional[str] = None
    citation: Citation


class ChecklistItem(_Model):
    item_id: str
    text_ar: str
    text_en: str
    due_date: Optional[date] = None
    done: bool = False


class ModelsUsed(_Model):
    filter: str
    reasoning: str
    writer: str


class Usage(_Model):
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0


class AnalysisResult(_Model):
    analysis_id: str = Field(pattern=r"^ana_[a-z0-9_]+$")
    schema_version: str = SCHEMA_VERSION
    regulation_id: str
    profile_id: str
    created_at: datetime
    filter: FilterResult
    applicability: Applicability
    confidence: Confidence
    reasoning_summary: Bilingual
    obligations: list[Obligation] = []
    next_deadline: Optional[date] = None
    priority: Priority
    summary: Bilingual
    checklist: list[ChecklistItem] = []
    models_used: ModelsUsed
    usage: Usage
    notified_at: Optional[datetime] = None


# --- Section 8: alerts, chat and jobs ---------------------------------------

class AlertItem(_Model):
    analysis_id: str
    regulation_id: str
    title: Bilingual
    issuing_authority: str
    source_id: SourceId
    doc_type: DocType
    applicability: Applicability
    priority: Priority
    next_deadline: Optional[date] = None
    checklist_done: int
    checklist_total: int
    published_date: Optional[date] = None


class ChatTurn(_Model):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(_Model):
    profile_id: str
    regulation_id: Optional[str] = None
    lang: Lang
    message: str
    history: list[ChatTurn] = []


class ChatCitation(_Model):
    regulation_id: str
    article_ref: Optional[str] = None
    quote: str = Field(max_length=300)
    source_url: str


class ChatResponse(_Model):
    answer: str
    lang: Lang
    confidence: Confidence
    citations: list[ChatCitation] = []
    model: str


class JobProgress(_Model):
    done: int = 0
    total: int = 0


class Job(_Model):
    job_id: str = Field(pattern=r"^job_[a-z0-9]+$")
    kind: JobKind
    status: JobStatus
    progress: JobProgress
    profile_id: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error: Optional[str] = None


class ErrorBody(_Model):
    code: str
    message: str


class ErrorResponse(_Model):
    error: ErrorBody


ALL_MODELS = [
    BusinessProfile, BusinessProfileCreate, RegulationRecord, AnalysisResult,
    AlertItem, ChatRequest, ChatResponse, Job, ErrorResponse,
]

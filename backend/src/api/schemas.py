"""Request and response contracts for the frontend API."""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from backend.src.research.language import InvalidLanguageTag, canonicalize_language
from backend.src.research.schemas import RunStatus


class CreateResearchRun(BaseModel):
    user_request: str = Field(min_length=1, max_length=2000)
    max_iterations: int = Field(default=3, ge=1, le=5)
    report_language: str | None = Field(
        default=None,
        description="目标报告语言；省略时根据研究请求推断。",
    )

    @field_validator("report_language")
    @classmethod
    def validate_report_language(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        try:
            return canonicalize_language(value)
        except InvalidLanguageTag as exc:
            raise ValueError(str(exc)) from exc


class PreviewReportLanguage(BaseModel):
    user_request: str = Field(min_length=1, max_length=2000)
    report_language: str | None = None

    @field_validator("report_language")
    @classmethod
    def validate_report_language(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        try:
            return canonicalize_language(value)
        except InvalidLanguageTag as exc:
            raise ValueError(str(exc)) from exc


class ReportLanguagePreview(BaseModel):
    tag: str
    name: str
    quality: str
    source: str


class AcceptedResearchRun(BaseModel):
    id: str
    status: RunStatus
    report_language: str


class ResearchRunSummary(BaseModel):
    id: str
    user_request: str
    report_language: str
    report_language_name: str
    report_language_quality: str
    report_direction: str
    status: RunStatus
    resume_status: RunStatus | None = None
    unfinished_tasks: int = 0
    can_resume: bool = False
    iteration: int
    max_iterations: int
    created_at: datetime
    updated_at: datetime
    research_question: str | None = None
    title: str | None = None


class ResearchRunList(BaseModel):
    items: list[ResearchRunSummary]
    total: int
    page: int
    page_size: int
    summary: "ResearchRunSummaryCounts"


class ResearchRunSummaryCounts(BaseModel):
    total: int
    active: int
    completed: int
    needs_human_review: int


class SourceView(BaseModel):
    url: str
    title: str
    publisher: str | None = None
    published_at: str | None = None
    source_type: str


class TaskView(BaseModel):
    id: str
    question: str
    task_type: str
    priority: str
    required_source_types: list[str]
    acceptance_criteria: list[str]
    queries: list[str]
    attempts: int
    completed: bool


class ResearchPlanView(BaseModel):
    research_question: str
    scope: str
    research_domains: list[str]
    risk_level: str
    completion_rules: list[str]
    tasks: list[TaskView]


class CandidateView(BaseModel):
    task_id: str | None = None
    iteration: int
    claim: str
    excerpt: str
    locator: str | None = None
    source: SourceView


class EvidenceView(CandidateView):
    id: str
    task_id: str
    verdict: str
    confidence: float
    limitations: list[str]


class FindingView(BaseModel):
    id: str
    task_id: str
    iteration: int
    statement: str
    classification: str
    confidence: float
    caveats: list[str]
    evidence_ids: list[str]


class CriticIssueView(BaseModel):
    severity: str
    finding_id: str | None = None
    problem: str
    follow_up_question: str | None = None
    follow_up_queries: list[str]


class CritiqueView(BaseModel):
    iteration: int
    decision: str
    approved_finding_ids: list[str]
    issues: list[CriticIssueView]


class ReportBlockView(BaseModel):
    heading: str
    text: str
    finding_ids: list[str]
    evidence_ids: list[str]


class ReportView(BaseModel):
    title: str
    language: str
    language_name: str
    direction: str
    markdown: str
    anchor_digest: str
    blocks: list[ReportBlockView]


class RunEventView(BaseModel):
    sequence: int
    message: str
    created_at: datetime


class ResearchProgress(BaseModel):
    id: str
    report_language: str
    status: RunStatus
    iteration: int
    max_iterations: int
    updated_at: datetime
    events: list[RunEventView]


class ResearchRunDetail(BaseModel):
    id: str
    user_request: str
    report_language: str
    report_language_name: str
    report_language_source: str
    report_language_quality: str
    report_direction: str
    status: RunStatus
    can_resume: bool = False
    error: str | None = None
    iteration: int
    max_iterations: int
    created_at: datetime
    updated_at: datetime
    plan: ResearchPlanView | None = None
    candidates: list[CandidateView]
    evidence: list[EvidenceView]
    findings: list[FindingView]
    critiques: list[CritiqueView]
    report: ReportView | None = None
    events: list[RunEventView]


class CitationSourceView(BaseModel):
    evidence_id: str
    claim: str
    excerpt: str
    locator: str | None = None
    url: str
    title: str
    publisher: str | None = None
    published_at: str | None = None
    source_type: str


class CitationReferenceView(BaseModel):
    run_id: str
    reference_id: str
    reference_type: str
    finding_statement: str | None = None
    sources: list[CitationSourceView]
    urls: list[str]


class HealthStatus(BaseModel):
    status: str

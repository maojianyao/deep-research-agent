"""Normalized SQLAlchemy models for persisted research runs."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Table, Text,
    UniqueConstraint, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


finding_evidence = Table(
    "finding_evidence",
    Base.metadata,
    Column("finding_id", ForeignKey("findings.id", ondelete="CASCADE"), primary_key=True),
    Column("evidence_id", ForeignKey("evidence_cards.id", ondelete="CASCADE"), primary_key=True),
)

critic_approved_finding = Table(
    "critic_approved_finding",
    Base.metadata,
    Column("review_id", ForeignKey("critic_reviews.id", ondelete="CASCADE"), primary_key=True),
    Column("finding_id", ForeignKey("findings.id", ondelete="CASCADE"), primary_key=True),
)

report_block_finding = Table(
    "report_block_finding",
    Base.metadata,
    Column("block_id", ForeignKey("report_blocks.id", ondelete="CASCADE"), primary_key=True),
    Column("finding_id", ForeignKey("findings.id", ondelete="CASCADE"), primary_key=True),
)

report_block_evidence = Table(
    "report_block_evidence",
    Base.metadata,
    Column("block_id", ForeignKey("report_blocks.id", ondelete="CASCADE"), primary_key=True),
    Column("evidence_id", ForeignKey("evidence_cards.id", ondelete="CASCADE"), primary_key=True),
)


class ResearchRunModel(Base):
    __tablename__ = "research_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_request: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    max_iterations: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    iteration: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    plan: Mapped["ResearchPlanModel"] = relationship(
        back_populates="run", cascade="all, delete-orphan", uselist=False
    )
    tasks: Mapped[list["ResearchTaskModel"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    candidates: Mapped[list["CandidateEvidenceModel"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    evidence: Mapped[list["EvidenceCardModel"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    findings: Mapped[list["FindingModel"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    critiques: Mapped[list["CriticReviewModel"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    report: Mapped["ReportModel"] = relationship(
        back_populates="run", cascade="all, delete-orphan", uselist=False
    )
    events: Mapped[list["RunEventModel"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class ResearchPlanModel(Base):
    __tablename__ = "research_plans"

    run_id: Mapped[str] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE"), primary_key=True
    )
    research_question: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False)
    completion_rules: Mapped[list[str]] = mapped_column(JSON, default=list)

    run: Mapped[ResearchRunModel] = relationship(back_populates="plan")


class ResearchTaskModel(Base):
    __tablename__ = "research_tasks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("research_runs.id", ondelete="CASCADE"), index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    task_type: Mapped[str] = mapped_column(String(20), nullable=False)
    priority: Mapped[str] = mapped_column(String(10), nullable=False)
    required_source_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    acceptance_criteria: Mapped[list[str]] = mapped_column(JSON, default=list)
    queries: Mapped[list[str]] = mapped_column(JSON, default=list)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run: Mapped[ResearchRunModel] = relationship(back_populates="tasks")


class SourceDocumentModel(Base):
    __tablename__ = "source_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    url: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    publisher: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[str | None] = mapped_column(String(40))
    source_type: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CandidateEvidenceModel(Base):
    __tablename__ = "candidate_evidences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("research_runs.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[str | None] = mapped_column(
        ForeignKey("research_tasks.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[int] = mapped_column(ForeignKey("source_documents.id"), nullable=False)
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    locator: Mapped[str | None] = mapped_column(Text)
    iteration: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run: Mapped[ResearchRunModel] = relationship(back_populates="candidates")
    source: Mapped[SourceDocumentModel] = relationship()


class EvidenceCardModel(Base):
    __tablename__ = "evidence_cards"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("research_runs.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("research_tasks.id", ondelete="CASCADE"), index=True)
    iteration: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_id: Mapped[int] = mapped_column(ForeignKey("source_documents.id"), nullable=False)
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    locator: Mapped[str | None] = mapped_column(Text)
    verdict: Mapped[str] = mapped_column(String(30), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    limitations: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run: Mapped[ResearchRunModel] = relationship(back_populates="evidence")
    source: Mapped[SourceDocumentModel] = relationship()
    findings: Mapped[list["FindingModel"]] = relationship(
        secondary=finding_evidence, back_populates="evidence"
    )


class FindingModel(Base):
    __tablename__ = "findings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("research_runs.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("research_tasks.id", ondelete="CASCADE"), index=True)
    iteration: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    classification: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    caveats: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run: Mapped[ResearchRunModel] = relationship(back_populates="findings")
    evidence: Mapped[list[EvidenceCardModel]] = relationship(
        secondary=finding_evidence, back_populates="findings"
    )


class CriticReviewModel(Base):
    __tablename__ = "critic_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("research_runs.id", ondelete="CASCADE"), index=True)
    iteration: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    decision: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run: Mapped[ResearchRunModel] = relationship(back_populates="critiques")
    issues: Mapped[list["CriticIssueModel"]] = relationship(
        back_populates="review", cascade="all, delete-orphan"
    )
    approved_findings: Mapped[list[FindingModel]] = relationship(
        secondary=critic_approved_finding
    )


class CriticIssueModel(Base):
    __tablename__ = "critic_issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    review_id: Mapped[int] = mapped_column(
        ForeignKey("critic_reviews.id", ondelete="CASCADE"), index=True
    )
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    finding_id: Mapped[str | None] = mapped_column(String(32), index=True)
    problem: Mapped[str] = mapped_column(Text, nullable=False)
    follow_up_question: Mapped[str | None] = mapped_column(Text)
    follow_up_queries: Mapped[list[str]] = mapped_column(JSON, default=list)

    review: Mapped[CriticReviewModel] = relationship(back_populates="issues")


class ReportModel(Base):
    __tablename__ = "reports"

    run_id: Mapped[str] = mapped_column(
        ForeignKey("research_runs.id", ondelete="CASCADE"), primary_key=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    markdown: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    run: Mapped[ResearchRunModel] = relationship(back_populates="report")
    blocks: Mapped[list["ReportBlockModel"]] = relationship(
        back_populates="report", cascade="all, delete-orphan", order_by="ReportBlockModel.position"
    )


class ReportBlockModel(Base):
    __tablename__ = "report_blocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_run_id: Mapped[str] = mapped_column(
        ForeignKey("reports.run_id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    heading: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    report: Mapped[ReportModel] = relationship(back_populates="blocks")
    findings: Mapped[list[FindingModel]] = relationship(secondary=report_block_finding)
    evidence: Mapped[list[EvidenceCardModel]] = relationship(secondary=report_block_evidence)


class RunEventModel(Base):
    __tablename__ = "run_events"
    __table_args__ = (UniqueConstraint("run_id", "sequence", name="uq_run_event_sequence"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("research_runs.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run: Mapped[ResearchRunModel] = relationship(back_populates="events")

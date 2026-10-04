"""Shared deterministic model factories for smoke tests."""

from __future__ import annotations

from backend.src.research.schemas import (
    CandidateEvidence, EvidenceCard, Finding, OutlineSection, ReportBlock,
    ReportDraft, ReportOutline, ResearchPlan, ResearchTask, SectionDraft,
    SourceDocument, SummaryDraft,
)


def make_source(url: str = "https://example.com/source", **overrides) -> SourceDocument:
    values = {
        "url": url,
        "title": "Example source",
        "publisher": "Example publisher",
        "published_at": "2026-01-01",
        "source_type": "official",
        "content": "Example source content with enough text for validation.",
    }
    values.update(overrides)
    return SourceDocument(**values)


def make_candidate(url: str = "https://example.com/source", **overrides) -> CandidateEvidence:
    values = {
        "source": make_source(url=url),
        "claim": "Example claim",
        "excerpt": "Example excerpt",
        "locator": "Section 1",
    }
    values.update(overrides)
    return CandidateEvidence(**values)


def make_evidence(
        evidence_id: str = "evidence_test",
        task_id: str = "task_test",
        claim: str = "Example claim",
        confidence: float = 0.8,
        **overrides,
) -> EvidenceCard:
    values = {
        "id": evidence_id,
        "task_id": task_id,
        "claim": claim,
        "excerpt": "Example excerpt",
        "source": make_source(),
        "locator": "Section 1",
        "verdict": "supported",
        "confidence": confidence,
        "limitations": ["Example limitation"],
    }
    values.update(overrides)
    return EvidenceCard(**values)


def make_task(task_id: str = "task_test", **overrides) -> ResearchTask:
    values = {
        "id": task_id,
        "question": "Example question",
        "queries": ["example query"],
    }
    values.update(overrides)
    return ResearchTask(**values)


def make_plan(task: ResearchTask | None = None, **overrides) -> ResearchPlan:
    values = {
        "research_question": "Example research question",
        "scope": "Example scope",
        "tasks": [task or make_task()],
        "completion_rules": ["Example rule"],
    }
    values.update(overrides)
    return ResearchPlan(**values)


def make_finding(
        finding_id: str = "finding_test",
        task_id: str = "task_test",
        evidence_ids: list[str] | None = None,
        **overrides,
) -> Finding:
    values = {
        "id": finding_id,
        "task_id": task_id,
        "statement": "Example finding",
        "classification": "fact",
        "evidence_ids": evidence_ids or ["evidence_test"],
        "confidence": 0.8,
        "caveats": ["Example caveat"],
    }
    values.update(overrides)
    return Finding(**values)


def make_outline(**overrides) -> ReportOutline:
    values = {
        "narrative": "Example narrative",
        "title": "Example report",
        "sections": [
            OutlineSection(heading="Method", role="context", key_points=["Method point"],
                           finding_ids=[]),
            OutlineSection(heading="Finding", role="argument", key_points=["Finding point"],
                           finding_ids=["finding_test"]),
        ],
    }
    values.update(overrides)
    return ReportOutline(**values)


def make_section(**overrides) -> SectionDraft:
    values = {
        "heading": "Finding",
        "text": "Example section text",
        "finding_ids": ["finding_test"],
        "evidence_ids": ["evidence_test"],
        "key_points": ["Finding point"],
    }
    values.update(overrides)
    return SectionDraft(**values)


def make_summary(**overrides) -> SummaryDraft:
    values = {
        "executive_summary": "Example summary",
        "conclusion": "Example conclusion",
        "limitations": "Example limitations",
    }
    values.update(overrides)
    return SummaryDraft(**values)


def make_report(evidence: EvidenceCard | None = None, **overrides) -> ReportDraft:
    evidence = evidence or make_evidence()
    values = {
        "title": "Example report",
        "blocks": [
            ReportBlock(heading="Summary", text="Summary text"),
            ReportBlock(heading="Finding", text="Finding text",
                        finding_ids=["finding_test"], evidence_ids=[evidence.id]),
        ],
    }
    values.update(overrides)
    return ReportDraft(**values)

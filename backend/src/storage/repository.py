"""Repository for saving and querying complete research runs."""

from __future__ import annotations

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, selectinload

from backend.src.research.schemas import (
    CandidateEvidence, CriticIssue, CriticReview, EvidenceCard, Finding, ReportBlock,
    ReportDraft, ResearchPlan, ResearchRun, ResearchTask, RunStatus, SourceDocument,
)
from backend.src.utils.documents import normalize_url

from .models import (
    CandidateEvidenceModel, CriticIssueModel, CriticReviewModel, EvidenceCardModel,
    FindingModel, ReportBlockModel, ReportModel, ResearchPlanModel, ResearchRunModel,
    ResearchTaskModel, RunEventModel, SourceDocumentModel,
)


class ResearchRunRepository:
    def __init__(self, engine: Engine):
        self.engine = engine

    def save_run(self, run: ResearchRun) -> str:
        """Save a complete snapshot of a run; repeated calls replace its run-owned rows."""
        with Session(self.engine) as session, session.begin():
            existing = session.get(ResearchRunModel, run.id)
            if existing is not None:
                session.delete(existing)
                session.flush()

            model = ResearchRunModel(
                id=run.id,
                user_request=run.user_request,
                status=run.status.value,
                max_iterations=run.max_iterations,
                iteration=run.iteration,
            )

            if run.plan is not None:
                model.plan = ResearchPlanModel(
                    research_question=run.plan.research_question,
                    scope=run.plan.scope,
                    completion_rules=run.plan.completion_rules,
                )
                model.tasks = [
                    ResearchTaskModel(
                        id=task.id,
                        run=model,
                        question=task.question,
                        task_type=task.task_type,
                        priority=task.priority,
                        required_source_types=task.required_source_types,
                        acceptance_criteria=task.acceptance_criteria,
                        queries=task.queries,
                        attempts=task.attempts,
                        completed=task.completed,
                    )
                    for task in run.plan.tasks
                ]

            sources = {str(item.source.url): self._source(session, item.source)
                       for item in run.candidates}
            for item in run.evidence:
                sources.setdefault(str(item.source.url), self._source(session, item.source))

            model.candidates = [
                CandidateEvidenceModel(
                    run=model,
                    task_id=item.task_id,
                    source=sources[str(item.source.url)],
                    claim=item.claim,
                    excerpt=item.excerpt,
                    locator=item.locator,
                    iteration=item.iteration,
                )
                for item in run.candidates
            ]

            evidence = {
                item.id: EvidenceCardModel(
                    id=item.id,
                    run=model,
                    task_id=item.task_id,
                    iteration=item.iteration,
                    source=sources[str(item.source.url)],
                    claim=item.claim,
                    excerpt=item.excerpt,
                    locator=item.locator,
                    verdict=item.verdict,
                    confidence=item.confidence,
                    limitations=item.limitations,
                )
                for item in run.evidence
            }

            findings = {
                item.id: FindingModel(
                    id=item.id,
                    run=model,
                    task_id=item.task_id,
                    iteration=item.iteration,
                    statement=item.statement,
                    classification=item.classification,
                    confidence=item.confidence,
                    caveats=item.caveats,
                    evidence=[evidence[eid] for eid in item.evidence_ids if eid in evidence],
                )
                for item in run.findings
            }
            model.evidence = list(evidence.values())
            model.findings = list(findings.values())

            critiques = run.critiques or ([run.critique] if run.critique is not None else [])
            model.critiques = []
            for critique in critiques:
                review = CriticReviewModel(
                    run=model,
                    iteration=critique.iteration,
                    decision=critique.decision,
                    approved_findings=[
                        findings[fid] for fid in critique.approved_finding_ids
                        if fid in findings
                    ],
                )
                review.issues = [
                    CriticIssueModel(
                        review=review,
                        severity=issue.severity,
                        finding_id=issue.finding_id,
                        problem=issue.problem,
                        follow_up_question=issue.follow_up_question,
                        follow_up_queries=issue.follow_up_queries,
                    )
                    for issue in critique.issues
                ]
                model.critiques.append(review)

            if run.report is not None:
                report = ReportModel(
                    run=model,
                    title=run.report.title,
                    markdown=run.to_markdown() or "",
                )
                report.blocks = [
                    ReportBlockModel(
                        report=report,
                        position=index,
                        heading=block.heading,
                        text=block.text,
                        findings=[findings[fid] for fid in block.finding_ids if fid in findings],
                        evidence=[evidence[eid] for eid in block.evidence_ids if eid in evidence],
                    )
                    for index, block in enumerate(run.report.blocks)
                ]
                model.report = report

            model.events = [
                RunEventModel(run=model, sequence=index, message=message)
                for index, message in enumerate(run.events, start=1)
            ]
            session.add(model)

        return run.id

    def list_runs(self, limit: int = 50, offset: int = 0,
                  status: str | None = None, search: str | None = None) -> list[dict]:
        """Return lightweight rows for the frontend research list."""
        query = (
            select(
                ResearchRunModel.id,
                ResearchRunModel.user_request,
                ResearchRunModel.status,
                ResearchRunModel.iteration,
                ResearchRunModel.max_iterations,
                ResearchRunModel.created_at,
                ResearchRunModel.updated_at,
                ResearchPlanModel.research_question,
                ReportModel.title,
            )
            .outerjoin(ResearchPlanModel, ResearchPlanModel.run_id == ResearchRunModel.id)
            .outerjoin(ReportModel, ReportModel.run_id == ResearchRunModel.id)
        )
        query = self._run_filters(query, status, search)
        query = query.order_by(ResearchRunModel.updated_at.desc(), ResearchRunModel.id.desc())
        query = query.limit(limit).offset(offset)
        with Session(self.engine) as session:
            return [row._asdict() for row in session.execute(query).all()]

    def count_runs(self, status: str | None = None, search: str | None = None) -> int:
        query = self._run_filters(select(func.count()).select_from(ResearchRunModel), status, search)
        with Session(self.engine) as session:
            return session.scalar(query) or 0

    def get_progress(self, run_id: str, after_sequence: int = 0) -> dict | None:
        """Fetch only run state and new events for inexpensive frontend polling."""
        with Session(self.engine) as session:
            row = session.execute(select(
                ResearchRunModel.id,
                ResearchRunModel.status,
                ResearchRunModel.iteration,
                ResearchRunModel.max_iterations,
                ResearchRunModel.updated_at,
            ).where(ResearchRunModel.id == run_id)).one_or_none()
            if row is None:
                return None
            events = session.execute(select(
                RunEventModel.sequence,
                RunEventModel.message,
                RunEventModel.created_at,
            ).where(
                RunEventModel.run_id == run_id,
                RunEventModel.sequence > after_sequence,
            ).order_by(RunEventModel.sequence)).all()
            return {
                "id": row.id,
                "status": row.status,
                "iteration": row.iteration,
                "max_iterations": row.max_iterations,
                "updated_at": row.updated_at,
                "events": [event._asdict() for event in events],
            }

    @staticmethod
    def _run_filters(query, status: str | None, search: str | None):
        if status:
            query = query.where(ResearchRunModel.status == status)
        if search:
            query = query.where(ResearchRunModel.user_request.contains(search, autoescape=True))
        return query

    def get_run(self, run_id: str) -> ResearchRunModel | None:
        """Return one fully loaded run, including all evidence-chain relationships."""
        query = (
            select(ResearchRunModel)
            .where(ResearchRunModel.id == run_id)
            .options(
                selectinload(ResearchRunModel.plan),
                selectinload(ResearchRunModel.tasks),
                selectinload(ResearchRunModel.candidates).selectinload(
                    CandidateEvidenceModel.source
                ),
                selectinload(ResearchRunModel.evidence)
                .selectinload(EvidenceCardModel.source),
                selectinload(ResearchRunModel.findings).selectinload(FindingModel.evidence),
                selectinload(ResearchRunModel.critiques)
                .selectinload(CriticReviewModel.issues),
                selectinload(ResearchRunModel.critiques).selectinload(
                    CriticReviewModel.approved_findings
                ),
                selectinload(ResearchRunModel.report)
                .selectinload(ReportModel.blocks)
                .selectinload(ReportBlockModel.findings),
                selectinload(ResearchRunModel.report)
                .selectinload(ReportModel.blocks)
                .selectinload(ReportBlockModel.evidence),
                selectinload(ResearchRunModel.events),
            )
        )
        with Session(self.engine) as session:
            return session.scalar(query)

    def load_run(self, run_id: str) -> ResearchRun | None:
        """Rebuild the domain run from its persisted snapshot for interrupted-run recovery."""
        model = self.get_run(run_id)
        if model is None:
            return None

        tasks = [ResearchTask(
            id=item.id,
            question=item.question,
            task_type=item.task_type,
            priority=item.priority,
            required_source_types=item.required_source_types,
            acceptance_criteria=item.acceptance_criteria,
            queries=item.queries,
            attempts=item.attempts,
            completed=item.completed,
        ) for item in model.tasks]
        plan = ResearchPlan(
            research_question=model.plan.research_question,
            scope=model.plan.scope,
            completion_rules=model.plan.completion_rules,
            tasks=tasks,
        ) if model.plan else None

        def source(item) -> SourceDocument:
            return SourceDocument(
                url=item.url,
                title=item.title,
                publisher=item.publisher,
                published_at=item.published_at,
                source_type=item.source_type,
                content=item.content,
            )

        candidates = [CandidateEvidence(
            task_id=item.task_id,
            iteration=item.iteration,
            source=source(item.source),
            claim=item.claim,
            excerpt=item.excerpt,
            locator=item.locator,
        ) for item in model.candidates]
        evidence = [EvidenceCard(
            id=item.id,
            task_id=item.task_id,
            iteration=item.iteration,
            claim=item.claim,
            excerpt=item.excerpt,
            source=source(item.source),
            locator=item.locator,
            verdict=item.verdict,
            confidence=item.confidence,
            limitations=item.limitations,
        ) for item in model.evidence]
        findings = [Finding(
            id=item.id,
            task_id=item.task_id,
            iteration=item.iteration,
            statement=item.statement,
            classification=item.classification,
            evidence_ids=[card.id for card in item.evidence],
            confidence=item.confidence,
            caveats=item.caveats,
        ) for item in model.findings]
        critiques = [CriticReview(
            decision=item.decision,
            iteration=item.iteration,
            issues=[CriticIssue(
                severity=issue.severity,
                finding_id=issue.finding_id,
                problem=issue.problem,
                follow_up_question=issue.follow_up_question,
                follow_up_queries=issue.follow_up_queries,
            ) for issue in item.issues],
            approved_finding_ids=[finding.id for finding in item.approved_findings],
        ) for item in sorted(model.critiques, key=lambda review: review.iteration)]
        report = ReportDraft(
            title=model.report.title,
            blocks=[ReportBlock(
                heading=block.heading,
                text=block.text,
                finding_ids=[finding.id for finding in block.findings],
                evidence_ids=[card.id for card in block.evidence],
            ) for block in model.report.blocks],
        ) if model.report else None
        return ResearchRun(
            id=model.id,
            user_request=model.user_request,
            status=RunStatus(model.status),
            max_iterations=model.max_iterations,
            iteration=model.iteration,
            plan=plan,
            candidates=candidates,
            evidence=evidence,
            findings=findings,
            critiques=critiques,
            critique=critiques[-1] if critiques else None,
            report=report,
            events=[item.message for item in sorted(model.events, key=lambda event: event.sequence)],
        )

    @staticmethod
    def _source(session: Session, source) -> SourceDocumentModel:
        url = normalize_url(str(source.url))
        existing = session.scalar(
            select(SourceDocumentModel).where(SourceDocumentModel.url == url)
        )
        if existing is not None:
            return existing
        model = SourceDocumentModel(
            url=url,
            title=source.title,
            publisher=source.publisher,
            published_at=source.published_at,
            source_type=source.source_type,
            content=source.content,
        )
        session.add(model)
        return model

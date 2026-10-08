"""Smoke tests for SQLAlchemy research-run persistence."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sqlalchemy import func, select

from backend.src.research.schemas import CriticIssue, CriticReview, ResearchRun, RunStatus
from backend.src.storage import ResearchRunRepository, create_db_engine, init_db
from backend.src.storage.models import SourceDocumentModel
from backend.tests.factories import (
    make_candidate, make_evidence, make_finding, make_plan, make_report, make_task,
)


def make_persisted_run(suffix: str = "") -> ResearchRun:
    task = make_task(task_id=f"task_storage{suffix}")
    evidence = make_evidence(
        evidence_id=f"evidence_storage{suffix}",
        task_id=task.id,
        confidence=0.8,
        iteration=1,
    )
    finding = make_finding(
        finding_id=f"finding_storage{suffix}",
        task_id=task.id,
        evidence_ids=[evidence.id],
        iteration=1,
    )
    candidate = make_candidate(
        url=str(evidence.source.url),
        claim="Candidate claim",
        excerpt="Candidate excerpt",
    )
    candidate.task_id = task.id
    candidate.iteration = 1

    return ResearchRun(
        id=f"run_storage{suffix}",
        user_request="Storage research topic",
        status=RunStatus.COMPLETED,
        iteration=1,
        plan=make_plan(task=task),
        candidates=[candidate],
        evidence=[evidence],
        findings=[finding],
        critique=CriticReview(
            decision="approve",
            iteration=1,
            issues=[CriticIssue(severity="low", problem="Example issue")],
            approved_finding_ids=[finding.id],
        ),
        critiques=[
            CriticReview(decision="research_more", iteration=0),
            CriticReview(
                decision="approve",
                iteration=1,
                issues=[CriticIssue(severity="low", problem="Example issue")],
                approved_finding_ids=[finding.id],
            ),
        ],
        report=make_report(evidence=evidence),
        events=["first event", "second event"],
    )


class StorageRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine = create_db_engine(f"sqlite:///{Path(self.temp.name) / 'research.db'}")
        init_db(self.engine)
        self.repository = ResearchRunRepository(self.engine)

    def test_save_and_load_complete_run(self):
        run = make_persisted_run()
        self.repository.save_run(run)

        saved = self.repository.get_run(run.id)
        self.assertIsNotNone(saved)
        self.assertEqual(saved.user_request, "Storage research topic")
        self.assertEqual(saved.status, "completed")
        self.assertEqual(saved.plan.research_question, "Example research question")
        self.assertEqual(saved.tasks[0].question, "Example question")
        self.assertEqual(saved.candidates[0].claim, "Candidate claim")
        self.assertEqual(saved.candidates[0].task_id, "task_storage")
        self.assertEqual(saved.candidates[0].iteration, 1)
        self.assertEqual(saved.evidence[0].id, "evidence_storage")
        self.assertEqual(saved.evidence[0].iteration, 1)
        self.assertEqual(saved.evidence[0].source.url, str(run.evidence[0].source.url))
        self.assertEqual(saved.findings[0].evidence[0].id, "evidence_storage")
        self.assertEqual(saved.findings[0].iteration, 1)
        self.assertEqual(len(saved.critiques), 2)
        self.assertEqual([item.decision for item in saved.critiques], ["research_more", "approve"])
        self.assertEqual(saved.critiques[1].approved_findings[0].id, "finding_storage")
        self.assertEqual(saved.critiques[1].issues[0].problem, "Example issue")
        self.assertEqual(saved.report.title, "Example report")
        self.assertIn("# Example report", saved.report.markdown)
        self.assertEqual(saved.report.blocks[0].heading, "Summary")
        self.assertEqual([event.message for event in saved.events], run.events)

    def test_save_is_idempotent_for_the_same_run(self):
        run = make_persisted_run()
        self.repository.save_run(run)

        run.status = RunStatus.FAILED
        run.event("third event")
        self.repository.save_run(run)

        saved = self.repository.get_run(run.id)
        self.assertEqual(saved.status, "failed")
        self.assertEqual(len(saved.events), 3)
        self.assertEqual(len(saved.candidates), 1)
        self.assertEqual(len(saved.findings), 1)

    def test_source_documents_are_reused_by_url(self):
        first = make_persisted_run()
        second = make_persisted_run(suffix="_2")
        self.repository.save_run(first)
        self.repository.save_run(second)

        with self.engine.connect() as connection:
            count = connection.scalar(select(func.count()).select_from(SourceDocumentModel))
        self.assertEqual(count, 1)

    def test_list_runs_returns_frontend_summary(self):
        run = make_persisted_run()
        self.repository.save_run(run)

        rows = self.repository.list_runs()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], run.id)
        self.assertEqual(rows[0]["user_request"], run.user_request)
        self.assertEqual(rows[0]["status"], "completed")
        self.assertEqual(rows[0]["research_question"], run.plan.research_question)
        self.assertEqual(rows[0]["title"], run.report.title)

    def test_load_run_rebuilds_domain_state_for_resume(self):
        run = make_persisted_run()
        run.status = RunStatus.RESEARCHING
        self.repository.save_run(run)

        loaded = self.repository.load_run(run.id)

        self.assertEqual(loaded.status, RunStatus.RESEARCHING)
        self.assertEqual(loaded.plan.tasks[0].id, run.plan.tasks[0].id)
        self.assertEqual(loaded.evidence[0].id, run.evidence[0].id)
        self.assertEqual(loaded.findings[0].evidence_ids, run.findings[0].evidence_ids)
        self.assertEqual(loaded.critique.approved_finding_ids, run.critique.approved_finding_ids)
        self.assertEqual(loaded.report.title, run.report.title)
        self.assertEqual(loaded.events, run.events)

    def test_get_progress_returns_only_new_events(self):
        run = make_persisted_run()
        self.repository.save_run(run)

        progress = self.repository.get_progress(run.id, after_sequence=1)

        self.assertEqual(progress["status"], run.status.value)
        self.assertEqual([item["sequence"] for item in progress["events"]], [2])
        self.assertEqual(progress["events"][0]["message"], "second event")
        self.assertIsNone(self.repository.get_progress("missing"))


if __name__ == "__main__":
    unittest.main()

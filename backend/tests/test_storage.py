"""Smoke tests for SQLAlchemy research-run persistence."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, func, inspect, select

from backend.src.research.schemas import CriticIssue, CriticReview, ReportBlock, ResearchRun, RunStatus
from backend.src.storage import ResearchRunRepository, create_db_engine, init_db
from backend.src.storage.models import (
    Base, CandidateEvidenceModel, CriticIssueModel, CriticReviewModel,
    EvidenceCardModel, FindingModel, ReportBlockModel, ReportModel,
    ResearchPlanModel, ResearchRunModel, ResearchTaskModel, RunEventModel,
    SourceDocumentModel, critic_approved_finding, finding_evidence,
    report_block_evidence, report_block_finding,
)
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
        run.report_language = "ja"
        run.report_language_source = "explicit"
        run.plan.research_domains = ["技术", "商业"]
        run.plan.risk_level = "high"
        run.report.report_language = "ja"
        run.report.reference_heading = "参考文献"
        self.repository.save_run(run)

        saved = self.repository.get_run(run.id)
        self.assertIsNotNone(saved)
        self.assertEqual(saved.user_request, "Storage research topic")
        self.assertEqual(saved.status, "completed")
        self.assertEqual(saved.report_language, "ja")
        self.assertEqual(saved.report_language_source, "explicit")
        self.assertEqual(saved.plan.research_domains, ["技术", "商业"])
        self.assertEqual(saved.plan.risk_level, "high")
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
        self.assertEqual(saved.report.reference_heading, "参考文献")
        self.assertIn("# Example report", saved.report.markdown)
        self.assertEqual(saved.report.blocks[0].heading, "Summary")
        self.assertEqual([event.message for event in saved.events], run.events)
        loaded = self.repository.load_run(run.id)
        self.assertEqual(loaded.report.report_language, "ja")

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

    def test_list_runs_resume_flag_only_applies_to_resumable_runs(self):
        legacy_cancelled = make_persisted_run("_legacy_cancelled")
        legacy_cancelled.status = RunStatus.CANCELLED
        legacy_cancelled.plan.tasks[0].completed = False
        completed = make_persisted_run("_done")
        self.repository.save_run(legacy_cancelled)
        self.repository.save_run(completed)

        rows = {row["id"]: row for row in self.repository.list_runs()}

        self.assertTrue(rows[legacy_cancelled.id]["can_resume"])
        self.assertFalse(rows[completed.id]["can_resume"])

    def test_load_run_rebuilds_domain_state_for_resume(self):
        run = make_persisted_run()
        run.status = RunStatus.RESEARCHING
        run.resume_status = RunStatus.CRITIC_REVIEW
        run.resume_iteration = 2
        self.repository.save_run(run)

        loaded = self.repository.load_run(run.id)

        self.assertEqual(loaded.status, RunStatus.RESEARCHING)
        self.assertEqual(loaded.resume_status, RunStatus.CRITIC_REVIEW)
        self.assertEqual(loaded.resume_iteration, 2)
        self.assertEqual(loaded.plan.tasks[0].id, run.plan.tasks[0].id)
        self.assertEqual(loaded.evidence[0].id, run.evidence[0].id)
        self.assertEqual(loaded.findings[0].evidence_ids, run.findings[0].evidence_ids)
        self.assertEqual(loaded.critique.approved_finding_ids, run.critique.approved_finding_ids)
        self.assertEqual(loaded.report.title, run.report.title)
        self.assertEqual(loaded.events, run.events)

    def test_startup_pauses_runs_left_in_active_phases(self):
        run = make_persisted_run()
        run.status = RunStatus.CRITIC_REVIEW
        run.iteration = 2
        self.repository.save_run(run)

        self.assertEqual(self.repository.pause_interrupted_runs(), 1)
        paused = self.repository.load_run(run.id)
        self.assertEqual(paused.status, RunStatus.PAUSED)
        self.assertEqual(paused.resume_status, RunStatus.CRITIC_REVIEW)
        self.assertEqual(paused.resume_iteration, 2)
        self.assertIn("后端服务已重启", paused.events[-1])

    def test_legacy_cancelled_run_with_unfinished_tasks_can_resume(self):
        run = make_persisted_run("_legacy_cancelled")
        run.status = RunStatus.CANCELLED
        run.iteration = 1
        run.plan.tasks[0].completed = False
        self.repository.save_run(run)

        summary = self.repository.list_runs()[0]

        self.assertEqual(summary["id"], run.id)
        self.assertTrue(summary["can_resume"])
        self.assertEqual(summary["unfinished_tasks"], 1)

    def test_init_db_migrates_old_runs_table_idempotently(self):
        old_engine = create_engine(f"sqlite:///{Path(self.temp.name) / 'legacy.db'}")
        with old_engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE research_runs (id VARCHAR(32) PRIMARY KEY, user_request TEXT NOT NULL, "
                "status VARCHAR(32) NOT NULL, max_iterations INTEGER NOT NULL DEFAULT 3, "
                "iteration INTEGER NOT NULL DEFAULT 0, created_at DATETIME, updated_at DATETIME)"
            )

        init_db(old_engine)
        init_db(old_engine)

        columns = {item["name"] for item in inspect(old_engine).get_columns("research_runs")}
        self.assertIn("resume_status", columns)
        self.assertIn("resume_iteration", columns)
        self.assertIn("report_language", columns)
        self.assertIn("report_language_source", columns)
        old_engine.dispose()

    def test_init_db_migrates_existing_plan_and_report_tables(self):
        old_engine = create_engine(
            f"sqlite:///{Path(self.temp.name) / 'old-related.db'}"
        )
        with old_engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE research_runs (id VARCHAR(32) PRIMARY KEY, user_request TEXT NOT NULL, "
                "status VARCHAR(32) NOT NULL, max_iterations INTEGER NOT NULL DEFAULT 3, "
                "iteration INTEGER NOT NULL DEFAULT 0, created_at DATETIME, updated_at DATETIME)"
            )
            connection.exec_driver_sql(
                "CREATE TABLE research_plans (run_id VARCHAR(32) PRIMARY KEY, "
                "research_question TEXT NOT NULL, scope TEXT NOT NULL, completion_rules JSON)"
            )
            connection.exec_driver_sql(
                "CREATE TABLE reports (run_id VARCHAR(32) PRIMARY KEY, "
                "title TEXT NOT NULL, markdown TEXT NOT NULL, created_at DATETIME, updated_at DATETIME)"
            )
            connection.exec_driver_sql(
                "INSERT INTO research_runs "
                "(id, user_request, status, max_iterations, iteration) "
                "VALUES ('legacy', '旧研究', 'completed', 3, 1)"
            )
            connection.exec_driver_sql(
                "INSERT INTO research_plans "
                "(run_id, research_question, scope, completion_rules) "
                "VALUES ('legacy', '旧问题', '旧范围', '[]')"
            )
            connection.exec_driver_sql(
                "INSERT INTO reports (run_id, title, markdown) "
                "VALUES ('legacy', '旧报告', '# 旧报告')"
            )

        init_db(old_engine)
        init_db(old_engine)

        run_columns = {
            item["name"] for item in inspect(old_engine).get_columns("research_runs")
        }
        plan_columns = {
            item["name"] for item in inspect(old_engine).get_columns("research_plans")
        }
        report_columns = {
            item["name"] for item in inspect(old_engine).get_columns("reports")
        }
        with old_engine.connect() as connection:
            run_values = connection.exec_driver_sql(
                "SELECT report_language, report_language_source FROM research_runs "
                "WHERE id = 'legacy'"
            ).one()
            plan_values = connection.exec_driver_sql(
                "SELECT risk_level FROM research_plans WHERE run_id = 'legacy'"
            ).one()
            reference_heading = connection.exec_driver_sql(
                "SELECT reference_heading FROM reports WHERE run_id = 'legacy'"
            ).scalar_one()

        self.assertIn("report_language", run_columns)
        self.assertIn("research_domains", plan_columns)
        self.assertIn("risk_level", plan_columns)
        self.assertIn("reference_heading", report_columns)
        self.assertEqual(tuple(run_values), ("zh-CN", "legacy"))
        self.assertEqual(tuple(plan_values), ("standard",))
        self.assertEqual(reference_heading, "参考文献")
        old_engine.dispose()

    def test_get_progress_returns_only_new_events(self):
        run = make_persisted_run()
        self.repository.save_run(run)

        progress = self.repository.get_progress(run.id, after_sequence=1)

        self.assertEqual(progress["status"], run.status.value)
        self.assertEqual([item["sequence"] for item in progress["events"]], [2])
        self.assertEqual(progress["events"][0]["message"], "second event")
        self.assertIsNone(self.repository.get_progress("missing"))

    def test_delete_run_removes_owned_rows_and_retains_source_shared_by_another_run(self):
        first = make_persisted_run()
        second = make_persisted_run("_shared")
        second.evidence[0].source = first.evidence[0].source
        second.candidates[0].source = first.evidence[0].source
        second.report = make_report(
            evidence=second.evidence[0],
            blocks=[
                ReportBlock(heading="Summary", text="Summary"),
                ReportBlock(
                    heading="Finding",
                    text="Finding",
                    finding_ids=[second.findings[0].id],
                    evidence_ids=[second.evidence[0].id],
                ),
            ],
        )
        self.repository.save_run(first)
        self.repository.save_run(second)

        self.assertTrue(self.repository.delete_run(first.id))
        self.assertIsNone(self.repository.get_run(first.id))
        self.assertIsNotNone(self.repository.get_run(second.id))
        self.assertIsNotNone(self.repository.load_run(second.id))
        self.assertFalse(self.repository.delete_run("missing"))

        with self.engine.connect() as connection:
            source_count = connection.scalar(select(func.count()).select_from(SourceDocumentModel))
        self.assertEqual(source_count, 1)

        owned_tables = [
            ResearchRunModel, ResearchPlanModel, ResearchTaskModel,
            CandidateEvidenceModel, EvidenceCardModel, FindingModel,
            CriticReviewModel, CriticIssueModel, ReportModel, ReportBlockModel,
            RunEventModel,
        ]
        with self.engine.connect() as connection:
            for model in owned_tables:
                if model is ResearchRunModel:
                    query = select(func.count()).select_from(model).where(model.id == first.id)
                elif model is ResearchPlanModel or model is ReportModel:
                    query = select(func.count()).select_from(model).where(model.run_id == first.id)
                elif model is CriticIssueModel:
                    query = select(func.count()).select_from(model).where(
                        model.review_id.in_(
                            select(CriticReviewModel.id).where(CriticReviewModel.run_id == first.id)
                        )
                    )
                elif model is ReportBlockModel:
                    query = select(func.count()).select_from(model).where(
                        model.report_run_id == first.id
                    )
                else:
                    query = select(func.count()).select_from(model).where(model.run_id == first.id)
                self.assertEqual(connection.scalar(query), 0, model.__tablename__)
            self.assertEqual(connection.scalar(
                select(func.count()).select_from(finding_evidence).where(
                    finding_evidence.c.finding_id == second.findings[0].id
                )), 1)
            remaining_review_ids = select(CriticReviewModel.id).where(CriticReviewModel.run_id == second.id)
            self.assertEqual(connection.scalar(
                select(func.count()).select_from(critic_approved_finding).where(
                    critic_approved_finding.c.review_id.in_(remaining_review_ids)
                )), 1)
            remaining_block_ids = select(ReportBlockModel.id).join(
                ReportModel, ReportBlockModel.report_run_id == ReportModel.run_id
            ).where(ReportModel.run_id == second.id)
            self.assertEqual(connection.scalar(
                select(func.count()).select_from(report_block_finding).where(
                    report_block_finding.c.block_id.in_(remaining_block_ids)
                )), 1)
            self.assertEqual(connection.scalar(
                select(func.count()).select_from(report_block_evidence).where(
                    report_block_evidence.c.block_id.in_(remaining_block_ids)
                )), 1)
            self.assertEqual(
                connection.scalar(select(func.count()).select_from(SourceDocumentModel)), 1)

    def test_init_db_migrates_old_runs_table_idempotently(self):
        old_engine = create_engine(f"sqlite:///{Path(self.temp.name) / 'old.db'}")
        with old_engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE research_runs (id VARCHAR(32) PRIMARY KEY, user_request TEXT NOT NULL, "
                "status VARCHAR(32) NOT NULL, max_iterations INTEGER NOT NULL DEFAULT 3, "
                "iteration INTEGER NOT NULL DEFAULT 0, created_at DATETIME, updated_at DATETIME)"
            )

        init_db(old_engine)
        init_db(old_engine)

        columns = {column["name"] for column in inspect(old_engine).get_columns("research_runs")}
        self.assertIn("resume_status", columns)
        self.assertIn("resume_iteration", columns)
        old_engine.dispose()

    def test_delete_run_clears_all_owned_association_tables(self):
        run = make_persisted_run()
        self.repository.save_run(run)

        self.assertTrue(self.repository.delete_run(run.id))

        with self.engine.connect() as connection:
            for association in (finding_evidence, critic_approved_finding,
                                report_block_finding, report_block_evidence):
                self.assertEqual(
                    connection.scalar(select(func.count()).select_from(association)), 0,
                    association.name,
                )
            for model in (
                ResearchRunModel, ResearchPlanModel, ResearchTaskModel,
                CandidateEvidenceModel, EvidenceCardModel, FindingModel,
                CriticReviewModel, CriticIssueModel, ReportModel, ReportBlockModel,
                RunEventModel, SourceDocumentModel,
            ):
                self.assertEqual(
                    connection.scalar(select(func.count()).select_from(model)), 0,
                    model.__tablename__,
                )

    def test_delete_run_removes_source_documents_used_only_by_that_run(self):
        run = make_persisted_run()
        self.repository.save_run(run)

        self.assertTrue(self.repository.delete_run(run.id))
        with self.engine.connect() as connection:
            source_count = connection.scalar(select(func.count()).select_from(SourceDocumentModel))
        self.assertEqual(source_count, 0)


if __name__ == "__main__":
    unittest.main()

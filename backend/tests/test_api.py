"""HTTP contract tests for frontend research workflows."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.src.research.schemas import ResearchRun, RunStatus
from backend.src.storage import create_db_engine
from backend.tests.test_storage import make_persisted_run


class ResearchApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        engine = create_db_engine(f"sqlite:///{Path(self.temp.name) / 'api.db'}")
        self.starts = []

        class Orchestrator:
            def __init__(inner_self, repository):
                inner_self.repository = repository

            async def run(inner_self, run):
                self.starts.append(run.id)
                run.status = RunStatus.COMPLETED
                run.event("test finished")
                inner_self.repository.save_run(run)
                return run

        self.app = create_app(engine, lambda repository: Orchestrator(repository))
        self.client = TestClient(self.app)

    def test_health_and_list_search_and_pagination(self):
        repository = self.app.state.repository
        first = make_persisted_run()
        second = make_persisted_run("_2")
        second.user_request = "Different topic"
        repository.save_run(first)
        repository.save_run(second)

        self.assertEqual(self.client.get("/api/health").json(), {"status": "ok"})
        response = self.client.get("/api/research-runs", params={"search": "Storage", "page_size": 1})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 1)
        self.assertEqual(response.json()["items"][0]["id"], first.id)

    def test_detail_and_markdown_download(self):
        run = make_persisted_run()
        self.app.state.repository.save_run(run)

        detail = self.client.get(f"/api/research-runs/{run.id}")
        self.assertEqual(detail.status_code, 200)
        body = detail.json()
        self.assertEqual(body["plan"]["tasks"][0]["id"], run.plan.tasks[0].id)
        self.assertEqual(body["evidence"][0]["id"], run.evidence[0].id)
        self.assertEqual(body["findings"][0]["evidence_ids"], run.findings[0].evidence_ids)
        self.assertEqual(body["critiques"][-1]["decision"], "approve")

        progress = self.client.get(
            f"/api/research-runs/{run.id}/progress", params={"after_sequence": 1})
        self.assertEqual(progress.status_code, 200)
        self.assertEqual([event["sequence"] for event in progress.json()["events"]], [2])

    def test_sse_stream_sends_progress_and_closes_on_terminal_run(self):
        run = make_persisted_run()
        self.app.state.repository.save_run(run)

        with self.client.stream("GET", f"/api/research-runs/{run.id}/events") as response:
            body = "".join(response.iter_text())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "text/event-stream; charset=utf-8")
        self.assertIn("event: progress", body)
        self.assertIn('"status": "completed"', body)
        self.assertIn("first event", body)

        report = self.client.get(f"/api/research-runs/{run.id}/report.md")
        self.assertEqual(report.status_code, 200)
        self.assertIn("# Example report", report.text)
        self.assertIn("attachment; filename=\"research-", report.headers["content-disposition"])

    def test_citation_ids_resolve_to_source_urls_and_are_run_scoped(self):
        run = make_persisted_run()
        self.app.state.repository.save_run(run)

        evidence = self.client.get(
            f"/api/research-runs/{run.id}/references/{run.evidence[0].id}")
        self.assertEqual(evidence.status_code, 200)
        self.assertEqual(evidence.json()["reference_type"], "evidence")
        self.assertEqual(evidence.json()["urls"], [str(run.evidence[0].source.url)])
        self.assertEqual(evidence.json()["sources"][0]["evidence_id"], run.evidence[0].id)

        finding = self.client.get(
            f"/api/research-runs/{run.id}/references/{run.findings[0].id}")
        self.assertEqual(finding.status_code, 200)
        self.assertEqual(finding.json()["reference_type"], "finding")
        self.assertEqual(finding.json()["finding_statement"], run.findings[0].statement)
        self.assertEqual(finding.json()["urls"], [str(run.evidence[0].source.url)])

        other_run = make_persisted_run("_other")
        self.app.state.repository.save_run(other_run)
        self.assertEqual(self.client.get(
            f"/api/research-runs/{other_run.id}/references/{run.evidence[0].id}"
        ).status_code, 404)

    def test_create_returns_accepted_and_starts_background_run(self):
        with self.client:
            response = self.client.post("/api/research-runs", json={
                "user_request": "Study a policy change",
                "max_iterations": 2,
            })
            self.assertEqual(response.status_code, 202)
            self.assertEqual(response.json()["report_language"], "en")
            run_id = response.json()["id"]
            self.assertEqual(response.json()["status"], "planning")

        saved = self.app.state.repository.get_run(run_id)
        self.assertEqual(saved.status, "completed")
        self.assertEqual(saved.report_language, "en")
        self.assertEqual(saved.report_language_source, "detected")
        self.assertEqual(self.starts, [run_id])

    def test_create_honors_explicit_language_alias_and_rejects_invalid_tag(self):
        with self.client:
            response = self.client.post("/api/research-runs", json={
                "user_request": "研究一项政策",
                "report_language": "Japanese",
            })
            self.assertEqual(response.status_code, 202, response.text)
            self.assertEqual(response.json()["report_language"], "ja")
            run_id = response.json()["id"]

        saved = self.app.state.repository.get_run(run_id)
        self.assertEqual(saved.report_language, "ja")
        self.assertEqual(saved.report_language_source, "explicit")

        invalid = self.client.post("/api/research-runs", json={
            "user_request": "Research this",
            "report_language": "not a language!",
        })
        self.assertEqual(invalid.status_code, 422)

    def test_detail_and_list_expose_language_quality_and_direction(self):
        run = make_persisted_run()
        run.report_language = "ar"
        run.report_language_source = "explicit"
        run.report.report_language = "ar"
        self.app.state.repository.save_run(run)

        detail = self.client.get(f"/api/research-runs/{run.id}").json()
        summary = self.client.get("/api/research-runs").json()["items"][0]

        self.assertEqual(detail["report_language"], "ar")
        self.assertEqual(detail["report_language_name"], "العربية")
        self.assertEqual(detail["report_direction"], "rtl")
        self.assertEqual(detail["report"]["language"], "ar")
        self.assertEqual(summary["report_language"], "ar")
        self.assertEqual(summary["report_language_quality"], "verified")

    def test_resume_is_idempotent_for_active_and_rejects_terminal(self):
        run = ResearchRun(user_request="Resume me", status=RunStatus.RESEARCHING)
        self.app.state.repository.save_run(run)

        class ActiveTask:
            @staticmethod
            def done():
                return False

        active = ActiveTask()
        self.app.state.run_tasks[run.id] = active
        response = self.client.post(f"/api/research-runs/{run.id}/resume")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(self.starts, [])
        self.app.state.run_tasks.clear()

        self.app.state.repository.save_run(make_persisted_run())
        terminal = self.client.post("/api/research-runs/run_storage/resume")
        self.assertEqual(terminal.status_code, 409)

    def test_resume_rehydrates_and_starts_interrupted_run(self):
        run = make_persisted_run("_interrupted")
        run.status = RunStatus.PAUSED
        run.resume_status = RunStatus.CRITIC_REVIEW
        run.resume_iteration = 2
        self.app.state.repository.save_run(run)

        response = self.client.post(f"/api/research-runs/{run.id}/resume")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["id"], run.id)
        self.assertEqual(self.starts, [run.id])
        saved = self.app.state.repository.load_run(run.id)
        self.assertEqual(saved.status, RunStatus.COMPLETED)
        self.assertEqual(saved.resume_status, RunStatus.CRITIC_REVIEW)
        self.assertEqual(saved.resume_iteration, 2)

    def test_legacy_cancelled_run_continues_from_unfinished_round(self):
        run = make_persisted_run("_legacy_cancelled")
        run.status = RunStatus.CANCELLED
        run.iteration = 1
        run.events = ["研究任务已取消"]
        run.plan.tasks[0].completed = False
        run.critique = None
        run.critiques = []
        self.app.state.repository.save_run(run)

        resumed_runs = []

        class ResumeRecorder:
            def __init__(inner_self, _repository):
                pass

            async def run(inner_self, resumed_run):
                resumed_runs.append((resumed_run.status, resumed_run.iteration))
                resumed_run.resume_status = resumed_run.status
                resumed_run.resume_iteration = resumed_run.iteration
                resumed_run.status = RunStatus.FAILED
                resumed_run.event("resume stub completed")
                self.app.state.repository.save_run(resumed_run)

        self.app.state.orchestrator_factory = ResumeRecorder
        response = self.client.post(f"/api/research-runs/{run.id}/resume")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(resumed_runs, [(RunStatus.RESEARCHING, 0)])
        saved = self.app.state.repository.load_run(run.id)
        self.assertEqual(saved.status, RunStatus.FAILED)
        self.assertEqual(saved.iteration, 0)
        self.assertEqual(saved.resume_status, RunStatus.RESEARCHING)

    def test_legacy_cancelled_run_with_approved_review_continues_to_writing(self):
        run = make_persisted_run("_legacy_approved")
        run.status = RunStatus.CANCELLED
        run.iteration = 1
        run.events = ["研究任务已取消"]
        run.plan.tasks[0].completed = False
        self.app.state.repository.save_run(run)
        observed = []

        class ResumeRecorder:
            def __init__(inner_self, _repository):
                pass

            async def run(inner_self, resumed_run):
                observed.append((resumed_run.status, resumed_run.iteration))
                resumed_run.status = RunStatus.FAILED
                self.app.state.repository.save_run(resumed_run)

        self.app.state.orchestrator_factory = ResumeRecorder
        response = self.client.post(f"/api/research-runs/{run.id}/resume")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(observed, [(RunStatus.WRITING, 1)])

    def test_explicitly_finished_run_is_not_resumable(self):
        run = make_persisted_run("_finished")
        run.status = RunStatus.CANCELLED
        run.events = ["研究任务已结束"]
        run.plan.tasks[0].completed = False
        self.app.state.repository.save_run(run)

        detail = self.client.get(f"/api/research-runs/{run.id}").json()
        response = self.client.post(f"/api/research-runs/{run.id}/resume")

        self.assertFalse(detail["can_resume"])
        self.assertEqual(response.status_code, 409)

    def test_completed_summary_is_not_resumable(self):
        run = make_persisted_run()
        run.status = RunStatus.COMPLETED
        self.app.state.repository.save_run(run)

        summary = self.client.get("/api/research-runs").json()["items"][0]

        self.assertFalse(summary["can_resume"])

    def test_create_app_marks_interrupted_runs_as_paused(self):
        run = ResearchRun(
            user_request="Survive a restart",
            status=RunStatus.RESEARCHING,
            resume_status=RunStatus.CRITIC_REVIEW,
            resume_iteration=2,
            iteration=2,
        )
        self.app.state.repository.save_run(run)

        restarted = create_app(self.app.state.repository.engine, lambda repository: None)
        paused = restarted.state.repository.load_run(run.id)

        self.assertEqual(paused.status, RunStatus.PAUSED)
        self.assertEqual(paused.resume_status, RunStatus.CRITIC_REVIEW)
        self.assertEqual(paused.resume_iteration, 2)
        self.assertIn("后端服务已重启", paused.events[-1])

    def test_shutdown_persists_latest_snapshot_as_paused(self):
        run = ResearchRun(
            user_request="Checkpoint shutdown",
            status=RunStatus.RESEARCHING,
            resume_status=RunStatus.RESEARCHING,
            resume_iteration=1,
            iteration=1,
        )
        self.app.state.repository.save_run(run)

        import asyncio
        pending = asyncio.new_event_loop().create_future()
        self.app.state.run_tasks[run.id] = pending
        self.app.state.run_snapshots[run.id] = run.model_copy(deep=True)
        lifespan = self.app.router.lifespan_context(self.app)
        async def stop_app():
            await lifespan.__aenter__()
            await lifespan.__aexit__(None, None, None)
        asyncio.run(stop_app())

        paused = self.app.state.repository.load_run(run.id)
        self.assertEqual(paused.status, RunStatus.PAUSED)
        self.assertEqual(paused.resume_status, RunStatus.RESEARCHING)
        self.assertEqual(paused.resume_iteration, 1)

    def test_failed_initialization_exposes_safe_error_and_can_retry(self):
        def fail_initialization(_repository):
            raise AttributeError("Configuration has no attribute use_tool_calling")

        self.app.state.orchestrator_factory = fail_initialization
        with self.client:
            response = self.client.post("/api/research-runs", json={
                "user_request": "A task that fails during initialization",
            })
            run_id = response.json()["id"]
            for _ in range(40):
                saved = self.app.state.repository.get_run(run_id)
                if saved.status == "failed":
                    break
                import time
                time.sleep(0.025)

            self.assertEqual(saved.status, "failed")
            self.assertIn("AttributeError", saved.events[-1].message)
            self.assertIn("use_tool_calling", saved.events[-1].message)
            self.assertNotIn("Bearer", saved.events[-1].message)
            detail = self.client.get(f"/api/research-runs/{run_id}").json()
            self.assertIn("AttributeError", detail["error"])
            self.assertIn("use_tool_calling", detail["error"])

            class RetryOrchestrator:
                def __init__(inner_self, repository):
                    inner_self.repository = repository

                async def run(inner_self, run):
                    self.starts.append(run.id)
                    run.status = RunStatus.COMPLETED
                    run.event("retry completed")
                    inner_self.repository.save_run(run)

            self.app.state.orchestrator_factory = RetryOrchestrator
            retried = self.client.post(f"/api/research-runs/{run_id}/resume")
            self.assertEqual(retried.status_code, 202)
            self.assertEqual(retried.json()["status"], "planning")

        self.assertEqual(self.app.state.repository.get_run(run_id).status, "completed")

    def test_public_error_redacts_credentials(self):
        from backend.src.api.research import _public_error

        message = _public_error(RuntimeError("Bearer secret-token api_key=private-value"))
        self.assertIn("RuntimeError", message)
        self.assertNotIn("secret-token", message)
        self.assertNotIn("private-value", message)

    def test_cancel_marks_interrupted_run_terminal(self):
        run = ResearchRun(user_request="Cancel me", status=RunStatus.RESEARCHING)
        self.app.state.repository.save_run(run)

        response = self.client.post(f"/api/research-runs/{run.id}/cancel")

        self.assertEqual(response.status_code, 202)
        saved = self.app.state.repository.get_run(run.id)
        self.assertEqual(saved.status, "cancelled")
        self.assertEqual(saved.events[-1].message, "研究任务已结束")

    def test_cancel_signals_an_active_background_task(self):
        run = ResearchRun(user_request="Cancel active", status=RunStatus.RESEARCHING)
        self.app.state.repository.save_run(run)

        class ActiveTask:
            cancelled = False

            @staticmethod
            def done():
                return False

            def cancel(inner_self):
                inner_self.cancelled = True

        active = ActiveTask()
        self.app.state.run_tasks[run.id] = active
        response = self.client.post(f"/api/research-runs/{run.id}/cancel")

        self.assertEqual(response.status_code, 202)
        self.assertTrue(active.cancelled)

    def test_delete_removes_run_and_rejects_active_runs(self):
        run = make_persisted_run()
        self.app.state.repository.save_run(run)

        response = self.client.delete(f"/api/research-runs/{run.id}")
        self.assertEqual(response.status_code, 204)
        self.assertIsNone(self.app.state.repository.get_run(run.id))
        self.assertEqual(self.client.get(f"/api/research-runs/{run.id}").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/research-runs/{run.id}").status_code, 404)

        active_run = ResearchRun(user_request="Active run", status=RunStatus.RESEARCHING)
        self.app.state.repository.save_run(active_run)

        class ActiveTask:
            @staticmethod
            def done():
                return False

        self.app.state.run_tasks[active_run.id] = ActiveTask()
        conflict = self.client.delete(f"/api/research-runs/{active_run.id}")
        self.assertEqual(conflict.status_code, 409)
        self.assertIsNotNone(self.app.state.repository.get_run(active_run.id))

    def test_invalid_or_missing_run_responses(self):
        self.assertEqual(self.client.get("/api/research-runs/not-found").status_code, 404)
        self.assertEqual(self.client.get("/api/research-runs/not-found/progress").status_code, 404)
        self.assertEqual(self.client.get("/api/research-runs", params={"status": "bogus"}).status_code, 422)
        self.assertEqual(self.client.post("/api/research-runs", json={"user_request": ""}).status_code, 422)


if __name__ == "__main__":
    unittest.main()

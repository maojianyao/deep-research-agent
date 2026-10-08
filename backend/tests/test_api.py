"""HTTP contract tests for frontend research workflows."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.src.api.main import create_app
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

        report = self.client.get(f"/api/research-runs/{run.id}/report.md")
        self.assertEqual(report.status_code, 200)
        self.assertIn("# Example report", report.text)
        self.assertIn("attachment; filename=\"research-", report.headers["content-disposition"])

    def test_create_returns_accepted_and_starts_background_run(self):
        with self.client:
            response = self.client.post("/api/research-runs", json={
                "user_request": "Study a policy change",
                "max_iterations": 2,
            })
            self.assertEqual(response.status_code, 202)
            run_id = response.json()["id"]
            self.assertEqual(response.json()["status"], "planning")

        saved = self.app.state.repository.get_run(run_id)
        self.assertEqual(saved.status, "completed")
        self.assertEqual(self.starts, [run_id])

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
        run.status = RunStatus.RESEARCHING
        self.app.state.repository.save_run(run)

        response = self.client.post(f"/api/research-runs/{run.id}/resume")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["id"], run.id)
        self.assertEqual(self.starts, [run.id])

    def test_cancel_marks_interrupted_run_terminal(self):
        run = ResearchRun(user_request="Cancel me", status=RunStatus.RESEARCHING)
        self.app.state.repository.save_run(run)

        response = self.client.post(f"/api/research-runs/{run.id}/cancel")

        self.assertEqual(response.status_code, 202)
        saved = self.app.state.repository.get_run(run.id)
        self.assertEqual(saved.status, "cancelled")
        self.assertEqual(saved.events[-1].message, "研究任务已取消")

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

    def test_invalid_or_missing_run_responses(self):
        self.assertEqual(self.client.get("/api/research-runs/not-found").status_code, 404)
        self.assertEqual(self.client.get("/api/research-runs/not-found/progress").status_code, 404)
        self.assertEqual(self.client.get("/api/research-runs", params={"status": "bogus"}).status_code, 422)
        self.assertEqual(self.client.post("/api/research-runs", json={"user_request": ""}).status_code, 422)


if __name__ == "__main__":
    unittest.main()

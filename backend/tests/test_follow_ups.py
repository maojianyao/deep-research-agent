"""HTTP contract tests for persistent report follow-up threads."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.src.research.schemas import ReportBlock, RunStatus
from backend.src.storage import create_db_engine
from backend.tests.factories import make_report
from backend.tests.test_storage import make_persisted_run


class FakeAnswerer:
    def __init__(self):
        self.calls = []

    async def answer(self, passage, history):
        self.calls.append((passage, history))
        return "**重点**：选区讨论的是报告摘要。"

    async def stream(self, passage, history):
        self.calls.append((passage, history))
        yield "**重点**：选区讨论的是报告摘要。"


class FollowUpApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database_url = f"sqlite:///{Path(self.temp.name) / 'follow-ups.db'}"
        self.answerer = FakeAnswerer()
        self.app = create_app(
            create_db_engine(self.database_url),
            orchestrator_factory=lambda repository: None,
            follow_up_answerer_factory=lambda: self.answerer,
        )
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def test_first_question_persists_thread_anchor_and_messages_across_app_recreation(self):
        run = make_persisted_run()
        self.app.state.repository.save_run(run)
        detail = self.client.get(f"/api/research-runs/{run.id}").json()
        anchor = {
            "text": "Summary",
            "start": 23,
            "end": 30,
            "prefix": "",
            "suffix": " text",
            "report_digest": detail["report"]["anchor_digest"],
        }

        response = self.client.post(
            f"/api/research-runs/{run.id}/follow-ups",
            json={"anchor": anchor, "question": "这一段是什么含义？"},
        )

        self.assertEqual(response.status_code, 201)
        thread = response.json()
        self.assertEqual(thread["anchor"], anchor)
        thread = self._wait_for_completed_thread(run.id, thread["id"])
        self.assertEqual(
            [(item["role"], item["content"], item["status"]) for item in thread["messages"]],
            [
                ("user", "这一段是什么含义？", "completed"),
                ("assistant", "**重点**：选区讨论的是报告摘要。", "completed"),
            ],
        )
        self.assertEqual(self.answerer.calls[0][0], "Summary")
        self.assertEqual(
            [(item["role"], item["content"]) for item in self.answerer.calls[0][1]],
            [("user", "这一段是什么含义？")],
        )

        recreated = create_app(
            create_db_engine(self.database_url),
            orchestrator_factory=lambda repository: None,
            follow_up_answerer_factory=FakeAnswerer,
        )
        restored = TestClient(recreated).get(
            f"/api/research-runs/{run.id}/follow-ups"
        )

        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.json()["items"], [thread])

    def test_rejects_ineligible_reports_invalid_anchors_and_out_of_limit_inputs(self):
        unfinished = make_persisted_run("_unfinished")
        unfinished.status = RunStatus.RESEARCHING
        self.app.state.repository.save_run(unfinished)
        no_report = make_persisted_run("_no_report")
        no_report.report = None
        self.app.state.repository.save_run(no_report)
        completed = make_persisted_run("_validation")
        self.app.state.repository.save_run(completed)
        digest = self.client.get(
            f"/api/research-runs/{completed.id}"
        ).json()["report"]["anchor_digest"]
        valid_anchor = {
            "text": "Summary",
            "start": 23,
            "end": 30,
            "prefix": "",
            "suffix": " text",
            "report_digest": digest,
        }

        def create(run_id, anchor=valid_anchor, question="为什么？"):
            return self.client.post(
                f"/api/research-runs/{run_id}/follow-ups",
                json={"anchor": anchor, "question": question},
            )

        cases = [
            ("unfinished", create(unfinished.id), 409),
            ("missing report", create(no_report.id), 409),
            ("missing run", create("missing"), 404),
            ("empty selection", create(completed.id, {**valid_anchor, "text": "", "end": 0}), 422),
            ("oversized selection", create(
                completed.id,
                {**valid_anchor, "text": "x" * 8001, "start": 0, "end": 8001},
            ), 422),
            ("mismatched offsets", create(completed.id, {**valid_anchor, "end": 8}), 422),
            ("offsets outside selected text", create(
                completed.id, {**valid_anchor, "start": 1, "end": 8},
            ), 422),
            ("outside report", create(completed.id, {**valid_anchor, "text": "External quote"}), 422),
            ("stale digest", create(
                completed.id, {**valid_anchor, "report_digest": "0" * 64},
            ), 422),
            ("blank question", create(completed.id, question="   "), 422),
            ("oversized question", create(completed.id, question="问" * 2001), 422),
        ]

        for label, response, expected_status in cases:
            with self.subTest(label=label):
                self.assertEqual(response.status_code, expected_status, response.text)

        self.assertEqual(self.answerer.calls, [])
        self.assertEqual(
            self.client.get(
                f"/api/research-runs/{completed.id}/follow-ups"
            ).json()["items"],
            [],
        )

    def test_selection_can_include_an_evidence_id_from_the_renderable_report(self):
        run = make_persisted_run("_citation")
        run.report = make_report(
            blocks=[
                ReportBlock(
                    heading="Summary",
                    text="See evidence_storage for details",
                )
            ]
        )
        self.app.state.repository.save_run(run)
        detail = self.client.get(f"/api/research-runs/{run.id}").json()
        report_text = "Example report Summary See evidence_storage for details"
        start = report_text.index("evidence_storage")
        anchor = {
            "text": "evidence_storage",
            "start": start,
            "end": start + len("evidence_storage"),
            "prefix": "",
            "suffix": " for details",
            "report_digest": detail["report"]["anchor_digest"],
        }

        response = self.client.post(
            f"/api/research-runs/{run.id}/follow-ups",
            json={"anchor": anchor, "question": "这条证据支持什么？"},
        )

        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["anchor"], anchor)

    def test_accepts_selection_after_a_rendered_markdown_table(self):
        run = make_persisted_run("_table")
        run.report.blocks = [ReportBlock(
            heading="Summary",
            text=(
                "Intro\n\n"
                "| A | B |\n"
                "| --- | --- |\n"
                "| 1 | 2 |\n\n"
                "| C |\n"
                "| --- |\n"
                "| 3 |\n\n"
                "After table"
            ),
        )]
        self.app.state.repository.save_run(run)
        detail = self.client.get(f"/api/research-runs/{run.id}").json()
        rendered_text = "Example report Summary Intro A B 1 2 C 3 After table"
        start = rendered_text.index("After table")
        anchor = {
            "text": "After table",
            "start": start,
            "end": start + len("After table"),
            "prefix": "Intro A B 1 2 C 3",
            "suffix": "",
            "report_digest": detail["report"]["anchor_digest"],
        }

        response = self.client.post(
            f"/api/research-runs/{run.id}/follow-ups",
            json={"anchor": anchor, "question": "表格说明了什么？"},
        )

        self.assertEqual(response.status_code, 201, response.text)

    def test_accepts_selection_after_underscore_emphasis_in_rendered_markdown(self):
        run = make_persisted_run("_emphasis")
        run.report.blocks = [ReportBlock(
            heading="Summary",
            text="See __key__ _italic_ evidence_storage for details",
        )]
        self.app.state.repository.save_run(run)
        detail = self.client.get(f"/api/research-runs/{run.id}").json()
        rendered_text = (
            "Example report Summary See key italic evidence_storage for details"
        )
        start = rendered_text.index("details")
        anchor = {
            "text": "details",
            "start": start,
            "end": start + len("details"),
            "prefix": "",
            "suffix": "",
            "report_digest": detail["report"]["anchor_digest"],
        }

        response = self.client.post(
            f"/api/research-runs/{run.id}/follow-ups",
            json={"anchor": anchor, "question": "这里指什么？"},
        )

        self.assertEqual(response.status_code, 201, response.text)

    def test_accepts_selection_after_a_literal_markdown_code_block(self):
        run = make_persisted_run("_code")
        run.report.blocks = [ReportBlock(
            heading="Summary",
            text="Code\n\n```text\na * b\n```\n\nLiteral `c * d`\n\nAfter code",
        )]
        self.app.state.repository.save_run(run)
        detail = self.client.get(f"/api/research-runs/{run.id}").json()
        rendered_text = "Example report Summary Code a * b Literal c * d After code"
        start = rendered_text.index("After code")
        anchor = {
            "text": "After code",
            "start": start,
            "end": start + len("After code"),
            "prefix": "",
            "suffix": "",
            "report_digest": detail["report"]["anchor_digest"],
        }

        response = self.client.post(
            f"/api/research-runs/{run.id}/follow-ups",
            json={"anchor": anchor, "question": "代码输出是什么？"},
        )

        self.assertEqual(response.status_code, 201, response.text)

    def test_deleting_a_run_cascades_its_follow_up_threads(self):
        run = make_persisted_run("_delete_follow_up")
        self.app.state.repository.save_run(run)
        detail = self.client.get(f"/api/research-runs/{run.id}").json()
        anchor = {
            "text": "Summary",
            "start": 23,
            "end": 30,
            "prefix": "",
            "suffix": " text",
            "report_digest": detail["report"]["anchor_digest"],
        }
        created = self.client.post(
            f"/api/research-runs/{run.id}/follow-ups",
            json={"anchor": anchor, "question": "会保留吗？"},
        )
        self.assertEqual(created.status_code, 201, created.text)

        self.assertTrue(self.app.state.repository.delete_run(run.id))

        self.assertEqual(
            self.app.state.follow_up_repository.list_threads(run.id),
            [],
        )

    def _wait_for_completed_thread(self, run_id, thread_id):
        import time
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            thread = self.client.get(
                f"/api/research-runs/{run_id}/follow-ups/{thread_id}"
            ).json()
            if thread["messages"][-1]["status"] == "completed":
                return thread
            time.sleep(0.02)
        self.fail("follow-up generation did not complete")


if __name__ == "__main__":
    unittest.main()

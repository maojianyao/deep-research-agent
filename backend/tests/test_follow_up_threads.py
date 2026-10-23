"""HTTP contract tests for multiple report-bound follow-up threads."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect

from backend.main import create_app
from backend.src.research.schemas import ReportBlock
from backend.src.services.follow_up import normalize_report_text
from backend.src.storage import create_db_engine, init_db
from backend.tests.test_storage import make_persisted_run


class ImmediateAnswerer:
    async def stream(self, passage, history):
        yield "回答"


class FollowUpThreadsApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database_url = f"sqlite:///{Path(self.temp.name) / 'threads.db'}"
        self.app = create_app(
            create_db_engine(self.database_url),
            orchestrator_factory=lambda repository: None,
            follow_up_answerer_factory=ImmediateAnswerer,
        )

    def test_multiple_threads_reject_overlaps_and_expand_only_the_selected_one(self):
        run = make_persisted_run("_multiple")
        self.app.state.repository.save_run(run)

        with TestClient(self.app) as client:
            detail = client.get(f"/api/research-runs/{run.id}").json()
            first = self._create(client, run.id, detail, "Summary", 23)
            second = self._create(client, run.id, detail, "Example", 0)
            self.assertNotEqual(first["id"], second["id"])
            listed = client.get(f"/api/research-runs/{run.id}/follow-ups").json()["items"]
            self.assertEqual(
                {item["id"]: item["is_minimized"] for item in listed},
                {first["id"]: True, second["id"]: False},
            )

            duplicate = self._post(client, run.id, detail, "Summary", 23, expected=None)
            crossing = self._post(
                client, run.id, detail, "Example report Summary Summary", 0, expected=None
            )
            self.assertEqual(duplicate.status_code, 409, duplicate.text)
            self.assertEqual(crossing.status_code, 409, crossing.text)

            expanded = client.post(
                f"/api/research-runs/{run.id}/follow-ups/{first['id']}/state",
                json={"minimized": False},
            )
            self.assertEqual(expanded.status_code, 200, expanded.text)
            states = {
                item["id"]: item["is_minimized"] for item in expanded.json()["items"]
            }
            self.assertEqual(states, {first["id"]: False, second["id"]: True})

    def test_escaped_anchor_and_expanded_state_survive_app_recreation(self):
        run = make_persisted_run("_persistent_state")
        run.report.blocks = [
            ReportBlock(
                heading="Summary",
                text='He said "quoted" & left',
            )
        ]
        self.app.state.repository.save_run(run)

        with TestClient(self.app) as client:
            detail = client.get(f"/api/research-runs/{run.id}").json()
            rendered = 'Example report Summary He said "quoted" & left'
            selection = '"quoted" & left'
            first = self._create(
                client, run.id, detail, selection, rendered.index(selection)
            )
            second = self._create(client, run.id, detail, "Example", 0)
            expanded = client.post(
                f"/api/research-runs/{run.id}/follow-ups/{first['id']}/state",
                json={"minimized": False},
            )
            self.assertEqual(expanded.status_code, 200, expanded.text)

        recreated = create_app(
            create_db_engine(self.database_url),
            orchestrator_factory=lambda repository: None,
            follow_up_answerer_factory=ImmediateAnswerer,
        )
        with TestClient(recreated) as client:
            items = client.get(
                f"/api/research-runs/{run.id}/follow-ups"
            ).json()["items"]

        by_id = {item["id"]: item for item in items}
        self.assertEqual(by_id[first["id"]]["anchor"]["text"], selection)
        self.assertFalse(by_id[first["id"]]["is_minimized"])
        self.assertTrue(by_id[second["id"]]["is_minimized"])

    def test_init_db_adds_minimized_state_to_existing_thread_table(self):
        legacy = create_engine(f"sqlite:///{Path(self.temp.name) / 'legacy-threads.db'}")
        with legacy.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE follow_up_threads (id VARCHAR(40) PRIMARY KEY)"
            )

        init_db(legacy)

        columns = {
            item["name"] for item in inspect(legacy).get_columns("follow_up_threads")
        }
        self.assertIn("is_minimized", columns)
        legacy.dispose()

    def test_cross_markdown_anchor_round_trips_through_http_and_recreation(self):
        run = make_persisted_run("_markdown_anchor")
        run.report.blocks = [ReportBlock(
            heading="Heading",
            text=(
                "Paragraph text\n\n"
                "- outer\n"
                "  - nested\n\n"
                "| A | B |\n"
                "| --- | --- |\n"
                "| 1 | 2 |\n\n"
                "```text\n"
                "code line\n"
                "```\n\n"
                "Tail"
            ),
        )]
        self.app.state.repository.save_run(run)
        rendered = normalize_report_text(run.to_markdown())

        with TestClient(self.app) as client:
            detail = client.get(f"/api/research-runs/{run.id}").json()
            selection = "Heading Paragraph text outer nested A B 1 2 code line Tail"
            first = self._create(
                client,
                run.id,
                detail,
                selection,
                rendered.index(selection),
            )
            self.assertEqual(first["anchor"]["text"], selection)
            self.assertEqual(
                first["anchor"]["end"] - first["anchor"]["start"],
                len(selection),
            )

        recreated = create_app(
            create_db_engine(self.database_url),
            orchestrator_factory=lambda repository: None,
            follow_up_answerer_factory=ImmediateAnswerer,
        )
        with TestClient(recreated) as client:
            restored = client.get(
                f"/api/research-runs/{run.id}/follow-ups/{first['id']}"
            ).json()
        self.assertEqual(restored["anchor"], first["anchor"])

    def _create(self, client, run_id, detail, text, start):
        response = self._post(client, run_id, detail, text, start, expected=201)
        return response.json()

    def _post(self, client, run_id, detail, text, start, expected):
        anchor = {
            "text": text,
            "start": start,
            "end": start + len(text),
            "prefix": "",
            "suffix": "",
            "report_digest": detail["report"]["anchor_digest"],
        }
        response = client.post(
            f"/api/research-runs/{run_id}/follow-ups",
            json={"anchor": anchor, "question": "请解释。"},
        )
        if expected is not None:
            self.assertEqual(response.status_code, expected, response.text)
        return response


if __name__ == "__main__":
    unittest.main()

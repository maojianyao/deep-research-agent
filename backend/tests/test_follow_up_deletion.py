"""HTTP contract tests for deleting follow-up conversations and their owner runs."""

from __future__ import annotations

import asyncio
import tempfile
import threading
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.src.storage import create_db_engine
from backend.tests.test_storage import make_persisted_run


class TrackedStream:
    def __init__(self, release: threading.Event):
        self.release = release
        self.closed = threading.Event()

    async def run(self):
        try:
            yield "第一段"
            while not self.release.is_set():
                await asyncio.sleep(0.01)
            yield "第二段"
        finally:
            self.closed.set()


class TrackingAnswerer:
    def __init__(self):
        self.streams = []

    async def stream(self, passage, history):
        stream = TrackedStream(threading.Event())
        self.streams.append(stream)
        async for chunk in stream.run():
            yield chunk


class FollowUpDeletionApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database_url = f"sqlite:///{Path(self.temp.name) / 'deletions.db'}"
        self.answerer = TrackingAnswerer()
        self.app = create_app(
            create_db_engine(self.database_url),
            orchestrator_factory=lambda repository: None,
            follow_up_answerer_factory=lambda: self.answerer,
        )

    def test_deleting_thread_cancels_generation_and_preserves_siblings_and_report(self):
        run = make_persisted_run("_delete_thread")
        self.app.state.repository.save_run(run)

        with TestClient(self.app) as client:
            report_before = client.get(f"/api/research-runs/{run.id}/report.md").content
            detail = client.get(f"/api/research-runs/{run.id}").json()
            first = self._create_thread(client, run.id, detail, "Summary", 23)
            second = self._create_thread(client, run.id, detail, "Example", 0)
            self._wait_for_streams(2)

            response = client.delete(
                f"/api/research-runs/{run.id}/follow-ups/{first['id']}"
            )

            self.assertEqual(response.status_code, 204, response.text)
            self.assertTrue(self.answerer.streams[0].closed.wait(1))
            self.assertEqual(
                client.get(
                    f"/api/research-runs/{run.id}/follow-ups/{first['id']}"
                ).status_code,
                404,
            )
            items = client.get(
                f"/api/research-runs/{run.id}/follow-ups"
            ).json()["items"]
            self.assertEqual([item["id"] for item in items], [second["id"]])

            self.answerer.streams[1].release.set()
            self._wait_for_thread_status(
                client, run.id, second["id"], "第一段第二段", "completed"
            )
            duplicate = client.delete(
                f"/api/research-runs/{run.id}/follow-ups/{first['id']}"
            )
            self.assertEqual(duplicate.status_code, 404)
            replacement = self._create_thread(client, run.id, detail, "Summary", 23)
            self.assertNotEqual(replacement["id"], first["id"])
            self.assertEqual(
                client.get(f"/api/research-runs/{run.id}/report.md").content,
                report_before,
            )

    def test_deleting_research_run_cancels_owned_streams_and_keeps_other_runs(self):
        first_run = make_persisted_run("_delete_owner")
        second_run = make_persisted_run("_keep_owner")
        self.app.state.repository.save_run(first_run)
        self.app.state.repository.save_run(second_run)

        with TestClient(self.app) as client:
            first_detail = client.get(f"/api/research-runs/{first_run.id}").json()
            second_detail = client.get(f"/api/research-runs/{second_run.id}").json()
            first = self._create_thread(client, first_run.id, first_detail, "Summary", 23)
            second = self._create_thread(
                client, second_run.id, second_detail, "Summary", 23
            )
            self._wait_for_streams(2)

            response = client.delete(f"/api/research-runs/{first_run.id}")

            self.assertEqual(response.status_code, 204, response.text)
            self.assertTrue(self.answerer.streams[0].closed.wait(1))
            self.assertFalse(self.answerer.streams[1].closed.is_set())
            self.assertEqual(
                client.get(f"/api/research-runs/{first_run.id}").status_code,
                404,
            )
            self.assertEqual(
                client.get(f"/api/research-runs/{second_run.id}").status_code,
                200,
            )
            self.assertEqual(
                client.get(
                    f"/api/research-runs/{second_run.id}/follow-ups/{second['id']}"
                ).status_code,
                200,
            )
            self.assertIsNotNone(first)

            self.answerer.streams[1].release.set()
            self._wait_for_thread_status(
                client,
                second_run.id,
                second["id"],
                "第一段第二段",
                "completed",
            )

    def _create_thread(self, client, run_id, detail, text, start):
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
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def _wait_for_streams(self, count):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if len(self.answerer.streams) >= count:
                return
            time.sleep(0.02)
        self.fail(f"expected {count} active streams")

    def _wait_for_thread_status(self, client, run_id, thread_id, content, status):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            thread = client.get(
                f"/api/research-runs/{run_id}/follow-ups/{thread_id}"
            ).json()
            assistant = thread["messages"][-1]
            if assistant["content"] == content and assistant["status"] == status:
                return
            time.sleep(0.02)
        self.fail(f"thread did not reach {status}")


if __name__ == "__main__":
    unittest.main()

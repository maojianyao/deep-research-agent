"""HTTP contract tests for durable background follow-up generation."""

from __future__ import annotations

import asyncio
import tempfile
import threading
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.src.services.follow_up import report_anchor_digest
from backend.src.storage import create_db_engine
from backend.tests.test_storage import make_persisted_run


class ControlledStreamingAnswerer:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls = []

    async def stream(self, passage, history):
        self.calls.append((passage, history))
        self.started.set()
        yield "第一段"
        while not self.release.is_set():
            await asyncio.sleep(0.01)
        yield "第二段"


class FailingStreamingAnswerer:
    async def stream(self, passage, history):
        yield "已经收到的部分"
        raise RuntimeError("upstream model failure")


class FollowUpStreamingApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database_url = f"sqlite:///{Path(self.temp.name) / 'streaming.db'}"
        self.answerers = []

        def answerer_factory():
            answerer = ControlledStreamingAnswerer()
            self.answerers.append(answerer)
            return answerer

        self.app = create_app(
            create_db_engine(self.database_url),
            orchestrator_factory=lambda repository: None,
            follow_up_answerer_factory=answerer_factory,
        )

    def test_generation_continues_without_a_browser_stream_and_persists_each_chunk(self):
        run = make_persisted_run("_background")
        self.app.state.repository.save_run(run)

        with TestClient(self.app) as client:
            detail = client.get(f"/api/research-runs/{run.id}").json()
            anchor = {
                "text": "Summary",
                "start": 23,
                "end": 30,
                "prefix": "",
                "suffix": " text",
                "report_digest": detail["report"]["anchor_digest"],
            }
            response = client.post(
                f"/api/research-runs/{run.id}/follow-ups",
                json={"anchor": anchor, "question": "请解释这一段。", "skip": "ignored"},
            )

            self.assertEqual(response.status_code, 201, response.text)
            created = response.json()
            self.assertGreaterEqual(created["stream_cursor"], 1)
            self.assertEqual(
                [(item["role"], item["status"]) for item in created["messages"]],
                [("user", "completed"), ("assistant", "generating")],
            )
            answerer = self.answerers[0]
            self.assertTrue(answerer.started.wait(1))

            first_chunk = self._wait_for_assistant(client, run.id, "第一段", "generating")
            self.assertEqual(first_chunk["content"], "第一段")
            self.assertEqual(first_chunk["status"], "generating")

            answerer.release.set()
            completed = self._wait_for_assistant(client, run.id, "第一段第二段", "completed")
            self.assertEqual(completed["content"], "第一段第二段")
            self.assertEqual(completed["status"], "completed")

    def test_sse_emits_ordered_typed_events_and_resumes_after_cursor(self):
        run = make_persisted_run("_sse")
        self.app.state.repository.save_run(run)

        with TestClient(self.app) as client:
            created = self._start_thread(client, run.id)
            thread_id = created["id"]
            answerer = self.answerers[0]
            self.assertTrue(answerer.started.wait(1))
            self._wait_for_assistant(client, run.id, "第一段", "generating")
            snapshot = client.get(
                f"/api/research-runs/{run.id}/follow-ups/{thread_id}"
            ).json()
            cursor = snapshot["stream_cursor"]
            answerer.release.set()
            self._wait_for_assistant(client, run.id, "第一段第二段", "completed")

            with client.stream(
                "GET",
                f"/api/research-runs/{run.id}/follow-ups/{thread_id}/events",
                params={"after_sequence": cursor},
            ) as response:
                body = "".join(response.iter_text())

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["content-type"], "text/event-stream; charset=utf-8")
            self.assertNotIn('"content": "第一段"', body)
            self.assertIn('"type": "delta"', body)
            self.assertIn('"content": "第二段"', body)
            self.assertIn('"type": "completed"', body)
            event_ids = [
                int(line.removeprefix("id: "))
                for line in body.splitlines() if line.startswith("id: ")
            ]
            self.assertEqual(event_ids, sorted(event_ids))
            self.assertGreater(event_ids[0], cursor)

    def test_client_disconnect_does_not_cancel_generation_and_cursor_resumes_delivery(self):
        run = make_persisted_run("_disconnect")
        self.app.state.repository.save_run(run)

        with TestClient(self.app) as client:
            created = self._start_thread(client, run.id)
            thread_id = created["id"]
            answerer = self.answerers[0]
            self.assertTrue(answerer.started.wait(1))
            self._wait_for_assistant(client, run.id, "第一段", "generating")

            self.assertTrue(self._disconnect_after_delta(
                client,
                f"/api/research-runs/{run.id}/follow-ups/{thread_id}/events",
            ))
            current = client.get(
                f"/api/research-runs/{run.id}/follow-ups/{thread_id}"
            ).json()
            cursor = current["stream_cursor"]
            self.assertEqual(current["messages"][-1]["content"], "第一段")
            self.assertEqual(current["messages"][-1]["status"], "generating")

            answerer.release.set()
            completed = self._wait_for_thread_assistant(
                client, run.id, thread_id, "第一段第二段", "completed"
            )
            self.assertEqual(completed["content"], "第一段第二段")

            with client.stream(
                "GET",
                f"/api/research-runs/{run.id}/follow-ups/{thread_id}/events",
                params={"after_sequence": cursor},
            ) as response:
                resumed = "".join(response.iter_text())

            self.assertNotIn('"content": "第一段"', resumed)
            self.assertIn('"type": "delta"', resumed)
            self.assertIn('"content": "第二段"', resumed)
            self.assertIn('"type": "completed"', resumed)

    def test_same_thread_rejects_second_question_while_generating(self):
        run = make_persisted_run("_busy")
        self.app.state.repository.save_run(run)

        with TestClient(self.app) as client:
            created = self._start_thread(client, run.id)
            thread_id = created["id"]
            answerer = self.answerers[0]
            self.assertTrue(answerer.started.wait(1))
            self._wait_for_assistant(client, run.id, "第一段", "generating")

            conflict = client.post(
                f"/api/research-runs/{run.id}/follow-ups/{thread_id}/questions",
                json={"question": "第二个问题"},
            )

            self.assertEqual(conflict.status_code, 409, conflict.text)
            current = client.get(
                f"/api/research-runs/{run.id}/follow-ups/{thread_id}"
            ).json()
            self.assertEqual(
                [item["role"] for item in current["messages"]],
                ["user", "assistant"],
            )
            answerer.release.set()
            self._wait_for_assistant(client, run.id, "第一段第二段", "completed")

            follow_up = client.post(
                f"/api/research-runs/{run.id}/follow-ups/{thread_id}/questions",
                json={"question": "生成完成后可以继续追问吗？"},
            )
            self.assertEqual(follow_up.status_code, 201, follow_up.text)
            self._wait_for_thread_assistant(
                client, run.id, thread_id, "第一段第二段", "completed"
            )
            current = client.get(
                f"/api/research-runs/{run.id}/follow-ups/{thread_id}"
            ).json()
            self.assertEqual(
                [item["role"] for item in current["messages"]],
                ["user", "assistant", "user", "assistant"],
            )

    def test_question_after_completion_starts_when_previous_task_is_still_exiting(self):
        run = make_persisted_run("_completion_boundary")
        self.app.state.repository.save_run(run)

        with TestClient(self.app) as client:
            created = self._start_thread(client, run.id)
            thread_id = created["id"]
            answerer = self.answerers[0]
            self.assertTrue(answerer.started.wait(1))
            self._wait_for_thread_assistant(
                client, run.id, thread_id, "第一段", "generating"
            )

            repository = self.app.state.follow_up_repository
            original_complete = repository.complete_message
            completion_persisted = threading.Event()
            release_completion = threading.Event()

            def complete_after_delay(thread_id, message_id):
                sequence = original_complete(thread_id, message_id)
                completion_persisted.set()
                if not release_completion.wait(2):
                    raise TimeoutError("test did not release completion task")
                return sequence

            repository.complete_message = complete_after_delay
            answerer.release.set()
            self.assertTrue(completion_persisted.wait(2))

            follow_up = client.post(
                f"/api/research-runs/{run.id}/follow-ups/{thread_id}/questions",
                json={"question": "完成后立即继续追问。"},
            )
            self.assertEqual(follow_up.status_code, 201, follow_up.text)
            release_completion.set()

            self._wait_for_thread_assistant(
                client, run.id, thread_id, "第一段第二段", "completed"
            )
            current = client.get(
                f"/api/research-runs/{run.id}/follow-ups/{thread_id}"
            ).json()
            self.assertEqual(
                [item["status"] for item in current["messages"]],
                ["completed", "completed", "completed", "completed"],
            )

    def test_different_threads_generate_concurrently(self):
        run = make_persisted_run("_parallel")
        self.app.state.repository.save_run(run)

        with TestClient(self.app) as client:
            first = self._start_thread(client, run.id)
            second = self._start_thread(client, run.id)
            answerer = self.answerers[0]
            self._wait_for_calls(answerer, 2)
            self._wait_for_thread_assistant(
                client, run.id, first["id"], "第一段", "generating"
            )
            self._wait_for_thread_assistant(
                client, run.id, second["id"], "第一段", "generating"
            )

            answerer.release.set()
            for thread_id in (first["id"], second["id"]):
                self._wait_for_thread_assistant(
                    client, run.id, thread_id, "第一段第二段", "completed"
                )

    def test_failed_generation_preserves_partial_text_and_emits_failure(self):
        run = make_persisted_run("_failure")
        self.app.state.repository.save_run(run)
        self.app.state.follow_up_answerer = FailingStreamingAnswerer()

        with TestClient(self.app) as client:
            created = self._start_thread(client, run.id)
            thread_id = created["id"]
            assistant = self._wait_for_thread_assistant(
                client, run.id, thread_id, "已经收到的部分", "failed"
            )
            self.assertEqual(assistant["error_code"], "generation_failed")
            self.assertIn("upstream model failure", assistant["error_message"])

            with client.stream(
                "GET",
                f"/api/research-runs/{run.id}/follow-ups/{thread_id}/events",
            ) as response:
                body = "".join(response.iter_text())

            self.assertIn('"type": "delta"', body)
            self.assertIn('"content": "已经收到的部分"', body)
            self.assertIn('"type": "status"', body)
            self.assertIn('"type": "failed"', body)
            self.assertIn('"status": "failed"', body)

    def test_startup_marks_abandoned_generating_messages_interrupted(self):
        run = make_persisted_run("_restart")
        self.app.state.repository.save_run(run)
        detail = self.app.state.repository.get_run(run.id)
        anchor = {
            "text": "Summary",
            "start": 23,
            "end": 30,
            "prefix": "",
            "suffix": " text",
            "report_digest": report_anchor_digest(detail.report.markdown),
        }
        started = self.app.state.follow_up_repository.start_thread(
            run_id=run.id,
            anchor=anchor,
            question="重启前的问题",
        )
        self.app.state.follow_up_repository.append_delta(
            started.thread["id"], started.assistant_message_id, "部分回答"
        )

        recreated = create_app(
            create_db_engine(self.database_url),
            orchestrator_factory=lambda repository: None,
            follow_up_answerer_factory=lambda: ControlledStreamingAnswerer(),
        )
        with TestClient(recreated) as client:
            thread = client.get(
                f"/api/research-runs/{run.id}/follow-ups/{started.thread['id']}"
            ).json()
            self.assertEqual(thread["messages"][-1]["content"], "部分回答")
            self.assertEqual(thread["messages"][-1]["status"], "interrupted")
            self.assertEqual(thread["messages"][-1]["error_code"], "generation_interrupted")

            with client.stream(
                "GET",
                f"/api/research-runs/{run.id}/follow-ups/{started.thread['id']}/events",
            ) as response:
                body = "".join(response.iter_text())
            self.assertIn('"type": "interrupted"', body)
            self.assertIn('"status": "interrupted"', body)

    def _wait_for_assistant(self, client, run_id, content, status):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            items = client.get(
                f"/api/research-runs/{run_id}/follow-ups"
            ).json()["items"]
            assistant = items[0]["messages"][-1]
            if assistant["content"] == content and assistant["status"] == status:
                return assistant
            time.sleep(0.02)
        self.fail(f"assistant did not reach {status!r} with content {content!r}")

    def _start_thread(self, client, run_id):
        detail = client.get(f"/api/research-runs/{run_id}").json()
        anchor = {
            "text": "Summary",
            "start": 23,
            "end": 30,
            "prefix": "",
            "suffix": " text",
            "report_digest": detail["report"]["anchor_digest"],
        }
        response = client.post(
            f"/api/research-runs/{run_id}/follow-ups",
            json={"anchor": anchor, "question": "请解释这一段。"},
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def _wait_for_thread_assistant(self, client, run_id, thread_id, content, status):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            thread = client.get(
                f"/api/research-runs/{run_id}/follow-ups/{thread_id}"
            ).json()
            assistant = thread["messages"][-1]
            if assistant["content"] == content and assistant["status"] == status:
                return assistant
            time.sleep(0.02)
        self.fail(f"thread did not reach {status!r} with content {content!r}")

    def _wait_for_calls(self, answerer, count):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if len(answerer.calls) >= count:
                return
            time.sleep(0.02)
        self.fail(f"expected {count} concurrent model calls")

    def _disconnect_after_delta(self, client, path):
        async def request_until_delta_disconnects():
            disconnect = asyncio.Event()
            received_delta = False
            request_sent = False

            async def receive():
                nonlocal request_sent
                if not request_sent:
                    request_sent = True
                    return {"type": "http.request", "body": b"", "more_body": False}
                await disconnect.wait()
                return {"type": "http.disconnect"}

            async def send(message):
                nonlocal received_delta
                if message["type"] != "http.response.body":
                    return
                body = message.get("body", b"")
                if b'"type": "delta"' in body:
                    received_delta = True
                    disconnect.set()

            await self.app(
                {
                    "type": "http",
                    "asgi": {"version": "3.0"},
                    "http_version": "1.1",
                    "method": "GET",
                    "scheme": "http",
                    "path": path,
                    "raw_path": path.encode(),
                    "query_string": b"",
                    "root_path": "",
                    "headers": [],
                    "client": ("testclient", 50000),
                    "server": ("testserver", 80),
                },
                receive,
                send,
            )
            return received_delta

        return client.portal.call(request_until_delta_disconnects)


if __name__ == "__main__":
    unittest.main()

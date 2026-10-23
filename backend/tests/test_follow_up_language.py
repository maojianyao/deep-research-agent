"""Language-aware follow-up generation tests."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.src.api.follow_ups import _stream_chunks
from backend.src.services.follow_up import LLMFollowUpAnswerer, _follow_up_messages
from backend.src.storage.follow_up_repository import StartedFollowUp


class FollowUpLanguageTests(unittest.IsolatedAsyncioTestCase):
    def test_prompt_requires_report_language_and_preserves_original_forms(self):
        messages = _follow_up_messages("Pasaje seleccionado", [], "es")
        self.assertIn("Español (es)", messages[0][1])
        self.assertIn("原文", messages[0][1])

    async def test_answer_repairs_one_wrong_language_response(self):
        llm = SimpleNamespace(
            ainvoke=AsyncMock(side_effect=[
                SimpleNamespace(content="This answer is in English."),
                SimpleNamespace(content="Esta respuesta explica el informe en español."),
            ])
        )
        answerer = LLMFollowUpAnswerer(llm)

        answer = await answerer.answer("Passage", [], "es")

        self.assertEqual(answer, "Esta respuesta explica el informe en español.")
        self.assertEqual(llm.ainvoke.await_count, 2)

    async def test_answer_fails_when_repair_still_uses_wrong_language(self):
        llm = SimpleNamespace(ainvoke=AsyncMock(
            return_value=SimpleNamespace(content="This is still English.")
        ))
        answerer = LLMFollowUpAnswerer(llm)

        with self.assertRaisesRegex(RuntimeError, "required language"):
            await answerer.answer("Passage", [], "ja")

    async def test_stream_adapter_receives_persisted_report_language(self):
        calls = []

        class Answerer:
            async def stream(self, passage, history, report_language="zh-CN"):
                calls.append((passage, history, report_language))
                yield "Respuesta"

        started = StartedFollowUp(
            thread={"anchor": {"text": "Pasaje"}},
            assistant_message_id=1,
            history=[{"role": "user", "content": "¿Qué significa?"}],
        )

        chunks = [chunk async for chunk in _stream_chunks(Answerer(), started, "es")]

        self.assertEqual(chunks, ["Respuesta"])
        self.assertEqual(calls[0][2], "es")


if __name__ == "__main__":
    unittest.main()

"""Smoke tests for shared LangChain agent infrastructure."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from backend.src.research.agents.base import _ainvoke, _pair_tool_messages
from backend.src.research.prompts import RoleContext


class PairToolMessagesTests(unittest.TestCase):
    def test_inserts_missing_tool_response_before_next_message(self):
        ai = AIMessage(content="", tool_calls=[{"name": "search", "args": {}, "id": "call_1"}])
        human = HumanMessage(content="next")
        repaired = _pair_tool_messages([ai, human])

        self.assertEqual(len(repaired), 3)
        self.assertIsInstance(repaired[1], ToolMessage)
        self.assertEqual(repaired[1].tool_call_id, "call_1")
        self.assertEqual(repaired[1].name, "search")
        self.assertIs(repaired[2], human)

    def test_inserts_missing_tool_response_at_end(self):
        ai = AIMessage(content="", tool_calls=[{"name": "search", "args": {}, "id": "call_1"}])
        repaired = _pair_tool_messages([ai])

        self.assertEqual(len(repaired), 2)
        self.assertIsInstance(repaired[1], ToolMessage)
        self.assertEqual(repaired[1].tool_call_id, "call_1")

    def test_existing_tool_response_is_not_duplicated(self):
        ai = AIMessage(content="", tool_calls=[{"name": "search", "args": {}, "id": "call_1"}])
        tool = ToolMessage(content="result", tool_call_id="call_1", name="search")
        repaired = _pair_tool_messages([ai, tool])

        self.assertEqual(len(repaired), 2)
        self.assertIs(repaired[1], tool)


class FakeAgent:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    async def ainvoke(self, *, input, context):
        self.calls.append((input, context))
        if self.error:
            raise self.error
        return {"structured_response": self.result}


class AInvokeTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_structured_response_and_passes_context(self):
        agent = FakeAgent(result={"answer": 42})
        context = RoleContext(user_role="test")

        result = await _ainvoke(agent, context, "payload")
        self.assertEqual(result, {"answer": 42})
        self.assertEqual(agent.calls[0][1], context)
        self.assertEqual(agent.calls[0][0]["messages"], "payload")

    async def test_wraps_agent_errors_as_runtime_error(self):
        agent = FakeAgent(error=ValueError("upstream failure"))
        context = RoleContext(user_role="test")

        with self.assertRaises(RuntimeError) as raised:
            await _ainvoke(agent, context, "payload")

        self.assertIn("upstream failure", str(raised.exception))


if __name__ == "__main__":
    unittest.main()

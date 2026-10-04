"""Agent 共享基础设施：搜索契约、消息修复中间件与异步调用封装。"""

from __future__ import annotations

from collections.abc import Callable, Awaitable

from langchain.agents import AgentState
from langchain.agents.middleware.types import ResponseT, InputAgentState, OutputAgentState, \
    ModelRequest, AgentMiddleware
from langchain_core.messages import BaseMessage, ToolMessage, AIMessage
from langgraph.graph.state import CompiledStateGraph
from langgraph.typing import ContextT

from backend.src.research.context_budget import log_payload_size
from backend.src.research.prompts import RoleContext
from backend.src.research.schemas import SourceDocument
from backend.src.utils.logger import get_logger

# 搜索适配器统一为异步契约；同步实现可用 asyncio.to_thread包装接入。它可以封装 Tavily、SearXNG 或企业知识库。
Search = Callable[[str], Awaitable[list[SourceDocument]]]

logger = get_logger(__name__)

_TOOL_RETRY_HINT = (
    "Error: your previous tool call could not be processed because its `arguments` were not valid JSON, "
    "or the call was left unanswered. Call the tool again; `arguments` must be one complete and valid JSON "
    "object (no bare newlines, no unescaped quotes, no trailing commas)."
)


def _pair_tool_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
    """补齐未被 ToolMessage 应答的 tool_calls/invalid_tool_calls，使消息序列满足 OpenAI 契约。"""
    repaired: list[BaseMessage] = []
    pending: dict[str, str] = {}

    def _flush() -> None:
        if pending:
            logger.warning("检测到 %d 个未被应答的工具调用 %s，已补齐合成 ToolMessage", len(pending), list(pending))
            repaired.extend(
                ToolMessage(content=_TOOL_RETRY_HINT, tool_call_id=call_id, name=name)
                for call_id, name in pending.items()
            )
            pending.clear()

    for msg in messages:
        if isinstance(msg, AIMessage):
            _flush()
            for tc in msg.tool_calls:
                pending[str(tc["id"])] = tc["name"]
            for tc in msg.invalid_tool_calls:
                if tc.get("id") is not None:
                    pending[str(tc["id"])] = tc.get("name") or "tool"
            repaired.append(msg)
        elif isinstance(msg, ToolMessage):
            pending.pop(str(msg.tool_call_id), None)
            repaired.append(msg)
        else:
            _flush()
            repaired.append(msg)
    _flush()
    return repaired


class RepairToolMessagesMiddleware(AgentMiddleware):
    """在每次模型调用前补齐未被应答的工具调用，保证消息序列满足 OpenAI 契约。"""

    def wrap_model_call(self, request: ModelRequest, handler):
        return handler(request.override(messages=_pair_tool_messages(list(request.messages))))

    async def awrap_model_call(self, request: ModelRequest, handler):
        return await handler(request.override(messages=_pair_tool_messages(list(request.messages))))


repair_tool_messages = RepairToolMessagesMiddleware()


async def _ainvoke(agent: CompiledStateGraph[AgentState[ResponseT], ContextT, InputAgentState, OutputAgentState[ResponseT]],
                   context: RoleContext,
                   messages: str | list[BaseMessage],
                   ):
    """异步执行消息，并以结构化方式返回结果;进入模型前记录载荷规模，便于观察上下文增长。"""
    try:
        if isinstance(messages, str):
            log_payload_size(context.user_role, messages)
        response = await agent.ainvoke(input={"messages": messages}, context=context)
        return response["structured_response"]
    except Exception as e:
        logger.error(f"模型调用异常：{e}", exc_info=True)
        raise RuntimeError(f"模型调用异常：{e}") from e

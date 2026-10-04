"""Critic Agent：独立挑战已有结论，决定是否需要继续补证。"""

from __future__ import annotations

import json

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.language_models.chat_models import BaseChatModel

from backend.src.research.agents.base import _ainvoke, repair_tool_messages
from backend.src.research.context_budget import round_robin_by_task, take_within_budget, \
    estimate_tokens, CRITIC_INPUT_BUDGET_TOKENS
from backend.src.research.prompts import dynamic_prompt, RoleContext
from backend.src.research.schemas import CriticReview, EvidenceCard, Finding, RoleAgent
from backend.src.utils.logger import get_logger


logger = get_logger(__name__)


class CriticAgent:
    """独立挑战已有结论，决定是否需要继续补证。"""
    _ROLE = RoleContext(user_role=RoleAgent.CRITIC)
    _INPUT_BUDGET_TOKENS = CRITIC_INPUT_BUDGET_TOKENS

    def __init__(self, model: BaseChatModel):
        self.agent = create_agent(model,
                                  tools=[],
                                  middleware=[dynamic_prompt, repair_tool_messages],
                                  response_format=ToolStrategy(CriticReview),
                                  )

    async def run(self, findings: list[Finding], evidence: list[EvidenceCard]) -> CriticReview:
        """基于紧凑视图给出闸门决策；全文不进模型，禁止新增事实。"""
        finding_items = [item.to_digest().model_dump() for item in findings]
        evidence_items = [item.to_digest().model_dump(mode="json") for item in evidence]
        # 置信度降序 + 按任务轮流取样，保证预算裁剪时每个任务仍有代表证据
        evidence_items = round_robin_by_task(
            sorted(evidence_items, key=lambda item: item["confidence"], reverse=True),
            key=lambda item: item["task_id"])
        findings_cost = estimate_tokens(json.dumps(finding_items, ensure_ascii=False))
        evidence_budget = max(self._INPUT_BUDGET_TOKENS - findings_cost, 10_000)
        evidence_items = take_within_budget(
            evidence_items, evidence_budget,
            render=lambda item: json.dumps(item, ensure_ascii=False))
        payload = json.dumps({"findings": finding_items, "evidence": evidence_items}, ensure_ascii=False)
        return await _ainvoke(self.agent, self._ROLE, payload)

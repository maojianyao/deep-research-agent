"""Planner Agent：将原始请求转化为有验收条件的研究计划。"""

from __future__ import annotations

import json

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.language_models.chat_models import BaseChatModel

from backend.src.research.agents.base import _ainvoke, repair_tool_messages
from backend.src.research.context_budget import round_robin_by_task, take_within_budget, \
    PLANNER_SUPPLEMENT_INPUT_BUDGET_TOKENS
from backend.src.research.prompts import dynamic_prompt, RoleContext
from backend.src.research.schemas import (
    CriticReview, EvidenceCard, Finding, ResearchPlan, ResearchPlanDraft, ResearchTask,
    RoleAgent, SupplementPlanDraft,
)
from backend.src.utils.logger import get_logger


logger = get_logger(__name__)


class PlannerAgent:
    """将原始请求转化为有验收条件的 ResearchPlan；支持 Critic 补证后的增量规划。"""
    _INPUT_BUDGET_TOKENS = PLANNER_SUPPLEMENT_INPUT_BUDGET_TOKENS

    def __init__(self, model: BaseChatModel):
        self.agent = create_agent(model,
                                  tools=[],
                                  middleware=[dynamic_prompt, repair_tool_messages],
                                  response_format=ToolStrategy(ResearchPlanDraft),
                                  )
        self.supplement_agent = create_agent(model,
                                             tools=[],
                                             middleware=[dynamic_prompt, repair_tool_messages],
                                             response_format=ToolStrategy(SupplementPlanDraft),
                                             )

    async def run(self, user_request: str, report_language: str = "zh-CN") -> ResearchPlan:
        """生成研究计划；不在此阶段检索或输出结论。"""
        logger.info(f"研究topic：{user_request}")
        role = RoleContext(user_role=RoleAgent.PLANNER, report_language=report_language)
        return (await _ainvoke(self.agent, role, user_request,)).to_plan()

    async def run_supplement(self, user_request: str, critique: CriticReview,
                             findings: list[Finding], evidence: list[EvidenceCard],
                             report_language: str = "zh-CN") -> list[ResearchTask]:
        """Critic 判定需补证后的增量规划：只返回新增任务，由编排器合并进现有计划。"""
        finding_items = [item.to_digest().model_dump() for item in findings]
        evidence_items = [item.to_digest().model_dump(mode="json") for item in evidence]
        evidence_items = round_robin_by_task(
            sorted(evidence_items, key=lambda item: item["confidence"], reverse=True),
            key=lambda item: item["task_id"])
        evidence_items = take_within_budget(
            evidence_items, self._INPUT_BUDGET_TOKENS // 2,
            render=lambda item: json.dumps(item, ensure_ascii=False))
        payload = json.dumps({
            "user_request": user_request,
            "critique": {"decision": critique.decision,
                         "issues": [issue.model_dump(exclude={"finding_id"}) for issue in critique.issues]},
            "existing_findings": finding_items,
            "evidence": evidence_items,
        }, ensure_ascii=False)
        role = RoleContext(
            user_role=RoleAgent.PLANNER,
            mode="supplement",
            report_language=report_language,
        )
        draft: SupplementPlanDraft = await _ainvoke(self.supplement_agent, role, payload)
        return [item.to_task() for item in draft.tasks]

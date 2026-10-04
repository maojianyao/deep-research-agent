"""Synthesizer Agent：将同一任务的合格证据综合为连贯结论。"""

from __future__ import annotations

import asyncio
import json

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.language_models.chat_models import BaseChatModel

from backend.src.research.agents.base import _ainvoke, repair_tool_messages
from backend.src.research.context_budget import take_within_budget, SYNTHESIZER_INPUT_BUDGET_TOKENS
from backend.src.research.prompts import dynamic_prompt, RoleContext
from backend.src.research.schemas import Finding, FindingDraft, ResearchTask, RoleAgent, EvidenceCard
from backend.src.utils.logger import get_logger


logger = get_logger(__name__)


class SynthesizerAgent:
    """将同一任务的合格证据综合为连贯结论，替代机械拼接；失败时返回 None 由编排器降级。"""
    _ROLE = RoleContext(user_role=RoleAgent.SYNTHESIZER)
    _INPUT_BUDGET_TOKENS = SYNTHESIZER_INPUT_BUDGET_TOKENS
    _EXCERPT_CHARS = 800

    def __init__(self, model: BaseChatModel, max_concurrent_syntheses: int = 4):
        self.agent = create_agent(model,
                                  tools=[],
                                  middleware=[dynamic_prompt, repair_tool_messages],
                                  response_format=ToolStrategy(FindingDraft),
                                  )
        self._semaphore = asyncio.Semaphore(max_concurrent_syntheses)

    async def run(self, task: ResearchTask, evidence: list[EvidenceCard]) -> Finding | None:
        """综合单任务证据为一条连贯结论；调用失败或引用无效时返回 None。"""
        if not evidence:
            return None
        evidence_items = [item.to_digest(excerpt_chars=self._EXCERPT_CHARS).model_dump(mode="json")
                          for item in evidence]
        evidence_items = take_within_budget(evidence_items, self._INPUT_BUDGET_TOKENS,
                                            render=lambda item: json.dumps(item, ensure_ascii=False))
        payload = json.dumps({
            "task": {"id": task.id, "question": task.question, "task_type": task.task_type},
            "evidence": evidence_items,
        }, ensure_ascii=False)
        try:
            async with self._semaphore:
                draft: FindingDraft = await _ainvoke(self.agent, self._ROLE, payload)
        except Exception as e:
            logger.warning("任务 %s 结论综合失败，将降级为机械合并：%s", task.id, e)
            return None
        known_ids = {item.id for item in evidence}
        evidence_ids = list(dict.fromkeys(eid for eid in draft.evidence_ids if eid in known_ids))
        if not evidence_ids:
            logger.warning("任务 %s 综合结论未引用有效证据，将降级为机械合并", task.id)
            return None
        cited = [item for item in evidence if item.id in set(evidence_ids)]
        caveats = list(dict.fromkeys([*draft.caveats, *(limit for item in cited for limit in item.limitations)]))
        return Finding(
            task_id=task.id,
            statement=draft.statement,
            classification=draft.classification,
            evidence_ids=evidence_ids,
            confidence=round(sum(item.confidence for item in cited) / len(cited), 2),
            caveats=caveats[:8],
        )

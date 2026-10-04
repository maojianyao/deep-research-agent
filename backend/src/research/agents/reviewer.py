"""EvidenceReviewer Agent：审核候选证据，绑定应用层管理的来源和任务 ID。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Awaitable
from functools import partial

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.language_models.chat_models import BaseChatModel

from backend.src.research.agents.base import _ainvoke, repair_tool_messages
from backend.src.research.context_budget import truncate_text
from backend.src.research.prompts import dynamic_prompt, RoleContext
from backend.src.research.schemas import (
    CandidateEvidence, EvidenceAssessment, EvidenceAssessmentBatch, EvidenceCard,
    ResearchTask, RoleAgent,
)
from backend.src.utils.logger import get_logger


logger = get_logger(__name__)


class EvidenceReviewerAgent:
    """审核候选证据，并由应用层绑定不可被模型伪造的来源和任务 ID。"""
    _ROLE = RoleContext(user_role=RoleAgent.REVIEWER)
    _BATCH_SIZE = 8  # 每次结构化调用承载的候选数：输入 ≈ 批内候选 × (正文窗口 + 摘录窗口)
    _SOURCE_CHARS = 1200  # 审查视角的正文窗口：足以判断摘录是否断章取义
    _EXCERPT_CHARS = 600

    def __init__(self, model: BaseChatModel, max_concurrent_reviews: int = 4):
        self.agent = create_agent(model,
                                  tools=[],
                                  middleware=[dynamic_prompt, repair_tool_messages],
                                  response_format=ToolStrategy(EvidenceAssessmentBatch),
                                  )
        self._semaphore = asyncio.Semaphore(max_concurrent_reviews)

    async def _bounded(self, factory: Callable[[], Awaitable]):
        """用信号量限制审查调用并发数"""
        async with self._semaphore:
            return await factory()

    async def run(self, task: ResearchTask, candidates: list[CandidateEvidence]) -> list[EvidenceCard]:
        """批量审查并返回可被综合器引用的 EvidenceCard 列表。"""
        if not candidates:
            return []
        batches = [candidates[i:i + self._BATCH_SIZE] for i in range(0, len(candidates), self._BATCH_SIZE)]
        results = await asyncio.gather(*(self._review_batch(task, batch) for batch in batches))
        cards: list[EvidenceCard] = []
        for batch, assessments in results:
            for candidate, assessment in zip(batch, assessments):
                cards.append(EvidenceCard(
                    task_id=task.id,
                    claim=candidate.claim,
                    excerpt=candidate.excerpt,
                    source=candidate.source,
                    locator=candidate.locator,
                    **assessment.model_dump(),
                ))
        return cards

    async def _review_batch(self, task: ResearchTask,
                            batch: list[CandidateEvidence],
                            ) -> tuple[list[CandidateEvidence], list[EvidenceAssessment]]:
        """审查单批候选；单批失败按 insufficient 降级，不阻断整体流水线。"""
        payload = json.dumps({
            "task": {"id": task.id, "question": task.question, "task_type": task.task_type,
                     "acceptance_criteria": [truncate_text(item, 200) for item in task.acceptance_criteria]},
            "candidates": [self._compact(item) for item in batch],
        }, ensure_ascii=False)
        try:
            result: EvidenceAssessmentBatch = await self._bounded(
                partial(_ainvoke, self.agent, self._ROLE, payload))
            assessments = list(result.items)
        except Exception as e:
            logger.error("审查批次失败，%d 条候选按 insufficient 降级：%s", len(batch), e)
            assessments = []
        if len(assessments) > len(batch):
            logger.warning("审查输出 %d 项多于候选 %d 项，已截断对齐", len(assessments), len(batch))
            assessments = assessments[:len(batch)]
        while len(assessments) < len(batch):
            logger.warning("审查输出 %d 项少于候选 %d 项，缺口按 insufficient 补齐", len(assessments), len(batch))
            assessments.append(EvidenceAssessment(verdict="insufficient", confidence=0.0,
                                                  limitations=["审查输出缺失"]))
        return batch, assessments

    @classmethod
    def _compact(cls, candidate: CandidateEvidence) -> dict:
        """候选证据的审查视图：正文截断、元数据齐全，全文不进模型。"""
        src = candidate.source
        return {
            "url": str(src.url), "title": src.title, "publisher": src.publisher,
            "published_at": src.published_at, "source_type": src.source_type,
            "claim": candidate.claim,
            "excerpt": truncate_text(candidate.excerpt, cls._EXCERPT_CHARS),
            "locator": candidate.locator,
            "content": truncate_text(src.content, cls._SOURCE_CHARS),
        }

"""Writer Agent：三阶段写作（大纲 → 分章 → 收束）。"""

from __future__ import annotations

import json

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.language_models.chat_models import BaseChatModel

from backend.src.research.agents.base import _ainvoke, repair_tool_messages
from backend.src.research.context_budget import take_within_budget, truncate_text, \
    WRITER_SECTION_INPUT_BUDGET_TOKENS
from backend.src.research.prompts import dynamic_prompt, RoleContext
from backend.src.research.schemas import (
    EvidenceCard, Finding, ReportBlock, ReportDraft, ReportOutline, RoleAgent, SectionDraft,
    SummaryDraft,
)
from backend.src.utils.logger import get_logger


logger = get_logger(__name__)


class WriterAgent:
    """三阶段写作：大纲规划 → 顺序分章撰写 → 摘要收束，维持全文论证连贯。"""
    _OUTLINE_ROLE = RoleContext(user_role=RoleAgent.WRITER, mode="outline")
    _SECTION_ROLE = RoleContext(user_role=RoleAgent.WRITER, mode="section")
    _SUMMARY_ROLE = RoleContext(user_role=RoleAgent.WRITER, mode="summary")
    _SECTION_INPUT_BUDGET_TOKENS = WRITER_SECTION_INPUT_BUDGET_TOKENS
    _FINDING_STATEMENT_CHARS = 500
    _SECTION_EXCERPT_CHARS = 800
    _SECTION_TEXT_BRIEF_CHARS = 300

    def __init__(self, model: BaseChatModel):
        self.outline_agent = create_agent(model,
                                          tools=[],
                                          middleware=[dynamic_prompt, repair_tool_messages],
                                          response_format=ToolStrategy(ReportOutline),
                                          )
        self.section_agent = create_agent(model,
                                          tools=[],
                                          middleware=[dynamic_prompt, repair_tool_messages],
                                          response_format=ToolStrategy(SectionDraft),
                                          )
        self.summary_agent = create_agent(model,
                                          tools=[],
                                          middleware=[dynamic_prompt, repair_tool_messages],
                                          response_format=ToolStrategy(SummaryDraft),
                                          )

    async def run(self, request: str, findings: list[Finding], evidence: list[EvidenceCard],
                  task_questions: dict[str, str] | None = None) -> ReportDraft:
        """三阶段编排：大纲 → 顺序分章 → 摘要收束与应用层组装。"""
        task_questions = task_questions or {}
        outline = await self.plan_outline(request, findings, task_questions)
        finding_by_id = {item.id: item for item in findings}
        evidence_by_id = {item.id: item for item in evidence}
        sections: list[SectionDraft] = []
        for index in range(len(outline.sections)):
            section = await self.write_section(
                request, outline, index, finding_by_id, evidence_by_id, task_questions,
                previous_section=sections[-1] if sections else None,
            )
            sections.append(section)
        summary = await self.write_summary(outline, sections)
        return self.assemble(outline, sections, summary)

    async def plan_outline(self, request: str, findings: list[Finding],
                           task_questions: dict[str, str]) -> ReportOutline:
        """阶段一：按研究维度规划章节结构，并保证每条结论恰好分配到一个章节。"""
        finding_items = [item.to_digest(statement_chars=self._FINDING_STATEMENT_CHARS).model_dump()
                         for item in findings]
        payload = json.dumps({"request": request, "task_questions": task_questions,
                              "findings": finding_items}, ensure_ascii=False)
        outline: ReportOutline = await _ainvoke(self.outline_agent, self._OUTLINE_ROLE, payload)
        known = {item.id for item in findings}
        assigned: set[str] = set()
        for section in outline.sections:
            section.finding_ids = [fid for fid in section.finding_ids
                                   if fid in known and fid not in assigned]
            assigned.update(section.finding_ids)
        unassigned = [item.id for item in findings if item.id not in assigned]
        if unassigned:
            outline.sections[-1].finding_ids.extend(unassigned)
            logger.warning("大纲未分配 %d 条结论，已并入最后一章", len(unassigned))
        return outline

    async def write_section(self, request: str, outline: ReportOutline, section_index: int,
                            finding_by_id: dict[str, Finding], evidence_by_id: dict[str, EvidenceCard],
                            task_questions: dict[str, str],
                            previous_section: SectionDraft | None = None) -> SectionDraft:
        """阶段二：单章撰写；只携带本章结论与关联证据，大纲主线与上一章接口用于章节衔接。"""
        section = outline.sections[section_index]
        previous = outline.sections[section_index - 1] if section_index > 0 else None
        next_section = outline.sections[section_index + 1] if section_index + 1 < len(outline.sections) else None
        section_findings = [finding_by_id[fid] for fid in section.finding_ids if fid in finding_by_id]
        related_ids = list(dict.fromkeys(eid for item in section_findings for eid in item.evidence_ids))
        evidence_items = [evidence_by_id[eid].to_digest(excerpt_chars=self._SECTION_EXCERPT_CHARS).model_dump(mode="json")
                          for eid in related_ids if eid in evidence_by_id]
        evidence_items = take_within_budget(evidence_items, self._SECTION_INPUT_BUDGET_TOKENS,
                                            render=lambda item: json.dumps(item, ensure_ascii=False))
        payload = json.dumps({
            "request": request,
            "report_title": outline.title,
            "narrative": outline.narrative,
            "outline": [{"heading": item.heading, "role": item.role, "key_points": item.key_points,
                         "transition_to_next": item.transition_to_next,
                         "is_current": item.heading == section.heading} for item in outline.sections],
            "section_heading": section.heading,
            "section_key_points": section.key_points,
            "methodology_section_heading": next(
                (item.heading for item in outline.sections if not item.finding_ids), None),
            "previous_section": ({
                "heading": previous_section.heading,
                "key_points": previous_section.key_points,
                "text_brief": truncate_text(previous_section.text, self._SECTION_TEXT_BRIEF_CHARS),
                "planned_transition": previous.transition_to_next if previous else None,
            } if previous_section else None),
            "next_section": ({"heading": next_section.heading, "key_points": next_section.key_points}
                             if next_section else None),
            "task_questions": task_questions,
            "findings": [item.to_digest(statement_chars=self._FINDING_STATEMENT_CHARS).model_dump()
                         for item in section_findings],
            "evidence": evidence_items,
        }, ensure_ascii=False)
        draft: SectionDraft = await _ainvoke(self.section_agent, self._SECTION_ROLE, payload)
        draft.heading = section.heading
        draft.key_points = list(section.key_points)
        # Bind references from the application-owned outline/findings; a model cannot drop them.
        draft.finding_ids = list(section.finding_ids)
        draft.evidence_ids = [eid for eid in related_ids if eid in evidence_by_id]
        return draft

    async def write_summary(self, outline: ReportOutline, sections: list[SectionDraft]) -> SummaryDraft:
        """阶段三：基于各章要点与正文摘要撰写执行摘要、结论与局限，保证全文前后呼应。"""
        payload = json.dumps({
            "report_title": outline.title,
            "sections": [{"heading": item.heading,
                          "key_points": item.key_points,
                          "text_brief": truncate_text(item.text, self._SECTION_TEXT_BRIEF_CHARS)}
                         for item in sections],
        }, ensure_ascii=False)
        return await _ainvoke(self.summary_agent, self._SUMMARY_ROLE, payload)

    @staticmethod
    def assemble(outline: ReportOutline, sections: list[SectionDraft], summary: SummaryDraft) -> ReportDraft:
        """应用层组装：摘要在前、分章居中、结论与局限收尾；纯确定性操作，不经过模型。"""
        finding_ids = list(dict.fromkeys(fid for item in sections for fid in item.finding_ids))
        evidence_ids = list(dict.fromkeys(eid for item in sections for eid in item.evidence_ids))
        blocks = [ReportBlock(heading="执行摘要", text=summary.executive_summary,
                              finding_ids=finding_ids, evidence_ids=evidence_ids)]
        blocks += [ReportBlock(heading=item.heading, text=item.text,
                               finding_ids=item.finding_ids, evidence_ids=item.evidence_ids)
                   for item in sections]
        blocks.append(ReportBlock(heading="结论与建议", text=summary.conclusion,
                                  finding_ids=finding_ids, evidence_ids=evidence_ids))
        if summary.limitations:
            blocks.append(ReportBlock(heading="不确定性与局限", text=summary.limitations,
                                      finding_ids=finding_ids, evidence_ids=evidence_ids))
        return ReportDraft(title=outline.title, blocks=blocks)

    @staticmethod
    def citations_are_valid(draft: ReportDraft, evidence: list[EvidenceCard]) -> bool:
        """确认每个报告块引用的证据 ID 都已通过审查并入库。"""
        known_ids = {item.id for item in evidence}
        return all(set(block.evidence_ids) <= known_ids
                   and (not block.finding_ids or bool(block.evidence_ids))
                   for block in draft.blocks)

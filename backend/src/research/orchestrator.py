"""确定性编排器：负责状态和循环，Agent 只负责各自的受限判断。"""

from __future__ import annotations

import asyncio

from backend.src.research.agents import CriticAgent, EvidenceReviewerAgent, PlannerAgent, ResearcherAgent, WriterAgent, \
    SynthesizerAgent
from backend.src.research.schemas import EvidenceCard, Finding, ResearchRun, ResearchTask, RunStatus
from backend.src.utils.logger import get_logger


logger = get_logger(__name__)

class ResearchOrchestrator:
    """以确定性状态机协调五个 Agent，并控制反思后的补证循环。"""

    def __init__(self, planner: PlannerAgent, researcher: ResearcherAgent,
                 reviewer: EvidenceReviewerAgent, synthesizer: SynthesizerAgent,
                 critic: CriticAgent, writer: WriterAgent):
        self.planner, self.researcher, self.reviewer = planner, researcher, reviewer
        self.synthesizer = synthesizer
        self.critic, self.writer = critic, writer

    async def run(self, research: ResearchRun) -> ResearchRun:
        """推进运行至终态；可传入已持久化的 ResearchRun 继续执行。"""
        count = 1
        while research.status not in {RunStatus.COMPLETED, RunStatus.NEEDS_HUMAN_REVIEW, RunStatus.FAILED}:
            if research.status is RunStatus.PLANNING:
                if research.plan is None:
                    logger.info(f"开始生成研究计划。。。")
                    research.plan = await self.planner.run(research.user_request)
                    research.event("研究计划已生成")
                    logger.info(f"\n\n规划agent：第 {count} 次生成计划\n"
                                f"用户输入的主题：{research.user_request}\n"
                                f"总研究问题：{research.plan.research_question}\n")
                else:
                    # Critic 补证回路：转交规划 Agent 基于审稿意见做增量补证规划
                    logger.info(f"开始增量补证规划。。。")
                    new_tasks = await self.planner.run_supplement(
                        research.user_request, research.critique, research.findings, research.evidence)
                    existing_questions = {task.question for task in research.plan.tasks}
                    new_tasks = [task for task in new_tasks if task.question not in existing_questions]
                    research.plan.tasks.extend(new_tasks)
                    research.event(f"补证规划已生成 {len(new_tasks)} 个新任务")
                    logger.info(f"\n\n规划agent：第 {count} 次补证规划，新增 {len(new_tasks)} 个任务\n")
                research.status = RunStatus.RESEARCHING
            elif research.status is RunStatus.RESEARCHING:
                logger.info(f"开始进行证据检索。。。")
                await self._research_iteration(research)
                research.status = RunStatus.CRITIC_REVIEW
                logger.info(f"检索agent已完成检索")
            elif research.status is RunStatus.CRITIC_REVIEW:
                logger.info(f"开始进行证据审查。。。")
                research.critique = await self.critic.run(research.findings, research.evidence)
                logger.info(f"\n\n审稿agent：\n"
                            f"审稿意见：{research.critique}\n")
                self._apply_critique(research)
                logger.info(f"审稿agent已完成审稿")
            elif research.status is RunStatus.WRITING:
                logger.info(f"开始进行三阶段报告写作。。。")
                findings = self._writable_findings(research)
                if not findings:
                    research.status = RunStatus.NEEDS_HUMAN_REVIEW
                    research.event("无可用结论可写作，需人工复核")
                    logger.info(f"\n无可用结论可写作\n")
                    continue
                task_questions = {task.id: task.question for task in research.plan.tasks} if research.plan else {}
                research.report = await self.writer.run(research.user_request, findings, research.evidence, task_questions)
                research.status = RunStatus.COMPLETED if self.writer.citations_are_valid(research.report, research.evidence) else RunStatus.FAILED
                research.event("报告已生成" if research.status is RunStatus.COMPLETED else "引用校验失败")
                logger.info(f"\n写作agent已完成写作\n")
            else:
                research.status = RunStatus.FAILED
                research.event("状态机遇到未知状态")
                logger.info(f"\n状态机遇到未知状态\n")
            count += 1
        return research

    async def _research_iteration(self, research: ResearchRun) -> None:
        """并发执行当前未完成任务的单轮检索、审查和初步结论生成。"""
        assert research.plan is not None
        research.iteration += 1
        pending = [task for task in research.plan.tasks if not task.completed]

        pending_json = "\n".join(task.model_dump_json(indent=2) for task in pending)
        logger.info(f"\n\n第 {research.iteration} 轮检索\n"
                    f"\n共 {len(pending)} 个检索任务\n"
                    f"{pending_json}")

        async def process(task: ResearchTask) -> None:
            candidates = await self.researcher.run(task)
            reviewed = await self.reviewer.run(task, candidates)
            supported = [item for item in reviewed if item.verdict in {"supported", "partially_supported"}]
            return task, candidates, reviewed, supported

        # gather 保持输入顺序，写回状态在事件循环单线程内完成，无需加
        # return_exceptions：单任务失败仅跳过该任务，不炸掉整轮检索
        outcomes = await asyncio.gather(*[process(task) for task in pending], return_exceptions=True)
        for outcome in outcomes:
            if isinstance(outcome, BaseException):
                logger.error("检索任务执行失败，已跳过：%s", outcome)
                research.event("存在执行失败的检索任务，已跳过")
                continue
            task, candidates, reviewed, supported = outcome
            research.candidates.extend(candidates)
            research.evidence.extend(item for item in reviewed if item.verdict in {"supported", "partially_supported"})
            findings = await self._synthesize_findings(task, supported)
            research.findings.extend(findings)
            task.completed = bool(findings)

            # 可修改对应详细日志信息输出
            sources_json = "\n".join(
                item.source.model_dump_json(include={"title", "url"}, indent=2)
                for item in candidates)
            logger.info(f"\n\n检索agent：检索任务id {task.id}\n"
                        f"检索源信息：{sources_json}")

            reviews_json = "\n".join(
                item.model_dump_json(include={"id": True, "claim": True,
                                              "excerpt": True, "verdict": True,
                                              "source": {"title": True, "url": True},
                                              "confidence": True,
                                              "limitations": True}, indent=2)
                for item in reviewed)
            logger.info(f"\n\n审查agent：检索任务id {task.id}\n"
                        f"审核信息：{reviews_json}")

            findings_json = "\n".join(item.model_dump_json(indent=2) for item in findings)
            logger.info(f"\n\n初步结论生成：\n"
                        f"初步结论：{findings_json}")
        research.event(f"完成第 {research.iteration} 轮检索")

    async def _synthesize_findings(self, task: ResearchTask, supported: list[EvidenceCard]) -> list[Finding]:
        """优先让综合 Agent 产出连贯结论；失败或无效时降级为机械合并，保证流水线不中断。"""
        if not supported:
            return []
        finding = await self.synthesizer.run(task, supported)
        if finding is not None:
            return [finding]
        return self._findings(task, supported)

    @staticmethod
    def _findings(task: ResearchTask, evidence: list[EvidenceCard]) -> list[Finding]:
        """将同一任务的合格证据合并为平均结论单元。"""
        supported = [item for item in evidence if item.verdict in {"supported", "partially_supported"}]
        if not supported:
            return []
        return [Finding(
            task_id=task.id,
            statement="；".join(item.claim for item in supported),
            classification="fact",
            evidence_ids=[item.id for item in supported],
            confidence=round(sum(item.confidence for item in supported) / len(supported), 2),
            caveats=[limit for item in supported for limit in item.limitations],
        )]

    def _apply_critique(self, research: ResearchRun) -> None:
        """把 Critic 决策转换为状态迁移；补证需求转交 Planner 增量规划。"""
        assert research.critique is not None and research.plan is not None
        known_ids = {item.id for item in research.findings}
        research.critique.approved_finding_ids = [
            item for item in research.critique.approved_finding_ids if item in known_ids
        ]
        logger.info(f"审稿意见：【{research.critique.decision}】")
        if research.critique.decision == "approve":
            research.status = RunStatus.WRITING
            return
        if research.critique.decision == "needs_human_review":
            research.status = RunStatus.NEEDS_HUMAN_REVIEW
            research.event("审稿判定需人工决定后续研究范围")
            return
        if research.iteration >= research.max_iterations:
            # 迭代预算耗尽：不再补证，基于现有证据链降级写作，避免整轮研究无产出
            research.status = RunStatus.WRITING
            research.event("达到最大迭代次数，基于现有证据链降级写作")
            logger.info(f"达到最大迭代次数（{research.iteration}/{research.max_iterations}），转写作Agent基于现有证据链生成报告")
            return
        # research_more：回到规划阶段，由 Planner 基于审稿意见增量补证，不再直接拼接任务
        research.status = RunStatus.PLANNING
        research.event("审稿要求补充检索，转交规划Agent增量补证")
        logger.info(f"审稿要求补证，已回到规划Agent进行增量补证规划")

    @staticmethod
    def _writable_findings(research: ResearchRun) -> list[Finding]:
        """优先使用 Critic 获准的结论；未获准时回退为全部已有结论，尽力生成报告。"""
        if research.critique is None:
            return list(research.findings)
        approved_ids = set(research.critique.approved_finding_ids)
        approved = [item for item in research.findings if item.id in approved_ids]
        if approved or not research.findings:
            return approved
        logger.warning("Critic 未批准任何结论，降级为使用全部 %d 条结论写作", len(research.findings))
        return list(research.findings)

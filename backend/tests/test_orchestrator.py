"""Smoke tests for the deterministic research orchestrator."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from backend.src.research.orchestrator import ResearchOrchestrator
from backend.src.research.schemas import CriticReview, ReportBlock, RunStatus
from backend.tests.factories import (
    make_candidate, make_evidence, make_finding, make_plan, make_report, make_task,
)


def make_stubs():
    return SimpleNamespace(
        planner=MagicMock(),
        researcher=MagicMock(),
        reviewer=MagicMock(),
        synthesizer=MagicMock(),
        critic=MagicMock(),
        writer=MagicMock(),
    )


class SynthesizeFindingsTests(unittest.IsolatedAsyncioTestCase):
    async def test_uses_synthesizer_result_when_available(self):
        task = make_task()
        evidence = [make_evidence()]
        finding = make_finding()
        orchestrator = ResearchOrchestrator(None, None, None, MagicMock(), None, None)
        orchestrator.synthesizer.run = AsyncMock(return_value=finding)

        result = await orchestrator._synthesize_findings(task, evidence)
        self.assertEqual(result, [finding])

    async def test_does_not_create_a_finding_when_synthesis_fails(self):
        task = make_task()
        evidence = [make_evidence(evidence_id="evidence_fallback", task_id=task.id)]
        orchestrator = ResearchOrchestrator(None, None, None, MagicMock(), None, None)
        orchestrator.synthesizer.run = AsyncMock(return_value=None)

        result = await orchestrator._synthesize_findings(task, evidence)
        self.assertEqual(result, [])


class ApplyCritiqueTests(unittest.TestCase):
    def make_run(self, decision: str, iteration: int = 1, max_iterations: int = 3):
        finding = make_finding(finding_id="finding_apply")
        run = make_plan_aware_run(finding=finding)
        run.iteration = iteration
        run.max_iterations = max_iterations
        run.critique = CriticReview(decision=decision, approved_finding_ids=["missing", "finding_apply"])
        return run

    def test_approve_moves_to_writing(self):
        run = self.make_run("approve")
        orchestrator = ResearchOrchestrator(None, None, None, None, None, None)
        orchestrator._apply_critique(run)
        self.assertEqual(run.status, RunStatus.WRITING)
        self.assertEqual(run.critique.approved_finding_ids, ["finding_apply"])

    def test_needs_human_review_is_terminal(self):
        run = self.make_run("needs_human_review")
        orchestrator = ResearchOrchestrator(None, None, None, None, None, None)
        orchestrator._apply_critique(run)
        self.assertEqual(run.status, RunStatus.NEEDS_HUMAN_REVIEW)
        self.assertIn("审稿判定需人工决定后续研究范围", run.events)

    def test_research_more_returns_to_planning_within_budget(self):
        run = self.make_run("research_more", iteration=1, max_iterations=3)
        orchestrator = ResearchOrchestrator(None, None, None, None, None, None)
        orchestrator._apply_critique(run)
        self.assertEqual(run.status, RunStatus.PLANNING)
        self.assertIn("审稿要求补充检索，转交规划Agent增量补证", run.events)

    def test_research_more_degrades_to_writing_when_budget_is_exhausted(self):
        run = self.make_run("research_more", iteration=3, max_iterations=3)
        orchestrator = ResearchOrchestrator(None, None, None, None, None, None)
        orchestrator._apply_critique(run)
        self.assertEqual(run.status, RunStatus.WRITING)
        self.assertIn("达到最大迭代次数，停止补证并仅基于已批准结论写作", run.events)


class WritableFindingsTests(unittest.TestCase):
    def test_without_critique_does_not_release_findings_to_writer(self):
        run = make_plan_aware_run()
        result = ResearchOrchestrator._writable_findings(run)
        self.assertEqual(result, [])

    def test_prefers_approved_findings(self):
        run = make_plan_aware_run()
        run.critique = CriticReview(decision="approve", approved_finding_ids=["finding_apply"])
        result = ResearchOrchestrator._writable_findings(run)
        self.assertEqual([item.id for item in result], ["finding_apply"])

    def test_excludes_findings_when_critic_approved_none(self):
        run = make_plan_aware_run()
        run.critique = CriticReview(decision="approve", approved_finding_ids=[])
        result = ResearchOrchestrator._writable_findings(run)
        self.assertEqual(result, [])


def make_plan_aware_run(finding=None):
    from backend.src.research.schemas import ResearchRun

    finding = finding or make_finding(finding_id="finding_apply")
    return ResearchRun(
        user_request="Request",
        plan=make_plan(),
        findings=[finding],
    )


class OrchestratorRunTests(unittest.IsolatedAsyncioTestCase):
    async def test_max_round_without_writable_findings_extends_research_once(self):
        from backend.src.research.schemas import ResearchRun

        initial_task = make_task(task_id="task_initial")
        initial_task.completed = True
        supplement_task = make_task(
            task_id="task_supplement",
            question="Which evidence is still missing?",
        )
        candidate = make_candidate()
        evidence = make_evidence(
            evidence_id="evidence_supplement",
            task_id=supplement_task.id,
        )
        finding = make_finding(
            finding_id="finding_supplement",
            task_id=supplement_task.id,
            evidence_ids=[evidence.id],
        )
        report = make_report(evidence=evidence)

        stubs = make_stubs()
        stubs.planner.run = AsyncMock(return_value=make_plan(task=initial_task))
        stubs.planner.run_supplement = AsyncMock(return_value=[supplement_task])
        stubs.researcher.run = AsyncMock(return_value=[candidate])
        stubs.reviewer.run = AsyncMock(return_value=[evidence])
        stubs.synthesizer.run = AsyncMock(return_value=finding)
        stubs.critic.run = AsyncMock(side_effect=[
            CriticReview(decision="research_more", approved_finding_ids=[]),
            CriticReview(decision="approve", approved_finding_ids=[finding.id]),
        ])
        stubs.writer.run = AsyncMock(return_value=report)
        stubs.writer.citations_are_valid = MagicMock(return_value=True)

        run = ResearchRun(user_request="Request", max_iterations=1)
        result = await ResearchOrchestrator(
            stubs.planner, stubs.researcher, stubs.reviewer,
            stubs.synthesizer, stubs.critic, stubs.writer,
        ).run(run)

        self.assertEqual(result.status, RunStatus.COMPLETED)
        self.assertEqual(result.iteration, 2)
        self.assertEqual(result.max_iterations, 2)
        self.assertEqual(result.report, report)
        stubs.planner.run_supplement.assert_awaited_once()
        stubs.writer.run.assert_awaited_once()
        self.assertIn(
            "无可用结论可写作，自动增加 1 轮补证",
            "\n".join(result.events),
        )

    async def test_max_round_keeps_extending_until_findings_are_writable(self):
        from backend.src.research.schemas import ResearchRun

        initial_task = make_task(task_id="task_initial")
        initial_task.completed = True
        first_supplement = make_task(
            task_id="task_supplement_1",
            question="Which source could fill the first gap?",
        )
        second_supplement = make_task(
            task_id="task_supplement_2",
            question="Which source could fill the remaining gap?",
        )
        candidate = make_candidate()
        evidence = make_evidence(
            evidence_id="evidence_final",
            task_id=second_supplement.id,
        )
        finding = make_finding(
            finding_id="finding_final",
            task_id=second_supplement.id,
            evidence_ids=[evidence.id],
        )
        report = make_report(evidence=evidence)

        stubs = make_stubs()
        stubs.planner.run = AsyncMock(return_value=make_plan(task=initial_task))
        stubs.planner.run_supplement = AsyncMock(
            side_effect=[[first_supplement], [second_supplement]]
        )
        stubs.researcher.run = AsyncMock(side_effect=[[], [], [candidate]])
        stubs.reviewer.run = AsyncMock(side_effect=[[], [], [evidence]])
        stubs.synthesizer.run = AsyncMock(return_value=finding)
        stubs.critic.run = AsyncMock(side_effect=[
            CriticReview(decision="research_more", approved_finding_ids=[]),
            CriticReview(decision="research_more", approved_finding_ids=[]),
            CriticReview(decision="approve", approved_finding_ids=[finding.id]),
        ])
        stubs.writer.run = AsyncMock(return_value=report)
        stubs.writer.citations_are_valid = MagicMock(return_value=True)

        result = await ResearchOrchestrator(
            stubs.planner, stubs.researcher, stubs.reviewer,
            stubs.synthesizer, stubs.critic, stubs.writer,
        ).run(ResearchRun(user_request="Request", max_iterations=1))

        self.assertEqual(result.status, RunStatus.COMPLETED)
        self.assertEqual(result.iteration, 3)
        self.assertEqual(result.max_iterations, 3)
        self.assertEqual(stubs.planner.run_supplement.await_count, 2)
        self.assertEqual(
            "\n".join(result.events).count("自动增加 1 轮补证"),
            2,
        )

    async def test_missing_writable_findings_stops_when_supplement_plans_nothing(self):
        from backend.src.research.schemas import ResearchRun

        initial_task = make_task(task_id="task_initial")
        initial_task.completed = True
        stubs = make_stubs()
        stubs.planner.run = AsyncMock(return_value=make_plan(task=initial_task))
        stubs.planner.run_supplement = AsyncMock(return_value=[])
        stubs.critic.run = AsyncMock(return_value=CriticReview(
            decision="research_more", approved_finding_ids=[]
        ))

        result = await ResearchOrchestrator(
            stubs.planner, stubs.researcher, stubs.reviewer,
            stubs.synthesizer, stubs.critic, stubs.writer,
        ).run(ResearchRun(user_request="Request", max_iterations=1))

        self.assertEqual(result.status, RunStatus.NEEDS_HUMAN_REVIEW)
        self.assertEqual(result.max_iterations, 2)
        stubs.researcher.run.assert_not_called()
        stubs.writer.run.assert_not_called()
        self.assertIn("补证规划未产生新任务", "\n".join(result.events))

    async def test_run_reaches_completed_terminal_state(self):
        task = make_task(task_id="task_full")
        plan = make_plan(task=task)
        candidate = make_candidate()
        evidence = make_evidence(evidence_id="evidence_full", task_id=task.id)
        finding = make_finding(
            finding_id="finding_full",
            task_id=task.id,
            evidence_ids=[evidence.id],
        )
        report = make_report(evidence=evidence)

        stubs = make_stubs()
        stubs.planner.run = AsyncMock(return_value=plan)
        stubs.researcher.run = AsyncMock(return_value=[candidate])
        stubs.reviewer.run = AsyncMock(return_value=[evidence])
        stubs.synthesizer.run = AsyncMock(return_value=finding)
        stubs.critic.run = AsyncMock(return_value=CriticReview(
            decision="approve", approved_finding_ids=[finding.id]))
        stubs.writer.run = AsyncMock(return_value=report)
        stubs.writer.citations_are_valid = MagicMock(return_value=True)
        persist = AsyncMock()

        from backend.src.research.schemas import ResearchRun
        run = ResearchRun(user_request="Request")
        result = await ResearchOrchestrator(
            stubs.planner, stubs.researcher, stubs.reviewer,
            stubs.synthesizer, stubs.critic, stubs.writer,
            on_update=persist,
        ).run(run)

        self.assertEqual(result.status, RunStatus.COMPLETED)
        self.assertTrue(result.plan.tasks[0].completed)
        self.assertEqual(result.iteration, 1)
        self.assertEqual(result.evidence, [evidence])
        self.assertEqual(result.findings, [finding])
        self.assertEqual(result.report, report)
        self.assertIn("研究计划已生成", result.events)
        self.assertIn("报告已生成", result.events)
        self.assertEqual(persist.await_count, 5)

    async def test_resume_from_critic_checkpoint_reuses_saved_critique(self):
        from backend.src.research.schemas import ResearchRun

        task = make_task(task_id="task_resume")
        finding = make_finding(finding_id="finding_resume", task_id=task.id)
        evidence = make_evidence(evidence_id="evidence_resume", task_id=task.id)
        critique = CriticReview(decision="approve", iteration=1,
                                approved_finding_ids=[finding.id])
        run = ResearchRun(
            user_request="Resume at critic",
            status=RunStatus.CRITIC_REVIEW,
            iteration=1,
            resume_status=RunStatus.CRITIC_REVIEW,
            resume_iteration=1,
            plan=make_plan(task=task),
            findings=[finding],
            evidence=[evidence],
            critique=critique,
            critiques=[critique],
        )
        report = make_report(evidence=evidence)
        stubs = make_stubs()
        stubs.critic.run = AsyncMock(side_effect=AssertionError("must reuse persisted critique"))
        stubs.writer.run = AsyncMock(return_value=report)
        stubs.writer.citations_are_valid = MagicMock(return_value=True)

        result = await ResearchOrchestrator(
            stubs.planner, stubs.researcher, stubs.reviewer,
            stubs.synthesizer, stubs.critic, stubs.writer,
        ).run(run)

        self.assertEqual(result.status, RunStatus.COMPLETED)
        stubs.critic.run.assert_not_awaited()
        stubs.writer.run.assert_awaited_once()

    async def test_writer_failure_fails_run_without_a_stitched_report(self):
        from backend.src.research.schemas import ResearchRun

        task = make_task(task_id="task_write")
        evidence = make_evidence(evidence_id="evidence_write", task_id=task.id)
        finding = make_finding(
            finding_id="finding_write", task_id=task.id, evidence_ids=[evidence.id])
        run = ResearchRun(
            user_request="Request",
            status=RunStatus.WRITING,
            plan=make_plan(task=task),
            evidence=[evidence],
            findings=[finding],
            critique=CriticReview(decision="approve", approved_finding_ids=[finding.id]),
        )
        stubs = make_stubs()
        stubs.writer.run = AsyncMock(side_effect=RuntimeError("model unavailable"))
        persist = AsyncMock()

        result = await ResearchOrchestrator(
            stubs.planner, stubs.researcher, stubs.reviewer,
            stubs.synthesizer, stubs.critic, stubs.writer,
            on_update=persist,
        ).run(run)

        self.assertEqual(result.status, RunStatus.FAILED)
        self.assertIsNone(result.report)
        self.assertIn("报告综合写作失败，未生成报告", result.events)
        self.assertEqual(persist.await_count, 2)

    async def test_wrong_report_language_is_rewritten_once(self):
        from backend.src.research.schemas import ResearchRun

        task = make_task(task_id="task_language")
        evidence = make_evidence(evidence_id="evidence_language", task_id=task.id)
        finding = make_finding(
            finding_id="finding_language",
            task_id=task.id,
            evidence_ids=[evidence.id],
        )
        wrong = make_report(
            evidence=evidence,
            title="English report",
            blocks=[ReportBlock(
                heading="Summary",
                text="This report explains the evidence and conclusion.",
                finding_ids=[finding.id],
                evidence_ids=[evidence.id],
            )],
        )
        repaired = make_report(
            evidence=evidence,
            report_language="ja",
            title="研究報告",
            reference_heading="参考文献",
            blocks=[ReportBlock(
                heading="概要",
                text="この研究報告は証拠と結論を説明します。",
                finding_ids=[finding.id],
                evidence_ids=[evidence.id],
            )],
        )
        run = ResearchRun(
            user_request="Request",
            report_language="ja",
            report_language_source="explicit",
            status=RunStatus.WRITING,
            plan=make_plan(task=task),
            evidence=[evidence],
            findings=[finding],
            critique=CriticReview(
                decision="approve", approved_finding_ids=[finding.id]
            ),
        )
        stubs = make_stubs()
        stubs.writer.run = AsyncMock(side_effect=[wrong, repaired])
        stubs.writer.citations_are_valid = MagicMock(return_value=True)

        result = await ResearchOrchestrator(
            stubs.planner, stubs.researcher, stubs.reviewer,
            stubs.synthesizer, stubs.critic, stubs.writer,
        ).run(run)

        self.assertEqual(result.status, RunStatus.COMPLETED)
        self.assertEqual(result.report.title, "研究報告")
        self.assertEqual(stubs.writer.run.await_count, 2)
        self.assertIn(
            "执行一次定向语言重写",
            "\n".join(result.events),
        )

    async def test_language_mismatch_after_repair_requires_human_review(self):
        from backend.src.research.schemas import ResearchRun

        task = make_task(task_id="task_language_fail")
        evidence = make_evidence(evidence_id="evidence_language_fail", task_id=task.id)
        finding = make_finding(
            finding_id="finding_language_fail",
            task_id=task.id,
            evidence_ids=[evidence.id],
        )
        wrong = make_report(
            evidence=evidence,
            title="English report",
            blocks=[ReportBlock(
                heading="Summary",
                text="This report still uses English.",
                finding_ids=[finding.id],
                evidence_ids=[evidence.id],
            )],
        )
        run = ResearchRun(
            user_request="Request",
            report_language="ja",
            report_language_source="explicit",
            status=RunStatus.WRITING,
            plan=make_plan(task=task),
            evidence=[evidence],
            findings=[finding],
            critique=CriticReview(
                decision="approve", approved_finding_ids=[finding.id]
            ),
        )
        stubs = make_stubs()
        stubs.writer.run = AsyncMock(side_effect=[wrong, wrong])
        stubs.writer.citations_are_valid = MagicMock(return_value=True)

        result = await ResearchOrchestrator(
            stubs.planner, stubs.researcher, stubs.reviewer,
            stubs.synthesizer, stubs.critic, stubs.writer,
        ).run(run)

        self.assertEqual(result.status, RunStatus.NEEDS_HUMAN_REVIEW)
        self.assertEqual(stubs.writer.run.await_count, 2)
        self.assertIn("需人工复核", "\n".join(result.events))

    async def test_research_iteration_skips_failed_task_without_blocking(self):
        task = make_task(task_id="task_failed")
        run = make_plan_aware_run()
        run.plan = make_plan(task=task)

        stubs = make_stubs()
        stubs.researcher.run = AsyncMock(side_effect=RuntimeError("task failed"))
        stubs.reviewer.run = AsyncMock()
        stubs.synthesizer.run = AsyncMock()
        orchestrator = ResearchOrchestrator(
            stubs.planner, stubs.researcher, stubs.reviewer,
            stubs.synthesizer, stubs.critic, stubs.writer,
        )

        await orchestrator._research_iteration(run)
        self.assertEqual(run.iteration, 1)
        self.assertFalse(run.plan.tasks[0].completed)
        self.assertIn("存在执行失败的检索任务，已跳过", run.events)
        self.assertIn("完成第 1 轮检索", run.events)

    async def test_unknown_state_fails_closed(self):
        from backend.src.research.schemas import ResearchRun

        run = ResearchRun(user_request="Request", status=RunStatus.SYNTHESIZING)
        stubs = make_stubs()
        result = await ResearchOrchestrator(
            stubs.planner, stubs.researcher, stubs.reviewer,
            stubs.synthesizer, stubs.critic, stubs.writer,
        ).run(run)

        self.assertEqual(result.status, RunStatus.FAILED)
        self.assertIn("状态机遇到未知状态", result.events)


if __name__ == "__main__":
    unittest.main()

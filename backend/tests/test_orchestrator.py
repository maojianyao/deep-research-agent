"""Smoke tests for the deterministic research orchestrator."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from backend.src.research.orchestrator import ResearchOrchestrator
from backend.src.research.schemas import CriticReview, RunStatus
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
        self.assertEqual(persist.await_count, 4)

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
        persist.assert_awaited_once_with(run)

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

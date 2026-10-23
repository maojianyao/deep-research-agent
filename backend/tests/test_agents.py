"""Smoke tests for deterministic Agent logic without network or LLM calls."""

from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from backend.src.research.agents.critic import CriticAgent
from backend.src.research.agents.planner import PlannerAgent
from backend.src.research.agents.researcher import ResearcherAgent
from backend.src.research.agents.reviewer import EvidenceReviewerAgent
from backend.src.research.agents.synthesizer import SynthesizerAgent
from backend.src.research.agents.writer import WriterAgent
from backend.src.research.schemas import (
    CandidateEvidenceDraft, CandidateEvidenceBatchDraft, CriticReview, EvidenceAssessment,
    EvidenceAssessmentBatch, FindingDraft, OutlineSection, ReportOutline, ResearchPlanDraft,
    ResearchTaskDraft, SectionDraft, SupplementPlanDraft,
)
from backend.tests.factories import (
    make_candidate, make_evidence, make_finding, make_outline, make_plan, make_report, make_section,
    make_source, make_summary, make_task,
)


def make_researcher() -> ResearcherAgent:
    agent = object.__new__(ResearcherAgent)
    agent.searches = []
    agent._semaphore = asyncio.Semaphore(4)
    agent._seen_documents = set()
    return agent


def make_reviewer() -> EvidenceReviewerAgent:
    agent = object.__new__(EvidenceReviewerAgent)
    agent.agent = "fake-compiled-agent"
    agent._semaphore = asyncio.Semaphore(4)
    return agent


def make_synthesizer() -> SynthesizerAgent:
    agent = object.__new__(SynthesizerAgent)
    agent.agent = "fake-compiled-agent"
    agent._semaphore = asyncio.Semaphore(4)
    return agent


def make_critic() -> CriticAgent:
    agent = object.__new__(CriticAgent)
    agent.agent = "fake-compiled-agent"
    return agent


def make_writer() -> WriterAgent:
    agent = object.__new__(WriterAgent)
    agent.outline_agent = "fake-outline-agent"
    agent.section_agent = "fake-section-agent"
    agent.summary_agent = "fake-summary-agent"
    return agent


class PlannerAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_converts_plan_draft(self):
        planner = object.__new__(PlannerAgent)
        planner.agent = "fake-agent"
        planner.supplement_agent = "fake-supplement-agent"
        draft = ResearchPlanDraft(
            research_question="Question", scope="Scope",
            tasks=[ResearchTaskDraft(question="Task")],
        )
        with patch("backend.src.research.agents.planner._ainvoke", AsyncMock(return_value=draft)) as invoke:
            plan = await planner.run("Request", report_language="ja")

        self.assertEqual(plan.research_question, "Question")
        self.assertEqual(len(plan.tasks), 1)
        self.assertEqual(invoke.await_args.args[2], "Request")
        self.assertEqual(invoke.await_args.args[1].report_language, "ja")

    async def test_run_supplement_builds_payload_and_returns_new_tasks(self):
        planner = object.__new__(PlannerAgent)
        planner.agent = "fake-agent"
        planner.supplement_agent = "fake-supplement-agent"
        draft = SupplementPlanDraft(
            supplement_focus="Gap",
            tasks=[ResearchTaskDraft(question="New task")],
        )
        evidence = make_evidence(evidence_id="evidence_1", task_id="task_1")
        finding = make_finding(finding_id="finding_1", task_id="task_1")
        critique = CriticReview(decision="research_more")

        with patch("backend.src.research.agents.planner._ainvoke", AsyncMock(return_value=draft)) as invoke:
            tasks = await planner.run_supplement("Request", critique, [finding], [evidence])

        self.assertEqual([task.question for task in tasks], ["New task"])
        payload = json.loads(invoke.await_args.args[2])
        self.assertEqual(payload["user_request"], "Request")
        self.assertEqual(payload["existing_findings"][0]["id"], "finding_1")
        self.assertEqual(payload["evidence"][0]["id"], "evidence_1")


class ResearcherAgentTests(unittest.IsolatedAsyncioTestCase):
    def test_keywords_extracts_english_and_cjk_tokens(self):
        task = make_task(question="LLM benchmark 中文问题", queries=["模型 test"])
        tokens = ResearcherAgent._keywords(task)
        self.assertIn("llm", tokens)
        self.assertIn("benchmark", tokens)
        self.assertIn("test", tokens)
        self.assertIn("中文", tokens)
        self.assertIn("问题", tokens)

    def test_keywords_supports_non_cjk_unicode_languages(self):
        task = make_task(
            question="تحليل politiques énergétiques",
            queries=["energía renovable", "エネルギー政策"],
        )
        tokens = ResearcherAgent._keywords(task)
        self.assertIn("تحليل", tokens)
        self.assertIn("energía", tokens)
        self.assertIn("renovable", tokens)
        self.assertIn("エネルギー政策", tokens)

    def test_relevance_weights_title_more_than_content(self):
        tokens = {"example"}
        title_hit = make_source(title="Example title", content="other", source_type="unknown")
        content_hit = make_source(title="other", content="example", source_type="unknown")
        self.assertGreater(
            ResearcherAgent._relevance(title_hit, tokens),
            ResearcherAgent._relevance(content_hit, tokens),
        )

    def test_relevance_boosts_primary_and_required_sources(self):
        tokens = {"topic"}
        normal = make_source(title="topic", content="text", source_type="unknown")
        primary = make_source(title="topic", content="text", source_type="government")
        self.assertGreater(
            ResearcherAgent._relevance(primary, tokens),
            ResearcherAgent._relevance(normal, tokens),
        )
        boosted = ResearcherAgent._relevance(primary, tokens, required_types=["government"])
        self.assertGreater(boosted, ResearcherAgent._relevance(primary, tokens))

    def test_select_documents_filters_short_content_and_limits_domains(self):
        task = make_task(question="example")
        docs = [
            make_source(url="https://a.example/1", title="One", content="example " + "x" * 80),
            make_source(url="https://a.example/2", title="Two", content="example " + "x" * 80),
            make_source(url="https://a.example/3", title="Three", content="example " + "x" * 80),
            make_source(url="https://b.example/1", title="Four", content="example " + "x" * 80),
            make_source(url="https://b.example/short", title="Short", content="too short"),
        ]
        selected = ResearcherAgent._select_documents([[[*docs]]], task)
        selected_urls = [str(item.url) for item in selected]

        self.assertEqual(len(selected), 3)
        self.assertNotIn("https://b.example/short", selected_urls)
        self.assertEqual(
            len([url for url in selected_urls if "a.example" in url]),
            ResearcherAgent._MAX_DOCS_PER_DOMAIN,
        )

    def test_limit_candidates_caps_per_url_and_truncates_excerpt(self):
        url = "https://example.com/same"
        candidates = [
            make_candidate(url=url, excerpt="x" * 700),
            make_candidate(url=url, excerpt="y" * 700),
            make_candidate(url=url, excerpt="z" * 700),
            make_candidate(url="https://example.com/other", excerpt="w" * 700),
        ]
        limited = ResearcherAgent._limit_candidates(candidates)

        self.assertEqual(len(limited), 3)
        self.assertLessEqual(len(limited[0].excerpt), ResearcherAgent._MAX_EXCERPT_CHARS + 1)
        self.assertEqual(len({str(item.source.url) for item in limited}), 2)

    async def test_search_all_degrades_failed_source_to_empty(self):
        researcher = make_researcher()

        async def good_search(query):
            return [make_source()]

        async def bad_search(query):
            raise RuntimeError("search failed")

        researcher.searches = [good_search, bad_search]
        result = await researcher._search_all("query")
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]), 1)

    async def test_search_all_deduplicates_across_sources_by_url_and_title(self):
        researcher = make_researcher()

        async def first_source(query):
            return [make_source(url="https://example.com/a?utm_source=x")]

        async def second_source(query):
            return [
                make_source(url="https://example.com/a"),
                make_source(url="https://example.com/b", title="Example source"),
            ]

        researcher.searches = [first_source, second_source]
        result = await researcher._search_all("query")

        self.assertEqual(len(result), 2)
        self.assertEqual(len(result[0]), 1)
        self.assertEqual(result[1], [])

    async def test_run_deduplicates_candidates_by_url(self):
        researcher = make_researcher()
        first = make_candidate(url="https://example.com/a")
        duplicate = make_candidate(url="https://example.com/a")
        second = make_candidate(url="https://example.com/b")
        task = make_task(queries=["q1", "q2", "q3"])

        with patch.object(researcher, "_extract", AsyncMock(side_effect=[
            [first, duplicate], [second],
        ])) as extract:
            result = await researcher.run(task)

        self.assertEqual(len(result), 2)
        self.assertEqual(extract.await_count, 2)

    async def test_run_preserves_distinct_claims_from_same_url(self):
        researcher = make_researcher()
        url = "https://example.com/a"
        candidates = [
            make_candidate(url=url, claim="First claim"),
            make_candidate(url=url, claim="First claim"),
            make_candidate(url=url, claim="Second claim"),
        ]

        with patch.object(researcher, "_extract", AsyncMock(return_value=candidates)):
            result = await researcher.run(make_task(queries=["q"]))

        self.assertEqual([item.claim for item in result], ["First claim", "Second claim"])


class EvidenceReviewerAgentTests(unittest.IsolatedAsyncioTestCase):
    def test_compact_truncates_source_and_excerpt(self):
        candidate = make_candidate(excerpt="x" * 800)
        candidate.source.content = "y" * 2000
        compact = EvidenceReviewerAgent._compact(candidate)

        self.assertLessEqual(len(compact["excerpt"]), EvidenceReviewerAgent._EXCERPT_CHARS + 1)
        self.assertLessEqual(len(compact["content"]), EvidenceReviewerAgent._SOURCE_CHARS + 1)
        self.assertEqual(compact["url"], str(candidate.source.url))

    async def test_run_returns_empty_for_empty_candidates(self):
        reviewer = make_reviewer()
        self.assertEqual(await reviewer.run(make_task(), []), [])

    async def test_run_binds_application_fields_to_assessment(self):
        reviewer = make_reviewer()
        task = make_task(task_id="task_bind")
        candidate = make_candidate()
        assessment = EvidenceAssessment(verdict="supported", confidence=0.9)

        with patch.object(reviewer, "_review_batch", AsyncMock(return_value=([candidate], [assessment]))):
            cards = await reviewer.run(task, [candidate])

        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0].task_id, "task_bind")
        self.assertEqual(cards[0].claim, candidate.claim)
        self.assertEqual(cards[0].verdict, "supported")
        self.assertEqual(cards[0].confidence, 0.9)

    async def test_review_batch_pads_missing_assessments(self):
        reviewer = make_reviewer()
        task = make_task()
        batch = [make_candidate(), make_candidate()]
        result = EvidenceAssessmentBatch(items=[
            EvidenceAssessment(verdict="supported", confidence=0.8),
        ])

        with patch("backend.src.research.agents.reviewer._ainvoke", AsyncMock(return_value=result)):
            reviewed, assessments = await reviewer._review_batch(task, batch)

        self.assertEqual(reviewed, batch)
        self.assertEqual(len(assessments), 2)
        self.assertEqual(assessments[1].verdict, "insufficient")
        self.assertEqual(assessments[1].confidence, 0.0)
        self.assertEqual(assessments[1].limitations, ["审查输出缺失"])

    async def test_review_batch_truncates_extra_assessments(self):
        reviewer = make_reviewer()
        task = make_task()
        batch = [make_candidate()]
        result = EvidenceAssessmentBatch(items=[
            EvidenceAssessment(verdict="supported", confidence=0.8),
            EvidenceAssessment(verdict="contradicted", confidence=0.1),
        ])

        with patch("backend.src.research.agents.reviewer._ainvoke", AsyncMock(return_value=result)):
            _, assessments = await reviewer._review_batch(task, batch)

        self.assertEqual(len(assessments), 1)
        self.assertEqual(assessments[0].verdict, "supported")


class SynthesizerAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_returns_none_without_evidence(self):
        synthesizer = make_synthesizer()
        self.assertIsNone(await synthesizer.run(make_task(), []))

    async def test_run_validates_and_averages_cited_evidence(self):
        synthesizer = make_synthesizer()
        task = make_task(task_id="task_synthesis")
        evidence = [
            make_evidence(evidence_id="evidence_1", task_id=task.id, confidence=0.7,
                          limitations=["shared limitation"]),
            make_evidence(evidence_id="evidence_2", task_id=task.id, confidence=0.9,
                          limitations=["shared limitation"]),
        ]
        draft = FindingDraft(
            statement="Synthesized statement",
            classification="fact",
            confidence=0.99,
            caveats=["draft caveat", "shared limitation"],
            evidence_ids=["evidence_1", "evidence_1", "missing", "evidence_2"],
        )

        with patch("backend.src.research.agents.synthesizer._ainvoke", AsyncMock(return_value=draft)):
            finding = await synthesizer.run(task, evidence)

        self.assertEqual(finding.task_id, task.id)
        self.assertEqual(finding.evidence_ids, ["evidence_1", "evidence_2"])
        self.assertEqual(finding.confidence, 0.8)
        self.assertEqual(finding.caveats, ["draft caveat", "shared limitation"])

    async def test_run_returns_none_for_invalid_citations(self):
        synthesizer = make_synthesizer()
        evidence = [make_evidence(evidence_id="evidence_valid")]
        draft = FindingDraft(statement="Statement", confidence=0.8, evidence_ids=["missing"])

        with patch("backend.src.research.agents.synthesizer._ainvoke", AsyncMock(return_value=draft)):
            self.assertIsNone(await synthesizer.run(make_task(), evidence))

    async def test_run_returns_none_when_model_fails(self):
        synthesizer = make_synthesizer()
        evidence = [make_evidence()]
        with patch("backend.src.research.agents.synthesizer._ainvoke",
                   AsyncMock(side_effect=RuntimeError("model failure"))):
            self.assertIsNone(await synthesizer.run(make_task(), evidence))


class CriticAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_builds_round_robin_payload_and_returns_review(self):
        critic = make_critic()
        finding = make_finding(finding_id="finding_1", task_id="task_1")
        plan = make_plan()
        evidence = [
            make_evidence(evidence_id="evidence_b1", task_id="task_b", confidence=0.9),
            make_evidence(evidence_id="evidence_a1", task_id="task_a", confidence=0.8),
            make_evidence(evidence_id="evidence_b2", task_id="task_b", confidence=0.7),
            make_evidence(evidence_id="evidence_a2", task_id="task_a", confidence=0.6),
        ]
        review = CriticReview(decision="approve")

        with patch("backend.src.research.agents.critic._ainvoke", AsyncMock(return_value=review)) as invoke:
            result = await critic.run([finding], evidence, plan)

        self.assertIs(result, review)
        payload = json.loads(invoke.await_args.args[2])
        self.assertEqual(
            [item["id"] for item in payload["evidence"]],
            ["evidence_b1", "evidence_a1", "evidence_b2", "evidence_a2"],
        )
        self.assertEqual(payload["findings"][0]["id"], "finding_1")
        self.assertEqual(payload["research_plan"]["research_question"], plan.research_question)
        self.assertEqual(payload["research_plan"]["tasks"][0]["id"], plan.tasks[0].id)
        self.assertEqual(invoke.await_args.args[1].report_language, "zh-CN")


class WriterAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_plan_outline_filters_unknown_and_assigns_unassigned(self):
        writer = make_writer()
        findings = [
            make_finding(finding_id="finding_assign"),
            make_finding(finding_id="finding_unassigned"),
        ]
        outline = ReportOutline(
            title="Report",
            sections=[
                OutlineSection(heading="Method", finding_ids=["missing", "finding_assign"]),
                OutlineSection(heading="Body", finding_ids=["finding_assign"]),
                OutlineSection(heading="End", finding_ids=[]),
            ],
        )

        with patch("backend.src.research.agents.writer._ainvoke", AsyncMock(return_value=outline)):
            result = await writer.plan_outline("Request", findings, {})

        self.assertEqual(result.sections[0].finding_ids, ["finding_assign"])
        self.assertEqual(result.sections[1].finding_ids, [])
        self.assertEqual(result.sections[-1].finding_ids, ["finding_unassigned"])

    async def test_write_section_normalizes_model_output(self):
        writer = make_writer()
        outline = make_outline()
        outline.sections[1].finding_ids = ["finding_section"]
        finding = make_finding(finding_id="finding_section", evidence_ids=["evidence_section"])
        evidence = make_evidence(evidence_id="evidence_section")
        draft = SectionDraft(
            heading="Wrong heading",
            text="Section text",
            finding_ids=["finding_section", "missing"],
            evidence_ids=["evidence_section", "missing"],
            key_points=["Wrong point"],
        )

        with patch("backend.src.research.agents.writer._ainvoke", AsyncMock(return_value=draft)):
            result = await writer.write_section(
                "Request", outline, 1,
                {finding.id: finding}, {evidence.id: evidence}, {},
            )

        self.assertEqual(result.heading, outline.sections[1].heading)
        self.assertEqual(result.key_points, outline.sections[1].key_points)
        self.assertEqual(result.finding_ids, ["finding_section"])
        self.assertEqual(result.evidence_ids, ["evidence_section"])

    async def test_write_section_receives_actual_previous_and_explicit_next(self):
        writer = make_writer()
        outline = make_outline()
        outline.sections.append(OutlineSection(
            heading="Conclusion", role="closure", key_points=["Conclusion point"],
            finding_ids=[],
        ))
        previous = make_section(heading="Method", text="Previous section conclusion.")
        draft = make_section()

        with patch("backend.src.research.agents.writer._ainvoke",
                   AsyncMock(return_value=draft)) as invoke:
            await writer.write_section(
                "Request", outline, 1, {}, {}, {},
                previous_section=previous,
            )

        payload = json.loads(invoke.await_args.args[2])
        self.assertEqual(payload["previous_section"]["text_brief"], "Previous section conclusion.")
        self.assertEqual(payload["next_section"]["heading"], "Conclusion")

    async def test_run_passes_actual_previous_section_to_next_section(self):
        writer = make_writer()
        outline = make_outline()
        generated = []

        async def fake_section(request, current_outline, index, finding_by_id,
                               evidence_by_id, task_questions, previous_section=None):
            section = make_section(heading=current_outline.sections[index].heading,
                                   text=f"Section {index}")
            generated.append((section, previous_section))
            return section

        writer.plan_outline = AsyncMock(return_value=outline)
        writer.write_section = fake_section
        writer.write_summary = AsyncMock(return_value=make_summary())

        await writer.run("Request", [make_finding()], [make_evidence()])

        self.assertIsNone(generated[0][1])
        self.assertIs(generated[1][1], generated[0][0])

    async def test_write_section_propagates_model_error_instead_of_copying_findings(self):
        writer = make_writer()
        outline = make_outline()
        outline.sections[1].finding_ids = ["finding_fallback"]
        finding = make_finding(finding_id="finding_fallback")
        evidence = make_evidence(evidence_id="evidence_fallback")

        with patch("backend.src.research.agents.writer._ainvoke",
                   AsyncMock(side_effect=RuntimeError("model failure"))):
            with self.assertRaisesRegex(RuntimeError, "model failure"):
                await writer.write_section(
                    "Request", outline, 1,
                    {finding.id: finding}, {evidence.id: evidence}, {},
                )

    async def test_write_summary_invokes_summary_agent(self):
        writer = make_writer()
        summary = make_summary()
        plan = make_plan(research_domains=["医疗"], risk_level="high")
        with patch(
            "backend.src.research.agents.writer._ainvoke",
            AsyncMock(return_value=summary),
        ) as invoke:
            result = await writer.write_summary(
                make_outline(), [make_section()], plan=plan
            )

        self.assertIs(result, summary)
        payload = json.loads(invoke.await_args.args[2])
        self.assertEqual(payload["research_profile"]["risk_level"], "high")
        self.assertEqual(payload["research_profile"]["domains"], ["医疗"])

    async def test_run_orchestrates_three_stages(self):
        writer = make_writer()
        outline = make_outline()
        sections = [make_section(heading="Method", finding_ids=[], evidence_ids=[]), make_section()]
        summary = make_summary()
        writer.plan_outline = AsyncMock(return_value=outline)
        writer.write_section = AsyncMock(side_effect=sections)
        writer.write_summary = AsyncMock(return_value=summary)

        result = await writer.run("Request", [make_finding()], [make_evidence()])

        writer.plan_outline.assert_awaited_once()
        self.assertEqual(writer.write_section.await_count, 2)
        writer.write_summary.assert_awaited_once()
        self.assertEqual(result.title, "Example report")
        self.assertEqual(result.blocks[0].heading, "执行摘要")
        self.assertEqual(result.blocks[-1].heading, "不确定性与局限")

    def test_assemble_builds_expected_block_order(self):
        outline = make_outline()
        sections = [make_section(heading="Method"), make_section(heading="Finding")]
        summary = make_summary()
        report = WriterAgent.assemble(outline, sections, summary)

        self.assertEqual(
            [block.heading for block in report.blocks],
            ["执行摘要", "Method", "Finding", "结论与建议", "不确定性与局限"],
        )

    def test_assemble_omits_limitations_when_none(self):
        outline = make_outline()
        summary = make_summary(limitations=None)
        report = WriterAgent.assemble(outline, [make_section()], summary)
        self.assertEqual(report.blocks[-1].heading, "结论与建议")

    def test_assemble_uses_model_generated_localized_headings(self):
        outline = make_outline(title="Rapport")
        sections = [make_section(heading="Analyse")]
        summary = make_summary(
            executive_summary_heading="Résumé exécutif",
            conclusion_heading="Conclusion",
            limitations_heading="Limites",
            reference_heading="Références",
        )

        report = WriterAgent.assemble(outline, sections, summary, "fr")

        self.assertEqual(report.report_language, "fr")
        self.assertEqual(report.reference_heading, "Références")
        self.assertEqual(report.blocks[0].heading, "Résumé exécutif")
        self.assertEqual(report.blocks[-1].heading, "Limites")
        self.assertIn("## Références", report.to_markdown([make_evidence()]))

    def test_citations_are_valid(self):
        evidence = make_evidence(evidence_id="evidence_known")
        valid = make_report(evidence=evidence)
        invalid_blocks = [block.model_copy(update={"evidence_ids": ["missing"]})
                          for block in make_report(evidence=evidence).blocks]
        invalid = make_report(evidence=evidence, blocks=invalid_blocks)

        self.assertTrue(WriterAgent.citations_are_valid(valid, [evidence]))
        self.assertFalse(WriterAgent.citations_are_valid(invalid, [evidence]))

        missing_refs = make_report(evidence=evidence)
        missing_refs.blocks[1].evidence_ids = []
        self.assertFalse(WriterAgent.citations_are_valid(missing_refs, [evidence]))


if __name__ == "__main__":
    unittest.main()

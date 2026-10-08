"""Smoke tests for persisted research contracts and conversions."""

from __future__ import annotations

import unittest

from backend.src.research.schemas import (
    CandidateEvidenceBatchDraft, CandidateEvidenceDraft, Finding, ResearchPlanDraft,
    ResearchRun, ResearchTask, ResearchTaskDraft, ReportBlock, ReportDraft, RunStatus,
    SourceRef,
)
from backend.tests.factories import (
    make_evidence, make_finding, make_report, make_source,
)


class SchemaDefaultsTests(unittest.TestCase):
    def test_task_defaults_and_unique_ids(self):
        task = ResearchTask(question="Question")
        self.assertTrue(task.id.startswith("task_"))
        self.assertEqual(task.task_type, "fact")
        self.assertEqual(task.priority, "medium")
        self.assertFalse(task.completed)

        another = ResearchTask(question="Question")
        self.assertNotEqual(task.id, another.id)

    def test_run_defaults_and_events(self):
        run = ResearchRun(user_request="Request")
        self.assertEqual(run.status, RunStatus.PLANNING)
        self.assertEqual(run.max_iterations, 3)
        self.assertEqual(run.events, [])

        run.event("first event")
        self.assertEqual(run.events, ["first event"])

    def test_task_rejects_negative_attempts(self):
        with self.assertRaises(ValueError):
            ResearchTask(question="Question", attempts=-1)


class SchemaConversionTests(unittest.TestCase):
    def test_task_draft_to_task_assigns_application_id(self):
        draft = ResearchTaskDraft(question="Question", queries=["query"])
        task = draft.to_task()
        self.assertTrue(task.id.startswith("task_"))
        self.assertEqual(task.question, "Question")
        self.assertEqual(task.queries, ["query"])
        self.assertFalse(task.completed)

    def test_plan_draft_to_plan_converts_all_tasks(self):
        draft = ResearchPlanDraft(
            research_question="Question",
            scope="Scope",
            tasks=[ResearchTaskDraft(question="One"), ResearchTaskDraft(question="Two")],
        )
        plan = draft.to_plan()
        self.assertEqual(len(plan.tasks), 2)
        self.assertNotEqual(plan.tasks[0].id, plan.tasks[1].id)
        self.assertEqual(plan.research_question, "Question")

    def test_source_ref_omits_content(self):
        doc = make_source()
        ref = SourceRef.from_document(doc)
        self.assertEqual(ref.url, str(doc.url))
        self.assertEqual(ref.title, doc.title)
        self.assertFalse(hasattr(ref, "content"))

    def test_candidate_batch_rebinds_known_urls_and_reports_unknown(self):
        doc = make_source(url="https://example.com/a")
        batch = CandidateEvidenceBatchDraft(items=[
            CandidateEvidenceDraft(source_url=str(doc.url), claim="Known", excerpt="Excerpt"),
            CandidateEvidenceDraft(source_url="https://unknown.example/x", claim="Unknown", excerpt="Excerpt"),
            CandidateEvidenceDraft(source_url=str(doc.url) + "/", claim="Trailing", excerpt="Excerpt"),
        ])
        candidates, unknown = batch.to_candidates({str(doc.url): doc})
        self.assertEqual(len(candidates), 2)
        self.assertEqual(unknown, ["https://unknown.example/x"])

    def test_candidate_batch_rebinds_normalized_url(self):
        doc = make_source(url="https://example.com/a?utm_source=x")
        batch = CandidateEvidenceBatchDraft(items=[
            CandidateEvidenceDraft(source_url="https://example.com/a", claim="Known", excerpt="Excerpt"),
        ])

        candidates, unknown = batch.to_candidates({str(doc.url): doc})

        self.assertEqual(len(candidates), 1)
        self.assertEqual(unknown, [])
        self.assertIs(candidates[0].source, doc)

    def test_evidence_digest_limits_sensitive_fields(self):
        evidence = make_evidence(
            claim="x" * 500,
            excerpt="y" * 500,
            limitations=["z" * 200, "z" * 200, "z" * 200, "z" * 200, "z" * 200],
        )
        digest = evidence.to_digest(excerpt_chars=100)
        self.assertLessEqual(len(digest.claim), 201)
        self.assertLessEqual(len(digest.excerpt), 101)
        self.assertEqual(len(digest.limitations), 4)
        self.assertEqual(digest.source.title, evidence.source.title)

    def test_finding_digest_limits_statement_and_caveats(self):
        finding = make_finding(
            statement="x" * 500,
            caveats=["y" * 200 for _ in range(7)],
        )
        digest = finding.to_digest(statement_chars=100)
        self.assertLessEqual(len(digest.statement), 101)
        self.assertEqual(len(digest.caveats), 5)
        self.assertEqual(digest.evidence_ids, finding.evidence_ids)


class ReportSchemaTests(unittest.TestCase):
    def test_report_markdown_without_evidence(self):
        report = make_report()
        markdown = report.to_markdown()
        self.assertIn("# Example report", markdown)
        self.assertIn("## Summary", markdown)
        self.assertNotIn("## 参考文献", markdown)

    def test_report_markdown_with_cited_evidence(self):
        evidence = make_evidence(evidence_id="evidence_cited")
        report = make_report(evidence=evidence)
        markdown = report.to_markdown([evidence])
        self.assertIn("## 参考文献", markdown)
        self.assertIn("Example source", markdown)
        self.assertIn(str(evidence.source.url), markdown)

    def test_report_markdown_deduplicates_references_by_url_and_title(self):
        source = make_source(url="https://example.com/a?utm_source=x", title="Same source")
        evidence = [
            make_evidence(evidence_id="evidence_1", source=source),
            make_evidence(evidence_id="evidence_2",
                          source=make_source(url="https://example.com/a", title="Same source")),
            make_evidence(evidence_id="evidence_3",
                          source=make_source(url="https://example.com/b", title="Same source")),
        ]
        report = make_report(
            evidence=evidence[0],
            blocks=[
                ReportBlock(heading="Summary", text="Summary"),
                ReportBlock(heading="Finding", text="Finding",
                            evidence_ids=[item.id for item in evidence]),
            ],
        )

        markdown = report.to_markdown(evidence)

        self.assertEqual(markdown.count("[Same source]"), 1)

    def test_run_markdown_is_none_before_report(self):
        run = ResearchRun(user_request="Request")
        self.assertIsNone(run.to_markdown())

    def test_run_markdown_uses_report_and_evidence(self):
        evidence = make_evidence(evidence_id="evidence_run")
        report = make_report(evidence=evidence)
        run = ResearchRun(user_request="Request", report=report, evidence=[evidence])
        self.assertIn("# Example report", run.to_markdown())

    def test_report_requires_at_least_one_block(self):
        with self.assertRaises(ValueError):
            ReportDraft(title="Empty", blocks=[])

    def test_finding_requires_evidence(self):
        with self.assertRaises(ValueError):
            Finding(task_id="task", statement="Statement",
                    classification="fact", evidence_ids=[])


if __name__ == "__main__":
    unittest.main()

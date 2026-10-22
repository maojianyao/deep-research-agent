// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { nextTick } from "vue";
import App from "../App.vue";
import ReportView from "./ReportView.vue";
import { useResearchStore } from "../stores/research";


function completedRun() {
  return {
    id: "run_followup",
    user_request: "Example report",
    status: "completed",
    can_resume: false,
    error: null,
    iteration: 1,
    max_iterations: 1,
    created_at: "2026-10-22T10:00:00",
    updated_at: "2026-10-22T10:00:00",
    plan: { research_question: "Question", scope: "Scope", completion_rules: [], tasks: [] },
    candidates: [],
    evidence: [],
    findings: [],
    critiques: [],
    report: {
      title: "Example report",
      markdown: "# Example report\n\n## Summary\n\nSummary text with **key evidence** (evidence_abc123).",
      anchor_digest: "a".repeat(64),
      blocks: [],
    },
    events: [],
  };
}

function mountCompletedReport(followUp = null) {
  const pinia = createPinia();
  setActivePinia(pinia);
  const store = useResearchStore();
  store.runId = "run_followup";
  store.run = completedRun();
  store.followUps = followUp ? [followUp] : [];
  store.selectedFollowUpId = followUp?.id || null;
  store.loadRuns = vi.fn();
  const wrapper = mount(App, {
    attachTo: document.body,
    global: { plugins: [pinia] },
  });
  return { wrapper, store };
}

function selectNode(node) {
  const range = document.createRange();
  range.selectNodeContents(node);
  const selection = window.getSelection();
  selection.removeAllRanges();
  selection.addRange(range);
  return selection;
}

afterEach(() => {
  window.getSelection()?.removeAllRanges();
  document.body.innerHTML = "";
  vi.restoreAllMocks();
});

describe("report follow-up DOM", () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn();
  });

  test("selecting completed report prose reveals 提问 and opens a focused side panel", async () => {
    const { wrapper } = mountCompletedReport();
    const body = wrapper.find("[data-report-body]");
    expect(body.exists()).toBe(true);
    const paragraph = body.element.querySelector("p");

    selectNode(paragraph);
    await body.trigger("mouseup");
    await nextTick();

    const trigger = wrapper.find("[data-follow-up-trigger]");
    expect(trigger.exists()).toBe(true);
    expect(trigger.text()).toContain("提问");

    await trigger.trigger("click");
    await nextTick();

    const panel = wrapper.find("[data-follow-up-panel]");
    expect(panel.exists()).toBe(true);
    expect(panel.text()).toContain("Summary text with key evidence");
    expect(document.activeElement).toBe(panel.find("[data-follow-up-input]").element);

    await panel.find("[data-follow-up-input]").setValue("   ");
    await panel.find("form").trigger("submit");
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  test("citation controls and selections outside the report do not reveal 提问", async () => {
    const { wrapper } = mountCompletedReport();
    const citation = wrapper.find(".citation-id");
    expect(citation.exists()).toBe(true);

    selectNode(citation.element);
    await citation.trigger("mouseup");
    await nextTick();
    expect(wrapper.find("[data-follow-up-trigger]").exists()).toBe(false);

    selectNode(wrapper.find("h1").element);
    await wrapper.find("main").trigger("mouseup");
    await nextTick();
    expect(wrapper.find("[data-follow-up-trigger]").exists()).toBe(false);
  });

  test("selection anchors use canonical offsets across rendered table blocks", async () => {
    const markdown = [
      "# Report",
      "",
      "Intro",
      "",
      "| A | B |",
      "| --- | --- |",
      "| 1 | 2 |",
      "",
      "After table.",
    ].join("\n");
    const wrapper = mount(ReportView, {
      attachTo: document.body,
      props: { markdown, active: false, eligible: true },
    });
    const renderedText = "Report Intro A B 1 2 After table.";

    selectNode(wrapper.findAll("td")[0].element);
    await wrapper.trigger("mouseup");
    let selection = wrapper.emitted("selection").at(-1)[0];
    expect(selection.anchor).toMatchObject({
      text: "1",
      start: renderedText.indexOf("1"),
      end: renderedText.indexOf("1") + 1,
    });

    const paragraph = wrapper.findAll("[data-report-body] p").at(-1);
    selectNode(paragraph.element);
    await wrapper.trigger("mouseup");
    selection = wrapper.emitted("selection").at(-1)[0];
    expect(selection.anchor).toMatchObject({
      text: "After table.",
      start: renderedText.indexOf("After table."),
      end: renderedText.indexOf("After table.") + "After table.".length,
    });
  });

  test("submitting a first question renders the persisted assistant answer", async () => {
    const { wrapper } = mountCompletedReport();
    const answer = "**已收到**：这段内容说明证据。";
    let request;
    globalThis.fetch.mockImplementation(async (url, options) => {
      request = { url, body: JSON.parse(options.body) };
      return {
        ok: true,
        status: 201,
        json: async () => ({
          id: "followup_new",
          run_id: "run_followup",
          anchor: request.body.anchor,
          messages: [
            {
              id: 1, role: "user", sequence: 1, content: request.body.question,
              status: "completed", error_code: null, error_message: null,
              created_at: "2026-10-22T10:01:00",
            },
            {
              id: 2, role: "assistant", sequence: 2, content: answer,
              status: "completed", error_code: null, error_message: null,
              created_at: "2026-10-22T10:01:01",
            },
          ],
          created_at: "2026-10-22T10:01:00",
          updated_at: "2026-10-22T10:01:01",
        }),
      };
    });

    const body = wrapper.find("[data-report-body]");
    selectNode(body.element.querySelector("strong"));
    await body.trigger("mouseup");
    await wrapper.find("[data-follow-up-trigger]").trigger("click");
    const panel = wrapper.find("[data-follow-up-panel]");
    await panel.find("[data-follow-up-input]").setValue("这段说明了什么？");
    await panel.find("form").trigger("submit");
    await flushPromises();
    await nextTick();

    expect(request.url).toBe("/api/research-runs/run_followup/follow-ups");
    expect(request.body.question).toBe("这段说明了什么？");
    expect(request.body.anchor.report_digest).toBe("a".repeat(64));
    const renderedText = "Example report Summary Summary text with key evidence (evidence_abc123).";
    expect(request.body.anchor).toMatchObject({
      text: "key evidence",
      start: renderedText.indexOf("key evidence"),
      end: renderedText.indexOf("key evidence") + "key evidence".length,
      prefix: "Example report Summary Summary text with",
      suffix: "(evidence_abc123).",
    });
    expect(panel.text()).toContain("这段说明了什么？");
    expect(panel.find("strong").text()).toBe("已收到");
    expect(panel.find("script").exists()).toBe(false);
  });

  test("restored conversation displays safe Markdown answers and blocks unsafe HTML", async () => {
    const thread = {
      id: "followup_saved",
      run_id: "run_followup",
      anchor: {
        text: "Summary text",
        start: 0,
        end: 12,
        prefix: "",
        suffix: "",
        report_digest: "a".repeat(64),
      },
      messages: [
        {
          id: 1, role: "user", sequence: 1, content: "请解释这一段。",
          status: "completed", error_code: null, error_message: null,
          created_at: "2026-10-22T10:01:00",
        },
        {
          id: 2, role: "assistant", sequence: 2,
          content: "**安全答案**\n\n<script>alert('xss')</script>",
          status: "completed", error_code: null, error_message: null,
          created_at: "2026-10-22T10:01:01",
        },
      ],
      created_at: "2026-10-22T10:01:00",
      updated_at: "2026-10-22T10:01:01",
    };
    const { wrapper } = mountCompletedReport(thread);
    await nextTick();

    const panel = wrapper.find("[data-follow-up-panel]");
    expect(panel.text()).toContain("请解释这一段。");
    expect(panel.find("strong").text()).toBe("安全答案");
    expect(panel.find("script").exists()).toBe(false);
    expect(panel.text()).not.toContain("alert('xss')");
    expect(document.activeElement).toBe(panel.find("[data-follow-up-input]").element);
  });
});

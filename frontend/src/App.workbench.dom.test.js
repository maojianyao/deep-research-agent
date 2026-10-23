// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia } from "pinia";
import App from "./App.vue";


function response(body) {
  return {
    ok: true,
    status: 200,
    json: async () => body,
  };
}

function completedRun(id = "run_route") {
  return {
    id,
    user_request: "A routable research report",
    status: "completed",
    can_resume: false,
    error: null,
    iteration: 1,
    max_iterations: 1,
    report_language: "zh-CN",
    report_language_name: "简体中文",
    report_language_quality: "verified",
    report_language_source: "detected",
    report_direction: "ltr",
    created_at: "2026-10-22T10:00:00",
    updated_at: "2026-10-22T10:00:00",
    plan: {
      research_question: "Question",
      scope: "Scope",
      research_domains: [],
      risk_level: "standard",
      completion_rules: [],
      tasks: [],
    },
    candidates: [],
    evidence: [],
    findings: [],
    critiques: [],
    report: {
      title: "Routable report",
      language: "zh-CN",
      language_name: "简体中文",
      direction: "ltr",
      markdown: "# Routable report\n\nReport body.",
      anchor_digest: "a".repeat(64),
      blocks: [],
    },
    events: [],
  };
}

function listResponse(items = []) {
  return response({
    items,
    total: items.length,
    page: 1,
    page_size: 20,
    summary: {
      total: items.length,
      active: 0,
      completed: items.length,
      needs_human_review: 0,
    },
  });
}

function runSummary(status, overrides = {}) {
  return {
    id: `run_${status}`,
    user_request: `Research request for ${status}`,
    report_language: "zh-CN",
    report_language_name: "简体中文",
    report_language_quality: "verified",
    report_direction: "ltr",
    status,
    can_resume: status === "paused",
    unfinished_tasks: 0,
    iteration: 1,
    max_iterations: 3,
    created_at: "2026-10-22T10:00:00",
    updated_at: "2026-10-22T10:00:00",
    research_question: "Question",
    title: status === "completed" ? "Completed report" : null,
    has_report: status === "completed",
    ...overrides,
  };
}

function routeFetch(runs) {
  return vi.fn(async (url) => {
    const path = String(url);
    if (path.startsWith("/api/research-runs?")) {
      return listResponse(runs.map((run) => ({
        ...run,
        research_question: run.plan?.research_question || run.research_question,
        title: run.report?.title || run.title,
        unfinished_tasks: 0,
      })));
    }
    if (path.endsWith("/follow-ups")) {
      return response({ items: [] });
    }
    const run = runs.find((item) => path.endsWith(`/${item.id}`));
    if (run) return response(run);
    return { ok: false, status: 404, json: async () => ({ detail: "Research run not found" }) };
  });
}


afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});


describe("research workspace overview", () => {
  beforeEach(() => {
    window.history.replaceState({}, "", "/");
  });

  test("shows workspace totals and filters active research through the active status group", async () => {
    const requests = [];
    globalThis.fetch = vi.fn(async (url) => {
      requests.push(String(url));
      return response({
        items: [],
        total: 0,
        page: 1,
        page_size: 20,
        summary: {
          total: 17,
          active: 3,
          completed: 12,
          needs_human_review: 2,
        },
      });
    });

    const wrapper = mount(App, {
      attachTo: document.body,
      global: { plugins: [createPinia()] },
    });
    await flushPromises();

    const metrics = wrapper.findAll(".metric-value").map((item) => item.text());
    expect(metrics).toEqual(["17", "3", "12", "2"]);

    const activeFilter = wrapper.findAll(".filter-button").find(
      (button) => button.text() === "进行中",
    );
    expect(activeFilter.attributes("aria-pressed")).toBe("false");
    await activeFilter.trigger("click");
    await flushPromises();

    expect(activeFilter.attributes("aria-pressed")).toBe("true");
    expect(requests.at(-1)).toContain("status=active");
  });

  test("leads with research tasks and shows actions for each task state", async () => {
    const requests = [];
    const items = [
      runSummary("completed"),
      runSummary("researching"),
      runSummary("needs_human_review"),
    ];
    globalThis.fetch = vi.fn(async (url) => {
      requests.push(String(url));
      return listResponse(items);
    });
    const wrapper = mount(App, {
      attachTo: document.body,
      global: { plugins: [createPinia()] },
    });
    await flushPromises();

    const register = wrapper.find(".research-register");
    const guide = wrapper.find("[data-research-guide]");
    expect(register.exists()).toBe(true);
    expect(guide.exists()).toBe(true);
    expect(
      register.element.compareDocumentPosition(guide.element)
      & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(wrapper.find(".home-brief").text()).not.toContain("研究如何推进");

    const rows = wrapper.findAll(".register-table tbody tr");
    expect(rows[0].find(".row-menu").text()).toContain("删除");
    expect(rows[0].text()).toContain("下载");
    expect(rows[1].text()).toContain("结束任务");
    expect(rows[2].text()).toContain("查看待复核");
    expect(rows[1].text()).toContain("第 1 / 3 轮");
    expect(rows[1].text()).not.toContain("%");

    await wrapper.find('select[aria-label="研究档案排序"]').setValue("updated_asc");
    await flushPromises();
    expect(requests.at(-1)).toContain("sort=updated_asc");
  });
});


describe("research run navigation", () => {
  beforeEach(() => {
    window.history.replaceState({}, "", "/");
    HTMLElement.prototype.scrollIntoView = vi.fn();
  });

  test("directly opening a run URL restores the completed report by default", async () => {
    const run = completedRun();
    globalThis.fetch = routeFetch([run]);
    window.history.replaceState({}, "", `/?run=${run.id}`);

    const wrapper = mount(App, {
      attachTo: document.body,
      global: { plugins: [createPinia()] },
    });
    await flushPromises();
    await flushPromises();

    expect(wrapper.find(".run-title").text()).toContain("A routable research report");
    expect(wrapper.find('[role="tab"][aria-selected="true"]').text()).toContain("研究报告");
    expect(wrapper.find("[data-report-body]").exists()).toBe(true);
    expect(window.location.search).toBe(`?run=${run.id}`);
  });

  test("opening from the task list writes a stable URL and browser back restores the list", async () => {
    const run = completedRun("run_from_list");
    globalThis.fetch = routeFetch([run]);
    const wrapper = mount(App, {
      attachTo: document.body,
      global: { plugins: [createPinia()] },
    });
    await flushPromises();

    await wrapper.findAll(".line-action").find(
      (button) => button.text() === "查看",
    ).trigger("click");
    await flushPromises();
    await flushPromises();

    expect(window.location.search).toBe("?run=run_from_list");
    expect(wrapper.find(".run-title").text()).toContain("A routable research report");

    window.history.replaceState({}, "", "/");
    window.dispatchEvent(new PopStateEvent("popstate"));
    await flushPromises();

    expect(wrapper.find(".home-title").text()).toContain("从一个问题");
    expect(wrapper.find(".run-title").exists()).toBe(false);
  });

  test("an invalid run URL shows an actionable missing-report state", async () => {
    globalThis.fetch = routeFetch([]);
    window.history.replaceState({}, "", "/?run=run_missing");

    const wrapper = mount(App, {
      attachTo: document.body,
      global: { plugins: [createPinia()] },
    });
    await flushPromises();
    await flushPromises();

    const state = wrapper.find(".run-load-state");
    expect(state.attributes("role")).toBe("alert");
    expect(state.text()).toContain("找不到这份研究档案");
    expect(state.findAll("button").map((button) => button.text())).toEqual([
      "重新读取",
      "返回研究任务",
    ]);
  });

  test("uses the report as the primary dossier view and exposes a section outline", async () => {
    const run = completedRun("run_reading");
    run.report.markdown = [
      "# Evidence report",
      "",
      "## Main finding",
      "",
      "Long-form report body.",
      "",
      "## Limitations",
      "",
      "Important limits.",
    ].join("\n");
    globalThis.fetch = routeFetch([run]);
    window.history.replaceState({}, "", "/?run=run_reading");

    const wrapper = mount(App, {
      attachTo: document.body,
      global: { plugins: [createPinia()] },
    });
    await flushPromises();
    await flushPromises();

    const tabs = wrapper.find('[role="tablist"][aria-label="研究档案内容"]');
    expect(tabs.exists()).toBe(true);
    const reportTab = tabs.findAll('[role="tab"]').find((tab) => tab.text().includes("研究报告"));
    const planTab = tabs.findAll('[role="tab"]').find((tab) => tab.text().includes("研究计划"));
    expect(reportTab.attributes("aria-selected")).toBe("true");
    expect(wrapper.find('[role="tabpanel"]').text()).toContain("Long-form report body");

    await planTab.trigger("click");
    expect(planTab.attributes("aria-selected")).toBe("true");
    expect(wrapper.find("#dossier-panel-plan").text()).toContain("Question");

    await reportTab.trigger("click");
    await flushPromises();

    const outline = wrapper.find("[data-report-outline]");
    expect(outline.exists()).toBe(true);
    expect(outline.text()).toContain("Main finding");
    expect(outline.text()).toContain("Limitations");
    expect(wrapper.find("[data-report-back-to-top]").exists()).toBe(true);
  });

  test("opens the matching evidence and returns to the report citation", async () => {
    const run = completedRun("run_trace");
    run.report.markdown = "# Trace report\n\nTrace claim (evidence_trace).";
    run.evidence = [{
      id: "evidence_trace",
      task_id: "task_1",
      iteration: 1,
      claim: "Trace evidence claim",
      excerpt: "Trace source excerpt",
      locator: "Paragraph 1",
      verdict: "supported",
      confidence: 0.9,
      limitations: [],
      source: {
        url: "https://example.com/trace",
        title: "Trace source",
        publisher: "Trace publisher",
        published_at: "2026-01-01",
        source_type: "official",
        language: "en",
      },
    }];
    globalThis.fetch = vi.fn(async (url) => {
      const path = String(url);
      if (path.endsWith("/evidence/evidence_trace")) {
        return response(run.evidence[0]);
      }
      if (path.includes("/evidence?")) {
        return response({
          items: run.evidence,
          total: 1,
          page: 1,
          page_size: 20,
          facets: { source_types: ["official"], languages: ["en"], verdicts: ["supported"] },
        });
      }
      if (path.endsWith("/follow-ups")) return response({ items: [] });
      if (path.startsWith("/api/research-runs?")) return listResponse([run]);
      return response(run);
    });
    window.history.replaceState({}, "", "/?run=run_trace");

    const wrapper = mount(App, {
      attachTo: document.body,
      global: { plugins: [createPinia()] },
    });
    await flushPromises();
    await flushPromises();

    const citation = wrapper.find('.citation-id[data-ref="evidence_trace"]');
    expect(citation.text()).toBe("1");
    await citation.trigger("click");
    await flushPromises();

    expect(wrapper.find("#dossier-tab-evidence").attributes("aria-selected")).toBe("true");
    expect(wrapper.find("[data-evidence-detail]").text()).toContain("Trace source excerpt");
    await wrapper.find("[data-return-to-report]").trigger("click");
    await flushPromises();

    expect(wrapper.find("#dossier-tab-report").attributes("aria-selected")).toBe("true");
    expect(wrapper.find("[data-report-body]").isVisible()).toBe(true);
  });

  test("uses readable citation numbers in synthesis findings", async () => {
    const run = completedRun("run_findings_trace");
    run.report.markdown = "# Report\n\nNo direct citation in prose.";
    run.evidence = [{
      id: "evidence_finding_trace",
      task_id: "task_1",
      iteration: 1,
      claim: "Finding evidence",
      excerpt: "Source excerpt",
      verdict: "supported",
      confidence: 0.9,
      limitations: [],
      source: {
        url: "https://example.com/finding",
        title: "Finding source",
        publisher: "Publisher",
        published_at: "2026-01-01",
        source_type: "official",
        language: "en",
      },
    }];
    run.findings = [{
      id: "finding_trace",
      task_id: "task_1",
      iteration: 1,
      statement: "Finding statement (evidence_finding_trace).",
      classification: "fact",
      confidence: 0.9,
      caveats: [],
      evidence_ids: ["evidence_finding_trace"],
    }];
    globalThis.fetch = vi.fn(async (url) => {
      const path = String(url);
      if (path.endsWith("/evidence/evidence_finding_trace")) {
        return response({ ...run.evidence[0], finding_ids: ["finding_trace"] });
      }
      if (path.includes("/evidence?")) {
        return response({
          items: run.evidence,
          total: 1,
          page: 1,
          page_size: 20,
          facets: { source_types: ["official"], languages: ["en"], verdicts: ["supported"] },
        });
      }
      if (path.endsWith("/follow-ups")) return response({ items: [] });
      if (path.startsWith("/api/research-runs?")) return listResponse([run]);
      return response(run);
    });
    window.history.replaceState({}, "", "/?run=run_findings_trace");
    const wrapper = mount(App, {
      attachTo: document.body,
      global: { plugins: [createPinia()] },
    });
    await flushPromises();
    await flushPromises();

    await wrapper.find("#dossier-tab-findings").trigger("click");
    const finding = wrapper.find(".finding-text");
    expect(finding.text()).not.toContain("evidence_finding_trace");
    expect(finding.find('.citation-id[data-ref="evidence_finding_trace"]').text()).toBe("1");
    await finding.find('.citation-id[data-ref="evidence_finding_trace"]').trigger("click");
    await flushPromises();

    const backToConclusion = wrapper.findAll("[data-return-to-report]").find(
      (button) => button.text().includes("综合结论"),
    );
    expect(backToConclusion).toBeTruthy();
    await backToConclusion.trigger("click");
    await flushPromises();

    expect(wrapper.find("#dossier-tab-findings").attributes("aria-selected")).toBe("true");
    expect(document.activeElement?.closest("[data-citation-item]")?.dataset.citationItem)
      .toBe("finding_trace");
  });

  test("links one evidence item back to findings and review notes", async () => {
    const run = completedRun("run_review_trace");
    run.report.markdown = "# Report\n\nNo report citation.";
    run.evidence = [{
      id: "evidence_review_trace",
      task_id: "task_1",
      iteration: 1,
      claim: "Review evidence",
      excerpt: "Review excerpt",
      verdict: "partially_supported",
      confidence: 0.8,
      limitations: [],
      source: {
        url: "https://example.com/review",
        title: "Review source",
        publisher: "Publisher",
        published_at: "2026-02-01",
        source_type: "academic",
        language: "en",
      },
    }];
    run.findings = [{
      id: "finding_review_trace",
      task_id: "task_1",
      iteration: 1,
      statement: "Supported point (evidence_review_trace).",
      classification: "fact",
      confidence: 0.8,
      caveats: [],
      evidence_ids: ["evidence_review_trace"],
    }];
    run.critiques = [{
      iteration: 1,
      decision: "research_more",
      approved_finding_ids: [],
      issues: [{
        severity: "major",
        finding_id: "finding_review_trace",
        problem: "The review needs stronger support (evidence_review_trace).",
        follow_up_questions: [],
        follow_up_queries: [],
      }],
    }];
    globalThis.fetch = vi.fn(async (url) => {
      const path = String(url);
      if (path.endsWith("/evidence/evidence_review_trace")) {
        return response({
          ...run.evidence[0],
          finding_ids: ["finding_review_trace"],
        });
      }
      if (path.includes("/evidence?")) {
        return response({
          items: run.evidence,
          total: 1,
          page: 1,
          page_size: 20,
          facets: { source_types: ["academic"], languages: ["en"], verdicts: ["partially_supported"] },
        });
      }
      if (path.endsWith("/follow-ups")) return response({ items: [] });
      if (path.startsWith("/api/research-runs?")) return listResponse([run]);
      return response(run);
    });
    window.history.replaceState({}, "", "/?run=run_review_trace");
    const wrapper = mount(App, {
      attachTo: document.body,
      global: { plugins: [createPinia()] },
    });
    await flushPromises();
    await flushPromises();

    await wrapper.find("#dossier-tab-critiques").trigger("click");
    await wrapper.find("#dossier-panel-critiques .citation-id").trigger("click");
    await flushPromises();

    const returnButtons = wrapper.findAll("[data-return-to-report]");
    expect(returnButtons.map((button) => button.text())).toEqual(
      expect.arrayContaining(["回到综合结论", "回到审稿意见"]),
    );
    const backToReview = returnButtons.find(
      (button) => button.text() === "回到审稿意见",
    );
    await backToReview.trigger("click");
    await flushPromises();

    expect(wrapper.find("#dossier-tab-critiques").attributes("aria-selected")).toBe("true");
    expect(document.activeElement?.closest("[data-citation-item]")?.dataset.citationItem)
      .toBe("critique-1-0");
  });
});

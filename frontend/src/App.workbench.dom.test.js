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

function routeFetch(runs) {
  return vi.fn(async (url) => {
    const path = String(url);
    if (path.startsWith("/api/research-runs?")) {
      return listResponse(runs.map((run) => ({
        ...run,
        research_question: run.plan.research_question,
        title: run.report?.title,
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
});


describe("research run navigation", () => {
  beforeEach(() => {
    window.history.replaceState({}, "", "/");
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
    expect(wrapper.find("[data-report-section]").element.open).toBe(true);
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
});

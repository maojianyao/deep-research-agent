// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { nextTick } from "vue";
import App from "../App.vue";
import ReportView from "./ReportView.vue";
import { useResearchStore } from "../stores/research";


class FakeEventSource {
  static instances = [];

  constructor(url) {
    this.url = url;
    this.listeners = new Map();
    this.closed = false;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type, listener) {
    this.listeners.set(type, listener);
  }

  close() {
    this.closed = true;
  }

  emit(type, data) {
    this.listeners.get(type)?.({ data: JSON.stringify(data) });
  }
}


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
  store.followUps = Array.isArray(followUp) ? followUp : (followUp ? [followUp] : []);
  store.selectedFollowUpId = Array.isArray(followUp)
    ? followUp.find((item) => item.is_minimized === false)?.id || null
    : followUp?.id || null;
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
    globalThis.EventSource = FakeEventSource;
    FakeEventSource.instances = [];
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

  test("report renders multiple highlights, markers, and restores an overlapping selection", async () => {
    const rendered = "Example report Summary Summary text with key evidence (evidence_abc123).";
    const firstId = "followup_first";
    const secondId = "followup_second";
    const threads = [
      {
        id: firstId, is_minimized: false,
        anchor: {
          text: "Example", start: 0, end: 7, prefix: "", suffix: "",
          report_digest: "a".repeat(64),
        },
        messages: [],
      },
      {
        id: secondId, is_minimized: true,
        anchor: {
          text: "key evidence", start: rendered.indexOf("key evidence"),
          end: rendered.indexOf("key evidence") + "key evidence".length,
          prefix: "", suffix: "", report_digest: "a".repeat(64),
        },
        messages: [],
      },
    ];
    const wrapper = mount(ReportView, {
      attachTo: document.body,
      props: {
        markdown: completedRun().report.markdown,
        active: false,
        eligible: true,
        followUps: threads,
      },
    });
    await nextTick();

    expect(wrapper.findAll("[data-follow-up-highlight]")).toHaveLength(2);
    const markers = wrapper.findAll("[data-follow-up-marker]");
    expect(markers).toHaveLength(1);
    expect(markers[0].attributes("data-thread-id")).toBe(secondId);

    selectNode(wrapper.find("h1").element);
    await wrapper.trigger("mouseup");
    expect(wrapper.emitted("restore-follow-up")?.at(-1)).toEqual([firstId]);
    expect(wrapper.emitted("selection")?.at(-1)).toEqual([null]);
  });

  test("clicking a marker exchanges the expanded conversation and close creates markers", async () => {
    const first = {
      id: "followup_open",
      run_id: "run_followup",
      is_minimized: false,
      anchor: {
        text: "Example", start: 0, end: 7, prefix: "", suffix: "",
        report_digest: "a".repeat(64),
      },
      messages: [
        { id: 31, role: "user", sequence: 1, content: "第一会话问题", status: "completed" },
        { id: 32, role: "assistant", sequence: 2, content: "第一会话回答", status: "completed" },
      ],
      stream_cursor: 3,
    };
    const second = {
      id: "followup_marker",
      run_id: "run_followup",
      is_minimized: true,
      anchor: {
        text: "Summary", start: 23, end: 30, prefix: "", suffix: "",
        report_digest: "a".repeat(64),
      },
      messages: [
        { id: 39, role: "user", sequence: 1, content: "第二会话早期问题", status: "completed" },
        { id: 40, role: "assistant", sequence: 2, content: "第二会话早期回答", status: "completed" },
        { id: 41, role: "user", sequence: 3, content: "第二会话问题", status: "completed" },
        { id: 42, role: "assistant", sequence: 4, content: "第二会话回答", status: "completed" },
      ],
      stream_cursor: 5,
    };
    let stateBody = { items: [{ ...first, is_minimized: true }, { ...second, is_minimized: false }] };
    globalThis.fetch.mockImplementation(async () => ({
      ok: true,
      status: 200,
      json: async () => stateBody,
    }));
    const { wrapper } = mountCompletedReport([first, second]);
    await nextTick();

    let panel = wrapper.find("[data-follow-up-panel]");
    expect(panel.text()).toContain("第一会话回答");
    const marker = wrapper.find(`[data-follow-up-marker][data-thread-id="${second.id}"]`);
    expect(marker.exists()).toBe(true);
    await marker.trigger("click");
    await flushPromises();
    await nextTick();

    panel = wrapper.find("[data-follow-up-panel]");
    expect(panel.text()).toContain("第二会话早期回答");
    expect(panel.text()).toContain("第二会话回答");
    expect(wrapper.findAll("[data-follow-up-marker]")).toHaveLength(1);

    stateBody = { items: [{ ...first, is_minimized: true }, { ...second, is_minimized: true }] };
    await panel.find('button[aria-label="关闭追问"]').trigger("click");
    await flushPromises();
    await nextTick();

    expect(wrapper.find("[data-follow-up-panel]").exists()).toBe(false);
    expect(wrapper.findAll("[data-follow-up-marker]")).toHaveLength(2);
  });

  test("deleting a conversation requires confirmation and removes its panel, highlight, and marker", async () => {
    const first = {
      id: "followup_delete",
      run_id: "run_followup",
      is_minimized: false,
      anchor: {
        text: "Example", start: 0, end: 7, prefix: "", suffix: "",
        report_digest: "a".repeat(64),
      },
      messages: [
        { id: 61, role: "user", sequence: 1, content: "待删除问题", status: "completed" },
        { id: 62, role: "assistant", sequence: 2, content: "待删除回答", status: "completed" },
      ],
      stream_cursor: 3,
    };
    const second = {
      id: "followup_keep",
      run_id: "run_followup",
      is_minimized: true,
      anchor: {
        text: "Summary", start: 23, end: 30, prefix: "", suffix: "",
        report_digest: "a".repeat(64),
      },
      messages: [],
      stream_cursor: 0,
    };
    let request;
    globalThis.fetch.mockImplementation(async (url, options) => {
      request = { url, method: options.method };
      return { ok: true, status: 204, json: async () => null };
    });
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    const { wrapper } = mountCompletedReport([first, second]);
    await nextTick();

    const deleteButton = wrapper.find("[data-delete-follow-up]");
    expect(deleteButton.exists()).toBe(true);
    await deleteButton.trigger("click");
    await flushPromises();
    expect(globalThis.fetch).not.toHaveBeenCalled();
    expect(wrapper.find("[data-follow-up-panel]").exists()).toBe(true);

    await deleteButton.trigger("click");
    await flushPromises();
    await nextTick();

    expect(confirm).toHaveBeenCalledTimes(2);
    expect(confirm.mock.calls[0][0]).toContain("删除");
    expect(request).toEqual({
      url: "/api/research-runs/run_followup/follow-ups/followup_delete",
      method: "DELETE",
    });
    expect(wrapper.find("[data-follow-up-panel]").exists()).toBe(false);
    expect(
      wrapper.find('[data-thread-id="followup_delete"]').exists()
    ).toBe(false);
    expect(
      wrapper.find('[data-thread-id="followup_keep"]').exists()
    ).toBe(true);
  });

  test("research task deletion warning mentions owned follow-up conversations", async () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const store = useResearchStore();
    store.runId = null;
    store.runs = [{
      id: "run_with_conversations",
      user_request: "带追问的研究",
      status: "completed",
      iteration: 1,
      max_iterations: 1,
      updated_at: "2026-10-23T09:00:00",
    }];
    store.total = 1;
    store.loadRuns = vi.fn();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const wrapper = mount(App, {
      attachTo: document.body,
      global: { plugins: [pinia] },
    });
    const deleteButton = wrapper.findAll("button").find((button) => button.text() === "删除");
    expect(deleteButton).toBeTruthy();

    await deleteButton.trigger("click");

    expect(confirm).toHaveBeenCalledTimes(1);
    expect(confirm.mock.calls[0][0]).toContain("追问会话");
  });

  test("clearing a report selection keeps the expanded generating stream connected", async () => {
    const thread = {
      id: "followup_generating",
      run_id: "run_followup",
      is_minimized: false,
      anchor: {
        text: "Example", start: 0, end: 7, prefix: "", suffix: "",
        report_digest: "a".repeat(64),
      },
      messages: [
        {
          id: 51, role: "user", sequence: 1, content: "请解释。",
          status: "completed", error_code: null, error_message: null,
        },
        {
          id: 52, role: "assistant", sequence: 2, content: "正在回答",
          status: "generating", error_code: null, error_message: null,
        },
      ],
      stream_cursor: 2,
    };
    const { wrapper, store } = mountCompletedReport(thread);
    await nextTick();
    store.connectFollowUpStream(thread);
    const source = FakeEventSource.instances[0];

    window.getSelection()?.removeAllRanges();
    await wrapper.find("[data-report-body]").trigger("mouseup");
    await nextTick();

    expect(source.closed).toBe(false);
    expect(store.selectedFollowUpId).toBe(thread.id);
  });

  test("submitting a first question renders the persisted assistant answer", async () => {
    const { wrapper } = mountCompletedReport();
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
              id: 2, role: "assistant", sequence: 2, content: "",
              status: "generating", error_code: null, error_message: null,
              created_at: "2026-10-22T10:01:01",
            },
          ],
          stream_cursor: 1,
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
    expect(FakeEventSource.instances).toHaveLength(1);
    expect(FakeEventSource.instances[0].url).toContain("after_sequence=1");

    FakeEventSource.instances[0].emit("follow-up", {
      thread_id: "followup_new",
      sequence: 2,
      type: "delta",
      message_id: 2,
      content: "**已收到**：这段内容说明证据。",
      status: "generating",
    });
    await nextTick();
    expect(panel.find("strong").text()).toBe("已收到");
    expect(panel.find("script").exists()).toBe(false);

    FakeEventSource.instances[0].emit("follow-up", {
      thread_id: "followup_new",
      sequence: 3,
      type: "completed",
      message_id: 2,
      content: "",
      status: "completed",
    });
    await nextTick();
    expect(FakeEventSource.instances[0].closed).toBe(true);
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

  test("failed answer shows an error and retry replaces the same assistant response", async () => {
    const failedThread = {
      id: "followup_retry",
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
          id: 11, role: "user", sequence: 1, content: "原问题只出现一次",
          status: "completed", error_code: null, error_message: null,
          created_at: "2026-10-22T10:01:00",
        },
        {
          id: 12, role: "assistant", sequence: 2, content: "失败前的片段",
          status: "failed", error_code: "generation_failed",
          error_message: "模型暂时不可用",
          created_at: "2026-10-22T10:01:01",
        },
      ],
      stream_cursor: 3,
      created_at: "2026-10-22T10:01:00",
      updated_at: "2026-10-22T10:01:01",
    };
    let request;
    globalThis.fetch.mockImplementation(async (url, options) => {
      request = { url, options };
      return {
        ok: true,
        status: 202,
        json: async () => ({
          ...failedThread,
          messages: [
            failedThread.messages[0],
            {
              ...failedThread.messages[1], content: "", status: "generating",
              error_code: null, error_message: null,
            },
          ],
          stream_cursor: 4,
        }),
      };
    });
    const { wrapper } = mountCompletedReport(failedThread);
    await nextTick();

    const panel = wrapper.find("[data-follow-up-panel]");
    expect(panel.text()).toContain("模型暂时不可用");
    const retry = panel.find("[data-retry-answer]");
    expect(retry.exists()).toBe(true);

    await retry.trigger("click");
    await flushPromises();
    await nextTick();

    expect(request.url).toBe(
      "/api/research-runs/run_followup/follow-ups/followup_retry/messages/12/retry"
    );
    expect(request.options.method).toBe("POST");
    expect(panel.text().split("原问题只出现一次").length - 1).toBe(1);
    expect(panel.text()).not.toContain("失败前的片段");
    expect(FakeEventSource.instances).toHaveLength(1);
    expect(FakeEventSource.instances[0].url).toContain("after_sequence=4");

    FakeEventSource.instances[0].emit("follow-up", {
      thread_id: failedThread.id,
      sequence: 5,
      type: "delta",
      message_id: 12,
      content: "重试后的回答",
      status: "generating",
    });
    FakeEventSource.instances[0].emit("follow-up", {
      thread_id: failedThread.id,
      sequence: 6,
      type: "completed",
      message_id: 12,
      content: "",
      status: "completed",
    });
    await nextTick();

    expect(panel.text()).toContain("重试后的回答");
    expect(panel.text().split("原问题只出现一次").length - 1).toBe(1);
  });

  test("reader can append another question while the full transcript stays visible", async () => {
    const existingThread = {
      id: "followup_continue",
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
          id: 21, role: "user", sequence: 1, content: "第一个问题",
          status: "completed", error_code: null, error_message: null,
          created_at: "2026-10-22T10:01:00",
        },
        {
          id: 22, role: "assistant", sequence: 2, content: "第一个回答",
          status: "completed", error_code: null, error_message: null,
          created_at: "2026-10-22T10:01:01",
        },
      ],
      stream_cursor: 3,
      created_at: "2026-10-22T10:01:00",
      updated_at: "2026-10-22T10:01:01",
    };
    let request;
    globalThis.fetch.mockImplementation(async (url, options) => {
      request = { url, body: JSON.parse(options.body) };
      return {
        ok: true,
        status: 201,
        json: async () => ({
          ...existingThread,
          messages: [
            ...existingThread.messages,
            {
              id: 23, role: "user", sequence: 3, content: request.body.question,
              status: "completed", error_code: null, error_message: null,
              created_at: "2026-10-22T10:02:00",
            },
            {
              id: 24, role: "assistant", sequence: 4, content: "",
              status: "generating", error_code: null, error_message: null,
              created_at: "2026-10-22T10:02:01",
            },
          ],
          stream_cursor: 4,
        }),
      };
    });
    const { wrapper } = mountCompletedReport(existingThread);
    await nextTick();

    const panel = wrapper.find("[data-follow-up-panel]");
    expect(panel.find("[data-follow-up-input]").attributes("maxlength")).toBe("2000");
    await panel.find("[data-follow-up-input]").setValue("第二个问题");
    await panel.find("form").trigger("submit");
    await flushPromises();
    await nextTick();

    expect(request.url).toBe(
      "/api/research-runs/run_followup/follow-ups/followup_continue/questions"
    );
    expect(panel.text()).toContain("第一个问题");
    expect(panel.text()).toContain("第一个回答");
    expect(panel.text()).toContain("第二个问题");
    expect(FakeEventSource.instances[0].url).toContain("after_sequence=4");

    FakeEventSource.instances[0].emit("follow-up", {
      thread_id: existingThread.id,
      sequence: 5,
      type: "delta",
      message_id: 24,
      content: "第二个回答",
      status: "generating",
    });
    FakeEventSource.instances[0].emit("follow-up", {
      thread_id: existingThread.id,
      sequence: 6,
      type: "completed",
      message_id: 24,
      content: "",
      status: "completed",
    });
    await nextTick();

    expect(panel.text()).toContain("第二个回答");
    expect(panel.text().split("第一个问题").length - 1).toBe(1);
  });

  test("reloaded generating conversation resumes from its cursor and reconnects without duplicates", async () => {
    const thread = {
      id: "followup_streaming",
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
          id: 1, role: "user", sequence: 1, content: "请继续解释。",
          status: "completed", error_code: null, error_message: null,
          created_at: "2026-10-22T10:01:00",
        },
        {
          id: 2, role: "assistant", sequence: 2, content: "第一段",
          status: "generating", error_code: null, error_message: null,
          created_at: "2026-10-22T10:01:01",
        },
      ],
      stream_cursor: 2,
      is_minimized: false,
      created_at: "2026-10-22T10:01:00",
      updated_at: "2026-10-22T10:01:01",
    };
    const pinia = createPinia();
    setActivePinia(pinia);
    const store = useResearchStore();
    store.loadRuns = vi.fn();
    globalThis.fetch.mockImplementation(async (url) => {
      if (url === "/api/research-runs/run_followup") {
        return { ok: true, status: 200, json: async () => completedRun() };
      }
      if (url === "/api/research-runs/run_followup/follow-ups") {
        return { ok: true, status: 200, json: async () => ({ items: [thread] }) };
      }
      throw new Error(`unexpected fetch ${url}`);
    });

    await store.openRun("run_followup");
    const wrapper = mount(App, {
      attachTo: document.body,
      global: { plugins: [pinia] },
    });
    await nextTick();

    const panel = wrapper.find("[data-follow-up-panel]");
    expect(panel.text()).toContain("第一段");
    expect(FakeEventSource.instances).toHaveLength(1);
    expect(FakeEventSource.instances[0].url).toContain("after_sequence=2");

    const firstSource = FakeEventSource.instances[0];
    firstSource.emit("follow-up", {
      thread_id: thread.id,
      sequence: 3,
      type: "delta",
      message_id: 2,
      content: "，第二段",
      status: "generating",
    });
    await nextTick();
    expect(panel.text().split("第一段").length - 1).toBe(1);
    expect(panel.text()).toContain("第一段，第二段");

    vi.useFakeTimers();
    try {
      firstSource.onerror();
      vi.advanceTimersByTime(1000);
      await flushPromises();
      expect(FakeEventSource.instances).toHaveLength(2);
      expect(FakeEventSource.instances[1].url).toContain("after_sequence=3");

      FakeEventSource.instances[1].emit("follow-up", {
        thread_id: thread.id,
        sequence: 4,
        type: "completed",
        message_id: 2,
        content: "",
        status: "completed",
      });
      await nextTick();
      expect(FakeEventSource.instances[1].closed).toBe(true);
      expect(panel.text().split("第一段").length - 1).toBe(1);
      expect(panel.text()).toContain("第一段，第二段");
    } finally {
      vi.useRealTimers();
    }
  });
});

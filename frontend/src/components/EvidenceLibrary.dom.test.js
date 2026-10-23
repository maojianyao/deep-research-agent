// @vitest-environment jsdom
import { afterEach, describe, expect, test, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import EvidenceLibrary from "./EvidenceLibrary.vue";


function evidence(id, overrides = {}) {
  return {
    id,
    task_id: "task_1",
    iteration: 1,
    claim: `Evidence claim ${id}`,
    excerpt: `Exact source excerpt ${id}`,
    locator: "Section 2",
    verdict: "supported",
    confidence: 0.92,
    limitations: ["Limited sample"],
    source: {
      url: `https://example.com/${id}`,
      title: `Source ${id}`,
      publisher: "Example publisher",
      published_at: "2026-01-01",
      source_type: "academic",
      language: "en",
    },
    finding_ids: ["finding_1"],
    ...overrides,
  };
}

function payload(items, overrides = {}) {
  return {
    items,
    total: 3,
    page: 1,
    page_size: 2,
    facets: {
      source_types: ["academic", "official"],
      languages: ["en", "ja"],
      verdicts: ["partially_supported", "supported"],
    },
    ...overrides,
  };
}


afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});


describe("evidence library", () => {
  test("lists every pageable result and filters through the evidence API", async () => {
    const requests = [];
    globalThis.fetch = vi.fn(async (url) => {
      requests.push(String(url));
      return { ok: true, status: 200, json: async () => payload([evidence("evidence_1"), evidence("evidence_2")]) };
    });
    const wrapper = mount(EvidenceLibrary, {
      props: { runId: "run_evidence" },
      attachTo: document.body,
    });
    await flushPromises();

    expect(wrapper.findAll("[data-evidence-card]")).toHaveLength(2);
    expect(wrapper.find("[data-evidence-total]").text()).toContain("3");
    expect(wrapper.find('select[aria-label="来源类型"]').text()).toContain("academic");
    expect(wrapper.find('select[aria-label="来源语言"]').text()).toContain("English");

    await wrapper.find('select[aria-label="来源类型"]').setValue("official");
    await flushPromises();
    expect(requests.at(-1)).toContain("source_type=official");
  });

  test("opens the complete evidence detail and source excerpt", async () => {
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => payload([evidence("evidence_detail")]),
    }));
    const wrapper = mount(EvidenceLibrary, {
      props: { runId: "run_evidence" },
      attachTo: document.body,
    });
    await flushPromises();

    await wrapper.find("[data-evidence-card] button").trigger("click");

    const detail = wrapper.find("[data-evidence-detail]");
    expect(detail.text()).toContain("Exact source excerpt evidence_detail");
    expect(detail.text()).toContain("Example publisher");
    expect(detail.find('a[href="https://example.com/evidence_detail"]').exists()).toBe(true);
  });

  test("shows a guided empty state and can clear filters", async () => {
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => payload([], { total: 0 }),
    }));
    const wrapper = mount(EvidenceLibrary, {
      props: { runId: "run_evidence" },
      attachTo: document.body,
    });
    await flushPromises();

    await wrapper.find('select[aria-label="来源类型"]').setValue("official");
    await flushPromises();

    expect(wrapper.text()).toContain("没有符合当前条件的证据");
    expect(wrapper.find("[data-clear-evidence-filters]").exists()).toBe(true);
  });

  test("traces an evidence card back to every report occurrence", async () => {
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => payload([evidence("evidence_trace")]),
    }));
    const wrapper = mount(EvidenceLibrary, {
      props: {
        runId: "run_evidence",
        citationOccurrences: {
          evidence_trace: [
            { index: 0, label: "1" },
            { index: 1, label: "4" },
          ],
        },
      },
      attachTo: document.body,
    });
    await flushPromises();
    await wrapper.find("[data-evidence-card] button").trigger("click");

    const links = wrapper.findAll("[data-return-to-report]");
    expect(links.map((link) => link.text())).toEqual(["回到引用 1", "回到引用 4"]);
    await links[1].trigger("click");
    expect(wrapper.emitted("return-to-report")?.at(-1)?.[0]).toEqual({
      evidenceId: "evidence_trace",
      occurrenceIndex: 1,
    });
  });
});

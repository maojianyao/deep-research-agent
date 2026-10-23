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

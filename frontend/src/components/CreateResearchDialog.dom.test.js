// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import CreateResearchDialog from "./CreateResearchDialog.vue";


function response(body) {
  return {
    ok: true,
    status: 200,
    json: async () => body,
  };
}


afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  document.body.innerHTML = "";
});


describe("create research request", () => {
  beforeEach(() => {
    HTMLDialogElement.prototype.showModal = vi.fn(function showModal() {
      this.open = true;
    });
    HTMLDialogElement.prototype.close = vi.fn(function close() {
      this.open = false;
    });
  });

  test("explains presets and the final language before submission", async () => {
    vi.useFakeTimers();
    globalThis.fetch = vi.fn(async () => response({
      tag: "zh-CN",
      name: "简体中文",
      quality: "verified",
      source: "detected",
    }));
    const wrapper = mount(CreateResearchDialog, { attachTo: document.body });
    wrapper.vm.open();

    expect(wrapper.findAll("[data-depth-preset]").map((item) => item.text())).toHaveLength(3);
    expect(wrapper.text()).toContain("快速");
    expect(wrapper.text()).toContain("标准");
    expect(wrapper.text()).toContain("深度");

    await wrapper.find("#topic").setValue("研究人工智能治理政策");
    await vi.advanceTimersByTimeAsync(300);
    await flushPromises();

    expect(wrapper.find("[data-report-language-preview]").text()).toContain("简体中文");
    expect(wrapper.find("[data-report-language-preview]").text()).toContain("zh-CN");
    expect(wrapper.find("[data-report-language-preview]").text()).toContain("跟随研究请求");
  });

  test("submits the selected preset as a compatible iteration count", async () => {
    const wrapper = mount(CreateResearchDialog, { attachTo: document.body });
    wrapper.vm.open();
    await wrapper.find("#topic").setValue("A useful research request");
    await wrapper.find('[data-depth-preset="deep"] input').setValue(true);
    await wrapper.find("form").trigger("submit");

    expect(wrapper.emitted("create")?.at(-1)?.[0]).toMatchObject({
      topic: "A useful research request",
      iterations: 5,
      reportLanguage: "",
    });
  });

  test("closing and reopening restores the unsent draft and options", async () => {
    const wrapper = mount(CreateResearchDialog, { attachTo: document.body });
    wrapper.vm.open();
    await wrapper.find("#topic").setValue("Keep this draft");
    await wrapper.find('[data-depth-preset="quick"] input').setValue(true);
    await wrapper.find('button[data-dialog-cancel]').trigger("click");

    wrapper.vm.open();

    expect(wrapper.find("#topic").element.value).toBe("Keep this draft");
    expect(wrapper.find('[data-depth-preset="quick"] input').element.checked).toBe(true);
  });

  test("renders a mobile-safe action footer with accessible validation state", async () => {
    const wrapper = mount(CreateResearchDialog, { attachTo: document.body });
    wrapper.vm.open();

    expect(wrapper.find("[data-dialog-actions]").exists()).toBe(true);
    expect(wrapper.find("#topic").attributes("required")).toBeDefined();
    expect(wrapper.find("#topic").attributes("aria-describedby")).toContain("topic-help");
    expect(wrapper.find("[data-form-error]").exists()).toBe(false);
  });
});

// @vitest-environment jsdom
import { describe, expect, test } from "vitest";
import { mount } from "@vue/test-utils";
import ResearchStagePanel from "./ResearchStagePanel.vue";


function run(overrides = {}) {
  return {
    status: "researching",
    resume_status: null,
    iteration: 1,
    max_iterations: 3,
    updated_at: "2026-10-23T10:00:00",
    plan: {
      tasks: [
        { id: "task_1", completed: true },
        { id: "task_2", completed: false },
      ],
    },
    findings: [],
    critiques: [],
    events: [],
    ...overrides,
  };
}


describe("research stage panel", () => {
  test("shows the real current stage and a supplemental-research loop", () => {
    const wrapper = mount(ResearchStagePanel, {
      props: {
        run: run({
          iteration: 2,
          events: [
            { sequence: 1, message: "审稿要求补充检索，转交规划Agent增量补证", created_at: "2026-10-23T10:00:00" },
          ],
        }),
      },
    });

    expect(wrapper.find("[data-current-stage]").text()).toContain("跨源检索");
    expect(wrapper.text()).toContain("第 2 轮补证");
    expect(wrapper.text()).toContain("已完成 1 / 2 项研究任务");
    expect(wrapper.text()).toContain("审稿要求补充检索");
    expect(wrapper.text()).not.toContain("%");
    expect(wrapper.findAll("[data-stage-state='complete']")).toHaveLength(2);
  });

  test("does not infer a supplemental round from iteration count alone", () => {
    const wrapper = mount(ResearchStagePanel, {
      props: {
        run: run({ iteration: 2 }),
      },
    });

    expect(wrapper.find("[data-current-stage]").text()).toContain("跨源检索");
    expect(wrapper.text()).not.toContain("第 2 轮补证");
  });

  test("keeps the saved checkpoint visible while paused", () => {
    const wrapper = mount(ResearchStagePanel, {
      props: {
        run: run({
          status: "paused",
          resume_status: "critic_review",
          critiques: [{ iteration: 1, decision: "approve", issues: [] }],
        }),
      },
    });

    expect(wrapper.find("[data-current-stage]").text()).toContain("综合反审");
    expect(wrapper.text()).toContain("已暂停");
    expect(wrapper.text()).toContain("继续任务后从当前阶段恢复");
  });

  test("marks every stage complete for a completed run", () => {
    const wrapper = mount(ResearchStagePanel, {
      props: {
        run: run({
          status: "completed",
          plan: { tasks: [{ id: "task_1", completed: true }] },
          report: { title: "Finished report" },
        }),
      },
    });

    expect(wrapper.findAll("[data-stage-state='complete']")).toHaveLength(6);
    expect(wrapper.text()).toContain("报告已完成");
    expect(wrapper.text()).toContain("查看或下载报告");
  });
});

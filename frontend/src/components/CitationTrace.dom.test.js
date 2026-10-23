// @vitest-environment jsdom
import { afterEach, describe, expect, test } from "vitest";
import { mount } from "@vue/test-utils";
import ReportView from "./ReportView.vue";


afterEach(() => {
  document.body.innerHTML = "";
});


describe("report citation trace", () => {
  test("shows readable labels while preserving source evidence identifiers", () => {
    const wrapper = mount(ReportView, {
      props: {
        markdown: "First claim (evidence_second). Second claim (evidence_first).",
        citationLabels: {
          evidence_second: "1",
          evidence_first: "2",
        },
      },
    });

    const citations = wrapper.findAll(".citation-id");
    expect(citations.map((item) => item.text())).toEqual(["1", "2"]);
    expect(citations[0].attributes("data-ref")).toBe("evidence_second");
    expect(citations[0].attributes("aria-label")).toContain("第 1 条来源");
  });
});

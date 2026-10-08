import test from "node:test";
import assert from "node:assert/strict";
import { marked } from "marked";
import "./markdown.js";

test("report markdown keeps tables and nested lists and links all citation IDs", () => {
  const markdown = [
    "| 地区 | 策略 |",
    "| --- | --- |",
    "| 中国 | 开放权重 |",
    "",
    "1. 主要结论（evidence_abc123，evidence_ghi789）",
    "   - 支持点 (evidence_def456、evidence_jkl012；补充来源)",
    "裸引用 evidence_bare123 与 finding_bare456，及混合格式（evidence_mix123, finding_mix456；来源注释）。",
    "代码标识 `evidence_code123` 不应成为引用按钮。",
    "     - 补充说明",
  ].join("\n");
  const html = marked.parse(markdown);

  assert.match(html, /<table>/);
  assert.match(html, /<ol>[\s\S]*<ul>[\s\S]*<li>支持点/);
  assert.match(html, /class="citation-id" data-ref="evidence_abc123"/);
  assert.match(html, /class="citation-id" data-ref="evidence_ghi789"/);
  assert.match(html, /class="citation-id" data-ref="evidence_def456"/);
  assert.match(html, /class="citation-id" data-ref="evidence_jkl012"/);
  assert.match(html, /class="citation-id" data-ref="evidence_bare123"/);
  assert.match(html, /class="citation-id" data-ref="finding_bare456"/);
  assert.match(html, /class="citation-id" data-ref="evidence_mix123"/);
  assert.match(html, /class="citation-id" data-ref="finding_mix456"/);
  assert.match(html, /<code>evidence_code123<\/code>/);
  assert.doesNotMatch(html, /data-ref="evidence_code123"/);
});

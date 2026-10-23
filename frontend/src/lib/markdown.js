import { marked, Renderer } from "marked";
import DOMPurify from "dompurify";

const renderer = new Renderer();
renderer.link = ({ href, title, text }) => {
  const safeHref = /^https?:\/\//i.test(href || "") ? href : "#";
  return `<a href="${safeHref}"${title ? ` title="${title}"` : ""} target="_blank" rel="noopener noreferrer">${text}</a>`;
};

marked.use({
  renderer,
  gfm: true,
  breaks: true,
  extensions: [{
    name: "researchCitation",
    level: "inline",
    start(source) {
      const indexes = [
        source.indexOf("("),
        source.indexOf("（"),
        source.search(/\b(?:evidence|finding)_[a-zA-Z0-9_]+/),
      ].filter((index) => index >= 0);
      return indexes.length ? Math.min(...indexes) : undefined;
    },
    tokenizer(source) {
      const code = /^(`+)[^`\n]+\1/.exec(source);
      if (code) return;
      const grouped = /^[（(]((?:evidence|finding)_[a-zA-Z0-9_]+[^）)]*)[）)]/.exec(source);
      if (grouped) {
        return {
          type: "researchCitation",
          raw: grouped[0],
          ids: grouped[1].match(/(?:evidence|finding)_[a-zA-Z0-9_]+/g),
          note: grouped[1].replace(/(?:evidence|finding)_[a-zA-Z0-9_]+/g, "").replace(/[，,、;；\s]+/g, " ").trim(),
        };
      }

      const bare = /^(?:evidence|finding)_[a-zA-Z0-9_]+\b/.exec(source);
      if (!bare) return;
      return {
        type: "researchCitation",
        raw: bare[0],
        ids: [bare[0]],
        note: "",
      };
    },
    renderer(token) {
      const links = token.ids.map((id) =>
        `<button type="button" class="citation-id" data-ref="${id}">${id}</button>`
      ).join("、");
      const note = token.note ? ` <span class="citation-note">${token.note}</span>` : "";
      return token.raw.startsWith("（") || token.raw.startsWith("(")
        ? `（${links}${note}）`
        : `${links}${note}`;
    },
  }],
});

export function safeMarkdown(markdown = "", { citationLabels = {} } = {}) {
  let rendered = marked.parse(markdown);
  rendered = rendered.replace(
    /<button type="button" class="citation-id" data-ref="([^"]+)">[^<]*<\/button>/g,
    (button, referenceId) => {
      const label = citationLabels[referenceId];
      if (!label) return button;
      const accessibleLabel = `第 ${label} 条来源：打开证据详情`;
      return `<button type="button" class="citation-id" data-ref="${referenceId}" aria-label="${accessibleLabel}" title="${accessibleLabel}">${label}</button>`;
    },
  );
  const dirty = rendered;
  return DOMPurify.sanitize(dirty, { USE_PROFILES: { html: true } });
}

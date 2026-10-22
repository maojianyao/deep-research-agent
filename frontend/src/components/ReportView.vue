<template>
  <div ref="reportBody" data-report-body class="markdown-content" @click="handleCitation" @mouseup="captureSelection">
    <div v-if="html" v-html="html"></div>
    <p v-else class="text-sm text-slate-500">{{ active ? "研究报告生成后会显示在这里。" : "当前研究没有生成报告。" }}</p>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import { safeMarkdown } from "../lib/markdown";

const props = defineProps({
  markdown: { type: String, default: "" },
  active: Boolean,
  eligible: Boolean,
});
const emit = defineEmits(["citation", "selection", "selection-error"]);
const reportBody = ref(null);

const html = computed(() => safeMarkdown(props.markdown));

function handleCitation(event) {
  const target = event.target.closest(".citation-id");
  if (target) emit("citation", target.dataset.ref);
}

function normalizeSpace(value) {
  return value.normalize("NFKC").replace(/\s+/gu, " ").trim();
}

const blockElements = new Set([
  "ADDRESS", "ARTICLE", "ASIDE", "BLOCKQUOTE", "DIV", "DL", "DT", "DD",
  "H1", "H2", "H3", "H4", "H5", "H6", "LI", "OL", "P", "PRE",
  "TABLE", "TBODY", "TD", "TH", "THEAD", "TR", "UL",
]);

function canonicalNodeText(node) {
  if (node.nodeType === Node.TEXT_NODE) return node.nodeValue || "";
  if (node.nodeName === "BR") return " ";
  const parts = [];
  const block = blockElements.has(node.nodeName);
  if (block) parts.push(" ");
  for (const child of node.childNodes) parts.push(canonicalNodeText(child));
  if (block) parts.push(" ");
  return parts.join("");
}

function canonicalRawRangeText(range) {
  const fragment = range.cloneContents();
  return Array.from(fragment.childNodes, canonicalNodeText).join("");
}

function canonicalRangeText(range) {
  return normalizeSpace(canonicalRawRangeText(range));
}

function normalizeRangePrefix(value) {
  const normalized = normalizeSpace(value);
  return normalized && /\s$/u.test(value.normalize("NFKC")) ? `${normalized} ` : normalized;
}

function endpointElement(node) {
  return node?.nodeType === Node.ELEMENT_NODE ? node : node?.parentElement;
}

function rangePart(root, boundary, boundaryOffset, fromStart) {
  const range = document.createRange();
  range.selectNodeContents(root);
  if (fromStart) range.setEnd(boundary, boundaryOffset);
  else range.setStart(boundary, boundaryOffset);
  const text = canonicalRawRangeText(range);
  return fromStart ? normalizeRangePrefix(text) : normalizeSpace(text);
}

function clearSelection() {
  emit("selection", null);
}

function captureSelection() {
  if (!props.eligible || !props.markdown) {
    clearSelection();
    return;
  }
  const selection = window.getSelection();
  if (!selection?.rangeCount || selection.isCollapsed) {
    clearSelection();
    return;
  }
  const range = selection.getRangeAt(0);
  const root = reportBody.value;
  const startElement = endpointElement(range.startContainer);
  const endElement = endpointElement(range.endContainer);
  if (!root?.contains(range.commonAncestorContainer)
      || startElement?.closest(".citation-id")
      || endElement?.closest(".citation-id")) {
    clearSelection();
    return;
  }

  const text = canonicalRangeText(range);
  if (!text) {
    clearSelection();
    return;
  }
  if (Array.from(text).length > 8000) {
    emit("selection-error", "选区超过 8,000 个字符，请缩短后重试。");
    clearSelection();
    return;
  }

  const before = rangePart(root, range.startContainer, range.startOffset, true);
  const after = rangePart(root, range.endContainer, range.endOffset, false);
  const start = Array.from(before).length;
  const rect = typeof range.getBoundingClientRect === "function"
    ? range.getBoundingClientRect()
    : { right: 0, bottom: 0 };
  emit("selection", {
    anchor: {
      text,
      start,
      end: start + Array.from(text).length,
      prefix: Array.from(normalizeSpace(before)).slice(-80).join(""),
      suffix: Array.from(after).slice(0, 80).join(""),
      report_digest: "",
    },
    position: {
      x: rect.right || Math.min(window.innerWidth - 96, 640),
      y: rect.bottom || 180,
    },
  });
}

</script>

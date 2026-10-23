<template>
  <div
    ref="reportBody"
    data-report-body
    tabindex="-1"
    class="relative"
    :lang="language || undefined"
    :dir="direction || 'auto'"
    @click="handleCitation"
    @mouseup="captureSelection"
  >
    <div ref="reportContent" class="markdown-content">
      <div v-if="html" v-html="html"></div>
      <p v-else class="text-sm text-slate-500">{{ active ? "研究报告生成后会显示在这里。" : "当前研究没有生成报告。" }}</p>
    </div>

    <div data-follow-up-overlay class="pointer-events-none absolute inset-0 z-10">
      <span
        v-for="(highlight, index) in highlights"
        :key="`${highlight.threadId}-${index}`"
        data-follow-up-highlight
        :data-thread-id="highlight.threadId"
        class="absolute rounded-sm border-b-2"
        :class="highlight.minimized
          ? 'border-emerald-500 bg-emerald-300/25'
          : 'border-amber-500 bg-amber-300/35'"
        :style="highlight.style"
        aria-hidden="true"
      ></span>
      <button
        v-for="marker in markers"
        :key="marker.threadId"
        type="button"
        data-follow-up-marker
        :data-thread-id="marker.threadId"
        class="follow-up-marker pointer-events-auto fixed z-30 grid h-11 w-11 place-items-center border-0 bg-transparent p-0"
        data-touch-target="44"
        :style="marker.style"
        title="恢复追问"
        :aria-label="`恢复追问：${marker.anchorText}`"
        @mousedown.prevent.stop
        @click.stop="$emit('restore-follow-up', marker.threadId)"
      ><span class="follow-up-marker-face" aria-hidden="true">追</span></button>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { safeMarkdown } from "../lib/markdown";

const props = defineProps({
  markdown: { type: String, default: "" },
  active: Boolean,
  eligible: Boolean,
  followUps: { type: Array, default: () => [] },
  language: { type: String, default: "" },
  direction: { type: String, default: "auto" },
  expanded: { type: Boolean, default: true },
  citationLabels: { type: Object, default: () => ({}) },
});
const emit = defineEmits([
  "citation", "selection", "selection-error", "restore-follow-up", "headings", "heading-change",
]);
const reportBody = ref(null);
const reportContent = ref(null);
const highlights = ref([]);
const markers = ref([]);
let selectionTimer;

const html = computed(() => safeMarkdown(props.markdown, {
  citationLabels: props.citationLabels,
}));
const overlayState = computed(() => props.followUps.map((thread) => ({
  id: thread.id,
  anchor: thread.anchor,
  isMinimized: thread.is_minimized,
})));

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
  if (node.nodeType === Node.ELEMENT_NODE && node.matches?.(".citation-id")) {
    return node.dataset.ref || "";
  }
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

function normalizeRangePrefix(value, preserveTrailingSpace = true) {
  const normalized = normalizeSpace(value);
  return normalized
    && preserveTrailingSpace
    && /\s$/u.test(value.normalize("NFKC"))
    ? `${normalized} `
    : normalized;
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
  if (!fromStart) return normalizeSpace(text);
  const actualPrefix = boundary.nodeType === Node.TEXT_NODE
    ? boundary.nodeValue.slice(0, boundaryOffset).normalize("NFKC")
    : "";
  const preserveTrailingSpace =
    boundary.nodeType === Node.TEXT_NODE
      ? boundaryOffset === 0 || /\s$/u.test(actualPrefix)
      : true;
  return normalizeRangePrefix(text, preserveTrailingSpace);
}

function clearSelection() {
  emit("selection", null);
}

function overlappingThreads(start, end) {
  return props.followUps.filter((thread) => (
    thread.anchor.start < end && thread.anchor.end > start
  ));
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
  const root = reportContent.value;
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
    emit("selection-error", "选区过长，请缩小范围（最多 8,000 个字符）。");
    clearSelection();
    return;
  }

  const before = rangePart(root, range.startContainer, range.startOffset, true);
  const after = rangePart(root, range.endContainer, range.endOffset, false);
  const start = Array.from(before).length;
  const end = start + Array.from(text).length;
  const overlaps = overlappingThreads(start, end);
  if (overlaps.length === 1) {
    selection.removeAllRanges();
    emit("selection", null);
    emit("restore-follow-up", overlaps[0].id);
    return;
  }
  if (overlaps.length > 1) {
    selection.removeAllRanges();
    emit("selection-error", "选区跨过多个追问，请缩小范围并只选择一个会话。");
    clearSelection();
    return;
  }

  const rect = typeof range.getBoundingClientRect === "function"
    ? range.getBoundingClientRect()
    : { right: 0, bottom: 0 };
  emit("selection", {
    anchor: {
      text,
      start,
      end,
      prefix: Array.from(normalizeSpace(before)).slice(-80).join(""),
      suffix: Array.from(after).slice(0, 80).join(""),
      report_digest: "",
    },
    position: {
      x: rect.right || Math.min(window.innerWidth - 96, 640),
      y: rect.top || Math.min(window.innerHeight - 96, 180),
    },
  });
}

function textNodes(root) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes = [];
  let node = walker.nextNode();
  while (node) {
    if (node.nodeValue) nodes.push(node);
    node = walker.nextNode();
  }
  return nodes;
}

function prefixLength(root, node, offset) {
  return Array.from(rangePart(root, node, offset, true)).length;
}

function boundaryAt(root, nodes, target) {
  if (!nodes.length) return null;
  if (target <= 0) return { node: nodes[0], offset: 0 };
  for (const node of nodes) {
    const end = prefixLength(root, node, node.nodeValue.length);
    if (target > end) continue;
    const chars = Array.from(node.nodeValue);
    let low = 0;
    let high = chars.length;
    while (low < high) {
      const middle = Math.floor((low + high) / 2);
      const offset = chars.slice(0, middle).join("").length;
      if (prefixLength(root, node, offset) >= target) high = middle;
      else low = middle + 1;
    }
    const offset = chars.slice(0, low).join("").length;
    return { node, offset };
  }
  const last = nodes.at(-1);
  return { node: last, offset: last.nodeValue.length };
}

function rangeForAnchor(root, nodes, anchor) {
  const start = boundaryAt(root, nodes, anchor.start);
  const end = boundaryAt(root, nodes, anchor.end);
  if (!start || !end) return null;
  const range = document.createRange();
  range.setStart(start.node, start.offset);
  range.setEnd(end.node, end.offset);
  return range;
}

function rebuildOverlays() {
  const root = reportBody.value;
  const content = reportContent.value;
  if (!root || !content || !props.followUps.length) {
    highlights.value = [];
    markers.value = [];
    return;
  }
  const base = root.getBoundingClientRect();
  const nodes = textNodes(content);
  const nextHighlights = [];
  const nextMarkers = [];
  props.followUps.forEach((thread, threadIndex) => {
    const range = rangeForAnchor(content, nodes, thread.anchor);
    if (!range) return;
    const hasRangeRects = typeof range.getClientRects === "function";
    const rawRects = hasRangeRects
      ? Array.from(range.getClientRects())
      : [];
    const rects = rawRects.filter((rect) => rect.width > 0 && rect.height > 0);
    const fallback = {
      left: 0,
      top: threadIndex * 28,
      width: 120,
      height: 16,
      right: 120,
      bottom: threadIndex * 28 + 16,
    };
    const positioned = (rects.length ? rects : [fallback]).map((rect) => ({
      left: `${rect.left - base.left}px`,
      top: `${rect.top - base.top}px`,
      width: `${rect.width}px`,
      height: `${rect.height}px`,
    }));
    positioned.forEach((style) => nextHighlights.push({
      threadId: thread.id,
      minimized: thread.is_minimized,
      style,
    }));
    if (thread.is_minimized) {
      const first = rects[0] || (hasRangeRects ? null : fallback);
      if (!first) return;
      const intersectsViewport =
        first.bottom > 0
        && first.top < window.innerHeight
        && first.right > 0
        && first.left < window.innerWidth;
      if (!intersectsViewport) return;
      const left = Math.max(
        2,
        Math.min(first.right + 3, window.innerWidth - 46),
      );
      const top = Math.max(
        2,
        Math.min(first.top - 2, window.innerHeight - 46),
      );
      nextMarkers.push({
        threadId: thread.id,
        anchorText: thread.anchor.text.slice(0, 40),
        style: {
          left: `${left}px`,
          top: `${top}px`,
        },
      });
    }
  });
  highlights.value = nextHighlights;
  markers.value = nextMarkers;
}

function scheduleOverlays() {
  nextTick(rebuildOverlays);
}

function scheduleSelectionCapture() {
  clearTimeout(selectionTimer);
  selectionTimer = setTimeout(captureSelection, 60);
}

function refreshHeadings() {
  const content = reportContent.value;
  if (!content) {
    emit("headings", []);
    return;
  }
  const items = Array.from(content.querySelectorAll("h2, h3, h4")).map((heading, index) => {
    const id = `report-heading-${index + 1}`;
    heading.id = id;
    heading.tabIndex = -1;
    return {
      id,
      level: Number(heading.tagName.slice(1)),
      text: heading.textContent?.trim() || `第 ${index + 1} 节`,
    };
  });
  emit("headings", items);
  updateActiveHeading();
}

function updateActiveHeading() {
  const content = reportContent.value;
  if (!content) return;
  const headings = Array.from(content.querySelectorAll("h2, h3, h4"));
  if (!headings.length) return;
  let active = headings[0];
  for (const heading of headings) {
    if (heading.getBoundingClientRect().top <= 150) active = heading;
    else break;
  }
  emit("heading-change", active.id);
}

function scrollToHeading(id) {
  const heading = document.getElementById(id);
  if (!reportContent.value?.contains(heading)) return;
  heading?.scrollIntoView({ behavior: "smooth", block: "start" });
  heading?.focus({ preventScroll: true });
}

function scrollToTop() {
  reportBody.value?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function focusCitation(referenceId, occurrenceIndex = 0) {
  const citations = Array.from(
    reportContent.value?.querySelectorAll(`.citation-id[data-ref="${referenceId}"]`) || [],
  );
  const target = citations[occurrenceIndex] || citations[0];
  if (!target) return false;
  target.scrollIntoView({ behavior: "smooth", block: "center" });
  target.classList.add("is-trace-focus");
  window.setTimeout(() => target.classList.remove("is-trace-focus"), 1600);
  target.focus();
  return true;
}

function focusReport() {
  reportBody.value?.focus();
}

function focusAnchor(anchor) {
  const root = reportContent.value;
  if (!root || !anchor) return false;
  const range = rangeForAnchor(root, textNodes(root), anchor);
  if (!range) return false;
  reportBody.value?.focus();
  const selection = window.getSelection();
  selection?.removeAllRanges();
  selection?.addRange(range);
  range.startContainer.parentElement?.scrollIntoView?.({
    behavior: "smooth",
    block: "center",
  });
  return true;
}

watch(
  [overlayState, html, () => props.expanded],
  rebuildOverlays,
  { deep: true, immediate: true, flush: "post" },
);
watch(
  [html, () => props.expanded],
  () => nextTick(refreshHeadings),
  { immediate: true, flush: "post" },
);
onMounted(() => {
  window.addEventListener("resize", scheduleOverlays);
  window.addEventListener("scroll", scheduleOverlays, true);
  window.addEventListener("scroll", updateActiveHeading, true);
  document.addEventListener("selectionchange", scheduleSelectionCapture);
  rebuildOverlays();
  refreshHeadings();
});
onUnmounted(() => {
  window.removeEventListener("resize", scheduleOverlays);
  window.removeEventListener("scroll", scheduleOverlays, true);
  window.removeEventListener("scroll", updateActiveHeading, true);
  document.removeEventListener("selectionchange", scheduleSelectionCapture);
  clearTimeout(selectionTimer);
});

defineExpose({ scrollToHeading, scrollToTop, focusCitation, focusReport, focusAnchor });
</script>

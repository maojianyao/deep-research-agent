<template>
  <div
    ref="reportBody"
    data-report-body
    class="relative"
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
        class="pointer-events-auto fixed z-30 grid h-[18px] w-[18px] place-items-center rounded-full border-2 border-white bg-emerald-600 text-[8px] font-bold text-white shadow-sm hover:bg-emerald-700"
        :style="marker.style"
        title="恢复追问"
        aria-label="恢复追问"
        @mousedown.prevent.stop
        @click.stop="$emit('restore-follow-up', marker.threadId)"
      >追</button>
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
});
const emit = defineEmits(["citation", "selection", "selection-error", "restore-follow-up"]);
const reportBody = ref(null);
const reportContent = ref(null);
const highlights = ref([]);
const markers = ref([]);

const html = computed(() => safeMarkdown(props.markdown));
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
    const rawRects = typeof range.getClientRects === "function"
      ? Array.from(range.getClientRects())
      : [];
    const rects = rawRects.filter((rect) => rect.width > 0 && rect.height > 0);
    const fallback = { left: 0, top: threadIndex * 28, width: 120, height: 16, right: 120 };
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
      const first = rects[0] || fallback;
      const left = Math.max(
        2,
        Math.min(first.right + 3, window.innerWidth - 20),
      );
      const top = Math.max(
        2,
        Math.min(first.top - 2, window.innerHeight - 20),
      );
      nextMarkers.push({
        threadId: thread.id,
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

watch(
  [overlayState, html],
  rebuildOverlays,
  { deep: true, immediate: true, flush: "post" },
);
onMounted(() => {
  window.addEventListener("resize", scheduleOverlays);
  window.addEventListener("scroll", scheduleOverlays, true);
  rebuildOverlays();
});
onUnmounted(() => {
  window.removeEventListener("resize", scheduleOverlays);
  window.removeEventListener("scroll", scheduleOverlays, true);
});
</script>

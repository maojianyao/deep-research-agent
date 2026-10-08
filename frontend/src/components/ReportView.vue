<template>
  <div class="markdown-content" @click="handleCitation">
    <div v-if="html" v-html="html"></div>
    <p v-else class="text-sm text-slate-500">{{ active ? "研究报告生成后会显示在这里。" : "当前研究没有生成报告。" }}</p>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { safeMarkdown } from "../lib/markdown";

const props = defineProps({ markdown: { type: String, default: "" }, active: Boolean });
const emit = defineEmits(["citation"]);

const html = computed(() => safeMarkdown(props.markdown));

function handleCitation(event) {
  const target = event.target.closest(".citation-id");
  if (target) emit("citation", target.dataset.ref);
}

</script>

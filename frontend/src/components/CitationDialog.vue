<template>
  <dialog ref="dialog" class="research-dialog fixed left-1/2 top-1/2 m-0 max-h-[85vh] w-[min(680px,calc(100vw-24px))] -translate-x-1/2 -translate-y-1/2 overflow-y-auto p-0 shadow-2xl">
    <div class="flex items-start justify-between border-b border-[var(--line)] p-6">
      <div><p class="dialog-kicker">引用核对</p><h2 class="dialog-title">这条结论从哪里来</h2></div>
      <button class="rounded p-1.5 text-xl text-[var(--muted)] hover:bg-[#eef3ef]" aria-label="关闭" @click="dialog?.close()">×</button>
    </div>
    <div class="max-h-[68vh] overflow-y-auto p-6">
      <p v-if="findingStatement" class="finding-text border-l-2 border-[var(--citation)] pl-4">{{ findingStatement }}</p>
      <article v-for="source in sources" :key="source.evidence_id" class="border-t border-[var(--line)] py-5 first:border-0 first:pt-0">
        <h3 class="reading-title text-[18px] text-[var(--ink-strong)]">{{ source.title }}</h3>
        <p class="mt-1 text-[11px] text-[var(--muted)]">{{ source.publisher || source.source_type }}<template v-if="source.published_at"> / {{ source.published_at }}</template></p>
        <a class="mt-2 block break-all text-[11px] text-[var(--citation)] underline underline-offset-2" :href="source.url" target="_blank" rel="noopener noreferrer">{{ source.url }} ↗</a>
        <p class="mt-3 text-[13px] leading-6 text-[var(--ink)]">{{ source.claim }}</p>
        <blockquote v-if="source.excerpt" class="reading-quote mt-3 border-l-2 border-[var(--moss)] pl-4 text-[13px] leading-7 text-[#566b67]">{{ source.excerpt }}</blockquote>
        <p v-if="source.locator" class="mt-2 text-[10px] text-[var(--muted)]">定位：{{ source.locator }}</p>
      </article>
      <p v-if="!sources.length && !loading" class="empty-note">没有找到这条引用的来源记录。</p>
      <p v-if="loading" class="empty-note">正在读取来源…</p>
    </div>
  </dialog>
</template>

<script setup>
import { ref } from "vue";
const dialog = ref(null);
defineProps({ sources: { type: Array, default: () => [] }, findingStatement: { type: String, default: "" }, loading: Boolean });
defineExpose({ open: () => dialog.value?.showModal(), close: () => dialog.value?.close() });
</script>

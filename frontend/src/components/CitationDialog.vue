<template>
  <dialog ref="dialog" class="fixed left-1/2 top-1/2 m-0 max-h-[85vh] w-[min(620px,calc(100vw-24px))] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-md border border-slate-200 p-0 shadow-2xl backdrop:bg-slate-900/50">
    <div class="flex items-start justify-between border-b border-slate-100 p-5">
      <div><p class="text-[10px] font-semibold tracking-widest text-teal-700">CITATION SOURCES</p><h2 class="mt-1 text-base font-semibold">引用来源</h2></div>
      <button class="rounded p-1 text-xl text-slate-500 hover:bg-slate-100" aria-label="关闭" @click="dialog?.close()">×</button>
    </div>
    <div class="max-h-[65vh] overflow-y-auto p-5">
      <p v-if="findingStatement" class="mb-4 text-sm leading-6 text-slate-600">{{ findingStatement }}</p>
      <article v-for="source in sources" :key="source.evidence_id" class="border-t border-slate-100 py-4 first:border-0 first:pt-0">
        <h3 class="text-sm font-semibold text-slate-800">{{ source.title }}</h3>
        <p class="mt-1 text-xs text-slate-500">{{ source.publisher || source.source_type }}<template v-if="source.published_at"> · {{ source.published_at }}</template></p>
        <a class="mt-2 block break-all text-xs text-teal-700 underline underline-offset-2" :href="source.url" target="_blank" rel="noopener noreferrer">{{ source.url }} ↗</a>
        <p class="mt-2 text-xs leading-5 text-slate-600">{{ source.claim }}</p>
        <blockquote v-if="source.excerpt" class="mt-2 border-l-2 border-teal-200 pl-3 text-xs leading-5 text-slate-500">{{ source.excerpt }}</blockquote>
        <p v-if="source.locator" class="mt-2 text-[10px] text-slate-400">定位：{{ source.locator }}</p>
      </article>
      <p v-if="!sources.length && !loading" class="text-sm text-slate-500">没有找到该引用的来源。</p>
      <p v-if="loading" class="text-sm text-slate-500">正在读取来源…</p>
    </div>
  </dialog>
</template>

<script setup>
import { ref } from "vue";
const dialog = ref(null);
defineProps({ sources: { type: Array, default: () => [] }, findingStatement: { type: String, default: "" }, loading: Boolean });
defineExpose({ open: () => dialog.value?.showModal(), close: () => dialog.value?.close() });
</script>

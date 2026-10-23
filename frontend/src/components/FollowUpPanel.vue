<template>
  <aside
    data-follow-up-panel
    class="fixed z-40 overflow-hidden border border-slate-200 bg-white shadow-2xl"
    :class="narrow
      ? 'inset-x-0 bottom-0 h-[min(78vh,620px)] w-full rounded-t-xl border-b-0'
      : 'bottom-auto right-4 top-20 h-[min(620px,calc(100vh-6rem))] w-[360px] rounded-md'"
    :data-layout="narrow ? 'sheet' : 'floating'"
    aria-label="追问会话"
    role="dialog"
    aria-modal="false"
  >
    <header class="flex items-center justify-between border-b border-slate-100 px-4 py-3">
      <div>
        <p class="text-[9px] font-bold tracking-[.14em] text-teal-800">FOLLOW-UP</p>
        <h2 class="mt-0.5 text-sm font-semibold">追问</h2>
      </div>
      <div class="flex items-center gap-1">
        <button
          v-if="canDelete"
          type="button"
          data-delete-follow-up
          class="rounded px-2 py-1 text-[10px] text-rose-700 hover:bg-rose-50"
          @click="$emit('delete')"
        >删除</button>
        <button type="button" class="rounded px-2 py-1 text-lg text-slate-400 hover:bg-slate-100" aria-label="最小化追问" title="最小化追问" @click="$emit('close')">—</button>
      </div>
    </header>

    <div class="flex h-[calc(100%-57px)] min-h-0 flex-col">
      <blockquote class="border-b border-slate-100 bg-amber-50/70 px-4 py-3 text-[11px] leading-5 text-slate-700">
        <p class="mb-1 text-[9px] font-semibold text-amber-800">已选报告片段</p>
        <p class="max-h-24 overflow-y-auto break-words">{{ passage }}</p>
      </blockquote>

      <div class="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-4" aria-live="polite">
        <article v-for="message in messages" :key="message.id" class="text-[11px] leading-6">
          <p class="mb-1 text-[9px] font-semibold" :class="message.role === 'user' ? 'text-slate-500' : 'text-teal-800'">
            {{ message.role === "user" ? "你" : "助手" }}
          </p>
          <p v-if="message.role === 'user'" class="whitespace-pre-wrap break-words rounded bg-slate-50 px-3 py-2 text-slate-700">{{ message.content }}</p>
          <div v-else class="markdown-content break-words text-slate-700" v-html="safeMarkdown(message.content)"></div>
          <p
            v-if="message.role === 'assistant' && message.status !== 'completed'"
            data-message-status
            class="mt-1 text-[9px]"
            :class="message.status === 'generating' ? 'text-teal-700' : 'text-rose-700'"
          >
            {{ messageStatus(message.status) }}
          </p>
          <p v-if="message.error_message" class="mt-1 text-[9px] text-rose-700">{{ message.error_message }}</p>
          <button
            v-if="message.role === 'assistant' && ['failed', 'interrupted'].includes(message.status)"
            type="button"
            data-retry-answer
            class="mt-1 rounded border border-rose-200 bg-white px-2 py-1 text-[9px] font-semibold text-rose-700 hover:bg-rose-50 disabled:opacity-40"
            :disabled="busy"
            @click="$emit('retry', message.id)"
          >重试回答</button>
        </article>
        <p v-if="!messages.length && !busy" class="text-[11px] leading-5 text-slate-400">输入一个针对所选片段的问题。</p>
        <p v-if="busy" class="text-[11px] text-teal-800" role="status">正在生成回答…</p>
        <p v-if="error" class="rounded bg-rose-50 px-3 py-2 text-[11px] text-rose-700" role="alert">{{ error }}</p>
      </div>

      <form class="border-t border-slate-100 p-3" @submit.prevent="submit">
        <label for="follow-up-question" class="sr-only">你的问题</label>
        <textarea
          id="follow-up-question"
          ref="input"
          v-model="question"
          data-follow-up-input
          maxlength="2000"
          rows="3"
          class="w-full resize-none rounded border border-slate-200 p-2.5 text-xs leading-5 outline-none focus:border-teal-700"
          placeholder="就这段内容继续提问…"
          @keydown.enter.exact.prevent="submit"
        ></textarea>
        <div class="mt-2 flex items-center justify-between">
          <span class="text-[9px]" :class="tooLong ? 'font-semibold text-rose-700' : 'text-slate-400'">{{ questionLength }} / 2000</span>
          <button
            type="submit"
            class="rounded bg-teal-800 px-3 py-1.5 text-[10px] font-semibold text-white disabled:opacity-40"
            :disabled="busy || !question.trim() || tooLong"
          >发送</button>
        </div>
        <p v-if="tooLong" data-input-too-long class="mt-1 text-[9px] text-rose-700" role="alert">
          问题超过 2,000 个字符，无法发送，请缩短。
        </p>
      </form>
    </div>
  </aside>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { safeMarkdown } from "../lib/markdown";

const props = defineProps({
  passage: { type: String, default: "" },
  messages: { type: Array, default: () => [] },
  busy: Boolean,
  error: { type: String, default: "" },
  canDelete: Boolean,
  narrow: Boolean,
});
const emit = defineEmits(["submit", "retry", "delete", "close"]);
const input = ref(null);
const question = ref("");
const questionLength = computed(() => Array.from(question.value).length);
const tooLong = computed(() => questionLength.value > 2000);

function focusInput() {
  nextTick(() => input.value?.focus());
}

function submit() {
  const value = question.value.trim();
  if (!value || props.busy || tooLong.value) return;
  emit("submit", value);
}

function messageStatus(status) {
  return {
    generating: "正在生成，可离开页面稍后回来",
    failed: "生成失败，已保留收到的内容",
    interrupted: "生成被中断，已保留收到的内容",
  }[status] || status;
}

watch(() => props.busy, (busy) => {
  if (!busy) {
    question.value = "";
    focusInput();
  }
});

onMounted(focusInput);
</script>

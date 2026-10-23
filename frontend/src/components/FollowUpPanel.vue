<template>
  <aside
    data-follow-up-panel
    class="follow-up-panel fixed z-40 overflow-hidden border shadow-2xl"
    :data-layout="narrow ? 'sheet' : 'floating'"
    aria-label="追问会话"
    role="dialog"
    aria-modal="false"
  >
    <header class="flex h-14 items-center justify-between border-b border-[var(--line)] px-4">
      <div>
        <p class="text-[10px] text-[var(--moss)]">选中段落的追问</p>
        <h2 class="reading-title mt-0.5 text-[16px] text-[var(--ink-strong)]">继续研究这一段</h2>
      </div>
      <div class="flex items-center gap-1">
        <button
          v-if="canDelete"
          type="button"
          data-delete-follow-up
          data-touch-target="44"
          class="grid h-11 w-11 place-items-center rounded-full text-rose-600 hover:bg-rose-50"
          aria-label="删除追问"
          title="删除追问"
          @click="$emit('delete')"
        >
          <svg class="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
            <path d="M3.5 4.5h9M6 4.5V3h4v1.5M5 6v6.5h6V6M7 7.5v3.5M9 7.5v3.5" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </button>
        <button type="button" data-touch-target="44" class="grid h-11 w-11 place-items-center rounded-full text-slate-400 hover:bg-slate-100" aria-label="最小化追问" title="最小化追问" @click="$emit('close')">
          <svg class="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
            <path d="M4 8h8" stroke-linecap="round" />
          </svg>
        </button>
      </div>
    </header>

    <div class="flex h-[calc(100%-56px)] min-h-0 flex-col">
      <p data-follow-up-live class="sr-only" aria-live="polite" aria-atomic="true">{{ liveStatus }}</p>
      <div data-follow-up-messages class="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-4">
        <blockquote data-selected-passage class="reading-quote mr-8 rounded-xl border-l-2 border-[var(--citation)] bg-[#eef3ee] px-3 py-2.5 text-xs leading-6 text-[var(--ink)]">
          <p :class="passageExpanded ? '' : 'line-clamp-3'" class="whitespace-pre-wrap break-words">{{ passage }}</p>
          <button
            type="button"
            data-passage-toggle
            data-touch-target="44"
            class="mt-1 min-h-11 text-[10px] font-medium text-amber-800 hover:underline"
            @click="passageExpanded = !passageExpanded"
          >{{ passageExpanded ? "收起引用" : "展开引用" }}</button>
        </blockquote>

        <article
          v-for="message in messages"
          :key="message.id"
          :data-message-role="message.role"
          :class="message.role === 'user'
            ? 'ml-auto max-w-[84%]'
            : 'mr-7 max-w-[90%]'"
          class="text-xs leading-5"
        >
          <div
            v-if="message.role === 'user'"
            class="whitespace-pre-wrap break-words rounded-xl bg-[#e9f0eb] px-3 py-2.5 text-[var(--ink)]"
          >{{ message.content }}</div>
          <div v-else class="markdown-content break-words rounded-xl border border-[var(--line)] bg-[#f7f9f5] px-3 py-2.5 text-[var(--ink)]" v-html="safeMarkdown(message.content)"></div>
          <p
            v-if="message.role === 'assistant' && message.status !== 'completed'"
            data-message-status
            class="mt-1 text-[10px]"
            :class="message.status === 'generating' ? 'text-[var(--moss)]' : 'text-[var(--danger)]'"
          >
            {{ messageStatus(message.status) }}
          </p>
          <p v-if="message.error_message" class="mt-1 text-[10px] text-[var(--danger)]">{{ message.error_message }}</p>
          <button
            v-if="message.role === 'assistant' && ['failed', 'interrupted'].includes(message.status)"
            type="button"
            data-retry-answer
            data-touch-target="44"
            class="mt-1 min-h-11 rounded-full border border-[#ddc3c3] bg-white px-3 py-1 text-[10px] font-semibold text-[var(--danger)] hover:bg-[#f7eceb] disabled:opacity-40"
            :disabled="busy"
            @click="$emit('retry', message.id)"
          >重试回答</button>
        </article>

        <p v-if="busy && !messages.some((item) => item.status === 'generating')" class="text-[11px] text-[var(--moss)]" role="status">正在生成回答…</p>
        <p v-if="error" class="rounded-xl bg-[#f7eceb] px-3 py-2 text-[11px] text-[var(--danger)]" role="alert">{{ error }}</p>
      </div>

      <form class="border-t border-[var(--line)] p-3" @submit.prevent="submit">
        <label for="follow-up-question" class="sr-only">追问问题</label>
        <textarea
          id="follow-up-question"
          ref="input"
          v-model="question"
          data-follow-up-input
          maxlength="2000"
          rows="2"
          class="w-full resize-none rounded-xl border border-[var(--line-strong)] p-2.5 text-xs leading-5 outline-none focus:border-[var(--moss)]"
          placeholder="继续提问..."
          @keydown.enter.exact.prevent="submit"
        ></textarea>
        <div class="mt-1.5 flex items-center justify-between">
          <span class="text-[10px]" :class="tooLong ? 'font-semibold text-[var(--danger)]' : 'text-[var(--muted)]'">{{ questionLength }} / 2000</span>
          <button
            type="submit"
            data-touch-target="44"
            class="h-11 rounded-full bg-[var(--petrol)] px-4 text-[11px] font-semibold text-white disabled:opacity-40"
            :disabled="busy || !question.trim() || tooLong"
          >发送</button>
        </div>
        <p v-if="tooLong" data-input-too-long class="mt-1 text-[10px] text-[var(--danger)]" role="alert">
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
const passageExpanded = ref(false);
const questionLength = computed(() => Array.from(question.value).length);
const tooLong = computed(() => questionLength.value > 2000);
const liveStatus = computed(() => {
  if (props.busy) return "正在生成回答";
  const latest = [...props.messages].reverse().find((message) => message.role === "assistant");
  if (!latest) return "";
  if (latest.status === "completed") return "回答已完成";
  if (latest.status === "failed") return "回答生成失败，可以重试";
  if (latest.status === "interrupted") return "回答生成被中断，可以重试";
  return "";
});

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
watch(() => props.passage, () => { passageExpanded.value = false; });

onMounted(focusInput);
</script>

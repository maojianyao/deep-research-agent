<template>
  <dialog
    ref="dialog"
    class="research-dialog"
    aria-labelledby="create-research-title"
    @cancel.prevent="close"
  >
    <form class="research-dialog-form" novalidate @submit.prevent="submit">
      <header class="dialog-heading">
        <div>
          <p class="dialog-kicker">新建研究</p>
          <h2 id="create-research-title" class="dialog-title">先写下你想弄清的问题</h2>
          <p class="section-note">补充研究深度与报告语言，系统会保留计划、证据和审稿记录。</p>
        </div>
        <button type="button" class="dialog-icon-action" aria-label="关闭" @click="close">×</button>
      </header>

      <div class="dialog-body">
        <label for="topic" class="dialog-field-label">研究主题或问题</label>
        <textarea
          id="topic"
          v-model="topic"
          maxlength="2000"
          required
          class="dialog-input dialog-topic"
          aria-describedby="topic-help"
          placeholder="例如：评估某项政策对中小企业创新投入的影响，重点关注实施机制、效果证据与地区差异。"
        ></textarea>
        <div id="topic-help" class="dialog-help flex justify-between gap-4">
          <span>描述你想得到什么结论，以及必须覆盖的范围。</span>
          <span class="shrink-0">{{ topic.length }} / 2000</span>
        </div>

        <fieldset class="research-depth">
          <legend class="dialog-field-label">研究深度</legend>
          <div class="depth-options">
            <label
              v-for="preset in presets"
              :key="preset.id"
              :data-depth-preset="preset.id"
              class="depth-option"
              :class="{ 'is-selected': depth === preset.id }"
            >
              <input v-model="depth" type="radio" name="research-depth" :value="preset.id" />
              <strong>{{ preset.label }}</strong>
              <span>{{ preset.description }}</span>
              <small>{{ preset.iterations }} 轮基础研究</small>
            </label>
          </div>
        </fieldset>

        <label for="report-language" class="dialog-field-label">报告语言</label>
        <select id="report-language" v-model="reportLanguage" class="dialog-input">
          <option value="">跟随研究请求（推荐）</option>
          <option v-for="language in languages" :key="language.tag" :value="language.tag">
            {{ language.label }}{{ language.verified ? " · 已验证" : "" }}
          </option>
        </select>
        <p
          data-report-language-preview
          class="language-preview"
          :class="{ 'is-error': previewError }"
          aria-live="polite"
        >
          <template v-if="previewError">{{ previewError }}</template>
          <template v-else-if="previewLoading">正在确认报告语言…</template>
          <template v-else-if="languagePreview">
            最终采用 {{ languagePreview.name }}（{{ languagePreview.tag }}），
            {{ languageSourceLabel }}。
          </template>
          <template v-else>输入研究问题后，会在此显示最终采用的报告语言。</template>
        </p>

        <details class="advanced-research">
          <summary>高级设置</summary>
          <label class="advanced-rounds">
            <input v-model="useCustomRounds" type="checkbox" />
            手动指定基础研究轮次
          </label>
          <select v-if="useCustomRounds" v-model.number="customIterations" class="dialog-input">
            <option v-for="count in 5" :key="count" :value="count">{{ count }} 轮</option>
          </select>
        </details>

        <p v-if="error" data-form-error class="form-error" role="alert">{{ error }}</p>
      </div>

      <footer data-dialog-actions class="dialog-actions">
        <button type="button" class="dialog-cancel" data-dialog-cancel @click="close">取消</button>
        <button type="submit" class="dialog-submit" :disabled="creating">
          {{ creating ? "正在发起…" : "开始研究" }}
        </button>
      </footer>
    </form>
  </dialog>
</template>

<script setup>
import { computed, onUnmounted, ref, watch } from "vue";
import { api } from "../lib/api";

defineProps({
  creating: Boolean,
  error: { type: String, default: "" },
});
const emit = defineEmits(["create", "close"]);

const presets = [
  { id: "quick", label: "快速", description: "先得到方向性结论", iterations: 1 },
  { id: "standard", label: "标准", description: "兼顾证据覆盖与等待时间", iterations: 3 },
  { id: "deep", label: "深度", description: "适合高风险或多方争议问题", iterations: 5 },
];
const languages = [
  { tag: "zh-CN", label: "简体中文", verified: true },
  { tag: "en", label: "English", verified: true },
  { tag: "ja", label: "日本語", verified: true },
  { tag: "es", label: "Español", verified: true },
  { tag: "ar", label: "العربية", verified: true },
  { tag: "fr", label: "Français", verified: false },
  { tag: "de", label: "Deutsch", verified: false },
  { tag: "ko", label: "한국어", verified: false },
  { tag: "pt", label: "Português", verified: false },
  { tag: "hi", label: "हिन्दी", verified: false },
];

const dialog = ref(null);
const topic = ref("");
const depth = ref("standard");
const reportLanguage = ref("");
const useCustomRounds = ref(false);
const customIterations = ref(3);
const previewLoading = ref(false);
const previewError = ref("");
const languagePreview = ref(null);
let previewTimer;
let previewRequest = 0;
let previewAbort;

const iterations = computed(() => {
  if (useCustomRounds.value) return customIterations.value;
  return presets.find((preset) => preset.id === depth.value)?.iterations || 3;
});
const languageSourceLabel = computed(() => ({
  detected: "跟随研究请求",
  explicit: "由你手动选择",
  fallback: "研究请求语言不明确，使用界面语言",
  legacy: "沿用历史设置",
}[languagePreview.value?.source] || "由服务确认"));

function open() {
  dialog.value?.showModal();
}

function close() {
  dialog.value?.close();
  emit("close");
}

function reset() {
  topic.value = "";
  depth.value = "standard";
  reportLanguage.value = "";
  useCustomRounds.value = false;
  customIterations.value = 3;
  languagePreview.value = null;
  previewError.value = "";
}

async function refreshLanguagePreview() {
  const request = ++previewRequest;
  previewAbort?.abort();
  previewAbort = new AbortController();
  if (!topic.value.trim()) {
    languagePreview.value = null;
    previewLoading.value = false;
    previewError.value = "";
    return;
  }
  previewLoading.value = true;
  previewError.value = "";
  try {
    const preview = await api("/research-runs/language-preview", {
      method: "POST",
      signal: previewAbort.signal,
      body: JSON.stringify({
        user_request: topic.value.trim(),
        report_language: reportLanguage.value || null,
      }),
    });
    if (request === previewRequest) languagePreview.value = preview;
  } catch (error) {
    if (request !== previewRequest || error.name === "AbortError") return;
    languagePreview.value = null;
    previewError.value = "暂时无法预览报告语言，开始研究时仍会自动判断。";
  } finally {
    if (request === previewRequest) previewLoading.value = false;
  }
}

function scheduleLanguagePreview() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(refreshLanguagePreview, 250);
}

function submit() {
  if (!topic.value.trim()) {
    previewError.value = "请先填写研究主题或问题。";
    return;
  }
  emit("create", {
    topic: topic.value.trim(),
    iterations: iterations.value,
    reportLanguage: reportLanguage.value,
  });
}

watch([topic, reportLanguage], scheduleLanguagePreview);
onUnmounted(() => {
  clearTimeout(previewTimer);
  previewAbort?.abort();
});

defineExpose({ open, close, reset });
</script>

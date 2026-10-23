<template>
  <section class="evidence-library" aria-label="审查证据库">
    <header class="evidence-library-head">
      <div>
        <p class="dialog-kicker">审查通过的证据</p>
        <h2>证据库</h2>
        <p>查看全部来源、原文摘录与审稿用途，不局限于右栏摘要。</p>
      </div>
      <strong data-evidence-total>{{ result.total }} 条</strong>
    </header>

    <div class="evidence-library-toolbar">
      <label class="evidence-search">
        <span>搜索证据</span>
        <input v-model="search" type="search" placeholder="结论、来源标题或原文摘录" />
      </label>
      <label>
        <span>来源类型</span>
        <select v-model="sourceType" aria-label="来源类型">
          <option value="">全部来源</option>
          <option v-for="item in result.facets.source_types" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <label>
        <span>来源语言</span>
        <select v-model="language" aria-label="来源语言">
          <option value="">全部语言</option>
          <option v-for="item in result.facets.languages" :key="item" :value="item">{{ languageLabel(item) }}</option>
        </select>
      </label>
      <label>
        <span>审稿结论</span>
        <select v-model="verdict" aria-label="审稿结论">
          <option value="">全部结论</option>
          <option v-for="item in result.facets.verdicts" :key="item" :value="item">{{ verdictLabel(item) }}</option>
        </select>
      </label>
      <label>
        <span>最低置信度</span>
        <select v-model="minConfidence" aria-label="最低置信度">
          <option value="">不限</option>
          <option value="0.7">70% 以上</option>
          <option value="0.9">90% 以上</option>
        </select>
      </label>
    </div>

    <div class="evidence-library-grid">
      <div class="evidence-results">
        <p v-if="loading" class="empty-note" role="status">正在读取审查证据…</p>
        <p v-else-if="error" class="form-error" role="alert">{{ error }}</p>
        <template v-else-if="result.items.length">
          <article v-for="item in result.items" :key="item.id" data-evidence-card class="evidence-library-card">
            <button type="button" @click="selected = item">
              <span class="evidence-verdict" :class="{ 'is-partial': item.verdict !== 'supported' }">
                {{ verdictLabel(item.verdict) }}
              </span>
              <strong>{{ item.claim }}</strong>
              <span>{{ item.source.title }}</span>
              <small>{{ item.source.source_type }} · {{ languageLabel(item.source.language) }} · 置信度 {{ Math.round(item.confidence * 100) }}%</small>
            </button>
          </article>
        </template>
        <div v-else class="evidence-empty">
          <p>没有符合当前条件的证据。</p>
          <button
            v-if="hasFilters"
            data-clear-evidence-filters
            type="button"
            class="secondary-action"
            @click="clearFilters"
          >清除筛选</button>
        </div>
        <footer v-if="pageCount > 1" class="evidence-pagination">
          <span>第 {{ result.page }} / {{ pageCount }} 页</span>
          <div>
            <button type="button" class="line-action" :disabled="page <= 1" @click="page -= 1">上一页</button>
            <button type="button" class="line-action" :disabled="page >= pageCount" @click="page += 1">下一页</button>
          </div>
        </footer>
      </div>

      <aside v-if="selected" data-evidence-detail class="evidence-detail" aria-label="证据详情">
        <div class="evidence-detail-head">
          <span class="evidence-verdict" :class="{ 'is-partial': selected.verdict !== 'supported' }">
            {{ verdictLabel(selected.verdict) }}
          </span>
          <button type="button" aria-label="关闭证据详情" @click="selected = null">×</button>
        </div>
        <h3>{{ selected.claim }}</h3>
        <p class="evidence-detail-label">原文摘录</p>
        <blockquote>{{ selected.excerpt }}</blockquote>
        <div v-if="selectedOccurrences.length" class="evidence-return-links">
          <p class="evidence-detail-label">报告引用位置</p>
          <button
            v-for="occurrence in selectedOccurrences"
            :key="occurrence.index"
            data-return-to-report
            type="button"
            @click="emit('return-to-report', {
              evidenceId: selected.id,
              occurrenceIndex: occurrence.index,
            })"
          >回到引用 {{ occurrence.label }}</button>
        </div>
        <dl>
          <div><dt>来源</dt><dd>{{ selected.source.title }}</dd></div>
          <div><dt>发布者</dt><dd>{{ selected.source.publisher || selected.source.source_type }}</dd></div>
          <div><dt>语言</dt><dd>{{ languageLabel(selected.source.language) }}</dd></div>
          <div><dt>定位</dt><dd>{{ selected.locator || "未提供" }}</dd></div>
          <div><dt>置信度</dt><dd>{{ Math.round(selected.confidence * 100) }}%</dd></div>
        </dl>
        <a :href="selected.source.url" target="_blank" rel="noopener noreferrer">打开原始来源 ↗</a>
      </aside>
    </div>
  </section>
</template>

<script setup>
import { computed, onUnmounted, reactive, ref, watch } from "vue";
import { api } from "../lib/api";

const props = defineProps({
  runId: { type: String, required: true },
  focusEvidenceId: { type: String, default: "" },
  citationOccurrences: { type: Object, default: () => ({}) },
});
const emit = defineEmits(["select-evidence", "return-to-report"]);
const result = reactive({
  items: [],
  total: 0,
  page: 1,
  page_size: 20,
  facets: { source_types: [], languages: [], verdicts: [] },
});
const search = ref("");
const sourceType = ref("");
const language = ref("");
const verdict = ref("");
const minConfidence = ref("");
const page = ref(1);
const loading = ref(false);
const error = ref("");
const selected = ref(null);
let searchTimer;
let requestSequence = 0;

const pageCount = computed(() => Math.max(1, Math.ceil(result.total / result.page_size)));
const hasFilters = computed(() => Boolean(
  search.value || sourceType.value || language.value || verdict.value || minConfidence.value,
));
const selectedOccurrences = computed(() => (
  props.citationOccurrences[selected.value?.id] || []
));

const languageNames = {
  en: "English",
  ja: "日本語",
  "zh-CN": "简体中文",
  "zh-TW": "繁體中文",
  es: "Español",
  ar: "العربية",
  fr: "Français",
  de: "Deutsch",
  ko: "한국어",
  unknown: "未知",
};
const languageLabel = (value) => languageNames[value] || value || "未知";
const verdictLabel = (value) => ({
  supported: "已支持",
  partially_supported: "部分支持",
  unsupported: "未支持",
}[value] || value);

async function load() {
  const sequence = ++requestSequence;
  loading.value = true;
  error.value = "";
  const params = new URLSearchParams({
    page: String(page.value),
    page_size: "20",
  });
  if (search.value.trim()) params.set("search", search.value.trim());
  if (sourceType.value) params.set("source_type", sourceType.value);
  if (language.value) params.set("language", language.value);
  if (verdict.value) params.set("verdict", verdict.value);
  if (minConfidence.value) params.set("min_confidence", minConfidence.value);
  try {
    const data = await api(`/research-runs/${encodeURIComponent(props.runId)}/evidence?${params}`);
    if (sequence !== requestSequence) return;
    Object.assign(result, data);
    if (props.focusEvidenceId) {
      const focused = result.items.find((item) => item.id === props.focusEvidenceId);
      if (focused) selected.value = focused;
    }
  } catch (requestError) {
    if (sequence === requestSequence) error.value = requestError.message;
  } finally {
    if (sequence === requestSequence) loading.value = false;
  }
}

function clearFilters() {
  search.value = "";
  sourceType.value = "";
  language.value = "";
  verdict.value = "";
  minConfidence.value = "";
  page.value = 1;
}

watch(() => props.runId, () => {
  selected.value = null;
  page.value = 1;
  load();
}, { immediate: true });
watch([sourceType, language, verdict, minConfidence], () => {
  page.value = 1;
  load();
});
watch(search, () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    page.value = 1;
    load();
  }, 250);
});
watch(page, load);
watch(() => props.focusEvidenceId, async (id) => {
  if (!id) return;
  const current = result.items.find((item) => item.id === id);
  if (current) {
    selected.value = current;
    return;
  }
  page.value = 1;
  await load();
});
watch(selected, (item) => {
  if (item) emit("select-evidence", item.id);
});
onUnmounted(() => clearTimeout(searchTimer));
</script>

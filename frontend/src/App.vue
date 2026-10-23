<template>
  <div class="app-shell">
    <aside class="research-spine fixed inset-y-0 left-0 z-20 hidden flex-col md:flex">
      <a class="spine-brand flex no-underline" href="#">
        <span class="spine-mark"><i></i><i></i><i></i></span>
        <span><span class="spine-name">知序</span><span class="spine-subtitle block">深度研究工作台</span></span>
      </a>
      <button class="spine-create" @click="openCreateDialog">＋ 新建研究</button>
      <p class="spine-label">工作空间</p>
      <button class="spine-nav is-active flex h-10 items-center gap-2 px-3 text-left text-xs"><span aria-hidden="true">▤</span>研究任务<span class="ml-auto text-[11px] opacity-70">{{ store.total }}</span></button>
      <a class="spine-nav mt-1 flex h-10 items-center gap-2 px-3 text-xs no-underline" href="#workflow"><span aria-hidden="true">⌘</span>研究流程</a>
      <div class="spine-foot mt-auto flex items-center gap-2 border-t px-1 pt-4 text-[10px]">
        <span class="h-2 w-2 rounded-full" :class="store.connection === 'offline' ? 'bg-rose-500' : store.connection === 'stream' ? 'animate-pulse bg-teal-600' : 'bg-emerald-600'"></span>
        {{ connectionLabel }}
        <button class="ml-auto rounded p-1 text-base" title="刷新研究列表" @click="store.loadRuns()">↻</button>
      </div>
    </aside>

    <div class="app-main">
      <header class="workspace-header flex items-center justify-between border-b">
        <div class="mobile-brand">
          <span class="spine-mark"><i></i><i></i><i></i></span>
          <strong>知序</strong>
        </div>
        <div class="workspace-breadcrumb hidden items-center gap-2 sm:flex"><span>工作空间</span><span>/</span><strong>{{ pageTitle }}</strong></div>
        <div class="flex items-center gap-3">
          <span class="hidden text-[11px] text-[#7a8a86] sm:inline">{{ today }}</span>
          <button class="mobile-create md:hidden" @click="openCreateDialog">新建研究</button>
          <span class="header-avatar" aria-label="研究工作台">研</span>
        </div>
      </header>

      <main class="workspace-main">
        <template v-if="!store.runId">
          <section class="home-brief">
            <div>
              <h1 class="home-title">从一个问题，追到一条证据链。</h1>
              <p class="home-deck">发起研究、查看进度，或回到已完成的研究报告。每一条结论都保留来源与审稿记录。</p>
            </div>
            <button class="primary-action shrink-0" @click="openCreateDialog"><span aria-hidden="true">＋</span>新建研究</button>
          </section>

          <section class="workspace-ledger" aria-label="研究任务总览">
            <div class="ledger-metric"><span class="metric-label">全部研究</span><strong class="metric-value">{{ store.total }}</strong><span class="metric-note">工作区中的研究档案</span></div>
            <div class="ledger-metric"><span class="metric-label">正在推进</span><strong class="metric-value">{{ activeCount }}</strong><span class="metric-note is-warm">当前页持续更新</span></div>
            <div class="ledger-metric"><span class="metric-label">已形成报告</span><strong class="metric-value">{{ completedCount }}</strong><span class="metric-note is-good">当前页可阅读</span></div>
            <div class="ledger-metric"><span class="metric-label">等待判断</span><strong class="metric-value">{{ reviewCount }}</strong><span class="metric-note is-alert">当前页需人工复核</span></div>
          </section>

          <WorkflowDiagram id="workflow" />
          <ResearchList @open="openRun" @finish="finishRun" @continue="continueRun" @delete="deleteRun" />
        </template>

        <section v-else class="run-dossier">
          <button class="w-fit text-xs text-[var(--moss)] hover:underline" @click="backToList">← 返回研究任务</button>
          <div v-if="!store.run" class="border-t border-[var(--line)] py-16 text-center text-sm text-[var(--muted)]">{{ store.error || "正在读取研究详情…" }}</div>
          <template v-else>
            <div class="dossier-header">
              <div class="min-w-0">
                <p class="run-kicker">研究档案 <span>{{ store.run.id }}</span></p>
                <h1 class="run-title">{{ store.run.user_request }}</h1>
                <div class="run-meta">
                  <span class="status-pill" :class="statusClass(store.run.status)">{{ statusLabel(store.run.status) }}</span>
                  <span data-report-language class="run-meta-language" :title="store.run.report_language_source">{{ store.run.report_language_name }} / {{ store.run.report_language }}</span>
                  <span>{{ store.run.report_language_quality === 'verified' ? '已验证语言' : '尽力支持' }}</span>
                  <span>第 {{ store.run.iteration }} / {{ store.run.max_iterations }} 轮</span>
                  <span>更新于 {{ formatDate(store.run.updated_at) }}</span>
                  <span class="text-[var(--moss)]">{{ connectionLabel }}</span>
                </div>
              </div>
              <div class="run-actions">
                <button v-if="store.isActive" class="secondary-action is-warning" @click="finishRun(store.run)">结束任务</button>
                <button v-if="store.run.can_resume || ['paused','failed'].includes(store.run.status)" class="secondary-action" @click="continueRun(store.run)">继续任务</button>
                <a v-if="store.run.report && store.run.status === 'completed'" class="primary-download" :href="`/api/research-runs/${store.run.id}/report.md`">下载 Markdown</a>
              </div>
            </div>

            <div v-if="runError" class="error-note" role="alert">
              <p class="font-semibold">研究任务未能完成</p>
              <p class="mt-1 break-words">{{ runError }}</p>
            </div>

            <div class="dossier-layout">
              <div class="folio-stack">
                <details data-report-section :open="reportOpen" class="folio-section" @toggle="handleReportToggle">
                  <summary class="folio-summary"><h2>研究报告</h2><span class="folio-summary-meta">引用编号可查看来源 <span class="fold-chevron" aria-hidden="true">⌄</span></span></summary>
                  <div class="folio-content"><div class="report-sheet"><ReportView :markdown="store.run.report?.markdown || ''" :active="store.isActive" :eligible="store.run.status === 'completed' && Boolean(store.run.report)" :follow-ups="store.followUps" :language="store.run.report?.language || store.run.report_language" :direction="store.run.report?.direction || store.run.report_direction" :expanded="reportOpen" @citation="showCitation" @selection="openFollowUpSelection" @selection-error="notify($event, true)" @restore-follow-up="restoreFollowUp" /></div></div>
                </details>

                <details class="folio-section">
                  <summary class="folio-summary"><h2>研究计划</h2><span class="folio-summary-meta">{{ completedTasks }} / {{ store.run.plan?.tasks?.length || 0 }} 项完成 <span class="fold-chevron" aria-hidden="true">⌄</span></span></summary>
                  <div class="folio-content fold-scroll max-h-[480px] overflow-y-auto overscroll-contain">
                    <template v-if="store.run.plan"><div class="plan-overview"><p class="plan-question">{{ store.run.plan.research_question }}</p><p class="plan-scope">{{ store.run.plan.scope }}</p><div class="domain-row"><span v-for="domain in store.run.plan.research_domains" :key="domain" class="domain-chip">{{ domain }}</span><span v-if="store.run.plan.risk_level === 'high'" class="domain-chip is-risk">高风险证据标准</span></div></div>
                      <div class="plan-task-list"><article v-for="task in store.run.plan.tasks" :key="task.id" class="plan-task"><span class="task-state" :class="{ 'is-complete': task.completed }">{{ task.completed ? '✓' : '·' }}</span><div class="task-question">{{ task.question }}<p v-if="task.acceptance_criteria?.length" class="task-criteria">验收：{{ task.acceptance_criteria.join('；') }}</p></div><span class="task-type">{{ task.task_type }} / {{ task.priority }}</span></article></div>
                    </template><p v-else class="empty-note">研究计划生成后会显示。</p>
                  </div>
                </details>

                <details class="folio-section">
                  <summary class="folio-summary"><h2>综合结论</h2><span class="folio-summary-meta">{{ store.run.findings.length }} 条 <span class="fold-chevron" aria-hidden="true">⌄</span></span></summary>
                  <div class="folio-content fold-scroll max-h-[480px] overflow-y-auto overscroll-contain"><div class="finding-list"><article v-for="finding in store.run.findings" :key="finding.id" class="finding-entry"><div class="finding-topline"><button class="reference-chip" @click="showCitation(finding.id)">{{ finding.classification }} / {{ finding.id }}</button><span class="text-[10px] text-[var(--muted)]">置信度 {{ Math.round(finding.confidence * 100) }}%</span></div><p class="finding-text">{{ finding.statement }}</p><div class="reference-row"><button v-for="id in finding.evidence_ids" :key="id" class="reference-link" @click="showCitation(id)">{{ id }}</button></div></article></div><p v-if="!store.run.findings.length" class="empty-note">当前还没有已综合的结论。</p></div>
                </details>

                <details class="folio-section">
                  <summary class="folio-summary"><h2>审稿意见</h2><span class="folio-summary-meta">{{ store.run.critiques.length }} 轮 <span class="fold-chevron" aria-hidden="true">⌄</span></span></summary>
                  <div class="folio-content fold-scroll max-h-[480px] overflow-y-auto overscroll-contain"><div class="critique-list"><article v-for="review in store.run.critiques" :key="review.iteration" class="critique-entry"><div class="critique-head"><span class="status-pill" :class="review.decision === 'approve' ? 'is-complete' : 'is-progress'">{{ review.decision === 'approve' ? '通过' : review.decision === 'research_more' ? '要求补证' : '人工复核' }}</span><span class="text-[10px] text-[var(--muted)]">第 {{ review.iteration }} 轮</span></div><p v-for="(issue,index) in review.issues" :key="index" class="critique-issue"><strong>{{ issue.severity }}</strong> / {{ issue.problem }} <button v-if="issue.finding_id" class="reference-link" @click="showCitation(issue.finding_id)">{{ issue.finding_id }}</button></p></article></div><p v-if="!store.run.critiques.length" class="empty-note">研究审稿后会在此显示意见。</p></div>
                </details>
              </div>

              <aside class="margin-rail">
                <section class="margin-card">
                  <div class="margin-card-head"><h2>研究进度</h2><span>第 {{ store.run.iteration }} / {{ store.run.max_iterations }} 轮</span></div>
                  <strong class="progress-figure">{{ progress }}%</strong>
                  <div class="progress-track"><span :style="{ width: `${progress}%` }"></span></div>
                  <p class="progress-caption">审稿与补证会在同一研究中持续推进。</p>
                </section>
                <section class="margin-card">
                  <div class="margin-card-head"><h2>活动记录</h2><span>{{ store.run.events.length }} 条</span></div>
                  <div class="activity-list"><article v-for="event in [...store.run.events].slice(-10).reverse()" :key="event.sequence" class="activity-entry"><span class="activity-dot"></span><div>{{ event.message }}<time class="activity-time">{{ formatDate(event.created_at) }}</time></div></article><p v-if="!store.run.events.length" class="empty-note">暂无活动记录。</p></div>
                </section>
                <section class="margin-card">
                  <div class="margin-card-head"><h2>审查通过的证据</h2><span>{{ store.run.evidence.length }} 条</span></div>
                  <div class="evidence-list"><article v-for="item in store.run.evidence.slice(0,10)" :key="item.id" class="evidence-entry"><p class="evidence-claim">{{ item.claim }}</p><a class="evidence-source" :href="item.source.url" target="_blank" rel="noopener noreferrer">↗ {{ item.source.title }}</a><p class="evidence-meta">{{ item.source.publisher || item.source.source_type }} / {{ Math.round(item.confidence * 100) }}%</p><button class="evidence-link" @click="showCitation(item.id)">{{ item.id }}</button></article><p v-if="!store.run.evidence.length" class="empty-note">证据审查后会在此显示。</p></div>
                </section>
              </aside>
            </div>
          </template>
        </section>
      </main>
    </div>

    <dialog ref="createDialog" class="research-dialog fixed left-1/2 top-1/2 m-0 max-h-[88vh] w-[min(620px,calc(100vw-24px))] -translate-x-1/2 -translate-y-1/2 overflow-y-auto p-0 shadow-2xl">
      <form class="p-6 sm:p-7" @submit.prevent="submitResearch">
        <div class="mb-6 flex items-start justify-between gap-4">
          <div><p class="dialog-kicker">新建研究</p><h2 class="dialog-title">先写下你想弄清的问题</h2><p class="section-note mt-2 max-w-lg">系统会拆解研究任务、追踪来源，并把结论与证据一起保存。</p></div>
          <button type="button" class="rounded p-1.5 text-xl text-[var(--muted)] hover:bg-[#eef3ef]" aria-label="关闭" @click="closeCreateDialog">×</button>
        </div>
        <label for="topic" class="dialog-field-label mb-2 block">研究主题或问题</label>
        <textarea id="topic" v-model="topic" maxlength="2000" required class="dialog-input min-h-36 w-full resize-y p-3 leading-7" placeholder="例如：评估某项政策对中小企业创新投入的影响，重点关注实施机制、效果证据与地区差异。"></textarea>
        <div class="dialog-help mt-1 flex justify-between gap-4"><span>技术、商业、政策、科学、人物与事件都可以研究</span><span class="shrink-0">{{ topic.length }} / 2000</span></div>
        <div class="mt-5 grid gap-4 sm:grid-cols-2">
          <div>
            <label for="report-language" class="dialog-field-label mb-2 block">报告语言</label>
            <input id="report-language" v-model.trim="reportLanguage" list="report-language-options" class="dialog-input h-10 w-full px-3" placeholder="跟随研究请求，例如 en">
          </div>
          <div>
            <label for="iterations" class="dialog-field-label mb-2 block">初始研究轮次</label>
            <select id="iterations" v-model.number="iterations" class="dialog-input h-10 w-full px-3"><option v-for="count in 5" :key="count" :value="count">{{ count }} 轮</option></select>
          </div>
        </div>
        <datalist id="report-language-options">
          <option v-for="language in reportLanguages" :key="language.tag" :value="language.tag">{{ language.label }}</option>
        </datalist>
        <p class="dialog-help mt-2">报告、计划、结论与追问使用所选语言；来源标题和原文摘录保持原语言。达到轮次上限但没有可写结论时，会自动追加一轮补证。</p>
        <div class="mt-6 flex justify-end gap-2"><button type="button" class="dialog-cancel" @click="closeCreateDialog">取消</button><button class="dialog-submit disabled:opacity-50" :disabled="creating">{{ creating ? '正在发起…' : '开始研究' }}</button></div>
      </form>
    </dialog>

    <CitationDialog ref="citationDialog" :sources="citationSources" :finding-statement="findingStatement" :loading="citationLoading" />
    <button
      v-if="pendingFollowUp"
      data-follow-up-trigger
      type="button"
      class="follow-up-trigger fixed z-30 inline-flex h-7 items-center gap-1 rounded-full px-2.5 text-[11px] font-semibold leading-none text-white transition-colors"
      :style="{ left: `${Math.max(8, Math.min(pendingFollowUp.position.x + 8, windowWidth - 64))}px`, top: `${Math.max(8, Math.min(pendingFollowUp.position.y - 36, windowHeight - 44))}px` }"
      aria-label="对选中内容提问"
      @mousedown.prevent
      @click="openFollowUpPanel"
    >
      <svg
        data-follow-up-trigger-icon
        class="h-3 w-3 shrink-0"
        viewBox="0 0 16 16"
        fill="none"
        stroke="currentColor"
        stroke-width="1.7"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
      >
        <path d="M3 3.5h10v7H7.2L4 13v-2.5H3z" />
      </svg>
      <span>提问</span>
    </button>
    <FollowUpPanel
      v-if="followUpOpen || store.selectedFollowUp"
      :passage="pendingFollowUp?.anchor.text || store.selectedFollowUp?.anchor.text || ''"
      :messages="store.selectedFollowUp?.messages || []"
      :busy="followUpBusy"
      :error="followUpError"
      :can-delete="Boolean(store.selectedFollowUp)"
      :narrow="narrowViewport"
      @submit="submitFollowUp"
      @retry="retryFollowUp"
      @delete="deleteFollowUp"
      @close="closeFollowUp"
    />
    <div v-if="toastMessage" class="toast fixed bottom-5 right-5 z-50 max-w-sm px-4 py-3" :class="{ 'is-error': toastError }" role="status">{{ toastMessage }}</div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useResearchStore } from "./stores/research";
import WorkflowDiagram from "./components/WorkflowDiagram.vue";
import ResearchList from "./components/ResearchList.vue";
import ReportView from "./components/ReportView.vue";
import CitationDialog from "./components/CitationDialog.vue";
import FollowUpPanel from "./components/FollowUpPanel.vue";

const store = useResearchStore();
const createDialog = ref(null);
const citationDialog = ref(null);
const citationSources = ref([]);
const findingStatement = ref("");
const citationLoading = ref(false);
const pendingFollowUp = ref(null);
const followUpOpen = ref(false);
const followUpSubmitting = ref(false);
const followUpError = ref("");
const windowWidth = ref(window.innerWidth);
const windowHeight = ref(window.innerHeight);
const topic = ref("");
const reportLanguage = ref("");
const reportOpen = ref(false);
const iterations = ref(3);
const creating = ref(false);
const toastMessage = ref("");
const toastError = ref(false);
let toastTimer;
const reportLanguages = [
  { tag: "zh-CN", label: "简体中文 · 已验证" },
  { tag: "en", label: "English · 已验证" },
  { tag: "ja", label: "日本語 · 已验证" },
  { tag: "es", label: "Español · 已验证" },
  { tag: "ar", label: "العربية · 已验证" },
  { tag: "fr", label: "Français" },
  { tag: "de", label: "Deutsch" },
  { tag: "ko", label: "한국어" },
  { tag: "pt", label: "Português" },
  { tag: "hi", label: "हिन्दी" },
];

const pageTitle = computed(() => store.run?.user_request || "研究任务");
const activeCount = computed(() => store.runs.filter((item) => !["completed", "failed", "cancelled", "needs_human_review", "paused"].includes(item.status)).length);
const completedCount = computed(() => store.runs.filter((item) => item.status === "completed").length);
const reviewCount = computed(() => store.runs.filter((item) => item.status === "needs_human_review").length);
const completedTasks = computed(() => store.run?.plan?.tasks?.filter((task) => task.completed).length || 0);
const runError = computed(() => store.run?.error || "");
const followUpBusy = computed(() => followUpSubmitting.value || store.selectedFollowUpBusy);
const narrowViewport = computed(() => windowWidth.value < 640);
const progress = computed(() => {
  const run = store.run;
  if (!run) return 0;
  if (run.status === "completed") return 100;
  const tasks = run.plan?.tasks || [];
  return Math.min(94, Math.round(run.iteration / Math.max(1, run.max_iterations) * 75 + tasks.filter((task) => task.completed).length / Math.max(1, tasks.length) * 25));
});
const today = new Date().toLocaleDateString("zh-CN", { year: "numeric", month: "long", day: "numeric" });
const connectionLabel = computed(() => ({ online: "API 已连接", stream: "实时连接", polling: "轮询回退", offline: "API 未连接", connecting: "正在连接" })[store.connection]);

function openCreateDialog() { createDialog.value?.showModal(); }
function closeCreateDialog() { createDialog.value?.close(); }
function formatDate(value) { return value ? new Date(value).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—"; }
function statusLabel(status) { return ({ planning: "规划中", researching: "研究中", reviewing_evidence: "审查中", synthesizing: "综合中", critic_review: "反方审阅", writing: "撰写报告", paused: "已暂停", completed: "已完成", needs_human_review: "待人工复核", failed: "失败", cancelled: "已结束" })[status] || status; }
function statusClass(status) {
  if (status === "completed") return "is-complete";
  if (["failed", "needs_human_review"].includes(status)) return "is-alert";
  if (["planning", "researching", "reviewing_evidence", "synthesizing", "critic_review", "writing"].includes(status)) return "is-progress";
  if (status === "paused") return "is-paused";
  return "is-muted";
}
function notify(message, error = false) {
  toastMessage.value = message;
  toastError.value = error;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toastMessage.value = ""; }, 3000);
}
async function openRun(id) { await store.openRun(id); }
async function backToList() { store.clearRun(); await store.loadRuns(); }
async function submitResearch() {
  if (!topic.value.trim()) return;
  creating.value = true;
  try {
    await store.createRun(topic.value.trim(), iterations.value, reportLanguage.value);
    topic.value = "";
    reportLanguage.value = "";
    closeCreateDialog();
    notify("研究已发起");
  } catch (error) { notify(error.message, true); }
  finally { creating.value = false; }
}
async function runAction(action) {
  try {
    await store.runAction(action);
    notify(action === "cancel" ? "已发送取消请求" : "已发送继续研究请求");
  } catch (error) { notify(error.message, true); }
}
async function finishRun(run) {
  if (!window.confirm(`结束研究主题“${run.user_request}”？已保存的进度会保留，但结束后不能继续。`)) return;
  if (store.runId !== run.id) await store.openRun(run.id);
  try {
    await store.runAction("cancel");
    notify("研究任务已结束");
  } catch (error) { notify(error.message, true); }
}
async function continueRun(run) {
  if (store.runId !== run.id) await store.openRun(run.id);
  try {
    await store.runAction("resume");
    notify("研究任务已从保存的进度继续");
  } catch (error) { notify(error.message, true); }
}
async function deleteRun(run) {
  if (!window.confirm(`确定删除研究主题“${run.user_request}”吗？计划、证据、结论、审稿记录、报告及其全部追问会话都会一并删除，此操作不可撤销。`)) return;
  try {
    await store.deleteRun(run.id);
    notify("研究记录及关联数据已删除");
  } catch (error) { notify(error.message, true); }
}
async function showCitation(referenceId) {
  citationLoading.value = true;
  citationSources.value = [];
  findingStatement.value = "";
  citationDialog.value?.open();
  try {
    const reference = await store.citation(referenceId);
    citationSources.value = reference?.sources || [];
    findingStatement.value = reference?.finding_statement || "";
  } catch (error) { notify(error.message, true); }
  finally { citationLoading.value = false; }
}

function openFollowUpSelection(selection) {
  pendingFollowUp.value = selection;
  followUpOpen.value = false;
  followUpError.value = "";
  if (selection) {
    store.closeFollowUpStream();
    store.selectedFollowUpId = null;
    return;
  }
  const expanded = store.followUps.find((item) => item.is_minimized === false);
  if (store.selectedFollowUpId === (expanded?.id || null)) return;
  store.closeFollowUpStream();
  store.selectedFollowUpId = expanded?.id || null;
  if (store.selectedFollowUp) store.connectFollowUpStream(store.selectedFollowUp);
}

function clearReportInteraction() {
  pendingFollowUp.value = null;
  followUpOpen.value = false;
  followUpError.value = "";
  window.getSelection()?.removeAllRanges();
}

function handleReportToggle(event) {
  reportOpen.value = event.currentTarget.open;
  if (reportOpen.value) return;
  clearReportInteraction();
}

async function restoreFollowUp(threadId) {
  pendingFollowUp.value = null;
  followUpOpen.value = false;
  followUpError.value = "";
  try {
    await store.expandFollowUp(threadId);
  } catch (error) {
    notify(error.message, true);
  }
}

function openFollowUpPanel() {
  if (!pendingFollowUp.value) return;
  followUpOpen.value = true;
  pendingFollowUp.value = {
    ...pendingFollowUp.value,
    anchor: {
      ...pendingFollowUp.value.anchor,
      report_digest: store.run?.report?.anchor_digest || "",
    },
  };
}

async function submitFollowUp(question) {
  if ((!pendingFollowUp.value && !store.selectedFollowUp) || followUpBusy.value) return;
  followUpSubmitting.value = true;
  followUpError.value = "";
  try {
    if (pendingFollowUp.value) {
      await store.createFollowUp(pendingFollowUp.value.anchor, question);
      pendingFollowUp.value = null;
    } else {
      await store.appendFollowUp(question);
    }
  } catch (error) {
    followUpError.value = error.message;
  } finally {
    followUpSubmitting.value = false;
  }
}

async function retryFollowUp(messageId) {
  if (followUpBusy.value || !store.selectedFollowUp) return;
  followUpSubmitting.value = true;
  followUpError.value = "";
  try {
    await store.retryFollowUp(messageId);
  } catch (error) {
    followUpError.value = error.message;
  } finally {
    followUpSubmitting.value = false;
  }
}

async function deleteFollowUp() {
  const thread = store.selectedFollowUp;
  if (!thread) return;
  if (!window.confirm("确定删除这次追问会话吗？完整消息记录、高亮和标记都会一并删除，此操作不可撤销。")) return;
  try {
    await store.deleteFollowUp(thread.id);
    pendingFollowUp.value = null;
    followUpOpen.value = false;
    followUpError.value = "";
    notify("追问会话已删除");
  } catch (error) {
    notify(error.message, true);
  }
}

async function closeFollowUp() {
  const hadPersistedThread = Boolean(store.selectedFollowUp);
  if (hadPersistedThread) {
    try {
      await store.minimizeFollowUp();
    } catch (error) {
      notify(error.message, true);
      return;
    }
  } else {
    store.closeFollowUpStream();
  }
  pendingFollowUp.value = null;
  followUpOpen.value = false;
  followUpError.value = "";
}

function updateViewport() {
  windowWidth.value = window.innerWidth;
  windowHeight.value = window.innerHeight;
}

watch(() => store.runId, () => {
  reportOpen.value = false;
  clearReportInteraction();
});

onMounted(() => {
  store.loadRuns();
  window.addEventListener("resize", updateViewport);
});
onUnmounted(() => {
  store.clearRun();
  clearTimeout(toastTimer);
  window.removeEventListener("resize", updateViewport);
});
</script>

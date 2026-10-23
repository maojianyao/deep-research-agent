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

          <ResearchList @open="openRun" @finish="finishRun" @continue="continueRun" @delete="deleteRun" />

          <section class="workspace-ledger" aria-label="研究任务总览">
            <div class="ledger-metric"><span class="metric-label">全部研究</span><strong class="metric-value">{{ store.summary.total }}</strong><span class="metric-note">工作区中的研究档案</span></div>
            <div class="ledger-metric"><span class="metric-label">正在推进</span><strong class="metric-value">{{ store.summary.active }}</strong><span class="metric-note is-warm">全工作区持续更新</span></div>
            <div class="ledger-metric"><span class="metric-label">已形成报告</span><strong class="metric-value">{{ store.summary.completed }}</strong><span class="metric-note is-good">全工作区可阅读</span></div>
            <div class="ledger-metric"><span class="metric-label">等待判断</span><strong class="metric-value">{{ store.summary.needs_human_review }}</strong><span class="metric-note is-alert">全工作区需人工复核</span></div>
          </section>

          <details id="workflow" data-research-guide class="home-guide">
            <summary>
              <span>了解研究如何推进</span>
              <span>从任务拆解到证据核验，共六个阶段</span>
              <span class="fold-chevron" aria-hidden="true">⌄</span>
            </summary>
            <WorkflowDiagram />
          </details>
        </template>

        <section v-else class="run-dossier">
          <button class="w-fit text-xs text-[var(--moss)] hover:underline" @click="backToList">← 返回研究任务</button>
          <div v-if="!store.run" class="run-load-state" :role="runLoading ? 'status' : 'alert'">
            <strong>{{ runLoading ? "正在读取研究档案" : runErrorMessage }}</strong>
            <p v-if="runLoading">正在加载计划、来源与报告。</p>
            <div v-if="!runLoading" class="mt-4 flex justify-center gap-2">
              <button class="secondary-action" @click="retryCurrentRun">重新读取</button>
              <button class="secondary-action" @click="backToList">返回研究任务</button>
            </div>
          </div>
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
              <aside data-dossier-nav class="dossier-index">
                <p class="dossier-index-title">档案目录</p>
                <nav class="dossier-tabs" role="tablist" aria-label="研究档案内容" aria-orientation="vertical">
                  <button
                    v-for="tab in dossierTabs"
                    :id="`dossier-tab-${tab.id}`"
                    :key="tab.id"
                    type="button"
                    role="tab"
                    class="dossier-tab"
                    :aria-selected="activeDossierTab === tab.id"
                    :aria-controls="`dossier-panel-${tab.id}`"
                    :tabindex="activeDossierTab === tab.id ? 0 : -1"
                    @click="activeDossierTab = tab.id"
                    @keydown.down.prevent="moveDossierTab(1)"
                    @keydown.up.prevent="moveDossierTab(-1)"
                    @keydown.right.prevent="moveDossierTab(1)"
                    @keydown.left.prevent="moveDossierTab(-1)"
                  >
                    <span>{{ tab.label }}</span>
                    <small>{{ tab.count }}</small>
                  </button>
                </nav>
                <div
                  v-if="activeDossierTab === 'report' && reportHeadings.length"
                  data-report-outline
                  class="index-outline"
                  aria-label="报告主题"
                >
                  <div class="index-outline-head">
                    <span>报告主题</span>
                    <small>{{ activeHeadingLabel || "阅读位置" }}</small>
                  </div>
                  <button
                    v-for="heading in reportHeadings"
                    :key="heading.id"
                    type="button"
                    :data-heading-level="heading.level"
                    :class="{ 'is-active': activeHeadingId === heading.id }"
                    :aria-current="activeHeadingId === heading.id ? 'location' : undefined"
                    @click="scrollToReportHeading(heading.id)"
                  >
                    <span class="index-outline-rule" aria-hidden="true"></span>
                    <span>{{ heading.text }}</span>
                  </button>
                  <button data-report-back-to-top type="button" class="index-back-top" @click="scrollToReportTop">
                    回到报告顶部
                  </button>
                </div>
              </aside>

              <div class="folio-stack">
                <section
                  v-show="activeDossierTab === 'report'"
                  id="dossier-panel-report"
                  role="tabpanel"
                  aria-labelledby="dossier-tab-report"
                  class="dossier-panel"
                >
                  <div class="report-sheet">
                    <ReportView
                      ref="reportView"
                      :markdown="store.run.report?.markdown || ''"
                      :active="store.isActive"
                      :eligible="store.run.status === 'completed' && Boolean(store.run.report)"
                      :follow-ups="store.followUps"
                      :language="store.run.report?.language || store.run.report_language"
                      :direction="store.run.report?.direction || store.run.report_direction"
                      :expanded="true"
                      :citation-labels="citationContext.labels"
                      @citation="openCitationTrace"
                      @headings="reportHeadings = $event"
                      @heading-change="activeHeadingId = $event"
                      @selection="openFollowUpSelection"
                      @selection-error="notify($event, true)"
                      @restore-follow-up="restoreFollowUp"
                    />
                  </div>
                </section>

                <section
                  v-if="activeDossierTab === 'plan'"
                  id="dossier-panel-plan"
                  role="tabpanel"
                  aria-labelledby="dossier-tab-plan"
                  class="dossier-panel"
                >
                  <div class="dossier-panel-heading"><h2>研究计划</h2><span>{{ completedTasks }} / {{ store.run.plan?.tasks?.length || 0 }} 项完成</span></div>
                  <template v-if="store.run.plan">
                    <div class="plan-overview"><p class="plan-question">{{ store.run.plan.research_question }}</p><p class="plan-scope">{{ store.run.plan.scope }}</p><div class="domain-row"><span v-for="domain in store.run.plan.research_domains" :key="domain" class="domain-chip">{{ domain }}</span><span v-if="store.run.plan.risk_level === 'high'" class="domain-chip is-risk">高风险证据标准</span></div></div>
                    <div class="plan-task-list"><article v-for="task in store.run.plan.tasks" :key="task.id" class="plan-task"><span class="task-state" :class="{ 'is-complete': task.completed }">{{ task.completed ? '✓' : '·' }}</span><div class="task-question">{{ task.question }}<p v-if="task.acceptance_criteria?.length" class="task-criteria">验收：{{ task.acceptance_criteria.join('；') }}</p></div><span class="task-type">{{ task.task_type }} / {{ task.priority }}</span></article></div>
                  </template>
                  <p v-else class="empty-note">研究计划生成后会显示。</p>
                </section>

                <section
                  v-if="activeDossierTab === 'findings'"
                  id="dossier-panel-findings"
                  role="tabpanel"
                  aria-labelledby="dossier-tab-findings"
                  class="dossier-panel"
                >
                  <div class="dossier-panel-heading"><h2>综合结论</h2><span>{{ store.run.findings.length }} 条</span></div>
                  <div class="finding-list" @click="handleInlineCitation">
                    <article
                      v-for="finding in store.run.findings"
                      :key="finding.id"
                      :data-citation-item="finding.id"
                      tabindex="-1"
                      class="finding-entry"
                    >
                      <div class="finding-topline"><button class="reference-chip" @click.stop="openCitationTrace(finding.id)">{{ finding.classification }} / 查看关联证据</button><span class="text-[11px] text-[var(--muted)]">置信度 {{ Math.round(finding.confidence * 100) }}%</span></div>
                      <div class="finding-text" v-html="renderCitedMarkdown(finding.statement)"></div>
                      <div class="reference-row"><button v-for="id in finding.evidence_ids" :key="id" class="reference-link" @click.stop="openCitationTrace(id)">[{{ citationLabel(id) }}]</button></div>
                    </article>
                  </div>
                  <p v-if="!store.run.findings.length" class="empty-note">当前还没有已综合的结论。</p>
                </section>

                <section
                  v-if="activeDossierTab === 'critiques'"
                  id="dossier-panel-critiques"
                  role="tabpanel"
                  aria-labelledby="dossier-tab-critiques"
                  class="dossier-panel"
                >
                  <div class="dossier-panel-heading"><h2>审稿意见</h2><span>{{ store.run.critiques.length }} 轮</span></div>
                  <div class="critique-list" @click="handleInlineCitation"><article v-for="review in store.run.critiques" :key="review.iteration" class="critique-entry"><div class="critique-head"><span class="status-pill" :class="review.decision === 'approve' ? 'is-complete' : 'is-progress'">{{ review.decision === 'approve' ? '通过' : review.decision === 'research_more' ? '要求补证' : '人工复核' }}</span><span class="text-[11px] text-[var(--muted)]">第 {{ review.iteration }} 轮</span></div><p v-for="(issue,index) in review.issues" :key="index" :data-citation-item="critiqueItemId(review, index)" tabindex="-1" class="critique-issue"><strong>{{ issue.severity }}</strong> / <span v-html="renderCitedMarkdown(issue.problem)"></span> <button v-if="issue.finding_id" class="reference-link" @click.stop="openCitationTrace(issue.finding_id)">[{{ citationLabel(issue.finding_id) }}]</button></p></article></div>
                  <p v-if="!store.run.critiques.length" class="empty-note">研究审稿后会在此显示意见。</p>
                </section>

                <section
                  v-if="activeDossierTab === 'evidence'"
                  id="dossier-panel-evidence"
                  role="tabpanel"
                  aria-labelledby="dossier-tab-evidence"
                  class="dossier-panel"
                >
                  <EvidenceLibrary
                    :run-id="store.run.id"
                    :focus-evidence-id="focusedEvidenceId"
                    :citation-occurrences="citationContext.occurrences"
                    @return-to-report="returnToReportCitation"
                  />
                </section>
              </div>

              <aside class="margin-rail">
                <ResearchStagePanel :run="store.run" />
                <section class="margin-card">
                  <div class="margin-card-head"><h2>活动记录</h2><span>{{ store.run.events.length }} 条</span></div>
                  <div class="activity-list"><article v-for="event in [...store.run.events].slice(-10).reverse()" :key="event.sequence" class="activity-entry"><span class="activity-dot"></span><div>{{ event.message }}<time class="activity-time">{{ formatDate(event.created_at) }}</time></div></article><p v-if="!store.run.events.length" class="empty-note">暂无活动记录。</p></div>
                </section>
                <section class="margin-card">
                  <div class="margin-card-head"><h2>审查通过的证据</h2><span>{{ store.run.evidence.length }} 条</span></div>
                  <div class="evidence-list"><article v-for="item in store.run.evidence.slice(0,10)" :key="item.id" class="evidence-entry"><p class="evidence-claim">{{ item.claim }}</p><a class="evidence-source" :href="item.source.url" target="_blank" rel="noopener noreferrer">↗ {{ item.source.title }}</a><p class="evidence-meta">{{ item.source.publisher || item.source.source_type }} / {{ Math.round(item.confidence * 100) }}%</p><button class="evidence-link" @click="showCitation(item.id)">{{ item.id }}</button></article><p v-if="!store.run.evidence.length" class="empty-note">证据审查后会在此显示。</p></div>
                  <button
                    v-if="store.run.evidence.length"
                    type="button"
                    class="evidence-library-entry"
                    @click="activeDossierTab = 'evidence'"
                  >查看全部 {{ store.run.evidence.length }} 条证据</button>
                </section>
              </aside>
            </div>
          </template>
        </section>
      </main>
    </div>

    <CreateResearchDialog
      ref="createDialog"
      :creating="creating"
      :error="createError"
      @create="submitResearch"
      @close="createError = ''"
    />

    <CitationDialog ref="citationDialog" :sources="citationSources" :finding-statement="findingStatement" :loading="citationLoading" />
    <button
      v-if="pendingFollowUp"
      data-follow-up-trigger
      type="button"
      class="follow-up-trigger fixed z-30 inline-flex min-h-11 items-center gap-1 rounded-full px-3 text-[11px] font-semibold leading-none text-white transition-colors"
      data-touch-target="44"
      :style="{ left: `${Math.max(8, Math.min(pendingFollowUp.position.x + 8, windowWidth - 80))}px`, top: `${Math.max(8, Math.min(pendingFollowUp.position.y - 48, windowHeight - 52))}px` }"
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
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { useResearchStore } from "./stores/research";
import WorkflowDiagram from "./components/WorkflowDiagram.vue";
import ResearchList from "./components/ResearchList.vue";
import ReportView from "./components/ReportView.vue";
import CitationDialog from "./components/CitationDialog.vue";
import FollowUpPanel from "./components/FollowUpPanel.vue";
import CreateResearchDialog from "./components/CreateResearchDialog.vue";
import EvidenceLibrary from "./components/EvidenceLibrary.vue";
import ResearchStagePanel from "./components/ResearchStagePanel.vue";
import { buildCitationContext } from "./lib/citations";
import { safeMarkdown } from "./lib/markdown";

const store = useResearchStore();
const createDialog = ref(null);
const citationDialog = ref(null);
const reportView = ref(null);
const citationSources = ref([]);
const findingStatement = ref("");
const citationLoading = ref(false);
const pendingFollowUp = ref(null);
const followUpOpen = ref(false);
const followUpSubmitting = ref(false);
const followUpError = ref("");
const windowWidth = ref(window.innerWidth);
const windowHeight = ref(window.innerHeight);
const activeDossierTab = ref("report");
const reportHeadings = ref([]);
const activeHeadingId = ref("");
const focusedEvidenceId = ref("");
const creating = ref(false);
const createError = ref("");
const runLoading = ref(false);
const runLoadError = ref("");
const toastMessage = ref("");
const toastError = ref(false);
let toastTimer;
const pageTitle = computed(() => store.run?.user_request || "研究任务");
const citationSections = computed(() => [
  ...(store.run?.findings || []).map((finding) => ({
    source: "findings",
    itemId: finding.id,
    referenceId: finding.id,
    markdown: finding.statement || "",
  })),
  ...(store.run?.critiques || []).flatMap((review) => (
    (review.issues || []).map((issue, index) => ({
      source: "critiques",
      itemId: critiqueItemId(review, index),
      referenceId: issue.finding_id || "",
      markdown: issue.problem || "",
    }))
  )),
]);
const citationContext = computed(
  () => buildCitationContext(
    store.run?.report?.markdown || "",
    [
      ...(store.run?.evidence || []).map((item) => item.id),
      ...(store.run?.findings || []).map((item) => item.id),
    ],
    citationSections.value,
  ),
);
const dossierTabs = computed(() => [
  { id: "report", label: "研究报告", count: store.run?.report ? "正文" : "未生成" },
  {
    id: "plan",
    label: "研究计划",
    count: `${completedTasks.value} / ${store.run?.plan?.tasks?.length || 0} 项`,
  },
  { id: "findings", label: "综合结论", count: `${store.run?.findings?.length || 0} 条` },
  { id: "critiques", label: "审稿意见", count: `${store.run?.critiques?.length || 0} 轮` },
  { id: "evidence", label: "审查证据", count: `${store.run?.evidence?.length || 0} 条` },
]);
const activeHeadingLabel = computed(
  () => reportHeadings.value.find((heading) => heading.id === activeHeadingId.value)?.text || "",
);
const runErrorMessage = computed(() => {
  const message = runLoadError.value || store.error;
  if (/not found/i.test(message || "")) {
    return "找不到这份研究档案。它可能已经被删除。";
  }
  return message || "无法读取研究档案。";
});
const completedTasks = computed(() => store.run?.plan?.tasks?.filter((task) => task.completed).length || 0);
const runError = computed(() => store.run?.error || "");
const followUpBusy = computed(() => followUpSubmitting.value || store.selectedFollowUpBusy);
const narrowViewport = computed(() => windowWidth.value < 640);
const today = new Date().toLocaleDateString("zh-CN", { year: "numeric", month: "long", day: "numeric" });
const connectionLabel = computed(() => ({ online: "API 已连接", stream: "实时连接", polling: "轮询回退", offline: "API 未连接", connecting: "正在连接" })[store.connection]);

function openCreateDialog() { createError.value = ""; createDialog.value?.open(); }
function formatDate(value) { return value ? new Date(value).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—"; }
function statusLabel(status) { return ({ planning: "规划中", researching: "研究中", reviewing_evidence: "审查中", synthesizing: "综合中", critic_review: "反方审阅", writing: "撰写报告", paused: "已暂停", completed: "已完成", needs_human_review: "待人工复核", failed: "失败", cancelled: "已结束" })[status] || status; }
function statusClass(status) {
  if (status === "completed") return "is-complete";
  if (["failed", "needs_human_review"].includes(status)) return "is-alert";
  if (["planning", "researching", "reviewing_evidence", "synthesizing", "critic_review", "writing"].includes(status)) return "is-progress";
  if (status === "paused") return "is-paused";
  return "is-muted";
}
function citationLabel(referenceId) {
  return citationContext.value.labels[referenceId] || "未引用";
}
function critiqueItemId(review, index) {
  return `critique-${review.iteration}-${index}`;
}
function renderCitedMarkdown(value) {
  return safeMarkdown(value || "", { citationLabels: citationContext.value.labels });
}
function handleInlineCitation(event) {
  const citation = event.target.closest?.(".citation-id");
  if (citation) openCitationTrace(citation.dataset.ref);
}
function notify(message, error = false) {
  toastMessage.value = message;
  toastError.value = error;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toastMessage.value = ""; }, 3000);
}
function runLocation(id = null) {
  const url = new URL(window.location.href);
  if (id) url.searchParams.set("run", id);
  else url.searchParams.delete("run");
  url.hash = "";
  return `${url.pathname}${url.search}`;
}
function syncRunUrl(id, mode = "push") {
  const target = runLocation(id);
  if (`${window.location.pathname}${window.location.search}` === target) return;
  window.history[mode === "replace" ? "replaceState" : "pushState"]({ runId: id }, "", target);
}
async function loadRunFromRoute(id) {
  runLoading.value = true;
  runLoadError.value = "";
  try {
    const error = await store.openRun(id);
    if (!store.run) {
      runLoadError.value = error || store.error || "无法读取研究档案。";
    }
  } finally {
    runLoading.value = false;
  }
}
async function openRun(id) {
  syncRunUrl(id);
  await loadRunFromRoute(id);
}
async function backToList() {
  syncRunUrl(null);
  store.clearRun();
  await store.loadRuns();
}
async function retryCurrentRun() {
  const id = new URLSearchParams(window.location.search).get("run");
  if (id) await loadRunFromRoute(id);
}
async function handlePopState() {
  const id = new URLSearchParams(window.location.search).get("run");
  if (!id) {
    store.clearRun();
    await store.loadRuns();
    return;
  }
  if (id !== store.runId || !store.run) await loadRunFromRoute(id);
}
async function submitResearch(payload) {
  if (!payload.topic.trim()) return;
  creating.value = true;
  createError.value = "";
  try {
    const result = await store.createRun(
      payload.topic.trim(),
      payload.iterations,
      payload.reportLanguage,
    );
    syncRunUrl(result.id, "replace");
    createDialog.value?.reset();
    createDialog.value?.close();
    notify("研究已发起");
  } catch (error) {
    createError.value = error.message;
    notify(error.message, true);
  }
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
  if (store.runId !== run.id) await openRun(run.id);
  try {
    await store.runAction("cancel");
    notify("研究任务已结束");
  } catch (error) { notify(error.message, true); }
}
async function continueRun(run) {
  if (store.runId !== run.id) await openRun(run.id);
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

async function openCitationTrace(referenceId) {
  let evidenceId = referenceId.startsWith("evidence_") ? referenceId : "";
  if (!evidenceId) {
    try {
      const reference = await store.citation(referenceId);
      evidenceId = reference?.sources?.[0]?.evidence_id || "";
    } catch (error) {
      notify(error.message, true);
      return;
    }
  }
  if (!evidenceId) {
    notify("没有找到这条引用对应的证据。", true);
    return;
  }
  focusedEvidenceId.value = evidenceId;
  activeDossierTab.value = "evidence";
}

async function returnToReportCitation({ evidenceId, occurrenceIndex }) {
  const occurrence = citationContext.value.occurrences[evidenceId]?.[occurrenceIndex];
  const source = occurrence?.source || "report";
  activeDossierTab.value = source;
  await nextTick();
  if (source === "report") {
    reportView.value?.focusCitation(
      evidenceId,
      Math.max(0, occurrence?.itemIndex ?? occurrenceIndex),
    );
    return;
  }
  focusDossierCitation(evidenceId, occurrence);
}
function focusDossierCitation(referenceId, occurrence) {
  const item = Array.from(document.querySelectorAll("[data-citation-item]")).find(
    (candidate) => candidate.dataset.citationItem === occurrence?.itemId,
  );
  if (!item) return;
  const citations = Array.from(item.querySelectorAll(".citation-id")).filter(
    (citation) => citation.dataset.ref === referenceId,
  );
  const target = citations[occurrence?.itemIndex || 0] || item;
  target.scrollIntoView?.({ behavior: "smooth", block: "center" });
  target.focus();
}

function openFollowUpSelection(selection) {
  if (!selection && followUpOpen.value && pendingFollowUp.value) return;
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

function scrollToReportHeading(id) {
  activeHeadingId.value = id;
  reportView.value?.scrollToHeading(id);
}
function moveDossierTab(direction) {
  const current = dossierTabs.value.findIndex((tab) => tab.id === activeDossierTab.value);
  const next = (current + direction + dossierTabs.value.length) % dossierTabs.value.length;
  activeDossierTab.value = dossierTabs.value[next].id;
  requestAnimationFrame(() => document.getElementById(`dossier-tab-${activeDossierTab.value}`)?.focus());
}
function scrollToReportTop() {
  activeHeadingId.value = reportHeadings.value[0]?.id || "";
  reportView.value?.scrollToTop();
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
  const threadId = store.selectedFollowUp?.id || "";
  const hadPersistedThread = Boolean(store.selectedFollowUp);
  const selectionAnchor = pendingFollowUp.value?.anchor || store.selectedFollowUp?.anchor;
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
  await nextTick();
  const marker = threadId
    ? document.querySelector(`[data-follow-up-marker][data-thread-id="${threadId}"]`)
    : null;
  if (marker) marker.focus();
  else if (!reportView.value?.focusAnchor(selectionAnchor)) reportView.value?.focusReport();
}

function updateViewport() {
  windowWidth.value = window.innerWidth;
  windowHeight.value = window.innerHeight;
}

watch(() => store.runId, () => {
  activeDossierTab.value = "report";
  reportHeadings.value = [];
  activeHeadingId.value = "";
  focusedEvidenceId.value = "";
  clearReportInteraction();
});
watch(activeDossierTab, (tab) => {
  if (tab !== "report") clearReportInteraction();
});

onMounted(() => {
  store.loadRuns();
  const initialRunId = new URLSearchParams(window.location.search).get("run");
  if (initialRunId) loadRunFromRoute(initialRunId);
  window.addEventListener("resize", updateViewport);
  window.addEventListener("popstate", handlePopState);
});
onUnmounted(() => {
  store.clearRun();
  clearTimeout(toastTimer);
  window.removeEventListener("resize", updateViewport);
  window.removeEventListener("popstate", handlePopState);
});
</script>

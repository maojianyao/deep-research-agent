<template>
  <div class="min-h-screen bg-slate-50 text-slate-800">
    <aside class="fixed inset-y-0 left-0 z-20 hidden w-[238px] flex-col border-r border-slate-200 bg-white p-4 md:flex">
      <a class="flex items-center gap-3 px-1 py-2 no-underline" href="#">
        <span class="grid h-8 w-8 grid-cols-3 items-end justify-center gap-[3px] rounded-md bg-teal-800 p-2"><i class="h-2 rounded-sm bg-white/70"></i><i class="h-4 rounded-sm bg-white"></i><i class="h-3 rounded-sm bg-white/85"></i></span>
        <span class="text-sm font-bold">知序<span class="mt-0.5 block text-[10px] font-medium text-slate-400">研究工作台</span></span>
      </a>
      <button class="mt-8 flex h-10 items-center gap-2 rounded bg-teal-800 px-3 text-left text-xs font-semibold text-white hover:bg-teal-900" @click="openCreateDialog"><span class="text-lg">＋</span> 新建研究</button>
      <p class="mb-2 mt-8 px-2 text-[10px] font-bold tracking-widest text-slate-400">工作空间</p>
      <button class="flex h-9 items-center gap-2 rounded bg-teal-50 px-2 text-left text-xs font-semibold text-teal-800"><span>▤</span>研究任务<span class="ml-auto text-[10px] text-slate-500">{{ store.total }}</span></button>
      <a class="mt-1 flex h-9 items-center gap-2 rounded px-2 text-xs text-slate-500 hover:bg-slate-50" href="#workflow"><span>⌘</span>工作流结构</a>
      <div class="mt-auto flex items-center gap-2 border-t border-slate-100 px-1 pt-3 text-[10px] text-slate-500">
        <span class="h-2 w-2 rounded-full" :class="store.connection === 'offline' ? 'bg-rose-500' : store.connection === 'stream' ? 'animate-pulse bg-teal-600' : 'bg-emerald-600'"></span>
        {{ connectionLabel }}
        <button class="ml-auto rounded p-1 text-base hover:bg-slate-100" title="刷新研究列表" @click="store.loadRuns()">↻</button>
      </div>
    </aside>

    <div class="md:ml-[238px]">
      <header class="flex h-12 items-center justify-between border-b border-slate-200 bg-white px-4 sm:px-7">
        <div class="flex items-center gap-2 text-[11px] text-slate-400"><span>工作空间</span><span>/</span><strong class="font-semibold text-slate-700">{{ pageTitle }}</strong></div>
        <div class="flex items-center gap-3 text-[10px] text-slate-400"><span class="hidden sm:inline">{{ today }}</span><span class="grid h-7 w-7 place-items-center rounded-full border border-slate-200 bg-slate-50 text-teal-800">研</span></div>
      </header>

      <main class="mx-auto max-w-[1440px] p-4 sm:p-7 lg:px-9">
        <template v-if="!store.runId">
          <div class="mb-6 flex items-center justify-between gap-4">
            <div><p class="text-[9px] font-bold tracking-[.16em] text-teal-800">RESEARCH OPERATIONS</p><h1 class="mt-1 text-2xl font-semibold tracking-normal">研究任务</h1><p class="mt-1 text-xs text-slate-500">从问题出发，追踪每一条证据直到结论。</p></div>
            <button class="shrink-0 rounded bg-teal-800 px-3 py-2 text-[11px] font-semibold text-white hover:bg-teal-900" @click="openCreateDialog"><span class="mr-1">＋</span>新建研究</button>
          </div>

          <section class="mb-6 grid grid-cols-2 overflow-hidden rounded-md border border-slate-200 bg-white lg:grid-cols-4">
            <div class="border-b border-r border-slate-100 p-3.5 lg:border-b-0"><p class="text-[10px] text-slate-500">全部任务</p><strong class="mt-2 block text-2xl font-semibold">{{ store.total }}</strong><p class="mt-1 text-[9px] text-slate-400">研究记录</p></div>
            <div class="border-b border-slate-100 p-3.5 lg:border-b-0 lg:border-r"><p class="text-[10px] text-slate-500">当前页进行中</p><strong class="mt-2 block text-2xl font-semibold">{{ activeCount }}</strong><p class="mt-1 text-[9px] text-amber-700">持续更新</p></div>
            <div class="border-r border-slate-100 p-3.5"><p class="text-[10px] text-slate-500">当前页已完成</p><strong class="mt-2 block text-2xl font-semibold">{{ completedCount }}</strong><p class="mt-1 text-[9px] text-emerald-700">报告可查看</p></div>
            <div class="p-3.5"><p class="text-[10px] text-slate-500">当前页待复核</p><strong class="mt-2 block text-2xl font-semibold">{{ reviewCount }}</strong><p class="mt-1 text-[9px] text-rose-700">需要判断</p></div>
          </section>

          <WorkflowDiagram id="workflow" class="mb-6" />
          <ResearchList @open="openRun" @finish="finishRun" @continue="continueRun" @delete="deleteRun" />
        </template>

        <section v-else>
          <button class="mb-5 text-xs text-teal-800 hover:underline" @click="backToList">← 返回研究任务</button>
          <div v-if="!store.run" class="rounded border border-slate-200 bg-white p-12 text-center text-sm text-slate-500">{{ store.error || "正在读取研究详情…" }}</div>
          <template v-else>
            <div class="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
              <div class="min-w-0"><p class="text-[9px] font-bold tracking-[.14em] text-teal-800">RESEARCH RUN · {{ store.run.id }}</p><h1 class="mt-2 max-w-4xl break-words text-xl font-semibold">{{ store.run.user_request }}</h1><div class="mt-3 flex flex-wrap items-center gap-3 text-[10px] text-slate-500"><span class="rounded px-2 py-1" :class="statusClass(store.run.status)">{{ statusLabel(store.run.status) }}</span><span>第 {{ store.run.iteration }} / {{ store.run.max_iterations }} 轮</span><span>更新于 {{ formatDate(store.run.updated_at) }}</span><span class="text-teal-800">{{ connectionLabel }}</span></div></div>
              <div class="flex shrink-0 gap-2">
                <button v-if="store.isActive" class="rounded border border-amber-200 bg-white px-3 py-2 text-[10px] text-amber-800 hover:bg-amber-50" @click="finishRun(store.run)">结束任务</button>
                <button v-if="store.run.can_resume || ['paused','failed'].includes(store.run.status)" class="rounded border border-teal-200 bg-white px-3 py-2 text-[10px] text-teal-800 hover:bg-teal-50" @click="continueRun(store.run)">继续任务</button>
                <a v-if="store.run.report && store.run.status === 'completed'" class="rounded bg-teal-800 px-3 py-2 text-[10px] font-semibold text-white no-underline hover:bg-teal-900" :href="`/api/research-runs/${store.run.id}/report.md`">↓ 下载报告</a>
              </div>
            </div>

            <div v-if="runError" class="mt-5 rounded border border-rose-200 bg-rose-50 px-4 py-3 text-xs leading-5 text-rose-800" role="alert">
              <p class="font-semibold">研究任务未能完成</p>
              <p class="mt-1 break-words">{{ runError }}</p>
            </div>

            <div class="mt-6 grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_290px]">
              <div class="grid min-w-0 gap-4">
                <section class="rounded-md border border-slate-200 bg-white">
                  <div class="flex items-center justify-between border-b border-slate-100 px-4 py-3"><h2 class="text-xs font-semibold">研究报告</h2><span class="text-[10px] text-slate-400">引用编号可点击查看来源</span></div>
                  <div class="p-4"><ReportView :markdown="store.run.report?.markdown || ''" :active="store.isActive" :eligible="store.run.status === 'completed' && Boolean(store.run.report)" :follow-ups="store.followUps" @citation="showCitation" @selection="openFollowUpSelection" @selection-error="notify($event, true)" @restore-follow-up="restoreFollowUp" /></div>
                </section>

                <details class="overflow-hidden rounded-md border border-slate-200 bg-white">
                  <summary class="flex cursor-pointer list-none items-center justify-between px-4 py-3 marker:hidden hover:bg-slate-50"><h2 class="text-xs font-semibold">研究计划</h2><span class="flex items-center gap-2 text-[10px] text-slate-400">{{ completedTasks }} / {{ store.run.plan?.tasks?.length || 0 }} 项完成 <span class="fold-chevron">⌄</span></span></summary>
                  <div class="fold-scroll h-72 overflow-y-auto overscroll-contain border-t border-slate-100 p-4">
                    <template v-if="store.run.plan"><p class="text-sm font-semibold leading-6">{{ store.run.plan.research_question }}</p><p class="mt-1 text-xs leading-5 text-slate-500">{{ store.run.plan.scope }}</p>
                      <div class="mt-4 grid gap-2"><article v-for="task in store.run.plan.tasks" :key="task.id" class="grid grid-cols-[18px_minmax(0,1fr)_auto] items-start gap-2 rounded border border-slate-100 p-2.5"><span class="grid h-4 w-4 place-items-center rounded-full text-[10px]" :class="task.completed ? 'bg-emerald-50 text-emerald-800' : 'bg-amber-50 text-amber-700'">{{ task.completed ? '✓' : '·' }}</span><div class="text-[11px] leading-5 text-slate-600">{{ task.question }}<p v-if="task.acceptance_criteria?.length" class="mt-1 text-[10px] text-slate-400">验收：{{ task.acceptance_criteria.join('；') }}</p></div><span class="text-[9px] text-slate-400">{{ task.task_type }} · {{ task.priority }}</span></article></div>
                    </template><p v-else class="text-xs text-slate-500">研究计划生成后会显示。</p>
                  </div>
                </details>

                <details class="overflow-hidden rounded-md border border-slate-200 bg-white">
                  <summary class="flex cursor-pointer list-none items-center justify-between px-4 py-3 marker:hidden hover:bg-slate-50"><h2 class="text-xs font-semibold">综合结论</h2><span class="flex items-center gap-2 text-[10px] text-slate-400">{{ store.run.findings.length }} 条 <span class="fold-chevron">⌄</span></span></summary>
                  <div class="fold-scroll h-72 divide-y divide-slate-100 overflow-y-auto overscroll-contain border-t border-slate-100 px-4"><article v-for="finding in store.run.findings" :key="finding.id" class="py-3"><div class="flex items-center justify-between gap-2"><button class="rounded border border-slate-200 bg-slate-50 px-2 py-1 text-[9px] text-teal-800" @click="showCitation(finding.id)">{{ finding.classification }} · {{ finding.id }}</button><span class="text-[9px] text-slate-400">置信度 {{ Math.round(finding.confidence * 100) }}%</span></div><p class="my-2 text-[11px] leading-6 text-slate-600">{{ finding.statement }}</p><div class="flex flex-wrap gap-1.5"><button v-for="id in finding.evidence_ids" :key="id" class="rounded border border-slate-200 px-1.5 py-1 text-[9px] text-teal-800 hover:bg-teal-50" @click="showCitation(id)">{{ id }}</button></div></article><p v-if="!store.run.findings.length" class="py-5 text-xs text-slate-500">当前还没有已综合的结论。</p></div>
                </details>

                <details class="overflow-hidden rounded-md border border-slate-200 bg-white">
                  <summary class="flex cursor-pointer list-none items-center justify-between px-4 py-3 marker:hidden hover:bg-slate-50"><h2 class="text-xs font-semibold">审稿意见</h2><span class="flex items-center gap-2 text-[10px] text-slate-400">{{ store.run.critiques.length }} 轮 <span class="fold-chevron">⌄</span></span></summary>
                  <div class="fold-scroll h-72 divide-y divide-slate-100 overflow-y-auto overscroll-contain border-t border-slate-100 px-4"><article v-for="review in store.run.critiques" :key="review.iteration" class="py-3"><div class="flex items-center justify-between"><span class="rounded px-2 py-1 text-[9px]" :class="review.decision === 'approve' ? 'bg-emerald-50 text-emerald-800' : 'bg-amber-50 text-amber-800'">{{ review.decision === 'approve' ? '通过' : review.decision === 'research_more' ? '要求补证' : '人工复核' }}</span><span class="text-[9px] text-slate-400">第 {{ review.iteration }} 轮</span></div><p v-for="(issue,index) in review.issues" :key="index" class="mt-2 text-[11px] leading-5 text-slate-600"><strong>{{ issue.severity }}</strong> · {{ issue.problem }} <button v-if="issue.finding_id" class="text-[9px] text-teal-800 underline" @click="showCitation(issue.finding_id)">{{ issue.finding_id }}</button></p></article><p v-if="!store.run.critiques.length" class="py-5 text-xs text-slate-500">研究审稿后会在此显示意见。</p></div>
                </details>
              </div>

              <aside class="grid gap-4">
                <section class="rounded-md border border-slate-200 bg-white p-4"><div class="flex items-center justify-between"><h2 class="text-xs font-semibold">研究进度</h2><span class="text-xs text-teal-800">{{ progress }}%</span></div><div class="mt-3 h-1.5 overflow-hidden rounded bg-slate-100"><div class="h-full rounded bg-teal-700 transition-all" :style="{ width: `${progress}%` }"></div></div><p class="mt-2 text-[10px] text-slate-500">第 {{ store.run.iteration }} 轮，共 {{ store.run.max_iterations }} 轮</p></section>
                <section class="rounded-md border border-slate-200 bg-white"><div class="flex items-center justify-between border-b border-slate-100 px-4 py-3"><h2 class="text-xs font-semibold">活动记录</h2><span class="text-[9px] text-slate-400">{{ store.run.events.length }} 条</span></div><div class="grid gap-3 p-4"><article v-for="event in [...store.run.events].slice(-10).reverse()" :key="event.sequence" class="grid grid-cols-[8px_1fr] gap-2 text-[10px] leading-5 text-slate-600"><span class="mt-1.5 h-1.5 w-1.5 rounded-full bg-teal-600"></span><div>{{ event.message }}<time class="block text-[9px] text-slate-400">{{ formatDate(event.created_at) }}</time></div></article><p v-if="!store.run.events.length" class="text-xs text-slate-500">暂无活动记录</p></div></section>
                <section class="rounded-md border border-slate-200 bg-white"><div class="flex items-center justify-between border-b border-slate-100 px-4 py-3"><h2 class="text-xs font-semibold">审查通过的证据</h2><span class="text-[9px] text-slate-400">{{ store.run.evidence.length }} 条</span></div><div class="divide-y divide-slate-100 px-4"><article v-for="item in store.run.evidence.slice(0,10)" :key="item.id" class="py-3"><p class="mb-1.5 text-[10px] leading-5 text-slate-600">{{ item.claim }}</p><a class="block break-all text-[10px] text-teal-800 hover:underline" :href="item.source.url" target="_blank" rel="noopener noreferrer">↗ {{ item.source.title }}</a><p class="mt-1 text-[9px] text-slate-400">{{ item.source.publisher || item.source.source_type }} · {{ Math.round(item.confidence * 100) }}%</p><button class="mt-1 text-[9px] text-teal-800 underline" @click="showCitation(item.id)">{{ item.id }}</button></article><p v-if="!store.run.evidence.length" class="py-4 text-xs text-slate-500">证据审查后会在此显示。</p></div></section>
              </aside>
            </div>
          </template>
        </section>
      </main>
    </div>

    <dialog ref="createDialog" class="fixed left-1/2 top-1/2 m-0 max-h-[85vh] w-[min(560px,calc(100vw-24px))] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-md border border-slate-200 p-0 shadow-2xl backdrop:bg-slate-900/50">
      <form class="p-5" @submit.prevent="submitResearch"><div class="mb-4 flex items-start justify-between"><div><p class="text-[10px] font-semibold tracking-widest text-teal-700">NEW RESEARCH</p><h2 class="mt-1 text-lg font-semibold">发起一项研究</h2></div><button type="button" class="rounded px-2 text-xl text-slate-500 hover:bg-slate-100" aria-label="关闭" @click="closeCreateDialog">×</button></div>
        <label for="topic" class="mb-2 block text-xs font-semibold text-slate-600">研究主题或问题</label><textarea id="topic" v-model="topic" maxlength="2000" required class="min-h-32 w-full resize-y rounded border border-slate-200 p-3 text-xs leading-6 outline-none focus:border-teal-700" placeholder="例如：评估某项政策对中小企业创新投入的影响，重点关注实施机制、效果证据与地区差异。"></textarea><div class="mt-1 flex justify-between text-[9px] text-slate-400"><span>支持技术、商业、政策、科学、人物/事件等主题</span><span>{{ topic.length }} / 2000</span></div>
        <label for="iterations" class="mb-2 mt-4 block text-xs font-semibold text-slate-600">最大研究轮次</label><select id="iterations" v-model.number="iterations" class="h-9 w-full rounded border border-slate-200 bg-white px-3 text-xs"><option v-for="count in 5" :key="count" :value="count">{{ count }} 轮</option></select>
        <div class="mt-5 flex justify-end gap-2"><button type="button" class="rounded border border-slate-200 px-3 py-2 text-[11px]" @click="closeCreateDialog">取消</button><button class="rounded bg-teal-800 px-3 py-2 text-[11px] font-semibold text-white disabled:opacity-50" :disabled="creating">{{ creating ? '正在提交…' : '开始研究 →' }}</button></div>
      </form>
    </dialog>

    <CitationDialog ref="citationDialog" :sources="citationSources" :finding-statement="findingStatement" :loading="citationLoading" />
    <button
      v-if="pendingFollowUp"
      data-follow-up-trigger
      type="button"
      class="fixed z-30 rounded bg-amber-600 px-2.5 py-1.5 text-[10px] font-semibold text-white shadow-lg hover:bg-amber-700"
      :style="{ left: `${Math.max(8, Math.min(pendingFollowUp.position.x + 8, windowWidth - 64))}px`, top: `${Math.max(8, Math.min(pendingFollowUp.position.y + 8, windowHeight - 44))}px` }"
      @mousedown.prevent
      @click="openFollowUpPanel"
    >提问</button>
    <FollowUpPanel
      v-if="followUpOpen || store.selectedFollowUp"
      :passage="pendingFollowUp?.anchor.text || store.selectedFollowUp?.anchor.text || ''"
      :messages="store.selectedFollowUp?.messages || []"
      :busy="followUpBusy"
      :error="followUpError"
      @submit="submitFollowUp"
      @retry="retryFollowUp"
      @close="closeFollowUp"
    />
    <div v-if="toastMessage" class="fixed bottom-5 right-5 z-50 max-w-sm rounded border border-slate-200 bg-white px-4 py-3 text-xs shadow-xl" :class="toastError ? 'text-rose-700' : 'text-slate-700'" role="status">{{ toastMessage }}</div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
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
const iterations = ref(3);
const creating = ref(false);
const toastMessage = ref("");
const toastError = ref(false);
let toastTimer;

const pageTitle = computed(() => store.run?.user_request || "研究任务");
const activeCount = computed(() => store.runs.filter((item) => !["completed", "failed", "cancelled", "needs_human_review", "paused"].includes(item.status)).length);
const completedCount = computed(() => store.runs.filter((item) => item.status === "completed").length);
const reviewCount = computed(() => store.runs.filter((item) => item.status === "needs_human_review").length);
const completedTasks = computed(() => store.run?.plan?.tasks?.filter((task) => task.completed).length || 0);
const runError = computed(() => store.run?.error || "");
const followUpBusy = computed(() => followUpSubmitting.value || store.selectedFollowUpBusy);
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
  if (status === "completed") return "bg-emerald-50 text-emerald-800";
  if (["failed", "needs_human_review"].includes(status)) return "bg-rose-50 text-rose-800";
  if (["planning", "researching", "reviewing_evidence", "synthesizing", "critic_review", "writing"].includes(status)) return "bg-amber-50 text-amber-800";
  if (status === "paused") return "bg-sky-50 text-sky-800";
  return "bg-slate-100 text-slate-600";
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
    await store.createRun(topic.value.trim(), iterations.value);
    topic.value = "";
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
  if (!window.confirm(`确定删除研究主题“${run.user_request}”吗？计划、证据、结论、审稿记录和报告都会一并删除，此操作不可撤销。`)) return;
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

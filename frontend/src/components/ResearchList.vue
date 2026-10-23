<template>
  <section class="research-register">
    <header class="register-heading">
      <div>
        <h2 class="register-title">研究档案</h2>
        <p class="section-note">查看研究状态、结论与证据来源。</p>
      </div>
      <span class="register-count">共 {{ store.total }} 项</span>
    </header>

    <div class="register-toolbar">
      <label class="register-search">
        <span aria-hidden="true">⌕</span>
        <input
          type="search"
          placeholder="搜索研究主题"
          :value="store.search"
          @input="store.setSearch($event.target.value)"
        />
      </label>
      <div class="register-controls">
        <label class="sort-control">
          <span>排序</span>
          <select
            aria-label="研究档案排序"
            :value="store.sort"
            @change="store.selectSort($event.target.value)"
          >
            <option value="updated_desc">最近更新</option>
            <option value="updated_asc">最早更新</option>
          </select>
        </label>
        <div class="filter-strip" aria-label="研究状态筛选">
          <button
            v-for="filter in filters"
            :key="filter.label"
            class="filter-button"
            :class="{ 'is-active': store.statusFilter === filter.value }"
            :aria-pressed="store.statusFilter === filter.value"
            @click="store.selectStatus(filter.value)"
          >{{ filter.label }}</button>
        </div>
      </div>
    </div>

    <div class="register-table-shell">
      <table class="register-table">
        <thead>
          <tr>
            <th>研究主题</th>
            <th>状态</th>
            <th>进度</th>
            <th>更新时间</th>
            <th class="text-right">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="run in store.runs"
            :key="run.id"
            class="research-row"
            tabindex="0"
            @click="openRow($event, run.id)"
            @keydown.enter.self="openRow($event, run.id)"
          >
            <td data-label="研究主题">
              <p class="topic-title">{{ run.title || run.research_question || run.user_request }}</p>
              <p class="topic-request">{{ run.user_request }}</p>
              <span class="topic-language">{{ run.report_language_name }} / {{ run.report_language }}</span>
            </td>
            <td data-label="状态"><span class="status-pill" :class="statusTone(run.status)">{{ statusText(run.status) }}</span></td>
            <td data-label="进度" class="w-40">
              <div class="table-progress-label"><span>第 {{ run.iteration }} / {{ run.max_iterations }} 轮</span><span>{{ progress(run) }}%</span></div>
              <div class="table-progress"><span :style="{ width: `${progress(run)}%` }"></span></div>
            </td>
            <td data-label="更新时间" class="whitespace-nowrap">{{ dateText(run.updated_at) }}</td>
            <td data-label="操作">
              <div class="row-actions">
                <button class="line-action" @click.stop="$emit('open', run.id)">查看</button>
                <button v-if="isActive(run.status)" class="line-action is-warning" @click.stop="$emit('finish', run)">结束任务</button>
                <button v-else-if="run.status === 'needs_human_review'" class="line-action is-warning" @click.stop="$emit('open', run.id)">查看待复核</button>
                <button v-else-if="run.can_resume || canContinue(run)" class="line-action" @click.stop="$emit('continue', run)">继续任务</button>
                <a v-if="run.has_report" class="line-action" :href="`/api/research-runs/${run.id}/report.md`" @click.stop>下载</a>
                <details class="row-menu" @click.stop>
                  <summary :aria-label="`更多操作：${run.title || run.user_request}`">•••</summary>
                  <button
                    class="line-action is-danger"
                    :disabled="isActive(run.status)"
                    :title="isActive(run.status) ? '请先结束正在执行的任务' : '删除该研究记录及其关联数据'"
                    @click.stop="$emit('delete', run)"
                  >删除</button>
                </details>
              </div>
            </td>
          </tr>
          <tr v-if="!store.runs.length">
            <td colspan="5" class="py-12 text-center">
              <p class="empty-note">{{ store.loading ? "正在读取研究记录…" : store.error || "还没有研究记录。发起第一项研究，开始建立证据链。" }}</p>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="register-footer">
      <span>第 {{ store.page }} / {{ store.pageCount }} 页</span>
      <div>
        <button class="line-action" :disabled="store.page <= 1" @click="store.selectPage(store.page - 1)">上一页</button>
        <button class="line-action" :disabled="store.page >= store.pageCount" @click="store.selectPage(store.page + 1)">下一页</button>
      </div>
    </div>
  </section>
</template>

<script setup>
import { useResearchStore } from "../stores/research";

const store = useResearchStore();
const emit = defineEmits(["open", "finish", "continue", "delete"]);

const filters = [
  { label: "全部", value: "" },
  { label: "进行中", value: "active" },
  { label: "已完成", value: "completed" },
  { label: "待复核", value: "needs_human_review" },
];
const statuses = {
  planning: "规划中",
  researching: "研究中",
  reviewing_evidence: "审查中",
  synthesizing: "综合中",
  critic_review: "反方审阅",
  writing: "撰写报告",
  paused: "已暂停",
  completed: "已完成",
  needs_human_review: "待复核",
  failed: "失败",
  cancelled: "已结束",
};
const statusText = (status) => statuses[status] || status;
const isActive = (status) => !["paused", "completed", "failed", "needs_human_review", "cancelled"].includes(status);
const canContinue = (run) => run.can_resume || ["paused", "failed"].includes(run.status);
const openRow = (event, runId) => {
  if (event.target.closest("button, a, summary, details, input, select")) return;
  emit("open", runId);
};
const statusTone = (status) => {
  if (status === "completed") return "is-complete";
  if (["needs_human_review", "failed"].includes(status)) return "is-alert";
  if (["planning", "researching", "reviewing_evidence", "synthesizing", "critic_review", "writing"].includes(status)) return "is-progress";
  if (status === "paused") return "is-paused";
  return "is-muted";
};
const progress = (run) => run.status === "completed" ? 100 : Math.min(94, Math.round(run.iteration / Math.max(1, run.max_iterations) * 100));
const dateText = (value) => value ? new Date(value).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—";
</script>

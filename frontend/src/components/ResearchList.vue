<template>
  <section>
    <div class="mb-3 flex items-end justify-between">
      <div><h2 class="text-sm font-semibold text-slate-800">研究记录</h2><p class="mt-1 text-xs text-slate-500">查看状态、研究结论与证据链</p></div>
      <span class="text-xs text-slate-500">共 {{ store.total }} 项</span>
    </div>
    <div class="mb-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <label class="flex h-9 min-w-0 items-center gap-2 rounded border border-slate-200 bg-white px-3 text-slate-400 sm:w-72">
        <span aria-hidden="true">⌕</span><input class="min-w-0 flex-1 bg-transparent text-xs text-slate-700 outline-none placeholder:text-slate-400" type="search" placeholder="搜索研究主题" :value="store.search" @input="store.setSearch($event.target.value)" />
      </label>
      <div class="flex w-fit gap-1 rounded border border-slate-200 bg-slate-100 p-1">
        <button v-for="filter in filters" :key="filter.label" class="rounded px-3 py-1.5 text-[11px]" :class="store.statusFilter === filter.value ? 'bg-white font-semibold text-slate-800 shadow-sm' : 'text-slate-500'" @click="store.selectStatus(filter.value)">{{ filter.label }}</button>
      </div>
    </div>
    <div class="overflow-x-auto rounded border border-slate-200 bg-white">
      <table class="w-full min-w-[700px] text-left">
        <thead class="border-b border-slate-200 bg-slate-50 text-[10px] font-medium text-slate-500"><tr><th class="px-3 py-3">研究主题</th><th class="px-3 py-3">状态</th><th class="px-3 py-3">进度</th><th class="px-3 py-3">更新时间</th><th class="px-3 py-3 text-right">操作</th></tr></thead>
        <tbody class="divide-y divide-slate-100 text-xs text-slate-600">
          <tr v-for="run in store.runs" :key="run.id" class="hover:bg-slate-50">
            <td class="max-w-[440px] px-3 py-3"><p class="truncate font-semibold text-slate-800">{{ run.title || run.research_question || run.user_request }}</p><p class="mt-1 truncate text-[10px] text-slate-400">{{ run.user_request }}</p></td>
            <td class="px-3 py-3"><span class="rounded px-2 py-1 text-[10px]" :class="statusClass(run.status)">{{ statusText(run.status) }}</span></td>
            <td class="w-40 px-3 py-3"><div class="flex justify-between text-[10px] text-slate-500"><span>第 {{ run.iteration }}/{{ run.max_iterations }} 轮</span><span>{{ progress(run) }}%</span></div><div class="mt-1.5 h-1 overflow-hidden rounded bg-slate-100"><div class="h-full rounded bg-teal-700" :style="{ width: `${progress(run)}%` }"></div></div></td>
            <td class="whitespace-nowrap px-3 py-3 text-[10px]">{{ dateText(run.updated_at) }}</td>
            <td class="px-3 py-3"><div class="flex justify-end gap-1.5">
              <button class="rounded border border-slate-200 px-2.5 py-1.5 text-[10px] hover:border-teal-700 hover:text-teal-800" @click="$emit('open', run.id)">查看</button>
              <button v-if="isActive(run.status)" class="rounded border border-amber-200 px-2.5 py-1.5 text-[10px] text-amber-800 hover:bg-amber-50" @click="$emit('finish', run)">结束任务</button>
              <button v-else-if="run.can_resume || canContinue(run)" class="rounded border border-teal-200 px-2.5 py-1.5 text-[10px] text-teal-800 hover:bg-teal-50" @click="$emit('continue', run)">继续任务</button>
              <button class="rounded border border-rose-200 px-2.5 py-1.5 text-[10px] text-rose-700 hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-40" :disabled="isActive(run.status)" :title="isActive(run.status) ? '请先结束正在执行的任务' : '删除该研究记录及其关联数据'" @click="$emit('delete', run)">删除</button>
            </div></td>
          </tr>
          <tr v-if="!store.runs.length"><td colspan="5" class="py-12 text-center text-xs text-slate-500">{{ store.loading ? "正在读取研究记录…" : store.error || "暂无符合条件的研究记录" }}</td></tr>
        </tbody>
      </table>
      <div class="flex items-center justify-between border-t border-slate-100 px-3 py-2 text-[10px] text-slate-500">
        <span>第 {{ store.page }} / {{ store.pageCount }} 页</span>
        <div class="flex gap-2"><button class="rounded border border-slate-200 px-2 py-1 disabled:opacity-40" :disabled="store.page <= 1" @click="store.selectPage(store.page - 1)">上一页</button><button class="rounded border border-slate-200 px-2 py-1 disabled:opacity-40" :disabled="store.page >= store.pageCount" @click="store.selectPage(store.page + 1)">下一页</button></div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { useResearchStore } from "../stores/research";
const store = useResearchStore();
defineEmits(["open", "finish", "continue", "delete"]);
const filters = [{ label: "全部", value: "" }, { label: "进行中", value: "researching" }, { label: "已完成", value: "completed" }, { label: "待复核", value: "needs_human_review" }];
const statuses = { planning: "规划中", researching: "研究中", reviewing_evidence: "审查中", synthesizing: "综合中", critic_review: "反方审阅", writing: "撰写报告", paused: "已暂停", completed: "已完成", needs_human_review: "待复核", failed: "失败", cancelled: "已结束" };
const statusText = (status) => statuses[status] || status;
const isActive = (status) => !["paused", "completed", "failed", "needs_human_review", "cancelled"].includes(status);
const canContinue = (run) => run.can_resume || ["paused", "failed"].includes(run.status);
const statusClass = (status) => status === "completed" ? "bg-emerald-50 text-emerald-800" : status === "needs_human_review" || status === "failed" ? "bg-rose-50 text-rose-800" : ["planning", "researching", "reviewing_evidence", "synthesizing", "critic_review", "writing"].includes(status) ? "bg-amber-50 text-amber-800" : status === "paused" ? "bg-sky-50 text-sky-800" : "bg-slate-100 text-slate-600";
const progress = (run) => run.status === "completed" ? 100 : Math.min(94, Math.round(run.iteration / Math.max(1, run.max_iterations) * 100));
const dateText = (value) => value ? new Date(value).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—";
</script>

<template>
  <section class="margin-card stage-card">
    <div class="margin-card-head">
      <h2>研究阶段</h2>
      <span>{{ statusLabel }}</span>
    </div>
    <div class="stage-current">
      <span>当前阶段</span>
      <strong data-current-stage>{{ currentStage.label }}</strong>
      <small v-if="supplementalRound" data-supplemental-round class="stage-supplemental">
        第 {{ run.iteration }} 轮补证
      </small>
    </div>
    <ol class="stage-list" aria-label="研究阶段">
      <li
        v-for="stage in stages"
        :key="stage.id"
        :data-stage-state="stage.state"
        :class="`is-${stage.state}`"
      >
        <span class="stage-dot" aria-hidden="true"></span>
        <span>{{ stage.label }}</span>
        <small>{{ stage.stateLabel }}</small>
      </li>
    </ol>
    <dl class="stage-facts">
      <div><dt>研究任务</dt><dd>已完成 {{ completedTasks }} / {{ totalTasks }} 项研究任务</dd></div>
      <div><dt>最近更新</dt><dd>{{ formatDate(run.updated_at) }}</dd></div>
    </dl>
    <div v-if="latestEvent" class="stage-latest">
      <span>{{ currentWorkLabel }}</span>
      <p>{{ latestEvent.message }}</p>
    </div>
    <p class="stage-next">{{ nextAction }}</p>
  </section>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  run: { type: Object, required: true },
});

const definitions = [
  { id: "scope", label: "界定问题", description: "主题、范围与目标" },
  { id: "plan", label: "拆解任务", description: "形成检索与验收标准" },
  { id: "collect", label: "跨源检索", description: "并行搜索与抓取来源" },
  { id: "verify", label: "核验证据", description: "筛选可支持结论的来源" },
  { id: "synthesize", label: "综合反审", description: "综合结论与补证复审" },
  { id: "write", label: "形成报告", description: "写作与引用校验" },
];

const statusIndexes = {
  planning: 1,
  researching: 2,
  reviewing_evidence: 3,
  synthesizing: 4,
  critic_review: 4,
  writing: 5,
  completed: 6,
  paused: 0,
  failed: 0,
  needs_human_review: 4,
  cancelled: 0,
};

const effectiveStatus = computed(() => {
  if (["paused", "failed"].includes(props.run.status) && props.run.resume_status) {
    return props.run.resume_status;
  }
  if (props.run.status === "needs_human_review") {
    if (props.run.report) return "writing";
    if (props.run.findings?.length) return "critic_review";
    if (props.run.plan?.tasks?.length) return "researching";
  }
  return props.run.status;
});
const activeIndex = computed(() => statusIndexes[effectiveStatus.value] ?? 1);
const allComplete = computed(() => props.run.status === "completed");
const currentStage = computed(() => definitions[
  Math.min(activeIndex.value, definitions.length - 1)
]);
const supplementalRound = computed(() => (
  !["completed", "failed", "needs_human_review", "cancelled"].includes(props.run.status)
  && (props.run.events || []).some((event) => /补证|补充检索/.test(event.message))
));
const totalTasks = computed(() => props.run.plan?.tasks?.length || 0);
const completedTasks = computed(
  () => props.run.plan?.tasks?.filter((task) => task.completed).length || 0,
);
const latestEvent = computed(() => [...(props.run.events || [])].at(-1) || null);
const currentWorkLabel = computed(() => (
  ["paused", "failed", "needs_human_review", "cancelled", "completed"].includes(
    props.run.status,
  ) ? "最近动态" : "当前工作"
));
const stages = computed(() => definitions.map((stage, index) => {
  let state = "pending";
  if (allComplete.value || index < activeIndex.value) state = "complete";
  else if (index === activeIndex.value) state = "active";
  return {
    ...stage,
    state,
    stateLabel: { complete: "已完成", active: "当前", pending: "待开始" }[state],
  };
}));
const statusLabel = computed(() => ({
  planning: "规划中",
  researching: "研究中",
  reviewing_evidence: "核验证据",
  synthesizing: "综合中",
  critic_review: "反方审阅",
  writing: "撰写报告",
  paused: "已暂停",
  completed: "报告已完成",
  needs_human_review: "待人工复核",
  failed: "执行失败",
  cancelled: "已结束",
}[props.run.status] || props.run.status));
const nextAction = computed(() => {
  if (props.run.status === "completed") return "查看或下载报告";
  if (props.run.status === "paused") return "继续任务后从当前阶段恢复";
  if (props.run.status === "failed") return "查看失败原因并决定是否继续任务";
  if (props.run.status === "needs_human_review") return "检查待复核问题后决定是否继续任务";
  if (props.run.status === "cancelled") return "任务已结束，记录仍可查阅";
  return "可结束任务，或等待研究自动更新";
});

function formatDate(value) {
  return value
    ? new Date(value).toLocaleString("zh-CN", {
      month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
    })
    : "—";
}
</script>

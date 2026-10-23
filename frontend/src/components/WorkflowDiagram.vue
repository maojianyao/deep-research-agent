<template>
  <section class="workflow-board">
    <div class="section-title-row">
      <div>
        <h2 class="section-title">研究如何推进</h2>
        <p class="section-note">问题先被拆成可检索任务，再经过证据审查与反方复核，最后进入写作。</p>
      </div>
    </div>
    <ol class="workflow-track" aria-label="深度研究流程">
      <li
        v-for="node in nodes"
        :key="node.number"
        class="workflow-step"
        :class="node.tone"
      >
        <span class="workflow-node">{{ node.number }}</span>
        <p class="workflow-name">{{ node.title }}</p>
        <p class="workflow-agent">{{ node.subtitle }}</p>
      </li>
    </ol>
    <p class="workflow-loop">证据不足时，Critic 会把缺口退回 Planner，继续补证</p>
  </section>
</template>

<script setup>
const nodes = [
  { number: "1", title: "界定问题", subtitle: "主题、范围与目标" },
  { number: "2", title: "拆解任务", subtitle: "Planner" },
  { number: "3", title: "跨源检索", subtitle: "Researcher", tone: "is-mid" },
  { number: "4", title: "核验证据", subtitle: "Reviewer", tone: "is-mid" },
  { number: "5", title: "综合反审", subtitle: "Synthesizer / Critic", tone: "is-mid" },
  { number: "6", title: "形成报告", subtitle: "Writer / 引用校验", tone: "is-write" },
];
</script>

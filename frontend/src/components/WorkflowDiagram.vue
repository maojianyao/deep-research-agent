<template>
  <section class="rounded-md border border-slate-200 bg-white p-4">
    <div class="mb-3 flex items-center justify-between">
      <div><h2 class="text-sm font-semibold text-slate-800">研究流程</h2><p class="mt-1 text-xs text-slate-500">从问题到可追溯报告</p></div>
      <span class="text-[10px] tracking-widest text-slate-400">MULTI-AGENT PIPELINE</span>
    </div>
    <div class="overflow-x-auto">
      <svg class="min-w-[760px]" viewBox="0 0 1060 158" role="img" aria-label="提出问题、规划任务、并行检索、证据审查、综合反审、报告生成的研究流程图">
        <defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto"><path d="M0 0L8 4L0 8" fill="none" stroke="#a7b2bd" stroke-width="1.4"/></marker></defs>
        <path d="M150 72H205M332 72H384M510 72H562M688 72H740M866 72H916" stroke="#a7b2bd" stroke-width="1.5" marker-end="url(#arrow)"/>
        <path d="M626 98V132H770V98" fill="none" stroke="#c5ccd4" stroke-width="1.2" stroke-dasharray="4 4" marker-end="url(#arrow)"/>
        <g v-for="node in nodes" :key="node.number">
          <rect :x="node.x" y="32" :width="node.width" height="78" rx="5" :fill="node.fill" :stroke="node.stroke"/>
          <circle :cx="node.x + 23" cy="55" r="11" :fill="node.bubble"/>
          <text :x="node.x + 23" y="59" text-anchor="middle" :fill="node.accent" font-size="11">{{ node.number }}</text>
          <text :x="node.x + 14" y="84" fill="#273746" font-size="14" font-weight="600">{{ node.title }}</text>
          <text :x="node.x + 14" y="100" fill="#7a8792" font-size="10">{{ node.subtitle }}</text>
        </g>
        <text x="700" y="148" fill="#8b969f" font-size="10">补证循环</text>
      </svg>
    </div>
  </section>
</template>

<script setup>
const nodes = [
  { number: "01", x: 8, width: 142, title: "提出问题", subtitle: "主题 · 范围 · 目标", fill: "#f0f4f8", stroke: "#d8e0e8", bubble: "#dce7f1", accent: "#3a617d" },
  { number: "02", x: 206, width: 126, title: "规划任务", subtitle: "Planner", fill: "#f0f4f8", stroke: "#d8e0e8", bubble: "#dce7f1", accent: "#3a617d" },
  { number: "03", x: 385, width: 126, title: "并行检索", subtitle: "Researcher", fill: "#eef5f4", stroke: "#d3e4e0", bubble: "#d7e9e4", accent: "#32756d" },
  { number: "04", x: 563, width: 126, title: "证据审查", subtitle: "Reviewer", fill: "#f8f4eb", stroke: "#e9dfca", bubble: "#eee4cc", accent: "#9c7130" },
  { number: "05", x: 741, width: 126, title: "综合 · 反审", subtitle: "Synthesizer · Critic", fill: "#f8f1ed", stroke: "#e8d8ce", bubble: "#eeddd3", accent: "#ad6042" },
  { number: "06", x: 917, width: 135, title: "报告生成", subtitle: "Writer · 引用校验", fill: "#f0f4f8", stroke: "#d8e0e8", bubble: "#dce7f1", accent: "#3a617d" },
];
</script>

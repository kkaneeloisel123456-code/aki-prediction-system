<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { api } from '../api/client'
import type { DashboardDemo } from '../api/types'
const data = ref<DashboardDemo | null>(null)
onMounted(() => { api.dashboard().then((d: import('../api/types').DashboardDemo) => { data.value = d }).catch(() => {}) })
const maxCases = computed(() => data.value ? Math.max(...data.value.trend.totalCases) : 1)
const COLORS = ['#38bdf8', '#4ade80', '#fbbf24', '#a78bfa', '#f87171']
const totalDeptCases = computed(() => data.value ? data.value.departments.reduce((s, d) => s + d.cases, 0) : 1)
</script>
<template>
  <h2 class="page-title">管理仪表盘</h2>
  <p class="page-subtitle">医院管理视角：AKI 发生率趋势、科室分布（演示数据）</p>
  <div class="kpi-grid" v-if="data">
    <div class="kpi-card"><div class="kpi-label">本月病例数</div><div class="kpi-value">{{ data!.trend.totalCases[data!.trend.months.length-1] }}</div><div class="kpi-delta positive">↑ 示例</div></div>
    <div class="kpi-card"><div class="kpi-label">本月 AKI 发生率</div><div class="kpi-value">{{ data.akiRate }}%</div><div class="kpi-delta positive">125 / 420</div></div>
    <div class="kpi-card"><div class="kpi-label">模型 AUC</div><div class="kpi-value">0.810</div><div class="kpi-delta neutral">50次嵌套CV</div></div>
    <div class="kpi-card"><div class="kpi-label">在线服务</div><div class="kpi-value" style="font-size:18px">Active</div><div class="kpi-delta neutral">演示</div></div>
  </div>
  <div class="grid-2" v-if="data">
    <div class="card">
      <div class="card-header"><span class="card-title">AKI 发生率趋势</span></div>
      <div class="card-body">
        <svg viewBox="0 0 500 220" style="width:100%;height:auto">
          <polyline :points="data!.trend.months.map((_: string, i: number)=>`${30+i*49},${190-data!.trend.akiRates[i]*4}`).join(' ')" fill="none" stroke="#38bdf8" stroke-width="2.5" />
          <g fill="#38bdf8"><circle v-for="(m,i) in data!.trend.months" :key="i" :cx="30+i*49" :cy="190-data!.trend.akiRates[i]*4" r="4" /></g>
          <g fill="#94a3b8" font-size="9"><text v-for="(m,i) in data!.trend.months" :key="i" :x="30+i*49" :y="212" text-anchor="middle">{{ m.slice(5) }}</text></g>
        </svg>
      </div>
    </div>
    <div class="card">
      <div class="card-header"><span class="card-title">科室手术量分布</span></div>
      <div class="card-body">
        <div v-for="(d,i) in data.departments" :key="d.name" style="margin-bottom:10px">
          <div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:3px"><span style="color:var(--text)">{{ d.name }}</span><span class="muted">{{ d.cases }} 例 · {{ d.akiRate }}%</span></div>
          <div style="height:8px;background:#1e293b;border-radius:4px;overflow:hidden"><div :style="{width:(d.cases/totalDeptCases*100)+'%',height:'100%',background:COLORS[i%5]}"></div></div>
        </div>
      </div>
    </div>
  </div>
  <p class="muted" v-if="data" style="margin-top:8px">本页图表为演示数据，不代表真实科室统计；实际部署后可接入医院信息系统。</p>
</template>

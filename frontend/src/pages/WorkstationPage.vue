<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '../api/client'
import type { CohortResponse } from '../api/types'
const cohort = ref<CohortResponse | null>(null)
const csvResult = ref('')
const busy = ref(false)
onMounted(() => { api.cohort().then(c => cohort.value = c).catch(() => {}) })
async function onUpload(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0]; if (!f) return
  busy.value = true
  try { const blob = await api.csvUpload(f); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = 'AKI_batch.csv'; a.click(); URL.revokeObjectURL(url); csvResult.value = `已预测：${f.name}` } finally { busy.value = false }
}
const color = (r: string) => r === '高' ? 'var(--red)' : r === '中' ? 'var(--yellow)' : 'var(--green)'
</script>
<template>
  <h2 class="page-title">医生工作台</h2>
  <p class="page-subtitle">患者列表 + 批量风险评估（演示数据，预测使用真实模型）</p>
  <div class="kpi-grid" style="grid-template-columns:repeat(3,1fr)">
    <div class="kpi-card"><div class="kpi-label">高风险</div><div class="kpi-value" :style="{ color: 'var(--red)' }">{{ cohort?.summary.high ?? 0 }}</div></div>
    <div class="kpi-card"><div class="kpi-label">中风险</div><div class="kpi-value" :style="{ color: 'var(--yellow)' }">{{ cohort?.summary.mid ?? 0 }}</div></div>
    <div class="kpi-card"><div class="kpi-label">低风险</div><div class="kpi-value" :style="{ color: 'var(--green)' }">{{ cohort?.summary.low ?? 0 }}</div></div>
  </div>
  <div class="card">
    <div class="card-header"><span class="card-title">今日待评估患者（演示队列 seed=42）</span></div>
    <div class="card-body" style="overflow-x:auto">
      <table>
        <thead><tr><th>ID</th><th>年龄</th><th>性别</th><th>手术类型</th><th>术前Scr</th><th>术前eGFR</th><th>APACHE II</th><th>预测风险</th><th>等级</th></tr></thead>
        <tbody>
          <tr v-for="p in cohort?.patients" :key="p.id" :style="{ background: p.riskLevel === '高' ? 'rgba(239,68,68,0.06)' : p.riskLevel === '中' ? 'rgba(251,191,36,0.06)' : 'none' }">
            <td>{{ p.id }}</td><td>{{ p.age }}</td><td>{{ p.sex }}</td><td>{{ p.surgery }}</td><td>{{ p.preScr }}</td><td>{{ p.preEgfr }}</td><td>{{ p.apache }}</td>
            <td>{{ (p.probability * 100).toFixed(1) }}%</td>
            <td><span class="tag" :class="'tag-' + (p.riskLevel === '高' ? 'high' : p.riskLevel === '中' ? 'medium' : 'low')">{{ p.riskLevel }}</span></td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
  <div class="card">
    <div class="card-header"><span class="card-title">批量风险评估</span></div>
    <div class="card-body">
      <div class="info-box">上传包含患者特征的 CSV，系统逐行生成 AKI 风险预测结果。</div>
      <input type="file" accept=".csv" @change="onUpload" />
      <p v-if="busy" class="muted" style="margin-top:8px">预测中…</p>
      <p v-else-if="csvResult" style="margin-top:8px">{{ csvResult }}</p>
    </div>
  </div>
</template>

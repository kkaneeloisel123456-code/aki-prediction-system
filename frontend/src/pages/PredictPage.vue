<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api } from '../api/client'
import type { FeaturesResponse, PredictResponse } from '../api/types'

const meta = ref<FeaturesResponse | null>(null)
const values = ref<Record<string, number | string>>({})
const result = ref<PredictResponse | null>(null)
const loading = ref(false)
const TIMING: Record<string, string> = { preop: '术前实验室指标', intraop: '术中 / ICU 入室指标', icu: 'ICU 入室指标', postop: '术后指标' }
const TIMING_ORDER = ['preop', 'intraop', 'icu', 'postop']

onMounted(async () => {
  const f = await api.features()
  meta.value = f
  const init: Record<string, number> = {}
  f.metas.forEach(m => (init[m.name] = m.median))
  values.value = init
})

const groups = computed(() => {
  if (!meta.value) return []
  return TIMING_ORDER.map(t => ({ timing: t, items: meta.value!.metas.filter(m => m.timing === t) })).filter(g => g.items.length)
})
const riskClass = computed((): string => result.value?.risk_level ?? 'medium')
const topShap = computed(() => result.value?.shap_values.slice(0, 6) ?? [])
const maxShap = computed(() => Math.max(0.001, ...topShap.value.map(s => Math.abs(s.shap))))

async function run() {
  loading.value = true
  try {
    const numeric: Record<string, number> = {}
    Object.entries(values.value).forEach(([k, v]) => { const n = parseFloat(String(v)); if (!Number.isNaN(n)) numeric[k] = n })
    result.value = await api.predict(numeric)
  } finally { loading.value = false }
}
function reset() {
  if (!meta.value) return
  const init: Record<string, number> = {}
  meta.value.metas.forEach(m => (init[m.name] = m.median))
  values.value = init; result.value = null
}
async function downloadPdf() {
  if (!result.value) return
  const numeric: Record<string, number> = {}
  Object.entries(values.value).forEach(([k, v]) => { const n = parseFloat(String(v)); if (!Number.isNaN(n)) numeric[k] = n })
  const blob = await api.reportPdf(numeric)
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a'); a.href = url; a.download = 'AKI_Report.pdf'; a.click(); URL.revokeObjectURL(url)
}
</script>

<template>
  <h2 class="page-title">AKI 风险预测</h2>
  <p class="page-subtitle">输入患者临床信息，获取实时风险预测、可解释分析与个体化建议</p>

  <div class="grid-2-1">
    <div class="card">
      <div class="card-header">
        <span class="card-title">患者信息录入</span>
        <button class="btn btn-secondary" @click="reset">重置</button>
      </div>
      <div class="card-body">
        <div v-for="g in groups" :key="g.timing" class="form-section">
          <div class="form-section-title">{{ TIMING[g.timing] ?? g.timing }}</div>
          <div class="form-grid">
            <div class="form-group" v-for="m in g.items" :key="m.name">
              <label :title="`训练集中位数 ${m.median}`">{{ m.name }}</label>
              <input class="form-control" type="number" step="any" v-model="values[m.name]" />
            </div>
          </div>
        </div>
        <button class="btn btn-primary" style="width:100%;justify-content:center;padding:8px" @click="run" :disabled="loading">
          {{ loading ? '预测中…' : '开始预测' }}
        </button>
      </div>
    </div>

    <div>
      <div class="risk-panel" :class="riskClass">
        <div class="risk-label" :class="riskClass">
          {{ result ? (riskClass === 'high' ? '高风险' : riskClass === 'medium' ? '中风险' : '低风险') : '等待预测' }}
        </div>
        <div class="risk-probability">{{ result ? (result.probability * 100).toFixed(1) : '—' }}%</div>
        <div style="font-size:11px;color:var(--text-muted)">AKI 发生概率</div>
        <div class="gauge">
          <div class="gauge-fill" :style="{ width: (result ? result.probability * 100 : 0) + '%', background: riskClass === 'high' ? 'var(--red)' : riskClass === 'medium' ? 'var(--yellow)' : 'var(--green)' }" />
        </div>
      </div>

      <div class="card">
        <div class="card-header"><span class="card-title">关键因素（SHAP）</span></div>
        <div class="card-body">
          <template v-if="topShap.length">
            <div class="shap-item" v-for="s in topShap" :key="s.feature">
              <div class="shap-header">
                <span style="color:var(--text)">{{ s.feature }}</span>
                <span :style="{ color: s.direction === 'risk' ? 'var(--red)' : 'var(--green)' }">{{ s.direction === 'risk' ? '增加风险' : '降低风险' }}</span>
              </div>
              <div class="shap-bar-bg">
                <div class="shap-bar" :style="{ width: (Math.abs(s.shap) / maxShap * 100) + '%', background: s.direction === 'risk' ? 'var(--red)' : 'var(--green)' }" />
              </div>
            </div>
          </template>
          <p v-else class="muted">填写特征后点击"开始预测"。</p>
        </div>
      </div>

      <div class="card">
        <div class="card-header"><span class="card-title">临床建议</span></div>
        <div class="card-body" style="font-size:12px;color:var(--text-muted)">
          <p style="margin-bottom:8px"><strong style="color:var(--text)">监测：</strong>每 6h 监测尿量和 Scr 变化</p>
          <p style="margin-bottom:8px"><strong style="color:var(--text)">预防：</strong>目标导向液体治疗，维持尿量 &gt; 0.5 ml/kg/h</p>
          <p style="margin-bottom:8px"><strong style="color:var(--text)">检查：</strong>每日复查 Scr、eGFR、电解质、血气</p>
          <p style="margin-bottom:0"><strong style="color:var(--text)">KDIGO：</strong>建议肾内科会诊评估</p>
        </div>
      </div>

      <button class="btn btn-primary" style="width:100%;justify-content:center;padding:8px" @click="downloadPdf" :disabled="!result">下载 PDF 报告</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api } from '../api/client'
import type { FeaturesResponse } from '../api/types'

const features = ref<FeaturesResponse | null>(null)
const busy     = ref(false)

const TIMING_LABELS: Record<string, string> = {
  preop:   '术前实验室指标',
  intraop: '术中 / ICU 入室指标',
  icu:     'ICU 入室指标',
  postop:  '术后指标',
}
const TIMING_ORDER = ['preop', 'intraop', 'icu', 'postop']
const TIMING_COLOR: Record<string, string> = {
  preop: 'var(--primary)', intraop: 'var(--yellow)', icu: '#a78bfa', postop: 'var(--green)',
}

// Mock report history (real deployment: fetch from backend)
const MOCK_REPORTS = [
  { id: 'R-2026001', date: '08-10 09:15', patientId: 'P-042', risk: '高风险', level: 'high',   prob: '71.2%' },
  { id: 'R-2026002', date: '08-10 08:47', patientId: 'P-017', risk: '低风险', level: 'low',    prob: '18.5%' },
  { id: 'R-2026003', date: '08-09 16:30', patientId: 'P-088', risk: '中风险', level: 'medium', prob: '44.7%' },
  { id: 'R-2026004', date: '08-09 11:02', patientId: 'P-031', risk: '低风险', level: 'low',    prob: '12.1%' },
  { id: 'R-2026005', date: '08-08 14:55', patientId: 'P-065', risk: '高风险', level: 'high',   prob: '83.6%' },
]

// Group features by timing
const groupedFeatures = computed(() => {
  if (!features.value?.metas) return []
  const map: Record<string, string[]> = {}
  features.value.metas.forEach(m => {
    if (!map[m.timing]) map[m.timing] = []
    map[m.timing].push(m.name)
  })
  return TIMING_ORDER
    .filter(t => map[t]?.length)
    .map(t => ({ timing: t, label: TIMING_LABELS[t] ?? t, color: TIMING_COLOR[t], names: map[t] }))
})

onMounted(() => api.features().then(f => { features.value = f }).catch(() => {}))

async function downloadDemo(row?: any) {
  busy.value = true
  try {
    let features: Record<string, number> = {}
    let pid = 'Demo'
    let overrideProb: number | undefined
    if (row && typeof row.patientId === 'string') {
      pid = row.patientId
      const probValue = parseFloat(row.prob)
      overrideProb = probValue / 100
      features = {
        "年龄": 45 + (probValue / 2),
        "APACHEII": probValue > 50 ? 25 : 10,
        "术前Scr": probValue > 50 ? 150 : 80,
      }
    }
    const blob = await api.reportPdf(features, pid, overrideProb)
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href = url; a.download = `AKI_Report_${pid}.pdf`; a.click()
    URL.revokeObjectURL(url)
  } catch (e: any) {
    alert('PDF 下载失败：' + (e?.message || e))
  } finally { busy.value = false }
}
</script>

<template>
  <h2 class="page-title">报告中心</h2>
  <p class="page-subtitle">PDF 报告管理与模型特征说明</p>

  <!-- Report history -->
  <div class="card">
    <div class="card-header">
      <span class="card-title">报告历史</span>
      <span class="muted" style="font-size:10px">演示数据 · 实际部署后接后端</span>
    </div>
    <div class="card-body" style="padding:0">
      <table>
        <thead><tr>
          <th>报告编号</th><th>生成时间</th><th>患者 ID</th><th>风险概率</th><th>等级</th><th>操作</th>
        </tr></thead>
        <tbody>
          <tr v-for="r in MOCK_REPORTS" :key="r.id">
            <td style="font-family:monospace;font-size:10px;color:var(--text-muted)">{{ r.id }}</td>
            <td>{{ r.date }}</td>
            <td><strong>{{ r.patientId }}</strong></td>
            <td><strong>{{ r.prob }}</strong></td>
            <td><span class="tag" :class="`tag-${r.level}`">{{ r.risk }}</span></td>
            <td>
              <button class="btn btn-secondary btn-sm" @click="downloadDemo(r)" :disabled="busy">
                {{ busy ? '…' : '下载' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- Download demo report -->
  <div class="card">
    <div class="card-header"><span class="card-title">下载示例报告</span></div>
    <div class="card-body" style="display:flex;align-items:center;gap:14px;flex-wrap:wrap">
      <p class="muted" style="flex:1;min-width:160px">使用训练集中位数生成示例患者报告，用于演示 PDF 格式与内容。</p>
      <button class="btn btn-primary" @click="downloadDemo" :disabled="busy">
        {{ busy ? '生成中…' : '下载示例 PDF' }}
      </button>
    </div>
  </div>

  <!-- Feature list grouped by timing -->
  <div class="card">
    <div class="card-header">
      <span class="card-title">模型特征列表</span>
      <span class="badge badge-info">{{ features?.features.length ?? '—' }} 个特征</span>
    </div>
    <div class="card-body">
      <p class="muted" v-if="!features" style="text-align:center;padding:12px">加载中…</p>
      <template v-else>
        <div v-for="g in groupedFeatures" :key="g.timing" style="margin-bottom:18px">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;padding-bottom:5px;border-bottom:1px solid var(--border)">
            <span style="width:3px;height:14px;border-radius:2px;flex-shrink:0" :style="{ background: g.color }"></span>
            <span style="font-size:10px;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:.5px">
              {{ g.label }}
            </span>
            <span class="muted" style="font-size:10px">{{ g.names.length }} 项</span>
          </div>
          <div style="display:flex;flex-wrap:wrap;gap:5px">
            <span v-for="name in g.names" :key="name"
                  style="padding:3px 10px;border-radius:12px;font-size:11px;color:var(--text-muted);border:1px solid var(--border);background:var(--bg-inset)">
              {{ name }}
            </span>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

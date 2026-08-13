<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api/client'
import { useSelectedPatient } from '../composables/usePatient'
import type { FeaturesResponse, PredictResponse } from '../api/types'

const meta      = ref<FeaturesResponse | null>(null)
const values    = ref<Record<string, number | string>>({})
const result    = ref<PredictResponse | null>(null)
const loading   = ref(false)
const error     = ref<string | null>(null)
const activeTab = ref('preop')
const selectedPatientId = ref<string | null>(null)

const TIMING: Record<string, string> = {
  preop:   '术前指标',
  intraop: '术中指标',
  icu:     'ICU 指标',
  postop:  '术后指标',
}
const TIMING_ORDER = ['preop', 'intraop', 'icu', 'postop']

const route = useRoute()
const { selectedPatient, clear: clearSelectedPatient } = useSelectedPatient()

onMounted(async () => {
  try {
    const f = await api.features()
    meta.value = f
    const init: Record<string, number> = {}
    const prefilled = selectedPatient.value?.features ?? {}
    f.metas.forEach((m: any) => {
      let val = m.median
      if (prefilled[m.name] !== undefined) {
        val = Number(prefilled[m.name])
      } else if (route.query[m.name] !== undefined) {
        const parsed = Number(route.query[m.name])
        if (!Number.isNaN(parsed)) val = parsed
      }
      init[m.name] = val
    })
    values.value = init
    if (selectedPatient.value) selectedPatientId.value = selectedPatient.value.id
    const first = TIMING_ORDER.find(t => f.metas.some((m: any) => m.timing === t))
    if (first) activeTab.value = first

    if (selectedPatient.value || route.query.auto === '1') {
      setTimeout(() => { run() }, 50)
    }
  } catch (e: any) {
    error.value = '无法加载特征定义，请确认后端服务已启动。'
  }
})

onBeforeUnmount(() => {
  clearSelectedPatient()
})

const availableTabs = computed(() =>
  meta.value
    ? TIMING_ORDER.filter(t => meta.value!.metas.some((m: any) => m.timing === t))
    : []
)
const currentItems = computed(() =>
  meta.value ? (meta.value.metas as any[]).filter((m: any) => m.timing === activeTab.value) : []
)

// Backend returns Chinese 高/中/低; normalize to CSS class keys.
const riskClass = computed((): string => {
  const r = String(result.value?.risk_level ?? '')
  if (r.includes('高') || r === 'high') return 'high'
  if (r.includes('中') || r === 'medium') return 'medium'
  return 'low'
})
const riskLevelText = computed(() => {
  if (!result.value) return '等待预测'
  return riskClass.value === 'high' ? '高风险' : riskClass.value === 'medium' ? '中风险' : '低风险'
})

// ── 3/4 弧仪表盘 ──────────────────────────────────────────────
// pathLength=100, 3/4 圆弧=75, rotate(135)把缺口置于正下方
const gaugeColor = computed(() => {
  if (!result.value) return 'var(--border-light)'
  if (riskClass.value === 'high')   return 'var(--red)'
  if (riskClass.value === 'medium') return 'var(--yellow)'
  return 'var(--green)'
})
const gaugeDisplay = computed(() => {
  const p = result.value?.probability
  if (p == null || !Number.isFinite(p)) return '—'
  return (Math.min(1, Math.max(0, p)) * 100).toFixed(1) + '%'
})
// 进度弧长 = probability × 75（最大填满3/4圆）
const gaugeFill = computed(() => {
  const p = result.value?.probability
  if (p == null || !Number.isFinite(p)) return 0
  return Math.min(1, Math.max(0, p)) * 75
})

// ── 双向 SHAP ─────────────────────────────────────────────────
const topShap = computed(() => result.value?.shap_values.slice(0, 6) ?? [])
const maxShap = computed(() =>
  Math.max(0.001, ...topShap.value.map((s: any) => Math.abs(s.shap)))
)

// ── 操作 ──────────────────────────────────────────────────────
function collectNumeric(): Record<string, number> | null {
  const numeric: Record<string, number> = {}
  for (const [k, v] of Object.entries(values.value)) {
    const str = String(v).trim()
    if (str === '') continue
    const n = Number(str)
    if (Number.isNaN(n) || !Number.isFinite(n)) {
      error.value = `字段 "${k}" 不是有效数字，请检查输入`
      return null
    }
    numeric[k] = n
  }
  return numeric
}

async function run() {
  loading.value = true
  error.value = null
  try {
    const numeric = collectNumeric()
    if (!numeric) return
    result.value = await api.predict(numeric, selectedPatientId.value ?? undefined)
  } catch (e: any) {
    result.value = null
    const msg = e?.message || ''
    if (msg.includes('422') || msg.includes('valid number')) error.value = '请检查输入：所有字段必须是有效数字'
    else if (msg.includes('Failed to fetch')) error.value = '无法连接服务器，请确认后端已启动'
    else error.value = '预测失败：' + msg
  } finally { loading.value = false }
}
const interpretation = computed(() => {
  if (!result.value?.shap_values?.length) return ''
  const top = [...result.value.shap_values].sort((a:any,b:any)=>Math.abs(b.shap)-Math.abs(a.shap)).slice(0,3)
  return '主要影响因素：' + top.map((s:any)=>{
    const label = (meta.value?.metas as any[])?.find((m:any)=>m.name===s.feature)?.label || s.feature
    return label + (s.direction==='risk' ? ' 升高' : ' 降低')
  }).join('、') + '。'
})

function reset() {
  if (!meta.value) return
  const init: Record<string, number> = {}
  meta.value.metas.forEach((m: any) => (init[m.name] = m.median))
  values.value = init; result.value = null
  error.value = null
}

async function downloadPdf() {
  if (!result.value) return
  const numeric = collectNumeric()
  if (!numeric) return
  try {
    const blob = await api.reportPdf(numeric, selectedPatientId.value ?? undefined)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = 'AKI_Report.pdf'; a.click()
    URL.revokeObjectURL(url)
  } catch (e: any) {
    error.value = 'PDF 下载失败：' + (e?.message || e)
  }
}
</script>

<template>
  <h2 class="page-title">AKI 风险预测</h2>
  <p class="page-subtitle">输入患者临床信息，获取实时风险预测、可解释分析与个体化建议</p>

  <div class="grid-2-1">
    <!-- ── 左列：Tab 输入表单 ── -->
    <div class="card">
      <div class="card-header">
        <span class="card-title">患者信息录入</span>
        <div style="display: flex; gap: 8px;">
          <button class="btn btn-secondary btn-sm" @click="reset" title="重置为临床中位数">重置</button>
          <button class="btn btn-primary btn-sm" @click="run" :disabled="loading">
            {{ loading ? '预测中…' : '开始预测' }}
          </button>
        </div>
      </div>
      <div class="card-body">
        <!-- Tab 导航 -->
        <div class="tabs">
          <button
            v-for="t in availableTabs" :key="t"
            class="tab" :class="{ active: activeTab === t }"
            @click="activeTab = t"
          >{{ TIMING[t] }}</button>
        </div>

        <!-- 当前 Tab 字段 -->
        <div class="form-grid">
          <div class="form-group" v-for="m in currentItems" :key="m.name">
            <label :title="`${m.reference || ''} · 中位数 ${m.median}`">
              {{ m.label || m.name }}<span v-if="m.unit" style="color:var(--text-dim)"> ({{ m.unit }})</span>
            </label>
            <input class="form-control" type="number" step="any" v-model="values[m.name]" :placeholder="String(m.median)" />
          </div>
        </div>

        <p style="font-size:10px;color:var(--text-dim);margin-top:10px;text-align:center">
          未填写的后续阶段数据，将默认使用临床中位数进行预测。
        </p>
        <p v-if="error" class="error" style="margin-top:8px">{{ error }}</p>
        <div v-if="interpretation" class="note" style="margin-top:10px">{{ interpretation }}</div>
      </div>
    </div>

    <!-- ── 右列：结果 ── -->
    <div>
      <!-- 3/4 弧仪表盘 -->
      <div class="card" style="text-align:center">
        <div class="card-header">
          <span class="card-title">风险评估结果</span>
          <span v-if="result" class="tag" :class="'tag-' + riskClass">{{ riskLevelText }}</span>
          <span v-else class="muted" style="font-size:10px">预测后显示</span>
        </div>
        <div class="card-body" style="padding-top:6px;padding-bottom:14px">
          <!--
            circle r=80, cx=cy=100 → circumference ≈ 502
            pathLength=100 → 3/4弧=75, 缺口=25
            rotate(135, 100, 100) 把默认起点(3点钟)旋转到(SE),
            使 25% 的缺口落在正下方
          -->
          <svg viewBox="0 0 200 185" class="gauge-svg">
            <!-- 背景弧 -->
            <circle cx="100" cy="100" r="80"
                    fill="none" stroke="var(--bg-inset)" stroke-width="16" stroke-linecap="round"
                    pathLength="100" stroke-dasharray="75 25"
                    transform="rotate(135, 100, 100)" />
            <!-- 进度弧 -->
            <circle cx="100" cy="100" r="80"
                    fill="none" :stroke="gaugeColor"
                    stroke-width="16" stroke-linecap="round"
                    pathLength="100" :stroke-dasharray="`${gaugeFill} 100`"
                    transform="rotate(135, 100, 100)"
                    class="gauge-progress" />
            <!-- 风险等级 -->
            <text x="100" y="72" text-anchor="middle"
                  class="gauge-risk-text"
                  :fill="result ? gaugeColor : 'var(--text-dim)'">
              {{ riskLevelText }}
            </text>
            <!-- 大概率数字 -->
            <text x="100" y="108" text-anchor="middle" class="gauge-pct-text">
              {{ gaugeDisplay }}
            </text>
            <!-- 副标题 -->
            <text x="100" y="127" text-anchor="middle" class="gauge-label-text">
              AKI 发生概率
            </text>
          </svg>
        </div>
      </div>

      <!-- 缺失字段提示 -->
      <div v-if="result && result.missing_filled && result.missing_filled.length > 0" class="card"
           style="border-left: 3px solid var(--yellow)">
        <div class="card-header">
          <span class="card-title" style="color:var(--yellow)">
            <svg style="width:13px;height:13px;vertical-align:-2px;stroke:currentColor;fill:none;stroke-width:2;margin-right:4px" viewBox="0 0 24 24">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
              <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
            </svg>
            {{ result.missing_filled.length }} 个字段使用了临床中位数填充
          </span>
        </div>
        <div class="card-body">
          <p style="font-size:10px;color:var(--text-dim);margin-bottom:8px">
            以下字段未录入，系统自动使用训练集中位数替代。建议补充实际测量值以提高预测精度：
          </p>
          <div style="display:flex;flex-wrap:wrap;gap:4px">
            <span v-for="f in result.missing_filled" :key="f"
                  style="font-size:10px;padding:2px 8px;border-radius:4px;background:rgba(251,191,36,.12);color:var(--yellow);border:1px solid rgba(251,191,36,.25)">
              {{ f }}
            </span>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header"><span class="card-title">关键影响因素（SHAP Top 6）</span></div>
        <div class="card-body">
          <template v-if="topShap.length">
            <div class="shap-bidir-header">
              <span style="color:var(--green)">← 降低风险</span>
              <span></span>
              <span style="color:var(--red);text-align:right">增加风险 →</span>
            </div>
            <div v-for="s in topShap" :key="s.feature" class="shap-bidir-row">
              <div class="shap-bar-left">
                <div
                  v-if="s.direction !== 'risk'"
                  class="shap-bar-fill-left"
                  :style="{ width: (Math.abs(s.shap) / maxShap * 100) + '%' }"
                />
              </div>
              <div class="shap-center-label" :title="s.feature">{{ s.feature }}</div>
              <div class="shap-bar-right">
                <div
                  v-if="s.direction === 'risk'"
                  class="shap-bar-fill-right"
                  :style="{ width: (Math.abs(s.shap) / maxShap * 100) + '%' }"
                />
              </div>
            </div>
          </template>
          <p v-else class="muted" style="text-align:center;padding:8px 0">预测后查看特征影响方向。</p>
        </div>
      </div>

      <!-- 临床建议 -->
      <div class="card">
        <div class="card-header"><span class="card-title">临床建议</span></div>
        <div class="card-body" style="font-size:12px;color:var(--text-muted)">
          <p style="margin-bottom:8px"><strong style="color:var(--text)">监测：</strong>每 6 h 监测尿量和 Scr 变化</p>
          <p style="margin-bottom:8px"><strong style="color:var(--text)">预防：</strong>目标导向液体治疗，维持尿量 &gt; 0.5 ml/kg/h</p>
          <p style="margin-bottom:8px"><strong style="color:var(--text)">检查：</strong>每日复查 Scr、eGFR、电解质、血气</p>
          <p style="margin-bottom:0"><strong style="color:var(--text)">KDIGO：</strong>建议肾内科会诊评估</p>
        </div>
      </div>

      <button
        class="btn btn-primary"
        style="width:100%;justify-content:center;padding:10px"
        @click="downloadPdf" :disabled="!result"
      >下载 PDF 报告</button>
    </div>
  </div>
</template>

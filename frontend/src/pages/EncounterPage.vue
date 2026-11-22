<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, saveBlob } from '../api/client'

const route = useRoute()
const router = useRouter()
const loading = ref(true)
const error = ref('')
const notice = ref('')
const encounter = ref<any>(null)
const metas = ref<any[]>([])
const values = reactive<Record<string, string>>({})
const diagnosis = ref('')
const orders = ref('')
const rowVersion = ref(1)
const draftVersion = ref(0)
const step = ref(1)
const saving = ref(false)
const predicting = ref(false)
const reviewing = ref(false)
const publishing = ref(false)
const dirty = ref(false)
const prediction = ref<any>(null)
const reviewDecision = ref('agree')
const reviewReason = ref('')
const reviewDone = ref(false)
const checklist = ref<any>(null)
const missingAck = ref(false)
const publishResult = ref<any>(null)
const publishError = ref('')
const collapsed = reactive<Record<string, boolean>>({})

const timings = [
  { key: 'preop', label: '术前指标', tone: 'timing-preop', desc: '术前基线检验与血流动力学' },
  { key: 'intraop', label: '术中指标', tone: 'timing-intraop', desc: '手术时长、液体与失血' },
  { key: 'icu', label: 'ICU 入科', tone: 'timing-icu', desc: '入 ICU 后早期检验' },
  { key: 'postop', label: '术后指标', tone: 'timing-postop', desc: '术后炎症、肾功能与电解质' },
]
const groups = computed(() => timings.map((t) => ({
  ...t,
  features: metas.value.filter((m) => m.timing === t.key),
})))
const allFeatures = computed(() => metas.value.map((m) => m.name))
const filledCount = computed(() => allFeatures.value.filter((name) => values[name] !== '' && values[name] != null).length)
const measuredCount = computed(() => allFeatures.value.filter((name) => {
  const v = values[name]
  return v !== '' && v != null && Number.isFinite(Number(v))
}).length)

const riskClass = computed(() => {
  const level = prediction.value?.risk_level ?? encounter.value?.latest_prediction?.risk_level
  return level === '高' ? 'high' : level === '中' ? 'medium' : 'low'
})
const riskText = computed(() => {
  const level = prediction.value?.risk_level ?? encounter.value?.latest_prediction?.risk_level
  return level ? `${level}风险` : '未评估'
})
const probabilityText = computed(() => {
  const p = prediction.value?.probability ?? encounter.value?.latest_prediction?.probability
  return typeof p === 'number' ? `${(p * 100).toFixed(1)}%` : '—'
})
const shapRows = computed(() => {
  const rows = prediction.value?.shap_values ?? encounter.value?.latest_prediction?.shap_values ?? []
  return [...rows].sort((a: any, b: any) => Math.abs(b.shap) - Math.abs(a.shap)).slice(0, 10)
})
const maxShap = computed(() => Math.max(0.001, ...shapRows.value.map((r: any) => Math.abs(r.shap))))
const currentPredictionId = computed(() => encounter.value?.current_prediction_id)
const hasPrediction = computed(() => Boolean(prediction.value || encounter.value?.latest_prediction))
const canEdit = computed(() => encounter.value?.can_edit !== false)
const isPublished = computed(() => encounter.value?.status === 'published')

const statusText: Record<string, string> = {
  draft: '草稿', predicted: '待复核', reviewed: '已复核', published: '已发布',
}
const decisionText: Record<string, string> = {
  agree: '认可模型结果', adjust: '调整判断', defer: '暂缓采纳', manual: '人工审核',
}
const featureLabels = computed(() => Object.fromEntries(
  metas.value.map((m) => [m.name, m.label || m.name]),
))
function shapLabel(name: string) { return featureLabels.value[name] || name }
function isFilledFeature(name: string) {
  const filled = prediction.value?.missing_filled ?? encounter.value?.latest_prediction?.missing_filled ?? []
  return filled.includes(name)
}
function fmt(value?: string) {
  if (!value) return '—'
  return new Date(value).toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}
function fieldLabel(meta: any) { return meta.label || meta.name }
function fieldUnit(meta: any) { return meta.unit || '' }
function fieldReference(meta: any) { return meta.reference || (meta.lo != null && meta.hi != null ? `参考 ${meta.lo}–${meta.hi}` : '') }
function isInvalid(meta: any) {
  const raw = values[meta.name]
  if (raw === '' || raw == null) return false
  const n = Number(raw)
  if (!Number.isFinite(n)) return true
  if (meta.lo != null && n < meta.lo) return true
  if (meta.hi != null && n > meta.hi) return true
  return false
}
function invalidCount() { return metas.value.filter(isInvalid).length }

function hydratePayload(payload: any) {
  for (const name of allFeatures.value) {
    const v = payload?.values?.[name]
    values[name] = v === null || v === undefined ? '' : String(v)
  }
  diagnosis.value = payload?.diagnosis ?? encounter.value?.diagnosis ?? ''
  orders.value = payload?.orders ?? encounter.value?.orders ?? ''
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [enc, feats] = await Promise.all([
      api.encounter(route.params.id as string),
      api.features(),
    ])
    encounter.value = enc
    metas.value = feats.metas ?? []
    rowVersion.value = enc.row_version
    const payload = enc.draft?.payload
    draftVersion.value = enc.draft?.draft_version ?? 0
    hydratePayload(payload)
    prediction.value = enc.latest_prediction ?? null
    reviewDone.value = Boolean(enc.latest_review)
    if (enc.status === 'published') {
      step.value = 4
      checklist.value = await api.checklist(enc.id, true).catch(() => null)
    } else if (enc.latest_review) {
      step.value = 4
      checklist.value = await api.checklist(enc.id, false).catch(() => null)
    } else if (enc.latest_prediction) {
      step.value = 3
    }
  } catch (e: any) {
    error.value = e?.message ?? '接诊记录加载失败'
  } finally {
    loading.value = false
  }
}

async function persistDraft(silent = false): Promise<boolean> {
  error.value = ''
  if (!canEdit.value) { error.value = '当前账号对该患者只有只读权限'; return false }
  if (invalidCount() > 0) { error.value = '存在超出临床合理范围的指标，请修正后再保存'; return false }
  saving.value = true
  try {
    const payloadValues: Record<string, number> = {}
    for (const meta of metas.value) {
      const raw = values[meta.name]
      if (raw === '' || raw == null) continue
      const n = Number(raw)
      if (Number.isFinite(n)) payloadValues[meta.name] = n
    }
    const res = await api.saveDraft(encounter.value.id, {
      row_version: rowVersion.value,
      draft_version: draftVersion.value,
      values: payloadValues,
      diagnosis: diagnosis.value,
      orders: orders.value,
    })
    draftVersion.value = res.draft_version
    dirty.value = false
    if (!silent) notice.value = `草稿已保存（版本 ${draftVersion.value}）`
    return true
  } catch (e: any) {
    error.value = e?.message ?? '草稿保存失败'
    return false
  } finally {
    saving.value = false
  }
}

async function runPrediction() {
  error.value = ''
  if (measuredCount.value === 0) { error.value = '至少录入一项实测指标后才能运行模型'; return }
  if (invalidCount() > 0) { error.value = '请先修正超出合理范围的指标'; return }
  const saved = await persistDraft(true)
  if (!saved) return
  predicting.value = true
  try {
    const payloadValues: Record<string, number> = {}
    for (const meta of metas.value) {
      const raw = values[meta.name]
      if (raw === '' || raw == null) continue
      const n = Number(raw)
      if (Number.isFinite(n)) payloadValues[meta.name] = n
    }
    const result = await api.clinicalPredict(encounter.value.id, {
      row_version: rowVersion.value,
      features: payloadValues,
    })
    encounter.value = { ...encounter.value, ...result }
    rowVersion.value = result.row_version
    prediction.value = result.prediction
    notice.value = `模型评估完成：${result.prediction.risk_level}风险，缺失指标 ${result.prediction.missing_filled?.length ?? 0} 项已按中位数填充。`
    step.value = 3
  } catch (e: any) {
    error.value = e?.message ?? '预测失败'
  } finally {
    predicting.value = false
  }
}

async function submitReview() {
  error.value = ''
  if (reviewDecision.value !== 'agree' && !reviewReason.value.trim()) {
    error.value = '调整、暂缓或人工审核必须填写理由'
    return
  }
  if (!reviewDone.value) {
    const saved = await persistDraft(true)
    if (!saved) return
  }
  reviewing.value = true
  try {
    const res = await api.review(encounter.value.id, {
      row_version: rowVersion.value,
      decision: reviewDecision.value,
      reason: reviewReason.value.trim(),
    })
    encounter.value = { ...encounter.value, ...res }
    rowVersion.value = res.row_version
    reviewDone.value = true
    checklist.value = await api.checklist(encounter.value.id, missingAck.value)
    step.value = 4
    notice.value = '医生复核已记录，可进行发布核对。'
  } catch (e: any) {
    error.value = e?.message ?? '复核失败'
  } finally {
    reviewing.value = false
  }
}

async function refreshChecklist() {
  try {
    checklist.value = await api.checklist(encounter.value.id, missingAck.value)
  } catch (e: any) {
    error.value = e?.message ?? '发布核对失败'
  }
}

async function publishReport() {
  error.value = ''
  publishError.value = ''
  publishing.value = true
  try {
    const res = await api.publish(encounter.value.id, {
      row_version: rowVersion.value,
      draft_version: draftVersion.value,
      missing_ack: missingAck.value,
    })
    publishResult.value = res
    notice.value = `正式报告 ${res.report_no} 已发布`
    await load()
  } catch (e: any) {
    publishError.value = e?.message ?? '发布失败'
  } finally {
    publishing.value = false
  }
}

async function downloadPdf() {
  try {
    const blob = await api.reportPdf(publishResult.value.id)
    saveBlob(blob, `${publishResult.value.report_no}.pdf`)
  } catch (e: any) {
    error.value = e?.message ?? '下载失败'
  }
}

function goStep(n: number) {
  if (n === 3 && !hasPrediction.value) { error.value = '请先运行模型评估'; return }
  error.value = ''
  step.value = n
}
function startManualReview() {
  error.value = ''
  if (measuredCount.value === 0) {
    error.value = '至少录入一项实测指标后才能进入人工审核'
    return
  }
  reviewDecision.value = 'manual'
  step.value = 4
}
function markDirty() { dirty.value = true }

function beforeUnload(event: BeforeUnloadEvent) {
  if (dirty.value) { event.preventDefault(); event.returnValue = '' }
}
onMounted(() => { load(); window.addEventListener('beforeunload', beforeUnload) })
onUnmounted(() => window.removeEventListener('beforeunload', beforeUnload))
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
          <RouterLink :to="encounter ? `/patients/${encounter.patient_id}` : '/patients'" class="btn btn-sm btn-ghost">← 患者档案</RouterLink>
        </div>
        <h1 class="page-title">接诊与风险报告</h1>
        <div class="page-subtitle" v-if="encounter">
          {{ encounter.patient_name }} · <span class="font-mono">{{ encounter.mrn }}</span> · {{ encounter.case_ref }} ·
          <span class="status" :class="`status-${encounter.status}`">{{ statusText[encounter.status] ?? encounter.status }}</span>
        </div>
      </div>
      <div class="page-actions" v-if="encounter">
        <button v-if="!isPublished" class="btn btn-secondary" :disabled="saving || !canEdit" @click="persistDraft(false)">{{ saving ? '保存中…' : '保存草稿' }}</button>
        <button class="btn btn-secondary" :disabled="loading" @click="load">重新载入</button>
      </div>
    </div>

    <div v-if="error" class="error">{{ error }}</div>
    <div v-if="notice" class="info-box">{{ notice }}</div>
    <div v-if="loading" class="card"><div class="empty-state">正在载入接诊记录…</div></div>

    <template v-else-if="encounter">
      <div class="steps">
        <div v-for="(s, i) in [
          { n: 1, t: '就诊信息', d: '核对患者与本次手术' },
          { n: 2, t: '指标录入', d: '围手术期检验与体征' },
          { n: 3, t: '模型评估', d: '风险概率与 SHAP' },
          { n: 4, t: '复核发布', d: '医生决策与正式报告' },
        ]" :key="s.n" class="step" :class="{ active: step === s.n, done: step > s.n }">
          <div class="step-num">{{ step > s.n ? '✓' : s.n }}</div>
          <div class="step-text"><div class="t">{{ s.t }}</div><div class="s">{{ s.d }}</div></div>
          <div v-if="i < 3" class="step-line" />
        </div>
      </div>

      <div v-if="!canEdit" class="warning-box">当前账号对该患者只有只读权限，无法修改就诊或发布报告。</div>

      <!-- STEP 1 -->
      <div v-if="step === 1" class="grid-2-1">
        <div class="card">
          <div class="card-header"><span class="card-title">本次就诊信息</span></div>
          <div class="card-body">
            <div class="info-grid mb-12">
              <div class="info-item"><div class="k">患者</div><div class="v">{{ encounter.patient_name }}</div></div>
              <div class="info-item"><div class="k">病历号</div><div class="v font-mono">{{ encounter.mrn }}</div></div>
              <div class="info-item"><div class="k">就诊编号</div><div class="v font-mono">{{ encounter.case_ref }}</div></div>
              <div class="info-item"><div class="k">发生时间</div><div class="v">{{ fmt(encounter.occurred_at) }}</div></div>
              <div class="info-item"><div class="k">手术类型</div><div class="v">{{ encounter.surgery_type || '未填写' }}</div></div>
              <div class="info-item"><div class="k">创建人</div><div class="v">{{ encounter.created_by_name || encounter.created_by }}</div></div>
            </div>
            <div class="form-group mb-12">
              <label>临床诊断（将写入正式报告）</label>
              <textarea v-model="diagnosis" class="form-control" rows="3" :disabled="!canEdit || isPublished" @input="markDirty" placeholder="如：冠状动脉粥样硬化性心脏病，拟行冠脉搭桥术" />
            </div>
            <div class="form-group">
              <label>医嘱 / 随访建议（将写入正式报告）</label>
              <textarea v-model="orders" class="form-control" rows="3" :disabled="!canEdit || isPublished" @input="markDirty" placeholder="如：术后监测肌酐与尿量，必要时肾内科会诊" />
            </div>
          </div>
          <div class="modal-foot" style="position:static;border-top:1px solid var(--border)">
            <button v-if="!isPublished" class="btn btn-secondary" :disabled="saving || !canEdit" @click="persistDraft(false)">保存草稿</button>
            <button class="btn btn-primary" @click="goStep(2)">下一步：录入指标 →</button>
          </div>
        </div>
        <div>
          <div class="side-card">
            <div class="side-title">填写说明</div>
            <div class="muted" style="font-size:11px;line-height:1.8">
              1. 本次就诊编号在同一患者下唯一。<br />
              2. 诊断与医嘱属于正式报告内容，建议在复核前完成。<br />
              3. 指标可分批录入，草稿不会影响正式记录。<br />
              4. 模型允许缺失指标并按训练中位数填充，缺失项需在发布前确认。
            </div>
          </div>
          <div class="side-card">
            <div class="side-title">版本状态</div>
            <div class="muted" style="font-size:11px;line-height:1.9">
              记录版本 v{{ rowVersion }}<br />
              草稿版本 {{ draftVersion }}<br />
              最近预测 {{ encounter.current_prediction_id || '无' }}
            </div>
          </div>
        </div>
      </div>

      <!-- STEP 2 -->
      <div v-else-if="step === 2" class="card">
        <div class="card-header">
          <span class="card-title">围手术期指标录入</span>
          <span class="status" :class="filledCount ? 'status-info' : 'status-draft'">已填 {{ filledCount }} / {{ allFeatures.length }}</span>
        </div>
        <div class="card-body">
          <div class="metric-progress">
            <div class="track"><div class="fill" :style="{width: `${allFeatures.length ? filledCount / allFeatures.length * 100 : 0}%`}" /></div>
            <div class="text">{{ measuredCount }} 项有效数值</div>
          </div>
          <div v-if="invalidCount()" class="warning-box">有 {{ invalidCount() }} 项数值超出临床合理范围，请修正后再保存或预测。</div>

          <div v-for="g in groups" :key="g.key" class="metric-group">
            <div class="metric-group-head" @click="collapsed[g.key] = !collapsed[g.key]">
              <div style="display:flex;align-items:center;gap:8px">
                <span class="metric-group-title">{{ g.label }}</span>
                <span class="metric-group-meta">{{ g.features.length }} 项 · {{ g.desc }}</span>
              </div>
              <span class="section-chevron" :class="{ open: !collapsed[g.key] }">›</span>
            </div>
            <div v-if="!collapsed[g.key]" class="metric-grid">
              <div v-for="m in g.features" :key="m.name" class="metric-field">
                <label>
                  <span>{{ fieldLabel(m) }}</span>
                  <span v-if="fieldUnit(m)" class="unit">{{ fieldUnit(m) }}</span>
                </label>
                <input v-model="values[m.name]" class="form-control" :class="{invalid: isInvalid(m)}" type="number" step="any" :disabled="!canEdit || isPublished" @input="markDirty" placeholder="留空表示缺失" />
                <div class="ref">{{ fieldReference(m) }}</div>
              </div>
            </div>
          </div>
        </div>
        <div class="modal-foot" style="position:static;border-top:1px solid var(--border)">
          <button class="btn btn-secondary" @click="goStep(1)">← 上一步</button>
          <button class="btn btn-secondary" :disabled="saving || !canEdit" @click="persistDraft(false)">保存草稿</button>
          <button class="btn btn-secondary" :disabled="!canEdit || isPublished" @click="startManualReview">无模型结果，人工审核</button>
          <button class="btn btn-primary" :disabled="predicting || !canEdit || isPublished" @click="runPrediction">
            {{ predicting ? '模型计算中…' : '保存并运行模型 →' }}
          </button>
        </div>
      </div>

      <!-- STEP 3 -->
      <div v-else-if="step === 3" class="grid-2-1">
        <div>
          <div class="card">
            <div class="card-header">
              <span class="card-title">模型评估结果</span>
              <span class="muted" style="font-size:10px">模型 {{ encounter.latest_prediction?.model_version || 'AKI-V1' }}</span>
            </div>
            <div class="card-body">
              <div class="assessment-grid">
                <div class="prob-card" :class="riskClass">
                  <div class="prob-label">预测 AKI 概率</div>
                  <div class="prob-value">{{ probabilityText }}</div>
                  <div class="prob-risk" :style="{color: `var(--${riskClass === 'high' ? 'red' : riskClass === 'medium' ? 'yellow' : 'green'})`}">{{ riskText }}</div>
                  <div class="prob-meta">
                    二分类判定：{{ (prediction?.prediction ?? encounter.latest_prediction?.prediction) === 1 ? '阳性' : '阴性' }}<br />
                    概率校准：{{ (prediction?.calibrated ?? encounter.latest_prediction?.calibrated) ? '已校准' : '未校准' }}<br />
                    实测 {{ measuredCount }} 项 / 缺失填充 {{ (prediction?.missing_filled ?? encounter.latest_prediction?.missing_filled ?? []).length }} 项
                  </div>
                </div>
                <div>
                  <div class="section-label" style="margin-top:0">主要影响因素（SHAP）</div>
                  <div v-if="!shapRows.length" class="muted">当前没有解释数据</div>
                  <div v-else class="shap-list">
                    <div v-for="s in shapRows" :key="s.feature" class="shap-row">
                      <div class="name" :title="s.feature">
                        {{ shapLabel(s.feature) }}
                        <span v-if="isFilledFeature(s.feature)" class="status status-draft">填充值</span>
                      </div>
                      <div class="bar"><span :style="{width: `${Math.abs(s.shap) / maxShap * 100}%`, background: s.shap >= 0 ? 'var(--red)' : 'var(--green)'}" /></div>
                      <div class="effect">{{ s.shap >= 0 ? '↑ 风险' : '↓ 保护' }} {{ Math.abs(s.shap).toFixed(3) }}</div>
                    </div>
                  </div>
                </div>
              </div>
              <div v-if="(prediction?.missing_filled ?? encounter.latest_prediction?.missing_filled ?? []).length" class="warning-box mt-12">
                缺失指标：{{ (prediction?.missing_filled ?? encounter.latest_prediction?.missing_filled ?? []).join('、') }}。模型已按训练中位数填充，这些值不等同于实测。
              </div>
            </div>
            <div class="modal-foot" style="position:static;border-top:1px solid var(--border)">
              <button class="btn btn-secondary" @click="goStep(2)">← 返回修改指标</button>
              <button class="btn btn-primary" @click="goStep(4)">下一步：医生复核 →</button>
            </div>
          </div>
        </div>
        <div>
          <div class="side-card">
            <div class="side-title">本次模型输入</div>
            <div class="muted" style="font-size:11px;line-height:1.9">
              患者：{{ encounter.patient_name }}<br />
              就诊：{{ encounter.case_ref }}<br />
              记录版本：v{{ rowVersion }}<br />
              草稿版本：{{ draftVersion }}<br />
              预测编号：{{ encounter.current_prediction_id }}
            </div>
          </div>
          <div class="side-card">
            <div class="side-title">重要提示</div>
            <div class="muted" style="font-size:11px;line-height:1.8">
              模型输出仅作为医生决策辅助，不能替代临床判断。修改指标后必须重新运行预测，否则不得发布报告。
            </div>
          </div>
        </div>
      </div>

      <!-- STEP 4 -->
      <div v-else-if="step === 4" class="grid-2-1">
        <div>
          <div class="card">
            <div class="card-header">
              <span class="card-title">医生复核</span>
              <span class="status" :class="reviewDone ? 'status-reviewed' : 'status-pending'">{{ reviewDone ? '已复核' : '待复核' }}</span>
            </div>
            <div class="card-body">
              <div v-if="!hasPrediction && !reviewDone" class="warning-box">当前没有有效模型结果。如确需继续，必须选择“人工审核”并填写理由。</div>
              <div class="form-grid-2">
                <div class="form-group">
                  <label>复核结论</label>
                  <select v-model="reviewDecision" class="form-control" :disabled="reviewDone || isPublished || !canEdit">
                    <option v-if="hasPrediction" value="agree">认可模型结果</option>
                    <option v-if="hasPrediction" value="adjust">调整风险判断</option>
                    <option v-if="hasPrediction" value="defer">暂缓采纳，继续观察</option>
                    <option v-if="!hasPrediction && !reviewDone" value="manual">人工审核（无模型结果）</option>
                  </select>
                </div>
                <div class="form-group">
                  <label>复核人</label>
                  <input class="form-control" :value="encounter.latest_review?.reviewer_name || '当前登录医生'" disabled />
                </div>
                <div class="form-group full">
                  <label>复核意见 {{ reviewDecision !== 'agree' ? '（必填）' : '（可选）' }}</label>
                  <textarea v-model="reviewReason" class="form-control" rows="3" :disabled="reviewDone || isPublished || !canEdit" placeholder="说明采纳、调整或暂缓的依据" />
                </div>
              </div>
              <div v-if="reviewDone && encounter.latest_review" class="info-box mt-12">
                已由 {{ encounter.latest_review.reviewer_name }} 于 {{ fmt(encounter.latest_review.created_at) }} 完成复核：{{ decisionText[encounter.latest_review.decision] || encounter.latest_review.decision }}。{{ encounter.latest_review.reason }}
              </div>
            </div>
            <div class="modal-foot" style="position:static;border-top:1px solid var(--border)">
              <button class="btn btn-secondary" @click="goStep(3)">← 返回评估</button>
              <button v-if="!reviewDone && !isPublished" class="btn btn-primary" :disabled="reviewing || !canEdit" @click="submitReview">{{ reviewing ? '提交中…' : '提交复核并进入发布核对' }}</button>
            </div>
          </div>

          <div v-if="reviewDone" class="card">
            <div class="card-header">
              <span class="card-title">发布核对清单</span>
              <button class="btn btn-sm btn-secondary" @click="refreshChecklist">重新核对</button>
            </div>
            <div class="card-body" v-if="checklist">
              <div class="check-list">
                <div v-for="item in checklist.items" :key="item.key" class="check-item">
                  <span class="check-icon" :class="item.ok ? 'ok' : 'bad'">{{ item.ok ? '✓' : '!' }}</span>
                  <div>
                    <div class="ct">{{ item.label }}</div>
                    <div v-if="item.detail" class="cd">{{ item.detail }}</div>
                  </div>
                </div>
              </div>
              <label v-if="checklist.missing_count" class="check-ack">
                <input v-model="missingAck" type="checkbox" @change="refreshChecklist" />
                我已确认 {{ checklist.missing_count }} 项指标缺失，并理解模型使用中位数填充。
              </label>
              <div v-if="publishError" class="error mt-12">{{ publishError }}</div>
              <div v-if="publishResult" class="info-box mt-12">
                正式报告已发布：<strong>{{ publishResult.report_no }}</strong>（v{{ publishResult.version }}）。
                <div class="flex gap-8 mt-8">
                  <button class="btn btn-sm btn-primary" @click="downloadPdf">下载 PDF</button>
                  <RouterLink :to="`/reports/${publishResult.id}`" class="btn btn-sm btn-secondary">查看报告</RouterLink>
                </div>
              </div>
            </div>
            <div class="modal-foot" style="position:static;border-top:1px solid var(--border)">
              <button v-if="!isPublished" class="btn btn-primary" :disabled="publishing || !checklist?.can_publish || !canEdit" @click="publishReport">
                {{ publishing ? '发布中…' : '发布正式报告' }}
              </button>
              <RouterLink v-if="isPublished && encounter.latest_report" :to="`/reports/${encounter.latest_report.id}`" class="btn btn-secondary">查看本次报告</RouterLink>
            </div>
          </div>
        </div>
        <div>
          <div class="side-card">
            <div class="side-title">报告摘要</div>
            <div class="muted" style="font-size:11px;line-height:1.9">
              患者：{{ encounter.patient_name }}<br />
              风险：{{ riskText }}<br />
              概率：{{ probabilityText }}<br />
              复核：{{ decisionText[encounter.latest_review?.decision] || encounter.latest_review?.decision || '未完成' }}<br />
              状态：{{ statusText[encounter.status] }}
            </div>
          </div>
          <div class="side-card">
            <div class="side-title">发布规则</div>
            <div class="muted" style="font-size:11px;line-height:1.8">
              正式报告一旦发布不可直接修改；如发现错误，由管理员撤销后重新发布新版本。旧版本仍保留审计记录。
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

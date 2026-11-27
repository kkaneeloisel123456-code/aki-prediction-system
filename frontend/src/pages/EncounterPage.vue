<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api, saveBlob } from '../api/client'
import { ElMessage } from 'element-plus'
import 'element-plus/es/components/message/style/css'

const route = useRoute()
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
const previousEncounter = ref<any>(null)
const previousLoading = ref(false)
const showPaste = ref(false)
const pasteText = ref('')
const pasteOverwrite = ref(false)
const pasteError = ref('')

const timings = [
  { key: 'preop', label: '术前指标', desc: '基线检验与血流动力学' },
  { key: 'intraop', label: '术中指标', desc: '手术时长、液体与失血' },
  { key: 'icu', label: 'ICU 入科', desc: '入 ICU 后早期检验' },
  { key: 'postop', label: '术后指标', desc: '炎症、肾功能与电解质' },
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

const riskLevel = computed(() => prediction.value?.risk_level ?? encounter.value?.latest_prediction?.risk_level ?? '')
const riskTone = computed(() => {
  if (riskLevel.value === '高') return 'high'
  if (riskLevel.value === '中') return 'mid'
  if (riskLevel.value === '低') return 'low'
  return 'none'
})
const riskText = computed(() => {
  if (!riskLevel.value) return '未评估'
  return riskLevel.value === '人工审核' ? '人工审核' : `${riskLevel.value}风险`
})
const probabilityText = computed(() => {
  const p = prediction.value?.probability ?? encounter.value?.latest_prediction?.probability
  return typeof p === 'number' ? `${(p * 100).toFixed(1)}%` : '—'
})
const binaryText = computed(() => {
  if (riskLevel.value === '人工审核') return '—'
  const v = prediction.value?.prediction ?? encounter.value?.latest_prediction?.prediction
  if (v === 1) return '阳性'
  if (v === 0) return '阴性'
  return '—'
})
const activePrediction = computed(() => prediction.value ?? encounter.value?.latest_prediction ?? null)
const isManualPrediction = computed(() => Boolean(
  activePrediction.value?.manual
  || activePrediction.value?.origin === 'manual'
  || activePrediction.value?.risk_level === '人工审核',
))
const hasPrediction = computed(() => Boolean(activePrediction.value))
const hasModelPrediction = computed(() => hasPrediction.value && !isManualPrediction.value)
const calibratedText = computed(() => {
  if (isManualPrediction.value) return '不适用'
  const v = prediction.value?.calibrated ?? encounter.value?.latest_prediction?.calibrated
  return v ? '已校准' : '未校准'
})
const missingCount = computed(() => (
  prediction.value?.missing_filled ?? encounter.value?.latest_prediction?.missing_filled ?? []
).length)
const shapRows = computed(() => {
  const rows = prediction.value?.shap_values ?? encounter.value?.latest_prediction?.shap_values ?? []
  return [...rows].sort((a: any, b: any) => Math.abs(b.shap) - Math.abs(a.shap)).slice(0, 8)
})
const maxShap = computed(() => Math.max(0.001, ...shapRows.value.map((r: any) => Math.abs(r.shap))))
const canEdit = computed(() => encounter.value?.can_edit !== false)
const isPublished = computed(() => encounter.value?.status === 'published')
const metricsLocked = computed(() => isPublished.value)
const reopening = ref(false)
const latestReport = computed(() => encounter.value?.latest_report ?? null)
const reviewOptions = computed(() => isManualPrediction.value
  ? [{ value: 'manual', label: '人工记录' }]
  : hasPrediction.value
    ? [
        { value: 'agree', label: '采纳模型结果' },
        { value: 'adjust', label: '调整风险判断（上调 / 下调）' },
        { value: 'defer', label: '暂不发布，继续观察' },
      ]
    : [{ value: 'manual', label: '无模型结果，人工记录' }])

const statusText: Record<string, string> = {
  draft: '草稿', predicted: '待复核', reviewed: '已复核', published: '已发布',
}
const decisionText: Record<string, string> = {
  agree: '采纳模型结果', adjust: '调整风险判断', defer: '暂不发布', manual: '人工记录',
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

type PasteEntry = { token: string; value: string; meta: any | null; invalid: boolean }

function normalizeToken(text: string) {
  return (text || '')
    .replace(/\s+/g, '')
    .replace(/[（(].*?[）)]/g, '')
    .toLowerCase()
}
const featureLookup = computed(() => {
  const lookup = new Map<string, any>()
  for (const meta of metas.value) {
    lookup.set(normalizeToken(meta.name), meta)
    lookup.set(normalizeToken(meta.label || ''), meta)
    lookup.set(normalizeToken(String(meta.label || '').replace(/[（(].*?[）)]/g, '')), meta)
  }
  return lookup
})
const previousLabel = computed(() => previousEncounter.value
  ? `上次 ${previousEncounter.value.case_ref} · ${fmt(previousEncounter.value.occurred_at)}`
  : '暂无上次就诊')
const pasteEntries = computed<PasteEntry[]>(() => parsePaste(pasteText.value))
const pasteMatched = computed(() => pasteEntries.value.filter((entry) => entry.meta && !entry.invalid))
const pasteUnmatched = computed(() => pasteEntries.value.filter((entry) => !entry.meta || entry.invalid))

function splitPasteLine(line: string): string[] {
  if (line.includes('\t')) return line.split('\t').map((cell) => cell.trim())
  if (line.includes('，')) return line.split('，').map((cell) => cell.trim())
  if (line.includes(',')) return line.split(',').map((cell) => cell.trim())
  return [line.trim()]
}
function parseNumeric(raw: string): number | null {
  const text = (raw || '').replace(/,/g, '')
  const match = text.match(/[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?/)
  if (!match) return null
  const value = Number(match[0])
  return Number.isFinite(value) ? value : null
}
function pasteEntry(token: string, raw: string): PasteEntry {
  const meta = featureLookup.value.get(normalizeToken(token)) || null
  const number = parseNumeric(raw)
  return {
    token: token.trim(),
    value: number === null ? String(raw || '').trim() : String(number),
    meta,
    invalid: !meta || number === null,
  }
}
function parsePaste(text: string): PasteEntry[] {
  const lines = text.split(/\r?\n/).filter((line) => line.trim())
  if (!lines.length) return []
  const firstCells = splitPasteLine(lines[0])
  const headerMatches = firstCells.filter((cell) => featureLookup.value.get(normalizeToken(cell))).length
  // Horizontal mode: a header row with at least two recognizable metric names.
  if (firstCells.length >= 2 && headerMatches >= 2) {
    const valueCells = splitPasteLine(lines[1] || '')
    return firstCells.map((token, index) => pasteEntry(token, valueCells[index] || ''))
  }
  const entries: PasteEntry[] = []
  const headerTokens = new Set(['指标', '项目', '名称', '指标名称'])
  for (const line of lines) {
    let cells = splitPasteLine(line)
    let token = ''
    let raw = ''
    if (cells.length >= 2) {
      token = cells[0]
      raw = cells[1]
    } else {
      const match = line.match(/^(.*?)[\s:：]+([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?.*)$/)
      if (match) {
        token = match[1]
        raw = match[2]
      } else {
        token = line
      }
    }
    if (headerTokens.has(normalizeToken(token))) continue
    if (!token.trim() && !raw.trim()) continue
    entries.push(pasteEntry(token, raw))
  }
  return entries
}

function openPaste() {
  pasteText.value = ''
  pasteError.value = ''
  pasteOverwrite.value = false
  showPaste.value = true
  nextTick(() => {
    (document.getElementById('paste-metrics') as HTMLTextAreaElement | null)?.focus()
  })
}
function applyPaste() {
  pasteError.value = ''
  if (!pasteText.value.trim()) { pasteError.value = '请先粘贴表格内容'; return }
  if (!pasteMatched.value.length) { pasteError.value = '未识别到可填写的指标，请检查指标名称和数值'; return }
  let applied = 0
  let skipped = 0
  for (const entry of pasteMatched.value) {
    if (!entry.meta) continue
    const current = values[entry.meta.name]
    if (!pasteOverwrite.value && current !== '' && current != null) {
      skipped += 1
      continue
    }
    values[entry.meta.name] = entry.value
    applied += 1
  }
  if (!applied) {
    pasteError.value = skipped
      ? `已填写的 ${skipped} 项未覆盖，请勾选“覆盖已填写项”后重试`
      : '没有可应用的指标'
    return
  }
  markDirty()
  showPaste.value = false
  notice.value = `已从粘贴表格填入 ${applied} 项指标${skipped ? `，跳过 ${skipped} 项已填写项` : ''}。`
  ElMessage.success('指标已填入')
}

async function loadPrevious(current: any) {
  previousLoading.value = true
  previousEncounter.value = null
  try {
    const list = await api.encounters(current.patient_id)
    const currentTime = new Date(current.occurred_at).getTime()
    const prior = (list.encounters ?? [])
      .filter((item: any) => item.id !== current.id)
      .filter((item: any) => {
        const time = new Date(item.occurred_at).getTime()
        return Number.isFinite(time) && (!Number.isFinite(currentTime) || time < currentTime)
      })[0]
    if (prior) previousEncounter.value = await api.encounter(prior.id)
  } catch {
    previousEncounter.value = null
  } finally {
    previousLoading.value = false
  }
}

function copyPrevious() {
  error.value = ''
  if (!previousEncounter.value) { error.value = '没有可复制的上次就诊'; return }
  if (!canEdit.value || metricsLocked.value) { error.value = '报告已发布，请先继续修订'; return }
  let copied = 0
  let kept = 0
  for (const meta of metas.value) {
    const raw = previousEncounter.value.values?.[meta.name]
    if (raw === null || raw === undefined || raw === '') continue
    const current = values[meta.name]
    if (current !== '' && current != null) { kept += 1; continue }
    values[meta.name] = String(raw)
    copied += 1
  }
  if (!copied) {
    notice.value = kept ? `上次就诊的指标已全部存在，未覆盖当前 ${kept} 项已填值。` : '上次就诊没有可复制的指标。'
    return
  }
  markDirty()
  notice.value = `已从上次就诊填入 ${copied} 项指标${kept ? `，保留 ${kept} 项已填值` : ''}。`
  ElMessage.success('已填入上次指标')
}

function hydratePayload(payload: any) {
  const sourceValues = payload?.values ?? encounter.value?.values ?? {}
  for (const name of allFeatures.value) {
    const v = sourceValues?.[name]
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
    const currentReview = enc.latest_review?.prediction_id === enc.latest_prediction?.id ? enc.latest_review : null
    reviewDone.value = Boolean(currentReview && ['reviewed', 'published'].includes(enc.status))
    reviewDecision.value = currentReview?.decision ?? (enc.latest_prediction ? 'agree' : 'manual')
    reviewReason.value = currentReview?.reason ?? ''
    missingAck.value = enc.status === 'published'
    if (enc.status === 'published' || enc.latest_review) {
      checklist.value = await api.checklist(enc.id, enc.status === 'published').catch(() => null)
    }
    await loadPrevious(enc)
  } catch (e: any) {
    error.value = e?.message ?? '接诊记录加载失败'
  } finally {
    loading.value = false
  }
}

async function persistDraft(silent = false): Promise<boolean> {
  error.value = ''
  if (!canEdit.value) { error.value = '当前账号对该患者只有只读权限'; return false }
  if (metricsLocked.value) { error.value = '报告已发布，请先继续修订'; return false }
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
    if (!silent) {
      notice.value = `草稿已保存（版本 ${draftVersion.value}）`
      ElMessage.success('草稿已保存')
    }
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
  if (metricsLocked.value) { error.value = '报告已发布，请先继续修订'; return }
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
    reviewDone.value = false
    encounter.value.latest_review = null
    reviewDecision.value = 'agree'
    reviewReason.value = ''
    checklist.value = null
    notice.value = `模型评估完成：${result.prediction.risk_level}风险，缺失指标 ${result.prediction.missing_filled?.length ?? 0} 项已按中位数填充。`
    ElMessage.success('模型评估完成')
  } catch (e: any) {
    error.value = e?.message ?? '预测失败'
  } finally {
    predicting.value = false
  }
}

async function submitReview() {
  error.value = ''
  if (reviewDone.value) { error.value = '本次就诊已经完成复核'; return }
  if (reviewDecision.value !== 'agree' && !reviewReason.value.trim()) {
    error.value = '调整、暂不发布或人工记录必须填写理由'
    return
  }
  const saved = await persistDraft(true)
  if (!saved) return
  reviewing.value = true
  try {
    const res = await api.review(encounter.value.id, {
      row_version: rowVersion.value,
      decision: reviewDecision.value,
      reason: reviewReason.value.trim(),
    })
    encounter.value = { ...encounter.value, ...res }
    rowVersion.value = res.row_version
    reviewDone.value = res.status === 'reviewed'
    checklist.value = await api.checklist(encounter.value.id, missingAck.value)
    notice.value = res.status === 'reviewed' ? '医生复核已记录，可进行发布核对。' : '已记录暂不发布，可继续补录、评估与复核。'
    ElMessage.success('复核已记录')
  } catch (e: any) {
    error.value = e?.message ?? '复核失败'
  } finally {
    reviewing.value = false
  }
}

function reviseReview() {
  if (isPublished.value || !canEdit.value) return
  reviewDone.value = false
  notice.value = '可以更新复核结论。已发出的报告保持不变，再次发布会生成新版本。'
}

function startManualReview() {
  error.value = ''
  if (metricsLocked.value) { error.value = '报告已发布，请先继续修订'; return }
  if (measuredCount.value === 0) { error.value = '至少录入一项实测指标后才能人工记录'; return }
  reviewDecision.value = 'manual'
  notice.value = '已切换到人工记录，填写理由后提交复核。'
}

async function refreshChecklist() {
  try {
    checklist.value = await api.checklist(encounter.value.id, missingAck.value)
  } catch (e: any) {
    error.value = e?.message ?? '发布核对失败'
  }
}

async function reopenVisit() {
  if (!encounter.value?.id || reopening.value) return
  reopening.value = true
  error.value = ''
  try {
    const next = await api.reopenEncounter(encounter.value.id)
    encounter.value = { ...encounter.value, ...next, status: next.status }
    rowVersion.value = next.row_version
    notice.value = '已恢复为可编辑。已发布的报告不会被改写，再次发布会生成新版本。'
    ElMessage.success('可以继续编辑')
    await load()
  } catch (e: any) {
    error.value = e?.message ?? '无法恢复编辑'
  } finally {
    reopening.value = false
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
    ElMessage.success(`报告 ${res.report_no} 已发布`)
    await load()
  } catch (e: any) {
    publishError.value = e?.message ?? '发布失败'
  } finally {
    publishing.value = false
  }
}

async function downloadPdf() {
  const report = publishResult.value ?? latestReport.value
  if (!report) return
  try {
    const blob = await api.reportPdf(report.id)
    saveBlob(blob, `${report.report_no}.pdf`)
  } catch (e: any) {
    error.value = e?.message ?? '下载失败'
  }
}

function markDirty() { dirty.value = true }

function beforeUnload(event: BeforeUnloadEvent) {
  if (dirty.value) { event.preventDefault(); event.returnValue = '' }
}
onMounted(() => { load(); window.addEventListener('beforeunload', beforeUnload) })
onUnmounted(() => window.removeEventListener('beforeunload', beforeUnload))
</script>

<template>
  <div class="pilot-page encounter-pilot">
    <div class="pilot-page-inner">
      <header class="pilot-head encounter-head">
        <div>
          <RouterLink :to="encounter ? `/patients/${encounter.patient_id}` : '/patients'" class="pilot-link pilot-back">← 患者档案</RouterLink>
          <div class="pilot-kicker">围术期评估</div>
          <h1 class="pilot-title">接诊与风险报告</h1>
        </div>
        <div class="pilot-actions encounter-head-actions" v-if="encounter">
          <span class="pilot-chip" :class="isPublished ? 'pilot-chip-accent' : ''">{{ statusText[encounter.status] ?? encounter.status }}</span>
          <button v-if="!isPublished" class="pilot-btn" type="button" :disabled="saving || !canEdit" @click="persistDraft(false)">{{ saving ? '保存中…' : '保存草稿' }}</button>
          <button v-else class="pilot-btn" type="button" :disabled="reopening || !canEdit" @click="reopenVisit">{{ reopening ? '恢复中…' : '继续修订' }}</button>
          <button class="pilot-btn" type="button" :disabled="loading" @click="load">重新载入</button>
        </div>
      </header>

      <div v-if="error" class="pilot-error">{{ error }}</div>
      <div v-if="notice" class="pilot-notice">{{ notice }}</div>
      <div v-if="loading" class="pilot-panel pilot-loading">正在载入接诊记录…</div>

      <template v-else-if="encounter">
        <section class="patient-banner">
          <div class="banner-main">
            <div class="banner-name">{{ encounter.patient_name }}<span class="banner-mrn pilot-mono">{{ encounter.mrn }}</span></div>
            <div class="banner-meta">
              <span>就诊 <b class="pilot-mono">{{ encounter.case_ref }}</b></span>
              <span>时间 <b>{{ fmt(encounter.occurred_at) }}</b></span>
              <span>手术 <b>{{ encounter.surgery_type || '未填写' }}</b></span>
              <span>创建人 <b>{{ encounter.created_by_name || encounter.created_by || '—' }}</b></span>
            </div>
          </div>
          <div class="banner-risk">
            <span class="banner-risk-label">{{ isManualPrediction ? '医生人工记录' : '模型风险估计' }}</span>
            <span class="banner-prob">{{ probabilityText }}</span>
            <span class="pilot-chip" :class="riskTone === 'high' ? 'pilot-chip-high' : riskTone === 'mid' ? 'pilot-chip-mid' : riskTone === 'low' ? 'pilot-chip-low' : 'pilot-chip-accent'">{{ riskText }}</span>
          </div>
        </section>

        <div v-if="!canEdit" class="pilot-error">当前账号对该患者只有只读权限，无法修改就诊或发布报告。</div>

        <nav class="encounter-steps" aria-label="接诊流程">
          <a href="#encounter-document"><span>01</span> 就诊文书</a>
          <a href="#encounter-metrics"><span>02</span> 指标录入</a>
          <a href="#encounter-review"><span>03</span> 医生复核</a>
          <a v-if="reviewDone && checklist" href="#encounter-publish"><span>04</span> 发布核对</a>
          <span v-else class="encounter-step-disabled" aria-disabled="true">04 · 复核后发布</span>
        </nav>
        <div class="encounter-layout">
          <main class="encounter-main">
            <section id="encounter-document" class="pilot-panel">
              <div class="pilot-panel-head">
                <span class="pilot-panel-title">本次就诊文书</span>
                <span class="pilot-muted">记录 v{{ rowVersion }} · 草稿 v{{ draftVersion }}</span>
              </div>
              <div class="pilot-panel-body doc-grid">
                <div class="form-field">
                  <label for="enc-diagnosis">临床诊断（写入正式报告）</label>
                  <textarea id="enc-diagnosis" v-model="diagnosis" class="pilot-textarea encounter-note" rows="4" :disabled="!canEdit || metricsLocked" placeholder="在此输入诊断。灰字只是示例，不会保存。" @input="markDirty" />
                  <p class="note-hint">框内灰字是示例。点进去输入后才会写入报告，回车用于换行。</p>
                </div>
                <div class="form-field">
                  <label for="enc-orders">医嘱 / 随访建议（写入正式报告）</label>
                  <textarea id="enc-orders" v-model="orders" class="pilot-textarea encounter-note" rows="4" :disabled="!canEdit || metricsLocked" placeholder="在此输入医嘱。灰字只是示例，不会保存。" @input="markDirty" />
                </div>
              </div>
            </section>

            <section id="encounter-metrics" class="pilot-panel metrics-panel">
              <div class="pilot-panel-head metrics-head">
                <div class="metrics-title">
                  <span class="pilot-panel-title">围手术期指标</span>
                  <span class="pilot-chip pilot-chip-accent">{{ measuredCount }} 项实测 / {{ allFeatures.length }} 项</span>
                </div>
                <div class="metrics-head-side">
                  <span v-if="metricsLocked" class="pilot-muted">已发布，指标锁定</span>
                  <div class="metric-tools">
                    <button
                      class="pilot-btn pilot-btn-sm"
                      type="button"
                      :disabled="!canEdit || metricsLocked || !previousEncounter || previousLoading"
                      :title="previousLabel"
                      @click="copyPrevious"
                    >
                      {{ previousLoading ? '查找上次…' : '复制上次就诊' }}
                    </button>
                    <button class="pilot-btn pilot-btn-sm" type="button" :disabled="!canEdit || metricsLocked" @click="openPaste">
                      粘贴表格
                    </button>
                  </div>
                </div>
              </div>
              <div class="pilot-panel-body">
                <div class="metric-progress">
                  <div class="metric-track"><span :style="{ width: `${allFeatures.length ? filledCount / allFeatures.length * 100 : 0}%` }" /></div>
                  <span>{{ invalidCount() ? `${invalidCount()} 项超范围` : '数值需在参考范围内' }}</span>
                </div>
                <div class="metric-source">
                  <span class="pilot-muted">{{ previousLabel }}</span>
                  <span class="pilot-muted">复制上次就诊只补空项，不覆盖已填值。</span>
                </div>
                <p class="rail-hint">请按术前、术中、入 ICU 和术后核对指标时点。本系统未逐项记录采样时间，需结合原始病历确认。</p>
                <div v-if="invalidCount()" class="pilot-error metric-error">有 {{ invalidCount() }} 项数值超出临床合理范围，请修正后再保存或预测。</div>

                <div v-for="g in groups" :key="g.key" class="metric-group">
                  <button class="metric-group-head" type="button" :aria-expanded="!collapsed[g.key]" @click="collapsed[g.key] = !collapsed[g.key]">
                    <span class="metric-group-title">{{ g.label }}</span>
                    <span class="metric-group-meta">{{ g.features.length }} 项 · {{ g.desc }}</span>
                    <span class="metric-chevron" :class="{ open: !collapsed[g.key] }">›</span>
                  </button>
                  <div v-if="!collapsed[g.key]" class="metric-rows">
                    <div v-for="m in g.features" :key="m.name" class="metric-row">
                      <div class="metric-label">
                        <span>{{ fieldLabel(m) }}</span>
                        <span v-if="fieldUnit(m)" class="metric-unit">{{ fieldUnit(m) }}</span>
                        <span class="metric-ref">{{ fieldReference(m) }}</span>
                      </div>
                      <input v-model="values[m.name]" class="pilot-input metric-input" :class="{ 'metric-input-bad': isInvalid(m) }" type="number" step="any" :disabled="!canEdit || metricsLocked" @input="markDirty" />
                      <span class="metric-state" :class="{ bad: isInvalid(m) }">{{ isInvalid(m) ? '超范围' : (values[m.name] ? '已填' : '缺失') }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </section>
          </main>

          <aside class="risk-rail">
            <section class="pilot-panel rail-panel">
              <div class="pilot-panel-head">
                <span class="pilot-panel-title">{{ isManualPrediction ? '人工记录' : '模型评估结果' }}</span>
                <span class="pilot-muted">{{ hasModelPrediction ? '已运行模型' : isManualPrediction ? '人工记录' : '尚未运行' }}</span>
              </div>
              <div class="pilot-panel-body">
                <div class="risk-value" :class="`risk-${riskTone}`">
                  <div class="risk-prob">{{ probabilityText }}</div>
                  <div class="risk-name">{{ riskText }}</div>
                </div>
                <dl class="risk-meta">
                  <div><dt>二分类</dt><dd>{{ binaryText }}</dd></div>
                  <div><dt>概率校准</dt><dd>{{ calibratedText }}</dd></div>
                  <div><dt>当前输入实测</dt><dd>{{ measuredCount }} 项</dd></div>
                  <div v-if="hasModelPrediction"><dt>结果使用填充</dt><dd>{{ missingCount }} 项（非实测）</dd></div>
                  <div v-if="hasPrediction"><dt>评估时间</dt><dd>{{ fmt(activePrediction?.predicted_at) }}</dd></div>
                  <div v-if="hasModelPrediction"><dt>模型版本</dt><dd class="pilot-mono" style="overflow-wrap:anywhere">{{ activePrediction?.model_version || '—' }}</dd></div>
                  <div><dt>预测编号</dt><dd class="pilot-mono">{{ encounter.current_prediction_id || '—' }}</dd></div>
                </dl>
                <div class="rail-follow">
                  <p v-if="hasModelPrediction" class="rail-hint">模型风险估计供医生复核，临床诊断与医嘱在就诊文书中单独记录。</p>
                  <p v-if="hasModelPrediction && dirty" class="rail-warning">当前页面有未保存修改，以上为上次运行结果。请保存并核对指标是否需要重新评估。</p>
                  <details v-if="hasModelPrediction && missingCount">
                    <summary>查看 {{ missingCount }} 项非实测输入</summary>
                    <p>{{ (activePrediction?.missing_filled ?? []).map(shapLabel).join('、') }}。模型按训练中位数填充。</p>
                  </details>
                  <RouterLink to="/assessment-guide" class="pilot-link">评估说明与使用局限 →</RouterLink>
                  <div class="rail-actions">
                    <button class="pilot-btn pilot-btn-primary" type="button" :disabled="predicting || !canEdit || metricsLocked" @click="runPrediction">
                      {{ predicting ? '计算中…' : (hasPrediction ? '重新运行模型' : '运行模型') }}
                    </button>
                    <button v-if="!hasPrediction && !reviewDone" class="pilot-btn" type="button" :disabled="!canEdit || measuredCount === 0" @click="startManualReview">无模型时人工记录</button>
                    <button class="pilot-btn" type="button" :disabled="saving || !canEdit || metricsLocked" @click="persistDraft(false)">{{ saving ? '保存中…' : '保存草稿' }}</button>
                  </div>
                  <p v-if="isPublished" class="rail-hint">报告已发布，内容已锁定。点“继续修订”后可再编辑；已发出的报告保持不变，再次发布会生成新版本。</p>
                  <p v-else-if="reviewDone" class="rail-hint">复核之后仍可修改诊断、医嘱和指标。改过指标后需要重新运行模型并再次复核，才能发布。</p>
                </div>
              </div>
            </section>

            <section v-if="shapRows.length" class="pilot-panel rail-panel">
              <div class="pilot-panel-head"><span class="pilot-panel-title">主要影响因素</span><span class="pilot-muted">SHAP</span></div>
              <div class="pilot-panel-body shap-list">
                <div v-for="s in shapRows" :key="s.feature" class="shap-row">
                  <div class="shap-name">
                    {{ shapLabel(s.feature) }}
                    <span v-if="isFilledFeature(s.feature)" class="pilot-chip">填充值</span>
                  </div>
                  <div class="shap-track"><span :style="{ width: `${Math.abs(s.shap) / maxShap * 100}%`, background: s.shap >= 0 ? 'var(--pilot-high)' : 'var(--pilot-low)' }" /></div>
                  <div class="shap-value" :class="{ risk: s.shap >= 0 }">{{ s.shap >= 0 ? '+' : '−' }}{{ Math.abs(s.shap).toFixed(3) }}</div>
                </div>
              </div>
            </section>

            <section id="encounter-review" class="pilot-panel rail-panel">
              <div class="pilot-panel-head">
                <span class="pilot-panel-title">医生复核</span>
                <span class="pilot-chip" :class="reviewDone ? 'pilot-chip-low' : ''">{{ reviewDone ? '已复核' : encounter.latest_review?.decision === 'defer' ? '暂不发布' : '待复核' }}</span>
              </div>
              <div class="pilot-panel-body review-form">
                <div v-if="!hasPrediction && !reviewDone" class="rail-warning">没有有效模型结果。确需继续时，选择“无模型结果，人工记录”并填写理由。</div>
                <div class="form-field">
                  <label for="review-decision">复核结论</label>
                  <select id="review-decision" v-model="reviewDecision" class="pilot-select" :disabled="reviewDone || isPublished || !canEdit">
                    <option v-for="o in reviewOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
                  </select>
                </div>
                <div class="form-field">
                  <label for="reviewer">复核人</label>
                  <input id="reviewer" class="pilot-input" :value="encounter.latest_review?.reviewer_name || '当前登录医生'" disabled />
                </div>
                <div class="form-field">
                  <label for="review-reason">复核意见 {{ reviewDecision !== 'agree' ? '（必填）' : '（可选）' }}</label>
                  <textarea id="review-reason" v-model="reviewReason" class="pilot-textarea" rows="3" :disabled="reviewDone || isPublished || !canEdit" placeholder="说明采纳、调整或暂不发布的依据" />
                </div>
                <button v-if="!reviewDone && !isPublished" class="pilot-btn pilot-btn-primary" type="button" :disabled="reviewing || !canEdit" @click="submitReview">{{ reviewing ? '提交中…' : '记录复核' }}</button>
                <button v-else-if="reviewDone && !isPublished" class="pilot-btn" type="button" :disabled="!canEdit" @click="reviseReview">重新复核</button>
                <div v-if="encounter.latest_review && encounter.latest_review.prediction_id === activePrediction?.id" class="review-record">
                  已由 {{ encounter.latest_review.reviewer_name }} 于 {{ fmt(encounter.latest_review.created_at) }} 记录：{{ decisionText[encounter.latest_review.decision] || encounter.latest_review.decision }}。{{ encounter.latest_review.reason }}
                </div>
              </div>
            </section>

            <section id="encounter-publish" v-if="reviewDone && checklist" class="pilot-panel rail-panel">
              <div class="pilot-panel-head">
                <span class="pilot-panel-title">发布核对</span>
                <button class="pilot-btn pilot-btn-ghost" type="button" @click="refreshChecklist">重新核对</button>
              </div>
              <div class="pilot-panel-body checklist-body">
                <div v-for="item in checklist.items" :key="item.key" class="check-row">
                  <span class="check-mark" :class="{ ok: item.ok }">{{ item.ok ? '✓' : '!' }}</span>
                  <div><div class="check-label">{{ item.label }}</div><div v-if="item.detail" class="check-detail">{{ item.detail }}</div></div>
                </div>
                <label v-if="checklist.missing_count" class="check-ack">
                  <input v-model="missingAck" type="checkbox" @change="refreshChecklist" />
                  <span v-if="isManualPrediction">这些指标没有实测，人工记录不使用模型填充值。</span>
                  <span v-else>我已确认 {{ checklist.missing_count }} 项指标缺失，模型按训练中位数填充。</span>
                </label>
                <div v-if="publishError" class="pilot-error publish-error">{{ publishError }}</div>
                <div v-if="isPublished && latestReport" class="publish-result">
                  正式报告已发布：<strong>{{ latestReport.report_no }}</strong>（v{{ latestReport.version }}）。
                  <div class="publish-actions">
                    <button class="pilot-btn pilot-btn-primary" type="button" @click="downloadPdf">下载 PDF</button>
                    <RouterLink :to="`/reports/${latestReport.id}`" class="pilot-btn">查看报告</RouterLink>
                  </div>
                </div>
                <div v-else-if="publishResult" class="publish-result">
                  正式报告已发布：<strong>{{ publishResult.report_no }}</strong>（v{{ publishResult.version }}）。
                  <div class="publish-actions">
                    <button class="pilot-btn pilot-btn-primary" type="button" @click="downloadPdf">下载 PDF</button>
                    <RouterLink :to="`/reports/${publishResult.id}`" class="pilot-btn">查看报告</RouterLink>
                  </div>
                </div>
                <button v-if="!isPublished" class="pilot-btn pilot-btn-primary publish-btn" type="button" :disabled="publishing || !checklist?.can_publish || !canEdit" @click="publishReport">{{ publishing ? '发布中…' : '发布正式报告' }}</button>
              </div>
            </section>
          </aside>
        </div>
      </template>
    </div>

    <ElDialog
      v-model="showPaste"
      title="粘贴表格填指标"
      width="680px"
      class="pilot-dialog"
      :close-on-click-modal="false"
      append-to-body
    >
      <p class="paste-copy">支持两列（指标名称 + 数值），也支持一行表头 + 一行数值；可直接从 Excel 复制。识别中文指标名或英文特征名，数值可带单位。</p>
      <textarea
        id="paste-metrics"
        v-model="pasteText"
        class="pilot-textarea paste-input"
        rows="8"
        placeholder="术前肌酐&#9;88&#10;术前 eGFR&#9;92&#10;或：&#10;术前肌酐&#9;术前 eGFR&#10;88&#9;92"
      />
      <label class="paste-overwrite">
        <input v-model="pasteOverwrite" type="checkbox" />
        覆盖当前已填写的指标
      </label>
      <div v-if="pasteText.trim()" class="paste-result">
        <div v-if="pasteMatched.length" class="paste-matched">
          <div class="paste-result-head"><span>可填入 {{ pasteMatched.length }} 项</span><span class="pilot-muted">数值已自动截取</span></div>
          <div class="paste-tags">
            <span v-for="entry in pasteMatched" :key="`${entry.token}-${entry.meta?.name}`" class="paste-tag">
              {{ entry.meta?.label || entry.token }} <b>{{ entry.value }}</b>
            </span>
          </div>
        </div>
        <div v-if="pasteUnmatched.length" class="paste-unmatched">
          <div class="paste-result-head"><span>未识别 {{ pasteUnmatched.length }} 项</span><span class="pilot-muted">请检查名称或数值</span></div>
          <div class="paste-tags">
            <span v-for="entry in pasteUnmatched" :key="`${entry.token}-${entry.value}`" class="paste-tag is-bad">
              {{ entry.token || '空名称' }} <b>{{ entry.value || '无数值' }}</b>
            </span>
          </div>
        </div>
      </div>
      <div v-if="pasteError" class="pilot-error paste-error" role="alert">{{ pasteError }}</div>
      <template #footer>
        <div class="dialog-actions">
          <button class="pilot-btn" type="button" @click="showPaste = false">取消</button>
          <button class="pilot-btn pilot-btn-primary" type="button" :disabled="!pasteMatched.length" @click="applyPaste">
            填入 {{ pasteMatched.length }} 项
          </button>
        </div>
      </template>
    </ElDialog>
  </div>
</template>

<style scoped>
.encounter-head-actions { gap: var(--pilot-space-4); }
.note-hint { margin: 6px 0 0; color: var(--pilot-muted); font-size: var(--pilot-font-xs); line-height: 1.5; }
.encounter-note { min-height: 96px; }
.encounter-steps{display:flex;flex-wrap:wrap;gap:8px;padding:12px 16px;margin:16px 0 24px;background:var(--pilot-surface);border:1px solid var(--pilot-line);border-radius:var(--pilot-radius-card)}
.encounter-steps a{display:flex;align-items:center;gap:10px;flex:1;min-width:135px;padding:8px;color:var(--pilot-ink-soft);text-decoration:none;font-size:13px}.encounter-steps a:hover{color:var(--pilot-accent);background:var(--pilot-accent-soft);border-radius:var(--pilot-radius-control)}.encounter-steps span{color:var(--pilot-accent);font-variant-numeric:tabular-nums}.encounter-pilot section[id]{scroll-margin-top:90px}
.encounter-steps .encounter-step-disabled{flex:1;min-width:135px;padding:8px;color:var(--pilot-muted);font-size:13px;align-self:center}
.encounter-head { margin-bottom: var(--pilot-space-3); }
.pilot-back { display: inline-block; margin-bottom: var(--pilot-space-2); font-size: var(--pilot-font-xs); }
.pilot-loading { padding: var(--pilot-space-7); color: var(--pilot-muted); text-align: center; }

.patient-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--pilot-space-4);
  flex-wrap: wrap;
  margin-bottom: var(--pilot-space-4);
  padding: var(--pilot-space-4) var(--pilot-space-5);
  border: 1px solid var(--pilot-line);
  border-left: 4px solid var(--pilot-accent);
  border-radius: var(--pilot-radius-card);
  background: var(--pilot-surface);
  box-shadow: var(--pilot-shadow);
}
.banner-name { display: flex; align-items: baseline; gap: var(--pilot-space-3); flex-wrap: wrap; color: var(--pilot-ink); font-size: var(--pilot-font-lg); font-weight: 700; }
.banner-mrn { color: var(--pilot-muted); font-size: var(--pilot-font-sm); font-weight: 500; }
.banner-meta { display: flex; gap: var(--pilot-space-4); flex-wrap: wrap; margin-top: var(--pilot-space-2); color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
.banner-meta b { color: var(--pilot-ink-soft); font-weight: 600; }
.banner-risk { display: flex; align-items: center; gap: var(--pilot-space-2); }
.banner-risk-label { color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
.banner-prob { color: var(--pilot-ink); font-size: var(--pilot-font-lg); font-weight: 700; }

.encounter-layout { display: grid; grid-template-columns: minmax(0, 1fr) 360px; gap: var(--pilot-space-4); align-items: start; }
.encounter-main { display: flex; flex-direction: column; gap: var(--pilot-space-4); min-width: 0; }
.risk-rail { position: sticky; top: var(--pilot-space-4); display: flex; flex-direction: column; gap: var(--pilot-space-4); min-width: 0; }
.rail-panel { margin: 0; }

.doc-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--pilot-space-4); }
.form-field { display: flex; flex-direction: column; gap: var(--pilot-space-2); }
.form-field label { color: var(--pilot-ink-soft); font-size: var(--pilot-font-xs); font-weight: 600; }

.metrics-title { display: flex; align-items: center; gap: var(--pilot-space-2); flex-wrap: wrap; }
.metrics-head { align-items: flex-start; }
.metrics-head-side { display: flex; flex-direction: column; align-items: flex-end; gap: var(--pilot-space-2); }
.metric-tools { display: flex; gap: var(--pilot-space-2); flex-wrap: wrap; justify-content: flex-end; }
.metric-progress { display: flex; align-items: center; gap: var(--pilot-space-3); margin-bottom: var(--pilot-space-2); color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
.metric-track { flex: 1; height: 4px; border-radius: 999px; background: var(--pilot-surface-2); overflow: hidden; }
.metric-track span { display: block; height: 100%; background: var(--pilot-accent); }
.metric-source { display: flex; flex-wrap: wrap; justify-content: space-between; gap: var(--pilot-space-1) var(--pilot-space-3); margin-bottom: var(--pilot-space-3); font-size: var(--pilot-font-xs); }
.metric-source .pilot-muted:last-child { text-align: right; }
.metric-error { margin-bottom: var(--pilot-space-3); }

.metric-group { margin-bottom: var(--pilot-space-3); border: 1px solid var(--pilot-line); border-radius: var(--pilot-radius-control); overflow: hidden; }
.metric-group:last-child { margin-bottom: 0; }
.metric-group-head {
  display: flex;
  align-items: center;
  gap: var(--pilot-space-3);
  width: 100%;
  min-height: 44px;
  padding: 0 var(--pilot-space-4);
  border: 0;
  border-bottom: 1px solid var(--pilot-line);
  background: var(--pilot-surface-2);
  color: var(--pilot-ink);
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.metric-group-title { font-weight: 700; }
.metric-group-meta { flex: 1; color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
.metric-chevron { color: var(--pilot-muted); transition: transform .15s; }
.metric-chevron.open { transform: rotate(90deg); }
.metric-rows { background: var(--pilot-surface); }
.metric-row {
  display: grid;
  grid-template-columns: minmax(180px, 1.3fr) 128px 64px;
  align-items: center;
  gap: var(--pilot-space-3);
  min-height: 56px;
  padding: var(--pilot-space-2) var(--pilot-space-4);
  border-bottom: 1px solid var(--pilot-line);
}
.metric-row:last-child { border-bottom: 0; }
.metric-label { display: flex; align-items: baseline; gap: var(--pilot-space-2); flex-wrap: wrap; min-width: 0; }
.metric-label > span:first-child { color: var(--pilot-ink); font-weight: 600; }
.metric-unit { color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
.metric-ref { width: 100%; color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
.metric-input { height: 40px; text-align: right; font-variant-numeric: tabular-nums; }
.metric-input-bad { border-color: var(--pilot-high); background: var(--pilot-high-soft); }
.metric-state { color: var(--pilot-muted); font-size: var(--pilot-font-xs); text-align: right; }
.metric-state.bad { color: var(--pilot-high); font-weight: 600; }

.risk-value { padding: var(--pilot-space-4); border: 1px solid var(--pilot-line); border-left: 4px solid var(--pilot-line-strong); border-radius: var(--pilot-radius-control); background: var(--pilot-surface-2); }
.risk-high { border-left-color: var(--pilot-high); background: var(--pilot-high-soft); }
.risk-mid { border-left-color: var(--pilot-mid); background: var(--pilot-mid-soft); }
.risk-low { border-left-color: var(--pilot-low); background: var(--pilot-low-soft); }
.risk-none { border-left-color: var(--pilot-line-strong); }
.risk-prob { color: var(--pilot-ink); font-size: var(--pilot-font-xl); font-weight: 700; line-height: 1.2; font-variant-numeric: tabular-nums; }
.risk-name { margin-top: var(--pilot-space-1); color: var(--pilot-ink-soft); font-size: var(--pilot-font-md); font-weight: 600; }
.risk-meta { display: grid; grid-template-columns: 1fr 1fr; gap: var(--pilot-space-3); margin: var(--pilot-space-4) 0; }
.risk-meta div { min-width: 0; }
.risk-meta dt { color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
.risk-meta dd { margin-top: var(--pilot-space-1); overflow: hidden; color: var(--pilot-ink); font-size: var(--pilot-font-xs); font-weight: 600; text-overflow: ellipsis; }
.rail-follow {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: var(--pilot-space-4);
}
.rail-follow .pilot-link { align-self: flex-start; }
.rail-follow details summary { cursor: pointer; line-height: 1.6; }
.rail-follow details p { margin: var(--pilot-space-3) 0 0; color: var(--pilot-muted); font-size: var(--pilot-font-xs); line-height: 1.6; }
.rail-actions { display: flex; flex-direction: column; gap: var(--pilot-space-3); }
.rail-hint { margin: 0; color: var(--pilot-muted); font-size: var(--pilot-font-xs); line-height: 1.6; }

.shap-list { display: flex; flex-direction: column; gap: var(--pilot-space-3); }
.shap-row { display: grid; grid-template-columns: minmax(0, 1fr) 72px; gap: var(--pilot-space-2); align-items: center; }
.shap-name { display: flex; align-items: center; gap: var(--pilot-space-2); overflow: hidden; color: var(--pilot-ink-soft); font-size: var(--pilot-font-xs); text-overflow: ellipsis; white-space: nowrap; }
.shap-track { grid-column: 1 / -1; height: 3px; border-radius: 999px; background: var(--pilot-surface-2); overflow: hidden; }
.shap-track span { display: block; height: 100%; }
.shap-value { grid-row: 1; grid-column: 2; color: var(--pilot-low); font-size: var(--pilot-font-xs); text-align: right; font-variant-numeric: tabular-nums; }
.shap-value.risk { color: var(--pilot-high); }

.review-form { display: flex; flex-direction: column; gap: var(--pilot-space-3); }
.rail-warning { padding: var(--pilot-space-2) var(--pilot-space-3); border: 1px solid var(--pilot-mid); border-radius: var(--pilot-radius-control); background: var(--pilot-mid-soft); color: var(--pilot-mid); font-size: var(--pilot-font-xs); }
.review-record { padding: var(--pilot-space-3); border: 1px solid var(--pilot-line); border-radius: var(--pilot-radius-control); background: var(--pilot-surface-2); color: var(--pilot-ink-soft); font-size: var(--pilot-font-xs); line-height: 1.6; }

.checklist-body { display: flex; flex-direction: column; gap: var(--pilot-space-3); }
.publish-btn { margin-top: var(--pilot-space-2); }
.check-row { display: flex; align-items: flex-start; gap: var(--pilot-space-2); }
.check-mark { display: inline-flex; align-items: center; justify-content: center; width: 16px; height: 16px; flex-shrink: 0; border-radius: 50%; background: var(--pilot-mid-soft); color: var(--pilot-mid); font-size: var(--pilot-font-xs); font-weight: 700; }
.check-mark.ok { background: var(--pilot-low-soft); color: var(--pilot-low); }
.check-label { color: var(--pilot-ink-soft); font-size: var(--pilot-font-xs); font-weight: 600; }
.check-detail { color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
.check-ack { display: flex; align-items: flex-start; gap: var(--pilot-space-2); margin-top: var(--pilot-space-2); color: var(--pilot-ink-soft); font-size: var(--pilot-font-xs); line-height: 1.5; }
.check-ack input { margin-top: 2px; accent-color: var(--pilot-accent); }
.publish-error { margin: var(--pilot-space-2) 0 0; }
.publish-result { margin-top: var(--pilot-space-2); padding: var(--pilot-space-3); border: 1px solid var(--pilot-line); border-radius: var(--pilot-radius-control); background: var(--pilot-accent-soft); color: var(--pilot-ink-soft); font-size: var(--pilot-font-xs); line-height: 1.6; }
.publish-actions { display: flex; gap: var(--pilot-space-3); margin-top: var(--pilot-space-3); }
.dialog-actions { display: flex; justify-content: flex-end; gap: var(--pilot-space-4); }
.publish-btn { width: 100%; margin-top: var(--pilot-space-2); }

.paste-copy { margin: 0 0 var(--pilot-space-3); color: var(--pilot-ink-soft); font-size: var(--pilot-font-sm); line-height: 1.6; }
.paste-input { width: 100%; min-height: 180px; font-family: "SFMono-Regular", Consolas, monospace; font-size: var(--pilot-font-xs); line-height: 1.6; resize: vertical; }
.paste-overwrite { display: inline-flex; align-items: center; gap: var(--pilot-space-2); margin-top: var(--pilot-space-2); color: var(--pilot-ink-soft); font-size: var(--pilot-font-xs); }
.paste-overwrite input { accent-color: var(--pilot-accent); }
.paste-result { margin-top: var(--pilot-space-3); padding-top: var(--pilot-space-3); border-top: 1px dashed var(--pilot-line); }
.paste-matched + .paste-unmatched { margin-top: var(--pilot-space-3); }
.paste-result-head { display: flex; justify-content: space-between; gap: var(--pilot-space-2); margin-bottom: var(--pilot-space-2); color: var(--pilot-ink-soft); font-size: var(--pilot-font-xs); font-weight: 600; }
.paste-tags { display: flex; flex-wrap: wrap; gap: var(--pilot-space-2); }
.paste-tag { padding: 3px 8px; border: 1px solid var(--pilot-line); border-radius: 999px; background: var(--pilot-surface-2); color: var(--pilot-ink-soft); font-size: 11px; }
.paste-tag b { color: var(--pilot-ink); font-weight: 700; }
.paste-tag.is-bad { border-color: var(--pilot-high); color: var(--pilot-high); }
.paste-error { margin-top: var(--pilot-space-2); }

@media (max-width: 1180px) {
  .encounter-layout { grid-template-columns: minmax(0, 1fr); }
  .risk-rail { position: static; min-width: 0; }
  .doc-grid { grid-template-columns: 1fr; }
}
@media (max-width: 720px) {
  .metric-row { grid-template-columns: minmax(0, 1fr) 112px 56px; }
  .banner-risk { width: 100%; justify-content: flex-start; }
}
</style>

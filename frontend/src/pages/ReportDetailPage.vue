<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api, saveBlob } from '../api/client'
import { useAuth } from '../composables/useAuth'

type Tone = 'neutral' | 'low' | 'mid' | 'high' | 'accent'

const route = useRoute()
const auth = useAuth()
const loading = ref(true)
const error = ref('')
const notice = ref('')
const report = ref<any>(null)
const metas = ref<any[]>([])
const showRevoke = ref(false)
const revokeReason = ref('')
const revokeError = ref('')
const revoking = ref(false)
const downloading = ref(false)
const copied = ref(false)

const snapshot = computed(() => report.value?.snapshot ?? {})
const patient = computed(() => snapshot.value.patient ?? {})
const encounter = computed(() => snapshot.value.encounter ?? {})
const pred = computed(() => snapshot.value.prediction ?? {})
const result = computed(() => pred.value.result ?? {})
const review = computed(() => snapshot.value.review ?? {})
const values = computed(() => encounter.value.values ?? {})

const probability = computed(() => {
  const raw = report.value?.probability ?? result.value.probability
  if (raw === null || raw === undefined || raw === '') return null
  const value = Number(raw)
  return Number.isFinite(value) ? value : null
})
const probabilityText = computed(() => probability.value === null ? '—' : `${(probability.value * 100).toFixed(1)}%`)
const hasModel = computed(() => probability.value !== null && !result.value.manual)
const riskLevel = computed(() => report.value?.risk_level || result.value.risk_level)
const riskText = computed(() => {
  if (!riskLevel.value) return '未评估'
  return riskLevel.value === '人工审核' ? '人工审核' : `${riskLevel.value}风险`
})
const riskTone = computed<Tone>(() => {
  if (riskLevel.value === '高') return 'high'
  if (riskLevel.value === '中') return 'mid'
  if (riskLevel.value === '低') return 'low'
  return 'neutral'
})
const statusText = computed(() => report.value?.status === 'revoked' ? '已撤销' : '已发布')
const statusTone = computed<Tone>(() => report.value?.status === 'revoked' ? 'high' : 'accent')
const pageTitle = computed(() => report.value ? `正式报告 ${report.value.report_no}` : '正式报告')
const pageDescription = computed(() => report.value
  ? `${patient.value.name || '患者'} · 病历号 ${patient.value.mrn || '—'} · 第 ${report.value.version} 版`
  : '读取报告快照与完整性摘要。')

const metaMap = computed(() => Object.fromEntries(
  metas.value.map((meta) => [meta.name, meta]),
))
function featureLabel(name?: string) {
  if (!name) return '—'
  return metaMap.value[name]?.label || name
}
function featureUnit(name?: string) {
  if (!name) return ''
  return metaMap.value[name]?.unit || ''
}
const missingFeatures = computed<string[]>(() =>
  Array.isArray(snapshot.value.missing_features) ? snapshot.value.missing_features.filter(Boolean) : [],
)
const missingSet = computed(() => new Set(missingFeatures.value))
const missingRows = computed(() => missingFeatures.value.map((name: string) => ({
  name,
  label: featureLabel(name),
})))

const valueRows = computed(() => {
  const entries = Object.entries(values.value) as [string, any][]
  const order = new Map(metas.value.map((meta: any, index: number) => [meta.name, index]))
  return entries
    .filter(([, value]) => value !== null && value !== undefined && String(value).trim() !== '')
    .sort(([a], [b]) => (order.get(a) ?? 999) - (order.get(b) ?? 999))
    .map(([name, value]) => ({
      name,
      label: featureLabel(name),
      value: String(value),
      unit: featureUnit(name),
      missing: missingSet.value.has(name),
    }))
})

const shapRows = computed(() => {
  const source = Array.isArray(result.value.shap_values) ? result.value.shap_values : []
  return source
    .map((row: any) => {
      const value = Number(row.shap)
      return {
        feature: row.feature,
        label: featureLabel(row.feature),
        shap: Number.isFinite(value) ? value : 0,
        missing: missingSet.value.has(row.feature),
      }
    })
    .sort((a: any, b: any) => Math.abs(b.shap) - Math.abs(a.shap))
    .slice(0, 8)
})
const maxShap = computed(() => Math.max(1e-9, ...shapRows.value.map((row: any) => Math.abs(row.shap))))
function shapWidth(row: any) {
  return `${Math.min(100, (Math.abs(row.shap) / maxShap.value) * 100)}%`
}

const decisionLabels: Record<string, string> = {
  agree: '采纳模型结果',
  adjust: '调整风险判断',
  defer: '暂不发布',
  manual: '人工审核',
}
const reviewDecisionText = computed(() => {
  const value = review.value.decision
  return value ? (decisionLabels[value] || value) : '未记录'
})

function fmt(value?: string) {
  if (!value) return '—'
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString('zh-CN')
}
function val(value: any) {
  return value === null || value === undefined || value === '' ? '—' : value
}
function openRevoke() {
  revokeReason.value = ''
  revokeError.value = ''
  showRevoke.value = true
}
async function copyHash() {
  if (!report.value?.sha256) return
  error.value = ''
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(report.value.sha256)
    } else {
      const area = document.createElement('textarea')
      area.value = report.value.sha256
      area.setAttribute('readonly', '')
      area.style.position = 'fixed'
      area.style.opacity = '0'
      document.body.appendChild(area)
      area.select()
      document.execCommand('copy')
      area.remove()
    }
    copied.value = true
    window.setTimeout(() => { copied.value = false }, 1600)
  } catch {
    error.value = '摘要复制失败，请手动选择文本。'
  }
}
async function load() {
  loading.value = true
  error.value = ''
  try {
    const [detail, features] = await Promise.all([
      api.report(route.params.id as string),
      api.features().catch(() => null),
    ])
    report.value = detail
    metas.value = features?.metas ?? []
  } catch (e: any) {
    error.value = e?.message ?? '报告加载失败'
  } finally {
    loading.value = false
  }
}
async function download() {
  if (!report.value) return
  downloading.value = true
  error.value = ''
  try {
    const blob = await api.reportPdf(report.value.id)
    saveBlob(blob, `${report.value.report_no}.pdf`)
  } catch (e: any) {
    error.value = e?.message ?? '下载失败'
  } finally {
    downloading.value = false
  }
}
async function revoke() {
  if (!revokeReason.value.trim()) {
    revokeError.value = '请填写撤销原因'
    return
  }
  revoking.value = true
  revokeError.value = ''
  try {
    await api.revokeReport(report.value.id, revokeReason.value.trim())
    showRevoke.value = false
    revokeReason.value = ''
    await load()
    notice.value = '报告已撤销；患者端将不再显示这份报告。'
  } catch (e: any) {
    revokeError.value = e?.message ?? '撤销失败'
  } finally {
    revoking.value = false
  }
}
onMounted(load)
</script>

<template>
  <div class="pilot-page">
    <div class="pilot-page-inner report-page">
      <PageHeader
        kicker="文书 / 正式报告"
        :title="pageTitle"
        :description="pageDescription"
      >
        <template #actions>
          <RouterLink to="/reports" class="pilot-btn pilot-btn-ghost">← 报告列表</RouterLink>
          <button
            v-if="report"
            class="pilot-btn pilot-btn-primary"
            type="button"
            :disabled="report.status !== 'published' || downloading"
            @click="download"
          >{{ downloading ? '生成中…' : '下载 PDF' }}</button>
          <button
            v-if="report && auth.user.value?.role === 'admin' && report.can_revoke"
            class="pilot-btn report-revoke-btn"
            type="button"
            @click="openRevoke"
          >撤销报告</button>
        </template>
      </PageHeader>

      <div v-if="error" class="pilot-error" role="alert">{{ error }}</div>
      <div v-if="notice" class="pilot-notice" role="status">{{ notice }}</div>

      <div v-if="loading" class="report-loading">
        <div class="pilot-skeleton report-loading-cover" />
        <div class="pilot-skeleton report-loading-body" />
      </div>

      <article v-else-if="report" class="report-paper">
        <header class="report-cover">
          <div class="report-cover-top">
            <span class="report-kicker">AKI 围术期风险评估 · 正式文书</span>
            <StatusPill :label="statusText" :tone="statusTone" />
          </div>
          <h1 class="report-cover-title">急性肾损伤风险预测报告</h1>
          <div class="report-cover-meta">
            <span>报告编号 {{ report.report_no }}</span>
            <span>第 {{ report.version }} 版</span>
            <span>生成于 {{ fmt(snapshot.generated_at) }}</span>
          </div>
        </header>

        <div v-if="report.status === 'revoked'" class="report-revoked">
          <strong>这份报告已撤销</strong>
          <span>撤销时间：{{ fmt(report.revoked_at) }} · 原因：{{ report.revoke_reason || '—' }}</span>
        </div>

        <div class="report-summary">
          <div class="report-summary-item">
            <span class="report-summary-label">患者</span>
            <strong class="report-summary-value">{{ patient.name || '—' }}</strong>
            <span class="report-summary-note pilot-mono">{{ patient.mrn || '—' }}</span>
          </div>
          <div class="report-summary-item">
            <span class="report-summary-label">AKI 风险</span>
            <strong class="report-summary-value">{{ hasModel ? probabilityText : '人工审核' }}</strong>
            <span class="report-summary-note">{{ hasModel ? riskText : '无模型概率' }}</span>
          </div>
          <div class="report-summary-item">
            <span class="report-summary-label">版本</span>
            <strong class="report-summary-value">第 {{ report.version }} 版</strong>
            <span class="report-summary-note">{{ statusText }}</span>
          </div>
          <div class="report-summary-item">
            <span class="report-summary-label">复核</span>
            <strong class="report-summary-value">{{ reviewDecisionText }}</strong>
            <span class="report-summary-note">{{ review.reviewer_name || '—' }}</span>
          </div>
        </div>

        <section class="report-sec">
          <h2 class="report-sec-title"><span>一</span>患者与就诊信息</h2>
          <dl class="report-facts">
            <div><dt>患者姓名</dt><dd>{{ val(patient.name) }}</dd></div>
            <div><dt>病历号</dt><dd class="pilot-mono">{{ val(patient.mrn) }}</dd></div>
            <div><dt>性别 / 出生年</dt><dd>{{ val(patient.sex) }} / {{ val(patient.birth_year) }}</dd></div>
            <div><dt>证件信息</dt><dd>{{ val(patient.certificate) }}</dd></div>
            <div><dt>就诊编号</dt><dd class="pilot-mono">{{ val(encounter.case_ref) }}</dd></div>
            <div><dt>发生时间</dt><dd>{{ fmt(encounter.occurred_at) }}</dd></div>
            <div class="is-wide"><dt>手术类型</dt><dd>{{ val(encounter.surgery_type) }}</dd></div>
          </dl>
        </section>

        <section class="report-sec">
          <h2 class="report-sec-title"><span>二</span>风险评估结果</h2>
          <div v-if="hasModel" class="report-risk-block">
            <div class="report-probability">
              <span class="report-prob-label">AKI 预测概率</span>
              <strong>{{ probabilityText }}</strong>
              <StatusPill :label="riskText" :tone="riskTone" />
              <span class="report-prob-note">概率由模型输出，需结合临床判断</span>
            </div>
            <dl class="report-model-facts">
              <div><dt>模型版本</dt><dd>{{ val(pred.model_version) }}</dd></div>
              <div><dt>预测时间</dt><dd>{{ fmt(pred.predicted_at) }}</dd></div>
              <div class="is-wide"><dt>输入指纹</dt><dd class="pilot-mono report-fingerprint">{{ val(pred.input_fingerprint) }}</dd></div>
            </dl>
          </div>
          <div v-else class="report-manual">
            <strong>人工审核 · 无模型概率</strong>
            <span>本次发布基于医生复核，未使用模型概率。</span>
          </div>

          <div v-if="hasModel" class="report-shap">
            <div class="report-shap-head">
              <h3>主要影响因素（SHAP）</h3>
              <span>正值推高风险，负值降低风险</span>
            </div>
            <div v-if="shapRows.length" class="report-shap-list">
              <div v-for="row in shapRows" :key="row.feature" class="report-shap-row">
                <span class="report-shap-label">
                  {{ row.label }}
                  <span v-if="row.missing" class="report-fill-tag">非实测</span>
                </span>
                <span class="report-shap-track" aria-hidden="true">
                  <span :class="row.shap >= 0 ? 'is-up' : 'is-down'" :style="{ width: shapWidth(row) }" />
                </span>
                <span class="report-shap-value pilot-mono" :class="row.shap >= 0 ? 'is-up' : 'is-down'">
                  {{ row.shap >= 0 ? '+' : '' }}{{ row.shap.toFixed(3) }}
                </span>
              </div>
            </div>
            <p v-else class="report-note">本次模型结果没有可展示的 SHAP 解释。</p>
            <p class="report-note">标记“非实测”的指标由训练队列中位数填充；SHAP 只用于解释模型输出，不替代临床判断。</p>
          </div>
        </section>

        <section class="report-sec">
          <h2 class="report-sec-title"><span>三</span>临床诊断</h2>
          <p class="report-text">{{ val(encounter.diagnosis) }}</p>
        </section>

        <section class="report-sec">
          <h2 class="report-sec-title"><span>四</span>医嘱与随访建议</h2>
          <p class="report-text">{{ val(encounter.orders) }}</p>
        </section>

        <section class="report-sec">
          <h2 class="report-sec-title"><span>五</span>本次实测指标</h2>
          <div v-if="valueRows.length" class="report-values">
            <div v-for="row in valueRows" :key="row.name" class="report-value">
              <span class="report-value-label">
                {{ row.label }}
                <span v-if="row.missing" class="report-fill-tag">非实测</span>
              </span>
              <span class="report-value-number pilot-mono">{{ row.value }}<small v-if="row.unit">{{ row.unit }}</small></span>
            </div>
          </div>
          <p v-else class="report-text">本报告没有记录实测指标。</p>
          <div v-if="missingRows.length" class="report-missing">
            <strong>缺失指标（{{ missingRows.length }} 项，模型按训练中位数填充，非实测）</strong>
            <p>{{ missingRows.map((row: any) => row.label).join('、') }}</p>
          </div>
        </section>

        <section class="report-sec">
          <h2 class="report-sec-title"><span>六</span>医生复核</h2>
          <dl class="report-facts">
            <div><dt>复核结论</dt><dd>{{ reviewDecisionText }}</dd></div>
            <div><dt>复核医生</dt><dd>{{ val(review.reviewer_name) }}</dd></div>
            <div><dt>复核时间</dt><dd>{{ fmt(review.created_at) }}</dd></div>
            <div><dt>发布人</dt><dd>{{ val(snapshot.published_by?.name) }}</dd></div>
            <div class="is-wide"><dt>复核意见</dt><dd>{{ val(review.reason) }}</dd></div>
          </dl>
        </section>

        <section class="report-sec">
          <h2 class="report-sec-title"><span>七</span>声明</h2>
          <p class="report-note report-declaration">
            本报告由急性肾损伤风险预测模型辅助生成，仅供临床医生参考，不能替代专业医疗判断。模型对缺失指标采用训练队列中位数填充，预测结果可能受输入完整性影响。
          </p>
        </section>

        <section class="report-sec report-integrity">
          <h2 class="report-sec-title"><span>八</span>完整性摘要</h2>
          <div class="report-hash-row">
            <code class="report-hash">{{ report.sha256 || '—' }}</code>
            <button
              class="pilot-btn report-copy-btn"
              type="button"
              :disabled="!report.sha256"
              @click="copyHash"
            >{{ copied ? '已复制' : '复制摘要' }}</button>
          </div>
          <p class="report-note">
            摘要为发布时写入的报告快照摘要。页面不在此处重新计算；下载 PDF 时后端会重新计算并比对，不一致会阻止下载。
          </p>
        </section>

        <footer class="report-signature">
          <span>报告编号：{{ report.report_no }}</span>
          <span>版本：v{{ report.version }}</span>
          <span>发布时间：{{ fmt(report.published_at) }}</span>
        </footer>
      </article>

      <SectionPanel v-else title="报告未加载">
        <EmptyState
          title="这份报告无法显示"
          description="报告不存在、已被删除，或当前账号没有查看权限。"
        >
          <RouterLink to="/reports" class="pilot-btn">返回报告列表</RouterLink>
        </EmptyState>
      </SectionPanel>

      <ElDialog
        v-model="showRevoke"
        title="撤销正式报告"
        width="520px"
        class="pilot-dialog"
        :close-on-click-modal="false"
        append-to-body
      >
        <p class="report-dialog-sub">撤销后患者端将无法查看，医生也不能继续基于这份报告操作；操作会写入审计日志。</p>
        <div class="report-dialog-field">
          <label for="revoke-reason">撤销原因 <span aria-hidden="true">*</span></label>
          <textarea
            id="revoke-reason"
            v-model="revokeReason"
            class="pilot-textarea"
            rows="3"
            maxlength="1000"
            placeholder="如：指标录入口误，需重新采集后发布新版本"
          />
          <span class="report-dialog-hint">{{ revokeReason.length }}/1000</span>
        </div>
        <div v-if="revokeError" class="pilot-error" role="alert">{{ revokeError }}</div>
        <template #footer>
          <div class="report-dialog-actions">
            <button class="pilot-btn" type="button" @click="showRevoke = false">取消</button>
            <button
              class="pilot-btn report-revoke-btn"
              type="button"
              :disabled="revoking || !revokeReason.trim()"
              @click="revoke"
            >{{ revoking ? '撤销中…' : '确认撤销' }}</button>
          </div>
        </template>
      </ElDialog>
    </div>
  </div>
</template>

<style scoped>
.report-page { max-width: 980px; margin: 0 auto; }
.report-loading { display: grid; gap: var(--pilot-space-3); }
.report-loading-cover { height: 150px; }
.report-loading-body { height: 520px; }
.report-paper {
  padding: 40px 48px 32px;
  border: 1px solid var(--pilot-line);
  border-radius: var(--pilot-radius-card);
  background: var(--pilot-surface);
  box-shadow: var(--pilot-shadow);
}
.report-cover { padding-bottom: var(--pilot-space-5); border-bottom: 2px solid var(--pilot-line-strong); }
.report-cover-top { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--pilot-space-3); }
.report-kicker { color: var(--pilot-muted); font-size: var(--pilot-font-xs); font-weight: 600; letter-spacing: .06em; }
.report-cover-title {
  margin: var(--pilot-space-4) 0 var(--pilot-space-3);
  color: var(--pilot-ink);
  font-size: var(--pilot-font-xl);
  font-weight: 700;
  line-height: 1.3;
}
.report-cover-meta { display: flex; flex-wrap: wrap; gap: 6px 16px; color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
.report-revoked {
  display: grid;
  gap: var(--pilot-space-1);
  margin-top: var(--pilot-space-4);
  padding: var(--pilot-space-3) var(--pilot-space-4);
  border-left: 3px solid var(--pilot-high);
  background: var(--pilot-high-soft);
  color: var(--pilot-high);
  font-size: var(--pilot-font-sm);
}
.report-summary {
  display: grid;
  grid-template-columns: minmax(0, 1.25fr) minmax(0, .9fr) minmax(0, .85fr) minmax(0, 1.15fr);
  margin: var(--pilot-space-5) 0 0;
  border: 1px solid var(--pilot-line);
}
.report-summary-item {
  display: grid;
  align-content: start;
  gap: var(--pilot-space-1);
  min-width: 0;
  padding: var(--pilot-space-3) var(--pilot-space-4);
  border-right: 1px solid var(--pilot-line);
}
.report-summary-item:last-child { border-right: 0; }
.report-summary-label { color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
.report-summary-value { overflow: hidden; color: var(--pilot-ink); font-size: var(--pilot-font-md); font-weight: 700; text-overflow: ellipsis; white-space: nowrap; }
.report-summary-note { overflow: hidden; color: var(--pilot-muted); font-size: var(--pilot-font-xs); text-overflow: ellipsis; white-space: nowrap; }
.report-sec { padding: var(--pilot-space-5) 0 0; }
.report-sec-title { display: flex; gap: var(--pilot-space-2); margin: 0 0 var(--pilot-space-4); color: var(--pilot-ink); font-size: var(--pilot-font-md); font-weight: 700; }
.report-sec-title span { color: var(--pilot-muted); font-family: "SFMono-Regular", Consolas, monospace; font-weight: 400; }
.report-facts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 var(--pilot-space-5); margin: 0; }
.report-facts > div { display: flex; gap: var(--pilot-space-3); padding: var(--pilot-space-2) 0; border-bottom: 1px dashed var(--pilot-line); }
.report-facts .is-wide { grid-column: 1 / -1; }
.report-facts dt { flex: 0 0 96px; color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
.report-facts dd { min-width: 0; margin: 0; overflow-wrap: anywhere; color: var(--pilot-ink-soft); font-size: var(--pilot-font-sm); }
.report-risk-block { display: grid; grid-template-columns: minmax(160px, 200px) minmax(0, 1fr); gap: var(--pilot-space-5); align-items: start; }
.report-probability { display: grid; align-content: start; gap: var(--pilot-space-2); padding: var(--pilot-space-4); border: 1px solid var(--pilot-line); background: var(--pilot-surface-2); }
.report-prob-label { color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
.report-probability strong { color: var(--pilot-ink); font-size: 32px; line-height: 1.1; }
.report-probability .pilot-chip { justify-self: start; }
.report-prob-note { color: var(--pilot-muted); font-size: var(--pilot-font-xs); line-height: 1.5; }
.report-model-facts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--pilot-space-3) var(--pilot-space-5); margin: 0; }
.report-model-facts > div { min-width: 0; padding-bottom: var(--pilot-space-2); border-bottom: 1px dashed var(--pilot-line); }
.report-model-facts .is-wide { grid-column: 1 / -1; }
.report-model-facts dt { color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
.report-model-facts dd { margin: var(--pilot-space-1) 0 0; overflow-wrap: anywhere; color: var(--pilot-ink-soft); font-size: var(--pilot-font-sm); }
.report-fingerprint { font-size: 11px; }
.report-manual { display: grid; gap: var(--pilot-space-1); padding: var(--pilot-space-4); border: 1px solid var(--pilot-line); background: var(--pilot-surface-2); }
.report-manual strong { color: var(--pilot-ink); font-size: var(--pilot-font-md); }
.report-manual span { color: var(--pilot-muted); font-size: var(--pilot-font-sm); }
.report-shap { margin-top: var(--pilot-space-5); }
.report-shap-head { display: flex; align-items: baseline; justify-content: space-between; gap: var(--pilot-space-3); margin-bottom: var(--pilot-space-3); }
.report-shap-head h3 { margin: 0; color: var(--pilot-ink); font-size: var(--pilot-font-sm); font-weight: 700; }
.report-shap-head span { color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
.report-shap-list { border-top: 1px solid var(--pilot-line); }
.report-shap-row {
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(80px, 1fr) 76px;
  align-items: center;
  gap: var(--pilot-space-3);
  padding: 7px 0;
  border-bottom: 1px dashed var(--pilot-line);
}
.report-shap-label { min-width: 0; overflow: hidden; color: var(--pilot-ink-soft); font-size: var(--pilot-font-sm); text-overflow: ellipsis; white-space: nowrap; }
.report-shap-track { height: 4px; background: var(--pilot-line); }
.report-shap-track span { display: block; height: 4px; min-width: 2px; }
.report-shap-track .is-up,
.report-shap-value.is-up { background: var(--pilot-high); color: var(--pilot-high); }
.report-shap-track .is-down,
.report-shap-value.is-down { background: var(--pilot-low); color: var(--pilot-low); }
.report-shap-value { font-size: 11px; text-align: right; white-space: nowrap; }
.report-text { margin: 0; color: var(--pilot-ink-soft); font-size: var(--pilot-font-sm); line-height: 1.8; white-space: pre-wrap; }
.report-note { margin: var(--pilot-space-3) 0 0; color: var(--pilot-muted); font-size: var(--pilot-font-xs); line-height: 1.7; }
.report-declaration { color: var(--pilot-ink-soft); font-size: var(--pilot-font-sm); }
.report-fill-tag { margin-left: var(--pilot-space-1); padding: 1px 5px; border: 1px solid var(--pilot-line-strong); color: var(--pilot-mid); font-size: 10px; font-weight: 500; white-space: nowrap; }
.report-values { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 var(--pilot-space-5); }
.report-value { display: flex; align-items: baseline; justify-content: space-between; gap: var(--pilot-space-3); padding: var(--pilot-space-2) 0; border-bottom: 1px dashed var(--pilot-line); }
.report-value-label { min-width: 0; overflow-wrap: anywhere; color: var(--pilot-ink-soft); font-size: var(--pilot-font-sm); }
.report-value-number { flex: 0 0 auto; color: var(--pilot-ink); font-size: var(--pilot-font-sm); text-align: right; white-space: nowrap; }
.report-value-number small { margin-left: var(--pilot-space-1); color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
.report-missing { margin-top: var(--pilot-space-4); padding: var(--pilot-space-3) var(--pilot-space-4); border: 1px solid var(--pilot-mid); background: var(--pilot-mid-soft); }
.report-missing strong { color: var(--pilot-mid); font-size: var(--pilot-font-sm); }
.report-missing p { margin: var(--pilot-space-1) 0 0; color: var(--pilot-ink-soft); font-size: var(--pilot-font-xs); line-height: 1.7; }
.report-integrity { margin-top: var(--pilot-space-5); padding-top: var(--pilot-space-4); border-top: 1px solid var(--pilot-line); }
.report-hash-row { display: flex; align-items: flex-start; gap: var(--pilot-space-3); }
.report-hash {
  flex: 1;
  min-width: 0;
  padding: var(--pilot-space-3);
  border: 1px solid var(--pilot-line);
  background: var(--pilot-surface-2);
  color: var(--pilot-ink-soft);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 11px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}
.report-copy-btn { flex: 0 0 auto; }
.report-signature { display: flex; flex-wrap: wrap; gap: var(--pilot-space-2) var(--pilot-space-5); margin-top: var(--pilot-space-5); padding-top: var(--pilot-space-4); border-top: 1px solid var(--pilot-line); color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
.report-revoke-btn { border-color: var(--pilot-high); color: var(--pilot-high); }
.report-dialog-sub { margin: 0 0 var(--pilot-space-4); color: var(--pilot-muted); font-size: var(--pilot-font-sm); line-height: 1.6; }
.report-dialog-field { display: flex; flex-direction: column; gap: var(--pilot-space-2); }
.report-dialog-field label { color: var(--pilot-ink-soft); font-size: var(--pilot-font-xs); font-weight: 600; }
.report-dialog-hint { color: var(--pilot-muted); font-size: var(--pilot-font-xs); text-align: right; }
.report-dialog-actions { display: flex; justify-content: flex-end; gap: var(--pilot-space-2); }
@media (max-width: 1024px) {
  .report-page { max-width: 820px; }
  .report-paper { padding: 32px; }
  .report-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .report-summary-item:nth-child(2) { border-right: 0; }
  .report-summary-item:nth-child(-n+2) { border-bottom: 1px solid var(--pilot-line); }
}
@media (max-width: 650px) {
  .report-page :deep(.pilot-title) { overflow-wrap: anywhere; }
  .report-paper { padding: var(--pilot-space-5) var(--pilot-space-4) var(--pilot-space-4); }
  .report-cover-title { font-size: var(--pilot-font-lg); }
  .report-cover-meta { display: grid; gap: var(--pilot-space-1); }
  .report-summary { grid-template-columns: minmax(0, 1fr); }
  .report-summary-item { border-right: 0; border-bottom: 1px solid var(--pilot-line); }
  .report-summary-item:last-child { border-bottom: 0; }
  .report-facts { grid-template-columns: minmax(0, 1fr); }
  .report-facts .is-wide { grid-column: auto; }
  .report-facts dt { flex-basis: 86px; }
  .report-risk-block { grid-template-columns: minmax(0, 1fr); }
  .report-model-facts { grid-template-columns: minmax(0, 1fr); }
  .report-model-facts .is-wide { grid-column: auto; }
  .report-shap-row { grid-template-columns: minmax(0, 1fr) 76px; }
  .report-shap-track { display: none; }
  .report-values { grid-template-columns: minmax(0, 1fr); }
  .report-hash-row { flex-direction: column; }
  .report-copy-btn { align-self: flex-start; }
  .report-dialog-actions { flex-wrap: wrap; }
}
</style>

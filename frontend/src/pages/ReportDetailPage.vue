<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api, saveBlob } from '../api/client'
import { useAuth } from '../composables/useAuth'

const route = useRoute()
const auth = useAuth()
const loading = ref(true)
const error = ref('')
const report = ref<any>(null)
const showRevoke = ref(false)
const revokeReason = ref('')
const revoking = ref(false)
const downloading = ref(false)

const snapshot = computed(() => report.value?.snapshot ?? {})
const patient = computed(() => snapshot.value.patient ?? {})
const encounter = computed(() => snapshot.value.encounter ?? {})
const pred = computed(() => snapshot.value.prediction ?? {})
const result = computed(() => pred.value.result ?? {})
const review = computed(() => snapshot.value.review ?? {})
const values = computed(() => encounter.value.values ?? {})
const shapRows = computed(() =>
  [...(result.value.shap_values ?? [])].sort((a: any, b: any) => Math.abs(b.shap) - Math.abs(a.shap)).slice(0, 8),
)
const valueRows = computed(() => {
  const list = Object.entries(values.value)
  const rows: any[] = []
  for (let i = 0; i < list.length; i += 2) rows.push(list.slice(i, i + 2))
  return rows
})
const riskClass = computed(() => {
  const level = report.value?.risk_level
  return level === '高' ? 'high' : level === '中' ? 'medium' : 'low'
})
const riskLabel = computed(() => {
  const level = report.value?.risk_level
  if (!level) return '未评估'
  return level === '人工审核' ? '人工审核' : `${level}风险`
})
const decisionLabels: Record<string, string> = {
  agree: '认可模型结果', adjust: '调整风险判断', defer: '暂缓采纳', manual: '人工审核',
}
function decisionText(value?: string) {
  return value ? (decisionLabels[value] || value) : '未复核'
}
function fmt(value?: string) {
  if (!value) return '—'
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString('zh-CN')
}
function val(value: any) {
  return value === null || value === undefined || value === '' ? '—' : value
}
async function load() {
  loading.value = true
  error.value = ''
  try {
    report.value = await api.report(route.params.id as string)
  } catch (e: any) {
    error.value = e?.message ?? '报告加载失败'
  } finally {
    loading.value = false
  }
}
async function download() {
  if (!report.value) return
  downloading.value = true
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
  if (!revokeReason.value.trim()) { error.value = '请填写撤销原因'; return }
  revoking.value = true
  try {
    await api.revokeReport(report.value.id, revokeReason.value.trim())
    showRevoke.value = false
    await load()
  } catch (e: any) {
    error.value = e?.message ?? '撤销失败'
  } finally {
    revoking.value = false
  }
}
onMounted(load)
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <div style="margin-bottom:4px"><RouterLink to="/reports" class="btn btn-sm btn-ghost">← 报告中心</RouterLink></div>
        <h1 class="page-title">正式报告 {{ report?.report_no || '' }}</h1>
        <div class="page-subtitle" v-if="report">
          {{ report.patient_name }} · v{{ report.version }} ·
          <span class="status" :class="`status-${report.status}`">{{ report.status === 'published' ? '已发布' : '已撤销' }}</span>
        </div>
      </div>
      <div class="page-actions" v-if="report">
        <button class="btn btn-primary" :disabled="report.status !== 'published' || downloading" @click="download">{{ downloading ? '生成中…' : '下载 PDF' }}</button>
        <button v-if="auth.user.value?.role === 'admin' && report.can_revoke" class="btn btn-danger" @click="showRevoke = true">撤销报告</button>
      </div>
    </div>
    <div v-if="error" class="error">{{ error }}</div>
    <div v-if="loading" class="card"><div class="empty-state">正在校验并加载报告…</div></div>

    <div v-else-if="report" class="report-layout">
      <div class="report-doc">
        <h1>急性肾损伤风险预测报告</h1>
        <div class="doc-sub">报告编号 {{ report.report_no }} · 第 {{ report.version }} 版 · 生成于 {{ fmt(snapshot.generated_at) }}</div>

        <div class="doc-sec">
          <div class="doc-sec-title">一、患者与就诊信息</div>
          <table class="doc-table">
            <tbody>
              <tr><th style="width:90px">患者姓名</th><td>{{ patient.name }}</td><th style="width:90px">病历号</th><td class="font-mono">{{ patient.mrn }}</td></tr>
              <tr><th>性别 / 出生年</th><td>{{ patient.sex }} / {{ val(patient.birth_year) }}</td><th>证件信息</th><td>{{ val(patient.certificate) }}</td></tr>
              <tr><th>就诊编号</th><td class="font-mono">{{ encounter.case_ref }}</td><th>发生时间</th><td>{{ fmt(encounter.occurred_at) }}</td></tr>
              <tr><th>手术类型</th><td colspan="3">{{ val(encounter.surgery_type) }}</td></tr>
            </tbody>
          </table>
        </div>

        <div class="doc-sec">
          <div class="doc-sec-title">二、风险评估结果</div>
          <div class="assessment-grid">
            <div class="prob-card" :class="riskClass" style="padding:14px">
              <div class="prob-label">AKI 预测概率</div>
              <div class="prob-value" style="font-size:30px">{{ typeof result.probability === 'number' ? `${(result.probability * 100).toFixed(1)}%` : '人工审核' }}</div>
              <div class="prob-risk">{{ riskLabel }}</div>
              <div class="prob-meta">模型版本：{{ pred.model_version || '人工审核 / 不适用' }}<br />输入指纹：<span class="font-mono" style="font-size:9px">{{ val(pred.input_fingerprint).slice(0, 24) }}…</span></div>
            </div>
            <div>
              <div class="muted" style="font-size:10px;margin-bottom:4px">主要 SHAP 贡献</div>
              <div v-for="s in shapRows" :key="s.feature" style="display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px dashed var(--border);font-size:10px">
                <span>{{ s.feature }}</span>
                <span :style="{color: s.shap >= 0 ? 'var(--red)' : 'var(--green)'}">{{ s.shap >= 0 ? '+' : '' }}{{ s.shap.toFixed(3) }}</span>
              </div>
              <div v-if="!shapRows.length" class="muted">无模型解释（人工审核）</div>
            </div>
          </div>
        </div>

        <div class="doc-sec">
          <div class="doc-sec-title">三、临床诊断</div>
          <div class="doc-text">{{ val(encounter.diagnosis) }}</div>
        </div>
        <div class="doc-sec">
          <div class="doc-sec-title">四、医嘱与随访建议</div>
          <div class="doc-text">{{ val(encounter.orders) }}</div>
        </div>

        <div class="doc-sec">
          <div class="doc-sec-title">五、本次实测指标</div>
          <div class="table-wrap">
            <table class="doc-table">
              <thead><tr><th>指标</th><th style="text-align:right">数值</th><th>指标</th><th style="text-align:right">数值</th></tr></thead>
              <tbody>
                <tr v-for="(pair, idx) in valueRows" :key="idx">
                  <template v-for="(item, j) in pair" :key="j">
                    <td>{{ item[0] }}</td><td style="text-align:right">{{ item[1] }}</td>
                  </template>
                  <template v-if="pair.length === 1"><td></td><td></td></template>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-if="snapshot.missing_features?.length" class="muted" style="font-size:9px;margin-top:6px">
            缺失指标（模型按训练中位数填充）：{{ snapshot.missing_features.join('、') }}
          </div>
        </div>

        <div class="doc-sec">
          <div class="doc-sec-title">六、医生复核</div>
          <table class="doc-table">
            <tbody>
              <tr><th style="width:90px">复核结论</th><td>{{ decisionText(review.decision) }}</td><th style="width:90px">复核医生</th><td>{{ review.reviewer_name || '—' }}</td></tr>
              <tr><th>复核时间</th><td>{{ fmt(review.created_at) }}</td><th>发布人</th><td>{{ snapshot.published_by?.name || '—' }}</td></tr>
              <tr><th>复核意见</th><td colspan="3">{{ review.reason || '—' }}</td></tr>
            </tbody>
          </table>
        </div>

        <div class="doc-sec">
          <div class="doc-sec-title">七、声明</div>
          <div class="muted" style="font-size:10px;line-height:1.8">
            本报告由急性肾损伤风险预测模型辅助生成，仅供临床医生参考，不能替代专业医疗判断。模型对缺失指标采用训练队列中位数填充，预测结果可能受输入完整性影响。
          </div>
        </div>

        <div class="report-sign">
          <span>报告编号：{{ report.report_no }}</span>
          <span>版本：v{{ report.version }}</span>
          <span>发布时间：{{ fmt(report.published_at) }}</span>
        </div>
      </div>

      <div>
        <div class="side-card">
          <div class="side-title">完整性校验</div>
          <div class="muted" style="font-size:10px">SHA-256</div>
          <div class="hash-text">{{ report.sha256 }}</div>
          <div class="status status-active mt-8">校验通过 · 快照不可篡改</div>
        </div>
        <div class="side-card">
          <div class="side-title">版本信息</div>
          <div class="muted" style="font-size:11px;line-height:1.9">
            报告版本：v{{ report.version }}<br />
            关联就诊：{{ report.encounter_id }}<br />
            模型版本：{{ pred.model_version || '人工审核 / 不适用' }}<br />
            预测时间：{{ fmt(pred.predicted_at) }}
          </div>
        </div>
        <div v-if="report.status === 'revoked'" class="side-card">
          <div class="side-title">撤销记录</div>
          <div class="muted" style="font-size:11px;line-height:1.8">撤销时间：{{ fmt(report.revoked_at) }}<br />原因：{{ report.revoke_reason }}</div>
        </div>
      </div>
    </div>

    <div v-if="showRevoke" class="modal-mask" @click.self="showRevoke = false">
      <div class="modal-panel" style="max-width:480px">
        <div class="modal-head"><div><div class="modal-title">撤销正式报告</div><div class="modal-sub">撤销后患者端将无法查看，操作会写入审计日志。</div></div><button class="modal-close" @click="showRevoke = false">×</button></div>
        <div class="modal-body">
          <div class="form-group"><label>撤销原因 *</label><textarea v-model="revokeReason" class="form-control" rows="3" placeholder="如：指标录入口误，需重新采集后发布新版本" /></div>
          <div v-if="error" class="error mt-12">{{ error }}</div>
        </div>
        <div class="modal-foot">
          <button class="btn btn-secondary" @click="showRevoke = false">取消</button>
          <button class="btn btn-danger" :disabled="revoking" @click="revoke">{{ revoking ? '撤销中…' : '确认撤销' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

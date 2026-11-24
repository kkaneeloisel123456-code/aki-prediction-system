<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api/client'
import { useAuth } from '../composables/useAuth'
import SectionPanel from '../components/SectionPanel.vue'
import EmptyState from '../components/EmptyState.vue'
import StatusPill from '../components/StatusPill.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuth()
const loading = ref(true)
const error = ref('')
const patient = ref<any>(null)
const encounters = ref<any[]>([])
const latestDetail = ref<any>(null)
const doctors = ref<any[]>([])
const metas = ref<any[]>([])
const showEncounter = ref(false)
const saveBusy = ref(false)
const formError = ref('')
const queryResult = ref<any>(null)
const showQuery = ref(false)
const queryModal = ref<HTMLElement | null>(null)
const queryTrigger = ref<HTMLElement | null>(null)
const showEdit = ref(false)
const editForm = reactive<any>({})
const copyState = ref('')

const encForm = reactive({
  case_ref: '', occurred_at: '', surgery_type: '', diagnosis: '', orders: '',
})
const isAdmin = computed(() => auth.user.value?.role === 'admin')
const canEdit = computed(() => patient.value?.access?.edit)

const statusText: Record<string, string> = {
  draft: '草稿', predicted: '待复核', reviewed: '已复核', published: '已发布',
}
function statusTone(status: string) {
  if (status === 'predicted') return 'mid'
  if (status === 'reviewed') return 'accent'
  if (status === 'published') return 'low'
  return 'neutral'
}
function fmt(value?: string) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}
function localNow() {
  const d = new Date()
  const off = d.getTimezoneOffset()
  return new Date(d.getTime() - off * 60_000).toISOString().slice(0, 16)
}

const latestEncounter = computed(() => latestDetail.value ?? encounters.value[0] ?? null)
const latestPrediction = computed(() => latestEncounter.value?.latest_prediction ?? null)
const latestReport = computed(() => latestEncounter.value?.latest_report ?? null)
const latestValues = computed(() => ({
  ...(latestEncounter.value?.values ?? {}),
  ...(latestEncounter.value?.draft?.payload?.values ?? {}),
}))
const riskLevel = computed(() => latestPrediction.value?.risk_level ?? '')
const riskLabel = computed(() => {
  if (!latestEncounter.value) return '无就诊'
  if (!latestPrediction.value) return '未评估'
  if (latestPrediction.value.origin === 'manual' || !riskLevel.value || riskLevel.value === '人工审核') {
    return '人工审核'
  }
  return `${riskLevel.value}风险`
})
const riskTone = computed(() => {
  if (riskLevel.value === '高') return 'high'
  if (riskLevel.value === '中') return 'mid'
  if (riskLevel.value === '低') return 'low'
  return 'neutral'
})
function predictionRiskLabel(record: any) {
  const prediction = record?.latest_prediction
  if (!prediction) return '未评估'
  if (prediction.origin === 'manual' || !prediction.risk_level || prediction.risk_level === '人工审核') {
    return '人工审核'
  }
  return `${prediction.risk_level}风险`
}
function predictionRiskTone(record: any) {
  const level = record?.latest_prediction?.risk_level
  if (level === '高') return 'high'
  if (level === '中') return 'mid'
  if (level === '低') return 'low'
  return 'neutral'
}
const probabilityText = computed(() => {
  const probability = latestPrediction.value?.probability
  return typeof probability === 'number' ? `${(probability * 100).toFixed(1)}%` : '—'
})
const filledMetas = computed(() => metas.value
  .filter(meta => {
    const value = latestValues.value[meta.name]
    return value !== null && value !== undefined && value !== ''
  })
  .slice(0, 10))
const filledCount = computed(() => metas.value.filter(meta => {
  const value = latestValues.value[meta.name]
  return value !== null && value !== undefined && value !== ''
}).length)
const missingCount = computed(() => Math.max(0, metas.value.length - filledCount.value))
const ownerName = computed(() => patient.value?.owner_name || '未指定')
const surgeryText = computed(() => latestEncounter.value?.surgery_type || '未记录')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const id = route.params.id as string
    const [p, e, f] = await Promise.all([
      api.patient(id),
      api.encounters(id),
      api.features().catch(() => ({ metas: [] })),
    ])
    patient.value = p
    encounters.value = e.encounters ?? []
    latestDetail.value = encounters.value[0]
      ? await api.encounter(encounters.value[0].id).catch(() => null)
      : null
    metas.value = f.metas ?? []
    if (isAdmin.value) {
      const d = await api.doctors().catch(() => ({ doctors: [] }))
      doctors.value = d.doctors ?? []
    }
  } catch (reason: any) {
    error.value = reason?.message ?? '患者档案加载失败'
  } finally {
    loading.value = false
  }
}

function openEncounter() {
  Object.assign(encForm, {
    case_ref: `CASE-${new Date().toISOString().slice(0, 10).replace(/-/g, '')}-${String(encounters.value.length + 1).padStart(3, '0')}`,
    occurred_at: localNow(), surgery_type: '', diagnosis: '', orders: '',
  })
  formError.value = ''
  showEncounter.value = true
}
async function submitEncounter() {
  formError.value = ''
  if (!encForm.case_ref.trim() || !encForm.occurred_at) {
    formError.value = '就诊编号和发生时间不能为空'
    return
  }
  saveBusy.value = true
  try {
    const created = await api.createEncounter(patient.value.id, {
      case_ref: encForm.case_ref.trim(),
      occurred_at: new Date(encForm.occurred_at).toISOString(),
      surgery_type: encForm.surgery_type.trim() || null,
      diagnosis: '',
      orders: '',
      values: {},
    })
    showEncounter.value = false
    router.push(`/encounters/${created.id}`)
  } catch (reason: any) {
    formError.value = reason?.message ?? '创建就诊失败'
  } finally {
    saveBusy.value = false
  }
}

async function issueCode() {
  error.value = ''
  copyState.value = ''
  try {
    queryResult.value = await api.queryCode(patient.value.id)
    showQuery.value = true
    await nextTick()
    focusQueryModal()
    await load()
  } catch (reason: any) {
    error.value = reason?.message ?? '查询码生成失败'
  }
}
function queryFocusables() {
  if (!queryModal.value) return [] as HTMLElement[]
  return Array.from(queryModal.value.querySelectorAll<HTMLElement>(
    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
  )).filter((element) => !element.hasAttribute('disabled'))
}
function focusQueryModal() {
  const first = queryFocusables()[0]
  ;(first ?? queryModal.value)?.focus()
}
function closeQuery() {
  showQuery.value = false
  void nextTick(() => queryTrigger.value?.focus())
}
function onQueryKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    closeQuery()
    return
  }
  if (event.key !== 'Tab') return
  const focusables = queryFocusables()
  if (!focusables.length) {
    event.preventDefault()
    queryModal.value?.focus()
    return
  }
  const first = focusables[0]
  const last = focusables[focusables.length - 1]
  const active = document.activeElement as HTMLElement | null
  if (!queryModal.value?.contains(active)) {
    event.preventDefault()
    first.focus()
  } else if (event.shiftKey && active === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && active === last) {
    event.preventDefault()
    first.focus()
  }
}
async function copyCode() {
  const code = queryResult.value?.query_code
  if (!code) return
  try {
    await navigator.clipboard.writeText(code)
    copyState.value = '已复制'
  } catch {
    copyState.value = '复制失败，请手动选择查询码'
  }
}

function openEdit() {
  Object.assign(editForm, {
    name: patient.value.name,
    sex: patient.value.sex,
    birth_year: patient.value.birth_year ?? '',
    certificate_last4: '',
    phone_last4: '',
    active: patient.value.active,
    owner_id: patient.value.owner_id ?? '',
  })
  formError.value = ''
  showEdit.value = true
}
async function submitEdit() {
  formError.value = ''
  saveBusy.value = true
  try {
    const payload: any = {
      name: editForm.name, sex: editForm.sex,
      birth_year: editForm.birth_year ? Number(editForm.birth_year) : null,
      active: Boolean(editForm.active),
    }
    if (editForm.certificate_last4) payload.certificate_last4 = editForm.certificate_last4
    if (editForm.phone_last4) payload.phone_last4 = editForm.phone_last4
    if (isAdmin.value && editForm.owner_id) payload.owner_id = editForm.owner_id
    await api.updatePatient(patient.value.id, payload)
    showEdit.value = false
    await load()
  } catch (reason: any) {
    formError.value = reason?.message ?? '保存失败'
  } finally {
    saveBusy.value = false
  }
}

const grantForm = reactive({ doctor_id: '', permission: 'view' })
async function addGrant() {
  if (!grantForm.doctor_id) return
  error.value = ''
  try {
    await api.addGrant(patient.value.id, { ...grantForm })
    await load()
  } catch (reason: any) { error.value = reason?.message ?? '授权失败' }
}
async function removeGrant(doctorId: string) {
  if (!confirm('确认撤销该医生的档案访问授权？')) return
  try {
    await api.removeGrant(patient.value.id, doctorId)
    await load()
  } catch (reason: any) { error.value = reason?.message ?? '撤销失败' }
}

onMounted(load)
</script>

<template>
  <div class="pilot-page patient-page">
    <div class="pilot-page-inner">
      <div class="patient-topline">
        <RouterLink to="/patients" class="pilot-link patient-back">← 患者档案</RouterLink>
      </div>

      <div v-if="error" class="pilot-error">{{ error }}</div>
      <div v-if="loading" class="pilot-skeleton patient-loading" aria-label="正在加载患者档案" />

      <template v-else-if="patient">
        <section class="pilot-banner patient-banner">
          <div class="pilot-banner-main">
            <div class="pilot-meta">
              <span class="pilot-mono">{{ patient.mrn }}</span>
              <span>{{ patient.sex }}</span>
              <span>{{ patient.birth_year ? `${patient.birth_year} 年出生` : '出生年未登记' }}</span>
            </div>
            <h1 class="pilot-banner-title">{{ patient.name }}</h1>
            <div class="pilot-meta patient-banner-meta">
              <span>手术：{{ surgeryText }}</span>
              <span>负责人：{{ ownerName }}</span>
              <span>就诊 {{ encounters.length }} 次</span>
            </div>
          </div>
          <div class="pilot-banner-side patient-banner-side">
            <div class="patient-risk-side">
              <span class="pilot-section-label">最近风险</span>
              <StatusPill :label="riskLabel" :tone="riskTone" />
              <strong v-if="latestPrediction?.probability != null" class="patient-risk-prob">{{ probabilityText }}</strong>
              <span v-if="latestEncounter" class="pilot-small">{{ fmt(latestEncounter.updated_at) }}</span>
            </div>
            <div class="pilot-actions patient-actions">
              <button v-if="canEdit" class="pilot-btn pilot-btn-primary" type="button" @click="openEncounter">新建接诊</button>
              <button ref="queryTrigger" class="pilot-btn" type="button" @click="issueCode">生成查询码</button>
              <button v-if="canEdit" class="pilot-btn" type="button" @click="openEdit">编辑档案</button>
              <button class="pilot-btn pilot-btn-ghost" type="button" :disabled="loading" @click="load">刷新</button>
            </div>
          </div>
        </section>

        <div class="patient-layout">
          <SectionPanel title="历次评估" :subtitle="`${encounters.length} 次 · 按发生时间倒序`" flush>
            <EmptyState
              v-if="!encounters.length"
              title="还没有就诊记录"
              description="新建接诊后，指标、预测、复核与报告会在这里形成一条可追溯的评估记录。"
            >
              <button v-if="canEdit" class="pilot-btn pilot-btn-primary" type="button" @click="openEncounter">新建接诊</button>
            </EmptyState>

            <div v-else class="encounter-list">
              <RouterLink
                v-for="encounter in encounters"
                :key="encounter.id"
                :to="`/encounters/${encounter.id}`"
                class="encounter-row"
              >
                <div class="encounter-row-head">
                  <span class="pilot-mono encounter-ref">{{ encounter.case_ref }}</span>
                  <StatusPill :label="statusText[encounter.status] ?? encounter.status" :tone="statusTone(encounter.status)" />
                </div>
                <div class="encounter-row-meta">
                  {{ fmt(encounter.occurred_at) }} · {{ encounter.surgery_type || '未记录手术' }}
                </div>
                <div class="encounter-row-foot">
                  <StatusPill
                    v-if="encounter.latest_prediction"
                    :label="predictionRiskLabel(encounter)"
                    :tone="predictionRiskTone(encounter)"
                  />
                  <span v-else class="pilot-small">未评估</span>
                  <span v-if="encounter.latest_report" class="pilot-small pilot-mono">{{ encounter.latest_report.report_no }}</span>
                </div>
              </RouterLink>
            </div>
          </SectionPanel>

          <SectionPanel
            title="本次指标"
            :subtitle="latestEncounter ? `最近一次就诊 · 已录入 ${filledCount}/${metas.length || 35} 项` : '没有可展示的就诊'"
          >
            <EmptyState
              v-if="!latestEncounter"
              title="暂无指标"
              description="建立接诊后，术前、术中、ICU 与术后指标会在这里汇总。"
            />
            <template v-else>
              <div class="metric-head">
                <strong>{{ filledCount }}<span>/{{ metas.length || 35 }}</span></strong>
                <span class="pilot-small">{{ missingCount ? `尚缺 ${missingCount} 项` : '指标已齐全' }}</span>
              </div>
              <dl v-if="filledMetas.length" class="metric-list">
                <div v-for="meta in filledMetas" :key="meta.name">
                  <dt>{{ meta.label || meta.name }}</dt>
                  <dd>
                    {{ latestValues[meta.name] }}
                    <span v-if="meta.unit" class="pilot-small">{{ meta.unit }}</span>
                  </dd>
                </div>
              </dl>
              <p v-else class="pilot-small">还没有录入任何指标，进入接诊页开始补录。</p>
              <RouterLink :to="`/encounters/${latestEncounter.id}`" class="pilot-btn metric-action">查看并补录全部指标</RouterLink>
            </template>
          </SectionPanel>

          <SectionPanel title="本次风险与发布">
            <template v-if="latestEncounter">
              <div class="risk-panel-head">
                <span class="pilot-section-label">最近一次评估</span>
                <StatusPill :label="riskLabel" :tone="riskTone" />
              </div>
              <div v-if="latestPrediction?.probability != null" class="risk-panel-prob">
                <strong>{{ probabilityText }}</strong>
                <span>预测概率</span>
              </div>
              <p v-else class="pilot-small risk-panel-copy">尚未运行模型，或本次为人工审核记录。</p>
              <p class="pilot-small risk-panel-copy">评估时间 {{ fmt(latestEncounter.updated_at) }}</p>
              <RouterLink :to="`/encounters/${latestEncounter.id}`" class="pilot-btn pilot-btn-primary risk-panel-action">进入接诊与发布</RouterLink>
              <RouterLink
                v-if="latestReport?.status === 'published'"
                :to="`/reports/${latestReport.id}`"
                class="pilot-btn risk-panel-action"
              >查看正式报告 {{ latestReport.report_no }}</RouterLink>
              <p class="pilot-small risk-panel-note">发布需在接诊页完成复核后操作；已发布记录不能改指标。</p>
            </template>
            <EmptyState v-else title="暂无风险" description="创建并完成一次接诊后，这里显示概率与发布状态。" />
          </SectionPanel>
        </div>

        <div class="patient-lower" :class="{ 'patient-lower-single': !isAdmin }">
          <SectionPanel title="档案信息">
            <dl class="patient-info-grid">
              <div><dt>病历号</dt><dd class="pilot-mono">{{ patient.mrn }}</dd></div>
              <div><dt>性别 / 出生年</dt><dd>{{ patient.sex }} / {{ patient.birth_year ?? '—' }}</dd></div>
              <div><dt>负责人</dt><dd>{{ ownerName }}</dd></div>
              <div><dt>联系电话</dt><dd>{{ patient.phone || '未登记' }}</dd></div>
              <div><dt>证件信息</dt><dd>{{ patient.certificate || '未登记' }}</dd></div>
              <div><dt>状态</dt><dd>{{ patient.active ? '在管' : '已归档' }}</dd></div>
              <div><dt>创建时间</dt><dd>{{ fmt(patient.created_at) }}</dd></div>
              <div><dt>最近更新</dt><dd>{{ fmt(patient.updated_at) }}</dd></div>
            </dl>
          </SectionPanel>

          <SectionPanel v-if="isAdmin" title="医生访问授权">
            <p v-if="!patient.grants?.length" class="pilot-small">除档案负责人外，尚未授权其他医生。</p>
            <div v-else class="grant-list">
              <div v-for="grant in patient.grants" :key="grant.doctor_id" class="grant-row">
                <span>{{ grant.display_name }}</span>
                <StatusPill :label="grant.permission === 'edit' ? '可编辑' : '只读'" tone="accent" />
                <button class="pilot-btn pilot-btn-ghost grant-revoke" type="button" @click="removeGrant(grant.doctor_id)">撤销</button>
              </div>
            </div>
            <div class="grant-form">
              <select v-model="grantForm.doctor_id" class="pilot-select" aria-label="选择医生">
                <option value="">选择医生…</option>
                <option v-for="doctor in doctors.filter(item => item.id !== patient.owner_id)" :key="doctor.id" :value="doctor.id">{{ doctor.display_name }}</option>
              </select>
              <select v-model="grantForm.permission" class="pilot-select" aria-label="授权权限">
                <option value="view">只读</option><option value="edit">可编辑</option>
              </select>
              <button class="pilot-btn" type="button" @click="addGrant">添加授权</button>
            </div>
          </SectionPanel>
        </div>
      </template>
    </div>

    <!-- 新建就诊 -->
    <div v-if="showEncounter" class="modal-mask" @click.self="showEncounter = false">
      <div class="modal-panel patient-modal">
        <div class="modal-head">
          <div><div class="modal-title">新建就诊</div><div class="modal-sub">为 {{ patient?.name }} 建立一次围手术期风险评估。</div></div>
          <button class="modal-close" type="button" aria-label="关闭" @click="showEncounter = false">×</button>
        </div>
        <div class="modal-body">
          <div class="pilot-form-grid">
            <div class="pilot-field">
              <label for="encounter-ref">就诊编号 *</label>
              <input id="encounter-ref" v-model="encForm.case_ref" class="pilot-input" />
            </div>
            <div class="pilot-field">
              <label for="encounter-time">发生时间 *</label>
              <input id="encounter-time" v-model="encForm.occurred_at" class="pilot-input" type="datetime-local" />
            </div>
            <div class="pilot-field span-2">
              <label for="encounter-surgery">手术类型</label>
              <input id="encounter-surgery" v-model="encForm.surgery_type" class="pilot-input" placeholder="如 冠脉搭桥术" />
              <span class="pilot-field-hint">诊断与医嘱在接诊页填写，避免两处重复录入。</span>
            </div>
          </div>
          <div v-if="formError" class="pilot-error patient-modal-error">{{ formError }}</div>
        </div>
        <div class="modal-foot">
          <button class="pilot-btn" type="button" @click="showEncounter = false">取消</button>
          <button class="pilot-btn pilot-btn-primary" type="button" :disabled="saveBusy" @click="submitEncounter">{{ saveBusy ? '创建中…' : '创建并进入接诊' }}</button>
        </div>
      </div>
    </div>

    <!-- 编辑档案 -->
    <div v-if="showEdit" class="modal-mask" @click.self="showEdit = false">
      <div class="modal-panel patient-modal">
        <div class="modal-head">
          <div><div class="modal-title">编辑患者档案</div><div class="modal-sub">证件与电话留空表示不修改已保存的末四位。</div></div>
          <button class="modal-close" type="button" aria-label="关闭" @click="showEdit = false">×</button>
        </div>
        <div class="modal-body">
          <div class="pilot-form-grid">
            <div class="pilot-field"><label for="edit-name">姓名</label><input id="edit-name" v-model="editForm.name" class="pilot-input" /></div>
            <div class="pilot-field"><label for="edit-sex">性别</label><select id="edit-sex" v-model="editForm.sex" class="pilot-select"><option>男</option><option>女</option><option>未知</option></select></div>
            <div class="pilot-field"><label for="edit-birth">出生年份</label><input id="edit-birth" v-model="editForm.birth_year" class="pilot-input" type="number" /></div>
            <div class="pilot-field"><label for="edit-status">状态</label><select id="edit-status" v-model="editForm.active" class="pilot-select"><option :value="true">在管</option><option :value="false">归档</option></select></div>
            <div class="pilot-field"><label for="edit-cert">证件号末四位（更新）</label><input id="edit-cert" v-model="editForm.certificate_last4" class="pilot-input" maxlength="4" /></div>
            <div class="pilot-field"><label for="edit-phone">手机号末四位（更新）</label><input id="edit-phone" v-model="editForm.phone_last4" class="pilot-input" maxlength="4" /></div>
            <div v-if="isAdmin" class="pilot-field span-2">
              <label for="edit-owner">档案负责人</label>
              <select id="edit-owner" v-model="editForm.owner_id" class="pilot-select">
                <option v-for="doctor in doctors" :key="doctor.id" :value="doctor.id">{{ doctor.display_name }}</option>
              </select>
            </div>
          </div>
          <div v-if="formError" class="pilot-error patient-modal-error">{{ formError }}</div>
        </div>
        <div class="modal-foot">
          <button class="pilot-btn" type="button" @click="showEdit = false">取消</button>
          <button class="pilot-btn pilot-btn-primary" type="button" :disabled="saveBusy" @click="submitEdit">保存</button>
        </div>
      </div>
    </div>

    <!-- 查询码 -->
    <div
      v-if="showQuery"
      class="modal-mask"
      @click.self="closeQuery"
      @keydown="onQueryKeydown"
    >
      <div
        ref="queryModal"
        class="modal-panel patient-query-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="patient-query-title"
        tabindex="-1"
      >
        <div class="modal-head">
          <div id="patient-query-title" class="modal-title">患者查询码</div>
          <button class="modal-close" type="button" aria-label="关闭" @click="closeQuery">×</button>
        </div>
        <div class="modal-body patient-query-body">
          <div class="patient-query-code pilot-mono">{{ queryResult?.query_code }}</div>
          <p class="pilot-notice patient-query-notice">{{ queryResult?.notice }}</p>
          <p class="pilot-small">过期时间：{{ fmt(new Date((queryResult?.expires_at ?? 0) * 1000).toISOString()) }}</p>
          <p v-if="copyState" class="pilot-small" role="status">{{ copyState }}</p>
          <button class="pilot-btn" type="button" @click="copyCode">复制查询码</button>
        </div>
        <div class="modal-foot">
          <button class="pilot-btn pilot-btn-primary" type="button" @click="closeQuery">我已记录</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.patient-page { padding-top: var(--pilot-space-4); }
.patient-topline { margin-bottom: var(--pilot-space-3); }
.patient-back { font-size: var(--pilot-font-xs); }
.patient-loading { height: 280px; margin-top: var(--pilot-space-3); }
.patient-banner { align-items: flex-start; }
.patient-banner-meta { margin-top: var(--pilot-space-3); }
.patient-banner-side { align-items: flex-end; }
.patient-risk-side {
  display: flex;
  align-items: flex-end;
  flex-direction: column;
  gap: var(--pilot-space-1);
}
.patient-risk-prob { color: var(--pilot-ink); font-size: var(--pilot-font-lg); line-height: 1.1; }
.patient-actions { justify-content: flex-end; }
.patient-layout {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--pilot-space-4);
  margin-top: var(--pilot-space-4);
  align-items: stretch;
}
.encounter-list { display: flex; flex-direction: column; }
.encounter-row {
  display: block;
  padding: var(--pilot-space-3) var(--pilot-space-4);
  border-bottom: 1px solid var(--pilot-line);
  color: inherit;
  text-decoration: none;
}
.encounter-row:last-child { border-bottom: 0; }
.encounter-row:hover { background: var(--pilot-hover); }
.encounter-row:focus-visible { outline: 2px solid var(--pilot-accent); outline-offset: -2px; }
.encounter-row-head { display: flex; align-items: center; justify-content: space-between; gap: var(--pilot-space-2); }
.encounter-ref { color: var(--pilot-ink); font-size: var(--pilot-font-xs); font-weight: 600; }
.encounter-row-meta { margin-top: var(--pilot-space-1); color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
.encounter-row-foot { display: flex; align-items: center; gap: var(--pilot-space-2); margin-top: var(--pilot-space-2); flex-wrap: wrap; }
.metric-head { display: flex; align-items: baseline; gap: var(--pilot-space-2); margin-bottom: var(--pilot-space-4); }
.metric-head strong { color: var(--pilot-ink); font-size: var(--pilot-font-xl); line-height: 1; }
.metric-head strong span { color: var(--pilot-muted); font-size: var(--pilot-font-sm); font-weight: 400; }
.metric-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 var(--pilot-space-4); margin: 0; }
.metric-list > div {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--pilot-space-2);
  padding: var(--pilot-space-2) 0;
  border-bottom: 1px dashed var(--pilot-line);
}
.metric-list dt { overflow: hidden; color: var(--pilot-muted); font-size: var(--pilot-font-xs); text-overflow: ellipsis; white-space: nowrap; }
.metric-list dd { margin: 0; color: var(--pilot-ink); font-size: var(--pilot-font-sm); font-weight: 600; text-align: right; }
.metric-action { width: 100%; margin-top: var(--pilot-space-4); }
.risk-panel-head { display: flex; align-items: center; justify-content: space-between; gap: var(--pilot-space-2); }
.risk-panel-prob { display: flex; align-items: baseline; gap: var(--pilot-space-2); margin-top: var(--pilot-space-4); }
.risk-panel-prob strong { color: var(--pilot-ink); font-size: var(--pilot-font-xl); line-height: 1; }
.risk-panel-prob span { color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
.risk-panel-copy { margin: var(--pilot-space-3) 0 0; line-height: 1.5; }
.risk-panel-action { width: 100%; margin-top: var(--pilot-space-3); }
.risk-panel-note { margin: var(--pilot-space-3) 0 0; line-height: 1.5; }
.patient-lower {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--pilot-space-4);
  margin-top: var(--pilot-space-4);
  align-items: stretch;
}
.patient-lower-single { grid-template-columns: minmax(0, 1fr); }
.patient-info-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--pilot-space-3) var(--pilot-space-4); margin: 0; }
.patient-info-grid dt { color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
.patient-info-grid dd { margin: var(--pilot-space-1) 0 0; color: var(--pilot-ink-soft); font-size: var(--pilot-font-sm); word-break: break-all; }
.grant-list { display: flex; flex-direction: column; }
.grant-row { display: flex; align-items: center; gap: var(--pilot-space-2); padding: var(--pilot-space-2) 0; border-bottom: 1px dashed var(--pilot-line); }
.grant-row > span:first-child { flex: 1; color: var(--pilot-ink-soft); font-size: var(--pilot-font-sm); }
.grant-revoke { color: var(--pilot-high); }
.grant-form { display: flex; gap: var(--pilot-space-2); margin-top: var(--pilot-space-4); flex-wrap: wrap; }
.grant-form .pilot-select { width: 150px; }
.patient-modal { width: min(620px, calc(100% - 32px)); }
.patient-modal-error { margin: var(--pilot-space-4) 0 0; }
.patient-query-modal { width: min(460px, calc(100% - 32px)); }
.patient-query-body { text-align: center; }
.patient-query-code {
  padding: var(--pilot-space-4) 0;
  color: var(--pilot-accent);
  font-size: 30px;
  font-weight: 700;
  letter-spacing: .14em;
}
.patient-query-notice { margin: 0 0 var(--pilot-space-3); text-align: left; }
@media (max-width: 1360px) {
  .metric-list { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 1024px) {
  .patient-layout { grid-template-columns: minmax(0, 1fr); }
  .patient-lower { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 650px) {
  .patient-banner-side { width: 100%; align-items: flex-start; }
  .patient-risk-side { align-items: flex-start; }
  .patient-actions { justify-content: flex-start; }
  .metric-list { grid-template-columns: minmax(0, 1fr); }
  .patient-info-grid { grid-template-columns: minmax(0, 1fr); }
}
</style>

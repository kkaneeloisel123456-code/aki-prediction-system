<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import PageHeader from '../components/PageHeader.vue'
import SectionPanel from '../components/SectionPanel.vue'
import EmptyState from '../components/EmptyState.vue'
import StatusPill from '../components/StatusPill.vue'
import PilotTabs from '../components/PilotTabs.vue'
import ThemeSwitch from '../components/ThemeSwitch.vue'
import { api, saveBlob } from '../api/client'

type Tone = 'neutral' | 'low' | 'mid' | 'high' | 'accent'

const initialized = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const status = ref<any>({ authenticated: false, account: null, patient: null })
const authMode = ref('login')
const tab = ref('overview')
const loadingData = ref(false)

const loginForm = reactive({ username: '', password: '' })
const registerForm = reactive({ username: '', display_name: '', password: '', phone_last4: '' })
const queryForm = reactive({ mrn: '', name: '', query_code: '', certificate_last4: '', phone_last4: '' })
const bindForm = reactive({ mrn: '', name: '', query_code: '', certificate_last4: '', phone_last4: '' })

const reports = ref<any[]>([])
const appointments = ref<any[]>([])
const feedback = ref<any[]>([])
const slots = ref<any[]>([])
const booking = reactive({ slot_id: '', reason: '' })
const feedbackForm = reactive({ appointment_id: '', doctor_id: '', rating: 5, content: '' })
const detail = ref<any>(null)
const showReport = ref(false)
const showBooking = ref(false)
const showFeedback = ref(false)
const cancelTarget = ref<any>(null)
const cancelOpen = ref(false)
const cancelBusy = ref(false)

const authTabs = [
  { value: 'login', label: '账号登录' },
  { value: 'register', label: '注册账号' },
  { value: 'query', label: '查询码查询' },
]

const account = computed(() => status.value?.account)
const patient = computed(() => status.value?.patient)
const isQueryMode = computed(() => status.value?.mode === 'query_code')
const completedAppointments = computed(() => appointments.value.filter((a) => a.status === 'completed'))
const feedbackIds = computed(() => new Set(feedback.value.map((item) => item.appointment_id).filter(Boolean)))
const evaluableAppointments = computed(() => completedAppointments.value.filter((item) => !feedbackIds.value.has(item.id)))
const upcoming = computed(() =>
  appointments.value
    .filter((a) => a.status === 'booked' || a.status === 'checked_in')
    .sort((a, b) => {
      const ta = Date.parse(a.scheduled_at)
      const tb = Date.parse(b.scheduled_at)
      return (Number.isNaN(ta) ? 0 : ta) - (Number.isNaN(tb) ? 0 : tb)
    }),
)

const pageTitle = computed(() => {
  if (!status.value.authenticated) return '患者身份核验'
  if (!status.value.patient) return '绑定本人档案'
  if (isQueryMode.value) return '报告查询'
  return '我的报告与随访'
})
const pageKicker = computed(() => {
  if (!status.value.authenticated) return '患者门户'
  if (isQueryMode.value) return '患者服务 / 查询码会话'
  if (!status.value.patient) return '患者服务 / 账号已登录'
  return '患者服务 / 已绑定'
})
const pageDescription = computed(() => {
  if (!status.value.authenticated) return '使用账号登录，或凭医院发放的查询码查看本人报告。'
  if (!status.value.patient) return '账号尚未关联患者档案，请使用医院提供的查询码完成绑定。'
  if (isQueryMode.value) return '临时查询会话只显示已发布报告，离开页面或超时后失效。'
  return `病历号 ${patient.value?.mrn || '—'} · ${reports.value.length} 份报告 · 待就诊 ${upcoming.value.length} 个`
})
const sessionLabel = computed(() => {
  if (isQueryMode.value) return '查询码临时会话'
  return account.value?.display_name || account.value?.username || '已实名绑定'
})

const appTabs = computed(() => {
  const tabs = [
    { value: 'overview', label: '首页' },
    { value: 'reports', label: '我的报告', count: reports.value.length },
  ]
  if (!isQueryMode.value) {
    tabs.push({ value: 'appointments', label: '预约就诊', count: upcoming.value.length })
    tabs.push({ value: 'feedback', label: '评价', count: feedback.value.length })
  }
  return tabs
})

const summaryItems = computed(() => {
  const items = [
    { label: '患者', value: patient.value?.name || '—', hint: patient.value?.mrn || '' },
    { label: '正式报告', value: reports.value.length, hint: '已发布可查看' },
  ]
  if (!isQueryMode.value) {
    items.push({ label: '待就诊', value: upcoming.value.length, hint: '已预约 / 已签到' })
    items.push({ label: '我的评价', value: feedback.value.length, hint: '含待审核' })
  }
  return items
})

const detailResult = computed(() => detail.value?.snapshot?.prediction?.result ?? {})
const detailProbability = computed(() => {
  const probability = detailResult.value?.probability
  return typeof probability === 'number' ? `${(probability * 100).toFixed(1)}%` : null
})
const detailRisk = computed(() => {
  if (detailResult.value?.manual || detailProbability.value === null) return '人工审核'
  return detailResult.value?.risk_level || '未分级'
})

const appointmentStatus: Record<string, string> = {
  booked: '已预约',
  checked_in: '已签到',
  completed: '已完成',
  cancelled: '已取消',
  no_show: '爽约',
}

function fmt(value?: string) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}
function riskTone(level?: string): Tone {
  if (level === '高') return 'high'
  if (level === '中') return 'mid'
  if (level === '低') return 'low'
  return 'neutral'
}
function riskLabel(level?: string) {
  if (!level) return '人工审核'
  return level === '人工审核' ? level : `${level}风险`
}
function appointmentTone(value?: string): Tone {
  if (value === 'completed') return 'low'
  if (value === 'checked_in') return 'mid'
  if (value === 'booked') return 'accent'
  if (value === 'cancelled' || value === 'no_show') return 'high'
  return 'neutral'
}
function feedbackTone(value?: string): Tone {
  if (value === 'public') return 'low'
  if (value === 'pending') return 'mid'
  return 'neutral'
}
function hasFeedback(appointment: any) {
  return feedbackIds.value.has(appointment.id)
}
function canCancel(appointment: any) {
  return appointment.status === 'booked'
}

async function refreshStatus() {
  try {
    status.value = await api.portal.status()
    if (status.value.authenticated) await loadData()
    else clearData()
  } catch {
    status.value = { authenticated: false, account: null, patient: null }
    clearData()
  }
}
function clearData() {
  reports.value = []
  appointments.value = []
  feedback.value = []
  slots.value = []
}
async function loadData() {
  loadingData.value = true
  try {
    const [reportResult, appointmentResult, feedbackResult] = await Promise.all([
      api.portal.reports(),
      api.portal.appointments().catch(() => ({ appointments: [] })),
      api.portal.myFeedback().catch(() => ({ feedback: [] })),
    ])
    reports.value = reportResult.reports ?? []
    appointments.value = appointmentResult.appointments ?? []
    feedback.value = feedbackResult.feedback ?? []
    if (status.value.authenticated && status.value.patient && !isQueryMode.value) {
      const slotResult = await api.portal.slots().catch(() => ({ slots: [] }))
      slots.value = slotResult.slots ?? []
    }
  } catch (e: any) {
    if (!reports.value.length) error.value = e?.message ?? '数据加载失败'
  } finally {
    loadingData.value = false
  }
}

async function doLogin() {
  error.value = ''
  notice.value = ''
  if (!loginForm.username || !loginForm.password) {
    error.value = '请输入账号和密码'
    return
  }
  busy.value = true
  try {
    await api.portal.login(loginForm.username, loginForm.password)
    await refreshStatus()
    tab.value = 'overview'
  } catch (e: any) {
    error.value = e?.message ?? '登录失败'
  } finally {
    busy.value = false
  }
}
async function doRegister() {
  error.value = ''
  notice.value = ''
  if (!registerForm.username || !registerForm.display_name || registerForm.password.length < 12) {
    error.value = '账号、姓名必填，密码至少 12 个字符'
    return
  }
  busy.value = true
  try {
    await api.portal.register({ ...registerForm })
    await api.portal.login(registerForm.username, registerForm.password)
    await refreshStatus()
    notice.value = '注册成功。请使用医院提供的查询码绑定本人档案。'
  } catch (e: any) {
    error.value = e?.message ?? '注册失败'
  } finally {
    busy.value = false
  }
}
async function doQuery() {
  error.value = ''
  notice.value = ''
  if (!queryForm.mrn || !queryForm.name || !queryForm.query_code) {
    error.value = '请填写病历号、姓名和查询码'
    return
  }
  if (!queryForm.certificate_last4 && !queryForm.phone_last4) {
    error.value = '请填写证件号末四位或手机号末四位'
    return
  }
  busy.value = true
  try {
    const result = await api.portal.query({ ...queryForm })
    await refreshStatus()
    tab.value = 'reports'
    notice.value = `身份核验成功，可查看 ${result.report_count} 份已发布报告。本临时会话将在 ${Math.round((result.expires_in ?? 0) / 60)} 分钟后失效。`
  } catch (e: any) {
    error.value = e?.message ?? '核验失败'
  } finally {
    busy.value = false
  }
}
async function doBind() {
  error.value = ''
  notice.value = ''
  if (!bindForm.mrn || !bindForm.name || !bindForm.query_code) {
    error.value = '请填写完整信息'
    return
  }
  if (!bindForm.certificate_last4 && !bindForm.phone_last4) {
    error.value = '请填写证件号末四位或手机号末四位'
    return
  }
  busy.value = true
  try {
    await api.portal.bind({ ...bindForm })
    await refreshStatus()
    notice.value = '档案绑定成功'
  } catch (e: any) {
    error.value = e?.message ?? '绑定失败'
  } finally {
    busy.value = false
  }
}
async function logout() {
  try {
    await api.portal.logout()
  } finally {
    status.value = { authenticated: false, account: null, patient: null }
    clearData()
    tab.value = 'overview'
    notice.value = ''
    error.value = ''
  }
}

async function openReport(report: any) {
  error.value = ''
  try {
    const result = await api.portal.report(report.id)
    detail.value = result.report ?? result
    showReport.value = true
  } catch (e: any) {
    error.value = e?.message ?? '报告加载失败'
  }
}
async function download(report: any) {
  try {
    const blob = await api.portal.reportPdf(report.id)
    saveBlob(blob, `${report.report_no}.pdf`)
  } catch (e: any) {
    error.value = e?.message ?? '下载失败'
  }
}
function openBooking() {
  error.value = ''
  showBooking.value = true
}
async function submitBooking() {
  error.value = ''
  if (!booking.slot_id) {
    error.value = '请选择号源'
    return
  }
  busy.value = true
  try {
    await api.portal.appointment({ slot_id: booking.slot_id, reason: booking.reason })
    showBooking.value = false
    booking.slot_id = ''
    booking.reason = ''
    notice.value = '预约成功'
    await loadData()
  } catch (e: any) {
    error.value = e?.message ?? '预约失败'
  } finally {
    busy.value = false
  }
}
function openFeedback(appointment?: any) {
  const target = appointment ?? evaluableAppointments.value[0]
  Object.assign(feedbackForm, {
    appointment_id: target?.id ?? '',
    doctor_id: target?.doctor_id ?? '',
    rating: 5,
    content: '',
  })
  error.value = ''
  showFeedback.value = true
}
async function submitFeedback() {
  error.value = ''
  if (!feedbackForm.appointment_id && !feedbackForm.doctor_id) {
    error.value = '请选择已完成的就诊或医生'
    return
  }
  busy.value = true
  try {
    await api.portal.feedback({ ...feedbackForm })
    showFeedback.value = false
    notice.value = '评价已提交，审核通过后公开显示。'
    await loadData()
  } catch (e: any) {
    error.value = e?.message ?? '评价提交失败'
  } finally {
    busy.value = false
  }
}
function askCancel(appointment: any) {
  cancelTarget.value = appointment
  error.value = ''
  cancelOpen.value = true
}
async function confirmCancel() {
  if (!cancelTarget.value) return
  cancelBusy.value = true
  error.value = ''
  try {
    await api.portal.cancelAppointment(cancelTarget.value.id, '患者端取消')
    cancelOpen.value = false
    cancelTarget.value = null
    notice.value = '预约已取消'
    await loadData()
  } catch (e: any) {
    error.value = e?.message ?? '取消失败'
  } finally {
    cancelBusy.value = false
  }
}

onMounted(async () => {
  await refreshStatus()
  initialized.value = true
})
</script>

<template>
  <div class="portal-page">
    <header class="portal-masthead">
      <div class="portal-masthead-inner">
        <div class="portal-brand">
          <div class="portal-logo" aria-hidden="true">AKI</div>
          <div class="portal-brand-copy">
            <strong>AKI 患者服务</strong>
            <span>急性肾损伤风险报告与随访</span>
          </div>
        </div>
        <div class="portal-mast-actions">
          <ThemeSwitch />
          <RouterLink to="/login" class="pilot-btn pilot-btn-ghost portal-staff-link">医护人员入口</RouterLink>
          <button v-if="status.authenticated" class="pilot-btn pilot-btn-sm" type="button" @click="logout">退出</button>
        </div>
      </div>
    </header>

    <main class="portal-main">
      <PageHeader v-if="status.authenticated || !initialized" :kicker="pageKicker" :title="pageTitle" :description="pageDescription" />

      <div v-if="error" class="pilot-error" role="alert">{{ error }}</div>
      <div v-if="notice" class="pilot-notice" role="status">{{ notice }}</div>

      <div v-if="!initialized" class="portal-loading" aria-label="正在连接患者服务">
        <div class="pilot-skeleton portal-skeleton" />
      </div>

      <div v-else-if="!status.authenticated" class="portal-auth-grid">
        <p class="pilot-kicker portal-auth-kicker">{{ pageKicker }}</p>
        <h1 class="pilot-title portal-auth-title">{{ pageTitle }}</h1>
        <p class="pilot-sub portal-auth-desc">{{ pageDescription }}</p>
        <section class="portal-auth-story">
          <p class="pilot-kicker">患者可以做什么</p>
          <h2>报告、预约与评价，集中查看。</h2>
          <p class="portal-auth-lead">
            绑定本人档案后，这里会保留医生发布的 AKI 风险报告、预约记录和评价记录。
          </p>
          <ol class="portal-feature-list">
            <li><b>01</b><span>使用账号登录，或凭医院查询码快速核验。</span></li>
            <li><b>02</b><span>绑定病历号后，查看正式发布的报告。</span></li>
            <li><b>03</b><span>需要复查时自行预约，完成后提交评价。</span></li>
          </ol>
          <p class="portal-auth-foot note">查询码会话仅用于查看报告，不展示预约和评价。</p>
        </section>
        <aside class="portal-auth-card">
          <h2 class="portal-auth-card-title">身份核验</h2>
          <p class="portal-auth-card-sub">选择一种入口进入患者服务</p>
          <PilotTabs v-model="authMode" :tabs="authTabs" label="患者身份核验方式" />

          <form v-if="authMode === 'login'" class="portal-form" @submit.prevent="doLogin">
            <div class="portal-form-grid">
              <div class="pilot-field span-2">
                <label for="portal-login-username">登录账号</label>
                <input id="portal-login-username" v-model="loginForm.username" class="pilot-input" autocomplete="username" placeholder="患者账号" />
              </div>
              <div class="pilot-field span-2">
                <label for="portal-login-password">密码</label>
                <input id="portal-login-password" v-model="loginForm.password" class="pilot-input" type="password" autocomplete="current-password" placeholder="登录密码" />
              </div>
            </div>
            <button class="pilot-btn pilot-btn-primary portal-submit" type="submit" :disabled="busy">{{ busy ? '登录中…' : '登录' }}</button>
          </form>

          <form v-else-if="authMode === 'register'" class="portal-form" @submit.prevent="doRegister">
            <div class="portal-form-grid">
              <div class="pilot-field">
                <label for="portal-register-username">登录账号</label>
                <input id="portal-register-username" v-model="registerForm.username" class="pilot-input" autocomplete="username" placeholder="4–64 位字母、数字或 ._-" />
              </div>
              <div class="pilot-field">
                <label for="portal-register-name">姓名</label>
                <input id="portal-register-name" v-model="registerForm.display_name" class="pilot-input" autocomplete="name" />
              </div>
              <div class="pilot-field">
                <label for="portal-register-password">密码（至少 12 个字符）</label>
                <input id="portal-register-password" v-model="registerForm.password" class="pilot-input" type="password" autocomplete="new-password" />
              </div>
              <div class="pilot-field">
                <label for="portal-register-phone">手机号末四位（可选）</label>
                <input id="portal-register-phone" v-model="registerForm.phone_last4" class="pilot-input" maxlength="4" inputmode="numeric" />
              </div>
            </div>
            <button class="pilot-btn pilot-btn-primary portal-submit" type="submit" :disabled="busy">{{ busy ? '注册中…' : '注册并登录' }}</button>
            <p class="portal-form-hint">注册后仍需医院查询码绑定本人档案。</p>
          </form>

          <form v-else class="portal-form" @submit.prevent="doQuery">
            <p class="portal-form-intro">查询码由医院工作人员生成，需同时核对证件或手机末四位。</p>
            <div class="portal-form-grid">
              <div class="pilot-field">
                <label for="portal-query-mrn">病历号</label>
                <input id="portal-query-mrn" v-model="queryForm.mrn" class="pilot-input" />
              </div>
              <div class="pilot-field">
                <label for="portal-query-name">姓名</label>
                <input id="portal-query-name" v-model="queryForm.name" class="pilot-input" autocomplete="name" />
              </div>
              <div class="pilot-field span-2">
                <label for="portal-query-code">查询码</label>
                <input id="portal-query-code" v-model="queryForm.query_code" class="pilot-input pilot-mono portal-code-input" maxlength="8" autocomplete="off" />
              </div>
              <div class="pilot-field">
                <label for="portal-query-certificate">证件号末四位</label>
                <input id="portal-query-certificate" v-model="queryForm.certificate_last4" class="pilot-input" maxlength="4" inputmode="numeric" placeholder="与档案登记一致" />
              </div>
              <div class="pilot-field">
                <label for="portal-query-phone">或手机号末四位</label>
                <input id="portal-query-phone" v-model="queryForm.phone_last4" class="pilot-input" maxlength="4" inputmode="numeric" placeholder="二选一填写" />
              </div>
            </div>
            <button class="pilot-btn pilot-btn-primary portal-submit" type="submit" :disabled="busy">{{ busy ? '核验中…' : '核验并查看报告' }}</button>
            <p class="portal-form-hint">临时会话仅可查看已发布报告，过期需重新申领查询码。</p>
          </form>
        </aside>
      </div>

      <div v-else-if="!status.patient" class="portal-bind-layout">
        <SectionPanel title="绑定本人档案" subtitle="使用医院提供的查询码，将账号与病历号关联">
          <p class="portal-form-intro">绑定后才能查看本人报告、预约和评价。姓名与病历号不是秘密，因此还需核对证件或手机末四位。</p>
          <form class="portal-form" @submit.prevent="doBind">
            <div class="portal-form-grid">
              <div class="pilot-field">
                <label for="portal-bind-mrn">病历号</label>
                <input id="portal-bind-mrn" v-model="bindForm.mrn" class="pilot-input" />
              </div>
              <div class="pilot-field">
                <label for="portal-bind-name">姓名</label>
                <input id="portal-bind-name" v-model="bindForm.name" class="pilot-input" autocomplete="name" />
              </div>
              <div class="pilot-field span-2">
                <label for="portal-bind-code">查询码</label>
                <input id="portal-bind-code" v-model="bindForm.query_code" class="pilot-input pilot-mono portal-code-input" maxlength="8" autocomplete="off" />
              </div>
              <div class="pilot-field">
                <label for="portal-bind-certificate">证件号末四位</label>
                <input id="portal-bind-certificate" v-model="bindForm.certificate_last4" class="pilot-input" maxlength="4" inputmode="numeric" placeholder="与档案登记一致" />
              </div>
              <div class="pilot-field">
                <label for="portal-bind-phone">或手机号末四位</label>
                <input id="portal-bind-phone" v-model="bindForm.phone_last4" class="pilot-input" maxlength="4" inputmode="numeric" placeholder="二选一填写" />
              </div>
            </div>
            <button class="pilot-btn pilot-btn-primary portal-submit" type="submit" :disabled="busy">{{ busy ? '绑定中…' : '绑定档案' }}</button>
          </form>
        </SectionPanel>
      </div>

      <div v-else>
        <div class="portal-summary" :class="{ 'is-compact': isQueryMode }" aria-label="患者服务概览">
          <div v-for="item in summaryItems" :key="item.label" class="portal-summary-item">
            <span class="pilot-section-label">{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
            <small>{{ item.hint }}</small>
          </div>
        </div>

        <div class="portal-session-line">
          <PilotTabs v-model="tab" :tabs="appTabs" label="患者服务分区" />
          <StatusPill :label="sessionLabel" tone="accent" />
        </div>

        <div v-if="loadingData" class="portal-loading" aria-label="正在加载患者数据">
          <div class="pilot-skeleton portal-skeleton" />
        </div>

        <div v-else-if="tab === 'overview'" class="portal-overview">
          <SectionPanel title="最近报告" :subtitle="reports.length ? `${reports.length} 份已发布报告` : '医生审核发布后显示'">
            <EmptyState v-if="!reports.length" title="暂无已发布报告" description="医生完成复核并发布后，报告会出现在这里。" />
            <div v-else class="portal-report-list">
              <article v-for="report in reports.slice(0, 3)" :key="report.id" class="portal-report-row">
                <div class="portal-report-main">
                  <div class="portal-report-title">
                    <button class="portal-report-link" type="button" @click="openReport(report)">{{ report.report_no }}</button>
                    <StatusPill :label="riskLabel(report.risk_level)" :tone="riskTone(report.risk_level)" />
                  </div>
                  <div class="portal-meta">
                    <span>第 {{ report.version }} 版</span>
                    <span>{{ fmt(report.published_at) }}</span>
                    <span>就诊 {{ report.encounter?.case_ref || '—' }}</span>
                  </div>
                </div>
                <div class="portal-report-actions">
                  <button class="pilot-btn pilot-btn-sm" type="button" @click="openReport(report)">查看</button>
                  <button class="pilot-btn pilot-btn-sm pilot-btn-primary" type="button" @click="download(report)">PDF</button>
                </div>
              </article>
            </div>
          </SectionPanel>

          <SectionPanel v-if="!isQueryMode" title="下一次就诊" :subtitle="upcoming.length ? `${upcoming.length} 个待就诊预约` : '暂无待就诊预约'">
            <EmptyState v-if="!upcoming.length" title="暂无待就诊预约" description="需要复查时，可在“预约就诊”中选择可用号源。" />
            <article v-for="appointment in upcoming.slice(0, 1)" :key="appointment.id" class="portal-next-visit">
              <div>
                <strong>{{ fmt(appointment.scheduled_at) }} · {{ appointment.doctor_name }}</strong>
                <p class="portal-meta">{{ appointment.appointment_type }} · {{ appointmentStatus[appointment.status] }}</p>
              </div>
              <button class="pilot-btn pilot-btn-sm pilot-btn-danger" type="button" @click="askCancel(appointment)">取消预约</button>
            </article>
          </SectionPanel>
        </div>

        <SectionPanel v-else-if="tab === 'reports'" title="我的报告" :subtitle="`${reports.length} 份已发布报告 · 按发布时间倒序`" flush>
          <EmptyState v-if="!reports.length" title="暂无报告" description="医生完成复核并发布后，报告会出现在这里。" />
          <div v-else class="portal-table-wrap" role="region" aria-label="患者报告列表，窄屏可横向滚动" tabindex="0">
            <div class="portal-mobile-hint">左右滑动查看完整表格</div>
            <table class="pilot-table portal-table">
              <thead>
                <tr>
                  <th scope="col">报告编号</th>
                  <th scope="col">风险</th>
                  <th scope="col">版本</th>
                  <th scope="col">就诊</th>
                  <th scope="col">发布时间</th>
                  <th scope="col" class="cell-actions">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="report in reports" :key="report.id">
                  <td class="cell-strong cell-mono">{{ report.report_no }}</td>
                  <td><StatusPill :label="riskLabel(report.risk_level)" :tone="riskTone(report.risk_level)" /></td>
                  <td>v{{ report.version }}</td>
                  <td>{{ report.encounter?.case_ref || '—' }}</td>
                  <td>{{ fmt(report.published_at) }}</td>
                  <td class="cell-actions">
                    <button class="pilot-btn pilot-btn-sm" type="button" @click="openReport(report)">查看</button>
                    <button class="pilot-btn pilot-btn-sm pilot-btn-primary" type="button" @click="download(report)">PDF</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </SectionPanel>

        <SectionPanel v-else-if="tab === 'appointments'" title="我的预约" :subtitle="`${appointments.length} 条预约记录`" flush>
          <template #actions>
            <button class="pilot-btn pilot-btn-primary pilot-btn-sm" type="button" @click="openBooking">＋ 预约就诊</button>
          </template>
          <EmptyState v-if="!appointments.length" title="暂无预约" description="需要复查时，选择可用号源提交预约。" />
          <div v-else class="portal-table-wrap" role="region" aria-label="患者预约列表，窄屏可横向滚动" tabindex="0">
            <div class="portal-mobile-hint">左右滑动查看完整表格</div>
            <table class="pilot-table portal-table">
              <thead>
                <tr>
                  <th scope="col">就诊时间</th>
                  <th scope="col">医生</th>
                  <th scope="col">类型</th>
                  <th scope="col">状态</th>
                  <th scope="col">原因</th>
                  <th scope="col" class="cell-actions">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="appointment in appointments" :key="appointment.id">
                  <td class="cell-strong">{{ fmt(appointment.scheduled_at) }}</td>
                  <td>{{ appointment.doctor_name }}</td>
                  <td>{{ appointment.appointment_type }}</td>
                  <td><StatusPill :label="appointmentStatus[appointment.status] || appointment.status" :tone="appointmentTone(appointment.status)" /></td>
                  <td class="portal-reason">{{ appointment.reason || '—' }}</td>
                  <td class="cell-actions">
                    <button v-if="canCancel(appointment)" class="pilot-btn pilot-btn-sm pilot-btn-danger" type="button" @click="askCancel(appointment)">取消</button>
                    <button v-if="appointment.status === 'completed' && !hasFeedback(appointment)" class="pilot-btn pilot-btn-sm" type="button" @click="openFeedback(appointment)">评价</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </SectionPanel>

        <SectionPanel v-else-if="tab === 'feedback'" title="我的评价" :subtitle="`${feedback.length} 条评价 · 审核后公开`">
          <template #actions>
            <button class="pilot-btn pilot-btn-primary pilot-btn-sm" type="button" :disabled="!evaluableAppointments.length" @click="openFeedback()">＋ 提交评价</button>
          </template>
          <div v-if="!completedAppointments.length" class="portal-inline-note">只有已完成的就诊可以评价。</div>
          <div v-else-if="!evaluableAppointments.length" class="portal-inline-note">已完成的就诊均已评价，审核通过后公开显示。</div>
          <EmptyState v-if="!feedback.length" title="还没有评价" description="完成一次就诊后，可以提交对医生和就医体验的评价。" />
          <div v-else class="portal-feedback-list">
            <article v-for="item in feedback" :key="item.id" class="portal-feedback-card">
              <div class="portal-feedback-head">
                <strong>{{ item.doctor_name || '医生' }}</strong>
                <span class="portal-stars" :aria-label="`${item.rating} 星`">{{ '★'.repeat(item.rating) }}</span>
              </div>
              <p class="portal-feedback-copy">{{ item.content || '未填写文字评价' }}</p>
              <div class="portal-feedback-foot">
                <span>{{ fmt(item.created_at) }}</span>
                <StatusPill :label="item.status === 'public' ? '已公开' : item.status === 'pending' ? '待审核' : '已隐藏'" :tone="feedbackTone(item.status)" />
              </div>
            </article>
          </div>
        </SectionPanel>
      </div>
    </main>

    <ElDialog
      v-model="showReport"
      :title="detail?.report_no || '报告详情'"
      class="pilot-dialog"
      width="min(900px, calc(100vw - 32px))"
      append-to-body
    >
      <div v-if="detail" class="portal-report-detail">
        <div class="portal-report-banner">
          <div class="portal-risk-block" :class="detailRisk === '高' ? 'is-high' : detailRisk === '中' ? 'is-mid' : detailRisk === '低' ? 'is-low' : 'is-neutral'">
            <span class="pilot-section-label">AKI 风险</span>
            <strong>{{ detailProbability ?? '人工审核' }}</strong>
            <StatusPill :label="detailRisk === '人工审核' ? '人工审核' : `${detailRisk}风险`" :tone="riskTone(detailRisk)" />
          </div>
          <div class="portal-report-copy">
            <div class="portal-meta">
              <span>{{ detail.patient_name || patient?.name || '患者' }}</span>
              <span>第 {{ detail.version }} 版</span>
              <span>{{ fmt(detail.published_at) }}</span>
            </div>
            <p><b>诊断：</b>{{ detail.snapshot?.encounter?.diagnosis || '—' }}</p>
            <p><b>医嘱：</b>{{ detail.snapshot?.encounter?.orders || '—' }}</p>
            <p><b>复核：</b>{{ detail.snapshot?.review?.reviewer_name || '—' }} · {{ detail.snapshot?.review?.reason || '—' }}</p>
          </div>
        </div>
        <p class="portal-report-note">
          本次评估为{{ detailRisk === '人工审核' ? '人工审核结果' : `${detailRisk}风险（概率 ${detailProbability}）` }}，仅作临床参考，不能替代医生诊断或医嘱。
        </p>
        <div class="portal-hash">
          <span class="pilot-section-label">报告完整性 SHA-256</span>
          <code>{{ detail.sha256 || '—' }}</code>
        </div>
      </div>
      <template #footer>
        <button class="pilot-btn" type="button" @click="showReport = false">关闭</button>
        <button v-if="detail" class="pilot-btn pilot-btn-primary" type="button" @click="download(detail)">下载 PDF</button>
      </template>
    </ElDialog>

    <ElDialog v-model="showBooking" title="预约就诊" class="pilot-dialog" width="min(560px, calc(100vw - 32px))" append-to-body>
      <div class="portal-dialog-body">
        <p class="portal-form-intro">选择可用号源；就诊完成后可以提交评价。</p>
        <div v-if="error" class="pilot-error" role="alert">{{ error }}</div>
        <div class="pilot-field">
          <label for="portal-booking-slot">可用号源</label>
          <select id="portal-booking-slot" v-model="booking.slot_id" class="pilot-select">
            <option value="">选择号源…</option>
            <option v-for="slot in slots" :key="slot.id" :value="slot.id">
              {{ fmt(slot.starts_at) }} · {{ slot.doctor_name }} · {{ slot.appointment_type }}（余 {{ slot.capacity - slot.booked }}）
            </option>
          </select>
        </div>
        <div class="pilot-field portal-dialog-field">
          <label for="portal-booking-reason">就诊原因</label>
          <textarea id="portal-booking-reason" v-model="booking.reason" class="pilot-textarea" rows="3" placeholder="如 AKI 风险随访" />
        </div>
      </div>
      <template #footer>
        <button class="pilot-btn" type="button" @click="showBooking = false">取消</button>
        <button class="pilot-btn pilot-btn-primary" type="button" :disabled="busy" @click="submitBooking">{{ busy ? '提交中…' : '确认预约' }}</button>
      </template>
    </ElDialog>

    <ElDialog v-model="showFeedback" title="就诊评价" class="pilot-dialog" width="min(560px, calc(100vw - 32px))" append-to-body>
      <div class="portal-dialog-body">
        <p class="portal-form-intro">评价经医院审核后公开，不会影响后续诊疗。</p>
        <div v-if="error" class="pilot-error" role="alert">{{ error }}</div>
        <div class="pilot-field">
          <label for="portal-feedback-appointment">关联已完成就诊</label>
          <select id="portal-feedback-appointment" v-model="feedbackForm.appointment_id" class="pilot-select">
            <option value="">选择就诊…</option>
            <option v-for="appointment in completedAppointments" :key="appointment.id" :value="appointment.id">
              {{ fmt(appointment.scheduled_at) }} · {{ appointment.doctor_name }}
            </option>
          </select>
        </div>
        <div class="pilot-field portal-dialog-field">
          <label for="portal-feedback-rating">评分</label>
          <select id="portal-feedback-rating" v-model="feedbackForm.rating" class="pilot-select">
            <option :value="5">★★★★★ 非常满意</option>
            <option :value="4">★★★★ 满意</option>
            <option :value="3">★★★ 一般</option>
            <option :value="2">★★ 不满意</option>
            <option :value="1">★ 很不满意</option>
          </select>
        </div>
        <div class="pilot-field portal-dialog-field">
          <label for="portal-feedback-content">评价内容</label>
          <textarea id="portal-feedback-content" v-model="feedbackForm.content" class="pilot-textarea" rows="4" placeholder="描述您的就医体验（可选）" />
        </div>
      </div>
      <template #footer>
        <button class="pilot-btn" type="button" @click="showFeedback = false">取消</button>
        <button class="pilot-btn pilot-btn-primary" type="button" :disabled="busy" @click="submitFeedback">{{ busy ? '提交中…' : '提交评价' }}</button>
      </template>
    </ElDialog>

    <ElDialog v-model="cancelOpen" title="取消预约" class="pilot-dialog" width="min(420px, calc(100vw - 32px))" append-to-body>
      <div class="portal-dialog-body">
        <p class="portal-form-intro">确认取消本次预约？取消后号源会释放，如需复诊需重新预约。</p>
        <div v-if="cancelTarget" class="portal-cancel-summary">
          <strong>{{ fmt(cancelTarget.scheduled_at) }} · {{ cancelTarget.doctor_name }}</strong>
          <span>{{ cancelTarget.appointment_type }} · {{ appointmentStatus[cancelTarget.status] }}</span>
        </div>
        <div v-if="error" class="pilot-error" role="alert">{{ error }}</div>
      </div>
      <template #footer>
        <button class="pilot-btn" type="button" @click="cancelOpen = false">保留预约</button>
        <button class="pilot-btn pilot-btn-danger" type="button" :disabled="cancelBusy" @click="confirmCancel">{{ cancelBusy ? '取消中…' : '确认取消' }}</button>
      </template>
    </ElDialog>
  </div>
</template>

<style scoped>
.portal-page {
  min-height: 100vh;
  background: var(--pilot-bg);
  color: var(--pilot-ink);
}
.portal-masthead {
  border-bottom: 1px solid var(--pilot-line);
  background: var(--pilot-surface);
}
.portal-masthead-inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--pilot-space-4);
  width: min(1160px, 100%);
  min-height: 64px;
  margin: 0 auto;
  padding: 0 var(--pilot-space-5);
}
.portal-brand { display: flex; align-items: center; gap: var(--pilot-space-3); min-width: 0; }
.portal-logo {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  flex: 0 0 34px;
  border: 1px solid var(--pilot-line-strong);
  border-radius: var(--pilot-radius-control);
  color: var(--pilot-accent);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .06em;
}
.portal-brand-copy { display: flex; flex-direction: column; min-width: 0; }
.portal-brand-copy strong { color: var(--pilot-ink); font-size: var(--pilot-font-sm); }
.portal-brand-copy span { margin-top: 2px; color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
.portal-mast-actions { display: flex; align-items: center; gap: var(--pilot-space-2); flex-wrap: wrap; justify-content: flex-end; }
.portal-staff-link { font-size: var(--pilot-font-xs); }
.portal-main {
  width: min(1120px, 100%);
  margin: 0 auto;
  padding: var(--pilot-space-6) var(--pilot-space-5) var(--pilot-space-7);
}
.portal-auth-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(360px, 420px);
  column-gap: var(--pilot-space-6);
  grid-template-areas:
    "kicker ."
    "title card"
    "desc card"
    "story card";
  align-items: start;
}
.portal-auth-kicker { grid-area: kicker; }
.portal-auth-title { grid-area: title; margin: 4px 0 0; }
.portal-auth-desc { grid-area: desc; margin: var(--pilot-space-2) 0 0; }
.portal-auth-story { grid-area: story; max-width: 540px; margin-top: var(--pilot-space-5); }
.portal-auth-card {
  grid-area: card;
  align-self: start;
  background: transparent;
  border: 0;
  box-shadow: none;
  padding: 0;
}
.portal-auth-card-title { margin: 0; font-size: var(--pilot-font-lg); }
.portal-auth-card-sub { margin: var(--pilot-space-1) 0 var(--pilot-space-4); color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
.portal-auth-copy h2 {
  margin: var(--pilot-space-1) 0 var(--pilot-space-3);
  color: var(--pilot-ink);
  font-size: var(--pilot-font-lg);
  font-weight: 700;
  line-height: 1.3;
}
.portal-auth-lead { color: var(--pilot-muted); font-size: var(--pilot-font-sm); line-height: 1.7; }
.portal-feature-list { display: grid; gap: var(--pilot-space-3); margin-top: var(--pilot-space-5); padding: 0; list-style: none; }
.portal-feature-list li { display: flex; gap: var(--pilot-space-3); align-items: flex-start; color: var(--pilot-ink-soft); font-size: var(--pilot-font-sm); line-height: 1.6; }
.portal-feature-list b { flex: 0 0 24px; color: var(--pilot-accent); font-family: "SFMono-Regular", Consolas, monospace; font-size: var(--pilot-font-xs); }
.portal-auth-foot { margin-top: var(--pilot-space-5); padding-top: var(--pilot-space-3); border-top: 1px solid var(--pilot-line); font-size: var(--pilot-font-xs); line-height: 1.6; }
.portal-form { display: grid; gap: var(--pilot-space-3); }
.portal-form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--pilot-space-3); }
.portal-field-span { grid-column: 1 / -1; }
.portal-submit { width: 100%; margin-top: var(--pilot-space-2); }
.portal-form-hint { color: var(--pilot-muted); font-size: var(--pilot-font-xs); line-height: 1.6; }
.portal-form-intro { margin: 0 0 var(--pilot-space-3); color: var(--pilot-muted); font-size: var(--pilot-font-xs); line-height: 1.7; }
.portal-code-input { letter-spacing: .18em; text-transform: uppercase; }
.portal-bind-layout { max-width: 620px; margin-top: var(--pilot-space-3); }
.portal-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  overflow: hidden;
  border: 1px solid var(--pilot-line);
  border-radius: var(--pilot-radius-card);
  background: var(--pilot-surface);
}
.portal-summary.is-compact { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.portal-summary-item { min-width: 0; padding: var(--pilot-space-4); border-right: 1px solid var(--pilot-line); }
.portal-summary-item:last-child { border-right: 0; }
.portal-summary-item strong {
  display: block;
  margin-top: var(--pilot-space-1);
  overflow: hidden;
  color: var(--pilot-ink);
  font-size: var(--pilot-font-lg);
  font-variant-numeric: tabular-nums;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.portal-summary-item small { display: block; margin-top: var(--pilot-space-1); color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
.portal-session-line {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--pilot-space-3);
  margin-top: var(--pilot-space-5);
  border-bottom: 1px solid var(--pilot-line);
}
.portal-session-line :deep(.pilot-tabs) { flex: 1; margin-bottom: 0; border-bottom: 0; }
.portal-session-line > .pilot-chip { margin-top: var(--pilot-space-1); flex: 0 0 auto; }
.portal-overview { display: grid; grid-template-columns: minmax(0, 1.5fr) minmax(270px, 1fr); gap: var(--pilot-space-4); align-items: start; }
.portal-report-list { display: grid; }
.portal-report-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--pilot-space-4);
  padding: var(--pilot-space-4) 0;
  border-bottom: 1px solid var(--pilot-line);
}
.portal-report-row:last-child { border-bottom: 0; }
.portal-report-main { min-width: 0; }
.portal-report-title { display: flex; align-items: center; gap: var(--pilot-space-2); flex-wrap: wrap; }
.portal-report-link {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--pilot-ink);
  font: inherit;
  font-weight: 700;
  cursor: pointer;
  text-align: left;
}
.portal-report-link:hover { color: var(--pilot-accent); text-decoration: underline; }
.portal-report-actions { display: flex; gap: var(--pilot-space-2); flex: 0 0 auto; }
.portal-next-visit { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--pilot-space-3); }
.portal-next-visit strong { color: var(--pilot-ink); }
.portal-meta { display: flex; align-items: center; gap: var(--pilot-space-2); flex-wrap: wrap; margin-top: var(--pilot-space-2); color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
.portal-meta > span + span::before { content: "·"; margin-right: var(--pilot-space-2); color: var(--pilot-line-strong); }
.portal-table-wrap { max-width: 100%; overflow-x: auto; }
.portal-table { min-width: 760px; }
.portal-table .portal-reason { max-width: 240px; white-space: normal; }
.portal-mobile-hint { display: none; padding: var(--pilot-space-2) var(--pilot-space-4); color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
.portal-inline-note {
  margin-bottom: var(--pilot-space-3);
  padding: var(--pilot-space-2) var(--pilot-space-3);
  border-left: 3px solid var(--pilot-mid);
  background: var(--pilot-mid-soft);
  color: var(--pilot-mid);
  font-size: var(--pilot-font-xs);
}
.portal-feedback-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--pilot-space-3); }
.portal-feedback-card {
  padding: var(--pilot-space-4);
  border: 1px solid var(--pilot-line);
  border-radius: var(--pilot-radius-control);
  background: var(--pilot-surface-2);
}
.portal-feedback-head { display: flex; align-items: center; justify-content: space-between; gap: var(--pilot-space-2); }
.portal-feedback-head strong { color: var(--pilot-ink); }
.portal-stars { color: var(--pilot-mid); font-size: var(--pilot-font-sm); letter-spacing: .04em; }
.portal-feedback-copy { min-height: 40px; margin: var(--pilot-space-3) 0; color: var(--pilot-ink-soft); font-size: var(--pilot-font-sm); line-height: 1.6; }
.portal-feedback-foot { display: flex; align-items: center; justify-content: space-between; gap: var(--pilot-space-2); color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
.portal-loading { padding: var(--pilot-space-6) 0; }
.portal-skeleton { height: 180px; }
.portal-dialog-body { display: grid; gap: var(--pilot-space-4); }
.portal-dialog-field { display: grid; gap: var(--pilot-space-2); }
.portal-report-detail { display: grid; gap: var(--pilot-space-4); }
.portal-report-banner { display: grid; grid-template-columns: minmax(190px, .7fr) minmax(0, 1.3fr); gap: var(--pilot-space-4); }
.portal-risk-block {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--pilot-space-2);
  padding: var(--pilot-space-4);
  border: 1px solid var(--pilot-line);
  border-left: 4px solid var(--pilot-line-strong);
  border-radius: var(--pilot-radius-control);
  background: var(--pilot-surface-2);
}
.portal-risk-block.is-high { border-left-color: var(--pilot-high); background: var(--pilot-high-soft); }
.portal-risk-block.is-mid { border-left-color: var(--pilot-mid); background: var(--pilot-mid-soft); }
.portal-risk-block.is-low { border-left-color: var(--pilot-low); background: var(--pilot-low-soft); }
.portal-risk-block strong { color: var(--pilot-ink); font-size: var(--pilot-font-xl); line-height: 1.1; }
.portal-report-copy { min-width: 0; color: var(--pilot-ink-soft); font-size: var(--pilot-font-sm); line-height: 1.7; }
.portal-report-copy p { margin-top: var(--pilot-space-2); }
.portal-report-copy b { color: var(--pilot-ink); }
.portal-report-note {
  padding: var(--pilot-space-3);
  border-left: 3px solid var(--pilot-accent);
  background: var(--pilot-accent-soft);
  color: var(--pilot-ink-soft);
  font-size: var(--pilot-font-sm);
  line-height: 1.7;
}
.portal-hash { padding-top: var(--pilot-space-3); border-top: 1px solid var(--pilot-line); }
.portal-hash code { display: block; margin-top: var(--pilot-space-1); overflow-wrap: anywhere; color: var(--pilot-muted); font-family: "SFMono-Regular", Consolas, monospace; font-size: var(--pilot-font-xs); line-height: 1.5; }
.portal-cancel-summary { display: grid; gap: var(--pilot-space-1); padding: var(--pilot-space-3); border: 1px solid var(--pilot-line); border-radius: var(--pilot-radius-control); background: var(--pilot-surface-2); }
.portal-cancel-summary strong { color: var(--pilot-ink); }
.portal-cancel-summary span { color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
@media (max-width: 900px) {
  .portal-auth-grid { display: flex; flex-direction: column; gap: var(--pilot-space-4); }
  .portal-auth-card { order: -1; }
  .portal-overview { grid-template-columns: minmax(0, 1fr); }
  .portal-report-banner { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 650px) {
  .portal-masthead-inner { align-items: flex-start; min-height: 0; padding: var(--pilot-space-3); gap: var(--pilot-space-2); flex-wrap: wrap; }
  .portal-brand-copy span { display: none; }
  .portal-mast-actions { gap: var(--pilot-space-1); }
  .portal-staff-link { font-size: 11px; padding: 0 var(--pilot-space-1); }
  .portal-main { padding: var(--pilot-space-4) var(--pilot-space-3) var(--pilot-space-6); }
  .portal-form-grid { grid-template-columns: minmax(0, 1fr); }
  .portal-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .portal-summary-item:nth-child(2) { border-right: 0; }
  .portal-summary-item:nth-child(-n+2) { border-bottom: 1px solid var(--pilot-line); }
  .portal-summary-item { padding: var(--pilot-space-3); }
  .portal-summary-item strong { font-size: var(--pilot-font-md); }
  .portal-session-line { flex-direction: column; gap: var(--pilot-space-2); border-bottom: 0; }
  .portal-session-line :deep(.pilot-tabs) { width: 100%; border-bottom: 1px solid var(--pilot-line); }
  .portal-session-line > .pilot-chip { align-self: flex-start; }
  .portal-report-row { align-items: flex-start; flex-direction: column; gap: var(--pilot-space-3); }
  .portal-report-actions { width: 100%; }
  .portal-table { min-width: 720px; }
  .portal-mobile-hint { display: block; }
  .portal-feedback-list { grid-template-columns: minmax(0, 1fr); }
  .portal-report-detail { gap: var(--pilot-space-3); }
  .portal-risk-block { padding: var(--pilot-space-3); }
  .portal-risk-block strong { font-size: var(--pilot-font-lg); }
}
</style>

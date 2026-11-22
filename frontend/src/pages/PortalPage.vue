<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { api, saveBlob } from '../api/client'

const initialized = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const status = ref<any>({ authenticated: false, account: null, patient: null })
const authMode = ref<'login' | 'register' | 'query'>('login')
const tab = ref<'overview' | 'reports' | 'appointments' | 'feedback'>('overview')
const loginForm = reactive({ username: '', password: '' })
const registerForm = reactive({ username: '', display_name: '', password: '', phone_last4: '' })
const queryForm = reactive({ mrn: '', name: '', query_code: '' })
const bindForm = reactive({ mrn: '', name: '', query_code: '' })
const reports = ref<any[]>([])
const appointments = ref<any[]>([])
const feedback = ref<any[]>([])
const doctors = ref<any[]>([])
const slots = ref<any[]>([])
const booking = reactive({ slot_id: '', reason: '' })
const feedbackForm = reactive({ appointment_id: '', doctor_id: '', rating: 5, content: '' })
const detail = ref<any>(null)
const showReport = ref(false)
const showBooking = ref(false)
const showFeedback = ref(false)
const loadingData = ref(false)

const account = computed(() => status.value?.account)
const patient = computed(() => status.value?.patient)
const isQueryMode = computed(() => status.value?.mode === 'query_code')
const completedAppointments = computed(() => appointments.value.filter((a) => a.status === 'completed'))
const upcoming = computed(() => appointments.value.filter((a) => a.status === 'booked' || a.status === 'checked_in'))

function fmt(value?: string) {
  if (!value) return '—'
  return new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}
function riskClass(level?: string) {
  return level === '高' ? 'status-high' : level === '中' ? 'status-medium' : level === '低' ? 'status-low' : 'status-draft'
}
const appointmentStatus: Record<string, string> = {
  booked: '已预约', checked_in: '已签到', completed: '已完成', cancelled: '已取消', no_show: '爽约',
}

async function refreshStatus() {
  try {
    status.value = await api.portal.status()
    if (status.value.authenticated) await loadData()
  } catch { status.value = { authenticated: false } }
}
async function loadData() {
  loadingData.value = true
  try {
    const [r, a, f] = await Promise.all([
      api.portal.reports(), api.portal.appointments().catch(() => ({ appointments: [] })),
      api.portal.myFeedback().catch(() => ({ feedback: [] })),
    ])
    reports.value = r.reports ?? []
    appointments.value = a.appointments ?? []
    feedback.value = f.feedback ?? []
    if (status.value.authenticated && status.value.patient && !isQueryMode.value) {
      const [d, s] = await Promise.all([api.portal.doctors().catch(() => ({ doctors: [] })), api.portal.slots().catch(() => ({ slots: [] }))])
      doctors.value = d.doctors ?? []
      slots.value = s.slots ?? []
    }
  } catch (e: any) {
    // A query-code session can still read reports even if appointment calls fail.
    if (!reports.value.length) error.value = e?.message ?? '数据加载失败'
  } finally {
    loadingData.value = false
  }
}

async function doLogin() {
  error.value = ''
  if (!loginForm.username || !loginForm.password) { error.value = '请输入账号和密码'; return }
  busy.value = true
  try {
    await api.portal.login(loginForm.username, loginForm.password)
    await refreshStatus()
    tab.value = 'overview'
  } catch (e: any) { error.value = e?.message ?? '登录失败' }
  finally { busy.value = false }
}
async function doRegister() {
  error.value = ''
  if (!registerForm.username || !registerForm.display_name || registerForm.password.length < 12) {
    error.value = '账号、姓名必填，密码至少 12 个字符'; return
  }
  busy.value = true
  try {
    await api.portal.register({ ...registerForm })
    await api.portal.login(registerForm.username, registerForm.password)
    await refreshStatus()
    notice.value = '注册成功。请使用医院提供的查询码绑定本人档案。'
  } catch (e: any) { error.value = e?.message ?? '注册失败' }
  finally { busy.value = false }
}
async function doQuery() {
  error.value = ''
  if (!queryForm.mrn || !queryForm.name || !queryForm.query_code) { error.value = '请填写病历号、姓名和查询码'; return }
  busy.value = true
  try {
    const res = await api.portal.query({ ...queryForm })
    await refreshStatus()
    tab.value = 'reports'
    notice.value = `身份核验成功，可查看 ${res.report_count} 份已发布报告。本临时会话将在 ${Math.round((res.expires_in ?? 0) / 60)} 分钟后失效。`
  } catch (e: any) { error.value = e?.message ?? '核验失败' }
  finally { busy.value = false }
}
async function doBind() {
  error.value = ''
  if (!bindForm.mrn || !bindForm.name || !bindForm.query_code) { error.value = '请填写完整信息'; return }
  busy.value = true
  try {
    await api.portal.bind({ ...bindForm })
    await refreshStatus()
    notice.value = '档案绑定成功'
  } catch (e: any) { error.value = e?.message ?? '绑定失败' }
  finally { busy.value = false }
}
async function logout() {
  try { await api.portal.logout() } finally {
    status.value = { authenticated: false, account: null, patient: null }
    reports.value = []; appointments.value = []; feedback.value = []
    tab.value = 'overview'
  }
}

async function openReport(r: any) {
  error.value = ''
  try {
    detail.value = await api.portal.report(r.id)
    showReport.value = true
  } catch (e: any) { error.value = e?.message ?? '报告加载失败' }
}
async function download(r: any) {
  try {
    const blob = await api.portal.reportPdf(r.id)
    saveBlob(blob, `${r.report_no}.pdf`)
  } catch (e: any) { error.value = e?.message ?? '下载失败' }
}
async function cancelAppointment(a: any) {
  if (!confirm('确认取消本次预约？')) return
  try {
    await api.portal.cancelAppointment(a.id, '患者端取消')
    notice.value = '预约已取消'
    await loadData()
  } catch (e: any) { error.value = e?.message ?? '取消失败' }
}
async function submitBooking() {
  if (!booking.slot_id) { error.value = '请选择号源'; return }
  busy.value = true
  try {
    await api.portal.appointment({ slot_id: booking.slot_id, reason: booking.reason })
    showBooking.value = false
    booking.slot_id = ''; booking.reason = ''
    notice.value = '预约成功'
    await loadData()
  } catch (e: any) { error.value = e?.message ?? '预约失败' }
  finally { busy.value = false }
}
function openFeedback(a?: any) {
  const target = a ?? completedAppointments.value[0]
  Object.assign(feedbackForm, {
    appointment_id: target?.id ?? '', doctor_id: target?.doctor_id ?? '', rating: 5, content: '',
  })
  error.value = ''
  showFeedback.value = true
}
async function submitFeedback() {
  if (!feedbackForm.appointment_id && !feedbackForm.doctor_id) { error.value = '请选择已完成的就诊或医生'; return }
  busy.value = true
  try {
    await api.portal.feedback({ ...feedbackForm })
    showFeedback.value = false
    notice.value = '评价已提交，审核通过后公开显示。'
    await loadData()
  } catch (e: any) { error.value = e?.message ?? '评价提交失败' }
  finally { busy.value = false }
}

onMounted(async () => {
  await refreshStatus()
  initialized.value = true
})
</script>

<template>
  <div class="portal-shell">
    <header class="portal-top">
      <div class="portal-brand">
        <div class="logo">AKI</div>
        <div><div class="name">患者服务</div><div class="sub">急性肾损伤风险报告与随访</div></div>
      </div>
      <div class="flex items-center gap-8">
        <RouterLink to="/login" class="btn btn-sm btn-ghost">医护人员入口</RouterLink>
        <button v-if="status.authenticated" class="btn btn-sm btn-secondary" @click="logout">退出</button>
      </div>
    </header>

    <main class="portal-main">
      <div v-if="error" class="error">{{ error }}</div>
      <div v-if="notice" class="info-box">{{ notice }}</div>

      <div v-if="!initialized" class="card"><div class="empty-state">正在连接患者服务…</div></div>

      <!-- Auth -->
      <div v-else-if="!status.authenticated" class="portal-auth-wrap">
        <h1>患者身份核验</h1>
        <p>使用账号登录，或凭医院发放的查询码快速查看本人报告。</p>
        <div class="portal-tab-bar">
          <button :class="{active: authMode === 'login'}" @click="authMode = 'login'">账号登录</button>
          <button :class="{active: authMode === 'register'}" @click="authMode = 'register'">注册账号</button>
          <button :class="{active: authMode === 'query'}" @click="authMode = 'query'">查询码查询</button>
        </div>

        <div v-if="authMode === 'login'">
          <div class="form-group mb-12"><label>账号</label><input v-model="loginForm.username" class="form-control" autocomplete="username" /></div>
          <div class="form-group mb-12"><label>密码</label><input v-model="loginForm.password" class="form-control" type="password" autocomplete="current-password" @keyup.enter="doLogin" /></div>
          <button class="btn btn-primary" style="width:100%" :disabled="busy" @click="doLogin">{{ busy ? '登录中…' : '登录' }}</button>
        </div>

        <div v-else-if="authMode === 'register'">
          <div class="form-group mb-12"><label>登录账号</label><input v-model="registerForm.username" class="form-control" placeholder="4–64 位字母、数字或 ._-" /></div>
          <div class="form-group mb-12"><label>姓名</label><input v-model="registerForm.display_name" class="form-control" /></div>
          <div class="form-group mb-12"><label>密码（至少 12 个字符）</label><input v-model="registerForm.password" class="form-control" type="password" /></div>
          <div class="form-group mb-12"><label>手机号末四位（可选）</label><input v-model="registerForm.phone_last4" class="form-control" maxlength="4" /></div>
          <button class="btn btn-primary" style="width:100%" :disabled="busy" @click="doRegister">{{ busy ? '注册中…' : '注册并登录' }}</button>
          <div class="muted mt-8" style="font-size:10px">注册后仍需医院查询码绑定本人档案。</div>
        </div>

        <div v-else>
          <div class="form-group mb-12"><label>病历号</label><input v-model="queryForm.mrn" class="form-control" /></div>
          <div class="form-group mb-12"><label>姓名</label><input v-model="queryForm.name" class="form-control" /></div>
          <div class="form-group mb-12"><label>查询码</label><input v-model="queryForm.query_code" class="form-control font-mono" maxlength="8" style="letter-spacing:2px;text-transform:uppercase" /></div>
          <button class="btn btn-primary" style="width:100%" :disabled="busy" @click="doQuery">{{ busy ? '核验中…' : '核验并查看报告' }}</button>
          <div class="muted mt-8" style="font-size:10px">查询码由医院工作人员生成，仅限本人使用，过期需重新申领。</div>
        </div>
      </div>

      <!-- Logged in but unbound -->
      <div v-else-if="!status.patient" class="portal-auth-wrap">
        <h1>绑定本人档案</h1>
        <p>账号尚未关联患者档案。请向医院索取查询码后绑定。</p>
        <div class="form-group mb-12"><label>病历号</label><input v-model="bindForm.mrn" class="form-control" /></div>
        <div class="form-group mb-12"><label>姓名</label><input v-model="bindForm.name" class="form-control" /></div>
        <div class="form-group mb-12"><label>查询码</label><input v-model="bindForm.query_code" class="form-control font-mono" maxlength="8" /></div>
        <button class="btn btn-primary" style="width:100%" :disabled="busy" @click="doBind">{{ busy ? '绑定中…' : '绑定档案' }}</button>
      </div>

      <!-- Patient home -->
      <div v-else>
        <div class="summary-strip">
          <div class="summary-item"><div class="label">患者</div><div class="value" style="font-size:18px">{{ patient.name }}</div><div class="hint font-mono">{{ patient.mrn }}</div></div>
          <div class="summary-item"><div class="label">正式报告</div><div class="value">{{ reports.length }}</div><div class="hint">已发布可查看</div></div>
          <div class="summary-item"><div class="label">待就诊</div><div class="value">{{ upcoming.length }}</div><div class="hint">已预约 / 已签到</div></div>
          <div class="summary-item"><div class="label">我的评价</div><div class="value">{{ feedback.length }}</div><div class="hint">含待审核</div></div>
        </div>

        <div class="flex items-center justify-between mb-12" style="gap:12px;flex-wrap:wrap">
          <div class="portal-nav">
            <button :class="{active: tab === 'overview'}" @click="tab = 'overview'">首页</button>
            <button :class="{active: tab === 'reports'}" @click="tab = 'reports'">我的报告</button>
            <button v-if="!isQueryMode" :class="{active: tab === 'appointments'}" @click="tab = 'appointments'">预约就诊</button>
            <button v-if="!isQueryMode" :class="{active: tab === 'feedback'}" @click="tab = 'feedback'">评价</button>
          </div>
          <span class="status status-info">{{ isQueryMode ? '查询码临时会话' : '已实名绑定' }}</span>
        </div>

        <div v-if="loadingData" class="card"><div class="empty-state">正在加载患者数据…</div></div>

        <div v-else-if="tab === 'overview'">
          <div class="portal-section-title">最近报告</div>
          <div v-if="!reports.length" class="empty-state card"><strong>暂无已发布报告</strong>医生完成复核并发布后，报告会出现在这里。</div>
          <div v-else class="portal-grid">
            <div v-for="r in reports.slice(0,3)" :key="r.id" class="portal-card">
              <div class="flex justify-between items-center"><h3>{{ r.report_no }}</h3><span class="status" :class="riskClass(r.risk_level)">{{ r.risk_level }}</span></div>
              <div class="line">第 {{ r.version }} 版 · {{ fmt(r.published_at) }}</div>
              <div class="line">就诊：{{ r.encounter?.case_ref }}</div>
              <div class="actions"><button class="btn btn-sm btn-primary" @click="openReport(r)">查看</button><button class="btn btn-sm btn-secondary" @click="download(r)">PDF</button></div>
            </div>
          </div>

          <div v-if="!isQueryMode" class="portal-section-title">下一次就诊</div>
          <div v-if="!upcoming.length" class="muted">暂无待就诊预约。</div>
          <div v-for="a in upcoming.slice(0,1)" :key="a.id" class="portal-card">
            <h3>{{ fmt(a.scheduled_at) }} · {{ a.doctor_name }}</h3>
            <div class="line">{{ a.appointment_type }} · {{ appointmentStatus[a.status] }}</div>
            <div class="actions"><button class="btn btn-sm btn-danger" @click="cancelAppointment(a)">取消预约</button></div>
          </div>
        </div>

        <div v-else-if="tab === 'reports'">
          <div v-if="!reports.length" class="empty-state card"><strong>暂无报告</strong></div>
          <div v-else class="table-wrap card">
            <table class="data-table">
              <thead><tr><th>报告编号</th><th>风险</th><th>版本</th><th>就诊</th><th>发布时间</th><th></th></tr></thead>
              <tbody>
                <tr v-for="r in reports" :key="r.id">
                  <td class="primary-cell font-mono">{{ r.report_no }}</td>
                  <td><span class="status" :class="riskClass(r.risk_level)">{{ r.risk_level || '人工审核' }}</span></td>
                  <td>v{{ r.version }}</td>
                  <td>{{ r.encounter?.case_ref }}</td>
                  <td>{{ fmt(r.published_at) }}</td>
                  <td class="text-right"><button class="btn btn-sm btn-secondary" @click="openReport(r)">查看</button> <button class="btn btn-sm btn-primary" @click="download(r)">PDF</button></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div v-else-if="tab === 'appointments'">
          <div class="flex justify-between items-center mb-12"><div class="portal-section-title" style="margin:0">我的预约</div><button class="btn btn-primary" @click="showBooking = true">＋ 预约就诊</button></div>
          <div v-if="!appointments.length" class="empty-state card"><strong>暂无预约</strong></div>
          <div v-else class="table-wrap card">
            <table class="data-table">
              <thead><tr><th>就诊时间</th><th>医生</th><th>类型</th><th>状态</th><th>原因</th><th></th></tr></thead>
              <tbody>
                <tr v-for="a in appointments" :key="a.id">
                  <td class="primary-cell">{{ fmt(a.scheduled_at) }}</td>
                  <td>{{ a.doctor_name }}</td><td>{{ a.appointment_type }}</td>
                  <td><span class="status" :class="a.status === 'completed' ? 'status-active' : a.status === 'booked' ? 'status-info' : 'status-draft'">{{ appointmentStatus[a.status] }}</span></td>
                  <td class="wrap">{{ a.reason || '—' }}</td>
                  <td class="text-right" style="white-space:nowrap">
                    <button v-if="a.status === 'booked' || a.status === 'checked_in'" class="btn btn-sm btn-danger" @click="cancelAppointment(a)">取消</button>
                    <button v-if="a.status === 'completed'" class="btn btn-sm btn-secondary" @click="openFeedback(a)">评价</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div v-else-if="tab === 'feedback'">
          <div class="flex justify-between items-center mb-12"><div class="portal-section-title" style="margin:0">我的评价</div><button class="btn btn-primary" :disabled="!completedAppointments.length" @click="openFeedback()">＋ 提交评价</button></div>
          <div class="warning-box" v-if="!completedAppointments.length">只有已完成的就诊可以评价。</div>
          <div v-if="!feedback.length" class="empty-state card"><strong>还没有评价</strong></div>
          <div v-else class="portal-grid">
            <div v-for="f in feedback" :key="f.id" class="portal-card">
              <div class="flex justify-between"><h3>{{ f.doctor_name || '医生' }}</h3><span style="color:var(--yellow)">{{ '★'.repeat(f.rating) }}</span></div>
              <div class="line">{{ f.content || '未填写文字评价' }}</div>
              <div class="line">{{ fmt(f.created_at) }} · {{ f.status === 'public' ? '已公开' : f.status === 'pending' ? '待审核' : '已隐藏' }}</div>
            </div>
          </div>
        </div>
      </div>
    </main>

    <!-- Report modal -->
    <div v-if="showReport" class="modal-mask" @click.self="showReport = false">
      <div class="modal-panel wide">
        <div class="modal-head"><div><div class="modal-title">{{ detail?.report_no }}</div><div class="modal-sub">{{ detail?.patient_name }} · 第 {{ detail?.version }} 版 · {{ fmt(detail?.published_at) }}</div></div><button class="modal-close" @click="showReport = false">×</button></div>
        <div class="modal-body" v-if="detail">
          <div class="assessment-grid">
            <div class="prob-card" :class="detail.risk_level === '高' ? 'high' : detail.risk_level === '中' ? 'medium' : 'low'">
              <div class="prob-label">AKI 风险</div>
              <div class="prob-value">{{ detail.snapshot?.prediction?.result?.probability != null ? `${(detail.snapshot.prediction.result.probability * 100).toFixed(1)}%` : '人工审核' }}</div>
              <div class="prob-risk">{{ detail.risk_level || '人工审核' }}</div>
            </div>
            <div>
              <div class="document-line" style="font-size:11px;line-height:1.8">
                <strong style="color:var(--text-bright)">诊断：</strong>{{ detail.snapshot?.encounter?.diagnosis || '—' }}<br />
                <strong style="color:var(--text-bright)">医嘱：</strong>{{ detail.snapshot?.encounter?.orders || '—' }}<br />
                <strong style="color:var(--text-bright)">复核：</strong>{{ detail.snapshot?.review?.reviewer_name || '—' }} · {{ detail.snapshot?.review?.reason || '—' }}
              </div>
            </div>
          </div>
          <div class="side-card mt-12"><div class="side-title">报告完整性</div><div class="hash-text">{{ detail.sha256 }}</div></div>
        </div>
        <div class="modal-foot"><button class="btn btn-secondary" @click="showReport = false">关闭</button><button class="btn btn-primary" @click="download(detail)">下载 PDF</button></div>
      </div>
    </div>

    <!-- Booking modal -->
    <div v-if="showBooking" class="modal-mask" @click.self="showBooking = false">
      <div class="modal-panel" style="max-width:560px">
        <div class="modal-head"><div><div class="modal-title">预约就诊</div><div class="modal-sub">选择医生号源；就诊完成后可提交评价。</div></div><button class="modal-close" @click="showBooking = false">×</button></div>
        <div class="modal-body">
          <div class="form-group mb-12"><label>可用号源</label>
            <select v-model="booking.slot_id" class="form-control">
              <option value="">选择号源…</option>
              <option v-for="s in slots" :key="s.id" :value="s.id">{{ fmt(s.starts_at) }} · {{ s.doctor_name }} · {{ s.appointment_type }}（余 {{ s.capacity - s.booked }}）</option>
            </select>
          </div>
          <div class="form-group"><label>就诊原因</label><textarea v-model="booking.reason" class="form-control" rows="2" placeholder="如 AKI 风险随访" /></div>
        </div>
        <div class="modal-foot"><button class="btn btn-secondary" @click="showBooking = false">取消</button><button class="btn btn-primary" :disabled="busy" @click="submitBooking">确认预约</button></div>
      </div>
    </div>

    <!-- Feedback modal -->
    <div v-if="showFeedback" class="modal-mask" @click.self="showFeedback = false">
      <div class="modal-panel" style="max-width:560px">
        <div class="modal-head"><div><div class="modal-title">就诊评价</div><div class="modal-sub">评价经医院审核后公开，不会影响后续诊疗。</div></div><button class="modal-close" @click="showFeedback = false">×</button></div>
        <div class="modal-body">
          <div class="form-group mb-12"><label>关联已完成就诊</label>
            <select v-model="feedbackForm.appointment_id" class="form-control">
              <option value="">选择就诊…</option>
              <option v-for="a in completedAppointments" :key="a.id" :value="a.id">{{ fmt(a.scheduled_at) }} · {{ a.doctor_name }}</option>
            </select>
          </div>
          <div class="form-group mb-12"><label>评分</label><select v-model="feedbackForm.rating" class="form-control"><option :value="5">★★★★★ 非常满意</option><option :value="4">★★★★ 满意</option><option :value="3">★★★ 一般</option><option :value="2">★★ 不满意</option><option :value="1">★ 很不满意</option></select></div>
          <div class="form-group"><label>评价内容</label><textarea v-model="feedbackForm.content" class="form-control" rows="3" placeholder="描述您的就医体验（可选）" /></div>
        </div>
        <div class="modal-foot"><button class="btn btn-secondary" @click="showFeedback = false">取消</button><button class="btn btn-primary" :disabled="busy" @click="submitFeedback">提交评价</button></div>
      </div>
    </div>
  </div>
</template>

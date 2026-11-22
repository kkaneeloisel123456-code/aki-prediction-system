<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '../api/client'
import { useAuth } from '../composables/useAuth'

const auth = useAuth()
const tab = ref<'slots' | 'appointments' | 'feedback'>('appointments')
const loading = ref(true)
const error = ref('')
const notice = ref('')
const slots = ref<any[]>([])
const appointments = ref<any[]>([])
const feedback = ref<any[]>([])
const doctors = ref<any[]>([])
const patients = ref<any[]>([])
const saving = ref(false)

const isAdmin = computed(() => auth.user.value?.role === 'admin')
const aptFilter = ref('')
const fbFilter = ref('pending')

const slotForm = reactive({
  doctor_id: '', starts_at: '', appointment_type: '门诊', capacity: 5,
})
const aptForm = reactive({ patient_id: '', slot_id: '', reason: '' })
const showAppointment = ref(false)

const appointmentStatus: Record<string, string> = {
  booked: '已预约', checked_in: '已签到', completed: '已完成', cancelled: '已取消', no_show: '爽约',
}
function fmt(value?: string) {
  if (!value) return '—'
  return new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}
function localFuture() {
  const d = new Date(Date.now() + 24 * 3600_000)
  const off = d.getTimezoneOffset()
  return new Date(d.getTime() - off * 60_000).toISOString().slice(0, 16)
}
function slotStatus(s: any) {
  if (!s.active) return ['已停用', 'status-inactive']
  if (s.booked >= s.capacity) return ['已约满', 'status-medium']
  return ['可预约', 'status-active']
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const requests: Promise<any>[] = [
      api.slots(), api.appointments(aptFilter.value ? `status=${aptFilter.value}` : ''),
      api.feedback(fbFilter.value ? `status=${fbFilter.value}` : ''),
    ]
    if (isAdmin.value) requests.push(api.doctors(), api.workstation())
    const [s, a, f, d, w] = await Promise.all(requests)
    slots.value = s.slots ?? []
    appointments.value = a.appointments ?? []
    feedback.value = f.feedback ?? []
    doctors.value = d?.doctors ?? []
    patients.value = w?.patients ?? []
    if (isAdmin.value && doctors.value.length && !slotForm.doctor_id) slotForm.doctor_id = doctors.value[0].id
  } catch (e: any) {
    error.value = e?.message ?? '预约数据加载失败'
  } finally {
    loading.value = false
  }
}

async function loadFeedback() {
  try { feedback.value = (await api.feedback(fbFilter.value ? `status=${fbFilter.value}` : '')).feedback ?? [] }
  catch (e: any) { error.value = e?.message ?? '评价加载失败' }
}
async function loadAppointments() {
  try { appointments.value = (await api.appointments(aptFilter.value ? `status=${aptFilter.value}` : '')).appointments ?? [] }
  catch (e: any) { error.value = e?.message ?? '预约加载失败' }
}

async function createSlot() {
  error.value = ''
  if (!slotForm.starts_at) { error.value = '请选择出诊时间'; return }
  saving.value = true
  try {
    await api.createSlot({
      doctor_id: slotForm.doctor_id || undefined,
      starts_at: new Date(slotForm.starts_at).toISOString(),
      appointment_type: slotForm.appointment_type,
      capacity: Number(slotForm.capacity),
    })
    notice.value = '号源已创建'
    slotForm.starts_at = ''
    await load()
  } catch (e: any) { error.value = e?.message ?? '号源创建失败' }
  finally { saving.value = false }
}
async function toggleSlot(s: any) {
  try {
    await api.updateSlot(s.id, { active: !Boolean(s.active) })
    await load()
  } catch (e: any) { error.value = e?.message ?? '号源更新失败' }
}
async function changeAppointment(a: any, status: string) {
  if (!confirm(`确认将预约状态变更为“${appointmentStatus[status]}”？`)) return
  try {
    await api.updateAppointment(a.id, status)
    notice.value = '预约状态已更新'
    await loadAppointments()
  } catch (e: any) { error.value = e?.message ?? '状态更新失败' }
}
async function moderate(f: any, status: string) {
  try {
    await api.moderateFeedback(f.id, status)
    await loadFeedback()
  } catch (e: any) { error.value = e?.message ?? '评价审核失败' }
}
function openAppointment() {
  Object.assign(aptForm, { patient_id: '', slot_id: '', reason: '' })
  error.value = ''
  showAppointment.value = true
}
async function submitAppointment() {
  if (!aptForm.patient_id || !aptForm.slot_id) { error.value = '请选择患者和号源'; return }
  saving.value = true
  try {
    await api.createAppointment({ ...aptForm })
    showAppointment.value = false
    notice.value = '现场预约已建立'
    await load()
  } catch (e: any) { error.value = e?.message ?? '预约创建失败' }
  finally { saving.value = false }
}

onMounted(() => { slotForm.starts_at = localFuture(); load() })
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h1 class="page-title">预约与反馈</h1>
        <div class="page-subtitle">号源排班、现场预约、待诊流转与患者评价审核</div>
      </div>
      <div class="page-actions">
        <button v-if="tab === 'appointments'" class="btn btn-primary" @click="openAppointment">＋ 现场预约</button>
        <button class="btn btn-secondary" :disabled="loading" @click="load">刷新</button>
      </div>
    </div>
    <div v-if="error" class="error">{{ error }}</div>
    <div v-if="notice" class="info-box">{{ notice }}</div>

    <div class="tabs">
      <button class="tab" :class="{active: tab === 'appointments'}" @click="tab = 'appointments'; loadAppointments()">预约与待诊</button>
      <button class="tab" :class="{active: tab === 'slots'}" @click="tab = 'slots'">号源管理</button>
      <button class="tab" :class="{active: tab === 'feedback'}" @click="tab = 'feedback'; loadFeedback()">评价审核</button>
    </div>

    <!-- Appointments -->
    <div v-if="tab === 'appointments'" class="card">
      <div class="toolbar">
        <select v-model="aptFilter" class="form-control" style="min-width:140px" @change="loadAppointments">
          <option value="">全部预约</option>
          <option value="booked">已预约</option>
          <option value="checked_in">已签到</option>
          <option value="completed">已完成</option>
          <option value="cancelled">已取消</option>
          <option value="no_show">爽约</option>
        </select>
        <span class="toolbar-spacer" />
        <span class="muted" style="font-size:10px">共 {{ appointments.length }} 条</span>
      </div>
      <div v-if="loading" class="empty-state">正在加载预约…</div>
      <div v-else-if="!appointments.length" class="empty-state"><strong>暂无预约</strong>患者可通过患者端预约，或由工作人员现场建立预约。</div>
      <div v-else class="table-wrap">
        <table class="data-table">
          <thead><tr><th>就诊时间</th><th>患者</th><th>医生</th><th>类型</th><th>原因</th><th>状态</th><th></th></tr></thead>
          <tbody>
            <tr v-for="a in appointments" :key="a.id">
              <td class="primary-cell">{{ fmt(a.scheduled_at) }}</td>
              <td>{{ a.patient_name }}<div class="sub-cell font-mono">{{ a.patient_id }}</div></td>
              <td>{{ a.doctor_name }}</td>
              <td>{{ a.appointment_type }}</td>
              <td class="wrap">{{ a.reason || '—' }}</td>
              <td><span class="status" :class="a.status === 'completed' ? 'status-active' : a.status === 'booked' ? 'status-info' : a.status === 'checked_in' ? 'status-reviewed' : a.status === 'no_show' ? 'status-high' : 'status-draft'">{{ appointmentStatus[a.status] ?? a.status }}</span></td>
              <td class="text-right" style="white-space:nowrap">
                <button v-if="a.status === 'booked'" class="btn btn-sm btn-secondary" @click="changeAppointment(a, 'checked_in')">签到</button>
                <button v-if="a.status === 'checked_in'" class="btn btn-sm btn-success" @click="changeAppointment(a, 'completed')">完成</button>
                <button v-if="a.status === 'booked' || a.status === 'checked_in'" class="btn btn-sm btn-danger" @click="changeAppointment(a, 'no_show')">爽约</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Slots -->
    <div v-if="tab === 'slots'" class="grid-2-1">
      <div class="card">
        <div class="card-header"><span class="card-title">号源列表</span></div>
        <div v-if="!slots.length" class="empty-state"><strong>尚未创建号源</strong>在右侧为医生设置出诊时间。</div>
        <div v-else class="table-wrap">
          <table class="data-table">
            <thead><tr><th>出诊时间</th><th>医生</th><th>类型</th><th>预约</th><th>状态</th><th></th></tr></thead>
            <tbody>
              <tr v-for="s in slots" :key="s.id">
                <td class="primary-cell">{{ fmt(s.starts_at) }}</td>
                <td>{{ s.doctor_name }}</td>
                <td>{{ s.appointment_type }}</td>
                <td>{{ s.booked }} / {{ s.capacity }}</td>
                <td><span class="status" :class="slotStatus(s)[1]">{{ slotStatus(s)[0] }}</span></td>
                <td class="text-right"><button class="btn btn-sm btn-secondary" @click="toggleSlot(s)">{{ s.active ? '停用' : '启用' }}</button></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <div class="card">
        <div class="card-header"><span class="card-title">新建号源</span></div>
        <div class="card-body">
          <div class="form-group mb-12" v-if="isAdmin">
            <label>出诊医生</label>
            <select v-model="slotForm.doctor_id" class="form-control">
              <option v-for="d in doctors" :key="d.id" :value="d.id">{{ d.display_name }}</option>
            </select>
          </div>
          <div class="form-group mb-12"><label>出诊时间</label><input v-model="slotForm.starts_at" class="form-control" type="datetime-local" /></div>
          <div class="form-group mb-12"><label>类型</label><select v-model="slotForm.appointment_type" class="form-control"><option>门诊</option><option>检查</option></select></div>
          <div class="form-group mb-12"><label>容量</label><input v-model="slotForm.capacity" class="form-control" type="number" min="1" max="100" /></div>
          <button class="btn btn-primary" :disabled="saving" @click="createSlot">创建号源</button>
        </div>
      </div>
    </div>

    <!-- Feedback -->
    <div v-if="tab === 'feedback'" class="card">
      <div class="toolbar">
        <select v-model="fbFilter" class="form-control" style="min-width:130px" @change="loadFeedback">
          <option value="pending">待审核</option>
          <option value="public">已公开</option>
          <option value="hidden">已隐藏</option>
          <option value="">全部</option>
        </select>
        <span class="toolbar-spacer" /><span class="muted" style="font-size:10px">共 {{ feedback.length }} 条</span>
      </div>
      <div v-if="!feedback.length" class="empty-state"><strong>暂无评价</strong>患者只能在就诊完成后提交评价。</div>
      <div v-else class="table-wrap">
        <table class="data-table">
          <thead><tr><th>患者</th><th>医生</th><th>评分</th><th>内容</th><th>状态</th><th>提交时间</th><th></th></tr></thead>
          <tbody>
            <tr v-for="f in feedback" :key="f.id">
              <td>{{ f.patient_name }}</td><td>{{ f.doctor_name || '—' }}</td>
              <td><span style="color:var(--yellow)">{{ '★'.repeat(f.rating || 0) }}</span></td>
              <td class="wrap">{{ f.content || '—' }}</td>
              <td><span class="status" :class="f.status === 'public' ? 'status-active' : f.status === 'pending' ? 'status-pending' : 'status-draft'">{{ f.status === 'public' ? '已公开' : f.status === 'pending' ? '待审核' : '已隐藏' }}</span></td>
              <td>{{ fmt(f.created_at) }}</td>
              <td class="text-right" style="white-space:nowrap">
                <button v-if="f.status !== 'public'" class="btn btn-sm btn-success" @click="moderate(f, 'public')">公开</button>
                <button v-if="f.status !== 'hidden'" class="btn btn-sm btn-secondary" @click="moderate(f, 'hidden')">隐藏</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-if="showAppointment" class="modal-mask" @click.self="showAppointment = false">
      <div class="modal-panel" style="max-width:560px">
        <div class="modal-head"><div><div class="modal-title">现场预约</div><div class="modal-sub">为已建档患者分配可用号源。</div></div><button class="modal-close" @click="showAppointment = false">×</button></div>
        <div class="modal-body">
          <div class="form-group mb-12">
            <label>患者</label>
            <select v-model="aptForm.patient_id" class="form-control">
              <option value="">选择患者…</option>
              <option v-for="p in patients" :key="p.id" :value="p.id">{{ p.name }}（{{ p.mrn }}）</option>
            </select>
          </div>
          <div class="form-group mb-12">
            <label>号源</label>
            <select v-model="aptForm.slot_id" class="form-control">
              <option value="">选择可用号源…</option>
              <option v-for="s in slots.filter(x => x.active && x.booked < x.capacity && new Date(x.starts_at) > new Date())" :key="s.id" :value="s.id">
                {{ fmt(s.starts_at) }} · {{ s.doctor_name }} · {{ s.appointment_type }}
              </option>
            </select>
          </div>
          <div class="form-group"><label>预约原因</label><textarea v-model="aptForm.reason" class="form-control" rows="2" /></div>
        </div>
        <div class="modal-foot"><button class="btn btn-secondary" @click="showAppointment = false">取消</button><button class="btn btn-primary" :disabled="saving" @click="submitAppointment">建立预约</button></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '../api/client'
import { useAuth } from '../composables/useAuth'

type Tab = 'appointments' | 'slots' | 'feedback'
type Tone = 'neutral' | 'low' | 'mid' | 'high' | 'accent'

const auth = useAuth()
const tab = ref<Tab>('appointments')
const loading = ref(true)
const error = ref('')
const notice = ref('')
const slots = ref<any[]>([])
const appointments = ref<any[]>([])
const feedback = ref<any[]>([])
const doctors = ref<any[]>([])
const patients = ref<any[]>([])
const saving = ref(false)
const slotBusy = ref('')
const showSlotConfirm = ref(false)
const pendingSlot = ref<any>(null)

const aptFilter = ref('')
const fbFilter = ref('pending')
const isAdmin = computed(() => auth.user.value?.role === 'admin')

const slotForm = reactive({
  doctor_id: '', starts_at: '', appointment_type: '门诊', capacity: 5,
})
const aptForm = reactive({ patient_id: '', slot_id: '', reason: '' })
const showAppointment = ref(false)
const dialogError = ref('')

const showStatusConfirm = ref(false)
const pendingStatus = ref<{ row: any, status: string } | null>(null)
const statusError = ref('')
const statusBusy = ref(false)

const appointmentStatus: Record<string, string> = {
  booked: '已预约', checked_in: '已签到', completed: '已完成', cancelled: '已取消', no_show: '爽约',
}
const appointmentTones: Record<string, Tone> = {
  booked: 'accent', checked_in: 'mid', completed: 'low', cancelled: 'neutral', no_show: 'high',
}
const feedbackStatus: Record<string, string> = { pending: '待审核', public: '已公开', hidden: '已隐藏' }
const feedbackTones: Record<string, Tone> = { pending: 'mid', public: 'low', hidden: 'neutral' }

const availableSlots = computed(() => slots.value.filter((s) => {
  return s.active && Number(s.booked) < Number(s.capacity) && new Date(s.starts_at) > new Date()
}))

const pageDescription = computed(() => {
  if (loading.value) return '正在读取预约与复查数据…'
  const feedbackLabel = fbFilter.value === 'pending' ? '条待审评价' : '条评价'
  return `号源排班、现场预约、待诊流转与患者评价审核 · ${appointments.value.length} 条预约 · ${feedback.value.length} ${feedbackLabel}`
})
const appointmentSubtitle = computed(() => loading.value
  ? '读取预约记录…'
  : `${appointments.value.length} 条记录 · ${aptFilter.value ? '已筛选状态' : '全部状态'}`)
const slotSubtitle = computed(() => loading.value
  ? '读取号源…'
  : `${slots.value.length} 个号源 · ${availableSlots.value.length} 个可预约`)
const feedbackSubtitle = computed(() => loading.value
  ? '读取评价…'
  : `${feedback.value.length} 条评价 · ${feedbackStatus[fbFilter.value] || '全部状态'}`)
const pendingStatusLabel = computed(() => pendingStatus.value
  ? appointmentStatus[pendingStatus.value.status] ?? pendingStatus.value.status
  : '')
const statusConfirmTitle = computed(() => pendingStatus.value
  ? `确认将预约变更为“${pendingStatusLabel.value}”？`
  : '变更预约状态')
const statusConfirmCopy = computed(() => {
  if (!pendingStatus.value) return ''
  const { row, status } = pendingStatus.value
  const patient = row.patient_name || '该患者'
  if (status === 'checked_in') return `确认 ${patient} 已到院签到？签到后可在完成就诊时继续流转。`
  if (status === 'completed') return `确认 ${patient} 的本次就诊已完成？完成后将进入后续评价与复查环节。`
  if (status === 'no_show') return `确认将 ${patient} 标记为爽约？该操作会保留在预约记录与审计日志中。`
  return `确认将 ${patient} 的预约变更为“${pendingStatusLabel.value}”？`
})

function fmt(value?: string) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}
function localFuture() {
  const d = new Date(Date.now() + 24 * 3600_000)
  const off = d.getTimezoneOffset()
  return new Date(d.getTime() - off * 60_000).toISOString().slice(0, 16)
}
function slotLabel(s: any) {
  if (!s.active) return '已停用'
  if (Number(s.booked) >= Number(s.capacity)) return '已约满'
  return '可预约'
}
function slotTone(s: any): Tone {
  if (!s.active) return 'high'
  if (Number(s.booked) >= Number(s.capacity)) return 'mid'
  return 'low'
}
function ratingStars(value?: number) {
  const count = Math.max(0, Math.min(5, Number(value) || 0))
  return count ? '★'.repeat(count) : '未评分'
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [s, a, f, w] = await Promise.all([
      api.slots(),
      api.appointments(aptFilter.value ? `status=${aptFilter.value}` : ''),
      api.feedback(fbFilter.value ? `status=${fbFilter.value}` : ''),
      api.workstation(),
    ])
    const now = Date.now()
    slots.value = (s.slots ?? []).slice().sort((left: any, right: any) => {
      const leftPast = new Date(left.starts_at).getTime() < now
      const rightPast = new Date(right.starts_at).getTime() < now
      if (leftPast !== rightPast) return leftPast ? 1 : -1
      return leftPast
        ? new Date(right.starts_at).getTime() - new Date(left.starts_at).getTime()
        : new Date(left.starts_at).getTime() - new Date(right.starts_at).getTime()
    })
    appointments.value = a.appointments ?? []
    feedback.value = f.feedback ?? []
    patients.value = w?.patients ?? []
    if (isAdmin.value) {
      doctors.value = (await api.doctors()).doctors ?? []
      if (doctors.value.length && !slotForm.doctor_id) slotForm.doctor_id = doctors.value[0].id
    }
  } catch (e: any) {
    error.value = e?.message ?? '预约数据加载失败'
  } finally {
    loading.value = false
  }
}
async function loadFeedback() {
  try {
    feedback.value = (await api.feedback(fbFilter.value ? `status=${fbFilter.value}` : '')).feedback ?? []
  } catch (e: any) {
    error.value = e?.message ?? '评价加载失败'
  }
}
async function loadAppointments() {
  try {
    appointments.value = (await api.appointments(aptFilter.value ? `status=${aptFilter.value}` : '')).appointments ?? []
  } catch (e: any) {
    error.value = e?.message ?? '预约加载失败'
  }
}

async function createSlot() {
  error.value = ''
  notice.value = ''
  if (!slotForm.starts_at) {
    error.value = '请选择出诊时间'
    return
  }
  saving.value = true
  try {
    await api.createSlot({
      doctor_id: slotForm.doctor_id || undefined,
      starts_at: new Date(slotForm.starts_at).toISOString(),
      appointment_type: slotForm.appointment_type,
      capacity: Number(slotForm.capacity),
    })
    notice.value = '号源已创建'
    slotForm.starts_at = localFuture()
    await load()
  } catch (e: any) {
    error.value = e?.message ?? '号源创建失败'
  } finally {
    saving.value = false
  }
}
async function applySlotActive(s: any) {
  slotBusy.value = s.id
  error.value = ''
  try {
    await api.updateSlot(s.id, { active: !Boolean(s.active) })
    notice.value = s.active ? '号源已停用' : '号源已启用'
    await load()
    return true
  } catch (e: any) {
    error.value = e?.message ?? '号源更新失败'
    return false
  } finally {
    slotBusy.value = ''
  }
}
function toggleSlot(s: any) {
  if (s.active && Number(s.booked) > 0) {
    pendingSlot.value = s
    showSlotConfirm.value = true
    return
  }
  void applySlotActive(s)
}
async function confirmDisableSlot() {
  if (!pendingSlot.value) return
  const ok = await applySlotActive(pendingSlot.value)
  if (ok) {
    showSlotConfirm.value = false
    pendingSlot.value = null
  }
}

function askStatus(a: any, status: string) {
  pendingStatus.value = { row: a, status }
  statusError.value = ''
  showStatusConfirm.value = true
}
async function confirmStatus() {
  if (!pendingStatus.value) return
  statusBusy.value = true
  statusError.value = ''
  try {
    await api.updateAppointment(pendingStatus.value.row.id, pendingStatus.value.status)
    showStatusConfirm.value = false
    notice.value = '预约状态已更新'
    await loadAppointments()
  } catch (e: any) {
    statusError.value = e?.message ?? '状态更新失败'
  } finally {
    statusBusy.value = false
  }
}

function openAppointment() {
  Object.assign(aptForm, { patient_id: '', slot_id: '', reason: '' })
  dialogError.value = ''
  showAppointment.value = true
}
async function submitAppointment() {
  dialogError.value = ''
  if (!aptForm.patient_id || !aptForm.slot_id) {
    dialogError.value = '请选择患者和可用号源'
    return
  }
  saving.value = true
  try {
    await api.createAppointment({ ...aptForm })
    showAppointment.value = false
    notice.value = '现场预约已建立'
    await load()
  } catch (e: any) {
    dialogError.value = e?.message ?? '预约创建失败'
  } finally {
    saving.value = false
  }
}
async function moderate(f: any, status: string) {
  error.value = ''
  try {
    await api.moderateFeedback(f.id, status)
    notice.value = status === 'public' ? '评价已公开' : '评价已隐藏'
    await loadFeedback()
  } catch (e: any) {
    error.value = e?.message ?? '评价审核失败'
  }
}

onMounted(() => {
  slotForm.starts_at = localFuture()
  load()
})
</script>

<template>
  <div class="pilot-page">
    <div class="pilot-page-inner schedule-page">
      <PageHeader
        kicker="复查 / 预约"
        title="复查安排"
        :description="pageDescription"
      >
        <template #actions>
          <button
            v-if="tab === 'appointments'"
            class="pilot-btn pilot-btn-primary"
            type="button"
            @click="openAppointment"
          >＋ 现场预约</button>
          <button class="pilot-btn" type="button" :disabled="loading" @click="load">刷新</button>
        </template>
      </PageHeader>

      <PilotTabs
        v-model="tab"
        label="预约与复查分区"
        :tabs="[
          { value: 'appointments', label: '预约与待诊', count: appointments.length },
          { value: 'slots', label: '号源管理', count: slots.length },
          { value: 'feedback', label: '评价审核', count: feedback.length },
        ]"
      />

      <div v-if="error" class="pilot-error" role="alert">{{ error }}</div>
      <div v-if="notice" class="pilot-notice" role="status">{{ notice }}</div>

      <SectionPanel
        v-if="tab === 'appointments'"
        title="预约与待诊"
        :subtitle="appointmentSubtitle"
        flush
      >
        <div class="schedule-toolbar">
          <label class="schedule-filter">
            <span>状态</span>
            <select v-model="aptFilter" class="pilot-select" @change="loadAppointments">
              <option value="">全部预约</option>
              <option value="booked">已预约</option>
              <option value="checked_in">已签到</option>
              <option value="completed">已完成</option>
              <option value="cancelled">已取消</option>
              <option value="no_show">爽约</option>
            </select>
          </label>
          <span class="pilot-count">共 {{ appointments.length }} 条 · 按就诊时间排序</span>
        </div>

        <div v-if="loading" class="schedule-loading">正在加载预约记录…</div>
        <div v-else-if="!appointments.length" class="schedule-empty">
          <EmptyState
            title="暂无预约"
            description="患者可通过患者服务预约，或由工作人员在现场建立预约。"
          >
            <button class="pilot-btn pilot-btn-primary" type="button" @click="openAppointment">＋ 现场预约</button>
          </EmptyState>
        </div>
        <div v-else class="schedule-table-scroll" role="region" aria-label="预约列表，窄屏可横向滚动" tabindex="0">
          <div class="schedule-mobile-hint">左右滑动查看完整表格</div>
          <table class="pilot-table schedule-table">
            <thead>
              <tr>
                <th scope="col">就诊时间</th>
                <th scope="col">患者</th>
                <th scope="col">医生</th>
                <th scope="col">类型</th>
                <th scope="col">原因</th>
                <th scope="col">状态</th>
                <th scope="col" class="cell-actions">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="a in appointments" :key="a.id">
                <td class="schedule-time">{{ fmt(a.scheduled_at) }}</td>
                <td>
                  <div class="schedule-patient">{{ a.patient_name }}</div>
                  <div class="schedule-sub pilot-mono">{{ a.mrn || a.patient_id }}</div>
                </td>
                <td>{{ a.doctor_name }}</td>
                <td>{{ a.appointment_type }}</td>
                <td class="schedule-reason" :title="a.reason || '未填写原因'">{{ a.reason || '—' }}</td>
                <td><StatusPill :label="appointmentStatus[a.status] ?? a.status" :tone="appointmentTones[a.status] ?? 'neutral'" /></td>
                <td class="cell-actions">
                  <div v-if="a.status === 'booked' || a.status === 'checked_in'" class="schedule-actions">
                    <button
                      v-if="a.status === 'booked'"
                      class="pilot-btn pilot-btn-sm"
                      type="button"
                      @click="askStatus(a, 'checked_in')"
                    >签到</button>
                    <button
                      v-if="a.status === 'checked_in'"
                      class="pilot-btn pilot-btn-sm pilot-btn-primary"
                      type="button"
                      @click="askStatus(a, 'completed')"
                    >完成</button>
                    <button
                      class="pilot-btn pilot-btn-sm pilot-btn-danger"
                      type="button"
                      @click="askStatus(a, 'no_show')"
                    >爽约</button>
                  </div>
                  <span v-else class="pilot-muted">—</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </SectionPanel>

      <div v-else-if="tab === 'slots'" class="pilot-split schedule-split">
        <SectionPanel title="号源列表" :subtitle="slotSubtitle" flush>
          <div v-if="loading" class="schedule-loading">正在加载号源…</div>
          <div v-else-if="!slots.length" class="schedule-empty">
            <EmptyState title="尚未创建号源" description="在右侧为医生设置出诊时间，号源会出现在现场预约的可选项里。" />
          </div>
          <div v-else class="schedule-table-scroll" role="region" aria-label="号源列表，窄屏可横向滚动" tabindex="0">
            <div class="schedule-mobile-hint">左右滑动查看完整表格</div>
            <table class="pilot-table slots-table">
              <thead>
                <tr>
                  <th scope="col">出诊时间</th>
                  <th scope="col">医生</th>
                  <th scope="col">类型</th>
                  <th scope="col">预约</th>
                  <th scope="col">状态</th>
                  <th scope="col" class="cell-actions">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="s in slots" :key="s.id">
                  <td class="schedule-time">{{ fmt(s.starts_at) }}</td>
                  <td>{{ s.doctor_name }}</td>
                  <td>{{ s.appointment_type }}</td>
                  <td class="pilot-mono">{{ s.booked }} / {{ s.capacity }}</td>
                  <td><StatusPill :label="slotLabel(s)" :tone="slotTone(s)" /></td>
                  <td class="cell-actions">
                    <button
                      class="pilot-btn pilot-btn-sm"
                      type="button"
                      :disabled="slotBusy === s.id"
                      @click="toggleSlot(s)"
                    >{{ slotBusy === s.id ? '更新中…' : (s.active ? '停用' : '启用') }}</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </SectionPanel>

        <SectionPanel title="新建号源" subtitle="设置医生、时间、类型与容量">
          <form class="slot-form" @submit.prevent="createSlot">
            <div v-if="isAdmin" class="pilot-field">
              <label for="slot-doctor">出诊医生</label>
              <select id="slot-doctor" v-model="slotForm.doctor_id" class="pilot-select">
                <option v-for="d in doctors" :key="d.id" :value="d.id">{{ d.display_name }}（{{ d.username }}）</option>
              </select>
            </div>
            <div class="pilot-field">
              <label for="slot-starts-at">出诊时间 <span class="required-mark">*</span></label>
              <input id="slot-starts-at" v-model="slotForm.starts_at" class="pilot-input" type="datetime-local" />
            </div>
            <div class="pilot-field">
              <label for="slot-type">号源类型</label>
              <select id="slot-type" v-model="slotForm.appointment_type" class="pilot-select">
                <option>门诊</option>
                <option>检查</option>
              </select>
            </div>
            <div class="pilot-field">
              <label for="slot-capacity">容量</label>
              <input id="slot-capacity" v-model="slotForm.capacity" class="pilot-input" type="number" min="1" max="100" />
              <p class="pilot-field-hint">容量不能小于当前已预约数量。</p>
            </div>
            <div class="slot-form-actions">
              <button class="pilot-btn pilot-btn-primary" type="submit" :disabled="saving || !doctors.length && isAdmin">
                {{ saving ? '创建中…' : '创建号源' }}
              </button>
            </div>
          </form>
        </SectionPanel>
      </div>

      <SectionPanel
        v-else-if="tab === 'feedback'"
        title="评价审核"
        :subtitle="feedbackSubtitle"
        flush
      >
        <div class="schedule-toolbar">
          <label class="schedule-filter">
            <span>审核状态</span>
            <select v-model="fbFilter" class="pilot-select" @change="loadFeedback">
              <option value="pending">待审核</option>
              <option value="public">已公开</option>
              <option value="hidden">已隐藏</option>
              <option value="">全部评价</option>
            </select>
          </label>
          <span class="pilot-count">共 {{ feedback.length }} 条 · 公开后患者端可见</span>
        </div>

        <div v-if="loading" class="schedule-loading">正在加载患者评价…</div>
        <div v-else-if="!feedback.length" class="schedule-empty">
          <EmptyState title="暂无评价" description="患者只能在就诊完成后提交评价；待审核评价会先进入这里。" />
        </div>
        <div v-else class="schedule-table-scroll" role="region" aria-label="评价列表，窄屏可横向滚动" tabindex="0">
          <div class="schedule-mobile-hint">左右滑动查看完整表格</div>
          <table class="pilot-table feedback-table">
            <thead>
              <tr>
                <th scope="col">患者</th>
                <th scope="col">医生</th>
                <th scope="col">评分</th>
                <th scope="col">评价内容</th>
                <th scope="col">状态</th>
                <th scope="col">提交时间</th>
                <th scope="col" class="cell-actions">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="f in feedback" :key="f.id">
                <td class="cell-strong">{{ f.patient_name }}</td>
                <td>{{ f.doctor_name || '—' }}</td>
                <td><span class="rating-stars" :aria-label="`${ratingStars(f.rating)}，共 5 分`">{{ ratingStars(f.rating) }}</span></td>
                <td class="feedback-content" :title="f.content || '未填写评价内容'">{{ f.content || '—' }}</td>
                <td><StatusPill :label="feedbackStatus[f.status] ?? f.status" :tone="feedbackTones[f.status] ?? 'neutral'" /></td>
                <td class="schedule-time">{{ fmt(f.created_at) }}</td>
                <td class="cell-actions">
                  <div class="schedule-actions">
                    <button v-if="f.status !== 'public'" class="pilot-btn pilot-btn-sm pilot-btn-primary" type="button" @click="moderate(f, 'public')">公开</button>
                    <button v-if="f.status !== 'hidden'" class="pilot-btn pilot-btn-sm" type="button" @click="moderate(f, 'hidden')">隐藏</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </SectionPanel>

      <ElDialog
        v-model="showAppointment"
        title="现场预约"
        width="560px"
        class="pilot-dialog"
        :close-on-click-modal="false"
        append-to-body
      >
        <p class="dialog-sub">为已建档患者分配可用号源；预约建立后会占用号源容量。</p>
        <div v-if="!patients.length" class="dialog-empty">当前没有可预约的患者档案，请先在患者档案中建立档案。</div>
        <div v-else class="dialog-form">
          <div class="pilot-field">
            <label for="appointment-patient">患者 <span class="required-mark">*</span></label>
            <select id="appointment-patient" v-model="aptForm.patient_id" class="pilot-select">
              <option value="">选择患者…</option>
              <option v-for="p in patients" :key="p.id" :value="p.id">{{ p.name }}（{{ p.mrn }}）</option>
            </select>
          </div>
          <div class="pilot-field">
            <label for="appointment-slot">可用号源 <span class="required-mark">*</span></label>
            <select id="appointment-slot" v-model="aptForm.slot_id" class="pilot-select" :disabled="!availableSlots.length">
              <option value="">{{ availableSlots.length ? '选择可用号源…' : '暂无可用号源' }}</option>
              <option v-for="s in availableSlots" :key="s.id" :value="s.id">
                {{ fmt(s.starts_at) }} · {{ s.doctor_name }} · {{ s.appointment_type }}
              </option>
            </select>
            <p class="pilot-field-hint">只显示未来、未停用且未约满的号源。</p>
          </div>
          <div class="pilot-field">
            <label for="appointment-reason">预约原因</label>
            <textarea id="appointment-reason" v-model="aptForm.reason" class="pilot-textarea" rows="2" placeholder="如：术后复查、伤口评估" />
          </div>
        </div>
        <div v-if="dialogError" class="pilot-error dialog-error" role="alert">{{ dialogError }}</div>
        <template #footer>
          <div class="dialog-actions">
            <button class="pilot-btn" type="button" @click="showAppointment = false">取消</button>
            <button class="pilot-btn pilot-btn-primary" type="button" :disabled="saving" @click="submitAppointment">
              {{ saving ? '建立中…' : '建立预约' }}
            </button>
          </div>
        </template>
      </ElDialog>

      <ElDialog
        v-model="showStatusConfirm"
        :title="statusConfirmTitle"
        width="480px"
        class="pilot-dialog"
        :close-on-click-modal="false"
        append-to-body
      >
        <p class="dialog-sub">{{ statusConfirmCopy }}</p>
        <div class="status-confirm-row">
          <span class="pilot-small">当前状态</span>
          <StatusPill
            v-if="pendingStatus"
            :label="appointmentStatus[pendingStatus.row.status] ?? pendingStatus.row.status"
            :tone="appointmentTones[pendingStatus.row.status] ?? 'neutral'"
          />
          <span class="pilot-muted">→</span>
          <StatusPill :label="pendingStatusLabel" :tone="pendingStatus ? appointmentTones[pendingStatus.status] ?? 'neutral' : 'neutral'" />
        </div>
        <div v-if="statusError" class="pilot-error dialog-error" role="alert">{{ statusError }}</div>
        <template #footer>
          <div class="dialog-actions">
            <button class="pilot-btn" type="button" @click="showStatusConfirm = false">取消</button>
            <button class="pilot-btn pilot-btn-primary" type="button" :disabled="statusBusy" @click="confirmStatus">
              {{ statusBusy ? '更新中…' : '确认变更' }}
            </button>
          </div>
        </template>
      </ElDialog>
      <ElDialog
        v-model="showSlotConfirm"
        title="停用号源"
        width="480px"
        class="pilot-dialog"
        :close-on-click-modal="false"
        append-to-body
      >
        <p class="dialog-sub">
          该号源已有 {{ pendingSlot?.booked ?? 0 }} 个预约。停用只关闭后续预约入口，
          <strong>不会取消已有预约</strong>。
        </p>
        <div v-if="pendingSlot" class="status-confirm-row">
          <span class="pilot-small">{{ fmt(pendingSlot.starts_at) }} · {{ pendingSlot.doctor_name }}</span>
          <StatusPill label="当前在用" tone="low" />
          <span class="pilot-muted">→</span>
          <StatusPill label="停用" tone="high" />
        </div>
        <template #footer>
          <div class="dialog-actions">
            <button class="pilot-btn" type="button" @click="showSlotConfirm = false; pendingSlot = null">取消</button>
            <button class="pilot-btn pilot-btn-danger" type="button" :disabled="slotBusy === pendingSlot?.id" @click="confirmDisableSlot">
              {{ slotBusy === pendingSlot?.id ? '停用中…' : '确认停用' }}
            </button>
          </div>
        </template>
      </ElDialog>
    </div>
  </div>
</template>

<style scoped>
.schedule-page { max-width: 1440px; }
.schedule-toolbar {
  display: flex;
  align-items: flex-end;
  gap: var(--pilot-space-4);
  flex-wrap: wrap;
  padding: var(--pilot-space-4);
  border-bottom: 1px solid var(--pilot-line);
  background: var(--pilot-surface);
}
.schedule-filter { display: flex; flex-direction: column; gap: var(--pilot-space-1); width: 168px; }
.schedule-filter > span { color: var(--pilot-muted); font-size: var(--pilot-font-xs); font-weight: 600; }
.pilot-count { margin-left: auto; color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
.schedule-loading { padding: var(--pilot-space-7) 0; color: var(--pilot-muted); text-align: center; }
.schedule-empty { padding: var(--pilot-space-5) 0; }
.schedule-table-scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; }
.schedule-mobile-hint { display: none; }
.schedule-table { min-width: 880px; }
.slots-table { min-width: 540px; }
.feedback-table { min-width: 880px; }
.schedule-time { color: var(--pilot-ink-soft); font-variant-numeric: tabular-nums; white-space: nowrap; }
.schedule-patient { color: var(--pilot-ink); font-weight: 600; }
.schedule-sub { margin-top: 2px; color: var(--pilot-muted); font-size: 11px; }
.schedule-reason {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.schedule-actions { display: flex; align-items: center; justify-content: flex-end; gap: var(--pilot-space-1); }
.schedule-actions .pilot-btn { height: 30px; padding: 0 var(--pilot-space-2); font-size: var(--pilot-font-xs); }
.schedule-split { align-items: stretch; }
.slot-form { display: grid; gap: var(--pilot-space-4); }
.slot-form-actions { padding-top: var(--pilot-space-2); }
.required-mark { color: var(--pilot-high); }
.dialog-form { display: grid; gap: var(--pilot-space-4); }
.dialog-sub { margin: 0 0 var(--pilot-space-4); color: var(--pilot-muted); font-size: var(--pilot-font-sm); line-height: 1.6; }
.dialog-empty { margin-bottom: var(--pilot-space-4); }
.dialog-error { margin: var(--pilot-space-4) 0 0; }
.dialog-actions { display: flex; justify-content: flex-end; gap: var(--pilot-space-2); }
.status-confirm-row { display: flex; align-items: center; gap: var(--pilot-space-2); flex-wrap: wrap; margin-top: var(--pilot-space-4); }
.rating-stars { color: var(--pilot-mid); letter-spacing: 1px; white-space: nowrap; }
.feedback-content { max-width: 320px; overflow-wrap: anywhere; }

@media (max-width: 1024px) {
  .schedule-split { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 650px) {
  .schedule-toolbar { align-items: stretch; }
  .schedule-filter { width: 100%; }
  .pilot-count { margin-left: 0; }
  .schedule-mobile-hint {
    display: block;
    position: sticky;
    left: 0;
    width: 100%;
    padding: var(--pilot-space-2) var(--pilot-space-4);
    border-bottom: 1px dashed var(--pilot-line);
    background: var(--pilot-surface);
    color: var(--pilot-muted);
    font-size: var(--pilot-font-xs);
  }
}
</style>

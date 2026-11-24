<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '../api/client'
import { useAuth } from '../composables/useAuth'

type Tab = 'overview' | 'users' | 'patients' | 'audit'
type Tone = 'neutral' | 'low' | 'mid' | 'high' | 'accent'

const auth = useAuth()
const tab = ref<Tab>('overview')
const loading = ref(true)
const error = ref('')
const notice = ref('')
const system = ref<any>(null)
const users = ref<any[]>([])
const accounts = ref<any[]>([])
const events = ref<any[]>([])
const auditAction = ref('')
const auditBusy = ref(false)
const backupBusy = ref(false)

const showUser = ref(false)
const editingUser = ref<any>(null)
const formError = ref('')
const saving = ref(false)
const userForm = reactive({
  username: '', display_name: '', role: 'doctor', password: '', must_change_password: true,
  active: true,
})
const accountForm = reactive({ id: '', active: true, password: '' })
const accountError = ref('')
const accountBusy = ref(false)

const isAdmin = computed(() => auth.user.value?.role === 'admin')
const pageDescription = computed(() => loading.value
  ? '正在读取员工账号、患者账号与审计数据…'
  : (!isAdmin.value
      ? '仅管理员可访问本页'
      : `员工账号、患者账号、审计追踪与数据库备份 · ${users.value.length} 个员工 · ${events.value.length} 条审计`))
const userDialogTitle = computed(() => editingUser.value ? '编辑员工账号' : '新建员工账号')
const selectedAccount = computed(() => accounts.value.find((a) => a.id === accountForm.id) || null)

const tabItems = computed(() => [
  { value: 'overview', label: '系统概览' },
  { value: 'users', label: '员工账号', count: users.value.length },
  { value: 'patients', label: '患者账号', count: accounts.value.length },
  { value: 'audit', label: '审计日志', count: events.value.length },
])

function fmt(value: any) {
  if (!value) return '—'
  if (typeof value === 'number') return new Date(value * 1000).toLocaleString('zh-CN')
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString('zh-CN')
}
function bytes(n?: number) {
  if (!n) return '—'
  if (n > 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`
  return `${(n / 1024).toFixed(0)} KB`
}
const AUDIT_ACTION_LABELS: Record<string, string> = {
  report_publish: '发布报告',
  report_revoke: '撤销报告',
  report_pdf_download: '下载报告 PDF',
  patient_create: '新建患者',
  patient_update: '更新患者',
  patient_grant: '添加患者授权',
  patient_grant_revoke: '撤销患者授权',
  query_code_issue: '生成查询码',
  encounter_create: '新建接诊',
  encounter_update: '更新接诊',
  draft_save: '保存草稿',
  draft_delete: '删除草稿',
  prediction_run: '运行模型',
  clinical_review: '记录复核',
  user_create: '新建账号',
  user_update: '更新账号',
  password_change: '修改密码',
  import_preview: '预览导入',
  import_commit: '提交导入',
  import_row_create: '导入患者',
  appointment_staff_create: '新建现场预约',
  slot_create: '创建号源',
  slot_update: '更新号源',
  appointment_status: '更新预约状态',
  feedback_moderate: '审核评价',
  database_backup: '数据库备份',
  patient_account_update: '更新患者账号',
  portal_register: '患者注册',
  portal_login: '患者登录',
  portal_bind_patient: '患者绑定档案',
  portal_query: '患者查询码核验',
  appointment_book: '患者预约',
  appointment_cancel: '取消预约',
  feedback_create: '提交评价',
  portal_report_view: '患者查看报告',
  portal_report_pdf: '患者下载报告 PDF',
}
const AUDIT_DETAIL_LABELS: Record<string, string> = {
  patient_id: '患者',
  filename: '文件名',
  model_version: '模型版本',
  report_id: '报告',
  encounter_id: '就诊',
  prediction_id: '预测',
  appointment_id: '预约',
  slot_id: '号源',
  doctor_id: '医生',
  patient_account_id: '患者账号',
  action: '动作',
  status: '状态',
  reason: '原因',
  role: '角色',
  active: '账号状态',
  batch_id: '批次号',
  valid: '有效行',
  invalid: '错误行',
  imported: '已导入',
  failed: '失败',
  mrn: '病历号',
  username: '账号',
  must_change_password: '要求修改密码',
  password_reset: '已重置密码',
  rows: '行数',
  missing_ack: '缺失指标确认',
  sheet_name: '工作表',
  sha256: '文件摘要',
  review_id: '复核记录',
  decision: '复核结论',
  draft_version: '草稿版本',
  row_version: '记录版本',
  base_row_version: '基线版本',
  appointment_type: '预约类型',
  starts_at: '开始时间',
  capacity: '号源容量',
  target_id: '目标记录',
  owner_id: '负责医生',
  version: '版本',
  total: '总行数',
  measured: '实测指标',
  missing: '缺失指标',
  case_ref: '就诊编号',
  row: '源文行号',
}
const SENSITIVE_AUDIT_KEYS = ['password', 'query_code', 'certificate', 'phone', 'token', 'secret']
const AUDIT_ENTITY_LABELS: Record<string, string> = {
  report: '报告',
  patient: '患者',
  encounter: '就诊',
  prediction: '预测',
  appointment: '预约',
  slot: '号源',
  user: '员工账号',
  patient_account: '患者账号',
  feedback: '评价',
  import_batch: '导入批次',
  backup: '数据库备份',
  system: '系统',
}
function auditActionLabel(action: string) {
  return AUDIT_ACTION_LABELS[action] ?? action
}
function auditEntityLabel(entityType?: string) {
  if (!entityType) return '—'
  return AUDIT_ENTITY_LABELS[entityType] ?? entityType
}
function auditActorLabel(event: any) {
  if (event.actor_name) return event.actor_name
  if (event.actor_type === 'user') return '员工'
  if (event.actor_type === 'query_code') return '查询码会话'
  if (event.actor_type === 'system') return '系统'
  return event.actor_type || '系统'
}
function auditDetail(detail: any) {
  if (!detail || typeof detail !== 'object') return String(detail ?? '—')
  const entries = Object.entries(detail)
  if (!entries.length) return '—'
  return entries.slice(0, 12).map(([key, value]) => {
    const label = AUDIT_DETAIL_LABELS[key] ?? key
    const sensitive = SENSITIVE_AUDIT_KEYS.some((fragment) => key.toLowerCase().includes(fragment))
    let display: string
    if (sensitive) {
      display = '已隐藏'
    } else if (value === null || value === undefined) {
      display = '无'
    } else if (typeof value === 'boolean') {
      display = value ? '是' : '否'
    } else if (Array.isArray(value)) {
      display = `共 ${value.length} 项`
    } else if (typeof value === 'object') {
      display = '已记录'
    } else {
      display = String(value).slice(0, 120)
    }
    return `${label}：${display}`
  }).join(' · ')
}
function userRoleLabel(role?: string) {
  return role === 'admin' ? '管理员' : '医生'
}
function accountStatusLabel(active: boolean) {
  return active ? '启用' : '停用'
}
function accountStatusTone(active: boolean): Tone {
  return active ? 'low' : 'high'
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [s, u, a] = await Promise.all([
      api.system(), api.adminUsers(), api.patientAccounts(),
    ])
    system.value = s
    users.value = u.users ?? []
    accounts.value = a.accounts ?? []
    await loadAudit()
  } catch (e: any) {
    error.value = e?.message ?? '管理数据加载失败'
  } finally {
    loading.value = false
  }
}
async function loadAudit() {
  auditBusy.value = true
  try {
    const res = await api.audit(auditAction.value ? `action=${encodeURIComponent(auditAction.value)}` : '')
    events.value = res.events ?? []
  } catch (e: any) {
    error.value = e?.message ?? '审计日志加载失败'
  } finally {
    auditBusy.value = false
  }
}
async function runBackup() {
  backupBusy.value = true
  error.value = ''
  try {
    const res = await api.backup()
    notice.value = `数据库备份完成：${res.filename}（${bytes(res.bytes)}）`
    system.value = await api.system()
  } catch (e: any) {
    error.value = e?.message ?? '备份失败'
  } finally {
    backupBusy.value = false
  }
}

function openCreateUser() {
  editingUser.value = null
  Object.assign(userForm, {
    username: '', display_name: '', role: 'doctor', password: '',
    must_change_password: true, active: true,
  })
  formError.value = ''
  showUser.value = true
}
function openEditUser(u: any) {
  editingUser.value = u
  Object.assign(userForm, {
    username: u.username, display_name: u.display_name, role: u.role,
    password: '', must_change_password: Boolean(u.must_change_password), active: Boolean(u.active),
  })
  formError.value = ''
  showUser.value = true
}
async function saveUser() {
  formError.value = ''
  if (editingUser.value && Boolean(editingUser.value.active) && !Boolean(userForm.active)) {
    const confirmed = window.confirm(
      `停用账号“${editingUser.value.display_name || editingUser.value.username}”后，该账号将立即退出登录且无法继续使用。确认停用？`,
    )
    if (!confirmed) return
  }
  saving.value = true
  try {
    if (editingUser.value) {
      const payload: any = {
        display_name: userForm.display_name.trim(),
        role: userForm.role,
        active: Boolean(userForm.active),
        must_change_password: Boolean(userForm.must_change_password),
      }
      if (userForm.password) payload.password = userForm.password
      if (!payload.display_name) {
        formError.value = '显示姓名不能为空'
        saving.value = false
        return
      }
      await api.updateUser(editingUser.value.id, payload)
    } else {
      if (!userForm.username.trim() || !userForm.display_name.trim() || userForm.password.length < 12) {
        formError.value = '账号、姓名必填，初始密码至少 12 个字符'
        saving.value = false
        return
      }
      await api.createUser({
        username: userForm.username.trim(),
        display_name: userForm.display_name.trim(),
        role: userForm.role,
        password: userForm.password,
        must_change_password: Boolean(userForm.must_change_password),
      })
    }
    showUser.value = false
    notice.value = editingUser.value ? '账号已更新' : '账号已创建'
    await load()
  } catch (e: any) {
    formError.value = e?.message ?? '保存失败'
  } finally {
    saving.value = false
  }
}

function openAccount(a: any) {
  Object.assign(accountForm, { id: a.id, active: Boolean(a.active), password: '' })
  accountError.value = ''
}
function clearAccount() {
  accountForm.id = ''
  accountForm.password = ''
  accountError.value = ''
}
async function saveAccount() {
  if (!accountForm.id) return
  accountError.value = ''
  if (selectedAccount.value?.active && !Boolean(accountForm.active)) {
    const confirmed = window.confirm(
      `停用患者账号“${selectedAccount.value.display_name}”后，该账号将无法继续登录。确认停用？`,
    )
    if (!confirmed) return
  }
  if (accountForm.password && accountForm.password.length < 12) {
    accountError.value = '重置密码至少 12 个字符'
    return
  }
  accountBusy.value = true
  try {
    const payload: any = { active: Boolean(accountForm.active) }
    if (accountForm.password) payload.password = accountForm.password
    await api.updatePatientAccount(accountForm.id, payload)
    notice.value = '患者账号已更新'
    clearAccount()
    await load()
  } catch (e: any) {
    accountError.value = e?.message ?? '更新失败'
  } finally {
    accountBusy.value = false
  }
}

onMounted(() => {
  if (!isAdmin.value) {
    error.value = '仅管理员可访问本页'
    loading.value = false
    return
  }
  load()
})
</script>

<template>
  <div class="pilot-page">
    <div class="pilot-page-inner admin-page">
      <PageHeader
        kicker="系统 / 管理"
        title="账号与审计"
        :description="pageDescription"
      >
        <template #actions>
          <button v-if="isAdmin" class="pilot-btn" type="button" :disabled="loading" @click="load">刷新</button>
        </template>
      </PageHeader>

      <div v-if="error" class="pilot-error" role="alert">{{ error }}</div>
      <div v-if="notice" class="pilot-notice" role="status">{{ notice }}</div>

      <PilotTabs v-if="isAdmin" v-model="tab" label="账号与审计分区" :tabs="tabItems" />

      <div v-if="loading" class="admin-loading">
        <div class="pilot-skeleton admin-loading-line" />
        <div class="pilot-skeleton admin-loading-line" />
        <div class="pilot-skeleton admin-loading-line is-short" />
      </div>

      <template v-else-if="system">
        <div v-if="tab === 'overview'" class="pilot-stack">
          <div class="admin-metrics">
            <div class="admin-metric">
              <span>员工账号</span>
              <strong>{{ system.counts.users }}</strong>
              <small>管理员与医生 · {{ users.length }} 个当前可见</small>
            </div>
            <div class="admin-metric">
              <span>患者档案</span>
              <strong>{{ system.counts.patients }}</strong>
              <small>累计 {{ system.counts.encounters }} 次就诊</small>
            </div>
            <div class="admin-metric">
              <span>正式报告</span>
              <strong>{{ system.counts.reports }}</strong>
              <small>已发布或已撤销文书</small>
            </div>
            <div class="admin-metric">
              <span>数据库</span>
              <strong>{{ bytes(system.database.bytes) }}</strong>
              <small class="pilot-mono">{{ system.database.filename }}</small>
            </div>
          </div>

          <div class="admin-overview-grid">
            <SectionPanel title="运行环境" subtitle="数据库、模型与预约业务摘要">
              <div class="admin-facts">
                <div><span>模型版本</span><strong class="pilot-mono">{{ system.model_version }}</strong></div>
                <div><span>数据库文件</span><strong class="pilot-mono">{{ system.database.filename }}</strong></div>
                <div><span>备份数量</span><strong>{{ system.backup_count }}</strong></div>
                <div><span>预约 / 评价</span><strong>{{ system.counts.appointments }} / {{ system.counts.feedback }}</strong></div>
              </div>
              <div class="admin-note">数据库采用 WAL 模式，备份由 SQLite Backup API 生成，并写入 SHA-256 校验文件。</div>
              <button class="pilot-btn pilot-btn-primary" type="button" :disabled="backupBusy" @click="runBackup">
                {{ backupBusy ? '备份中…' : '立即创建数据库备份' }}
              </button>
            </SectionPanel>

            <SectionPanel title="最近备份" :subtitle="system.backup_count ? `共 ${system.backup_count} 个备份` : '尚未创建手动备份'" flush>
              <div v-if="!system.backups?.length" class="admin-backup-empty">
                <EmptyState title="还没有手动备份" description="点击“立即创建数据库备份”生成第一份快照；备份文件名包含时间与校验信息。" />
              </div>
              <div v-else class="admin-backup-list">
                <div v-for="b in system.backups" :key="b.name" class="admin-backup-row">
                  <div class="admin-backup-main">
                    <span class="pilot-mono">{{ b.name }}</span>
                    <small>{{ fmt(b.created_at) }}</small>
                  </div>
                  <span class="pilot-small">{{ bytes(b.bytes) }}</span>
                </div>
              </div>
            </SectionPanel>
          </div>
        </div>

        <SectionPanel
          v-else-if="tab === 'users'"
          title="员工账号"
          :subtitle="`${users.length} 个账号 · 管理员与医生共用登录入口`"
          flush
        >
          <template #actions>
            <button class="pilot-btn pilot-btn-primary" type="button" @click="openCreateUser">＋ 新建员工</button>
          </template>
          <div v-if="!users.length" class="admin-empty">
            <EmptyState title="还没有员工账号" description="先创建管理员或医生账号，账号才能登录临床业务。" />
          </div>
          <div v-else class="admin-table-scroll" role="region" aria-label="员工账号表格，窄屏可横向滚动" tabindex="0">
            <div class="admin-mobile-hint">左右滑动查看完整表格</div>
            <table class="pilot-table admin-users-table">
              <thead>
                <tr>
                  <th scope="col">账号</th>
                  <th scope="col">姓名</th>
                  <th scope="col">角色</th>
                  <th scope="col">状态</th>
                  <th scope="col">首登改密</th>
                  <th scope="col">最近登录</th>
                  <th scope="col" class="cell-actions">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="u in users" :key="u.id">
                  <td class="pilot-mono cell-strong">{{ u.username }}</td>
                  <td>{{ u.display_name }}</td>
                  <td>{{ userRoleLabel(u.role) }}</td>
                  <td><StatusPill :label="u.active ? '启用' : '停用'" :tone="u.active ? 'low' : 'high'" /></td>
                  <td>{{ u.must_change_password ? '是' : '否' }}</td>
                  <td class="admin-date">{{ fmt(u.last_login_at) }}</td>
                  <td class="cell-actions"><button class="pilot-btn pilot-btn-sm" type="button" @click="openEditUser(u)">编辑</button></td>
                </tr>
              </tbody>
            </table>
          </div>
        </SectionPanel>

        <div v-else-if="tab === 'patients'" class="pilot-split admin-accounts-split">
          <SectionPanel title="患者端账号" :subtitle="`${accounts.length} 个账号 · 绑定档案后才能查看报告`" flush>
            <div v-if="!accounts.length" class="admin-empty">
              <EmptyState title="暂无患者账号" description="患者可在患者服务页面自行注册并绑定档案；管理员也可在这里查看绑定状态。" />
            </div>
            <div v-else class="admin-table-scroll" role="region" aria-label="患者账号表格，窄屏可横向滚动" tabindex="0">
              <div class="admin-mobile-hint">左右滑动查看完整表格</div>
              <table class="pilot-table admin-accounts-table">
                <thead>
                  <tr><th scope="col">账号</th><th scope="col">姓名</th><th scope="col">绑定档案</th><th scope="col">状态</th><th scope="col" class="cell-actions">操作</th></tr>
                </thead>
                <tbody>
                  <tr v-for="a in accounts" :key="a.id" :class="{ 'is-selected': accountForm.id === a.id }">
                    <td class="pilot-mono cell-strong">{{ a.username }}</td>
                    <td>{{ a.display_name }}</td>
                    <td>{{ a.patient_name || '未绑定' }}<div v-if="a.mrn" class="admin-sub pilot-mono">{{ a.mrn }}</div></td>
                    <td><StatusPill :label="accountStatusLabel(a.active)" :tone="accountStatusTone(a.active)" /></td>
                    <td class="cell-actions"><button class="pilot-btn pilot-btn-sm" type="button" @click="openAccount(a)">管理</button></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </SectionPanel>

          <SectionPanel title="账号设置" subtitle="启用、停用或重置患者登录密码">
            <div v-if="!selectedAccount" class="admin-account-placeholder">
              <EmptyState title="选择一个患者账号" description="从左侧点击“管理”，可以查看绑定档案并更新账号状态。" />
            </div>
            <div v-else class="admin-account-form">
              <div class="admin-account-summary">
                <span class="pilot-section-label">当前账号</span>
                <strong>{{ selectedAccount.display_name }}</strong>
                <span class="pilot-mono">{{ selectedAccount.username }}</span>
                <span class="pilot-small">{{ selectedAccount.patient_name || '未绑定档案' }}<template v-if="selectedAccount.mrn"> · {{ selectedAccount.mrn }}</template></span>
              </div>
              <div class="pilot-field">
                <label for="account-active">账号状态</label>
                <select id="account-active" v-model="accountForm.active" class="pilot-select">
                  <option :value="true">启用</option>
                  <option :value="false">停用</option>
                </select>
              </div>
              <div class="pilot-field">
                <label for="account-password">重置密码（留空则不修改）</label>
                <input id="account-password" v-model="accountForm.password" class="pilot-input" type="password" placeholder="至少 12 个字符" autocomplete="new-password" />
                <p class="pilot-field-hint">重置后该患者已有的登录会话会失效。</p>
              </div>
              <div class="admin-account-actions">
                <button class="pilot-btn" type="button" @click="clearAccount">取消选择</button>
                <button class="pilot-btn pilot-btn-primary" type="button" :disabled="accountBusy" @click="saveAccount">
                  {{ accountBusy ? '保存中…' : '保存账号设置' }}
                </button>
              </div>
              <div v-if="accountError" class="pilot-error admin-account-error" role="alert">{{ accountError }}</div>
            </div>
          </SectionPanel>
        </div>

        <SectionPanel
          v-else-if="tab === 'audit'"
          title="审计日志"
          :subtitle="`${events.length} 条记录 · 只读，不可在页面删除`"
          flush
        >
          <div class="admin-audit-toolbar">
            <label class="admin-audit-filter">
              <span>操作类型</span>
              <input v-model="auditAction" class="pilot-input" type="search" placeholder="如 report_publish、appointment_status…" @keydown.enter.prevent="loadAudit" />
            </label>
            <button class="pilot-btn" type="button" :disabled="auditBusy" @click="loadAudit">{{ auditBusy ? '查询中…' : '查询' }}</button>
            <button v-if="auditAction" class="pilot-btn pilot-btn-ghost" type="button" @click="auditAction = ''; loadAudit()">清除</button>
          </div>
          <div v-if="!events.length" class="admin-empty">
            <EmptyState title="没有审计记录" description="发布、撤销、账号变更和备份操作都会在这里留下记录。" />
          </div>
          <div v-else class="admin-table-scroll" role="region" aria-label="审计日志表格，窄屏可横向滚动" tabindex="0">
            <div class="admin-mobile-hint">左右滑动查看完整表格</div>
            <table class="pilot-table admin-audit-table">
              <thead>
                <tr>
                  <th scope="col">时间</th>
                  <th scope="col">操作人</th>
                  <th scope="col">动作</th>
                  <th scope="col">对象</th>
                  <th scope="col">IP</th>
                  <th scope="col">详情</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="e in events" :key="e.id">
                  <td class="admin-date">{{ fmt(e.created_at) }}</td>
                  <td>{{ auditActorLabel(e) }}</td>
                  <td class="audit-action">{{ auditActionLabel(e.action) }}</td>
                  <td>{{ auditEntityLabel(e.entity_type) }}<div class="admin-sub pilot-mono">{{ e.entity_id || '—' }}</div></td>
                  <td class="pilot-mono">{{ e.ip || '—' }}</td>
                  <td class="admin-audit-detail" :title="auditDetail(e.detail)">{{ auditDetail(e.detail) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </SectionPanel>
      </template>

      <ElDialog
        v-model="showUser"
        :title="userDialogTitle"
        width="620px"
        class="pilot-dialog"
        :close-on-click-modal="false"
        append-to-body
      >
        <p class="admin-dialog-sub">新账号默认要求首次登录修改密码；停用账号无法继续登录。</p>
        <div class="admin-user-form">
          <div class="pilot-field">
            <label for="user-username">登录账号 <span class="admin-required">*</span></label>
            <input id="user-username" v-model="userForm.username" class="pilot-input" autocomplete="off" :disabled="Boolean(editingUser)" />
          </div>
          <div class="pilot-field">
            <label for="user-display-name">显示姓名 <span class="admin-required">*</span></label>
            <input id="user-display-name" v-model="userForm.display_name" class="pilot-input" autocomplete="off" />
          </div>
          <div class="pilot-field">
            <label for="user-role">角色</label>
            <select id="user-role" v-model="userForm.role" class="pilot-select">
              <option value="doctor">医生</option>
              <option value="admin">管理员</option>
            </select>
          </div>
          <div class="pilot-field">
            <label for="user-active">账号状态</label>
            <select id="user-active" v-model="userForm.active" class="pilot-select">
              <option :value="true">启用</option>
              <option :value="false">停用</option>
            </select>
          </div>
          <div class="pilot-field admin-field-full">
            <label for="user-password">{{ editingUser ? '重置密码（留空不修改）' : '初始密码 *' }}</label>
            <input id="user-password" v-model="userForm.password" class="pilot-input" type="password" autocomplete="new-password" :placeholder="editingUser ? '留空保持现有密码' : '至少 12 个字符'" />
          </div>
          <label class="admin-check-field admin-field-full" for="user-first-login">
            <input id="user-first-login" v-model="userForm.must_change_password" type="checkbox" />
            <span>首次登录必须修改密码</span>
          </label>
        </div>
        <div v-if="formError" class="pilot-error admin-dialog-error" role="alert">{{ formError }}</div>
        <template #footer>
          <div class="admin-dialog-actions">
            <button class="pilot-btn" type="button" @click="showUser = false">取消</button>
            <button class="pilot-btn pilot-btn-primary" type="button" :disabled="saving" @click="saveUser">
              {{ saving ? '保存中…' : '保存' }}
            </button>
          </div>
        </template>
      </ElDialog>
    </div>
  </div>
</template>

<style scoped>
.admin-page { max-width: 1440px; }
.admin-loading { display: grid; gap: var(--pilot-space-3); padding: var(--pilot-space-5) 0; }
.admin-loading-line { height: 28px; }
.admin-loading-line.is-short { width: 40%; }
.admin-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: var(--pilot-space-3); }
.admin-metric {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  padding: var(--pilot-space-4) var(--pilot-space-4) var(--pilot-space-3);
  border: 1px solid var(--pilot-line);
  border-radius: var(--pilot-radius-card);
  background: var(--pilot-surface);
  box-shadow: var(--pilot-shadow);
}
.admin-metric > span { color: var(--pilot-muted); font-size: var(--pilot-font-xs); font-weight: 600; }
.admin-metric > strong { color: var(--pilot-ink); font-size: var(--pilot-font-xl); font-weight: 700; line-height: 1.2; }
.admin-metric > small { overflow: hidden; color: var(--pilot-muted); font-size: 11px; line-height: 1.5; text-overflow: ellipsis; white-space: nowrap; }
.admin-overview-grid { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr); gap: var(--pilot-space-4); align-items: stretch; }
.admin-facts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--pilot-space-3) var(--pilot-space-5); }
.admin-facts > div { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.admin-facts span { color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
.admin-facts strong { overflow-wrap: anywhere; color: var(--pilot-ink); font-size: var(--pilot-font-sm); }
.admin-note { margin: var(--pilot-space-4) 0; color: var(--pilot-muted); font-size: var(--pilot-font-xs); line-height: 1.65; }
.admin-backup-list { display: grid; }
.admin-backup-row { display: flex; align-items: center; justify-content: space-between; gap: var(--pilot-space-3); padding: var(--pilot-space-3) var(--pilot-space-4); border-bottom: 1px solid var(--pilot-line); }
.admin-backup-row:last-child { border-bottom: 0; }
.admin-backup-main { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.admin-backup-main > span { overflow-wrap: anywhere; color: var(--pilot-ink-soft); font-size: var(--pilot-font-xs); }
.admin-backup-main > small { color: var(--pilot-muted); font-size: 11px; }
.admin-backup-empty { padding: var(--pilot-space-2) 0; }
.admin-table-scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; }
.admin-mobile-hint { display: none; }
.admin-users-table { min-width: 900px; }
.admin-accounts-table { min-width: 540px; }
.admin-audit-table { min-width: 1000px; }
.admin-empty { padding: var(--pilot-space-4) 0; }
.admin-date { color: var(--pilot-ink-soft); font-variant-numeric: tabular-nums; white-space: nowrap; }
.admin-sub { margin-top: 2px; color: var(--pilot-muted); font-size: 11px; }
.admin-audit-toolbar { display: flex; align-items: flex-end; gap: var(--pilot-space-2); flex-wrap: wrap; padding: var(--pilot-space-4); border-bottom: 1px solid var(--pilot-line); }
.admin-audit-filter { display: flex; flex-direction: column; gap: var(--pilot-space-1); width: min(360px, 100%); }
.admin-audit-filter > span { color: var(--pilot-muted); font-size: var(--pilot-font-xs); font-weight: 600; }
.admin-audit-detail { max-width: 320px; overflow-wrap: anywhere; color: var(--pilot-muted); font-size: 11px; line-height: 1.55; }
.admin-accounts-split { align-items: stretch; }
.admin-accounts-split .pilot-panel { min-width: 0; }
tr.is-selected td { background: var(--pilot-accent-soft); }
tr.is-selected td:first-child { box-shadow: inset 3px 0 0 var(--pilot-accent); }
.admin-account-placeholder { padding: var(--pilot-space-2) 0; }
.admin-account-form { display: grid; gap: var(--pilot-space-4); }
.admin-account-summary { display: flex; flex-direction: column; gap: 2px; padding: var(--pilot-space-3); border: 1px solid var(--pilot-line); background: var(--pilot-surface-2); border-radius: var(--pilot-radius-control); }
.admin-account-summary strong { color: var(--pilot-ink); font-size: var(--pilot-font-md); }
.admin-account-summary .pilot-small { overflow-wrap: anywhere; }
.admin-account-actions { display: flex; justify-content: flex-end; gap: var(--pilot-space-2); flex-wrap: wrap; padding-top: var(--pilot-space-2); }
.admin-account-error { margin: 0; }
.admin-dialog-sub { margin: 0 0 var(--pilot-space-4); color: var(--pilot-muted); font-size: var(--pilot-font-sm); line-height: 1.6; }
.admin-user-form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--pilot-space-4); }
.admin-field-full { grid-column: 1 / -1; }
.admin-required { color: var(--pilot-high); }
.admin-check-field { display: flex; align-items: center; gap: var(--pilot-space-2); color: var(--pilot-ink-soft); font-size: var(--pilot-font-sm); }
.admin-check-field input { accent-color: var(--pilot-accent); }
.admin-dialog-error { margin: var(--pilot-space-4) 0 0; }
.admin-dialog-actions { display: flex; justify-content: flex-end; gap: var(--pilot-space-2); }

@media (max-width: 1024px) {
  .admin-overview-grid,
  .admin-accounts-split { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 800px) {
  .admin-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .admin-facts { grid-template-columns: minmax(0, 1fr); }
  .admin-user-form { grid-template-columns: minmax(0, 1fr); }
  .admin-field-full { grid-column: auto; }
}
@media (max-width: 650px) {
  .admin-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .admin-metric > small { overflow: visible; text-overflow: clip; white-space: normal; }
  .admin-audit-toolbar { align-items: stretch; flex-direction: column; }
  .admin-audit-filter { width: 100%; }
  .admin-mobile-hint {
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

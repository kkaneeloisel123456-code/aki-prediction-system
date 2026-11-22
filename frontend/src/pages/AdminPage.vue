<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '../api/client'
import { useAuth } from '../composables/useAuth'

const auth = useAuth()
const tab = ref<'overview' | 'users' | 'patients' | 'audit'>('overview')
const loading = ref(true)
const error = ref('')
const notice = ref('')
const system = ref<any>(null)
const users = ref<any[]>([])
const accounts = ref<any[]>([])
const events = ref<any[]>([])
const auditAction = ref('')
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

const isAdmin = computed(() => auth.user.value?.role === 'admin')

function fmt(value: any) {
  if (!value) return '—'
  if (typeof value === 'number') return new Date(value * 1000).toLocaleString('zh-CN')
  return new Date(value).toLocaleString('zh-CN')
}
function bytes(n?: number) {
  if (!n) return '—'
  if (n > 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`
  return `${(n / 1024).toFixed(0)} KB`
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
  try {
    const res = await api.audit(auditAction.value ? `action=${encodeURIComponent(auditAction.value)}` : '')
    events.value = res.events ?? []
  } catch (e: any) { error.value = e?.message ?? '审计日志加载失败' }
}
async function runBackup() {
  backupBusy.value = true
  error.value = ''
  try {
    const res = await api.backup()
    notice.value = `数据库备份完成：${res.filename}（${bytes(res.bytes)}）`
    system.value = await api.system()
  } catch (e: any) { error.value = e?.message ?? '备份失败' }
  finally { backupBusy.value = false }
}

function openCreateUser() {
  editingUser.value = null
  Object.assign(userForm, { username: '', display_name: '', role: 'doctor', password: '', must_change_password: true, active: true })
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
  saving.value = true
  try {
    if (editingUser.value) {
      const payload: any = {
        display_name: userForm.display_name, role: userForm.role,
        active: Boolean(userForm.active), must_change_password: Boolean(userForm.must_change_password),
      }
      if (userForm.password) payload.password = userForm.password
      await api.updateUser(editingUser.value.id, payload)
    } else {
      if (!userForm.username || !userForm.display_name || userForm.password.length < 12) {
        formError.value = '账号、姓名必填，初始密码至少 12 个字符'
        saving.value = false
        return
      }
      await api.createUser({
        username: userForm.username, display_name: userForm.display_name,
        role: userForm.role, password: userForm.password,
        must_change_password: Boolean(userForm.must_change_password),
      })
    }
    showUser.value = false
    notice.value = editingUser.value ? '账号已更新' : '账号已创建'
    await load()
  } catch (e: any) { formError.value = e?.message ?? '保存失败' }
  finally { saving.value = false }
}

function openAccount(a: any) {
  Object.assign(accountForm, { id: a.id, active: Boolean(a.active), password: '' })
  formError.value = ''
}
async function saveAccount() {
  if (!accountForm.id) return
  formError.value = ''
  try {
    const payload: any = { active: Boolean(accountForm.active) }
    if (accountForm.password) payload.password = accountForm.password
    await api.updatePatientAccount(accountForm.id, payload)
    accountForm.id = ''
    accountForm.password = ''
    notice.value = '患者账号已更新'
    await load()
  } catch (e: any) { formError.value = e?.message ?? '更新失败' }
}
onMounted(() => { if (!isAdmin.value) { error.value = '仅管理员可访问本页'; loading.value = false } else load() })
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h1 class="page-title">账号与审计</h1>
        <div class="page-subtitle">员工账号、患者账号、持久化审计日志与数据库备份</div>
      </div>
      <div class="page-actions"><button class="btn btn-secondary" :disabled="loading" @click="load">刷新</button></div>
    </div>
    <div v-if="error" class="error">{{ error }}</div>
    <div v-if="notice" class="info-box">{{ notice }}</div>

    <div class="tabs">
      <button class="tab" :class="{active: tab === 'overview'}" @click="tab = 'overview'">系统概览</button>
      <button class="tab" :class="{active: tab === 'users'}" @click="tab = 'users'">员工账号</button>
      <button class="tab" :class="{active: tab === 'patients'}" @click="tab = 'patients'">患者账号</button>
      <button class="tab" :class="{active: tab === 'audit'}" @click="tab = 'audit'">审计日志</button>
    </div>

    <div v-if="loading" class="card"><div class="empty-state">正在加载管理数据…</div></div>

    <template v-else-if="system">
      <div v-if="tab === 'overview'">
        <div class="summary-strip">
          <div class="summary-item"><div class="label">员工账号</div><div class="value">{{ system.counts.users }}</div><div class="hint">管理员与医生</div></div>
          <div class="summary-item"><div class="label">患者档案</div><div class="value">{{ system.counts.patients }}</div><div class="hint">累计 {{ system.counts.encounters }} 次就诊</div></div>
          <div class="summary-item"><div class="label">正式报告</div><div class="value">{{ system.counts.reports }}</div><div class="hint">审计事件 {{ system.counts.audit_events }}</div></div>
          <div class="summary-item"><div class="label">数据库</div><div class="value" style="font-size:16px">{{ bytes(system.database.bytes) }}</div><div class="hint">{{ system.database.filename }}</div></div>
        </div>
        <div class="grid-2">
          <div class="card">
            <div class="card-header"><span class="card-title">生产环境信息</span></div>
            <div class="card-body">
              <div class="info-grid" style="grid-template-columns:1fr 1fr">
                <div class="info-item"><div class="k">模型版本</div><div class="v font-mono">{{ system.model_version }}</div></div>
                <div class="info-item"><div class="k">数据库文件</div><div class="v font-mono">{{ system.database.filename }}</div></div>
                <div class="info-item"><div class="k">备份数量</div><div class="v">{{ system.backup_count }}</div></div>
                <div class="info-item"><div class="k">预约 / 评价</div><div class="v">{{ system.counts.appointments }} / {{ system.counts.feedback }}</div></div>
              </div>
              <div class="info-box mt-12">数据库采用 WAL 模式，备份由 SQLite Backup API 生成，并写入 SHA-256 校验文件。</div>
              <button class="btn btn-primary" :disabled="backupBusy" @click="runBackup">{{ backupBusy ? '备份中…' : '立即创建数据库备份' }}</button>
            </div>
          </div>
          <div class="card">
            <div class="card-header"><span class="card-title">最近备份</span></div>
            <div class="card-body">
              <div v-if="!system.backups?.length" class="muted">还没有手动备份。</div>
              <div v-for="b in system.backups" :key="b.name" style="display:flex;justify-content:space-between;gap:10px;padding:6px 0;border-bottom:1px dashed var(--border)">
                <div><div class="font-mono" style="font-size:10px;color:var(--text)">{{ b.name }}</div><div class="sub-cell">{{ fmt(b.created_at) }}</div></div>
                <span style="font-size:10px;color:var(--text-dim)">{{ bytes(b.bytes) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="tab === 'users'" class="card">
        <div class="toolbar">
          <span class="card-title">员工账号</span><span class="toolbar-spacer" />
          <button class="btn btn-primary" @click="openCreateUser">＋ 新建员工账号</button>
        </div>
        <div class="table-wrap">
          <table class="data-table">
            <thead><tr><th>账号</th><th>姓名</th><th>角色</th><th>状态</th><th>首登改密</th><th>最近登录</th><th></th></tr></thead>
            <tbody>
              <tr v-for="u in users" :key="u.id">
                <td class="primary-cell font-mono">{{ u.username }}</td>
                <td>{{ u.display_name }}</td>
                <td>{{ u.role === 'admin' ? '管理员' : '医生' }}</td>
                <td><span class="status" :class="u.active ? 'status-active' : 'status-inactive'">{{ u.active ? '启用' : '停用' }}</span></td>
                <td>{{ u.must_change_password ? '是' : '否' }}</td>
                <td>{{ fmt(u.last_login_at) }}</td>
                <td class="text-right"><button class="btn btn-sm btn-secondary" @click="openEditUser(u)">编辑</button></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-if="tab === 'patients'" class="grid-2-1">
        <div class="card">
          <div class="card-header"><span class="card-title">患者端账号</span></div>
          <div v-if="!accounts.length" class="empty-state"><strong>暂无患者账号</strong>患者可在患者服务页面自行注册并绑定档案。</div>
          <div v-else class="table-wrap">
            <table class="data-table">
              <thead><tr><th>账号</th><th>姓名</th><th>绑定档案</th><th>状态</th><th></th></tr></thead>
              <tbody>
                <tr v-for="a in accounts" :key="a.id">
                  <td class="primary-cell font-mono">{{ a.username }}</td>
                  <td>{{ a.display_name }}</td>
                  <td>{{ a.patient_name || '未绑定' }}<div v-if="a.mrn" class="sub-cell font-mono">{{ a.mrn }}</div></td>
                  <td><span class="status" :class="a.active ? 'status-active' : 'status-inactive'">{{ a.active ? '启用' : '停用' }}</span></td>
                  <td class="text-right"><button class="btn btn-sm btn-secondary" @click="openAccount(a)">管理</button></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div class="card">
          <div class="card-header"><span class="card-title">账号操作</span></div>
          <div class="card-body">
            <div v-if="!accountForm.id" class="muted">从左侧选择一个患者账号后可启用、停用或重置密码。</div>
            <template v-else>
              <div class="form-group mb-12"><label>账号状态</label><select v-model="accountForm.active" class="form-control"><option :value="true">启用</option><option :value="false">停用</option></select></div>
              <div class="form-group mb-12"><label>重置密码（留空则不修改）</label><input v-model="accountForm.password" class="form-control" type="password" placeholder="至少 12 个字符" /></div>
              <button class="btn btn-primary" @click="saveAccount">保存账号设置</button>
            </template>
            <div v-if="formError" class="error mt-12">{{ formError }}</div>
          </div>
        </div>
      </div>

      <div v-if="tab === 'audit'" class="card">
        <div class="toolbar">
          <input v-model="auditAction" class="form-control" placeholder="按操作类型筛选，如 report_publish…" />
          <button class="btn btn-secondary" @click="loadAudit">查询</button>
          <span class="toolbar-spacer" /><span class="muted" style="font-size:10px">最近 {{ events.length }} 条</span>
        </div>
        <div class="table-wrap">
          <table class="data-table">
            <thead><tr><th>时间</th><th>操作人</th><th>动作</th><th>对象</th><th>IP</th><th>详情</th></tr></thead>
            <tbody>
              <tr v-for="e in events" :key="e.id">
                <td>{{ fmt(e.created_at) }}</td>
                <td>{{ e.actor_name || e.actor_type }}</td>
                <td class="font-mono">{{ e.action }}</td>
                <td>{{ e.entity_type }}<div class="sub-cell font-mono">{{ e.entity_id }}</div></td>
                <td class="font-mono">{{ e.ip || '—' }}</td>
                <td class="wrap"><span class="font-mono" style="font-size:9px">{{ JSON.stringify(e.detail) }}</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <div v-if="showUser" class="modal-mask" @click.self="showUser = false">
      <div class="modal-panel" style="max-width:560px">
        <div class="modal-head"><div><div class="modal-title">{{ editingUser ? '编辑员工账号' : '新建员工账号' }}</div><div class="modal-sub">新账号默认要求首次登录修改密码。</div></div><button class="modal-close" @click="showUser = false">×</button></div>
        <div class="modal-body">
          <div class="form-grid-2">
            <div class="form-group"><label>登录账号</label><input v-model="userForm.username" class="form-control" :disabled="Boolean(editingUser)" /></div>
            <div class="form-group"><label>显示姓名</label><input v-model="userForm.display_name" class="form-control" /></div>
            <div class="form-group"><label>角色</label><select v-model="userForm.role" class="form-control"><option value="doctor">医生</option><option value="admin">管理员</option></select></div>
            <div class="form-group"><label>状态</label><select v-model="userForm.active" class="form-control"><option :value="true">启用</option><option :value="false">停用</option></select></div>
            <div class="form-group full"><label>{{ editingUser ? '重置密码（留空不修改）' : '初始密码 *' }}</label><input v-model="userForm.password" class="form-control" type="password" /></div>
            <label class="form-group full" style="flex-direction:row;align-items:center;gap:8px"><input v-model="userForm.must_change_password" type="checkbox" /> 首次登录必须修改密码</label>
          </div>
          <div v-if="formError" class="error mt-12">{{ formError }}</div>
        </div>
        <div class="modal-foot"><button class="btn btn-secondary" @click="showUser = false">取消</button><button class="btn btn-primary" :disabled="saving" @click="saveUser">保存</button></div>
      </div>
    </div>
  </div>
</template>

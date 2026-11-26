<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import { useAuth } from '../composables/useAuth'
import { ElMessage } from 'element-plus'
import 'element-plus/es/components/message/style/css'

const router = useRouter()
const auth = useAuth()
const loading = ref(true)
const error = ref('')
const rows = ref<any[]>([])
const search = ref('')
const riskFilter = ref('')
const showCreate = ref(false)
const saving = ref(false)
const formError = ref('')
const doctors = ref<any[]>([])

const form = reactive({
  mrn: '', name: '', sex: '未知', birth_date: '', certificate_last4: '', phone_last4: '', owner_id: '',
})

const filtered = computed(() => rows.value.filter((p) => {
  const q = search.value.trim().toLowerCase()
  if (q && !(`${p.name} ${p.mrn}`.toLowerCase().includes(q))) return false
  if (riskFilter.value && p.latest_risk !== riskFilter.value) return false
  return true
}))

function riskText(level?: string) {
  if (!level) return '未评估'
  return `${level}风险`
}
function riskClass(level?: string) {
  if (level === '高') return 'pilot-chip-high'
  if (level === '中') return 'pilot-chip-mid'
  if (level === '低') return 'pilot-chip-low'
  return ''
}
function fmt(value?: string) {
  if (!value) return '—'
  return new Date(value).toLocaleDateString('zh-CN')
}
const today = new Date().toISOString().slice(0, 10)
function openPatient(row: any) {
  router.push(`/patients/${row.id}`)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [w, d] = await Promise.all([api.workstation(), api.doctors().catch(() => ({ doctors: [] }))])
    rows.value = w.patients ?? []
    doctors.value = d.doctors ?? []
  } catch (e: any) {
    error.value = e?.message ?? '患者列表加载失败'
  } finally {
    loading.value = false
  }
}

function openCreate() {
  Object.assign(form, {
    mrn: '', name: '', sex: '未知', birth_date: '', certificate_last4: '',
    phone_last4: '', owner_id: '',
  })
  formError.value = ''
  showCreate.value = true
}

async function submitCreate() {
  formError.value = ''
  if (!form.mrn.trim() || !form.name.trim()) {
    formError.value = '病历号和姓名不能为空'
    return
  }
  if (auth.user.value?.role === 'admin' && !form.owner_id) {
    formError.value = '请选择一名医生作为档案负责人'
    return
  }
  saving.value = true
  try {
    const payload: any = {
      mrn: form.mrn.trim(), name: form.name.trim(), sex: form.sex,
      birth_date: form.birth_date || null,
      certificate_last4: form.certificate_last4.trim() || null,
      phone_last4: form.phone_last4.trim() || null,
    }
    if (auth.user.value?.role === 'admin' && form.owner_id) payload.owner_id = form.owner_id
    const created = await api.createPatient(payload)
    showCreate.value = false
    ElMessage.success('患者档案已创建')
    router.push(`/patients/${created.id}`)
  } catch (e: any) {
    formError.value = e?.message ?? '创建失败'
  } finally {
    saving.value = false
  }
}
function handleWindowEscape(event: KeyboardEvent) {
  if (event.key !== 'Escape' || !showCreate.value || event.defaultPrevented) return
  const picker = document.querySelector('.el-picker-panel')
  if (picker && picker.getBoundingClientRect().height > 0) return
  showCreate.value = false
}
onMounted(() => {
  load()
  window.addEventListener('keydown', handleWindowEscape)
})
onUnmounted(() => window.removeEventListener('keydown', handleWindowEscape))
</script>

<template>
  <div class="pilot-page patients-pilot">
    <div class="pilot-page-inner">
      <header class="pilot-head">
        <div>
          <div class="pilot-kicker">患者主索引</div>
          <h1 class="pilot-title">患者档案</h1>
          <p class="pilot-sub">真实患者档案、授权与就诊入口 · 当前 {{ rows.length }} 份档案</p>
        </div>
        <div class="pilot-actions">
          <RouterLink to="/batch" class="pilot-btn">批量导入</RouterLink>
          <button class="pilot-btn pilot-btn-primary" type="button" @click="openCreate">＋ 新建患者</button>
          <button class="pilot-btn" type="button" :disabled="loading" @click="load">刷新</button>
        </div>
      </header>

      <div v-if="error" class="pilot-error">{{ error }}</div>

      <section class="pilot-panel patients-panel">
        <div class="pilot-toolbar">
          <label class="pilot-search">
            <span class="pilot-muted">搜索</span>
            <input v-model="search" class="pilot-input" placeholder="姓名或病历号" />
          </label>
          <label class="pilot-filter">
            <span class="pilot-muted">风险</span>
            <select v-model="riskFilter" class="pilot-select">
              <option value="">全部等级</option>
              <option value="高">高风险</option>
              <option value="中">中风险</option>
              <option value="低">低风险</option>
            </select>
          </label>
          <span class="pilot-count">共 {{ filtered.length }} 条</span>
        </div>

        <div v-if="loading" class="pilot-loading">正在载入患者档案…</div>
        <ElTable
          v-else
          :data="filtered"
          row-key="id"
          class="patient-table"
          @row-click="openPatient"
        >
          <ElTableColumn label="患者" min-width="180">
            <template #default="{ row }">
              <div class="patient-name">{{ row.name }}</div>
              <div class="patient-meta">{{ row.phone || '未登记联系方式' }}</div>
            </template>
          </ElTableColumn>
          <ElTableColumn label="性别 / 出生日期" width="168">
            <template #default="{ row }">{{ row.sex }} <span class="pilot-muted">/ {{ row.birth_date || row.birth_year || '—' }}</span></template>
          </ElTableColumn>
          <ElTableColumn label="病历号" width="132">
            <template #default="{ row }"><span class="pilot-mono">{{ row.mrn }}</span></template>
          </ElTableColumn>
          <ElTableColumn label="档案负责人" width="120">
            <template #default="{ row }">{{ row.owner_name || '未指定' }}</template>
          </ElTableColumn>
          <ElTableColumn label="就诊" width="64" align="center" prop="encounter_count" />
          <ElTableColumn label="最近风险" width="148">
            <template #default="{ row }">
              <span class="pilot-chip" :class="riskClass(row.latest_risk)">{{ riskText(row.latest_risk) }}</span>
              <span v-if="row.latest_prediction != null" class="patient-prob">{{ (row.latest_prediction * 100).toFixed(1) }}%</span>
            </template>
          </ElTableColumn>
          <ElTableColumn label="更新时间" width="112">
            <template #default="{ row }">{{ fmt(row.updated_at) }}</template>
          </ElTableColumn>
          <ElTableColumn label="" width="80" align="right">
            <template #default="{ row }">
              <button class="pilot-btn pilot-btn-ghost" type="button" @click.stop="openPatient(row)">查看</button>
            </template>
          </ElTableColumn>
          <template #empty>
            <ElEmpty :description="rows.length ? '没有匹配的患者，调整筛选条件后再试。' : '还没有患者档案，先建立第一份档案。'" />
          </template>
        </ElTable>
      </section>
    </div>

    <ElDialog
      v-model="showCreate"
      title="新建患者档案"
      width="640px"
      class="pilot-dialog"
      :close-on-click-modal="false"
      append-to-body
    >
      <form id="create-patient-form" @submit.prevent="submitCreate" @keydown.enter.prevent="submitCreate">
      <div class="dialog-sub">只登记检索与身份核对所需字段，证件与电话仅存末四位。</div>
      <div class="patient-form">
        <div class="form-field">
          <label for="patient-mrn">病历号 *</label>
          <input id="patient-mrn" v-model="form.mrn" class="pilot-input" placeholder="如 MRN2026001" autocomplete="off" />
        </div>
        <div class="form-field">
          <label for="patient-name">姓名 *</label>
          <input id="patient-name" v-model="form.name" class="pilot-input" placeholder="患者真实姓名" autocomplete="off" />
        </div>
        <div class="form-field">
          <label for="patient-sex">性别</label>
          <select id="patient-sex" v-model="form.sex" class="pilot-select">
            <option>未知</option><option>男</option><option>女</option>
          </select>
        </div>
        <div class="form-field">
          <label for="patient-birth">出生日期</label>
          <input id="patient-birth" v-model="form.birth_date" class="pilot-input" type="date" :max="today" />
        </div>
        <div class="form-field">
          <label for="patient-cert">证件号末四位</label>
          <input id="patient-cert" v-model="form.certificate_last4" class="pilot-input" maxlength="4" placeholder="用于患者核验" autocomplete="off" />
        </div>
        <div class="form-field">
          <label for="patient-phone">手机号末四位</label>
          <input id="patient-phone" v-model="form.phone_last4" class="pilot-input" maxlength="4" placeholder="用于患者核验" autocomplete="off" />
        </div>
        <div v-if="auth.user.value?.role === 'admin'" class="form-field form-field-full">
          <label for="patient-owner">档案负责人（医生）</label>
          <select id="patient-owner" v-model="form.owner_id" class="pilot-select">
            <option value="">请选择医生</option>
            <option v-for="d in doctors" :key="d.id" :value="d.id">{{ d.display_name }}（{{ d.username }}）</option>
          </select>
          <div class="field-hint">管理员不能作为临床档案负责人，请先创建医生账号。</div>
        </div>
      </div>
      <div v-if="formError" class="pilot-error form-error">{{ formError }}</div>
      </form>
      <template #footer>
        <div class="dialog-actions">
          <button class="pilot-btn" type="button" @click="showCreate = false">取消</button>
          <button class="pilot-btn pilot-btn-primary" type="submit" form="create-patient-form" :disabled="saving">
            {{ saving ? '创建中…' : '创建档案' }}
          </button>
        </div>
      </template>
    </ElDialog>
  </div>
</template>

<style scoped>
.patients-panel { overflow: hidden; }
.pilot-dialog { max-width: calc(100vw - 48px); }
.pilot-toolbar {
  display: flex;
  align-items: flex-end;
  gap: var(--pilot-space-4);
  flex-wrap: wrap;
  padding: var(--pilot-space-4);
  border-bottom: 1px solid var(--pilot-line);
  background: var(--pilot-surface);
}
.pilot-search { display: flex; flex-direction: column; gap: var(--pilot-space-1); min-width: 240px; }
.pilot-filter { display: flex; flex-direction: column; gap: var(--pilot-space-1); width: 144px; }
.pilot-count { margin-left: auto; color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
.pilot-loading { padding: var(--pilot-space-7) 0; color: var(--pilot-muted); text-align: center; }
.patient-name {
  overflow: hidden;
  color: var(--pilot-ink);
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.patient-meta { margin-top: var(--pilot-space-1); color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
.patient-prob { margin-left: var(--pilot-space-2); color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
.dialog-sub { margin-bottom: var(--pilot-space-4); color: var(--pilot-muted); font-size: var(--pilot-font-sm); }
.patient-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--pilot-space-4);
}
.form-field { display: flex; flex-direction: column; gap: var(--pilot-space-1); }
.form-field label { color: var(--pilot-ink-soft); font-size: var(--pilot-font-xs); font-weight: 600; }
.form-field-full { grid-column: 1 / -1; }
.field-hint { color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
.form-error { margin: var(--pilot-space-4) 0 0; }
.dialog-actions { display: flex; justify-content: flex-end; gap: var(--pilot-space-4); }

@media (max-width: 720px) {
  .patient-form { grid-template-columns: 1fr; }
  .pilot-toolbar { align-items: stretch; }
  .pilot-search, .pilot-filter { width: 100%; }
  .pilot-count { margin-left: 0; }
}
</style>

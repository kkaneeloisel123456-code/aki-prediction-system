<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import { useAuth } from '../composables/useAuth'

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
  mrn: '', name: '', sex: '男', birth_year: '', certificate_last4: '', phone_last4: '', owner_id: '',
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
  if (level === '高') return 'status-high'
  if (level === '中') return 'status-medium'
  if (level === '低') return 'status-low'
  return 'status-draft'
}
function fmt(value?: string) {
  if (!value) return '—'
  return new Date(value).toLocaleDateString('zh-CN')
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
    mrn: '', name: '', sex: '男', birth_year: '', certificate_last4: '',
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
      birth_year: form.birth_year ? Number(form.birth_year) : null,
      certificate_last4: form.certificate_last4.trim() || null,
      phone_last4: form.phone_last4.trim() || null,
    }
    if (auth.user.value?.role === 'admin' && form.owner_id) payload.owner_id = form.owner_id
    const created = await api.createPatient(payload)
    showCreate.value = false
    router.push(`/patients/${created.id}`)
  } catch (e: any) {
    formError.value = e?.message ?? '创建失败'
  } finally {
    saving.value = false
  }
}
onMounted(load)
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h1 class="page-title">患者档案</h1>
        <div class="page-subtitle">真实患者主索引、档案授权与就诊入口 · 当前 {{ rows.length }} 份档案</div>
      </div>
      <div class="page-actions">
        <button class="btn btn-primary" @click="openCreate">＋ 新建患者</button>
        <button class="btn btn-secondary" :disabled="loading" @click="load">刷新</button>
      </div>
    </div>

    <div v-if="error" class="error">{{ error }}</div>

    <div class="card">
      <div class="toolbar">
        <input v-model="search" class="form-control" placeholder="搜索姓名或病历号…" />
        <select v-model="riskFilter" class="form-control" style="min-width:130px">
          <option value="">全部风险等级</option>
          <option value="高">高风险</option>
          <option value="中">中风险</option>
          <option value="低">低风险</option>
        </select>
        <span class="toolbar-spacer" />
        <span class="muted" style="font-size:10px">共 {{ filtered.length }} 条</span>
      </div>
      <div v-if="loading" class="empty-state">正在加载患者档案…</div>
      <div v-else-if="!filtered.length" class="empty-state">
        <strong>{{ rows.length ? '没有匹配的患者' : '还没有患者档案' }}</strong>
        {{ rows.length ? '调整筛选条件后再试。' : '点击右上角“新建患者”建立第一份档案。' }}
      </div>
      <div v-else class="table-wrap">
        <table class="data-table">
          <thead>
            <tr>
              <th>患者</th><th>性别 / 出生年</th><th>病历号</th><th>档案负责人</th>
              <th>就诊</th><th>最近风险</th><th>更新时间</th><th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in filtered" :key="p.id" class="clickable" @click="router.push(`/patients/${p.id}`)">
              <td>
                <div class="primary-cell">{{ p.name }}</div>
                <div class="sub-cell">{{ p.phone || '未登记联系方式' }}</div>
              </td>
              <td>{{ p.sex }}<span class="sub-cell"> / {{ p.birth_year ?? '—' }}</span></td>
              <td class="font-mono">{{ p.mrn }}</td>
              <td>{{ p.owner_name || '未指定' }}</td>
              <td>{{ p.encounter_count }}</td>
              <td>
                <span class="status" :class="riskClass(p.latest_risk)">{{ riskText(p.latest_risk) }}</span>
                <span v-if="p.latest_prediction != null" class="sub-cell">{{ (p.latest_prediction * 100).toFixed(1) }}%</span>
              </td>
              <td>{{ fmt(p.updated_at) }}</td>
              <td class="text-right"><span class="btn btn-sm btn-secondary">查看</span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div v-if="showCreate" class="modal-mask" @click.self="showCreate = false">
      <div class="modal-panel" style="max-width:620px">
        <div class="modal-head">
          <div><div class="modal-title">新建患者档案</div><div class="modal-sub">只登记检索与身份核对所需的字段，证件与电话仅存末四位。</div></div>
          <button class="modal-close" @click="showCreate = false">×</button>
        </div>
        <div class="modal-body">
          <div class="form-grid-2">
            <div class="form-group"><label>病历号 *</label><input v-model="form.mrn" class="form-control" placeholder="如 MRN2026001" /></div>
            <div class="form-group"><label>姓名 *</label><input v-model="form.name" class="form-control" placeholder="患者真实姓名" /></div>
            <div class="form-group">
              <label>性别</label>
              <select v-model="form.sex" class="form-control"><option>男</option><option>女</option><option>未知</option></select>
            </div>
            <div class="form-group"><label>出生年份</label><input v-model="form.birth_year" class="form-control" type="number" placeholder="如 1960" /></div>
            <div class="form-group"><label>证件号末四位</label><input v-model="form.certificate_last4" class="form-control" maxlength="4" placeholder="用于患者核验" /></div>
            <div class="form-group"><label>手机号末四位</label><input v-model="form.phone_last4" class="form-control" maxlength="4" placeholder="用于患者核验" /></div>
            <div v-if="auth.user.value?.role === 'admin'" class="form-group full">
              <label>档案负责人（医生）</label>
              <select v-model="form.owner_id" class="form-control">
                <option value="">系统自动指派？不，请选择医生</option>
                <option v-for="d in doctors" :key="d.id" :value="d.id">{{ d.display_name }}（{{ d.username }}）</option>
              </select>
              <div class="muted" style="font-size:9px">管理员不能作为临床档案负责人，请先创建医生账号。</div>
            </div>
          </div>
          <div v-if="formError" class="error mt-12">{{ formError }}</div>
        </div>
        <div class="modal-foot">
          <button class="btn btn-secondary" @click="showCreate = false">取消</button>
          <button class="btn btn-primary" :disabled="saving" @click="submitCreate">{{ saving ? '创建中…' : '创建档案' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

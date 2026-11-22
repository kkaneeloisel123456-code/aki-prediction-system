<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api/client'
import { useAuth } from '../composables/useAuth'

const route = useRoute()
const router = useRouter()
const auth = useAuth()
const loading = ref(true)
const error = ref('')
const patient = ref<any>(null)
const encounters = ref<any[]>([])
const doctors = ref<any[]>([])
const showEncounter = ref(false)
const saveBusy = ref(false)
const formError = ref('')
const queryResult = ref<any>(null)
const showQuery = ref(false)
const showEdit = ref(false)
const editForm = reactive<any>({})

const encForm = reactive({
  case_ref: '', occurred_at: '', surgery_type: '', diagnosis: '', orders: '',
})
const isAdmin = computed(() => auth.user.value?.role === 'admin')
const canEdit = computed(() => patient.value?.access?.edit)

const statusText: Record<string, string> = {
  draft: '草稿', predicted: '待复核', reviewed: '已复核', published: '已发布',
}
function fmt(value?: string) {
  if (!value) return '—'
  return new Date(value).toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}
function localNow() {
  const d = new Date()
  const off = d.getTimezoneOffset()
  return new Date(d.getTime() - off * 60_000).toISOString().slice(0, 16)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const id = route.params.id as string
    const [p, e] = await Promise.all([api.patient(id), api.encounters(id)])
    patient.value = p
    encounters.value = e.encounters ?? []
    if (isAdmin.value) {
      const d = await api.doctors().catch(() => ({ doctors: [] }))
      doctors.value = d.doctors ?? []
    }
  } catch (e: any) {
    error.value = e?.message ?? '患者档案加载失败'
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
      diagnosis: encForm.diagnosis,
      orders: encForm.orders,
      values: {},
    })
    showEncounter.value = false
    router.push(`/encounters/${created.id}`)
  } catch (e: any) {
    formError.value = e?.message ?? '创建就诊失败'
  } finally {
    saveBusy.value = false
  }
}

async function issueCode() {
  error.value = ''
  try {
    queryResult.value = await api.queryCode(patient.value.id)
    showQuery.value = true
    await load()
  } catch (e: any) {
    error.value = e?.message ?? '查询码生成失败'
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
  } catch (e: any) {
    formError.value = e?.message ?? '保存失败'
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
  } catch (e: any) { error.value = e?.message ?? '授权失败' }
}
async function removeGrant(doctorId: string) {
  if (!confirm('确认撤销该医生的档案访问授权？')) return
  try {
    await api.removeGrant(patient.value.id, doctorId)
    await load()
  } catch (e: any) { error.value = e?.message ?? '撤销失败' }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
          <RouterLink to="/patients" class="btn btn-sm btn-ghost">← 患者档案</RouterLink>
        </div>
        <h1 class="page-title">{{ patient?.name || '患者详情' }}</h1>
        <div class="page-subtitle">
          <span class="font-mono">{{ patient?.mrn }}</span> · {{ patient?.sex }} · {{ patient?.birth_year || '出生年未登记' }}
        </div>
      </div>
      <div class="page-actions">
        <button v-if="canEdit && patient" class="btn btn-primary" @click="openEncounter">＋ 新建接诊</button>
        <button v-if="patient" class="btn btn-secondary" @click="issueCode">生成患者查询码</button>
        <button v-if="canEdit" class="btn btn-secondary" @click="openEdit">编辑档案</button>
        <button class="btn btn-secondary" :disabled="loading" @click="load">刷新</button>
      </div>
    </div>

    <div v-if="error" class="error">{{ error }}</div>
    <div v-if="loading" class="card"><div class="empty-state">正在加载患者档案…</div></div>

    <template v-else-if="patient">
      <div class="card">
        <div class="card-header">
          <span class="card-title">基本信息</span>
          <span class="status" :class="patient.active ? 'status-active' : 'status-inactive'">{{ patient.active ? '在管' : '已归档' }}</span>
        </div>
        <div class="card-body">
          <div class="info-grid">
            <div class="info-item"><div class="k">病历号</div><div class="v font-mono">{{ patient.mrn }}</div></div>
            <div class="info-item"><div class="k">性别 / 出生年</div><div class="v">{{ patient.sex }} / {{ patient.birth_year ?? '—' }}</div></div>
            <div class="info-item"><div class="k">档案负责人</div><div class="v">{{ patient.owner_name || '未指定' }}</div></div>
            <div class="info-item"><div class="k">联系电话</div><div class="v">{{ patient.phone || '未登记' }}</div></div>
            <div class="info-item"><div class="k">证件信息</div><div class="v">{{ patient.certificate || '未登记' }}</div></div>
            <div class="info-item"><div class="k">就诊记录</div><div class="v">{{ encounters.length }} 次</div></div>
            <div class="info-item"><div class="k">创建时间</div><div class="v">{{ fmt(patient.created_at) }}</div></div>
            <div class="info-item"><div class="k">最近更新</div><div class="v">{{ fmt(patient.updated_at) }}</div></div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <span class="card-title">就诊记录</span>
          <span class="muted" style="font-size:10px">{{ encounters.length }} 次</span>
        </div>
        <div v-if="!encounters.length" class="empty-state">
          <strong>还没有就诊记录</strong>
          点击“新建接诊”开始录入指标并生成风险报告。
        </div>
        <div v-else class="table-wrap">
          <table class="data-table">
            <thead><tr><th>就诊编号</th><th>发生时间</th><th>手术类型</th><th>状态</th><th>最近风险</th><th>报告</th><th></th></tr></thead>
            <tbody>
              <tr v-for="e in encounters" :key="e.id" class="clickable" @click="router.push(`/encounters/${e.id}`)">
                <td class="primary-cell">{{ e.case_ref }}</td>
                <td>{{ fmt(e.occurred_at) }}</td>
                <td>{{ e.surgery_type || '—' }}</td>
                <td><span class="status" :class="`status-${e.status}`">{{ statusText[e.status] ?? e.status }}</span></td>
                <td>
                  <span v-if="e.latest_prediction" class="status" :class="`status-${e.latest_prediction.risk_level === '高' ? 'high' : e.latest_prediction.risk_level === '中' ? 'medium' : 'low'}`">{{ e.latest_prediction.risk_level }}</span>
                  <span v-else class="muted">未评估</span>
                </td>
                <td><span v-if="e.latest_report" class="font-mono" style="font-size:10px">{{ e.latest_report.report_no }}</span><span v-else class="muted">—</span></td>
                <td class="text-right"><span class="btn btn-sm btn-secondary">进入</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-if="isAdmin" class="card">
        <div class="card-header"><span class="card-title">医生访问授权</span></div>
        <div class="card-body">
          <div v-if="!patient.grants?.length" class="muted">除档案负责人外，尚未授权其他医生。</div>
          <div v-for="g in patient.grants" :key="g.doctor_id" style="display:flex;align-items:center;gap:10px;padding:7px 0;border-bottom:1px dashed var(--border)">
            <span style="font-size:11px;color:var(--text-bright)">{{ g.display_name }}</span>
            <span class="status status-info">{{ g.permission === 'edit' ? '可编辑' : '只读' }}</span>
            <span class="flex-1" />
            <button class="btn btn-sm btn-danger" @click="removeGrant(g.doctor_id)">撤销</button>
          </div>
          <div class="flex gap-8 mt-12" style="flex-wrap:wrap">
            <select v-model="grantForm.doctor_id" class="form-control" style="width:200px">
              <option value="">选择医生…</option>
              <option v-for="d in doctors.filter(x => x.id !== patient.owner_id)" :key="d.id" :value="d.id">{{ d.display_name }}</option>
            </select>
            <select v-model="grantForm.permission" class="form-control" style="width:110px">
              <option value="view">只读</option><option value="edit">可编辑</option>
            </select>
            <button class="btn btn-secondary" @click="addGrant">添加授权</button>
          </div>
        </div>
      </div>
    </template>

    <!-- 新建就诊 -->
    <div v-if="showEncounter" class="modal-mask" @click.self="showEncounter = false">
      <div class="modal-panel" style="max-width:620px">
        <div class="modal-head">
          <div><div class="modal-title">新建就诊</div><div class="modal-sub">为 {{ patient?.name }} 建立一次围手术期风险评估。</div></div>
          <button class="modal-close" @click="showEncounter = false">×</button>
        </div>
        <div class="modal-body">
          <div class="form-grid-2">
            <div class="form-group"><label>就诊编号 *</label><input v-model="encForm.case_ref" class="form-control" /></div>
            <div class="form-group"><label>发生时间 *</label><input v-model="encForm.occurred_at" class="form-control" type="datetime-local" /></div>
            <div class="form-group full"><label>手术类型</label><input v-model="encForm.surgery_type" class="form-control" placeholder="如 冠脉搭桥术" /></div>
            <div class="form-group full"><label>临床诊断（可稍后补充）</label><textarea v-model="encForm.diagnosis" class="form-control" rows="2" /></div>
            <div class="form-group full"><label>医嘱 / 随访建议（可稍后补充）</label><textarea v-model="encForm.orders" class="form-control" rows="2" /></div>
          </div>
          <div v-if="formError" class="error mt-12">{{ formError }}</div>
        </div>
        <div class="modal-foot">
          <button class="btn btn-secondary" @click="showEncounter = false">取消</button>
          <button class="btn btn-primary" :disabled="saveBusy" @click="submitEncounter">{{ saveBusy ? '创建中…' : '创建并进入接诊' }}</button>
        </div>
      </div>
    </div>

    <!-- 编辑档案 -->
    <div v-if="showEdit" class="modal-mask" @click.self="showEdit = false">
      <div class="modal-panel" style="max-width:620px">
        <div class="modal-head">
          <div><div class="modal-title">编辑患者档案</div><div class="modal-sub">证件与电话留空表示不修改已保存的末四位。</div></div>
          <button class="modal-close" @click="showEdit = false">×</button>
        </div>
        <div class="modal-body">
          <div class="form-grid-2">
            <div class="form-group"><label>姓名</label><input v-model="editForm.name" class="form-control" /></div>
            <div class="form-group"><label>性别</label><select v-model="editForm.sex" class="form-control"><option>男</option><option>女</option><option>未知</option></select></div>
            <div class="form-group"><label>出生年份</label><input v-model="editForm.birth_year" class="form-control" type="number" /></div>
            <div class="form-group"><label>状态</label><select v-model="editForm.active" class="form-control"><option :value="true">在管</option><option :value="false">归档</option></select></div>
            <div class="form-group"><label>证件号末四位（更新）</label><input v-model="editForm.certificate_last4" class="form-control" maxlength="4" /></div>
            <div class="form-group"><label>手机号末四位（更新）</label><input v-model="editForm.phone_last4" class="form-control" maxlength="4" /></div>
            <div v-if="isAdmin" class="form-group full">
              <label>档案负责人</label>
              <select v-model="editForm.owner_id" class="form-control">
                <option v-for="d in doctors" :key="d.id" :value="d.id">{{ d.display_name }}</option>
              </select>
            </div>
          </div>
          <div v-if="formError" class="error mt-12">{{ formError }}</div>
        </div>
        <div class="modal-foot">
          <button class="btn btn-secondary" @click="showEdit = false">取消</button>
          <button class="btn btn-primary" :disabled="saveBusy" @click="submitEdit">保存</button>
        </div>
      </div>
    </div>

    <!-- 查询码 -->
    <div v-if="showQuery" class="modal-mask" @click.self="showQuery = false">
      <div class="modal-panel" style="max-width:480px">
        <div class="modal-head"><div class="modal-title">患者查询码</div><button class="modal-close" @click="showQuery = false">×</button></div>
        <div class="modal-body" style="text-align:center">
          <div class="font-mono" style="font-size:30px;font-weight:900;letter-spacing:6px;color:var(--primary);padding:14px 0">{{ queryResult?.query_code }}</div>
          <div class="warning-box" style="text-align:left">{{ queryResult?.notice }}</div>
          <div class="muted" style="font-size:10px">过期时间：{{ fmt(new Date(queryResult?.expires_at * 1000).toISOString()) }}</div>
        </div>
        <div class="modal-foot"><button class="btn btn-primary" @click="showQuery = false">我已记录</button></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, saveBlob } from '../api/client'

const router = useRouter()
const loading = ref(true)
const error = ref('')
const reports = ref<any[]>([])
const search = ref('')
const status = ref('published')
const downloading = ref('')

const filtered = computed(() => reports.value.filter((r) => {
  const q = search.value.trim().toLowerCase()
  if (!q) return true
  return `${r.report_no} ${r.patient_name} ${r.mrn}`.toLowerCase().includes(q)
}))

function fmt(value?: string) {
  if (!value) return '—'
  return new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}
function riskClass(level?: string) {
  return level === '高' ? 'status-high' : level === '中' ? 'status-medium' : level === '低' ? 'status-low' : 'status-draft'
}
async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await api.reports(`status=${status.value}`)
    reports.value = res.reports ?? []
  } catch (e: any) {
    error.value = e?.message ?? '报告列表加载失败'
  } finally {
    loading.value = false
  }
}
async function download(r: any) {
  downloading.value = r.id
  try {
    const blob = await api.reportPdf(r.id)
    saveBlob(blob, `${r.report_no}.pdf`)
  } catch (e: any) {
    error.value = e?.message ?? '下载失败'
  } finally {
    downloading.value = ''
  }
}
onMounted(load)
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h1 class="page-title">报告中心</h1>
        <div class="page-subtitle">已发布正式报告的检索、完整性校验与版本追溯</div>
      </div>
      <div class="page-actions">
        <button class="btn btn-secondary" :disabled="loading" @click="load">刷新</button>
      </div>
    </div>
    <div v-if="error" class="error">{{ error }}</div>

    <div class="card">
      <div class="toolbar">
        <input v-model="search" class="form-control" placeholder="搜索报告号、姓名或病历号…" />
        <select v-model="status" class="form-control" style="min-width:120px" @change="load">
          <option value="published">已发布</option>
          <option value="revoked">已撤销</option>
          <option value="all">全部状态</option>
        </select>
        <span class="toolbar-spacer" />
        <span class="muted" style="font-size:10px">共 {{ filtered.length }} 份</span>
      </div>
      <div v-if="loading" class="empty-state">正在加载报告…</div>
      <div v-else-if="!filtered.length" class="empty-state">
        <strong>没有符合条件的报告</strong>
        报告只能在医生复核并完成发布核对后生成。
      </div>
      <div v-else class="table-wrap">
        <table class="data-table">
          <thead><tr><th>报告编号</th><th>患者</th><th>版本</th><th>风险</th><th>状态</th><th>发布时间</th><th>完整性</th><th></th></tr></thead>
          <tbody>
            <tr v-for="r in filtered" :key="r.id" class="clickable" @click="router.push(`/reports/${r.id}`)">
              <td>
                <div class="primary-cell font-mono">{{ r.report_no }}</div>
                <div class="sub-cell">{{ r.id }}</div>
              </td>
              <td>
                <div>{{ r.patient_name }}</div>
                <div class="sub-cell font-mono">{{ r.mrn }}</div>
              </td>
              <td>v{{ r.version }}</td>
              <td>
                <span class="status" :class="riskClass(r.risk_level)">{{ r.risk_level || '人工审核' }}</span>
                <div v-if="r.probability != null" class="sub-cell">{{ (r.probability * 100).toFixed(1) }}%</div>
              </td>
              <td><span class="status" :class="`status-${r.status}`">{{ r.status === 'published' ? '已发布' : '已撤销' }}</span></td>
              <td>{{ fmt(r.published_at) }}</td>
              <td><span class="font-mono" style="font-size:9px">{{ r.sha256?.slice(0, 12) }}…</span></td>
              <td class="text-right" @click.stop>
                <button class="btn btn-sm btn-secondary" :disabled="downloading === r.id" @click="download(r)">PDF</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

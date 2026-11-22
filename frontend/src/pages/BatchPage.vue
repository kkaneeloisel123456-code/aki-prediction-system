<script setup lang="ts">
import { computed, ref } from 'vue'
import { api } from '../api/client'

const preview = ref<any>(null)
const result = ref<any>(null)
const busy = ref(false)
const error = ref('')
const fileName = ref('')

const validRows = computed(() => (preview.value?.rows ?? []).filter((r: any) => !r.errors.length))
const canCommit = computed(() => Boolean(validRows.value.length) && !preview.value?.header_errors?.length && !busy.value)

function fieldCount(row: any) { return Object.keys(row.values ?? {}).length }
function statusLabel(row: any) {
  if (row.errors?.length) return '不可导入'
  return row.patient_exists ? '关联已有档案' : '新建档案'
}
function statusClass(row: any) {
  if (row.errors?.length) return 'status-high'
  return row.patient_exists ? 'status-info' : 'status-active'
}

async function onFile(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  fileName.value = file.name
  preview.value = null
  result.value = null
  error.value = ''
  busy.value = true
  try {
    preview.value = await api.importPreview(file)
  } catch (err: any) {
    error.value = err?.message ?? '预览失败'
  } finally {
    busy.value = false
  }
}

async function commit() {
  if (!preview.value || !validRows.value.length) return
  if (!confirm(`将导入 ${validRows.value.length} 行有效数据并建立草稿就诊，是否继续？`)) return
  busy.value = true
  error.value = ''
  try {
    result.value = await api.importCommit({
      filename: preview.value.filename || fileName.value,
      rows: validRows.value,
    })
  } catch (e: any) {
    error.value = e?.message ?? '导入失败'
  } finally {
    busy.value = false
  }
}

function reset() {
  preview.value = null
  result.value = null
  fileName.value = ''
  error.value = ''
  const input = document.getElementById('import-file') as HTMLInputElement | null
  if (input) input.value = ''
}
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h1 class="page-title">批量导入</h1>
        <div class="page-subtitle">CSV 预览校验后写入真实患者档案与草稿就诊，支持逐行错误定位</div>
      </div>
      <div class="page-actions">
        <a href="/api/imports/template.csv" class="btn btn-secondary">下载导入模板</a>
        <button v-if="preview || result" class="btn btn-secondary" @click="reset">重新选择文件</button>
      </div>
    </div>
    <div v-if="error" class="error">{{ error }}</div>

    <div v-if="!preview && !result" class="card">
      <div class="card-header"><span class="card-title">选择 CSV 文件</span><span class="muted" style="font-size:10px">最大 5 MB · 最多 500 行</span></div>
      <div class="card-body">
        <div class="info-box">
          模板包含患者身份、就诊信息与 35 项模型指标。导入前会逐行校验病历号、时间、指标范围和档案权限；预览阶段不会写入数据库。
        </div>
        <label class="upload-zone" for="import-file" style="display:block">
          <div class="upload-zone-icon">⇪</div>
          <p><strong style="color:var(--text-bright)">点击选择 CSV 文件</strong></p>
          <div class="upload-hint">UTF-8 或 GBK 编码；首行必须为列名</div>
          <input id="import-file" type="file" accept=".csv,text/csv" style="display:none" :disabled="busy" @change="onFile" />
        </label>
        <div v-if="busy" class="muted mt-8">正在解析并校验 {{ fileName }} …</div>
      </div>
    </div>

    <div v-if="preview" class="card">
      <div class="card-header">
        <span class="card-title">预览结果 · {{ preview.filename }}</span>
        <span class="muted" style="font-size:10px">共 {{ preview.summary.total }} 行</span>
      </div>
      <div class="card-body">
        <div class="summary-strip" style="margin-bottom:14px">
          <div class="summary-item"><div class="label">有效行</div><div class="value" style="color:var(--green)">{{ preview.summary.valid }}</div></div>
          <div class="summary-item"><div class="label">错误行</div><div class="value" :style="{color: preview.summary.invalid ? 'var(--red)' : 'var(--text-dim)'}">{{ preview.summary.invalid }}</div></div>
          <div class="summary-item"><div class="label">新建档案</div><div class="value">{{ preview.summary.new_patients }}</div></div>
          <div class="summary-item"><div class="label">关联已有档案</div><div class="value">{{ preview.summary.existing_patients }}</div></div>
        </div>
        <div v-if="preview.ignored_headers?.length" class="muted" style="font-size:10px">已忽略列：{{ preview.ignored_headers.join('、') }}</div>
        <div v-for="msg in preview.header_errors" :key="msg" class="error mt-8">{{ msg }}</div>
        <div v-if="preview.header_errors?.length" class="warning-box mt-12">请修正表头后重新上传；当前文件不允许提交。</div>

        <div class="table-wrap mt-12" style="max-height:440px;overflow:auto">
          <table class="data-table">
            <thead><tr><th>行</th><th>病历号</th><th>姓名</th><th>就诊编号</th><th>发生时间</th><th>指标</th><th>档案处理</th><th>校验结果</th></tr></thead>
            <tbody>
              <tr v-for="row in preview.rows" :key="row.index">
                <td>{{ row.index }}</td>
                <td class="font-mono">{{ row.mrn || '—' }}</td>
                <td>{{ row.name || '—' }}</td>
                <td class="font-mono">{{ row.case_ref || '—' }}</td>
                <td>{{ row.occurred_at ? new Date(row.occurred_at).toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}) : '—' }}</td>
                <td>{{ fieldCount(row) }} 项</td>
                <td><span class="status" :class="statusClass(row)">{{ statusLabel(row) }}</span></td>
                <td class="wrap">
                  <div v-for="e in row.errors" :key="e" style="color:var(--red);font-size:10px">{{ e }}</div>
                  <div v-for="w in row.warnings" :key="w" style="color:var(--yellow);font-size:10px">{{ w }}</div>
                  <div v-if="!row.errors.length && !row.warnings.length" style="color:var(--green);font-size:10px">通过</div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <div class="modal-foot" style="position:static;border-top:1px solid var(--border)">
        <span class="muted" style="font-size:10px;margin-right:auto">仅导入无错误的 {{ validRows.length }} 行。导入后生成草稿就诊，仍需医生预测、复核与发布。</span>
        <button class="btn btn-primary" :disabled="!canCommit" @click="commit">{{ busy ? '导入中…' : `确认导入 ${validRows.length} 行` }}</button>
      </div>
    </div>

    <div v-if="result" class="card">
      <div class="card-header"><span class="card-title">导入完成 · 批次 {{ result.batch_id }}</span></div>
      <div class="card-body">
        <div class="summary-strip" style="margin-bottom:14px">
          <div class="summary-item"><div class="label">提交</div><div class="value">{{ result.total }}</div></div>
          <div class="summary-item"><div class="label">成功</div><div class="value" style="color:var(--green)">{{ result.imported }}</div></div>
          <div class="summary-item"><div class="label">失败</div><div class="value" :style="{color: result.failed ? 'var(--red)' : 'var(--text-dim)'}">{{ result.failed }}</div></div>
          <div class="summary-item"><div class="label">状态</div><div class="value" style="font-size:15px;color:var(--green)">已记录</div></div>
        </div>
        <div class="table-wrap">
          <table class="data-table">
            <thead><tr><th>行</th><th>结果</th><th>患者档案</th><th>草稿就诊</th></tr></thead>
            <tbody>
              <tr v-for="r in result.results" :key="r.index">
                <td>{{ r.index }}</td>
                <td><span class="status" :class="r.ok ? 'status-active' : 'status-high'">{{ r.ok ? '成功' : '失败' }}</span></td>
                <td class="font-mono">{{ r.patient_id || '—' }}</td>
                <td>
                  <RouterLink v-if="r.ok" :to="`/encounters/${r.encounter_id}`" class="btn btn-sm btn-secondary">进入接诊</RouterLink>
                  <span v-else style="color:var(--red);font-size:10px">{{ r.error }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="info-box mt-12">导入只建立草稿。请逐条进入接诊，完成指标确认、模型预测、医生复核与正式报告发布。</div>
      </div>
    </div>
  </div>
</template>

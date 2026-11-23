<script setup lang="ts">
import { computed, ref } from 'vue'
import { api } from '../api/client'

type Tone = 'neutral' | 'low' | 'mid' | 'high' | 'accent'

const preview = ref<any>(null)
const result = ref<any>(null)
const busy = ref(false)
const error = ref('')
const fileName = ref('')
const showCommit = ref(false)
const commitError = ref('')

const validRows = computed(() => (preview.value?.rows ?? []).filter((r: any) => !r.errors.length))
const canCommit = computed(() => Boolean(validRows.value.length) && !preview.value?.header_errors?.length && !busy.value)
const pageDescription = computed(() => {
  if (busy.value) return '正在解析并校验文件…'
  if (result.value) return `批次 ${result.value.batch_id} 已记录 · ${result.value.imported} 行进入草稿就诊`
  if (preview.value) return '预览通过后可提交；导入只建立草稿，不直接发布报告'
  return '用 CSV 建立患者档案与草稿就诊，逐行错误定位，不覆盖已有报告'
})
const previewSubtitle = computed(() => preview.value
  ? `${preview.value.filename || fileName.value} · 共 ${preview.value.summary?.total ?? preview.value.rows.length} 行`
  : '')
const validCount = computed(() => Number(preview.value?.summary?.valid ?? validRows.value.length))
const invalidCount = computed(() => Number(preview.value?.summary?.invalid ?? 0))

function fieldCount(row: any) { return Object.keys(row.values ?? {}).length }
function statusLabel(row: any) {
  if (row.errors?.length) return '不可导入'
  if (row.warnings?.length) return '有提示'
  return row.patient_exists ? '关联已有档案' : '新建档案'
}
function statusTone(row: any): Tone {
  if (row.errors?.length) return 'high'
  if (row.warnings?.length) return 'mid'
  return row.patient_exists ? 'accent' : 'low'
}
function fmt(value?: string) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}
function chooseFile() {
  (document.getElementById('import-file') as HTMLInputElement | null)?.click()
}
function onZoneKeydown(event: KeyboardEvent) {
  if (event.key !== 'Enter' && event.key !== ' ') return
  event.preventDefault()
  chooseFile()
}
function reset() {
  preview.value = null
  result.value = null
  fileName.value = ''
  error.value = ''
  commitError.value = ''
  showCommit.value = false
  const input = document.getElementById('import-file') as HTMLInputElement | null
  if (input) input.value = ''
}

async function onFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  await processFile(file)
}
async function onDrop(event: DragEvent) {
  const file = event.dataTransfer?.files?.[0]
  if (!file) return
  await processFile(file)
}
async function processFile(file: File) {
  fileName.value = file.name
  preview.value = null
  result.value = null
  error.value = ''
  commitError.value = ''
  busy.value = true
  try {
    preview.value = await api.importPreview(file)
  } catch (err: any) {
    error.value = err?.message ?? '预览失败'
  } finally {
    busy.value = false
  }
}

async function downloadTemplate() {
  error.value = ''
  try {
    const response = await fetch('/api/imports/template.csv', { credentials: 'include' })
    if (!response.ok) throw new Error('模板下载失败')
    const text = await response.text()
    const lines = text.split(/\r?\n/)
    if (lines[0] && !lines[0].includes('负责人ID')) {
      lines[0] = `${lines[0]},负责人ID`
      for (let index = 1; index < lines.length; index += 1) {
        if (lines[index].trim()) lines[index] = `${lines[index]},`
      }
    }
    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = 'AKI_import_template.csv'
    link.click()
    window.setTimeout(() => URL.revokeObjectURL(link.href), 1000)
  } catch (e: any) {
    error.value = e?.message ?? '模板下载失败'
  }
}

function askCommit() {
  if (!canCommit.value) return
  commitError.value = ''
  showCommit.value = true
}
async function confirmCommit() {
  if (!preview.value || !validRows.value.length) return
  busy.value = true
  commitError.value = ''
  try {
    result.value = await api.importCommit({
      filename: preview.value.filename || fileName.value,
      rows: validRows.value,
    })
    preview.value = null
    showCommit.value = false
  } catch (e: any) {
    commitError.value = e?.message ?? '导入失败'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="pilot-page">
    <div class="pilot-page-inner import-page">
      <PageHeader
        kicker="录入 / 批量导入"
        title="批量导入"
        :description="pageDescription"
      >
        <template #actions>
          <button class="pilot-btn" type="button" @click="downloadTemplate">下载导入模板</button>
          <button v-if="preview || result" class="pilot-btn" type="button" @click="reset">重新选择文件</button>
        </template>
      </PageHeader>

      <div v-if="error" class="pilot-error" role="alert">{{ error }}</div>

      <SectionPanel
        v-if="!preview && !result"
        title="选择导入文件"
        subtitle="最大 5 MB · 最多 500 行 · 预览阶段不写入数据库"
      >
        <div class="import-intro">
          <div class="import-intro-copy">
            <span class="pilot-section-label">导入范围</span>
            <strong>患者身份、就诊信息与模型指标</strong>
            <p>模板包含 35 项模型指标。导入前会逐行校验病历号、时间、指标范围与档案权限；提交后只建立草稿就诊，仍需医生预测、复核与发布。</p>
            <p>管理员导入新患者时，需在 CSV 中填写“负责人ID”（医生登录名）；医生导入时自动归属本人。</p>
          </div>
          <div class="import-format">
            <span class="import-format-mark">CSV</span>
            <span>UTF-8 或 GBK<br>首行必须为列名</span>
          </div>
        </div>

        <label
          class="import-zone"
          for="import-file"
          role="button"
          tabindex="0"
          :aria-busy="busy"
          @keydown="onZoneKeydown"
          @dragover.prevent
          @dragenter.prevent
          @drop.prevent="onDrop"
        >
          <span class="import-zone-mark">CSV</span>
          <span class="import-zone-copy">
            <strong>{{ busy ? `正在解析 ${fileName} …` : '选择 CSV 文件' }}</strong>
            <span>点击浏览，或把文件拖到这里后选择</span>
          </span>
          <span class="import-zone-action">浏览文件</span>
          <input id="import-file" type="file" accept=".csv,text/csv" class="import-file-input" :disabled="busy" @change="onFile" />
        </label>
        <p class="import-zone-hint">文件只用于预览校验，不会在预览阶段写入数据库。</p>
      </SectionPanel>

      <SectionPanel
        v-if="preview"
        title="预览结果"
        :subtitle="previewSubtitle"
        flush
      >
        <template #actions>
          <button class="pilot-btn pilot-btn-sm" type="button" @click="reset">清除预览</button>
        </template>
        <div class="import-body">
          <div class="import-summary">
            <div class="import-summary-cell"><span>有效行</span><strong class="is-low">{{ preview.summary?.valid ?? validRows.length }}</strong><small>可提交导入</small></div>
            <div class="import-summary-cell"><span>错误行</span><strong :class="invalidCount ? 'is-high' : 'is-muted'">{{ invalidCount }}</strong><small>{{ invalidCount ? '需修正后重传' : '没有错误' }}</small></div>
            <div class="import-summary-cell"><span>新建档案</span><strong>{{ preview.summary?.new_patients ?? 0 }}</strong><small>将创建患者档案</small></div>
            <div class="import-summary-cell"><span>关联已有档案</span><strong>{{ preview.summary?.existing_patients ?? 0 }}</strong><small>按病历号匹配</small></div>
          </div>

          <div v-if="preview.ignored_headers?.length" class="import-note">已忽略列：{{ preview.ignored_headers.join('、') }}</div>
          <div v-for="msg in preview.header_errors" :key="msg" class="pilot-error import-alert" role="alert">{{ msg }}</div>
          <div v-if="preview.header_errors?.length" class="import-alert import-alert-warn">
            请修正表头后重新上传；当前文件不允许提交。
          </div>

          <div class="import-table-scroll" role="region" aria-label="导入预览表格，窄屏可横向滚动" tabindex="0">
            <div class="import-mobile-hint">左右滑动查看完整表格</div>
            <table class="pilot-table import-table">
              <thead>
                <tr>
                  <th scope="col">行</th>
                  <th scope="col">病历号</th>
                  <th scope="col">姓名</th>
                  <th scope="col">就诊编号</th>
                  <th scope="col">发生时间</th>
                  <th scope="col">指标</th>
                  <th scope="col">档案处理</th>
                  <th scope="col">校验结果</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in preview.rows" :key="row.index">
                  <td class="pilot-mono">{{ row.index }}</td>
                  <td class="pilot-mono">{{ row.mrn || '—' }}</td>
                  <td class="cell-strong">{{ row.name || '—' }}</td>
                  <td class="pilot-mono">{{ row.case_ref || '—' }}</td>
                  <td>{{ fmt(row.occurred_at) }}</td>
                  <td>{{ fieldCount(row) }} 项</td>
                  <td><StatusPill :label="statusLabel(row)" :tone="statusTone(row)" /></td>
                  <td class="import-issues">
                    <div v-for="e in row.errors" :key="e" class="import-issue is-high">{{ e }}</div>
                    <div v-for="w in row.warnings" :key="w" class="import-issue is-mid">{{ w }}</div>
                    <span v-if="!row.errors.length && !row.warnings.length" class="import-pass">通过</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <template #footer>
          <div class="import-footer">
            <span class="pilot-small">仅导入无错误的 {{ validCount }} 行。导入后生成草稿就诊，仍需医生预测、复核与发布。</span>
            <button class="pilot-btn pilot-btn-primary" type="button" :disabled="!canCommit" @click="askCommit">
              确认导入 {{ validCount }} 行
            </button>
          </div>
        </template>
      </SectionPanel>

      <SectionPanel
        v-if="result"
        :title="`导入完成 · 批次 ${result.batch_id}`"
        subtitle="批次结果已写入审计日志；失败行未创建档案或就诊。"
        flush
      >
        <div class="import-body">
          <div class="import-summary is-result">
            <div class="import-summary-cell"><span>提交</span><strong>{{ result.total }}</strong><small>本次提交行数</small></div>
            <div class="import-summary-cell"><span>成功</span><strong class="is-low">{{ result.imported }}</strong><small>已建立草稿就诊</small></div>
            <div class="import-summary-cell"><span>失败</span><strong :class="result.failed ? 'is-high' : 'is-muted'">{{ result.failed }}</strong><small>{{ result.failed ? '查看失败原因' : '没有失败行' }}</small></div>
            <div class="import-summary-cell"><span>状态</span><strong class="is-low">已记录</strong><small>等待医生接诊</small></div>
          </div>

          <div class="import-table-scroll" role="region" aria-label="导入结果表格，窄屏可横向滚动" tabindex="0">
            <div class="import-mobile-hint">左右滑动查看完整表格</div>
            <table class="pilot-table import-table import-result-table">
              <thead>
                <tr><th scope="col">行</th><th scope="col">结果</th><th scope="col">患者档案</th><th scope="col">草稿就诊</th></tr>
              </thead>
              <tbody>
                <tr v-for="r in result.results" :key="r.index">
                  <td class="pilot-mono">{{ r.index }}</td>
                  <td><StatusPill :label="r.ok ? '成功' : '失败'" :tone="r.ok ? 'low' : 'high'" /></td>
                  <td class="pilot-mono">{{ r.patient_id || '—' }}</td>
                  <td>
                    <RouterLink v-if="r.ok" :to="`/encounters/${r.encounter_id}`" class="pilot-link">进入接诊 →</RouterLink>
                    <span v-else class="import-issue is-high">{{ r.error }}</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="import-note">导入只建立草稿。请逐条进入接诊，完成指标确认、模型预测、医生复核与正式报告发布。</div>
        </div>
      </SectionPanel>

      <ElDialog
        v-model="showCommit"
        title="确认导入"
        width="520px"
        class="pilot-dialog"
        :close-on-click-modal="false"
        append-to-body
      >
        <p class="import-confirm-copy">将导入 {{ validCount }} 行有效数据并建立草稿就诊。预览阶段未写入的档案与就诊会在提交后写入数据库。</p>
        <div class="import-confirm-meta">
          <div><span>文件</span><strong>{{ preview?.filename || fileName }}</strong></div>
          <div><span>有效行</span><strong>{{ validCount }}</strong></div>
          <div><span>错误行</span><strong>{{ invalidCount }}</strong></div>
        </div>
        <div v-if="commitError" class="pilot-error import-alert" role="alert">{{ commitError }}</div>
        <template #footer>
          <div class="dialog-actions">
            <button class="pilot-btn" type="button" @click="showCommit = false">取消</button>
            <button class="pilot-btn pilot-btn-primary" type="button" :disabled="busy" @click="confirmCommit">
              {{ busy ? '导入中…' : `确认导入 ${validCount} 行` }}
            </button>
          </div>
        </template>
      </ElDialog>
    </div>
  </div>
</template>

<style scoped>
.import-page { max-width: 1240px; }
.import-intro {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--pilot-space-5);
  padding-bottom: var(--pilot-space-5);
  border-bottom: 1px dashed var(--pilot-line);
}
.import-intro-copy { display: flex; flex-direction: column; gap: var(--pilot-space-1); max-width: 680px; }
.import-intro-copy strong { color: var(--pilot-ink); font-size: var(--pilot-font-md); }
.import-intro-copy p { margin: var(--pilot-space-1) 0 0; color: var(--pilot-muted); font-size: var(--pilot-font-sm); line-height: 1.6; }
.import-format {
  display: flex;
  align-items: center;
  gap: var(--pilot-space-2);
  flex: 0 0 auto;
  color: var(--pilot-muted);
  font-size: var(--pilot-font-xs);
  line-height: 1.5;
}
.import-format-mark {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  border: 1px solid var(--pilot-line-strong);
  border-radius: var(--pilot-radius-control);
  color: var(--pilot-accent);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 11px;
  font-weight: 700;
}
.import-zone {
  display: flex;
  align-items: center;
  gap: var(--pilot-space-4);
  margin-top: var(--pilot-space-5);
  padding: var(--pilot-space-5);
  border: 1px dashed var(--pilot-line-strong);
  border-radius: var(--pilot-radius-card);
  background: var(--pilot-surface-2);
  cursor: pointer;
  transition: border-color .15s, background .15s;
}
.import-zone:hover,
.import-zone:focus-visible { border-color: var(--pilot-accent); background: var(--pilot-accent-soft); outline: none; }
.import-zone-mark {
  display: grid;
  place-items: center;
  width: 52px;
  height: 52px;
  border: 1px solid var(--pilot-line-strong);
  border-radius: var(--pilot-radius-control);
  background: var(--pilot-surface);
  color: var(--pilot-accent);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 12px;
  font-weight: 700;
}
.import-zone-copy { display: flex; flex-direction: column; gap: var(--pilot-space-1); flex: 1; min-width: 0; }
.import-zone-copy strong { color: var(--pilot-ink); font-size: var(--pilot-font-md); }
.import-zone-copy span { color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
.import-zone-action { color: var(--pilot-accent); font-size: var(--pilot-font-sm); font-weight: 600; white-space: nowrap; }
.import-file-input { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.import-zone-hint { margin: var(--pilot-space-2) 0 0; color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
.import-body { padding: var(--pilot-space-4); }
.import-summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: var(--pilot-space-2); margin-bottom: var(--pilot-space-4); }
.import-summary-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--pilot-space-3) var(--pilot-space-4);
  border: 1px solid var(--pilot-line);
  border-radius: var(--pilot-radius-control);
  background: var(--pilot-surface-2);
}
.import-summary-cell > span { color: var(--pilot-muted); font-size: var(--pilot-font-xs); font-weight: 600; }
.import-summary-cell > strong { color: var(--pilot-ink); font-size: var(--pilot-font-xl); font-weight: 700; line-height: 1.2; }
.import-summary-cell > small { color: var(--pilot-muted); font-size: 11px; }
.import-summary-cell > strong.is-low { color: var(--pilot-low); }
.import-summary-cell > strong.is-high { color: var(--pilot-high); }
.import-summary-cell > strong.is-muted { color: var(--pilot-muted); }
.import-note { margin: var(--pilot-space-3) 0 0; color: var(--pilot-muted); font-size: var(--pilot-font-xs); line-height: 1.6; }
.import-alert { margin: var(--pilot-space-3) 0 0; }
.import-alert-warn {
  padding: var(--pilot-space-3) var(--pilot-space-4);
  border: 1px solid var(--pilot-mid);
  border-radius: var(--pilot-radius-control);
  background: var(--pilot-mid-soft);
  color: var(--pilot-mid);
  font-size: var(--pilot-font-sm);
}
.import-table-scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; }
.import-mobile-hint { display: none; }
.import-table { min-width: 980px; }
.import-result-table { min-width: 640px; }
.import-issues { min-width: 220px; }
.import-issue { font-size: var(--pilot-font-xs); line-height: 1.55; overflow-wrap: anywhere; }
.import-issue.is-high { color: var(--pilot-high); }
.import-issue.is-mid { color: var(--pilot-mid); }
.import-pass { color: var(--pilot-low); font-size: var(--pilot-font-xs); font-weight: 600; }
.import-footer { display: flex; align-items: center; justify-content: space-between; gap: var(--pilot-space-4); }
.import-confirm-copy { margin: 0 0 var(--pilot-space-4); color: var(--pilot-ink-soft); line-height: 1.6; }
.import-confirm-meta { display: grid; gap: var(--pilot-space-2); margin-bottom: var(--pilot-space-4); padding: var(--pilot-space-3) var(--pilot-space-4); border: 1px solid var(--pilot-line); background: var(--pilot-surface-2); border-radius: var(--pilot-radius-control); }
.import-confirm-meta > div { display: flex; justify-content: space-between; gap: var(--pilot-space-4); font-size: var(--pilot-font-sm); }
.import-confirm-meta span { color: var(--pilot-muted); }
.import-confirm-meta strong { color: var(--pilot-ink); overflow-wrap: anywhere; text-align: right; }
.dialog-actions { display: flex; justify-content: flex-end; gap: var(--pilot-space-2); }

@media (max-width: 800px) {
  .import-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .import-intro { flex-direction: column; }
  .import-zone { align-items: flex-start; flex-wrap: wrap; }
  .import-zone-copy { flex-basis: calc(100% - 68px); }
  .import-zone-action { margin-left: 68px; }
  .import-footer { align-items: flex-start; flex-direction: column; }
}
@media (max-width: 650px) {
  .import-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .import-zone { padding: var(--pilot-space-4); }
  .import-zone-action { margin-left: 0; }
  .import-mobile-hint {
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

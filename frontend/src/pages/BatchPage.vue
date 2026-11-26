<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { api, saveBlob } from '../api/client'

type Tone = 'neutral' | 'low' | 'mid' | 'high' | 'accent'

const preview = ref<any>(null)
const result = ref<any>(null)
const busy = ref(false)
const error = ref('')
const fileName = ref('')
const currentFile = ref<File | null>(null)
const sheetNames = ref<string[]>([])
const needsSheet = ref(false)
const selectedSheet = ref('')
const showCommit = ref(false)
const commitError = ref('')
const mappingOpen = ref(false)
const mappingDraft = reactive<Record<string, string>>({})

const validRows = computed(() => (preview.value?.rows ?? []).filter((r: any) => !r.errors.length))
const validCount = computed(() => Number(preview.value?.summary?.valid ?? validRows.value.length))
const invalidCount = computed(() => Number(preview.value?.summary?.invalid ?? 0))
const canCommit = computed(() => Boolean(preview.value?.batch_id && validRows.value.length) && !preview.value?.header_errors?.length && !busy.value)
const pageDescription = computed(() => {
  if (busy.value) return '正在解析并校验文件…'
  if (result.value) return `批次 ${result.value.batch_id} 已记录 · ${result.value.imported} 行进入草稿就诊`
  if (preview.value) return '核对映射和错误行后，按批次号提交；导入只建立草稿，不直接发布报告'
  return '支持 XLSX / CSV，多工作表手选、列映射和错误行导出；导入只建立草稿'
})
const previewSubtitle = computed(() => {
  if (!preview.value) return ''
  const sheet = preview.value.sheet_name ? ` · 工作表 ${preview.value.sheet_name}` : ''
  return `${preview.value.filename || fileName.value}${sheet} · 共 ${preview.value.summary?.total ?? preview.value.rows.length} 行`
})
const mappingGroups = computed(() => {
  const groups = ['患者信息', '就诊信息', '模型指标']
  const options = preview.value?.field_options ?? []
  return groups
    .map((label) => ({ label, options: options.filter((option: any) => option.group === label) }))
    .filter((group) => group.options.length)
})
const mappingStats = computed(() => {
  const columns = preview.value?.columns ?? {}
  const mapped = Object.values(columns).filter((value) => value && value !== '__ignore__').length
  return { mapped, ignored: Object.keys(columns).length - mapped }
})
const formatLabel = computed(() => preview.value?.file_type === 'xlsx' ? 'XLSX' : 'CSV')

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
function clearMapping() {
  for (const key of Object.keys(mappingDraft)) delete mappingDraft[key]
}
function loadMapping(columns: Record<string, string>) {
  clearMapping()
  for (const header of preview.value?.headers ?? []) {
    mappingDraft[header] = columns?.[header] || '__ignore__'
  }
}
function reset() {
  preview.value = null
  result.value = null
  fileName.value = ''
  currentFile.value = null
  sheetNames.value = []
  needsSheet.value = false
  selectedSheet.value = ''
  error.value = ''
  commitError.value = ''
  showCommit.value = false
  mappingOpen.value = false
  clearMapping()
  const input = document.getElementById('import-file') as HTMLInputElement | null
  if (input) input.value = ''
}

async function onFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  await handleFile(file)
}
async function onDrop(event: DragEvent) {
  const file = event.dataTransfer?.files?.[0]
  if (!file) return
  await handleFile(file)
}
async function handleFile(file: File) {
  currentFile.value = file
  fileName.value = file.name
  preview.value = null
  result.value = null
  error.value = ''
  commitError.value = ''
  showCommit.value = false
  sheetNames.value = []
  needsSheet.value = false
  selectedSheet.value = ''
  clearMapping()
  await processFile(file)
}

async function processFile(file: File, options: { sheet_name?: string; mapping?: Record<string, string> } = {}) {
  busy.value = true
  error.value = ''
  commitError.value = ''
  try {
    const res = await api.importPreview(file, options)
    if (res.requires_sheet) {
      preview.value = null
      needsSheet.value = true
      sheetNames.value = res.sheet_names ?? []
      selectedSheet.value = ''
      return
    }
    needsSheet.value = false
    preview.value = res
    selectedSheet.value = res.sheet_name || options.sheet_name || ''
    loadMapping(res.columns ?? {})
  } catch (err: any) {
    preview.value = null
    error.value = err?.message ?? '预览失败'
  } finally {
    busy.value = false
  }
}

async function chooseSheet(name: string) {
  if (!currentFile.value) return
  selectedSheet.value = name
  needsSheet.value = false
  await processFile(currentFile.value, { sheet_name: name })
}

function openMapping() {
  if (!preview.value) return
  loadMapping(preview.value.columns ?? {})
  mappingOpen.value = true
}

async function applyMapping() {
  if (!currentFile.value || !preview.value) return
  const mapping = { ...mappingDraft }
  mappingOpen.value = false
  await processFile(currentFile.value, {
    sheet_name: selectedSheet.value || preview.value.sheet_name || '',
    mapping,
  })
}

async function downloadTemplate() {
  error.value = ''
  try {
    const response = await fetch('/api/imports/template.xlsx', { credentials: 'same-origin' })
    if (!response.ok) throw new Error('模板下载失败')
    saveBlob(await response.blob(), 'AKI_import_template.xlsx')
  } catch (e: any) {
    error.value = e?.message ?? '模板下载失败'
  }
}

async function downloadErrors() {
  if (!preview.value?.batch_id) return
  error.value = ''
  try {
    const blob = await api.importErrors(preview.value.batch_id)
    saveBlob(blob, `AKI_import_errors_${preview.value.batch_id}.xlsx`)
  } catch (e: any) {
    error.value = e?.message ?? '错误行导出失败'
  }
}

function askCommit() {
  if (!canCommit.value) return
  commitError.value = ''
  showCommit.value = true
}
async function confirmCommit() {
  if (!preview.value?.batch_id) return
  busy.value = true
  commitError.value = ''
  try {
    result.value = await api.importCommit({ batch_id: preview.value.batch_id })
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
          <RouterLink to="/patients" class="pilot-btn">← 患者档案</RouterLink>
          <button class="pilot-btn" type="button" @click="downloadTemplate">下载 XLSX 模板</button>
          <button v-if="currentFile || preview || result || needsSheet" class="pilot-btn" type="button" @click="reset">重新选择文件</button>
        </template>
      </PageHeader>

      <div v-if="error" class="pilot-error" role="alert">{{ error }}</div>

      <SectionPanel
        v-if="!preview && !result && !needsSheet"
        title="选择导入文件"
        subtitle="最大 5 MB · 最多 500 行 · 预览阶段不写入数据库"
      >
        <div class="import-intro">
          <div class="import-intro-copy">
            <span class="pilot-section-label">导入范围</span>
            <strong>患者身份、就诊信息与模型指标</strong>
            <p>支持 XLSX 与 CSV。XLSX 有多个工作表时必须先选数据表；导入前可改列映射，逐行校验病历号、时间、指标范围与档案权限。</p>
            <p>管理员导入新患者时需填写“负责人ID”（医生登录名）；医生导入时只能归属本人。提交只建立草稿就诊，仍需预测、复核与发布。</p>
          </div>
          <div class="import-format">
            <span class="import-format-mark">XLSX</span>
            <span>XLSX / CSV<br>首行必须为列名</span>
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
          <span class="import-zone-mark">XLSX</span>
          <span class="import-zone-copy">
            <strong>{{ busy ? `正在解析 ${fileName} …` : '选择 XLSX 或 CSV 文件' }}</strong>
            <span>点击浏览，或把文件拖到这里后选择</span>
          </span>
          <span class="import-zone-action">浏览文件</span>
          <input id="import-file" type="file" accept=".xlsx,.xlsm,.csv" class="import-file-input" :disabled="busy" @change="onFile" />
        </label>
        <p class="import-zone-hint">文件只用于预览校验，不会在预览阶段写入数据库。</p>
      </SectionPanel>

      <SectionPanel
        v-if="needsSheet && !preview"
        title="选择工作表"
        :subtitle="`${fileName} 包含多个工作表，请选择一个作为导入数据表`"
      >
        <div class="sheet-choice-list">
          <button
            v-for="name in sheetNames"
            :key="name"
            class="sheet-choice"
            type="button"
            :disabled="busy"
            @click="chooseSheet(name)"
          >
            <span class="sheet-choice-name">{{ name }}</span>
            <span class="sheet-choice-arrow">读取此表 →</span>
          </button>
        </div>
        <p class="import-zone-hint">未选中的工作表不会参与解析，也不会写入数据库。</p>
      </SectionPanel>

      <SectionPanel
        v-if="preview"
        title="预览结果"
        :subtitle="previewSubtitle"
        flush
      >
        <template #actions>
          <button class="pilot-btn pilot-btn-sm" type="button" @click="openMapping">编辑列映射</button>
          <button v-if="invalidCount" class="pilot-btn pilot-btn-sm" type="button" @click="downloadErrors">导出错误行</button>
          <button class="pilot-btn pilot-btn-sm" type="button" @click="reset">清除预览</button>
        </template>
        <div class="import-body">
          <div class="import-summary">
            <div class="import-summary-cell"><span>有效行</span><strong class="is-low">{{ validCount }}</strong><small>可提交导入</small></div>
            <div class="import-summary-cell"><span>错误行</span><strong :class="invalidCount ? 'is-high' : 'is-muted'">{{ invalidCount }}</strong><small>{{ invalidCount ? '可导出后修正重传' : '没有错误' }}</small></div>
            <div class="import-summary-cell"><span>新建档案</span><strong>{{ preview.summary?.new_patients ?? 0 }}</strong><small>将创建患者档案</small></div>
            <div class="import-summary-cell"><span>关联已有档案</span><strong>{{ preview.summary?.existing_patients ?? 0 }}</strong><small>按病历号匹配</small></div>
          </div>

          <div class="import-file-meta">
            <span><span class="pilot-section-label">文件</span> {{ preview.filename || fileName }}</span>
            <span><span class="pilot-section-label">格式</span> {{ formatLabel }}</span>
            <span v-if="preview.sheet_name"><span class="pilot-section-label">工作表</span> {{ preview.sheet_name }}</span>
            <span class="pilot-mono"><span class="pilot-section-label">批次</span> {{ preview.batch_id }}</span>
          </div>

          <div class="import-mapping-strip">
            <div>
              <span class="pilot-section-label">列映射</span>
              <strong>{{ mappingStats.mapped }} 列已映射</strong>
              <span v-if="mappingStats.ignored" class="pilot-muted"> · {{ mappingStats.ignored }} 列忽略</span>
            </div>
            <button class="pilot-btn pilot-btn-sm" type="button" @click="openMapping">调整映射</button>
          </div>

          <div v-for="msg in preview.header_errors" :key="msg" class="pilot-error import-alert" role="alert">{{ msg }}</div>
          <div v-if="preview.header_errors?.length" class="import-alert import-alert-warn">
            请修正列映射后重新校验；当前批次不允许提交。
          </div>
          <div v-for="msg in preview.header_warnings" :key="msg" class="import-note">{{ msg }}</div>

          <div class="import-table-scroll" role="region" aria-label="导入预览表格，窄屏可横向滚动" tabindex="0">
            <div class="import-mobile-hint">左右滑动查看完整表格</div>
            <table class="pilot-table import-table">
              <thead>
                <tr>
                  <th scope="col">行</th>
                  <th scope="col">病历号</th>
                  <th scope="col">姓名</th>
                  <th scope="col">性别</th>
                  <th scope="col">出生日期</th>
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
                  <td>{{ row.sex || '—' }}</td>
                  <td class="pilot-mono">{{ row.birth_date || row.birth_year || '—' }}</td>
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
            <span class="pilot-small">提交时只发送批次号 {{ preview.batch_id }}。仅导入无错误的 {{ validCount }} 行；导入后生成草稿就诊，仍需医生预测、复核与发布。</span>
            <div class="import-footer-actions">
              <button v-if="invalidCount" class="pilot-btn" type="button" @click="downloadErrors">导出错误行</button>
              <button class="pilot-btn pilot-btn-primary" type="button" :disabled="!canCommit" @click="askCommit">
                确认导入 {{ validCount }} 行
              </button>
            </div>
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
        v-model="mappingOpen"
        title="列映射"
        width="760px"
        class="pilot-dialog mapping-dialog"
        :close-on-click-modal="false"
        append-to-body
      >
        <div class="mapping-copy">
          <p>源文件列已自动匹配，可在这里改为患者字段、就诊字段或 35 项模型指标。未映射列会被忽略，不影响导入。</p>
          <span class="pilot-muted">当前 {{ mappingStats.mapped }} 列已映射 · {{ mappingStats.ignored }} 列忽略</span>
        </div>
        <div class="mapping-table-scroll">
          <table class="pilot-table mapping-table">
            <thead>
              <tr><th scope="col">源列</th><th scope="col">示例值</th><th scope="col">导入字段</th></tr>
            </thead>
            <tbody>
              <tr v-for="header in preview?.headers ?? []" :key="header">
                <td class="cell-strong">{{ header }}</td>
                <td class="pilot-mono mapping-sample">{{ preview?.samples?.[header] || '—' }}</td>
                <td>
                  <select v-model="mappingDraft[header]" class="pilot-select mapping-select">
                    <option value="__ignore__">忽略此列</option>
                    <optgroup v-for="group in mappingGroups" :key="group.label" :label="group.label">
                      <option v-for="option in group.options" :key="option.value" :value="option.value">{{ option.label }}</option>
                    </optgroup>
                  </select>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <template #footer>
          <div class="dialog-actions">
            <button class="pilot-btn" type="button" @click="mappingOpen = false">取消</button>
            <button class="pilot-btn pilot-btn-primary" type="button" :disabled="busy" @click="applyMapping">
              {{ busy ? '重新校验中…' : '应用映射并重新校验' }}
            </button>
          </div>
        </template>
      </ElDialog>

      <ElDialog
        v-model="showCommit"
        title="确认导入"
        width="520px"
        class="pilot-dialog"
        :close-on-click-modal="false"
        append-to-body
      >
        <p class="import-confirm-copy">将按批次 <b class="pilot-mono">{{ preview?.batch_id }}</b> 提交 {{ validCount }} 行有效数据，并建立草稿就诊。预览阶段未写入的档案与就诊会在提交后写入数据库。</p>
        <div class="import-confirm-meta">
          <div><span>文件</span><strong>{{ preview?.filename || fileName }}</strong></div>
          <div v-if="preview?.sheet_name"><span>工作表</span><strong>{{ preview.sheet_name }}</strong></div>
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
  width: 46px;
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
  font-size: 11px;
  font-weight: 700;
}
.import-zone-copy { display: flex; flex-direction: column; gap: var(--pilot-space-1); flex: 1; min-width: 0; }
.import-zone-copy strong { color: var(--pilot-ink); font-size: var(--pilot-font-md); }
.import-zone-copy span { color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
.import-zone-action { color: var(--pilot-accent); font-size: var(--pilot-font-sm); font-weight: 600; white-space: nowrap; }
.import-file-input { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
.import-zone-hint { margin: var(--pilot-space-2) 0 0; color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
.import-body { padding: var(--pilot-space-4); }
.import-summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: var(--pilot-space-2); margin-bottom: var(--pilot-space-3); }
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
.import-file-meta { display: flex; flex-wrap: wrap; gap: var(--pilot-space-2) var(--pilot-space-4); margin-bottom: var(--pilot-space-3); color: var(--pilot-ink-soft); font-size: var(--pilot-font-xs); }
.import-file-meta > span { display: inline-flex; align-items: center; gap: var(--pilot-space-1); min-width: 0; overflow-wrap: anywhere; }
.import-mapping-strip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--pilot-space-3);
  margin-bottom: var(--pilot-space-3);
  padding: var(--pilot-space-2) var(--pilot-space-3);
  border: 1px solid var(--pilot-line);
  border-radius: var(--pilot-radius-control);
  background: var(--pilot-surface-2);
  color: var(--pilot-muted);
  font-size: var(--pilot-font-xs);
}
.import-mapping-strip strong { color: var(--pilot-ink); font-size: var(--pilot-font-sm); }
.import-note { margin: var(--pilot-space-2) 0 0; color: var(--pilot-muted); font-size: var(--pilot-font-xs); line-height: 1.6; }
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
.import-footer-actions { display: flex; align-items: center; gap: var(--pilot-space-2); flex-shrink: 0; }
.import-confirm-copy { margin: 0 0 var(--pilot-space-4); color: var(--pilot-ink-soft); line-height: 1.6; }
.import-confirm-meta { display: grid; gap: var(--pilot-space-2); margin-bottom: var(--pilot-space-4); padding: var(--pilot-space-3) var(--pilot-space-4); border: 1px solid var(--pilot-line); background: var(--pilot-surface-2); border-radius: var(--pilot-radius-control); }
.import-confirm-meta > div { display: flex; justify-content: space-between; gap: var(--pilot-space-4); font-size: var(--pilot-font-sm); }
.import-confirm-meta span { color: var(--pilot-muted); }
.import-confirm-meta strong { color: var(--pilot-ink); overflow-wrap: anywhere; text-align: right; }
.dialog-actions { display: flex; justify-content: flex-end; gap: var(--pilot-space-2); }

.sheet-choice-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--pilot-space-3); }
.sheet-choice {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--pilot-space-3);
  min-height: 64px;
  padding: var(--pilot-space-3) var(--pilot-space-4);
  border: 1px solid var(--pilot-line);
  border-radius: var(--pilot-radius-control);
  background: var(--pilot-surface-2);
  color: var(--pilot-ink);
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.sheet-choice:hover,
.sheet-choice:focus-visible { border-color: var(--pilot-accent); background: var(--pilot-accent-soft); outline: none; }
.sheet-choice-name { font-weight: 700; overflow-wrap: anywhere; }
.sheet-choice-arrow { color: var(--pilot-accent); font-size: var(--pilot-font-xs); white-space: nowrap; }

.mapping-copy { margin-bottom: var(--pilot-space-3); color: var(--pilot-ink-soft); font-size: var(--pilot-font-sm); line-height: 1.6; }
.mapping-copy p { margin: 0 0 var(--pilot-space-1); }
.mapping-table-scroll { max-height: 52vh; overflow: auto; border: 1px solid var(--pilot-line); border-radius: var(--pilot-radius-control); }
.mapping-table { min-width: 0; }
.mapping-table th { position: sticky; top: 0; z-index: 1; }
.mapping-table td { padding: var(--pilot-space-2) var(--pilot-space-3); }
.mapping-sample { max-width: 180px; overflow: hidden; color: var(--pilot-muted); text-overflow: ellipsis; white-space: nowrap; }
.mapping-select { width: 100%; min-width: 190px; }

@media (max-width: 800px) {
  .import-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .import-intro { flex-direction: column; }
  .import-zone { align-items: flex-start; flex-wrap: wrap; }
  .import-zone-copy { flex-basis: calc(100% - 68px); }
  .import-zone-action { margin-left: 68px; }
  .import-footer { align-items: flex-start; flex-direction: column; }
  .import-footer-actions { width: 100%; justify-content: flex-end; }
  .sheet-choice-list { grid-template-columns: 1fr; }
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
  .mapping-dialog { width: calc(100vw - 24px) !important; }
}
</style>

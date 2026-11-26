<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api, saveBlob } from '../api/client'

type Tone = 'neutral' | 'low' | 'mid' | 'high' | 'accent'

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

const statusName = computed(() => {
  const names: Record<string, string> = { published: '已发布', revoked: '已撤销', all: '全部状态' }
  return names[status.value] ?? '已发布'
})

const subtitle = computed(() => loading.value
  ? '读取报告索引…'
  : `${filtered.value.length} 份 · ${statusName.value}${search.value.trim() ? ' · 已筛选' : ''}`)

const empty = computed(() => {
  if (search.value.trim()) {
    return {
      title: '没有匹配的报告',
      description: '换一个报告编号、患者姓名或病历号再试，也可以清除搜索查看完整列表。',
    }
  }
  if (status.value === 'revoked') {
    return {
      title: '没有已撤销报告',
      description: '管理员撤销正式报告后，记录会保留在这里，并显示撤销时间和原因。',
    }
  }
  if (status.value === 'all') {
    return {
      title: '还没有正式报告',
      description: '完成首份报告的复核与发布核对后，这里会保留所有版本和状态。',
    }
  }
  return {
    title: '还没有已发布报告',
    description: '报告需要在接诊页完成医生复核与发布核对后生成；未发布记录不会出现在这里。',
  }
})

function riskLabel(level?: string) {
  if (!level) return '未评估'
  return level === '人工审核' ? '人工审核' : `${level}风险`
}
function riskTone(level?: string): Tone {
  if (level === '高') return 'high'
  if (level === '中') return 'mid'
  if (level === '低') return 'low'
  return 'neutral'
}
function statusLabel(value?: string) {
  return value === 'revoked' ? '已撤销' : '已发布'
}
function statusTone(value?: string): Tone {
  return value === 'revoked' ? 'high' : 'accent'
}
function hasProbability(value: any) {
  return value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value))
}
function pct(value: any) {
  return `${(Number(value) * 100).toFixed(1)}%`
}
function fmt(value?: string) {
  if (!value) return '—'
  const d = new Date(value)
  return Number.isNaN(d.getTime())
    ? value
    : d.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}
function setStatus(next: string) {
  status.value = next
  void load()
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
  error.value = ''
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
  <div class="pilot-page">
    <div class="pilot-page-inner">
      <PageHeader
        kicker="临床工作"
        title="评估报告"
        description="已发布正式报告的检索、版本追溯与文件下载。撤销记录由管理员操作并保留原因。"
      >
        <template #actions>
          <button class="pilot-btn" type="button" :disabled="loading" @click="load">刷新</button>
        </template>
      </PageHeader>

      <div v-if="error" class="pilot-error" role="alert">{{ error }}</div>

      <SectionPanel title="正式报告" :subtitle="subtitle" flush>
        <div class="report-toolbar">
          <input
            v-model="search"
            class="pilot-input report-search"
            type="search"
            aria-label="搜索报告编号、患者姓名或病历号"
            placeholder="搜索报告编号、患者姓名或病历号"
          >
          <select
            v-model="status"
            class="pilot-select report-status-filter"
            aria-label="报告状态"
            @change="load"
          >
            <option value="published">已发布</option>
            <option value="revoked">已撤销</option>
            <option value="all">全部状态</option>
          </select>
          <span class="report-count pilot-small">共 {{ filtered.length }} 份</span>
        </div>

        <div v-if="loading" class="report-loading" aria-label="正在加载报告">
          <div v-for="i in 4" :key="i" class="pilot-skeleton report-skeleton-row" />
        </div>

        <EmptyState
          v-else-if="!filtered.length"
          :title="empty.title"
          :description="empty.description"
        >
          <button v-if="search.trim()" class="pilot-btn" type="button" @click="search = ''">清除搜索</button>
          <button
            v-else-if="status === 'revoked'"
            class="pilot-btn"
            type="button"
            @click="setStatus('published')"
          >查看已发布</button>
          <RouterLink v-else-if="status === 'published'" to="/patients" class="pilot-btn">去患者档案</RouterLink>
        </EmptyState>

        <div v-else class="report-table-wrap" role="region" aria-label="报告列表，窄屏可横向滚动" tabindex="0">
          <div class="report-mobile-hint">左右滑动查看完整表格</div>
          <table class="pilot-table report-table">
            <thead>
              <tr>
                <th scope="col">报告编号</th>
                <th scope="col">患者</th>
                <th scope="col">风险</th>
                <th scope="col">状态</th>
                <th scope="col">发布时间</th>
                <th scope="col">完整性</th>
                <th scope="col" class="cell-actions">文件</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in filtered" :key="r.id">
                <td>
                  <RouterLink :to="`/reports/${r.id}`" class="report-no pilot-mono">{{ r.report_no }}</RouterLink>
                  <div class="report-sub">第 {{ r.version }} 版</div>
                </td>
                <td>
                  <div class="report-patient-name" :title="r.patient_name">{{ r.patient_name }}</div>
                  <div class="report-sub pilot-mono" :title="r.mrn">{{ r.mrn }}</div>
                </td>
                <td>
                  <StatusPill :label="riskLabel(r.risk_level)" :tone="riskTone(r.risk_level)" />
                  <div v-if="hasProbability(r.probability)" class="report-prob pilot-mono">{{ pct(r.probability) }}</div>
                  <div v-else-if="r.risk_level === '人工审核'" class="report-sub">无模型概率</div>
                </td>
                <td><StatusPill :label="statusLabel(r.status)" :tone="statusTone(r.status)" /></td>
                <td class="report-date">{{ fmt(r.published_at) }}</td>
                <td>
                  <span :title="r.sha256 ? `SHA-256：${r.sha256}` : '未记录摘要'">
                    <StatusPill :label="r.sha256 ? '摘要已记录' : '摘要缺失'" tone="neutral" />
                  </span>
                </td>
                <td class="cell-actions">
                  <button
                    class="pilot-btn report-pdf-btn"
                    type="button"
                    :disabled="downloading === r.id"
                    :aria-label="`下载 ${r.report_no} 的 PDF`"
                    @click="download(r)"
                  >{{ downloading === r.id ? '生成中…' : 'PDF' }}</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </SectionPanel>
    </div>
  </div>
</template>

<style scoped>
.report-toolbar {
  display: flex;
  align-items: center;
  gap: var(--pilot-space-3);
  flex-wrap: wrap;
  padding: var(--pilot-space-4);
  border-bottom: 1px solid var(--pilot-line);
}
.report-search { flex: 1 1 320px; min-width: 220px; width: auto; }
.report-status-filter { flex: 0 0 132px; width: 132px; }
.report-count { margin-left: auto; white-space: nowrap; }
.report-loading { padding: var(--pilot-space-4); }
.report-skeleton-row { height: 52px; margin-bottom: var(--pilot-space-2); }
.report-skeleton-row:last-child { margin-bottom: 0; }
.report-table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }
.report-mobile-hint { display: none; }
.report-table { min-width: 880px; }
.report-pdf-btn { height: 32px; padding: 0 var(--pilot-space-3); font-size: var(--pilot-font-xs); }
.report-table th { white-space: nowrap; }
.report-table td { vertical-align: top; }
.report-no {
  display: inline-block;
  color: var(--pilot-accent);
  font-size: var(--pilot-font-sm);
  font-weight: 700;
  text-decoration: none;
  white-space: nowrap;
}
.report-no:hover { color: var(--pilot-accent-hover); text-decoration: underline; }
.report-no:focus-visible { outline: 2px solid var(--pilot-accent); outline-offset: 2px; }
.report-sub {
  margin-top: var(--pilot-space-1);
  color: var(--pilot-muted);
  font-size: var(--pilot-font-xs);
  line-height: 1.4;
  white-space: nowrap;
}
.report-patient-name {
  max-width: 180px;
  overflow: hidden;
  color: var(--pilot-ink);
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.report-prob { margin-top: var(--pilot-space-1); color: var(--pilot-ink-soft); font-size: var(--pilot-font-xs); }
.report-date { color: var(--pilot-ink-soft); white-space: nowrap; }
@media (max-width: 650px) {
  .report-toolbar { align-items: stretch; }
  .report-search { flex-basis: 100%; }
  .report-status-filter { flex: 1 1 140px; width: auto; }
  .report-count { flex: 0 0 auto; margin-left: 0; align-self: center; }
  .report-mobile-hint {
    display: block;
    position: sticky;
    left: 0;
    width: 100%;
    padding: var(--pilot-space-2) var(--pilot-space-4);
    border-bottom: 1px dashed var(--pilot-line);
    color: var(--pilot-muted);
    font-size: var(--pilot-font-xs);
    background: var(--pilot-surface);
  }
}
</style>

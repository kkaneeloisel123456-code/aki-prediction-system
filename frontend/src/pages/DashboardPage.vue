<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api/client'
import PageHeader from '../components/PageHeader.vue'
import SectionPanel from '../components/SectionPanel.vue'
import EmptyState from '../components/EmptyState.vue'
import StatusPill from '../components/StatusPill.vue'

const loading = ref(true)
const error = ref('')
const summary = ref<any>(null)
const pendingRows = ref<any[]>([])
const featureMetas = ref<any[]>([])

const statusText: Record<string, string> = {
  draft: '草稿', predicted: '待复核', reviewed: '已复核', published: '已发布',
}
const riskRank: Record<string, number> = { 高: 0, 中: 1, 低: 2, 人工审核: 3 }
const totalFeatures = computed(() => featureMetas.value.length)
const today = computed(() =>
  new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' }).format(new Date()),
)

function fmtDate(value?: string) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}
function isToday(value?: string) {
  if (!value) return false
  const d = new Date(value)
  const now = new Date()
  return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate()
}
function riskText(row: any) {
  const level = row.riskLevel
  if (!level) return '未评估'
  return level === '人工审核' ? '人工审核' : `${level}风险`
}
function riskTone(row: any) {
  if (row.riskLevel === '高') return 'high'
  if (row.riskLevel === '中') return 'mid'
  if (row.riskLevel === '低') return 'low'
  return 'neutral'
}
function statusTone(status: string) {
  if (status === 'predicted') return 'mid'
  if (status === 'reviewed') return 'accent'
  return 'neutral'
}
function progressText(row: any) {
  if (!totalFeatures.value) return '—'
  return `${row.filled}/${totalFeatures.value}`
}

const sortedPending = computed(() => [...pendingRows.value].sort((a, b) => {
  const ra = riskRank[a.riskLevel] ?? 4
  const rb = riskRank[b.riskLevel] ?? 4
  if (ra !== rb) return ra - rb
  return String(b.occurred_at).localeCompare(String(a.occurred_at))
}))

const todayRows = computed(() => sortedPending.value.filter(row => isToday(row.occurred_at)))
const missingItems = computed(() => {
  const counts = new Map<string, { label: string; count: number; row: any }>()
  for (const row of todayRows.value) {
    for (const name of row.missing) {
      const meta = featureMetas.value.find(item => item.name === name)
      const label = meta?.label || name
      const current = counts.get(name)
      if (current) current.count += 1
      else counts.set(name, { label, count: 1, row })
    }
  }
  return [...counts.values()].sort((a, b) => b.count - a.count).slice(0, 8)
})
const totalMissingToday = computed(() => todayRows.value.reduce((sum, row) => sum + row.missing.length, 0))
const firstMissingRow = computed(() => todayRows.value.find(row => row.missing.length > 0) ?? null)
const pendingRiskCounts = computed(() => {
  const counts = { high: 0, mid: 0, low: 0 }
  for (const row of sortedPending.value) {
    if (row.riskLevel === '高') counts.high += 1
    else if (row.riskLevel === '中') counts.mid += 1
    else if (row.riskLevel === '低') counts.low += 1
  }
  return counts
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [data, feats] = await Promise.all([
      api.dashboard(),
      api.features().catch(() => ({ metas: [] })),
    ])
    summary.value = data
    featureMetas.value = feats.metas ?? []
    const rows = data.recent_encounters ?? []
    const details = await Promise.all(rows.map((row: any) => api.encounter(row.id).catch(() => null)))
    const featureNames = featureMetas.value.map((meta: any) => meta.name)
    pendingRows.value = rows.map((row: any, index: number) => {
      const detail = details[index]
      const payloadValues = detail?.draft?.payload?.values ?? {}
      const merged = { ...(detail?.values ?? {}), ...payloadValues }
      const filled = featureNames.filter((name: string) => merged[name] !== null && merged[name] !== undefined && merged[name] !== '').length
      const missing = featureNames.filter((name: string) => merged[name] === null || merged[name] === undefined || merged[name] === '')
      return {
        ...row,
        riskLevel: detail?.latest_prediction?.risk_level ?? '',
        probability: detail?.latest_prediction?.probability ?? null,
        filled,
        missing,
      }
    })
  } catch (e: any) {
    error.value = e?.message ?? '工作台加载失败'
  } finally {
    loading.value = false
  }
}
onMounted(load)
</script>

<template>
  <div class="pilot-page">
    <div class="pilot-page-inner">
      <PageHeader
        kicker="待评估"
        title="未发布评估"
        :description="`${today} · 高风险优先，按发生时间排序`"
      >
        <template #actions>
          <RouterLink to="/patients" class="pilot-btn pilot-btn-primary">新建接诊</RouterLink>
          <button class="pilot-btn" type="button" :disabled="loading" @click="load">刷新</button>
        </template>
      </PageHeader>

      <div v-if="error" class="pilot-error">{{ error }}</div>

      <div v-if="loading" class="pilot-stack" aria-label="正在加载">
        <div class="pilot-skeleton dashboard-skeleton" />
        <div class="pilot-skeleton dashboard-skeleton" />
      </div>

      <div v-else class="dashboard-grid">
        <SectionPanel
          class="dashboard-pending"
          title="评估队列"
          :subtitle="`${sortedPending.length} 份 · 高风险 ${pendingRiskCounts.high} 份`"
          flush
        >
          <EmptyState
            v-if="!sortedPending.length"
            title="没有未发布评估"
            description="已发布报告不会出现在这里。新建接诊后，草稿、待复核和已复核记录会按风险与时间排序。"
          >
            <RouterLink to="/patients" class="pilot-btn pilot-btn-primary">新建接诊</RouterLink>
          </EmptyState>

          <div v-else class="assessment-list">
            <RouterLink
              v-for="row in sortedPending"
              :key="row.id"
              :to="`/encounters/${row.id}`"
              class="assessment-row"
            >
              <div class="assessment-main">
                <div class="assessment-title">
                  <strong>{{ row.patient_name }}</strong>
                  <span class="assessment-mrn pilot-mono">{{ row.mrn || row.patient_id }}</span>
                </div>
                <div class="assessment-meta">
                  <span class="pilot-mono">{{ row.case_ref }}</span>
                  <span>{{ fmtDate(row.occurred_at) }}</span>
                  <span v-if="row.probability != null">{{ (row.probability * 100).toFixed(1) }}%</span>
                </div>
              </div>
              <div class="assessment-side">
                <StatusPill :label="riskText(row)" :tone="riskTone(row)" />
                <StatusPill :label="statusText[row.status] ?? row.status" :tone="statusTone(row.status)" />
                <span class="assessment-progress" :title="`${progressText(row)} 项指标已录入`">{{ progressText(row) }}</span>
                <span class="assessment-action">继续评估</span>
              </div>
            </RouterLink>
          </div>
        </SectionPanel>

        <aside class="dashboard-side">
          <SectionPanel
            class="dashboard-side-card"
            title="今日缺失项"
            :subtitle="todayRows.length ? `${todayRows.length} 份未发布记录，共 ${totalMissingToday} 项未填` : '仅统计今天发生的就诊'"
          >
            <div v-if="!todayRows.length" class="dashboard-aside-empty">
              <p class="pilot-small">今天没有待补录的就诊。</p>
              <RouterLink to="/patients" class="pilot-link">建立新接诊</RouterLink>
            </div>
            <div v-else-if="!missingItems.length" class="dashboard-aside-empty">
              <p class="pilot-small">今天发生的待评估记录已填满指标，可继续预测或复核。</p>
            </div>
            <ul v-else class="missing-list">
              <li v-for="item in missingItems" :key="item.label">
                <span>{{ item.label }}</span>
                <strong>{{ item.count }} 例</strong>
              </li>
            </ul>
            <RouterLink
              v-if="firstMissingRow"
              :to="`/encounters/${firstMissingRow.id}`"
              class="pilot-btn missing-action"
            >去补录</RouterLink>
          </SectionPanel>

          <SectionPanel class="dashboard-side-card" title="今日复查">
            <div class="review-summary">
              <strong>{{ summary?.today_appointments ?? 0 }}</strong>
              <span>人次已预约或签到</span>
            </div>
            <RouterLink to="/schedule" class="pilot-btn section-action">查看复查安排</RouterLink>
          </SectionPanel>
        </aside>

        <p class="dashboard-footnote pilot-small">
          在管患者 {{ summary?.patients_total ?? 0 }} 人 · 累计就诊 {{ summary?.encounters_total ?? 0 }} 次 · 已发布报告 {{ summary?.reports_total ?? 0 }} 份
        </p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dashboard-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(320px, 1fr);
  grid-template-rows: minmax(0, 1fr) minmax(0, 1fr) auto;
  gap: var(--pilot-space-4);
  align-items: stretch;
}
.dashboard-pending { grid-row: 1 / span 2; }
.dashboard-side {
  display: grid;
  grid-template-rows: minmax(0, 1fr) minmax(0, 1fr);
  grid-column: 2;
  grid-row: 1 / span 2;
  gap: var(--pilot-space-4);
  min-width: 0;
}
.dashboard-side-card { display: flex; flex-direction: column; min-height: 0; }
.dashboard-skeleton { height: 260px; }
.assessment-list { display: flex; flex-direction: column; }
.assessment-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--pilot-space-4);
  min-height: 64px;
  padding: var(--pilot-space-3) var(--pilot-space-4);
  border-bottom: 1px solid var(--pilot-line);
  color: inherit;
  text-decoration: none;
  transition: background .15s;
}
.assessment-row:last-child { border-bottom: 0; }
.assessment-row:hover { background: var(--pilot-hover); }
.assessment-row:focus-visible {
  outline: 2px solid var(--pilot-accent);
  outline-offset: -2px;
}
.assessment-main { min-width: 0; }
.assessment-title { display: flex; align-items: baseline; gap: var(--pilot-space-2); flex-wrap: wrap; }
.assessment-title strong { color: var(--pilot-ink); font-size: var(--pilot-font-md); }
.assessment-mrn { color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
.assessment-meta {
  display: flex;
  align-items: center;
  gap: var(--pilot-space-2);
  flex-wrap: wrap;
  margin-top: var(--pilot-space-1);
  color: var(--pilot-muted);
  font-size: var(--pilot-font-xs);
}
.assessment-side {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--pilot-space-2);
  flex-wrap: wrap;
}
.assessment-progress { color: var(--pilot-muted); font-size: var(--pilot-font-xs); white-space: nowrap; }
.assessment-action { color: var(--pilot-accent); font-size: var(--pilot-font-xs); font-weight: 600; white-space: nowrap; }
.dashboard-aside-empty { display: grid; gap: var(--pilot-space-2); }
.dashboard-aside-empty p { margin: 0; }
.missing-list { display: flex; flex-direction: column; margin: 0; padding: 0; list-style: none; }
.missing-list li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--pilot-space-3);
  padding: var(--pilot-space-2) 0;
  border-bottom: 1px dashed var(--pilot-line);
  color: var(--pilot-ink-soft);
  font-size: var(--pilot-font-sm);
}
.missing-list li:last-child { border-bottom: 0; }
.missing-list strong { color: var(--pilot-mid); font-size: var(--pilot-font-xs); white-space: nowrap; }
.missing-action { margin-top: var(--pilot-space-4); width: 100%; }
.review-summary { display: flex; align-items: baseline; gap: var(--pilot-space-2); }
.review-summary strong { color: var(--pilot-ink); font-size: var(--pilot-font-xl); line-height: 1; }
.review-summary span { color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
.section-action { margin-top: var(--pilot-space-4); width: 100%; }
.dashboard-footnote {
  grid-column: 1 / -1;
  grid-row: 3;
  margin: 0;
  padding-top: var(--pilot-space-1);
  line-height: 1.6;
}
@media (max-width: 1024px) {
  .dashboard-grid { grid-template-columns: minmax(0, 1fr); grid-template-rows: auto auto auto; }
  .dashboard-pending { grid-row: auto; }
  .dashboard-side { grid-column: 1; grid-row: auto; grid-template-rows: auto auto; }
  .dashboard-footnote { grid-column: 1; grid-row: auto; }
}
@media (max-width: 650px) {
  .assessment-row { align-items: flex-start; flex-direction: column; gap: var(--pilot-space-2); }
  .assessment-side { justify-content: flex-start; }
}
</style>

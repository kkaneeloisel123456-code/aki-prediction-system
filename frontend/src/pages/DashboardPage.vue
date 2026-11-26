<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api/client'
import type { ClinicalTask, ClinicalTasks, TaskStage } from '../api/types'
import PageHeader from '../components/PageHeader.vue'
import SectionPanel from '../components/SectionPanel.vue'
import EmptyState from '../components/EmptyState.vue'
import StatusPill from '../components/StatusPill.vue'
import PilotTabs from '../components/PilotTabs.vue'
import { useAuth } from '../composables/useAuth'
const auth = useAuth()
const loading = ref(true)
const error = ref('')
const summaryError = ref('')
const summary = ref<any>(null)
const queue = ref<ClinicalTasks | null>(null)
const stage = ref<'all' | TaskStage>('all')
const offset = ref(0)
let requestId = 0
const labels: Record<TaskStage, string> = { supplement: '待补录', assess: '待运行评估', review: '待医生复核', publish: '待发布核对', observe: '暂不发布', reconcile: '记录待核对' }
const primaryStages: TaskStage[] = ['supplement', 'assess', 'review', 'publish']
const allCount = computed(() => queue.value ? Object.values(queue.value.counts).reduce((sum, n) => sum + n, 0) : 0)
const tabs = computed(() => [
  { value: 'all', label: '全部', count: queue.value ? allCount.value : null },
  ...Object.entries(labels).map(([value, label]) => ({ value, label, count: queue.value?.counts[value as TaskStage] ?? null })),
])
const today = new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' }).format(new Date())
function fmtDate(value: string) {
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}
function taskLink(row: ClinicalTask) {
  const anchors: Record<TaskStage, string> = { supplement: 'metrics', assess: 'metrics', review: 'review', publish: 'publish', observe: 'review', reconcile: 'document' }
  return `/encounters/${row.id}#encounter-${anchors[row.stage]}`
}
function actionText(row: ClinicalTask) {
  if (!row.can_edit) return '查看记录 →'
  return ({ supplement: '补录指标', assess: '运行评估', review: '进行复核', publish: '发布核对', observe: '查看观察记录', reconcile: '核对记录' })[row.stage] + ' →'
}
function riskText(row: ClinicalTask) { return row.manual ? '人工记录' : row.risk_level ? `模型${row.risk_level}风险` : '尚无当前模型结果' }
function riskTone(row: ClinicalTask) { return row.risk_level === '高' ? 'high' : row.risk_level === '中' ? 'mid' : row.risk_level === '低' ? 'low' : 'neutral' }
async function loadTasks() {
  const id = ++requestId
  loading.value = true
  error.value = ''
  try { const result = await api.tasks(stage.value, offset.value); if (id === requestId) queue.value = result }
  catch (e: any) { if (id === requestId) { error.value = e?.message || '待办加载失败'; queue.value = null } }
  finally { if (id === requestId) loading.value = false }
}
function selectStage(value: string) { stage.value = value as 'all' | TaskStage; offset.value = 0; void loadTasks() }
function changePage(direction: number) { offset.value = Math.max(0, offset.value + direction * 20); void loadTasks() }
async function loadSummary() {
  summaryError.value = ''; summary.value = null
  try { summary.value = await api.dashboard() }
  catch (e: any) { summaryError.value = e?.message || '辅助统计读取失败' }
}
function refresh() { void loadTasks(); void loadSummary() }
onMounted(refresh)
</script>

<template>
  <div class="pilot-page"><div class="pilot-page-inner">
    <PageHeader kicker="临床工作" title="工作台" :description="`${today} · 当前授权范围内的待办`">
      <template #actions><RouterLink to="/patients" class="pilot-btn pilot-btn-primary">新建接诊</RouterLink><button class="pilot-btn" type="button" :disabled="loading" @click="refresh">刷新</button></template>
    </PageHeader>
    <section class="dashboard-welcome">
      <div><span class="pilot-kicker">CLINICAL WORKSPACE</span><h2>你好，{{ auth.user.value?.display_name || '医生' }}</h2><p>先处理待办，再完成患者输入核对、模型评估与医生复核。</p></div>
      <RouterLink to="/assessment-guide" class="pilot-btn">查看评估说明</RouterLink>
    </section>
    <div v-if="queue && !error" class="dashboard-stats" :aria-busy="loading">
      <button v-for="key in primaryStages" :key="key" type="button" :class="{ selected: stage === key }" @click="selectStage(key)"><span>{{ labels[key] }}</span><strong>{{ queue.counts[key] }}</strong><small>查看对应待办 →</small></button>
    </div>
    <div class="dashboard-grid">
      <SectionPanel id="assessment-queue" title="临床待办" subtitle="按工作阶段筛选；有当前模型结果时按风险、再按就诊时间排序。只读记录仅供查看。" flush>
        <div class="queue-tabs"><PilotTabs :model-value="stage" :tabs="tabs" label="待办类型" @update:model-value="selectStage" /></div>
        <div v-if="error" class="queue-error" role="alert"><p>{{ error }}</p><p>未能确认当前待办数量，请重新读取。</p><button class="pilot-btn" @click="loadTasks">重试</button></div>
        <div v-else-if="loading" class="queue-loading" role="status">正在读取待办…</div>
        <template v-else-if="queue">
          <EmptyState v-if="!queue.tasks.length" :title="stage === 'all' ? '当前没有未完成记录' : `当前没有“${labels[stage as TaskStage]}”记录`" description="统计覆盖当前授权范围；已发布报告可在评估报告中查看。"><RouterLink to="/patients" class="pilot-btn">查看患者档案</RouterLink></EmptyState>
          <div v-else class="assessment-list">
            <RouterLink v-for="row in queue.tasks" :key="row.id" :to="taskLink(row)" class="assessment-row">
              <div class="assessment-main">
                <div class="assessment-title"><strong>{{ row.patient_name }}</strong><span class="pilot-mono">{{ row.mrn }}</span><span v-if="!row.can_edit" class="readonly-tag">只读</span></div>
                <div class="assessment-meta"><span class="pilot-mono">{{ row.case_ref }}</span><span>{{ fmtDate(row.occurred_at) }}</span></div>
                <div class="assessment-meta"><span>当前实测 {{ row.filled }}/{{ row.total_features }} 项</span><span v-if="row.missing_count">缺失 {{ row.missing_count }} 项</span><span v-if="row.invalid_count">需修正 {{ row.invalid_count }} 项</span></div>
              </div>
              <div class="assessment-side">
                <div class="assessment-badges"><StatusPill :label="riskText(row)" :tone="riskTone(row)" /><span v-if="row.probability != null" class="pilot-mono">{{ (row.probability * 100).toFixed(1) }}%</span><StatusPill :label="labels[row.stage]" tone="neutral" /></div>
                <span class="assessment-action">{{ actionText(row) }}</span>
              </div>
            </RouterLink>
          </div>
          <div v-if="queue.total" class="queue-pagination"><span>共 {{ queue.total }} 份 · 第 {{ offset + 1 }}–{{ Math.min(offset + 20, queue.total) }} 份</span><div><button class="pilot-btn" :disabled="offset === 0" @click="changePage(-1)">上一页</button><button class="pilot-btn" :disabled="offset + 20 >= queue.total" @click="changePage(1)">下一页</button></div></div>
        </template>
      </SectionPanel>
      <aside class="dashboard-side">
        <SectionPanel title="工作提示" subtitle="模型结果与医生结论分别记录"><p>缺失指标可能参与填充；已有评估结果的记录应先核对输入及填充说明，再决定复核意见。</p><p>“暂不发布”保留观察理由；“待发布核对”仍须通过病历、医嘱和缺失项等检查。</p><RouterLink to="/assessment-guide" class="pilot-link">输入要求与模型局限 →</RouterLink></SectionPanel>
        <SectionPanel title="复查与累计统计">
          <div v-if="summaryError" role="alert"><p class="pilot-small">{{ summaryError }}，统计暂不可用。</p><button class="pilot-btn" @click="loadSummary">重试统计</button></div>
          <dl v-else-if="summary" class="summary-list"><div><dt>今日复查预约</dt><dd>{{ summary.today_appointments }}</dd></div><div><dt>在管患者</dt><dd>{{ summary.patients_total }}</dd></div><div><dt>已发布报告</dt><dd>{{ summary.reports_total }}</dd></div></dl>
          <p v-else class="pilot-small" role="status">正在读取统计…</p>
          <RouterLink to="/schedule" class="pilot-btn section-action">查看复查随访</RouterLink>
        </SectionPanel>
      </aside>
    </div>
  </div></div>
</template>

<style scoped>
.dashboard-welcome{display:flex;align-items:center;justify-content:space-between;gap:24px;padding:28px 32px;margin-bottom:20px;border:1px solid var(--pilot-line);border-radius:var(--pilot-radius-card);background:linear-gradient(115deg,var(--pilot-accent-soft),var(--pilot-surface))}.dashboard-welcome h2{margin:10px 0;font-size:25px;font-weight:600}.dashboard-welcome p{margin:0;color:var(--pilot-muted);line-height:1.8}
.dashboard-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin-bottom:24px}.dashboard-stats button{display:grid;gap:10px;padding:20px;text-align:left;background:var(--pilot-surface);border:1px solid var(--pilot-line);border-radius:var(--pilot-radius-card);color:var(--pilot-ink);cursor:pointer;font:inherit}.dashboard-stats button:hover,.dashboard-stats .selected{border-color:var(--pilot-accent)}.dashboard-stats span,.dashboard-stats small{font-size:12px;color:var(--pilot-muted)}.dashboard-stats strong{font-size:28px;font-weight:600;color:var(--pilot-accent)}
.dashboard-grid{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:24px;align-items:start}.dashboard-grid>*{min-width:0}.dashboard-side{display:grid;gap:20px}.dashboard-side p{line-height:1.8;color:var(--pilot-muted);margin-top:0;font-size:13px}.queue-tabs{padding:16px 20px 0}.queue-tabs :deep(.pilot-tabs){flex-wrap:wrap;overflow:visible}.queue-loading,.queue-error{padding:32px;color:var(--pilot-muted)}.queue-error{color:var(--pilot-high)}
.assessment-row{display:flex;align-items:center;justify-content:space-between;gap:20px;padding:20px;border-bottom:1px solid var(--pilot-line);color:inherit;text-decoration:none}.assessment-row:hover{background:var(--pilot-hover)}.assessment-row:focus-visible{outline:2px solid var(--pilot-accent);outline-offset:-2px}.assessment-main{min-width:0}.assessment-title,.assessment-meta,.assessment-badges{display:flex;align-items:center;flex-wrap:wrap;gap:8px}.assessment-title strong{font-size:15px}.assessment-title>span,.assessment-meta{color:var(--pilot-muted);font-size:12px}.assessment-meta{margin-top:8px;overflow-wrap:anywhere}.readonly-tag{padding:2px 6px;border:1px solid var(--pilot-line);border-radius:4px}.assessment-side{display:grid;justify-items:end;gap:12px;max-width:55%}.assessment-badges{justify-content:flex-end;font-size:12px}.assessment-action{font-size:13px;color:var(--pilot-accent);font-weight:600}.queue-pagination{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;padding:16px 20px;color:var(--pilot-muted);font-size:12px}.queue-pagination>div{display:flex;gap:8px}.summary-list{margin:0}.summary-list>div{display:flex;justify-content:space-between;padding:12px 0;border-bottom:1px solid var(--pilot-line);font-size:13px}.summary-list dt{color:var(--pilot-muted)}.summary-list dd{margin:0;font-weight:600}.section-action{margin-top:20px;width:100%}
@media(max-width:1100px){.dashboard-grid{grid-template-columns:minmax(0,1fr)}.dashboard-side{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:700px){.dashboard-stats{grid-template-columns:repeat(2,minmax(0,1fr))}.dashboard-welcome{padding:20px;align-items:flex-start;flex-direction:column}.dashboard-side{grid-template-columns:minmax(0,1fr)}.assessment-row{align-items:flex-start;flex-direction:column}.assessment-side{justify-items:start;max-width:100%}.assessment-badges{justify-content:flex-start}}
</style>

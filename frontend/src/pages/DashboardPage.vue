<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { api } from '../api/client'
import { useAuth } from '../composables/useAuth'

const auth = useAuth()
const loading = ref(true)
const error = ref('')
const summary = ref<any>(null)

const maxMonthly = computed(() => {
  const rows = summary.value?.monthly ?? []
  return Math.max(1, ...rows.map((r: any) => Math.max(r.encounters, r.reports)))
})
const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '夜间值班辛苦了'
  if (h < 12) return '上午好'
  if (h < 18) return '下午好'
  return '晚上好'
})
const today = computed(() =>
  new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' }).format(new Date()),
)

function fmtDate(value?: string) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}
const statusText: Record<string, string> = {
  draft: '草稿', predicted: '待复核', reviewed: '已复核', published: '已发布',
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    summary.value = await api.dashboard()
  } catch (e: any) {
    error.value = e?.message ?? '数据加载失败'
  } finally {
    loading.value = false
  }
}
onMounted(load)
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h1 class="page-title">{{ greeting }}，{{ auth.user.value?.display_name || auth.user.value?.username }}</h1>
        <div class="page-subtitle">{{ today }} · 急性肾损伤临床风险管理工作台</div>
      </div>
      <div class="page-actions">
        <RouterLink to="/patients" class="btn btn-primary">＋ 新建接诊</RouterLink>
        <RouterLink to="/reports" class="btn btn-secondary">报告中心</RouterLink>
        <button class="btn btn-secondary" :disabled="loading" @click="load">刷新</button>
      </div>
    </div>

    <div v-if="error" class="error">{{ error }}</div>
    <div v-if="loading" class="card"><div class="empty-state">正在加载工作台…</div></div>

    <template v-else-if="summary">
      <div class="summary-strip">
        <div class="summary-item">
          <div class="label">在管患者</div>
          <div class="value">{{ summary.patients_total }}</div>
          <div class="hint">当前账号可见的有效档案</div>
        </div>
        <div class="summary-item">
          <div class="label">就诊记录</div>
          <div class="value">{{ summary.encounters_total }}</div>
          <div class="hint">累计接诊与评估</div>
        </div>
        <div class="summary-item">
          <div class="label">待处理</div>
          <div class="value" :style="{color: summary.pending_total ? 'var(--yellow)' : 'var(--green)'}">{{ summary.pending_total }}</div>
          <div class="hint">尚未发布正式报告</div>
        </div>
        <div class="summary-item">
          <div class="label">已发布报告</div>
          <div class="value">{{ summary.reports_total }}</div>
          <div class="hint">今日预约 {{ summary.today_appointments }} 人次</div>
        </div>
      </div>

      <div class="grid-2-1">
        <div>
          <div class="card">
            <div class="card-header">
              <span class="card-title">待处理就诊</span>
              <RouterLink to="/patients" style="font-size:10px;color:var(--primary)">查看全部 →</RouterLink>
            </div>
            <div v-if="!summary.recent_encounters?.length" class="empty-state">
              <strong>暂无待处理就诊</strong>
              已发布的记录不再出现在这里。
            </div>
            <div v-else class="table-wrap">
              <table class="data-table">
                <thead>
                  <tr><th>患者</th><th>就诊编号</th><th>发生时间</th><th>状态</th><th></th></tr>
                </thead>
                <tbody>
                  <tr v-for="e in summary.recent_encounters" :key="e.id">
                    <td>
                      <div class="primary-cell">{{ e.patient_name }}</div>
                      <div class="sub-cell">{{ e.mrn || e.patient_id }}</div>
                    </td>
                    <td>{{ e.case_ref }}</td>
                    <td>{{ fmtDate(e.occurred_at) }}</td>
                    <td><span class="status" :class="`status-${e.status}`">{{ statusText[e.status] ?? e.status }}</span></td>
                    <td class="text-right">
                      <RouterLink :to="`/encounters/${e.id}`" class="btn btn-sm btn-secondary">继续评估</RouterLink>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div class="card">
            <div class="card-header"><span class="card-title">近六个月业务量</span></div>
            <div class="card-body">
              <div v-for="m in summary.monthly" :key="m.month" style="display:grid;grid-template-columns:64px 1fr 1fr 80px;gap:10px;align-items:center;margin-bottom:9px">
                <span style="font-size:10px;color:var(--text-dim)">{{ m.month.slice(5) }} 月</span>
                <div class="metric-progress" style="margin:0">
                  <div class="track"><div class="fill" :style="{width: `${m.encounters / maxMonthly * 100}%`}" /></div>
                </div>
                <div style="height:5px;background:var(--bg-inset);border-radius:3px;overflow:hidden">
                  <div :style="{width: `${m.reports / maxMonthly * 100}%`,height:'100%',background:'var(--green)',borderRadius:'3px'}" />
                </div>
                <span style="font-size:10px;color:var(--text-dim);text-align:right">{{ m.encounters }} 诊 / {{ m.reports }} 报</span>
              </div>
              <div class="muted" style="font-size:10px;margin-top:4px">蓝色为就诊量，绿色为报告发布量。</div>
            </div>
          </div>
        </div>

        <div>
          <div class="card">
            <div class="card-header"><span class="card-title">风险构成</span></div>
            <div class="card-body">
              <div v-for="(level, key) in { 高: 'high', 中: 'medium', 低: 'low' }" :key="key" style="display:flex;align-items:center;gap:10px;margin-bottom:12px">
                <span class="status" :class="`status-${key === '高' ? 'high' : key === '中' ? 'medium' : 'low'}`" style="width:42px;justify-content:center">{{ key }}风险</span>
                <div style="flex:1;height:8px;background:var(--bg-inset);border-radius:4px;overflow:hidden">
                  <div :style="{width: `${summary.risk_distribution[key] / Math.max(1, summary.risk_distribution.高 + summary.risk_distribution.中 + summary.risk_distribution.低) * 100}%`,height:'100%',background: `var(--${key === '高' ? 'red' : key === '中' ? 'yellow' : 'green'})`,borderRadius:'4px'}" />
                </div>
                <span style="font-size:12px;font-weight:800;color:var(--text-bright);width:28px;text-align:right">{{ summary.risk_distribution[key] }}</span>
              </div>
              <div class="info-box mb-0" style="margin-top:4px">按每个患者最近一次有效预测统计。</div>
            </div>
          </div>

          <div class="card">
            <div class="card-header"><span class="card-title">手术类型分布</span></div>
            <div class="card-body">
              <div v-if="!summary.departments?.length" class="muted">暂无数据</div>
              <div v-for="d in summary.departments.slice(0,6)" :key="d.name" style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px dashed var(--border)">
                <span style="font-size:11px;color:var(--text)">{{ d.name }}</span>
                <span style="font-size:11px;font-weight:700;color:var(--text-bright)">{{ d.cases }}</span>
              </div>
            </div>
          </div>

          <div class="card">
            <div class="card-header"><span class="card-title">快捷入口</span></div>
            <div class="card-body" style="display:flex;flex-direction:column;gap:8px">
              <RouterLink to="/patients" class="btn btn-secondary">患者档案与接诊</RouterLink>
              <RouterLink to="/reports" class="btn btn-secondary">报告检索与下载</RouterLink>
              <RouterLink to="/schedule" class="btn btn-secondary">预约排班与反馈</RouterLink>
              <RouterLink v-if="auth.user.value?.role === 'admin'" to="/admin" class="btn btn-secondary">账号、审计与备份</RouterLink>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

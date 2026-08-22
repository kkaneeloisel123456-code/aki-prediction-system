<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api } from '../api/client'

const meta = ref<any>(null)
const offline = ref(false)
const cvRows = ref<Record<string, unknown>[]>([])
// 数据未就绪时条形图区域显示占位，只渲染一次，避免
// “兜底值→真实值”切换引发的宽度过渡/元素重建（Voting 行“卡一下”）。
const perfLoaded = ref(false)

onMounted(() => {
  api.meta().then((m: any) => { meta.value = m }).catch(() => { offline.value = true })
  // 首页条形图必须与“模型性能”页同源：在线时直接用 /api/performance
  // 的 CV 结果渲染，杜绝两页数字打架。
  api.performance()
    .then((p) => { cvRows.value = p.cv ?? [] })
    .catch(() => { /* 离线兜底 */ })
    .finally(() => { perfLoaded.value = true })
})

// 离线兜底值与 outputs/tables/final_cv_results.csv 逐项同步（50次CV口径）。
// 注意：final_cv_results.csv 中 Voting 的模型名是 'Voting Ensemble'（带空格），
// 兜底表的 key 必须与之完全一致，否则真实数据到达时该行 key 变化、
// 被 Vue 重建并失去高亮（表现为"卡一下才出现"）。
const FALLBACK_PERF = [
  { key: 'LogisticRegression', name: 'LR',     auc: 0.7939, std: 0.0432, color: '#a78bfa' },
  { key: 'RandomForest',       name: 'RF',     auc: 0.8073, std: 0.0409, color: '#38bdf8' },
  { key: 'XGBoost',            name: 'XGB',    auc: 0.8056, std: 0.0435, color: '#fb923c' },
  { key: 'ExtraTrees',         name: 'ET',     auc: 0.7935, std: 0.0430, color: '#4ade80' },
  { key: 'Voting Ensemble',    name: 'Voting', auc: 0.8096, std: 0.0428, color: '#38bdf8', highlight: true },
]
const NAME_MAP: Record<string, string> = {
  LogisticRegression: 'LR', RandomForest: 'RF', XGBoost: 'XGB',
  ExtraTrees: 'ET', 'Voting Ensemble': 'Voting',
}

const MODEL_PERF = computed(() => {
  if (!perfLoaded.value) return []
  if (!cvRows.value.length) return FALLBACK_PERF
  const byKey = Object.fromEntries(FALLBACK_PERF.map(f => [f.key, f]))
  const rows = cvRows.value.map((r: any) => {
    const key = String(r['模型'] ?? '')
    return {
      key,
      name: NAME_MAP[key] ?? key,
      auc: Number(r['50次CV AUC均值'] ?? 0) || 0,
      std: Number(r['标准差'] ?? 0) || 0,
    }
  })
  return rows
    .filter(r => r.auc > 0)
    .map(r => ({
      ...r,
      color: byKey[r.key]?.color ?? 'var(--primary)',
      highlight: r.key === 'Voting Ensemble',
    }))
})
const votingStd = computed(() => {
  const v = MODEL_PERF.value.find(m => m.name === 'Voting')
  return v && v.std ? `均值 ± ${v.std.toFixed(3)}` : '均值 ± 0.043'
})

// bar 宽度百分比（基准 0.72, 上限 0.86）
const barPct = (auc: number) =>
  Math.max(2, ((auc - 0.72) / (0.86 - 0.72) * 100)).toFixed(1) + '%'
</script>

<template>
  <!-- 后端离线提示：避免离线时硬编码兜底值被误认为实时数据 -->
  <div v-if="offline" class="warning-box">
    ⚠ 后端服务未连接，以下指标为训练阶段固定值（非实时数据）。请确认服务已启动：双击 启动系统.bat 或运行 uvicorn backend.app.main:app --port 8000
  </div>
  <!-- Hero 横幅 -->
  <div class="hero-banner">
    <div class="hero-content">
      <div class="hero-title">AKI 智能风险预测系统</div>
      <div class="hero-sub">
        基于 420 例心脏手术后患者临床数据 &nbsp;·&nbsp;
        50 次嵌套交叉验证 &nbsp;·&nbsp; SHAP 可解释性分析
      </div>
      <div class="hero-tags">
        <span class="hero-tag">Logistic Regression</span>
        <span class="hero-tag">Random Forest</span>
        <span class="hero-tag">XGBoost</span>
        <span class="hero-tag">ExtraTrees</span>
        <span class="hero-tag">Voting Ensemble</span>
      </div>
    </div>
    <div class="hero-metrics">
      <div class="hero-metric">
        <div class="hero-metric-val">{{ meta?.best_auc ? meta.best_auc.toFixed(3) : '0.810' }}</div>
        <div class="hero-metric-label">AUC</div>
      </div>
      <div class="hero-metric">
        <div class="hero-metric-val">29.8%</div>
        <div class="hero-metric-label">AKI 发生率</div>
      </div>
      <div class="hero-metric">
        <div class="hero-metric-val">420</div>
        <div class="hero-metric-label">训练样本</div>
      </div>
    </div>
  </div>

  <!-- KPI 卡片 -->
  <div class="kpi-grid">
    <div class="kpi-card kpi-card-blue">
      <div class="kpi-label">训练样本量</div>
      <div class="kpi-value">420</div>
      <div class="kpi-delta neutral">心脏手术后患者</div>
    </div>
    <div class="kpi-card kpi-card-purple">
      <div class="kpi-label">入选特征数</div>
      <div class="kpi-value">{{ meta?.n_features ?? 35 }}</div>
      <div class="kpi-delta neutral">RF 重要性筛选</div>
    </div>
    <div class="kpi-card kpi-card-blue">
      <div class="kpi-label">50次嵌套 CV AUC</div>
      <div class="kpi-value">{{ meta?.best_auc ? meta.best_auc.toFixed(3) : '0.810' }}</div>
      <div class="kpi-delta positive">{{ votingStd }}</div>
    </div>
    <div class="kpi-card kpi-card-green">
      <div class="kpi-label">集成策略</div>
      <div class="kpi-value" style="font-size:15px;margin-top:5px">Voting</div>
      <div class="kpi-delta neutral">LR · RF · XGB · ET</div>
    </div>
    <div class="kpi-card kpi-card-orange">
      <div class="kpi-label">AKI 发生率</div>
      <div class="kpi-value">29.8%</div>
      <div class="kpi-delta neutral">125 / 420 例</div>
    </div>
  </div>

  <!-- 中间两列 -->
  <div class="grid grid-2">
    <!-- 模型性能条形图 -->
    <div class="card">
      <div class="card-header">
        <span class="card-title">模型性能对比（AUC）</span>
        <span class="badge badge-info">5折×10次嵌套CV</span>
      </div>
      <div class="card-body">
        <p v-if="!perfLoaded" class="muted" style="text-align:center;padding:14px 0">加载中…</p>
        <template v-else>
        <div
          v-for="m in MODEL_PERF" :key="m.name"
          class="perf-bar-row" :class="{ highlight: m.highlight }"
        >
          <div class="perf-bar-name">{{ m.name }}</div>
          <div class="perf-bar-track">
            <div class="perf-bar-fill" :style="{ width: barPct(m.auc), background: m.color }" />
          </div>
          <div class="perf-bar-val">{{ m.auc.toFixed(3) }}</div>
        </div>
        </template>
        <p style="font-size:10px;color:var(--text-dim);margin-top:12px">
          ▪ 基准线 0.72 &nbsp;·&nbsp; Voting Ensemble 最优
        </p>
      </div>
    </div>

    <!-- 研究概述 -->
    <div class="card">
      <div class="card-header"><span class="card-title">研究概述</span></div>
      <div class="card-body">
        <p style="font-size:12px;color:var(--text-muted);line-height:1.75;margin-bottom:14px">
          本系统基于 420 例心脏手术患者临床数据，采用 LR、RF、XGBoost、ExtraTrees 四种基模型与
          Voting 集成策略，构建术后 AKI 风险预测模型。通过 SHAP 可解释性分析、DCA 决策曲线、
          嵌套式交叉验证与 Bootstrap 内部验证，为临床决策提供透明、可信的个体化风险评估。
        </p>
        <div class="info-box" style="margin-bottom:0">
          核心能力：在线预测 -> 风险分层 -> 危险因素解析 -> 干预建议 -> PDF 报告
        </div>
      </div>
    </div>
  </div>

  <!-- 功能导航 -->
  <div class="card">
    <div class="card-header"><span class="card-title">功能导航</span></div>
    <div class="card-body">
      <div class="grid grid-3">
        <RouterLink to="/performance" class="nav-card">
          <b>模型性能</b>
          <p>ROC / PR 曲线、校准、DCA、SHAP、CV 可信度</p>
        </RouterLink>
        <RouterLink to="/predict" class="nav-card">
          <b>风险预测</b>
          <p>实时个体风险评估、可解释建议与 PDF 报告</p>
        </RouterLink>
        <RouterLink to="/workstation" class="nav-card">
          <b>医生工作台</b>
          <p>患者风险列表、批量 CSV 评估</p>
        </RouterLink>
      </div>
    </div>
  </div>
</template>

<style scoped>
.nav-card {
  padding: 14px; background: var(--bg-nav); border-radius: 6px;
  border: 1px solid var(--border); text-decoration: none; color: inherit; display: block;
}
.nav-card b { font-size: 13px; color: var(--text-bright); display: block; margin-bottom: 5px; font-weight: 700; }
.nav-card p { font-size: 11px; color: var(--text-dim); line-height: 1.5; }
</style>

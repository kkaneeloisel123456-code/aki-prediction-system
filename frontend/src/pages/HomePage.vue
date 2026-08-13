<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '../api/client'

const meta = ref<any>(null)
onMounted(() => api.meta().then((m: any) => { meta.value = m }).catch(() => {}))

// 模型 AUC 对比数据（与 outputs/tables/final_cv_results.csv 一致）
const MODEL_PERF = [
  { name: 'LR',     auc: 0.794, color: '#a78bfa' },
  { name: 'RF',     auc: 0.807, color: '#38bdf8' },
  { name: 'XGB',    auc: 0.806, color: '#fb923c' },
  { name: 'ET',     auc: 0.794, color: '#4ade80' },
  { name: 'Voting', auc: 0.810, color: '#38bdf8', highlight: true },
]
// bar 宽度百分比（基准 0.72, 上限 0.86）
const barPct = (auc: number) =>
  Math.max(2, ((auc - 0.72) / (0.86 - 0.72) * 100)).toFixed(1) + '%'
</script>

<template>
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
      <div class="kpi-delta positive">均值 ± 0.043</div>
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
          核心能力：在线预测 → 风险分层 → 危险因素解析 → 干预建议 → PDF 报告
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

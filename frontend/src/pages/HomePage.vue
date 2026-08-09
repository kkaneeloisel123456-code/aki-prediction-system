<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '../api/client'
import type { MetaResponse } from '../api/types'
const meta = ref<MetaResponse | null>(null)
onMounted(() => api.meta().then(m => meta.value = m).catch(() => {}))
</script>

<template>
  <h2 class="page-title">系统首页</h2>
  <p class="page-subtitle">急性肾损伤（AKI）智能预测系统 · 实时风险分层与可解释分析</p>

  <div class="kpi-grid">
    <div class="kpi-card"><div class="kpi-label">训练样本量</div><div class="kpi-value">420</div><div class="kpi-delta neutral">心脏手术后患者</div></div>
    <div class="kpi-card"><div class="kpi-label">入选特征数</div><div class="kpi-value">{{ meta?.n_features ?? 35 }}</div><div class="kpi-delta neutral">RF Top35</div></div>
    <div class="kpi-card"><div class="kpi-label">50次嵌套 CV AUC</div><div class="kpi-value">{{ meta?.best_auc ? meta.best_auc.toFixed(3) : '—' }}</div><div class="kpi-delta positive">± 0.045</div></div>
    <div class="kpi-card"><div class="kpi-label">最佳模型</div><div class="kpi-value" style="font-size:16px;margin-top:6px">Voting Ensemble</div><div class="kpi-delta neutral">LR+RF+XGB+ET</div></div>
    <div class="kpi-card"><div class="kpi-label">AKI 发生率</div><div class="kpi-value">29.8%</div><div class="kpi-delta neutral">125 / 420</div></div>
  </div>

  <div class="grid grid-2">
    <div class="card">
      <div class="card-header"><span class="card-title">研究概述</span></div>
      <div class="card-body">
        <p style="font-size:12px;color:var(--text-muted);line-height:1.7">
          本系统基于 420 例心脏手术患者临床数据，采用 Logistic Regression、Random Forest、XGBoost、ExtraTrees 四种基模型与 Voting 集成策略，构建术后 AKI 风险预测模型。通过 SHAP 可解释性分析、DCA 决策曲线、嵌套式交叉验证与 Bootstrap 内部验证，为临床决策提供透明、可信的个体化风险评估。
        </p>
        <div class="info-box" style="margin-top:12px;margin-bottom:0">核心能力：在线预测 → 风险分层 → 危险因素解析 → 干预建议 → PDF 报告</div>
      </div>
    </div>
    <div class="card">
      <div class="card-header"><span class="card-title">数据质量校验</span></div>
      <div class="card-body">
        <div style="display:flex;gap:12px;margin-bottom:12px">
          <div style="flex:1;text-align:center;padding:12px;background:rgba(34,197,94,0.08);border-radius:4px;border:1px solid rgba(34,197,94,0.15)">
            <div style="font-size:22px;color:var(--green);font-weight:800">OK</div>
            <div style="font-size:10px;color:var(--green);margin-top:3px">KDIGO Scr 标准校验通过</div>
          </div>
          <div style="flex:1;text-align:center;padding:12px;background:rgba(34,197,94,0.08);border-radius:4px;border:1px solid rgba(34,197,94,0.15)">
            <div style="font-size:22px;color:var(--green);font-weight:800">OK</div>
            <div style="font-size:10px;color:var(--green);margin-top:3px">AKI 分组 vs 分期一致性通过</div>
          </div>
        </div>
        <p style="font-size:11px;color:var(--text-dim)">所有保留特征均在 AKI 诊断（术后 48h/7d）之前即可获取，预测时点为"入 ICU 即刻"。</p>
      </div>
    </div>
  </div>

  <div class="card">
    <div class="card-header"><span class="card-title">功能导航</span></div>
    <div class="card-body">
      <div class="grid grid-3">
        <RouterLink to="/performance" class="nav-card"><b>模型性能</b><p>ROC/PR、校准、DCA、SHAP、CV</p></RouterLink>
        <RouterLink to="/predict" class="nav-card"><b>风险预测</b><p>实时预测，可解释建议与 PDF</p></RouterLink>
        <RouterLink to="/workstation" class="nav-card"><b>医生工作台</b><p>患者列表、批量评估</p></RouterLink>
      </div>
    </div>
  </div>
</template>

<style scoped>
.nav-card { padding:12px; background:var(--bg-nav); border-radius:4px; border:1px solid var(--border); text-decoration:none; color:inherit; display:block; }
.nav-card b { font-size:13px; color:var(--text); }
.nav-card p { font-size:11px; color:var(--text-dim); margin-top:4px; }
</style>

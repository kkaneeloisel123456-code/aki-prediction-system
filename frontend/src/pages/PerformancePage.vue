<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '../api/client'
import type { PerformanceResponse } from '../api/types'

const tab = ref('compare')
const perf = ref<PerformanceResponse | null>(null)
const figures = ref<string[]>([])
const tabs = [
  { id: 'compare', label: '性能对比' }, { id: 'curves', label: 'ROC / PR' },
  { id: 'calibration', label: '校准 / DCA' }, { id: 'cv', label: 'CV 可信度' },
  { id: 'ablation', label: '消融实验' }, { id: 'ensemble', label: '集成对比' },
]
const has = (n: string) => figures.value.includes(n)
onMounted(() => {
  api.performance().then(p => perf.value = p).catch(() => {})
  api.figures().then((f: string[]) => { figures.value = f }).catch(() => {})
})
</script>
<template>
  <h2 class="page-title">模型性能评估</h2>
  <p class="page-subtitle">五折 × 十次 = 五十次嵌套交叉验证 · 模型对比与可解释性分析</p>
  <div class="tabs">
    <button v-for="t in tabs" :key="t.id" class="tab" :class="{ active: tab === t.id }" @click="tab = t.id">{{ t.label }}</button>
  </div>

  <div v-if="tab === 'compare'" class="card">
    <div class="card-header"><span class="card-title">模型性能总览</span></div>
    <div class="card-body">
      <table v-if="perf?.cv?.length">
        <thead><tr><th v-for="k in Object.keys(perf.cv[0])" :key="k">{{ k }}</th></tr></thead>
        <tbody><tr v-for="(row,i) in perf.cv" :key="i"><td v-for="(v,k) in row" :key="k">{{ String(v) }}</td></tr></tbody>
      </table>
      <p v-else class="muted">未找到评估结果。</p>
    </div>
  </div>

  <div v-if="tab === 'curves'" class="grid">
    <div class="card" v-for="fig in ['roc_curves.png','pr_curves.png','confusion_matrices.png']" :key="fig">
      <div class="card-header"><span class="card-title">{{ fig.replace('.png','') }}</span></div>
      <div class="card-body"><img v-if="has(fig)" :src="api.figureUrl(fig)" :alt="fig" /><p v-else class="muted">图未生成</p></div>
    </div>
  </div>

  <div v-if="tab === 'calibration'" class="grid">
    <div class="card" v-for="fig in ['calibration_curves.png','decision_curve.png','clinical_impact_curve.png','shap_summary.png']" :key="fig">
      <div class="card-header"><span class="card-title">{{ fig.replace('.png','') }}</span></div>
      <div class="card-body"><img v-if="has(fig)" :src="api.figureUrl(fig)" :alt="fig" /><p v-else class="muted">图未生成</p></div>
    </div>
  </div>

  <div v-if="tab === 'cv'" class="grid">
    <div class="card"><div class="card-header"><span class="card-title">五折 CV ROC（均值 ± 1 SD）</span></div><div class="card-body"><img v-if="has('cv_roc_with_ci.png')" :src="api.figureUrl('cv_roc_with_ci.png')" /><p v-else class="muted">未生成</p></div></div>
    <div class="card"><div class="card-header"><span class="card-title">Bootstrap AUC 分布</span></div><div class="card-body"><img v-if="has('bootstrap_auc_dist.png')" :src="api.figureUrl('bootstrap_auc_dist.png')" /><p v-else class="muted">未生成</p></div></div>
  </div>

  <div v-if="tab === 'ablation'" class="card">
    <div class="card-header"><span class="card-title">特征消融实验</span></div>
    <div class="card-body">
      <img v-if="has('ablation_heatmap.png')" :src="api.figureUrl('ablation_heatmap.png')" />
      <p class="muted" style="margin-top:12px">逐步移除特征组，观察 AUC 变化。</p>
    </div>
  </div>

  <div v-if="tab === 'ensemble'" class="card">
    <div class="card-header"><span class="card-title">集成方法对比</span></div>
    <div class="card-body">
      <img v-if="has('ensemble_comparison.png')" :src="api.figureUrl('ensemble_comparison.png')" />
      <div class="grid grid-3" style="margin-top:16px">
        <div><b>Voting</b><p class="muted">Soft Voting 概率平均，简单稳定</p></div>
        <div><b>Stacking</b><p class="muted">元学习器自动组合基模型</p></div>
        <div><b>Weighted Avg</b><p class="muted">手动/自动分配权重</p></div>
      </div>
    </div>
  </div>
</template>

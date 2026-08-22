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
const FIG_LABELS: Record<string, string> = {
  'roc_curves.png':            'ROC 曲线对比',
  'pr_curves.png':             'PR 曲线（精准率-召回率）',
  'confusion_matrices_cv_oof.jpg': '混淆矩阵（5折 CV OOF）',
  'calibration_curves.png':    '校准曲线',
  'decision_curve.png':        '决策曲线分析 DCA',
  'clinical_impact_curve.png': '临床影响曲线',
  'shap_summary.png':          'SHAP 特征重要性',
  'cv_roc_with_ci.png':        'CV ROC（均值 ± 1 SD）',
  'bootstrap_auc_dist.png':    'Bootstrap AUC 分布',
  'ablation_heatmap.png':      '特征消融热力图',
  'ensemble_comparison.png':   '集成方法对比',
}
const figLabel = (f: string) => FIG_LABELS[f] ?? f.replace('.png', '')
const has = (n: string) => figures.value.includes(n)
const offline = ref(false)
onMounted(() => {
  api.performance().then(p => perf.value = p).catch(() => { offline.value = true })
  api.figures().then((f: string[]) => { figures.value = f }).catch(() => { offline.value = true })
})

// 表格显示：模型列用中文名，数值列取 4 位小数（CSV 原值是 16 位浮点）。
const MODEL_CN: Record<string, string> = {
  LogisticRegression: '逻辑回归 LR',
  RandomForest: '随机森林 RF',
  XGBoost: 'XGBoost',
  ExtraTrees: '极端随机树 ET',
  'Voting Ensemble': '投票集成 Voting',
}
function fmtCell(k: string, v: unknown): string {
  if (v == null || v === '') return '-'
  if (typeof v === 'number') return v.toFixed(4)
  if (k === '模型') return MODEL_CN[String(v)] ?? String(v)
  return String(v)
}
</script>
<template>
  <h2 class="page-title">模型性能评估</h2>
  <p class="page-subtitle">五折 × 十次 = 五十次嵌套交叉验证 · 模型对比与可解释性分析</p>
  <div v-if="offline" class="warning-box">
    ⚠ 无法连接后端或评估产物缺失：请确认服务已启动，且已在受控环境运行过 python run_clean.py 生成 outputs/ 图表。
  </div>
  <div class="tabs">
    <button v-for="t in tabs" :key="t.id" class="tab" :class="{ active: tab === t.id }" @click="tab = t.id">{{ t.label }}</button>
  </div>


  <div v-if="tab === 'compare'">
    <div class="card" style="margin-bottom:16px">
      <div class="card-header"><span class="card-title">模型性能总览（50次嵌套 CV）</span></div>
      <div class="card-body">
        <table v-if="perf?.cv?.length">
          <thead><tr><th v-for="k in Object.keys(perf.cv[0])" :key="k">{{ k }}</th></tr></thead>
          <tbody><tr v-for="(row,i) in perf.cv" :key="i"><td v-for="(v,k) in row" :key="k">{{ fmtCell(String(k), v) }}</td></tr></tbody>
        </table>
        <p v-else class="muted">未找到评估结果。</p>
      </div>
    </div>

    <!-- 混淆矩阵独立展示 -->
    <div class="card">
      <div class="card-header">
        <span class="card-title">混淆矩阵 - 5 折 CV OOF 预测结果</span>
        <span class="muted" style="font-size:10px">各模型在 Out-of-Fold 样本上的分类结果</span>
      </div>
      <div class="card-body" style="text-align:center">
        <img
             v-if="has('confusion_matrices_cv_oof.jpg')"
             :src="api.figureUrl('confusion_matrices_cv_oof.jpg')"
             alt="混淆矩阵"
             style="max-width:100%;max-height:520px;object-fit:contain;border-radius:4px" />
        <p v-else class="muted">图未生成</p>
      </div>
    </div>
  </div>


  <div v-if="tab === 'curves'" class="grid">
    <div class="card" v-for="fig in ['roc_curves.png','pr_curves.png']" :key="fig">
      <div class="card-header"><span class="card-title">{{ figLabel(fig) }}</span></div>
      <div class="card-body">
        <img v-if="has(fig)" :src="api.figureUrl(fig)" :alt="figLabel(fig)"
             style="max-height:360px;object-fit:contain;width:100%" />
        <p v-else class="muted">图未生成</p>
      </div>
    </div>
  </div>

  <div v-if="tab === 'calibration'">
    <div class="grid">
      <div class="card" v-for="fig in ['calibration_curves.png','decision_curve.png','clinical_impact_curve.png','shap_summary.png']" :key="fig">
        <div class="card-header"><span class="card-title">{{ figLabel(fig) }}</span></div>
        <div class="card-body">
          <img v-if="has(fig)" :src="api.figureUrl(fig)" :alt="figLabel(fig)"
               style="max-height:360px;object-fit:contain;width:100%" />
          <p v-else class="muted">图未生成</p>
        </div>
      </div>
    </div>
    <div class="grid grid-2" style="margin-top:16px">
      <!-- 后端早已返回这两张表，此前前端没有消费 -->
      <div class="card">
        <div class="card-header"><span class="card-title">校准指标（5 折 OOF）</span></div>
        <div class="card-body">
          <table v-if="perf?.calibration?.length">
            <thead><tr><th>指标</th><th>数值</th></tr></thead>
            <tbody>
              <tr v-for="(row, i) in perf.calibration" :key="i">
                <td>{{ String(row['metric'] ?? '') }}</td>
                <td>{{ fmtCell('value', row['value']) }}</td>
              </tr>
            </tbody>
          </table>
          <p v-else class="muted">未找到校准指标。</p>
        </div>
      </div>
      <div class="card">
        <div class="card-header">
          <span class="card-title">Hosmer-Lemeshow 分组（20% 测试集近似，n≈84）</span>
        </div>
        <div class="card-body">
          <table v-if="perf?.hosmer_lemeshow?.length">
            <thead><tr><th v-for="k in Object.keys(perf.hosmer_lemeshow[0])" :key="k">{{ k }}</th></tr></thead>
            <tbody>
              <tr v-for="(row, i) in perf.hosmer_lemeshow" :key="i">
                <td v-for="(v, k) in row" :key="k">{{ fmtCell(String(k), v) }}</td>
              </tr>
            </tbody>
          </table>
          <p v-else class="muted">未找到 HL 检验数据。</p>
          <p class="muted" style="font-size:10px;margin-top:8px">
            汇总：chi2=12.053，df=8，P=0.149（LR 简化模型在测试集上的近似复现，样本量小，仅供参考）。
          </p>
        </div>
      </div>
    </div>
  </div>

  <div v-if="tab === 'cv'" class="grid">
    <div class="card">
      <div class="card-header"><span class="card-title">五折 CV ROC（均值 ± 1 SD）</span></div>
      <div class="card-body">
        <img v-if="has('cv_roc_with_ci.png')" :src="api.figureUrl('cv_roc_with_ci.png')"
             style="max-height:360px;object-fit:contain;width:100%" />
        <p v-else class="muted">未生成</p>
      </div>
    </div>
    <div class="card">
      <div class="card-header"><span class="card-title">Bootstrap AUC 分布</span></div>
      <div class="card-body">
        <img v-if="has('bootstrap_auc_dist.png')" :src="api.figureUrl('bootstrap_auc_dist.png')"
             style="max-height:360px;object-fit:contain;width:100%" />
        <p v-else class="muted">未生成</p>
      </div>
    </div>
  </div>

  <div v-if="tab === 'ablation'" class="card">
    <div class="card-header"><span class="card-title">特征消融实验</span></div>
    <div class="card-body" style="text-align:center">
      <img v-if="has('ablation_heatmap.png')" :src="api.figureUrl('ablation_heatmap.png')"
           style="max-height:420px;object-fit:contain;max-width:100%" />
      <p v-else class="muted">图未生成</p>
      <p class="muted" style="margin-top:12px">逐步移除特征组，观察 AUC 变化。</p>
    </div>
  </div>

  <div v-if="tab === 'ensemble'" class="card">
    <div class="card-header"><span class="card-title">集成方法对比</span></div>
    <div class="card-body">
      <img v-if="has('ensemble_comparison.png')" :src="api.figureUrl('ensemble_comparison.png')"
           style="max-height:360px;object-fit:contain;max-width:100%" />
      <p v-else class="muted">图未生成</p>
      <div class="grid grid-3" style="margin-top:16px">
        <div><b>Voting</b><p class="muted">Soft Voting 概率平均，简单稳定</p></div>
        <div><b>Stacking</b><p class="muted">元学习器自动组合基模型</p></div>
        <div><b>Weighted Avg</b><p class="muted">手动/自动分配权重</p></div>
      </div>
    </div>
  </div>
</template>

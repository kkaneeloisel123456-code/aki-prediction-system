<script setup lang="ts">
import ResearchNav from '../components/ResearchNav.vue'
import { computed, onMounted, ref } from 'vue'
import PageHeader from '../components/PageHeader.vue'
import SectionPanel from '../components/SectionPanel.vue'
import EmptyState from '../components/EmptyState.vue'
import PilotTabs from '../components/PilotTabs.vue'
import { api } from '../api/client'
import type { PerformanceResponse } from '../api/types'

type PerfRow = Record<string, unknown>

const tab = ref('compare')
const perf = ref<PerformanceResponse | null>(null)
const figures = ref<string[]>([])
const loading = ref(true)
const offline = ref(false)

const tabs = [
  { value: 'compare', label: '性能对比' },
  { value: 'curves', label: 'ROC / PR' },
  { value: 'calibration', label: '校准 / DCA' },
  { value: 'cv', label: 'CV 可信度' },
  { value: 'ablation', label: '消融实验' },
  { value: 'ensemble', label: '集成对比' },
]

const FIG_LABELS: Record<string, string> = {
  'roc_curves.png': 'ROC 曲线对比',
  'pr_curves.png': 'PR 曲线（精准率—召回率）',
  'confusion_matrices_cv_oof.jpg': '混淆矩阵（5 折 CV OOF）',
  'calibration_curves.png': '校准曲线',
  'decision_curve.png': '决策曲线分析 DCA',
  'clinical_impact_curve.png': '临床影响曲线',
  'shap_summary.png': 'SHAP 特征重要性',
  'cv_roc_with_ci.png': 'CV ROC（均值 ± 1 SD）',
  'bootstrap_auc_dist.png': 'Bootstrap AUC 分布',
  'ablation_heatmap.png': '特征消融热力图',
  'ensemble_comparison.png': '集成方法对比',
}

const MODEL_CN: Record<string, string> = {
  LogisticRegression: '逻辑回归 LR',
  RandomForest: '随机森林 RF',
  XGBoost: 'XGBoost',
  ExtraTrees: '极端随机树 ET',
  'Voting Ensemble': '投票集成 Voting',
}

const SUMMARY_COLUMNS = [
  { key: 'Model', label: '模型' },
  { key: 'OOF AUC', label: 'OOF AUC' },
  { key: '50xCV AUC (mean)', label: '50 次 CV AUC' },
  { key: '50xCV AUC (std)', label: 'CV 标准差' },
  { key: 'Accuracy', label: '准确率' },
  { key: 'Precision', label: '精准率' },
  { key: 'Recall', label: '召回率' },
  { key: 'F1', label: 'F1' },
]

const CV_COLUMNS = [
  { key: '模型', label: '模型' },
  { key: '50次CV AUC均值', label: '50 次 CV AUC' },
  { key: '标准差', label: '标准差' },
]

const CAL_LABELS: Record<string, string> = {
  Brier_raw: 'Brier（原始）',
  Brier_calibrated_OOF: 'Brier（OOF 校准）',
  Expected_positive_raw: '期望阳性（原始）',
  Observed_positive: '实际阳性',
}

const summaryRows = computed<PerfRow[]>(() =>
  (perf.value?.summary as PerfRow[] | undefined) ?? [],
)
const cvRows = computed<PerfRow[]>(() =>
  (perf.value?.cv as PerfRow[] | undefined) ?? [],
)
const calibrationRows = computed<PerfRow[]>(() =>
  (perf.value?.calibration as PerfRow[] | undefined) ?? [],
)
const hlRows = computed<PerfRow[]>(() =>
  (perf.value?.hosmer_lemeshow as PerfRow[] | undefined) ?? [],
)
const hlColumns = computed(() => hlRows.value.length ? Object.keys(hlRows.value[0]) : [])

const modelRows = computed(() => summaryRows.value.length ? summaryRows.value : cvRows.value)
const modelCount = computed(() => modelRows.value.length)
const bestAuc = computed<number | null>(() => {
  let best: number | null = null
  for (const row of modelRows.value) {
    const raw = row['50xCV AUC (mean)'] ?? row['50次CV AUC均值'] ?? row['OOF AUC']
    const value = Number(raw)
    if (Number.isFinite(value) && (best === null || value > best)) best = value
  }
  return best
})
const bestModel = computed(() => {
  if (bestAuc.value === null) return null
  const row = modelRows.value.find((item) => {
    const raw = item['50xCV AUC (mean)'] ?? item['50次CV AUC均值'] ?? item['OOF AUC']
    return Number(raw) === bestAuc.value
  })
  return row ? modelName(String(row.Model ?? row['模型'] ?? '')) : null
})

const showSummaryTable = computed(() => summaryRows.value.length > 0)
const tableColumns = computed(() => showSummaryTable.value ? SUMMARY_COLUMNS : CV_COLUMNS)

const figLabel = (file: string) => FIG_LABELS[file] ?? file.replace(/\.(png|jpg|webp)$/i, '')
const has = (name: string) => figures.value.includes(name)
const modelName = (name: string) => MODEL_CN[name] ?? name
const calLabel = (name: string) => CAL_LABELS[name] ?? name

function fmtCell(key: string, value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'number') {
    if (['组', '样本数', '观测阳性'].includes(key) && Number.isInteger(value)) return String(value)
    if (key === '期望阳性') return value.toFixed(1)
    return value.toFixed(4)
  }
  if (key === 'Model' || key === '模型') return modelName(String(value))
  return String(value)
}

function calValue(metric: string, value: unknown): string {
  if (typeof value !== 'number') return '—'
  if (metric === 'Expected_positive_raw' || metric === 'Observed_positive') {
    return Number.isInteger(value) ? String(value) : value.toFixed(1)
  }
  return value.toFixed(4)
}

async function load() {
  loading.value = true
  offline.value = false
  try {
    const [performance, figureNames] = await Promise.all([api.performance(), api.figures()])
    perf.value = performance
    figures.value = figureNames
  } catch {
    offline.value = true
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
        kicker="科研与维护"
        title="研究验证"
        description="50 次嵌套 CV · 模型对比、校准与消融"
      >
        <template #actions>
          <button class="pilot-btn" type="button" :disabled="loading" @click="load">
            {{ loading ? '读取中…' : '刷新' }}
          </button>
        </template>
      </PageHeader>
      <ResearchNav />

      <div v-if="offline" class="pilot-error" role="alert">
        无法连接后端或评估产物缺失。请确认服务已启动，并已在受控环境生成评估图表。
      </div>

      <div class="perf-summary" aria-label="模型评估概览">
        <div class="perf-summary-item">
          <span class="pilot-section-label">参与比较</span>
          <strong>{{ modelCount || '—' }}</strong>
          <small>个模型</small>
        </div>
        <div class="perf-summary-item">
          <span class="pilot-section-label">验证强度</span>
          <strong>50</strong>
          <small>次嵌套交叉验证</small>
        </div>
        <div class="perf-summary-item">
          <span class="pilot-section-label">最佳 50×CV AUC</span>
          <strong>{{ bestAuc === null ? '—' : bestAuc.toFixed(4) }}</strong>
          <small>{{ bestModel || '暂无结果' }}</small>
        </div>
        <div class="perf-summary-item">
          <span class="pilot-section-label">校准指标</span>
          <strong>{{ calibrationRows.length || '—' }}</strong>
          <small>项 Brier / 阳性计数</small>
        </div>
      </div>

      <PilotTabs v-model="tab" :tabs="tabs" label="研究验证分区" />

      <div v-if="loading" class="pilot-stack" aria-label="正在加载评估结果">
        <div class="pilot-skeleton perf-skeleton" />
        <div class="pilot-skeleton perf-skeleton perf-skeleton-short" />
      </div>

      <div v-else class="pilot-stack">
        <template v-if="tab === 'compare'">
          <SectionPanel
            title="模型性能总览"
            :subtitle="showSummaryTable ? 'OOF 与 50 次嵌套 CV · 指标保留 4 位小数' : '50 次嵌套 CV · AUC 均值与标准差'"
            flush
          >
            <EmptyState
              v-if="!modelRows.length"
              title="未找到评估结果"
              description="确认 outputs/ 中已经生成模型对比结果，再刷新本页。"
            />
            <div v-else class="perf-table-wrap" role="region" aria-label="模型性能表，窄屏可横向滚动" tabindex="0">
              <div class="perf-mobile-hint">左右滑动查看完整表格</div>
              <table class="pilot-table perf-table">
                <thead>
                  <tr>
                    <th v-for="column in tableColumns" :key="column.key" scope="col">{{ column.label }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, index) in modelRows" :key="String(row.Model ?? row['模型'] ?? index)">
                    <td v-for="column in tableColumns" :key="column.key" :class="{ 'cell-strong': column.key === 'Model' || column.key === '模型' }">
                      {{ fmtCell(column.key, row[column.key]) }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </SectionPanel>

          <SectionPanel
            title="混淆矩阵"
            subtitle="各模型在 Out-of-Fold 样本上的分类结果"
          >
            <div class="perf-figure-frame">
              <img
                v-if="has('confusion_matrices_cv_oof.jpg')"
                :src="api.figureUrl('confusion_matrices_cv_oof.jpg')"
                class="perf-figure perf-figure-tall"
                alt="混淆矩阵，5 折 CV OOF 预测结果"
              >
              <EmptyState v-else title="图未生成" description="生成混淆矩阵后刷新本页。" />
            </div>
          </SectionPanel>
        </template>

        <div v-else-if="tab === 'curves'" class="perf-grid-2">
          <SectionPanel v-for="figure in ['roc_curves.png', 'pr_curves.png']" :key="figure" :title="figLabel(figure)">
            <img
              v-if="has(figure)"
              :src="api.figureUrl(figure)"
              class="perf-figure"
              :alt="figLabel(figure)"
            >
            <EmptyState v-else title="图未生成" :description="`${figLabel(figure)} 尚未生成。`" />
          </SectionPanel>
        </div>

        <template v-else-if="tab === 'calibration'">
          <div class="perf-grid-2">
            <SectionPanel
              v-for="figure in ['calibration_curves.png', 'decision_curve.png', 'clinical_impact_curve.png', 'shap_summary.png']"
              :key="figure"
              :title="figLabel(figure)"
            >
              <img
                v-if="has(figure)"
                :src="api.figureUrl(figure)"
                class="perf-figure"
                :alt="figLabel(figure)"
              >
              <EmptyState v-else title="图未生成" :description="`${figLabel(figure)} 尚未生成。`" />
            </SectionPanel>
          </div>

          <div class="perf-grid-2">
            <SectionPanel title="校准指标" subtitle="5 折 OOF">
              <EmptyState v-if="!calibrationRows.length" title="未找到校准指标" description="生成校准结果后刷新本页。" />
              <table v-else class="pilot-table perf-small-table">
                <thead><tr><th scope="col">指标</th><th scope="col">数值</th></tr></thead>
                <tbody>
                  <tr v-for="row in calibrationRows" :key="String(row.metric)">
                    <td>{{ calLabel(String(row.metric)) }}</td>
                    <td class="perf-number">{{ calValue(String(row.metric), row.value) }}</td>
                  </tr>
                </tbody>
              </table>
            </SectionPanel>

            <SectionPanel title="Hosmer–Lemeshow 分组" subtitle="20% 测试集近似，n≈84">
              <EmptyState v-if="!hlRows.length" title="未找到 HL 检验数据" description="生成 HL 分组后刷新本页。" />
              <template v-else>
                <div class="perf-table-wrap" role="region" aria-label="HL 分组表，窄屏可横向滚动" tabindex="0">
                  <table class="pilot-table perf-table perf-hl-table">
                    <thead>
                      <tr><th v-for="key in hlColumns" :key="key" scope="col">{{ key }}</th></tr>
                    </thead>
                    <tbody>
                      <tr v-for="(row, index) in hlRows" :key="index">
                        <td v-for="key in hlColumns" :key="key">{{ fmtCell(key, row[key]) }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <p class="perf-note">
                  汇总：chi2=12.053，df=8，P=0.149。LR 简化模型在测试集上的近似复现，样本量小，仅供参考。
                </p>
              </template>
            </SectionPanel>
          </div>
        </template>

        <div v-else-if="tab === 'cv'" class="perf-grid-2">
          <SectionPanel title="五折 CV ROC" subtitle="均值 ± 1 SD">
            <img v-if="has('cv_roc_with_ci.png')" :src="api.figureUrl('cv_roc_with_ci.png')" class="perf-figure" alt="五折 CV ROC 曲线">
            <EmptyState v-else title="图未生成" description="生成 CV ROC 曲线后刷新本页。" />
          </SectionPanel>
          <SectionPanel title="Bootstrap AUC 分布" subtitle="重采样稳定性">
            <img v-if="has('bootstrap_auc_dist.png')" :src="api.figureUrl('bootstrap_auc_dist.png')" class="perf-figure" alt="Bootstrap AUC 分布">
            <EmptyState v-else title="图未生成" description="生成 Bootstrap 分布后刷新本页。" />
          </SectionPanel>
        </div>

        <SectionPanel v-else-if="tab === 'ablation'" title="特征消融实验">
          <div class="perf-figure-frame">
            <img v-if="has('ablation_heatmap.png')" :src="api.figureUrl('ablation_heatmap.png')" class="perf-figure perf-figure-tall" alt="特征消融热力图">
            <EmptyState v-else title="图未生成" description="生成消融热力图后刷新本页。" />
          </div>
          <p class="perf-note">逐步移除特征组，观察 AUC 变化。</p>
        </SectionPanel>

        <SectionPanel v-else-if="tab === 'ensemble'" title="集成方法对比">
          <div class="perf-figure-frame">
            <img v-if="has('ensemble_comparison.png')" :src="api.figureUrl('ensemble_comparison.png')" class="perf-figure" alt="集成方法对比">
            <EmptyState v-else title="图未生成" description="生成集成对比图后刷新本页。" />
          </div>
          <div class="perf-ensemble-notes">
            <div><strong>Voting</strong><p>Soft Voting 概率平均，简单稳定。</p></div>
            <div><strong>Stacking</strong><p>元学习器自动组合基模型。</p></div>
            <div><strong>Weighted Avg</strong><p>手动或自动分配权重。</p></div>
          </div>
        </SectionPanel>
      </div>
    </div>
  </div>
</template>

<style scoped>
.perf-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin-bottom: var(--pilot-space-5);
  overflow: hidden;
  border: 1px solid var(--pilot-line);
  border-radius: var(--pilot-radius-card);
  background: var(--pilot-surface);
}
.perf-summary-item {
  min-width: 0;
  padding: var(--pilot-space-4) var(--pilot-space-4);
  border-right: 1px solid var(--pilot-line);
}
.perf-summary-item:last-child { border-right: 0; }
.perf-summary-item strong {
  display: block;
  margin-top: var(--pilot-space-1);
  color: var(--pilot-ink);
  font-size: var(--pilot-font-lg);
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
}
.perf-summary-item small {
  display: block;
  min-height: 16px;
  margin-top: var(--pilot-space-1);
  overflow: hidden;
  color: var(--pilot-muted);
  font-size: var(--pilot-font-xs);
  text-overflow: ellipsis;
  white-space: nowrap;
}
.perf-grid-2 {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--pilot-space-4);
}
.perf-figure-frame { min-width: 0; }
.perf-figure {
  display: block;
  width: 100%;
  max-height: 380px;
  border: 1px solid var(--pilot-line);
  border-radius: var(--pilot-radius-control);
  background: var(--pilot-surface-2);
  object-fit: contain;
}
.perf-figure-tall { max-height: 520px; }
.perf-table-wrap {
  max-width: 100%;
  overflow-x: auto;
}
.perf-table { min-width: 900px; }
.perf-table th,
.perf-table td { white-space: nowrap; }
.perf-small-table { min-width: 0; }
.perf-small-table .perf-number { text-align: right; font-variant-numeric: tabular-nums; }
.perf-hl-table { min-width: 460px; }
.perf-note {
  margin: var(--pilot-space-3) 0 0;
  color: var(--pilot-muted);
  font-size: var(--pilot-font-xs);
  line-height: 1.6;
}
.perf-mobile-hint {
  display: none;
  padding: var(--pilot-space-2) var(--pilot-space-4);
  color: var(--pilot-muted);
  font-size: var(--pilot-font-xs);
}
.perf-ensemble-notes {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--pilot-space-4);
  margin-top: var(--pilot-space-4);
  padding-top: var(--pilot-space-4);
  border-top: 1px solid var(--pilot-line);
}
.perf-ensemble-notes strong { color: var(--pilot-ink); }
.perf-ensemble-notes p {
  margin-top: var(--pilot-space-1);
  color: var(--pilot-muted);
  font-size: var(--pilot-font-xs);
}
.perf-skeleton { height: 240px; }
.perf-skeleton-short { height: 120px; }
@media (max-width: 900px) {
  .perf-grid-2 { grid-template-columns: minmax(0, 1fr); }
  .perf-ensemble-notes { grid-template-columns: minmax(0, 1fr); gap: var(--pilot-space-2); }
}
@media (max-width: 650px) {
  .perf-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .perf-summary-item:nth-child(2) { border-right: 0; }
  .perf-summary-item:nth-child(-n+2) { border-bottom: 1px solid var(--pilot-line); }
  .perf-summary-item { padding: var(--pilot-space-3); }
  .perf-summary-item strong { font-size: var(--pilot-font-md); }
  .perf-table { min-width: 780px; }
  .perf-mobile-hint { display: block; }
  .perf-figure { max-height: 300px; }
}
</style>

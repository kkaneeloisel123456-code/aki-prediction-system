<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import PageHeader from '../components/PageHeader.vue'
import SectionPanel from '../components/SectionPanel.vue'
import EmptyState from '../components/EmptyState.vue'
import StatusPill from '../components/StatusPill.vue'
import PilotTabs from '../components/PilotTabs.vue'
import { api } from '../api/client'

type ImpRow = { feature: string; median: number | null }

const tab = ref('flow')
const tabs = [
  { value: 'flow', label: '治理流程' },
  { value: 'quality', label: '缺失值查询' },
  { value: 'dashboard', label: '质量仪表盘' },
]

const figures = ref<string[]>([])
const figuresError = ref(false)

const funnelSlides = [
  { key: 'funnel_data.webp', label: '数据' },
  { key: 'funnel_modeling.webp', label: '建模' },
  { key: 'funnel_web.webp', label: 'Web 系统概览' },
]
const funnelIdx = ref(0)

const impRows = ref<ImpRow[]>([])
const impSearch = ref('')
const impLoading = ref(false)
const impError = ref(false)

const filteredRows = computed(() => {
  const query = impSearch.value.trim().toLowerCase()
  return query
    ? impRows.value.filter((row) => row.feature.toLowerCase().includes(query))
    : impRows.value
})

const dashboardData = ref<any>(null)
const dashboardError = ref('')
const dashboardLoading = ref(false)

const akiShare = computed(() => {
  const balance = dashboardData.value?.classBalance
  if (!balance) return 0
  const total = Number(balance.aki) + Number(balance.nonAki)
  return total > 0 ? (Number(balance.aki) / total) * 100 : 0
})

const typePieStyle = computed(() => {
  const types = dashboardData.value?.dataTypes
  if (!types) return ''
  const float64 = Number(types.float64) || 0
  const int64 = Number(types.int64) || 0
  const object = Number(types.object) || 0
  const total = float64 + int64 + object
  if (!total) return ''
  const first = (float64 / total) * 100
  const second = first + (int64 / total) * 100
  return `conic-gradient(var(--pilot-accent) 0% ${first}%, var(--pilot-mid) ${first}% ${second}%, var(--pilot-high) ${second}% 100%)`
})

const has = (name: string) => figures.value.includes(name)

async function load() {
  figuresError.value = false
  impLoading.value = true
  dashboardLoading.value = true

  const figuresPromise = api.figures()
    .then((result: string[]) => { figures.value = result })
    .catch(() => { figuresError.value = true })

  const imputationPromise = api.imputation()
    .then((result) => { impRows.value = result.features })
    .catch(() => { impError.value = true })
    .finally(() => { impLoading.value = false })

  const qualityPromise = api.dataQuality()
    .then((result) => { dashboardData.value = result })
    .catch(() => { dashboardError.value = '质量数据加载失败' })
    .finally(() => { dashboardLoading.value = false })

  await Promise.allSettled([figuresPromise, imputationPromise, qualityPromise])
}

function funnelNext(delta: number) {
  funnelIdx.value = (funnelIdx.value + delta + funnelSlides.length) % funnelSlides.length
}

onMounted(load)
</script>

<template>
  <div class="pilot-page">
    <div class="pilot-page-inner">
      <PageHeader
        kicker="系统 / 数据"
        title="数据治理"
        description="从原始数据到建模数据集的完整处理管线 · 35 项特征"
      >
        <template #actions>
          <button class="pilot-btn" type="button" :disabled="impLoading || dashboardLoading" @click="load">刷新</button>
        </template>
      </PageHeader>

      <div v-if="figuresError" class="pilot-error" role="alert">
        评估图表索引加载失败；治理图表可能无法显示，其它数据仍可查看。
      </div>

      <PilotTabs v-model="tab" :tabs="tabs" label="数据治理分区" />

      <div v-if="tab === 'flow'" class="pilot-stack">
        <SectionPanel title="AKI 系统核心模块" subtitle="从数据治理到临床随访的业务链路">
          <div class="gov-figure-frame">
            <img
              v-if="has('aki_core_modules.webp')"
              :src="api.figureUrl('aki_core_modules.webp')"
              class="gov-figure gov-figure-modules"
              alt="AKI 系统核心模块总览"
            >
            <EmptyState v-else title="图未生成" description="核心模块总览图尚未生成，刷新后重试。" />
          </div>
        </SectionPanel>

        <SectionPanel title="特征筛选漏斗" subtitle="从原始数据到建模数据集的筛选项">
          <div class="gov-funnel-switch" role="group" aria-label="特征筛选漏斗视图">
            <button
              v-for="(slide, index) in funnelSlides"
              :key="slide.key"
              type="button"
              class="gov-funnel-tab"
              :class="{ 'is-active': funnelIdx === index }"
              :aria-pressed="funnelIdx === index"
              @click="funnelIdx = index"
            >{{ slide.label }}</button>
          </div>

          <div v-if="has(funnelSlides[funnelIdx].key)" class="gov-funnel-stage">
            <img
              :src="api.figureUrl(funnelSlides[funnelIdx].key)"
              class="gov-figure gov-figure-funnel"
              :alt="`特征筛选漏斗：${funnelSlides[funnelIdx].label}`"
            >
            <button class="gov-funnel-arrow is-left" type="button" aria-label="上一张漏斗图" @click="funnelNext(-1)">‹</button>
            <button class="gov-funnel-arrow is-right" type="button" aria-label="下一张漏斗图" @click="funnelNext(1)">›</button>
          </div>
          <EmptyState v-else title="图未生成" description="特征筛选漏斗图尚未生成，刷新后重试。" />

          <p class="gov-funnel-caption">{{ funnelIdx + 1 }} / {{ funnelSlides.length }}</p>
        </SectionPanel>
      </div>

      <div v-else-if="tab === 'quality'">
        <SectionPanel
          title="特征缺失值 / 训练中位数"
          :subtitle="`${impRows.length} 个特征 · 数据来自训练集填充值`"
          flush
        >
          <div class="gov-toolbar">
            <label class="gov-search">
              <span class="gov-search-icon" aria-hidden="true"></span>
              <input
                v-model="impSearch"
                class="pilot-input"
                type="search"
                aria-label="搜索特征名"
                placeholder="搜索特征名…"
              >
            </label>
            <span class="pilot-small">显示 {{ filteredRows.length }} 项</span>
          </div>

          <div v-if="impLoading" class="gov-loading" aria-label="正在加载缺失值数据">
            <div v-for="i in 4" :key="i" class="pilot-skeleton gov-skeleton-row" />
          </div>
          <div v-else-if="impError" class="gov-inline-error">加载失败，请确认后端服务已启动。</div>
          <EmptyState
            v-else-if="!filteredRows.length"
            title="没有匹配的特征"
            description="换一个特征名，或清除搜索查看全部中位数填充值。"
          >
            <button v-if="impSearch.trim()" class="pilot-btn" type="button" @click="impSearch = ''">清除搜索</button>
          </EmptyState>
          <div v-else class="gov-table-wrap" role="region" aria-label="特征中位数表，窄屏可横向滚动" tabindex="0">
            <div class="gov-mobile-hint">左右滑动查看完整表格</div>
            <table class="pilot-table gov-table">
              <thead>
                <tr>
                  <th scope="col">#</th>
                  <th scope="col">特征名</th>
                  <th scope="col" class="gov-number">训练集中位数（填充值）</th>
                  <th scope="col">状态</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, index) in filteredRows" :key="row.feature">
                  <td class="gov-index">{{ index + 1 }}</td>
                  <td class="cell-strong">{{ row.feature }}</td>
                  <td class="gov-number">{{ row.median !== null ? Number(row.median).toFixed(4) : '—' }}</td>
                  <td>
                    <StatusPill
                      :label="row.median !== null ? '有填充值' : '无'"
                      :tone="row.median !== null ? 'low' : 'high'"
                    />
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p class="gov-note">当患者预测时某字段未录入，系统会使用对应训练集中位数代替。搜索只匹配特征名。</p>
        </SectionPanel>
      </div>

      <div v-else>
        <div v-if="dashboardError" class="pilot-error" role="alert">{{ dashboardError }}</div>

        <div v-if="dashboardLoading" class="gov-dashboard-loading" aria-label="正在加载质量仪表盘">
          <div class="pilot-skeleton gov-stat-skeleton" />
          <div class="pilot-skeleton gov-dashboard-skeleton" />
        </div>

        <div v-else-if="dashboardData" class="pilot-stack">
          <div class="gov-stat-strip" aria-label="数据质量概览">
            <div class="gov-stat">
              <span class="pilot-section-label">总样本量</span>
              <strong>{{ dashboardData.stats.samples }}</strong>
              <small>条记录</small>
            </div>
            <div class="gov-stat">
              <span class="pilot-section-label">模型特征数</span>
              <strong>{{ dashboardData.stats.features }}</strong>
              <small>项进入模型</small>
            </div>
            <div class="gov-stat">
              <span class="pilot-section-label">数据完整性</span>
              <strong>{{ dashboardData.stats.completeness || dashboardData.stats.missingRate }}</strong>
              <small>缺失率 {{ dashboardData.stats.missingRate }}</small>
            </div>
            <div class="gov-stat">
              <span class="pilot-section-label">重复记录</span>
              <strong>{{ dashboardData.stats.duplicates }}</strong>
              <small>条重复</small>
            </div>
          </div>

          <div class="gov-dashboard-grid">
            <SectionPanel title="字段完整率" subtitle="低于 100% 的字段">
              <EmptyState
                v-if="!dashboardData.completenessRates?.length"
                title="所有字段均无缺失"
                description="当前数据完整性为 100%。"
              />
              <div v-else class="gov-bars">
                <div v-for="item in dashboardData.completenessRates" :key="item.feature" class="gov-bar-row">
                  <div class="gov-bar-meta">
                    <span>{{ item.feature }}</span>
                    <strong>{{ Number(item.rate).toFixed(1) }}%</strong>
                  </div>
                  <div class="gov-bar-track">
                    <div class="gov-bar-fill" :style="{ width: `${Math.max(0, Math.min(100, Number(item.rate)))}%` }" />
                  </div>
                </div>
                <p class="gov-note">缺失值在预测时使用训练集中位数自动填充。</p>
              </div>
            </SectionPanel>

            <SectionPanel title="样本分类均衡" subtitle="AKI 与 Non-AKI">
              <div class="gov-balance">
                <div class="gov-balance-head">
                  <span class="is-high">AKI {{ dashboardData.classBalance.aki }}</span>
                  <span class="is-low">Non-AKI {{ dashboardData.classBalance.nonAki }}</span>
                </div>
                <div class="gov-balance-track">
                  <div class="gov-balance-aki" :style="{ width: `${akiShare}%` }" />
                  <div class="gov-balance-nonaki" :style="{ width: `${100 - akiShare}%` }" />
                </div>
                <div class="gov-balance-foot">
                  <span>阳性率 {{ akiShare.toFixed(1) }}%</span>
                  <span>共 {{ dashboardData.classBalance.aki + dashboardData.classBalance.nonAki }} 例</span>
                </div>
              </div>
            </SectionPanel>

            <SectionPanel title="字段数据类型" subtitle="原始数据表">
              <div class="gov-types">
                <div class="gov-pie" :style="{ background: typePieStyle }" aria-hidden="true" />
                <div class="gov-type-legend">
                  <div><i class="is-float" /> <span>Float64</span> <strong>{{ dashboardData.dataTypes.float64 }}</strong></div>
                  <div><i class="is-int" /> <span>Int64</span> <strong>{{ dashboardData.dataTypes.int64 }}</strong></div>
                  <div><i class="is-object" /> <span>Object</span> <strong>{{ dashboardData.dataTypes.object }}</strong></div>
                </div>
              </div>
            </SectionPanel>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.gov-figure-frame { min-width: 0; }
.gov-figure {
  display: block;
  width: 100%;
  max-height: 560px;
  border: 1px solid var(--pilot-line);
  border-radius: var(--pilot-radius-control);
  background: var(--pilot-surface-2);
  object-fit: contain;
}
.gov-figure-modules { max-height: 620px; }
.gov-figure-funnel { max-height: 520px; }
.gov-funnel-switch {
  display: flex;
  flex-wrap: wrap;
  gap: var(--pilot-space-2);
  margin-bottom: var(--pilot-space-4);
}
.gov-funnel-tab {
  min-height: 32px;
  padding: 0 var(--pilot-space-3);
  border: 1px solid var(--pilot-line);
  border-radius: var(--pilot-radius-pill);
  background: transparent;
  color: var(--pilot-muted);
  font: inherit;
  font-size: var(--pilot-font-xs);
  cursor: pointer;
}
.gov-funnel-tab:hover { color: var(--pilot-ink); background: var(--pilot-hover); }
.gov-funnel-tab.is-active {
  border-color: var(--pilot-accent);
  background: var(--pilot-accent-soft);
  color: var(--pilot-accent);
}
.gov-funnel-tab:focus-visible { outline: 2px solid var(--pilot-accent); outline-offset: 1px; }
.gov-funnel-stage {
  position: relative;
  width: 100%;
}
.gov-funnel-arrow {
  position: absolute;
  top: 50%;
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border: 0;
  border-radius: 50%;
  background: var(--pilot-ink);
  color: var(--pilot-surface);
  font: inherit;
  font-size: 20px;
  line-height: 1;
  opacity: .65;
  cursor: pointer;
  transform: translateY(-50%);
}
.gov-funnel-arrow:hover { opacity: 1; }
.gov-funnel-arrow.is-left { left: var(--pilot-space-2); }
.gov-funnel-arrow.is-right { right: var(--pilot-space-2); }
.gov-funnel-caption {
  margin-top: var(--pilot-space-2);
  color: var(--pilot-muted);
  font-size: var(--pilot-font-xs);
  text-align: center;
}
.gov-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--pilot-space-3);
  padding: var(--pilot-space-3) var(--pilot-space-4);
  border-bottom: 1px solid var(--pilot-line);
}
.gov-search {
  position: relative;
  display: flex;
  align-items: center;
  flex: 1;
  max-width: 360px;
}
.gov-search-icon {
  position: absolute;
  left: 14px;
  top: 50%;
  width: 11px;
  height: 11px;
  border: 1.5px solid var(--pilot-muted);
  border-radius: 50%;
  transform: translateY(-50%);
  pointer-events: none;
}
.gov-search-icon::after {
  content: "";
  position: absolute;
  right: -4px;
  bottom: -3px;
  width: 6px;
  height: 1.5px;
  background: var(--pilot-muted);
  transform: rotate(45deg);
  transform-origin: left center;
}
.gov-search .pilot-input { padding-left: 36px; }
.gov-table-wrap { max-width: 100%; overflow-x: auto; }
.gov-table { min-width: 560px; }
.gov-table .gov-number { text-align: right; font-variant-numeric: tabular-nums; }
.gov-table .gov-index { color: var(--pilot-muted); }
.gov-mobile-hint {
  display: none;
  padding: var(--pilot-space-2) var(--pilot-space-4);
  color: var(--pilot-muted);
  font-size: var(--pilot-font-xs);
}
.gov-note {
  margin: var(--pilot-space-3) var(--pilot-space-4) var(--pilot-space-1);
  color: var(--pilot-muted);
  font-size: var(--pilot-font-xs);
  line-height: 1.6;
}
.gov-loading { padding: var(--pilot-space-4); }
.gov-skeleton-row { height: 32px; margin-bottom: var(--pilot-space-2); }
.gov-inline-error {
  padding: var(--pilot-space-6) var(--pilot-space-4);
  color: var(--pilot-high);
  font-size: var(--pilot-font-sm);
  text-align: center;
}
.gov-stat-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  overflow: hidden;
  border: 1px solid var(--pilot-line);
  border-radius: var(--pilot-radius-card);
  background: var(--pilot-surface);
}
.gov-stat {
  min-width: 0;
  padding: var(--pilot-space-4);
  border-right: 1px solid var(--pilot-line);
}
.gov-stat:last-child { border-right: 0; }
.gov-stat strong {
  display: block;
  margin-top: var(--pilot-space-1);
  color: var(--pilot-ink);
  font-size: var(--pilot-font-lg);
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
}
.gov-stat small {
  display: block;
  min-height: 16px;
  margin-top: var(--pilot-space-1);
  color: var(--pilot-muted);
  font-size: var(--pilot-font-xs);
}
.gov-dashboard-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr) minmax(0, .95fr);
  gap: var(--pilot-space-4);
  align-items: stretch;
}
.gov-bars { display: grid; gap: var(--pilot-space-3); }
.gov-bar-meta {
  display: flex;
  justify-content: space-between;
  gap: var(--pilot-space-3);
  margin-bottom: var(--pilot-space-1);
  color: var(--pilot-ink-soft);
  font-size: var(--pilot-font-xs);
}
.gov-bar-meta strong { color: var(--pilot-low); font-variant-numeric: tabular-nums; }
.gov-bar-track {
  height: 6px;
  overflow: hidden;
  border-radius: 3px;
  background: var(--pilot-surface-2);
}
.gov-bar-fill { height: 100%; border-radius: 3px; background: var(--pilot-low); }
.gov-balance { padding: var(--pilot-space-1) 0; }
.gov-balance-head {
  display: flex;
  justify-content: space-between;
  gap: var(--pilot-space-2);
  margin-bottom: var(--pilot-space-2);
  font-size: var(--pilot-font-xs);
  font-weight: 600;
}
.gov-balance-head .is-high { color: var(--pilot-high); }
.gov-balance-head .is-low { color: var(--pilot-low); }
.gov-balance-track {
  display: flex;
  height: 12px;
  overflow: hidden;
  border-radius: var(--pilot-radius-pill);
  background: var(--pilot-surface-2);
}
.gov-balance-aki { background: var(--pilot-high); }
.gov-balance-nonaki { background: var(--pilot-low); }
.gov-balance-foot {
  display: flex;
  justify-content: space-between;
  gap: var(--pilot-space-2);
  margin-top: var(--pilot-space-2);
  color: var(--pilot-muted);
  font-size: var(--pilot-font-xs);
}
.gov-types {
  display: flex;
  align-items: center;
  gap: var(--pilot-space-5);
}
.gov-pie {
  width: 96px;
  height: 96px;
  flex: 0 0 96px;
  border: 1px solid var(--pilot-line);
  border-radius: 50%;
}
.gov-type-legend {
  display: grid;
  flex: 1;
  gap: var(--pilot-space-2);
  min-width: 0;
  font-size: var(--pilot-font-xs);
}
.gov-type-legend > div { display: flex; align-items: center; gap: var(--pilot-space-2); }
.gov-type-legend i { width: 8px; height: 8px; flex: 0 0 8px; border-radius: 50%; }
.gov-type-legend i.is-float { background: var(--pilot-accent); }
.gov-type-legend i.is-int { background: var(--pilot-mid); }
.gov-type-legend i.is-object { background: var(--pilot-high); }
.gov-type-legend span { flex: 1; color: var(--pilot-ink-soft); }
.gov-type-legend strong { color: var(--pilot-ink); font-variant-numeric: tabular-nums; }
.gov-stat-skeleton { height: 96px; }
.gov-dashboard-skeleton { height: 320px; }
@media (max-width: 1024px) {
  .gov-dashboard-grid { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
  .gov-dashboard-grid > :last-child { grid-column: 1 / -1; }
}
@media (max-width: 650px) {
  .gov-stat-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .gov-stat:nth-child(2) { border-right: 0; }
  .gov-stat:nth-child(-n+2) { border-bottom: 1px solid var(--pilot-line); }
  .gov-stat { padding: var(--pilot-space-3); }
  .gov-stat strong { font-size: var(--pilot-font-md); }
  .gov-dashboard-grid { grid-template-columns: minmax(0, 1fr); }
  .gov-dashboard-grid > :last-child { grid-column: auto; }
  .gov-toolbar { align-items: stretch; flex-direction: column; }
  .gov-search { max-width: none; }
  .gov-table { min-width: 520px; }
  .gov-mobile-hint { display: block; }
  .gov-types { gap: var(--pilot-space-4); }
  .gov-pie { width: 80px; height: 80px; flex-basis: 80px; }
  .gov-note { margin-inline: var(--pilot-space-3); }
}
</style>

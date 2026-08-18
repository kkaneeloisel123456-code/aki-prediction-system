<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api } from '../api/client'

const tab = ref('flow')
const figures = ref<string[]>([])
const tabs = [
  { id: 'flow',     label: '治理流程' },
  { id: 'quality',  label: '缺失值查询' },
  { id: 'dashboard',label: '质量仪表盘' },
]
const has = (n: string) => figures.value.includes(n)

// 特征筛选漏斗轮播：数据 / 建模 / Web系统概览
const funnelSlides = [
  { key: 'funnel_data.png',     label: '数据' },
  { key: 'funnel_modeling.png', label: '建模' },
  { key: 'funnel_web.png',      label: 'Web系统概览' },
]
const funnelIdx = ref(0)

// 缺失值 / 填充中位数 查询
type ImpRow = { feature: string; median: number | null }
const impRows   = ref<ImpRow[]>([])
const impSearch = ref('')
const impLoading = ref(false)
const impError   = ref(false)

const filteredRows = computed(() => {
  const q = impSearch.value.trim().toLowerCase()
  return q
    ? impRows.value.filter(r => r.feature.toLowerCase().includes(q))
    : impRows.value
})

const dashboardData = ref<any>(null)
const dashboardError = ref('')
const dashboardLoading = ref(false)

const typePieStyle = computed(() => {
  if (!dashboardData.value) return ''
  const t = dashboardData.value.dataTypes
  const total = t.float64 + t.int64 + t.object
  if (total === 0) return ''
  const p1 = (t.float64 / total) * 100
  const p2 = p1 + (t.int64 / total) * 100
  return `conic-gradient(var(--primary) 0% ${p1}%, var(--yellow) ${p1}% ${p2}%, var(--red) ${p2}% 100%)`
})

onMounted(() => {
  api.figures().then((f: string[]) => { figures.value = f }).catch(() => {})
  impLoading.value = true
  api.imputation()
    .then(d => { impRows.value = d.features })
    .catch(() => { impError.value = true })
    .finally(() => { impLoading.value = false })

  dashboardLoading.value = true
  api.dataQuality()
    .then((d: any) => { dashboardData.value = d })
    .catch(() => { dashboardError.value = '质量数据加载失败' })
    .finally(() => { dashboardLoading.value = false })
})
</script>
<template>
  <h2 class="page-title">数据治理</h2>
  <p class="page-subtitle">从原始数据到建模数据集的完整处理管线</p>
  <div class="tabs">
    <button v-for="t in tabs" :key="t.id" class="tab" :class="{ active: tab === t.id }" @click="tab = t.id">{{ t.label }}</button>
  </div>

  <!-- 治理流程 -->
  <div v-if="tab === 'flow'">
    <div class="card" style="margin-bottom:16px">
      <div class="card-header"><span class="card-title">AKI系统核心模块总览</span></div>
      <div class="card-body" style="text-align:center">
        <img v-if="has('aki_core_modules.png')" :src="api.figureUrl('aki_core_modules.png')"
             style="max-height:1100px;width:100%;object-fit:contain" />
        <p v-else class="muted">图未生成</p>
      </div>
    </div>
    <div class="card">
      <div class="card-header"><span class="card-title">特征筛选漏斗</span></div>
      <div class="card-body" style="text-align:center">
        <!-- 三图轮播：数据 / 建模 / Web系统概览 -->
        <div style="display:flex;justify-content:center;gap:8px;margin-bottom:14px">
          <button
            v-for="(slide, i) in funnelSlides" :key="slide.key"
            @click="funnelIdx = i"
            :style="{
              padding:'5px 18px', borderRadius:'20px', fontSize:'12px',
              border: funnelIdx === i ? 'none' : '1px solid var(--border)',
              background: funnelIdx === i ? 'var(--primary)' : 'transparent',
              color: funnelIdx === i ? '#fff' : 'var(--text-muted)',
              cursor:'pointer', transition:'all .2s'
            }">{{ slide.label }}</button>
        </div>
        <div style="position:relative;display:inline-block;width:100%">
          <img
            :src="api.figureUrl(funnelSlides[funnelIdx].key)"
            style="max-height:600px;width:100%;object-fit:contain;border-radius:8px;transition:opacity .3s" />
          <button @click="funnelIdx = (funnelIdx - 1 + funnelSlides.length) % funnelSlides.length"
                  style="position:absolute;left:8px;top:50%;transform:translateY(-50%);background:rgba(0,0,0,.35);border:none;color:#fff;width:32px;height:32px;border-radius:50%;cursor:pointer;font-size:16px;display:flex;align-items:center;justify-content:center">&#8249;</button>
          <button @click="funnelIdx = (funnelIdx + 1) % funnelSlides.length"
                  style="position:absolute;right:8px;top:50%;transform:translateY(-50%);background:rgba(0,0,0,.35);border:none;color:#fff;width:32px;height:32px;border-radius:50%;cursor:pointer;font-size:16px;display:flex;align-items:center;justify-content:center">&#8250;</button>
        </div>
        <div style="margin-top:8px;font-size:11px;color:var(--text-muted)">{{ funnelIdx + 1 }} / {{ funnelSlides.length }}</div>
      </div>
    </div>
  </div>

  <!-- 缺失值查询 -->
  <div v-if="tab === 'quality'" class="card">
    <div class="card-header">
      <span class="card-title">特征缺失值 / 训练中位数查询</span>
      <span class="muted" style="font-size:10px">共 {{ impRows.length }} 个特征 · 数据来自训练集填充值</span>
    </div>
    <div class="card-body">
      <p style="font-size:11px;color:var(--text-dim);margin-bottom:10px;line-height:1.6">
        以下为模型训练阶段使用的 <strong>中位数填充值</strong>（Median Imputation）。
        当患者预测时某字段未录入，系统将自动使用对应中位数代替。<br>
        可通过搜索框快速定位特定特征的填充值，了解缺失数据如何被处理。
      </p>
      <!-- 搜索框 -->
      <div style="position:relative;margin-bottom:12px;max-width:320px">
        <svg style="position:absolute;left:9px;top:50%;transform:translateY(-50%);width:13px;height:13px;stroke:var(--text-dim);fill:none;stroke-width:2"
             viewBox="0 0 24 24">
          <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
        </svg>
        <input v-model="impSearch" placeholder="搜索特征名…"
               style="width:100%;padding:5px 9px 5px 30px;border-radius:6px;border:1px solid var(--border-light);background:var(--bg-inset);color:var(--text);font-size:12px" />
      </div>
      <!-- 加载 / 错误 / 表格 -->
      <div v-if="impLoading" style="text-align:center;padding:24px;color:var(--text-dim)">加载中…</div>
      <div v-else-if="impError" style="text-align:center;padding:24px;color:var(--red)">
        加载失败，请确认后端服务已启动。
      </div>
      <template v-else>
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>特征名</th>
              <th style="text-align:right">训练集中位数（填充值）</th>
              <th style="text-align:center">状态</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in filteredRows" :key="row.feature">
              <td style="color:var(--text-dim)">{{ i + 1 }}</td>
              <td>{{ row.feature }}</td>
              <td style="text-align:right;font-variant-numeric:tabular-nums">
                {{ row.median !== null ? Number(row.median).toFixed(4) : '—' }}
              </td>
              <td style="text-align:center">
                <span style="font-size:10px;padding:2px 7px;border-radius:4px"
                      :style="row.median !== null
                        ? 'background:rgba(34,197,94,.1);color:#22c55e;border:1px solid rgba(34,197,94,.2)'
                        : 'background:rgba(239,68,68,.08);color:var(--red);border:1px solid rgba(239,68,68,.2)'">
                  {{ row.median !== null ? '有填充值' : '无' }}
                </span>
              </td>
            </tr>
            <tr v-if="filteredRows.length === 0">
              <td colspan="4" style="text-align:center;color:var(--text-dim);padding:16px">无匹配结果</td>
            </tr>
          </tbody>
        </table>
      </template>
    </div>
  </div>

  <!-- 质量仪表盘 -->
  <div v-if="tab === 'dashboard'">
    <div v-if="dashboardError" class="error" style="margin-bottom:12px">{{ dashboardError }}</div>
    <div v-if="dashboardLoading" style="text-align:center;padding:40px;color:var(--text-dim)">数据加载中...</div>
    <div v-else-if="dashboardData" style="display:flex;flex-direction:column;gap:16px;">
      <!-- Key Stats -->
      <div class="grid" style="grid-template-columns: repeat(4, 1fr);">
        <div class="card" style="padding:16px;text-align:center;">
          <div style="font-size:24px;font-weight:600;color:var(--primary)">{{ dashboardData.stats.samples }}</div>
          <div style="font-size:12px;color:var(--text-dim);margin-top:4px">总样本量</div>
        </div>
        <div class="card" style="padding:16px;text-align:center;">
          <div style="font-size:24px;font-weight:600;color:var(--primary)">{{ dashboardData.stats.features }}</div>
          <div style="font-size:12px;color:var(--text-dim);margin-top:4px">模型特征数</div>
        </div>
        <div class="card" style="padding:16px;text-align:center;">
          <div style="font-size:24px;font-weight:600;color:var(--green)">{{ dashboardData.stats.completeness || dashboardData.stats.missingRate }}</div>
          <div style="font-size:12px;color:var(--text-dim);margin-top:4px">数据完整性</div>
        </div>
        <div class="card" style="padding:16px;text-align:center;">
          <div style="font-size:24px;font-weight:600;color:var(--green)">{{ dashboardData.stats.duplicates }}</div>
          <div style="font-size:12px;color:var(--text-dim);margin-top:4px">重复记录数</div>
        </div>
      </div>
      
      <div style="display: flex; flex-wrap: wrap; gap: 16px;">
        <!-- Missing Rates Bar Chart (CSS) -->
        <div class="card" style="flex: 2; min-width: 320px;">
          <div class="card-header"><span class="card-title">数据完整性（有缺失的列）</span></div>
          <div class="card-body" style="padding-top:8px">
            <p v-if="!dashboardData.completenessRates || !dashboardData.completenessRates.length" class="muted" style="font-size:11px;padding:8px 0">所有列均无缺失，数据完整性 100%。</p>
            <div v-for="item in (dashboardData.completenessRates || [])" :key="item.feature" style="margin-bottom:12px">
              <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px">
                <span>{{ item.feature }}</span>
                <span style="color:var(--green)">{{ item.rate }}%</span>
              </div>
              <div style="height:6px;background:var(--bg-inset);border-radius:3px;overflow:hidden">
                <div :style="{ width: item.rate + '%', height: '100%', background: 'var(--green)' }"></div>
              </div>
            </div>
            <p class="muted" style="font-size:10px;margin-top:10px;line-height:1.5">缺失值在模型预测时将使用训练集中位数自动填充。</p>
          </div>
        </div>

        <div style="flex: 1; min-width: 300px; display:flex;flex-direction:column;gap:16px">
          <!-- Class Balance -->
          <div class="card">
            <div class="card-header"><span class="card-title">样本分类均衡度 (AKI vs Non-AKI)</span></div>
            <div class="card-body" style="display:flex;align-items:center;justify-content:center;padding:24px 16px;">
               <div style="width:100%">
                 <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:6px">
                    <span style="color:var(--red);font-weight:600">AKI ({{ dashboardData.classBalance.aki }})</span>
                    <span style="color:var(--green);font-weight:600">Non-AKI ({{ dashboardData.classBalance.nonAki }})</span>
                 </div>
                 <div style="height:12px;display:flex;border-radius:6px;overflow:hidden;background:var(--bg-inset)">
                    <div :style="{ width: (dashboardData.classBalance.aki / (dashboardData.classBalance.aki + dashboardData.classBalance.nonAki) * 100) + '%' }" style="background:var(--red)"></div>
                    <div :style="{ width: (dashboardData.classBalance.nonAki / (dashboardData.classBalance.aki + dashboardData.classBalance.nonAki) * 100) + '%' }" style="background:var(--green)"></div>
                 </div>
                 <div style="text-align:center;font-size:11px;color:var(--text-dim);margin-top:10px">
                    阳性率：{{ (dashboardData.classBalance.aki / (dashboardData.classBalance.aki + dashboardData.classBalance.nonAki) * 100).toFixed(1) }}%
                 </div>
               </div>
            </div>
          </div>
          
          <!-- Data Types -->
          <div class="card">
            <div class="card-header"><span class="card-title">特征数据类型分布</span></div>
            <div class="card-body" style="display:flex; align-items:center; gap: 24px;">
               <!-- CSS Pie Chart -->
               <div :style="{ background: typePieStyle }" style="width:100px; height:100px; border-radius:50%; flex-shrink:0;"></div>
               <div style="flex:1; display:flex; flex-direction:column; gap:8px;">
                 <div style="display:flex;align-items:center;gap:8px">
                   <div style="width:10px;height:10px;border-radius:50%;background:var(--primary)"></div>
                   <div style="flex:1;font-size:12px;color:var(--text)">Float64</div>
                   <div style="font-weight:600;font-size:13px">{{ dashboardData.dataTypes.float64 }}</div>
                 </div>
                 <div style="display:flex;align-items:center;gap:8px">
                   <div style="width:10px;height:10px;border-radius:50%;background:var(--yellow)"></div>
                   <div style="flex:1;font-size:12px;color:var(--text)">Int64</div>
                   <div style="font-weight:600;font-size:13px">{{ dashboardData.dataTypes.int64 }}</div>
                 </div>
                 <div style="display:flex;align-items:center;gap:8px">
                   <div style="width:10px;height:10px;border-radius:50%;background:var(--red)"></div>
                   <div style="flex:1;font-size:12px;color:var(--text)">Object</div>
                   <div style="font-weight:600;font-size:13px">{{ dashboardData.dataTypes.object }}</div>
                 </div>
               </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

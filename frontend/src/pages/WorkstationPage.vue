<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import { useSelectedPatient } from '../composables/usePatient'
import type { CohortResponse } from '../api/types'

const router = useRouter()
const { set: setSelectedPatient } = useSelectedPatient()
const cohort    = ref<CohortResponse | null>(null)
const csvResult = ref('')
const busy      = ref(false)
const dragging  = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

onMounted(() => { api.cohort().then((c: any) => cohort.value = c).catch(() => {}) })

function viewPatient(p: any) {
  setSelectedPatient({
    id: p.id,
    features: p.features ?? {},
    probability: p.probability,
    riskLevel: p.riskLevel,
  })
  router.push('/predict')
}

// 迷你条颜色
function barColor(level: string): string {
  if (level === '高') return 'var(--red)'
  if (level === '中') return 'var(--yellow)'
  return 'var(--green)'
}
function tagClass(level: string): string {
  if (level === '高') return 'tag-high'
  if (level === '中') return 'tag-medium'
  return 'tag-low'
}

async function processFile(file: File) {
  busy.value = true; csvResult.value = ''
  try {
    const blob = await api.csvUpload(file)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = 'AKI_batch.csv'; a.click()
    URL.revokeObjectURL(url)
    csvResult.value = `✓ 已完成预测：${file.name}`
  } catch (err: any) {
    csvResult.value = `失败：${err?.message || err}`
  } finally { busy.value = false }
}

async function onUpload(e: Event) {
  const input = e.target as HTMLInputElement
  const f = input.files?.[0]
  if (f) await processFile(f)
  input.value = ''
}
function onDrop(e: DragEvent) {
  dragging.value = false
  const f = e.dataTransfer?.files?.[0]
  if (f && f.name.toLowerCase().endsWith('.csv')) processFile(f)
}
function triggerInput() { fileInput.value?.click() }
</script>

<template>
  <h2 class="page-title">医生工作台</h2>
  <p class="page-subtitle">患者风险列表与批量评估 <span style="background:rgba(251,191,36,.15);color:#fbbf24;padding:1px 7px;border-radius:8px;font-size:9px;font-weight:700;margin-left:4px">演示数据</span> · 预测使用真实模型</p>

  <!-- 风险汇总 KPI -->
  <div class="kpi-grid" style="grid-template-columns:repeat(3,1fr);max-width:500px;margin-bottom:18px">
    <div class="kpi-card kpi-card-red">
      <div class="kpi-label">高风险</div>
      <div class="kpi-value" style="color:var(--red)">{{ cohort?.summary?.high ?? 0 }}</div>
    </div>
    <div class="kpi-card kpi-card-orange">
      <div class="kpi-label">中风险</div>
      <div class="kpi-value" style="color:var(--yellow)">{{ cohort?.summary?.mid ?? 0 }}</div>
    </div>
    <div class="kpi-card kpi-card-green">
      <div class="kpi-label">低风险</div>
      <div class="kpi-value" style="color:var(--green)">{{ cohort?.summary?.low ?? 0 }}</div>
    </div>
  </div>

  <div class="grid-2-1">
    <!-- 左：患者表格 -->
    <div class="card">
      <div class="card-header">
        <span class="card-title">今日待评估患者（演示队列 seed=42）</span>
        <span class="badge badge-info">{{ cohort?.patients?.length ?? 0 }} 例</span>
      </div>
      <div style="overflow-x:auto">
        <table>
          <thead>
            <tr>
              <th>ID</th><th>年龄</th><th>手术类型</th>
              <th>AKI 概率</th><th>等级</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="p in cohort?.patients" :key="p.id"
              :style="{
                borderLeft: p.riskLevel === '高' ? '3px solid var(--red)'
                           : p.riskLevel === '中' ? '3px solid var(--yellow)'
                           : '3px solid transparent'
              }"
            >
              <td style="font-family:monospace;font-size:10px;color:var(--text-muted)">{{ p.id }}</td>
              <td>{{ p.age }}</td>
              <td>{{ p.surgery }}</td>
              <!-- 行内迷你风险条 -->
              <td>
                <div class="mini-risk-bar">
                  <div class="mini-risk-track">
                    <div
                      class="mini-risk-fill"
                      :style="{
                        width: (p.probability * 100) + '%',
                        background: barColor(p.riskLevel)
                      }"
                    />
                  </div>
                  <span class="mini-risk-val">{{ (p.probability * 100).toFixed(1) }}%</span>
                </div>
              </td>
              <td>
                <span class="tag" :class="tagClass(p.riskLevel)">{{ p.riskLevel }}风险</span>
              </td>
              <td>
                <button class="btn btn-secondary btn-sm" @click="viewPatient(p)">查看</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 右：批量上传 -->
    <div>
      <div class="card">
        <div class="card-header"><span class="card-title">批量风险评估</span></div>
        <div class="card-body">
          <div class="info-box" style="margin-bottom:12px">
            上传包含患者特征的 CSV，系统逐行预测并下载结果文件。
          </div>
          <div
            class="upload-zone"
            :class="{ 'drag-over': dragging }"
            role="button"
            tabindex="0"
            @click="triggerInput"
            @keydown.enter.prevent="triggerInput"
            @keydown.space.prevent="triggerInput"
            @dragover.prevent="dragging = true"
            @dragleave="dragging = false"
            @drop.prevent="onDrop"
          >
            <div class="upload-zone-icon">📄</div>
            <p>拖拽 CSV 文件到此处</p>
            <p class="upload-hint">或点击选择文件 · 仅支持 .csv 格式</p>
          </div>
          <input type="file" accept=".csv" ref="fileInput" style="display:none" @change="onUpload" />
          <p v-if="busy" class="muted" style="margin-top:10px;text-align:center">⏳ 预测中，请稍候…</p>
          <p v-else-if="csvResult" style="margin-top:10px;font-size:12px;color:var(--green);text-align:center">
            {{ csvResult }}
          </p>
        </div>
      </div>

      <!-- 风险分布小卡 -->
      <div class="card">
        <div class="card-header"><span class="card-title">风险分布</span></div>
        <div class="card-body">
          <template v-if="cohort">
            <div v-for="(item, level) in [
              { label:'高风险', color:'var(--red)',    count: cohort.summary.high },
              { label:'中风险', color:'var(--yellow)', count: cohort.summary.mid  },
              { label:'低风险', color:'var(--green)',  count: cohort.summary.low  },
            ]" :key="item.label" style="margin-bottom:10px">
              <div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:4px">
                <span style="color:var(--text)">{{ item.label }}</span>
                <span style="color:var(--text-dim)">{{ item.count }} 例</span>
              </div>
              <div style="height:6px;background:var(--bg-inset);border-radius:3px;overflow:hidden">
                <div :style="{
                  width: ((item.count / (cohort.summary.high + cohort.summary.mid + cohort.summary.low)) * 100) + '%',
                  height: '100%',
                  background: item.color,
                  borderRadius: '3px',
                  transition: 'width .6s ease'
                }"/>
              </div>
            </div>
          </template>
          <p v-else class="muted" style="text-align:center">加载中…</p>
        </div>
      </div>
    </div>
  </div>
</template>

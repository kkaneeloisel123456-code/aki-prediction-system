<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '../api/client'
import type { FeaturesResponse } from '../api/types'
const features = ref<FeaturesResponse | null>(null)
const busy = ref(false)
onMounted(() => api.features().then((f) => { features.value = f }).catch(() => {}))
async function downloadDemo() {
  busy.value = true
  try { const blob = await api.reportPdf({}); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = 'AKI_Report_Demo.pdf'; a.click(); URL.revokeObjectURL(url) } finally { busy.value = false }
}
</script>
<template>
  <h2 class="page-title">报告中心</h2>
  <p class="page-subtitle">完成风险预测后，可在此下载 PDF 报告</p>
  <div class="card"><div class="card-header"><span class="card-title">PDF 报告下载</span></div>
    <div class="card-body">
      <p class="muted" style="margin-bottom:12px">尚未生成报告？可先下载示例报告。</p>
      <button class="btn btn-primary" @click="downloadDemo" :disabled="busy">{{ busy ? '生成中…' : '下载示例 PDF 报告' }}</button>
    </div>
  </div>
  <div class="card"><div class="card-header"><span class="card-title">特征列表</span></div>
    <div class="card-body">
      <p class="muted" v-if="!features">加载中…</p>
      <template v-else>
        <p class="muted">模型使用 {{ features.features.length }} 个特征：</p>
        <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:10px">
          <span v-for="f in features.features" :key="f" style="background:#0f172a;padding:4px 10px;border-radius:12px;font-size:12px;color:var(--text-muted);border:1px solid var(--border)">{{ f }}</span>
        </div>
      </template>
    </div>
  </div>
</template>

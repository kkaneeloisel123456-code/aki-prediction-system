<script setup lang="ts">
import { ref } from 'vue'
import { api } from '../api/client'
const result = ref('')
const busy = ref(false)
async function onUpload(e: Event) {
  const input = e.target as HTMLInputElement
  const f = input.files?.[0]
  if (!f) return
  busy.value = true
  result.value = ''
  try {
    const blob = await api.csvUpload(f)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a'); a.href = url; a.download = 'AKI_batch.csv'; a.click(); URL.revokeObjectURL(url)
    result.value = `已预测并下载：${f.name}`
  } catch (err: any) {
    result.value = `失败：${err?.message || err}`
  } finally {
    busy.value = false
    input.value = ''
  }
}
</script>
<template>
  <h2 class="page-title">批量预测</h2>
  <p class="page-subtitle">上传 CSV 文件（列名为特征名），逐行预测并下载结果</p>
  <div class="card"><div class="card-header"><span class="card-title">批量风险评估</span><a :href="api.templateUrl()" download style="font-size:10px;color:var(--primary);text-decoration:none">下载模板 CSV ↓</a></div>
    <div class="card-body">
      <div class="info-box">上传包含患者特征的 CSV，系统为每一行生成 AKI 风险预测。首行需为列名。</div>
      <input type="file" accept=".csv" @change="onUpload" />
      <p v-if="busy" class="muted" style="margin-top:8px">预测中…</p>
      <p v-else-if="result" style="margin-top:8px">{{ result }}</p>
    </div>
  </div>
</template>

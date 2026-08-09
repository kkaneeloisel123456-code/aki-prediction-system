<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '../api/client'
const tab = ref('flow')
const figures = ref<string[]>([])
const tabs = [{ id: 'flow', label: '治理流程' }, { id: 'quality', label: '缺失值分析' }, { id: 'dashboard', label: '质量仪表盘' }]
const has = (n: string) => figures.value.includes(n)
onMounted(() => { api.figures().then((f: string[]) => { figures.value = f }).catch(() => {}) })
</script>
<template>
  <h2 class="page-title">数据治理</h2>
  <p class="page-subtitle">从原始数据到建模数据集的完整处理管线</p>
  <div class="tabs"><button v-for="t in tabs" :key="t.id" class="tab" :class="{ active: tab === t.id }" @click="tab = t.id">{{ t.label }}</button></div>
  <div v-if="tab === 'flow'" class="grid">
    <div class="card"><div class="card-header"><span class="card-title">七阶段数据治理管线</span></div><div class="card-body"><img v-if="has('data_governance_flow.png')" :src="api.figureUrl('data_governance_flow.png')" /></div></div>
    <div class="card"><div class="card-header"><span class="card-title">特征筛选漏斗</span></div><div class="card-body"><img v-if="has('feature_selection_funnel.png')" :src="api.figureUrl('feature_selection_funnel.png')" /></div></div>
  </div>
  <div v-if="tab === 'quality'" class="card"><div class="card-body"><img v-if="has('data_quality_dashboard.png')" :src="api.figureUrl('data_quality_dashboard.png')" /><p class="muted">KDIGO 诊断标准校验、AKI 分组与分期一致性。</p></div></div>
  <div v-if="tab === 'dashboard'" class="card"><div class="card-header"><span class="card-title">数据质量仪表盘</span></div><div class="card-body"><img v-if="has('data_quality_dashboard.png')" :src="api.figureUrl('data_quality_dashboard.png')" /></div></div>
</template>

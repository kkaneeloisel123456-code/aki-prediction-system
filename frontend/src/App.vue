<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
const route = useRoute()
const title = computed(() => (route.meta.title as string) ?? '')
const nav = [
  { to: '/', label: '首页', icon: 'M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z M9 22 9 12 15 12 15 22' },
  { to: '/performance', label: '模型性能', icon: 'M18 20 18 10 M12 20 12 4 M6 20 6 14' },
  { to: '/predict', label: '风险预测', icon: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z M12 6v6l4 2' },
  { to: '/workstation', label: '医生工作台', icon: 'M22 12h-4l-3 9L9 3l-3 9H2' },
  { to: '/dashboard', label: '管理仪表盘', icon: 'M3 3h7v7H3z M14 3h7v7h-7z M14 14h7v7h-7z M3 14h7v7H3z' },
  { to: '/report', label: '报告中心', icon: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z M14 2v6h6 M16 13H8 M16 17H8 M10 9H8' },
  { to: '/governance', label: '数据治理', icon: 'M11 11a8 8 0 1 0 0-16 8 8 0 0 0 0 16z M21 21l-4.35-4.35' },
]
</script>

<template>
  <div class="layout">
    <aside class="sidebar">
      <div class="brand">
        <h1>AKI 预测系统</h1>
        <p>急性肾损伤智能风险评估</p>
      </div>
      <nav class="nav">
        <RouterLink v-for="n in nav" :key="n.to" :to="n.to">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" v-html="n.icon"></svg>
          {{ n.label }}
        </RouterLink>
      </nav>
      <div class="sidebar-footer">白菜卷队 · 广西科技大学<br />暑期数创 2026 · v3.0</div>
    </aside>
    <main class="main">
      <header class="topbar">
        <div class="breadcrumb">当前位置：<strong>{{ title }}</strong></div>
        <div class="topbar-actions">
          <span class="badge badge-success">模型在线</span>
          <span class="badge badge-info">Voting Ensemble · AUC 0.810</span>
        </div>
      </header>
      <div class="content">
        <RouterView />
      </div>
    </main>
  </div>
</template>

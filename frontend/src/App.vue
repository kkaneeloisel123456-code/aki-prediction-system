<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useTheme } from './composables/useTheme'

const route = useRoute()
const { theme, toggle } = useTheme()
const title = computed(() => (route.meta?.title as string) ?? '')

const nav = [
  { to: '/',            label: '首页',     icon: 'home'       },
  { to: '/performance', label: '模型性能', icon: 'bar-chart'  },
  { to: '/predict',     label: '风险预测', icon: 'target'     },
  { to: '/workstation', label: '医生工作台',icon: 'users'     },
  { to: '/batch',       label: '批量预测',  icon: 'upload'    },
  { to: '/dashboard',   label: '管理仪表盘',icon: 'grid'     },
  { to: '/report',      label: '报告中心', icon: 'file-text'  },
  { to: '/governance',  label: '数据治理', icon: 'shield'     },
]
</script>

<template>
  <div class="layout">
    <!-- ── 侧边栏 ── -->
    <nav class="sidebar">
      <div class="sidebar-brand">
        <div class="sidebar-logo">AKI</div>
        <div class="sidebar-brand-text">
          <div class="sidebar-title">AKI 预测系统</div>
          <div class="sidebar-subtitle">急性肾损伤智能风险评估</div>
        </div>
      </div>

      <div class="sidebar-nav">
        <RouterLink
          v-for="n in nav" :key="n.to"
          :to="n.to"
          class="sidebar-link"
          active-class="active"
          exact-active-class="active"
        >
          <!-- 使用 inline SVG 简单图标 -->
          <span class="sidebar-icon">
            <!-- home -->
            <svg v-if="n.icon==='home'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>
            </svg>
            <!-- bar-chart -->
            <svg v-if="n.icon==='bar-chart'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>
            </svg>
            <!-- target -->
            <svg v-if="n.icon==='target'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>
            </svg>
            <!-- users -->
            <svg v-if="n.icon==='users'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>
            </svg>
            <!-- upload -->
            <svg v-if="n.icon==='upload'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
            </svg>
            <!-- grid -->
            <svg v-if="n.icon==='grid'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>
            </svg>
            <!-- file-text -->
            <svg v-if="n.icon==='file-text'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><line x1="10" y1="9" x2="8" y2="9"/>
            </svg>
            <!-- shield -->
            <svg v-if="n.icon==='shield'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
            </svg>
          </span>
          <span class="sidebar-label">{{ n.label }}</span>
        </RouterLink>
      </div>

      <div class="sidebar-footer">
        <button class="sidebar-theme-btn" @click="toggle">
          <span class="sidebar-icon">
            <svg v-if="theme === 'dark'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
            </svg>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
            </svg>
          </span>
          <span class="sidebar-label">{{ theme === 'dark' ? '切换浅色' : '切换深色' }}</span>
        </button>
        <div class="sidebar-version">v2.0 · Voting Ensemble</div>
      </div>
    </nav>

    <!-- ── 主区域 ── -->
    <div class="main">
      <header class="topbar">
        <div class="topbar-left">
          <span class="current-page">{{ title }}</span>
        </div>
        <div class="topbar-actions">
          <span class="badge badge-success">● 模型在线</span>
          <span class="badge badge-info">AUC 0.810</span>
        </div>
      </header>
      <div class="content">
        <RouterView />
      </div>
    </div>
  </div>
</template>

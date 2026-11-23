<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTheme } from './composables/useTheme'
import { useAuth } from './composables/useAuth'
import { api } from './api/client'

const route = useRoute()
const router = useRouter()
const { theme, toggle } = useTheme()
const auth = useAuth()
const user = auth.user
const online = ref(false)
const bestAuc = ref('-')
const isPublic = computed(() => route.meta.public === true)
const roleLabel = computed(() => user.value?.role === 'admin' ? '管理员' : '医生')

async function refreshHealth() {
  try {
    const h = await api.health()
    online.value = h.model_loaded
  } catch { online.value = false }
}

// 后端晚于前端启动、或中途崩溃时，徽标要能自己恢复/更新。
let healthTimer: ReturnType<typeof setInterval> | undefined

async function refreshShell() {
  await refreshHealth()
  if (isPublic.value) return
  // meta 与 health 分开处理：表格读取失败不应把已确认在线的模型误标为离线。
  try {
    const m = await api.meta()
    if (m.best_auc != null) bestAuc.value = m.best_auc.toFixed(3)
  } catch { /* 顶栏 AUC 保持 '-' */ }
}

function handleUnauthorized() {
  if (!isPublic.value) {
    void router.replace({ path: '/login', query: { redirect: route.fullPath } })
  }
}

onMounted(async () => {
  window.addEventListener('aki:unauthorized', handleUnauthorized)
  await refreshShell()
  healthTimer = setInterval(refreshHealth, 30_000)
})
watch(isPublic, (value) => { if (!value) void refreshShell() })
onUnmounted(() => {
  window.removeEventListener('aki:unauthorized', handleUnauthorized)
  if (healthTimer) clearInterval(healthTimer)
})

async function signOut() {
  await auth.logout()
  await router.replace('/login')
}

const title = computed(() => (route.meta?.title as string) ?? '')

type NavItem = { to: string; label: string; icon: string; adminOnly?: boolean }

const navGroups = computed(() => {
  const groups: { label: string; items: NavItem[] }[] = [
    {
      label: '待评估',
      items: [{ to: '/', label: '未发布评估', icon: 'home' }],
    },
    {
      label: '患者',
      items: [{ to: '/patients', label: '患者档案', icon: 'users' }],
    },
    {
      label: '文书',
      items: [{ to: '/reports', label: '报告与撤销', icon: 'file-text' }],
    },
    {
      label: '录入',
      items: [{ to: '/batch', label: '批量导入', icon: 'upload' }],
    },
    {
      label: '复查',
      items: [{ to: '/schedule', label: '复查安排', icon: 'calendar' }],
    },
    {
      label: '系统',
      items: [
        { to: '/admin', label: '账号与审计', icon: 'shield', adminOnly: true },
        { to: '/performance', label: '模型说明', icon: 'bar-chart' },
        { to: '/governance', label: '数据治理', icon: 'layers' },
      ],
    },
  ]
  return groups
    .map(group => ({
      ...group,
      items: group.items.filter(item => !item.adminOnly || user.value?.role === 'admin'),
    }))
    .filter(group => group.items.length > 0)
})

const passwordOpen = ref(false)
const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const passwordError = ref('')
const passwordBusy = ref(false)

watch(() => user.value?.must_change_password, (value) => {
  if (value) passwordOpen.value = true
}, { immediate: true })

async function submitPassword() {
  passwordError.value = ''
  if (newPassword.value.length < 12) {
    passwordError.value = '新密码至少 12 个字符'
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    passwordError.value = '两次输入的新密码不一致'
    return
  }
  passwordBusy.value = true
  try {
    await api.changePassword(currentPassword.value, newPassword.value)
    await auth.restore(true)
    currentPassword.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
    passwordOpen.value = false
  } catch (e: any) {
    passwordError.value = e?.message ?? '修改失败'
  } finally {
    passwordBusy.value = false
  }
}
</script>

<template>
  <RouterView v-if="isPublic" />
  <div v-else class="layout pilot-shell">
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
        <div v-for="group in navGroups" :key="group.label" class="sidebar-group">
          <div class="sidebar-group-label">{{ group.label }}</div>
          <RouterLink
            v-for="n in group.items" :key="n.to"
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
              <!-- calendar -->
              <svg v-if="n.icon==='calendar'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
              </svg>
              <!-- layers -->
              <svg v-if="n.icon==='layers'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <polygon points="12 2 2 7 12 12 22 7 12 2"/><polygon points="2 12 12 17 22 12"/><polygon points="2 17 12 22 22 17"/>
              </svg>
            </span>
            <span class="sidebar-label">{{ n.label }}</span>
          </RouterLink>
        </div>
      </div>

      <div class="sidebar-footer">
        <div class="sidebar-user">
          <div class="sidebar-user-info">
            <span class="sidebar-user-name">{{ user?.display_name || user?.username }}</span>
            <span class="sidebar-user-role">{{ roleLabel }}</span>
          </div>
          <button class="sidebar-logout" type="button" @click="signOut">退出</button>
        </div>
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
        <div class="sidebar-version">v3.0 · 临床业务版</div>
      </div>
    </nav>

    <!-- ── 主区域 ── -->
    <div class="main">
      <header class="topbar">
        <div class="topbar-left">
          <span class="current-page">{{ title }}</span>
        </div>
        <div class="topbar-actions">
          <span class="badge" :class="online ? 'badge-success' : 'badge-warn'" style="cursor:default">● {{ online ? '服务在线' : '服务离线' }}</span>
          <span class="badge badge-info">模型 AUC {{ bestAuc }}</span>
        </div>
      </header>
      <div class="content">
        <RouterView />
      </div>
    </div>

    <div v-if="passwordOpen" class="modal-mask">
      <div class="modal-panel" style="max-width: 440px">
        <div class="modal-head">
          <div>
            <div class="modal-title">首次登录：请修改初始密码</div>
            <div class="modal-sub">修改完成前，业务接口将被暂时锁定。</div>
          </div>
        </div>
        <div class="modal-body">
          <div class="form-group" style="margin-bottom: 12px">
            <label>当前密码</label>
            <input v-model="currentPassword" class="form-control" type="password" autocomplete="current-password" />
          </div>
          <div class="form-group" style="margin-bottom: 12px">
            <label>新密码（至少 12 个字符）</label>
            <input v-model="newPassword" class="form-control" type="password" autocomplete="new-password" />
          </div>
          <div class="form-group" style="margin-bottom: 12px">
            <label>确认新密码</label>
            <input v-model="confirmPassword" class="form-control" type="password" autocomplete="new-password" />
          </div>
          <div v-if="passwordError" class="error">{{ passwordError }}</div>
        </div>
        <div class="modal-foot">
          <button class="btn btn-primary" :disabled="passwordBusy" @click="submitPassword">
            {{ passwordBusy ? '提交中…' : '修改并继续' }}
          </button>
          <button class="btn btn-secondary" @click="signOut">退出登录</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sidebar-user {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-card);
}
.sidebar-user-info { display: flex; flex: 1; flex-direction: column; min-width: 0; }
.sidebar-user-name {
  overflow: hidden;
  color: var(--text-bright);
  font-size: 11px;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sidebar-user-role { margin-top: 2px; color: var(--text-dim); font-size: 9px; }
.sidebar-logout {
  padding: 4px 6px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--text-dim);
  font-size: 10px;
  cursor: pointer;
}
.sidebar-logout:hover { background: var(--bg-hover); color: var(--primary); }
@media (max-width: 900px) {
  .sidebar-user { justify-content: center; padding: 6px; }
  .sidebar-user-info { display: none; }
  .sidebar-logout { padding: 4px; font-size: 9px; }
}
</style>

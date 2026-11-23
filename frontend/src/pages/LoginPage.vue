<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuth } from '../composables/useAuth'
import { useTheme } from '../composables/useTheme'
import ThemeSwitch from '../components/ThemeSwitch.vue'
import darkVisual from '../assets/login-visual-dark.webp'
import lightVisual from '../assets/login-visual-light.webp'

const router = useRouter()
const route = useRoute()
const auth = useAuth()
const { theme } = useTheme()
const visual = computed(() => theme.value === 'dark' ? darkVisual : lightVisual)

const username = ref('')
const password = ref('')
const remember = ref(false)
const loading = ref(false)
const error = ref('')
const notice = ref('')
const accountInput = ref<HTMLInputElement | null>(null)

onMounted(() => accountInput.value?.focus())

function safeRedirect(): string {
  const target = route.query.redirect
  if (typeof target === 'string' && target.startsWith('/') && !target.startsWith('//')) {
    return target
  }
  return '/'
}

function readableError(reason: unknown): string {
  const message = reason instanceof Error ? reason.message : String(reason)
  if (message.includes('401')) return '账号或密码错误，请重新输入。'
  if (message.includes('429')) return '登录尝试次数过多，请 5 分钟后再试。'
  if (message.includes('503')) return '登录功能尚未初始化，请先运行 scripts/init_auth.py。'
  if (/failed to fetch|networkerror|load failed/i.test(message)) {
    return '无法连接后端服务，请确认后端已启动后重试。'
  }
  return message || '登录失败，请稍后重试。'
}

async function submit() {
  error.value = ''
  notice.value = ''
  if (!username.value.trim()) {
    error.value = '请输入账号。'
    return
  }
  if (!password.value) {
    error.value = '请输入密码。'
    return
  }
  loading.value = true
  try {
    await auth.login(username.value.trim(), password.value, remember.value)
    await router.replace(safeRedirect())
  } catch (reason) {
    error.value = readableError(reason)
  } finally {
    loading.value = false
  }
}

function forgotPassword() {
  error.value = ''
  notice.value = '请联系系统管理员重置密码。'
}
</script>

<template>
  <main class="login-page">
    <section class="login-visual" aria-label="肾脏与围术期评估示意">
      <div class="login-visual-image" :style="{ backgroundImage: `url(${visual})` }" />
      <div class="login-visual-shade" />
      <div class="login-visual-caption">
        <span class="login-visual-kicker">围术期指标链路</span>
        <div class="login-phases">
          <span>术前</span><i aria-hidden="true" /><span>术中</span><i aria-hidden="true" /><span>ICU</span><i aria-hidden="true" /><span>术后</span>
        </div>
      </div>
    </section>

    <section class="login-stage" aria-labelledby="login-title">
      <div class="login-card">
        <header class="login-card-head">
          <div class="login-brand">
            <span class="login-logo" aria-hidden="true">AKI</span>
            <span class="login-brand-name">围术期 AKI 风险评估</span>
          </div>
          <ThemeSwitch />
        </header>

        <div class="login-heading">
          <p class="login-kicker">临床工作台</p>
          <h1 id="login-title">登录</h1>
          <p>使用授权账号进入评估、文书与复查流程。</p>
        </div>

        <div v-if="auth.statusError.value" class="pilot-error" role="alert">
          无法连接后端服务，请确认后端已启动。
        </div>
        <div v-else-if="!auth.configured.value" class="pilot-error" role="alert">
          尚未初始化授权账号，请先运行 scripts/init_auth.py。
        </div>

        <form class="login-form" @submit.prevent="submit">
          <div class="login-field">
            <label for="login-username">账号</label>
            <input
              id="login-username"
              ref="accountInput"
              v-model="username"
              class="pilot-input"
              type="text"
              inputmode="text"
              autocomplete="username"
              placeholder="医生或管理员账号"
              :disabled="loading"
              maxlength="64"
            >
          </div>

          <div class="login-field">
            <label for="login-password">密码</label>
            <input
              id="login-password"
              v-model="password"
              class="pilot-input"
              type="password"
              autocomplete="current-password"
              placeholder="登录密码"
              :disabled="loading"
              maxlength="1024"
            >
          </div>

          <div class="login-options">
            <label class="login-remember">
              <input v-model="remember" type="checkbox" :disabled="loading">
              <span>记住登录状态</span>
            </label>
            <button class="login-text-button" type="button" @click="forgotPassword">忘记密码</button>
          </div>

          <div class="login-message-slot">
            <div v-if="error" class="pilot-error login-message" role="alert">{{ error }}</div>
            <div v-else-if="notice" class="pilot-notice login-message" role="status">{{ notice }}</div>
          </div>

          <button class="pilot-btn pilot-btn-primary login-submit" type="submit" :disabled="loading || !auth.configured.value">
            {{ loading ? '正在登录…' : '登录' }}
          </button>
        </form>

        <footer class="login-foot">
          <span>仅限授权医务人员使用</span>
          <RouterLink to="/portal" class="pilot-link">患者查询入口</RouterLink>
        </footer>
      </div>
    </section>
  </main>
</template>

<style scoped>
.login-page {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(440px, .85fr);
  min-height: 100vh;
  background: var(--pilot-bg);
  color: var(--pilot-ink);
}
.login-visual {
  position: relative;
  min-height: 100vh;
  overflow: hidden;
  border-right: 1px solid var(--pilot-line);
  background: var(--pilot-surface-2);
}
.login-visual-image {
  position: absolute;
  inset: 0;
  background-position: center;
  background-size: cover;
  filter: saturate(.72) sepia(.18) brightness(1.03);
  transform: scale(1.02);
}
:global(html[data-theme="dark"]) .login-visual-image {
  filter: saturate(.85) brightness(.82);
}
.login-visual-shade {
  position: absolute;
  inset: 0;
  background:
    linear-gradient(180deg, transparent 34%, var(--pilot-bg) 100%),
    linear-gradient(90deg, transparent 55%, color-mix(in srgb, var(--pilot-bg) 30%, transparent) 100%);
}
.login-visual-caption {
  position: absolute;
  right: 40px;
  bottom: 40px;
  left: 40px;
  z-index: 2;
}
.login-visual-kicker {
  display: block;
  margin-bottom: var(--pilot-space-3);
  color: var(--pilot-muted);
  font-size: var(--pilot-font-xs);
  font-weight: 600;
  letter-spacing: .08em;
}
.login-phases {
  display: flex;
  align-items: center;
  gap: var(--pilot-space-2);
  flex-wrap: wrap;
}
.login-phases span {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  padding: 0 var(--pilot-space-3);
  border: 1px solid var(--pilot-line);
  border-radius: var(--pilot-radius-control);
  background: color-mix(in srgb, var(--pilot-surface) 82%, transparent);
  color: var(--pilot-ink-soft);
  font-size: var(--pilot-font-xs);
  font-weight: 600;
  backdrop-filter: blur(8px);
}
.login-phases i {
  width: 18px;
  height: 1px;
  background: var(--pilot-line-strong);
}
.login-stage {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: var(--pilot-space-6) var(--pilot-space-5);
}
.login-card {
  width: min(420px, 100%);
  padding: var(--pilot-space-6);
  border: 1px solid var(--pilot-line);
  border-radius: var(--pilot-radius-card);
  background: var(--pilot-surface);
  box-shadow: var(--pilot-shadow);
}
.login-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--pilot-space-3);
  margin-bottom: var(--pilot-space-5);
}
.login-brand {
  display: flex;
  align-items: center;
  gap: var(--pilot-space-2);
  min-width: 0;
}
.login-logo {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border: 1px solid var(--pilot-line-strong);
  border-radius: var(--pilot-radius-control);
  color: var(--pilot-accent);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .06em;
}
.login-brand-name {
  color: var(--pilot-ink);
  font-size: var(--pilot-font-sm);
  font-weight: 700;
}
.login-heading { margin-bottom: var(--pilot-space-5); }
.login-kicker {
  margin: 0 0 var(--pilot-space-1);
  color: var(--pilot-muted);
  font-size: var(--pilot-font-xs);
  font-weight: 600;
  letter-spacing: .04em;
}
.login-heading h1 {
  margin: 0;
  color: var(--pilot-ink);
  font-size: var(--pilot-font-xl);
  font-weight: 700;
  line-height: 1.2;
}
.login-heading p {
  margin: var(--pilot-space-2) 0 0;
  color: var(--pilot-muted);
  font-size: var(--pilot-font-sm);
  line-height: 1.6;
}
.login-form { display: flex; flex-direction: column; gap: var(--pilot-space-4); }
.login-field { display: flex; flex-direction: column; gap: var(--pilot-space-2); }
.login-field label {
  color: var(--pilot-ink-soft);
  font-size: var(--pilot-font-xs);
  font-weight: 600;
}
.login-options {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--pilot-space-3);
  font-size: var(--pilot-font-xs);
}
.login-remember {
  display: inline-flex;
  align-items: center;
  gap: var(--pilot-space-2);
  color: var(--pilot-muted);
  cursor: pointer;
}
.login-remember input { width: 16px; height: 16px; accent-color: var(--pilot-accent); }
.login-text-button {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--pilot-accent);
  font: inherit;
  cursor: pointer;
}
.login-text-button:hover { color: var(--pilot-accent-hover); text-decoration: underline; }
.login-text-button:focus-visible { outline: 2px solid var(--pilot-accent); outline-offset: 2px; }
.login-message-slot { min-height: 0; }
.login-message { margin: 0; }
.login-submit { width: 100%; height: 44px; }
.login-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--pilot-space-3);
  margin-top: var(--pilot-space-5);
  padding-top: var(--pilot-space-4);
  border-top: 1px solid var(--pilot-line);
  color: var(--pilot-muted);
  font-size: var(--pilot-font-xs);
}
@media (max-width: 1050px) {
  .login-page { grid-template-columns: minmax(0, 1fr) minmax(430px, .95fr); }
}
@media (max-width: 820px) {
  .login-page { display: block; }
  .login-visual {
    height: clamp(180px, 26vh, 230px);
    min-height: 0;
    border-right: 0;
    border-bottom: 1px solid var(--pilot-line);
  }
  .login-visual-caption { right: 16px; bottom: 14px; left: 16px; }
  .login-visual-kicker { margin-bottom: var(--pilot-space-2); }
  .login-stage {
    align-items: flex-start;
    min-height: 0;
    padding: var(--pilot-space-5) var(--pilot-space-4) var(--pilot-space-6);
  }
}
@media (max-width: 650px) {
  .login-card { padding: var(--pilot-space-5); }
  .login-brand-name { font-size: var(--pilot-font-xs); }
  .login-card-head { flex-direction: row; align-items: center; }
  .login-phases span { min-height: 28px; padding: 0 var(--pilot-space-2); }
}
@media (max-width: 380px) {
  .login-card-head { align-items: flex-start; flex-direction: column; }
}
</style>
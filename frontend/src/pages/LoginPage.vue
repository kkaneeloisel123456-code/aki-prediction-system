<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useTheme } from '../composables/useTheme'
import { useAuth } from '../composables/useAuth'
import darkVisual from '../assets/login-visual-dark.webp'
import lightVisual from '../assets/login-visual-light.webp'

const router = useRouter()
const route = useRoute()
const { theme, toggle } = useTheme()
const auth = useAuth()

const username = ref('')
const password = ref('')
const remember = ref(false)
const loading = ref(false)
const error = ref('')
const notice = ref('')
const accountInput = ref<HTMLInputElement | null>(null)

const visual = computed(() => theme.value === 'dark' ? darkVisual : lightVisual)
const themeLabel = computed(() => theme.value === 'dark' ? '切换浅色' : '夜间模式')

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
  <main class="login-page" :class="theme">
    <section
      class="login-visual"
      :style="{ backgroundImage: `url(${visual})` }"
      aria-label="肾脏医学主视觉"
    >
      <div class="visual-copy">
        <p class="visual-eyebrow">AKI CLINICAL INTELLIGENCE</p>
        <h1>让每一次评估，都更有依据</h1>
        <p class="visual-subtitle">急性肾损伤智能风险评估 · SHAP 可解释性分析</p>
      </div>
    </section>

    <section class="login-panel">
      <div class="login-card">
        <div class="login-card-top">
          <div class="login-logo" aria-label="AKI">AKI</div>
          <button class="theme-toggle" type="button" @click="toggle" :aria-label="themeLabel">
            <svg v-if="theme === 'dark'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
              <circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.42-1.42M17.66 6.34l1.41-1.41"/>
            </svg>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
            </svg>
            <span>{{ themeLabel }}</span>
          </button>
        </div>

        <div class="login-heading">
          <h2>欢迎登录</h2>
          <p>使用授权账号进入临床智能评估工作台</p>
        </div>

        <div v-if="auth.statusError.value" class="login-message error" role="alert">
          无法连接后端服务，请确认后端已启动。
        </div>
        <div v-else-if="!auth.configured.value" class="login-message error" role="alert">
          尚未初始化授权账号，请先运行 scripts/init_auth.py。
        </div>

        <form class="login-form" @submit.prevent="submit">
          <label class="field-label" for="login-username">账号</label>
          <input
            id="login-username"
            ref="accountInput"
            v-model="username"
            class="login-input"
            type="text"
            inputmode="text"
            autocomplete="username"
            placeholder="请输入医生或管理员账号"
            :disabled="loading"
            maxlength="64"
          >

          <label class="field-label" for="login-password">密码</label>
          <input
            id="login-password"
            v-model="password"
            class="login-input"
            type="password"
            autocomplete="current-password"
            placeholder="请输入密码"
            :disabled="loading"
            maxlength="1024"
          >

          <div class="form-options">
            <label class="remember-option">
              <input v-model="remember" type="checkbox" :disabled="loading">
              <span>记住登录状态</span>
            </label>
            <button class="forgot-button" type="button" @click="forgotPassword">忘记密码？</button>
          </div>

          <div v-if="error" class="login-message error" role="alert">{{ error }}</div>
          <div v-if="notice" class="login-message notice" role="status">{{ notice }}</div>

          <button class="login-submit" type="submit" :disabled="loading || !auth.configured.value">
            <span>{{ loading ? '正在登录…' : '登录系统' }}</span>
            <span v-if="!loading" aria-hidden="true">→</span>
          </button>
        </form>

        <p class="login-footnote">仅限授权医务人员使用</p>
      </div>
    </section>
  </main>
</template>

<style scoped>
.login-page {
  --login-panel: #080f1c;
  --login-card: #101b2e;
  --login-border: #1a2a40;
  --login-input: #0c1422;
  --login-heading: #eef4ff;
  --login-copy: #7898bc;
  --login-dim: #4a6788;
  --login-primary: #38bdf8;
  --login-button: #0ea5e9;
  --login-visual-fallback: #080f1c;
  --login-left-title: #eef4ff;
  display: grid;
  grid-template-columns: minmax(0, 58fr) minmax(430px, 42fr);
  min-height: 100vh;
  background: var(--login-panel);
  color: var(--login-copy);
}
.login-page.light {
  --login-panel: #f0f4f8;
  --login-card: #ffffff;
  --login-border: #dde5ef;
  --login-input: #ffffff;
  --login-heading: #0c1a2e;
  --login-copy: #4d6a8a;
  --login-dim: #7a9bc0;
  --login-primary: #0284c7;
  --login-button: #0284c7;
  --login-visual-fallback: #eaf3f8;
  --login-left-title: #0c1a2e;
}
.login-visual {
  position: relative;
  min-height: 100vh;
  background-color: var(--login-visual-fallback);
  background-position: center;
  background-size: cover;
  background-repeat: no-repeat;
  overflow: hidden;
}
.visual-copy {
  position: absolute;
  left: clamp(28px, 4vw, 72px);
  right: clamp(28px, 4vw, 72px);
  bottom: clamp(30px, 5vh, 58px);
  color: var(--login-left-title);
}
.visual-eyebrow {
  margin: 0 0 18px;
  color: var(--login-primary);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: .22em;
}
.visual-copy h1 {
  margin: 0;
  color: var(--login-left-title);
  font-size: clamp(28px, 2.4vw, 40px);
  line-height: 1.25;
  letter-spacing: -.02em;
}
.visual-subtitle {
  margin: 18px 0 0;
  color: var(--login-copy);
  font-size: 14px;
  line-height: 1.6;
}
.login-panel {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 0;
  background: var(--login-panel);
}
.login-card {
  width: min(500px, calc(100% - 64px));
  padding: 44px 44px 32px;
  border: 1px solid var(--login-border);
  border-radius: 18px;
  background: var(--login-card);
  box-shadow: 0 20px 55px rgba(0, 0, 0, .14);
}
.login-card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 42px;
}
.login-logo {
  color: var(--login-primary);
  font-size: 34px;
  font-weight: 800;
  letter-spacing: .06em;
}
.theme-toggle {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 8px 11px;
  border: 1px solid var(--login-border);
  border-radius: 7px;
  background: transparent;
  color: var(--login-copy);
  font-size: 12px;
  cursor: pointer;
}
.theme-toggle:hover { color: var(--login-primary); border-color: var(--login-primary); }
.theme-toggle svg { width: 16px; height: 16px; }
.login-heading { margin-bottom: 34px; }
.login-heading h2 {
  margin: 0 0 12px;
  color: var(--login-heading);
  font-size: 30px;
  line-height: 1.3;
}
.login-heading p { margin: 0; color: var(--login-copy); font-size: 14px; line-height: 1.7; }
.login-form { display: flex; flex-direction: column; }
.field-label {
  margin: 0 0 8px;
  color: var(--login-copy);
  font-size: 14px;
  font-weight: 600;
}
.field-label:not(:first-child) { margin-top: 22px; }
.login-input {
  width: 100%;
  height: 50px;
  padding: 0 15px;
  border: 1px solid var(--login-border);
  border-radius: 7px;
  outline: none;
  background: var(--login-input);
  color: var(--login-heading);
  font-size: 14px;
  transition: border-color .2s, box-shadow .2s;
}
.login-input::placeholder { color: var(--login-dim); }
.login-input:focus { border-color: var(--login-primary); box-shadow: 0 0 0 3px rgba(56, 189, 248, .14); }
.login-input:disabled { opacity: .6; }
.form-options {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin: 20px 0 26px;
  font-size: 13px;
}
.remember-option { display: inline-flex; align-items: center; gap: 8px; color: var(--login-copy); cursor: pointer; }
.remember-option input { width: 16px; height: 16px; accent-color: var(--login-primary); }
.forgot-button {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--login-primary);
  font-size: 13px;
  cursor: pointer;
}
.login-submit {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  min-height: 50px;
  border: 0;
  border-radius: 7px;
  background: var(--login-button);
  color: #fff;
  font-size: 15px;
  font-weight: 700;
  cursor: pointer;
  transition: filter .2s, transform .2s;
}
.login-submit:hover:not(:disabled) { filter: brightness(1.08); transform: translateY(-1px); }
.login-submit:disabled { opacity: .55; cursor: not-allowed; }
.login-footnote { margin: 30px 0 0; color: var(--login-dim); font-size: 12px; text-align: center; }
.login-message { margin: 0 0 18px; padding: 10px 12px; border-radius: 6px; font-size: 12px; line-height: 1.6; }
.login-message.error { border-left: 3px solid var(--red); background: rgba(248, 113, 113, .08); color: var(--red); }
.login-message.notice { border-left: 3px solid var(--login-primary); background: rgba(56, 189, 248, .08); color: var(--login-primary); }
@media (max-width: 1050px) {
  .login-page { grid-template-columns: minmax(0, 48fr) minmax(410px, 52fr); }
  .login-card { width: calc(100% - 48px); padding: 36px 34px 28px; }
  .visual-copy h1 { font-size: 28px; }
}
@media (max-width: 760px) {
  .login-page { display: block; }
  .login-visual { display: none; }
  .login-panel { min-height: 100vh; padding: 24px 0; }
  .login-card { width: min(460px, calc(100% - 32px)); padding: 30px 24px 24px; border-radius: 14px; }
  .login-card-top { margin-bottom: 30px; }
  .login-heading { margin-bottom: 26px; }
  .login-heading h2 { font-size: 26px; }
}
@media (max-width: 390px) {
  .form-options { align-items: flex-start; gap: 10px; font-size: 12px; }
  .theme-toggle { padding: 7px 9px; }
}
</style>

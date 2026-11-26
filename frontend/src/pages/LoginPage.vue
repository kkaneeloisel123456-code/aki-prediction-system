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
const serviceState = computed(() => {
  if (auth.statusError.value) return { label: '服务连接异常', tone: 'danger' }
  if (!auth.ready.value) return { label: '正在检查服务', tone: 'checking' }
  if (!auth.configured.value) return { label: '待初始化授权', tone: 'warn' }
  return { label: '服务已就绪', tone: 'ok' }
})

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
  if (message.includes('429')) return '登录尝试次数过多，请 15 分钟后再试。'
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
      <aside class="login-corner login-corner-top" aria-label="系统状态">
        <span class="login-corner-kicker">Clinical Decision Support</span>
        <div class="login-service" :class="`is-${serviceState.tone}`">
          <i aria-hidden="true" />
          <div>
            <strong>{{ serviceState.label }}</strong>
            <span>授权访问 · 审计留痕</span>
          </div>
        </div>
        <div class="login-task-tags" aria-label="核心工作流">
          <span>风险评估</span><span>文书生成</span><span>复查管理</span>
        </div>
      </aside>

      <aside class="login-corner login-corner-bottom" aria-label="模型概览">
        <div class="login-corner-head">
          <span class="login-corner-kicker">模型概览</span>
          <span class="login-corner-code">PERIOPERATIVE</span>
        </div>
        <div class="login-model-stats">
          <div><strong>35</strong><span>项围术期指标</span></div>
          <div><strong>3</strong><span>级风险分层</span></div>
          <div><strong>SHAP</strong><span>归因解释</span></div>
        </div>
        <div class="login-model-flow" aria-label="围术期阶段">
          <span>术前</span><i aria-hidden="true" /><span>术中</span><i aria-hidden="true" /><span>ICU</span><i aria-hidden="true" /><span>术后</span>
        </div>
      </aside>

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

        <div class="login-register"><span>首次使用临床工作台？</span><RouterLink to="/register" class="pilot-link">申请医生账号 →</RouterLink></div>
        <footer class="login-foot">
          <span>仅限授权医务人员使用</span>
          <RouterLink to="/portal" class="pilot-link">患者查询入口</RouterLink>
        </footer>
      </div>
    </section>
  </main>
</template>

<style scoped>
.login-register { display:flex; flex-wrap:wrap; justify-content:space-between; gap:8px; margin-top:20px; padding:16px 0; border-top:1px solid var(--pilot-line); font-size:12px; color:var(--pilot-muted); }
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
  padding: 0 var(--pilot-space-4);
  border: 1px solid var(--pilot-line);
  border-radius: var(--pilot-radius-pill);
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
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: var(--pilot-space-6) var(--pilot-space-5);
  overflow: hidden;
  isolation: isolate;
}
.login-stage::before,
.login-stage::after {
  content: "";
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
}
.login-stage::before {
  background:
    radial-gradient(circle at 100% 0, color-mix(in srgb, var(--pilot-accent-soft) 62%, transparent), transparent 36%),
    radial-gradient(circle at 100% 100%, color-mix(in srgb, var(--pilot-surface-2) 72%, transparent), transparent 34%);
}
.login-stage::after {
  background-image:
    linear-gradient(var(--pilot-line) 1px, transparent 1px),
    linear-gradient(90deg, var(--pilot-line) 1px, transparent 1px);
  background-size: 44px 44px;
  opacity: .1;
  -webkit-mask-image:
    radial-gradient(circle at 100% 0, #000 0, transparent 48%),
    radial-gradient(circle at 100% 100%, #000 0, transparent 44%);
  mask-image:
    radial-gradient(circle at 100% 0, #000 0, transparent 48%),
    radial-gradient(circle at 100% 100%, #000 0, transparent 44%);
}
.login-corner {
  position: absolute;
  left: 50%;
  z-index: 1;
  width: min(420px, calc(100% - 2 * var(--pilot-space-5)));
  color: var(--pilot-muted);
  pointer-events: none;
  transform: translateX(-50%);
}
.login-corner-top {
  top: clamp(24px, 3.2vh, 40px);
  padding-top: var(--pilot-space-3);
  border-top: 1px solid var(--pilot-line-strong);
}
.login-corner-bottom {
  bottom: clamp(24px, 3.2vh, 40px);
  padding-top: var(--pilot-space-3);
  border-top: 1px solid var(--pilot-line);
}
.login-corner-kicker {
  display: block;
  color: var(--pilot-muted);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: .12em;
  text-transform: uppercase;
}
.login-corner-code {
  color: var(--pilot-line-strong);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: .08em;
}
.login-service {
  display: flex;
  align-items: flex-start;
  gap: var(--pilot-space-3);
  margin-top: var(--pilot-space-2);
}
.login-service i {
  flex: 0 0 auto;
  width: 6px;
  height: 6px;
  margin-top: 5px;
  border-radius: 50%;
  background: var(--pilot-muted);
}
.login-service strong {
  display: block;
  color: var(--pilot-ink);
  font-size: var(--pilot-font-xs);
  font-weight: 700;
}
.login-service span {
  display: block;
  margin-top: 2px;
  color: var(--pilot-muted);
  font-size: 10px;
  letter-spacing: .02em;
}
.login-task-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: var(--pilot-space-3);
}
.login-task-tags span {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 var(--pilot-space-3);
  border: 1px solid var(--pilot-line);
  border-radius: var(--pilot-radius-pill);
  background: color-mix(in srgb, var(--pilot-surface) 64%, transparent);
  color: var(--pilot-ink-soft);
  font-size: 10px;
  font-weight: 600;
}
.login-service.is-ok i {
  background: var(--pilot-low);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--pilot-low-soft) 80%, transparent);
}
.login-service.is-warn i {
  background: var(--pilot-mid);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--pilot-mid-soft) 80%, transparent);
}
.login-service.is-danger i {
  background: var(--pilot-high);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--pilot-high-soft) 80%, transparent);
}
.login-service.is-checking i { animation: login-service-pulse 1.4s ease-in-out infinite; }
@keyframes login-service-pulse {
  0%, 100% { opacity: .45; }
  50% { opacity: 1; }
}
.login-corner-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--pilot-space-3);
}
.login-model-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin-top: var(--pilot-space-3);
}
.login-model-stats > div {
  min-width: 0;
  padding-left: var(--pilot-space-3);
  border-left: 1px solid var(--pilot-line);
}
.login-model-stats > div:first-child {
  padding-left: 0;
  border-left: 0;
}
.login-model-stats strong {
  display: block;
  color: var(--pilot-ink);
  font-size: var(--pilot-font-lg);
  font-weight: 700;
  line-height: 1.15;
  font-variant-numeric: tabular-nums;
}
.login-model-stats span {
  display: block;
  margin-top: 2px;
  color: var(--pilot-muted);
  font-size: 10px;
  line-height: 1.35;
  white-space: nowrap;
}
.login-model-flow {
  display: flex;
  align-items: center;
  gap: var(--pilot-space-2);
  margin-top: var(--pilot-space-3);
  color: var(--pilot-muted);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: .04em;
}
.login-model-flow i {
  width: 12px;
  height: 1px;
  background: var(--pilot-line-strong);
}
.login-card {
  position: relative;
  z-index: 2;
  width: min(420px, 100%);
  padding: var(--pilot-space-6);
  border: 1px solid var(--pilot-line);
  border-radius: 18px;
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
  border-radius: 10px;
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
.login-field .pilot-input { border-radius: 10px; }
.login-card-head :deep(.theme-switch) { border-radius: 10px; }
.login-card-head :deep(.theme-switch-option) { border-radius: 8px; }
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
.login-message { margin: 0; border-radius: 10px; }
.login-submit { width: 100%; height: 44px; border-radius: 10px; }
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
@media (max-height: 1000px) and (min-width: 821px) {
  .login-task-tags { display: none; }
}
@media (max-height: 980px) and (min-width: 821px) {
  .login-model-flow { display: none; }
}
@media (max-height: 780px) and (min-width: 821px) {
  .login-corner { display: none; }
}
@media (max-width: 820px) {
  .login-page { display: block; }
  .login-corner { display: none; }
  .login-stage::before,
  .login-stage::after { display: none; }
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

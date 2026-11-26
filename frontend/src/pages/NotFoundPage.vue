<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useAuth } from '../composables/useAuth'
const auth = useAuth()
const showLogin = computed(() =>
  auth.ready.value && !auth.isAuthenticated.value && auth.configured.value,
)
onMounted(() => { void auth.restore() })
</script>

<template>
  <main class="pilot-page not-found-page">
    <div class="pilot-page-inner not-found-inner">
      <div class="not-found-code" aria-hidden="true">404</div>
      <h1 class="pilot-title">页面不存在或链接已失效</h1>
      <p class="pilot-sub">请检查地址是否完整。返回工作台可继续处理待办。</p>
      <div class="pilot-actions not-found-actions">
        <RouterLink to="/" class="pilot-btn pilot-btn-primary">返回工作台</RouterLink>
        <RouterLink v-if="showLogin" to="/login" class="pilot-btn">去登录</RouterLink>
      </div>
    </div>
  </main>
</template>

<style scoped>
.not-found-page { display: grid; place-items: center; min-height: 100vh; }
.not-found-inner { max-width: 520px; text-align: center; }
.not-found-code {
  margin-bottom: var(--pilot-space-4);
  color: var(--pilot-line-strong);
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 72px;
  font-weight: 700;
  letter-spacing: .08em;
  line-height: 1;
}
.not-found-actions { justify-content: center; margin-top: var(--pilot-space-5); }
</style>

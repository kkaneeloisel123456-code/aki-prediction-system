<script setup lang="ts">
import { useTheme } from '../composables/useTheme'

withDefaults(defineProps<{ label?: string }>(), { label: '配色' })
const { theme, setTheme } = useTheme()
</script>

<template>
  <div class="theme-switch" role="group" :aria-label="label">
    <button
      type="button"
      class="theme-switch-option"
      :aria-pressed="theme === 'light'"
      @click="setTheme('light')"
    >浅色</button>
    <button
      type="button"
      class="theme-switch-option"
      :aria-pressed="theme === 'dark'"
      @click="setTheme('dark')"
    >深色</button>
  </div>
</template>

<style scoped>
.theme-switch {
  display: inline-flex;
  gap: 2px;
  padding: 2px;
  border: 1px solid var(--pilot-line);
  border-radius: var(--pilot-radius-control);
  background: var(--pilot-surface-2);
}
.theme-switch-option {
  min-width: 48px;
  height: 30px;
  padding: 0 var(--pilot-space-2);
  border: 0;
  border-radius: 1px;
  background: transparent;
  color: var(--pilot-muted);
  font: inherit;
  font-size: var(--pilot-font-xs);
  font-weight: 600;
  cursor: pointer;
}
.theme-switch-option[aria-pressed="true"] {
  background: var(--pilot-surface);
  color: var(--pilot-ink);
  box-shadow: var(--pilot-shadow);
}
.theme-switch-option:focus-visible {
  outline: 2px solid var(--pilot-accent);
  outline-offset: 1px;
}
</style>

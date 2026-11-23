<script setup lang="ts">
defineProps<{
  title: string
  kicker?: string
  description?: string
}>()
</script>

<template>
  <header class="pilot-head app-page-header">
    <div class="app-page-header-copy">
      <div v-if="kicker" class="pilot-kicker">{{ kicker }}</div>
      <h1 class="pilot-title">{{ title }}</h1>
      <p v-if="description" class="pilot-sub">{{ description }}</p>
    </div>
    <div v-if="$slots.actions" class="pilot-actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<style scoped>
.app-page-header-copy { min-width: 0; }
@media (max-width: 650px) {
  .app-page-header { flex-direction: column; align-items: stretch; }
}
</style>

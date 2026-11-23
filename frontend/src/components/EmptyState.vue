<script setup lang="ts">
withDefaults(defineProps<{
  title: string
  description?: string
}>(), {
  description: '',
})
</script>

<template>
  <div class="pilot-empty app-empty">
    <strong class="app-empty-title">{{ title }}</strong>
    <p v-if="description" class="app-empty-copy">{{ description }}</p>
    <div v-if="$slots.default" class="app-empty-actions">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.app-empty-title {
  display: block;
  color: var(--pilot-ink);
  font-size: var(--pilot-font-md);
  font-weight: 700;
}
.app-empty-copy {
  max-width: 46ch;
  margin: var(--pilot-space-2) auto 0;
  color: var(--pilot-muted);
  font-size: var(--pilot-font-sm);
  line-height: 1.6;
}
.app-empty-actions {
  display: flex;
  justify-content: center;
  gap: var(--pilot-space-2);
  margin-top: var(--pilot-space-4);
}
</style>

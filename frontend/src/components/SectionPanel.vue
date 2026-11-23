<script setup lang="ts">
withDefaults(defineProps<{
  title?: string
  subtitle?: string
  flush?: boolean
}>(), {
  title: '',
  subtitle: '',
  flush: false,
})
</script>

<template>
  <section class="pilot-panel app-section-panel">
    <header v-if="title || $slots.actions" class="pilot-panel-head">
      <div class="app-section-panel-copy">
        <h2 v-if="title" class="pilot-panel-title">{{ title }}</h2>
        <p v-if="subtitle" class="app-section-panel-sub">{{ subtitle }}</p>
      </div>
      <div v-if="$slots.actions" class="pilot-actions">
        <slot name="actions" />
      </div>
    </header>
    <div class="pilot-panel-body" :class="{ 'is-flush': flush }">
      <slot />
    </div>
    <footer v-if="$slots.footer" class="app-section-panel-foot">
      <slot name="footer" />
    </footer>
  </section>
</template>

<style scoped>
.app-section-panel { min-width: 0; }
.app-section-panel-copy { min-width: 0; }
.app-section-panel-sub {
  margin: var(--pilot-space-1) 0 0;
  color: var(--pilot-muted);
  font-size: var(--pilot-font-xs);
}
.pilot-panel-body.is-flush { padding: 0; }
.app-section-panel-foot {
  padding: var(--pilot-space-3) var(--pilot-space-4);
  border-top: 1px solid var(--pilot-line);
}
</style>

<script setup lang="ts">
withDefaults(defineProps<{
  id: string
  label: string
  hint?: string
  error?: string
  required?: boolean
}>(), {
  hint: '',
  error: '',
  required: false,
})
</script>

<template>
  <div class="app-field" :class="{ 'has-error': error }">
    <label class="app-field-label" :for="id">
      {{ label }}<span v-if="required" class="app-field-required" aria-hidden="true">*</span>
    </label>
    <slot :id="id" :described-by="error ? `${id}-error` : (hint ? `${id}-hint` : undefined)" />
    <p v-if="hint && !error" :id="`${id}-hint`" class="app-field-hint">{{ hint }}</p>
    <p v-if="error" :id="`${id}-error`" class="app-field-error" role="alert">{{ error }}</p>
  </div>
</template>

<style scoped>
.app-field { display: flex; flex-direction: column; gap: var(--pilot-space-2); min-width: 0; }
.app-field-label {
  color: var(--pilot-muted);
  font-size: var(--pilot-font-xs);
  font-weight: 600;
}
.app-field-required { margin-left: 2px; color: var(--pilot-high); }
.app-field-hint { margin: 0; color: var(--pilot-muted); font-size: var(--pilot-font-xs); }
.app-field-error { margin: 0; color: var(--pilot-high); font-size: var(--pilot-font-xs); }
</style>

<script setup lang="ts">
type TabItem = {
  value: string
  label: string
  count?: number | null
}

defineProps<{
  modelValue: string
  tabs: TabItem[]
  label?: string
}>()

defineEmits<{
  (e: 'update:modelValue', value: string): void
}>()
</script>

<template>
  <nav class="pilot-tabs" :aria-label="label || '页面分区'">
    <button
      v-for="tab in tabs"
      :key="tab.value"
      class="pilot-tab"
      :class="{ 'is-active': modelValue === tab.value }"
      type="button"
      :aria-current="modelValue === tab.value ? 'page' : undefined"
      @click="$emit('update:modelValue', tab.value)"
    >
      <span>{{ tab.label }}</span>
      <span v-if="tab.count !== null && tab.count !== undefined" class="pilot-tab-count">{{ tab.count }}</span>
    </button>
  </nav>
</template>

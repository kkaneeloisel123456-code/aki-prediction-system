<script setup lang="ts">
export type StatusTone = 'neutral' | 'low' | 'mid' | 'high' | 'accent'

withDefaults(defineProps<{
  label: string
  tone?: StatusTone
}>(), {
  tone: 'neutral',
})
</script>

<template>
  <span class="pilot-chip" :class="tone === 'neutral' ? '' : `pilot-chip-${tone}`">{{ label }}</span>
</template>

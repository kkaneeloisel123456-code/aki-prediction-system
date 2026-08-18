import { ref, watch } from 'vue'

export type Theme = 'dark' | 'light'

const STORAGE_KEY = 'aki-theme'

function getInitial(): Theme {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved === 'light' || saved === 'dark') return saved
  } catch { /* storage blocked (private mode) — fall back to dark */ }
  return 'dark'
}

const theme = ref<Theme>(getInitial())

function apply(value: Theme) {
  document.documentElement.setAttribute('data-theme', value)
}
apply(theme.value)

watch(theme, (v) => {
  apply(v)
  try { localStorage.setItem(STORAGE_KEY, v) } catch { /* ignore */ }
})

export function useTheme() {
  const toggle = () => {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
  }
  return { theme, toggle }
}

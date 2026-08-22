import { ref } from 'vue'

export interface SelectedPatient {
  id: string
  features: Record<string, number>
  probability?: number
  riskLevel?: string
}

// sessionStorage key: survives an accidental F5 on the predict page but not
// a new browser tab (a demo-patient shouldn't leak into a fresh session).
const STORAGE_KEY = 'aki-selected-patient'

function restore(): SelectedPatient | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const p = JSON.parse(raw)
    if (p && typeof p.id === 'string' && p.features && typeof p.features === 'object') {
      return p as SelectedPatient
    }
  } catch {
    /* corrupted entry or storage disabled - start fresh */
  }
  return null
}

const selectedPatient = ref<SelectedPatient | null>(restore())

export function useSelectedPatient() {
  const set = (p: SelectedPatient) => {
    selectedPatient.value = p
    try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(p)) } catch { /* storage disabled */ }
  }
  const clear = () => {
    selectedPatient.value = null
    try { sessionStorage.removeItem(STORAGE_KEY) } catch { /* storage disabled */ }
  }
  return { selectedPatient, set, clear }
}

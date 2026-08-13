import { ref } from 'vue'

export interface SelectedPatient {
  id: string
  features: Record<string, number>
  probability?: number
  riskLevel?: string
}

const selectedPatient = ref<SelectedPatient | null>(null)

export function useSelectedPatient() {
  const set = (p: SelectedPatient) => { selectedPatient.value = p }
  const clear = () => { selectedPatient.value = null }
  return { selectedPatient, set, clear }
}

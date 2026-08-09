import type { FeaturesResponse, HealthResponse, PerformanceResponse, PredictResponse, MetaResponse, CohortResponse, DashboardDemo } from './types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...init })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

export const api = {
  health: () => request<HealthResponse>('/api/health'),
  features: () => request<FeaturesResponse>('/api/features'),
  predict: (features: Record<string, number>, patientId?: string) =>
    request<PredictResponse>('/api/predict', { method: 'POST', body: JSON.stringify({ features, patient_id: patientId }) }),
  performance: () => request<PerformanceResponse>('/api/performance'),
  meta: () => request<MetaResponse>('/api/meta'),
  figures: () => request<string[]>('/api/figures'),
  figureUrl: (name: string) => `/api/figures/${encodeURIComponent(name)}`,
  tables: () => request<string[]>('/api/tables'),
  tableData: (name: string) => fetch(`/api/tables/${encodeURIComponent(name)}`).then(r => r.json()),
  cohort: () => request<CohortResponse>('/api/workstation/cohort'),
  dashboard: () => request<DashboardDemo>('/api/dashboard/demo'),
  reportPdf: async (features: Record<string, number>) => {
    const res = await fetch('/api/report/pdf', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ features }) })
    if (!res.ok) throw new Error('PDF failed')
    return res.blob()
  },
  csvUpload: (file: File) => {
    const form = new FormData(); form.append('file', file)
    return fetch('/api/predict/csv', { method: 'POST', body: form }).then(r => r.blob())
  },
}

import type { FeaturesResponse, HealthResponse, PerformanceResponse, PredictResponse, MetaResponse, CohortResponse, DashboardDemo } from './types'

// API 地址解耦：运行时 window.AKI_API_BASE 优先，其次构建时 VITE_API_BASE，
// 缺省时与前端同源（本地由 FastAPI 托管；GitHub Pages 上需指向已部署的后端）。
const API_BASE = String(
  (window as { AKI_API_BASE?: unknown }).AKI_API_BASE ||
  import.meta.env.VITE_API_BASE ||
  ''
).replace(/\/+$/, '')

function url(path: string): string {
  return `${API_BASE}${path}`
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url(path), { headers: { 'Content-Type': 'application/json' }, ...init })
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (body?.detail) detail = String(body.detail)
    } catch { /* keep default message */ }
    throw new Error(detail)
  }
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
  figureUrl: (name: string) => url(`/api/figures/${encodeURIComponent(name)}`),
  tables: () => request<string[]>('/api/tables'),
  tableData: (name: string) => request<any>(`/api/tables/${encodeURIComponent(name)}`),
  cohort: () => request<CohortResponse>('/api/workstation/cohort'),
  dashboard: () => request<DashboardDemo>('/api/dashboard/demo'),
  imputation: () => request<{ count: number; features: Array<{ feature: string; median: number | null }> }>('/api/data/imputation'),
  dataQuality: () => request<any>('/api/data/quality'),
  templateUrl: () => url('/api/template.csv'),
  reportPdf: async (features: Record<string, number>, patientId?: string, overrideProb?: number) => {
    const res = await fetch(url('/api/report/pdf'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ features, patient_id: patientId, override_prob: overrideProb }) })
    if (!res.ok) throw new Error(`PDF 生成失败 (${res.status})`)
    return res.blob()
  },
  csvUpload: async (file: File) => {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch(url('/api/predict/csv'), { method: 'POST', body: form })
    if (!res.ok) {
      let detail = `CSV 处理失败 (${res.status})`
      try {
        const body = await res.json()
        if (body?.detail) detail = String(body.detail)
      } catch { /* keep default message */ }
      throw new Error(detail)
    }
    return res.blob()
  },
}

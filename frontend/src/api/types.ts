export interface ShapContribution { feature: string; value: number; shap: number; direction: string }
export interface HealthResponse { status: string; model_loaded: boolean; n_features: number; database_ok: boolean }
export interface AssessmentGuide {
  model_version: string
  n_features: number
  risk_low: number
  risk_high: number
  calibrated: boolean
  validation: { auc_mean: number; auc_std: number } | null
}
export type TaskStage = 'supplement' | 'assess' | 'review' | 'publish' | 'observe' | 'reconcile'
export interface ClinicalTask {
  id: string; patient_name: string; mrn: string; case_ref: string; occurred_at: string
  status: string; stage: TaskStage; can_edit: boolean; filled: number; total_features: number
  missing_count: number; invalid_count: number; risk_level: string | null
  probability: number | null; manual: boolean
}
export interface ClinicalTasks {
  counts: Record<TaskStage, number>; total: number; offset: number; limit: number; tasks: ClinicalTask[]
}
export interface FeatureMeta {
  name: string
  median: number
  timing: 'preop' | 'intraop' | 'icu' | 'postop'
  label: string | null
  unit: string | null
  reference: string | null
  input: string | null
  /** Clinical plausibility bounds used for form validation (null = none). */
  lo: number | null
  hi: number | null
}
export interface FeaturesResponse { features: string[]; metas: FeatureMeta[]; risk_low: number; risk_high: number }
export interface PredictResponse { patient_id: string | null; probability: number; prediction: number; risk_level: '低'|'中'|'高'; calibrated: boolean; shap_values: ShapContribution[]; expected_value: number; missing_filled: string[] }
export interface PerformanceResponse { cv?: Record<string, unknown>[]; calibration?: Record<string, unknown>[]; summary?: unknown[]; hosmer_lemeshow?: Record<string, unknown>[] }
export interface MetaResponse { n_features: number; n_models: number; best_auc: number | null; risk_low: number; risk_high: number }
export interface CohortPatient { id: string; age: number; sex: string; surgery: string; preScr: number; preEgfr: number; apache: number; probability: number; riskLevel: string; features?: Record<string, number> }
export interface CohortResponse { patients: CohortPatient[]; summary: { high: number; mid: number; low: number; total: number } }
export interface DashboardDemo { trend: { months: string[]; akiRates: number[]; totalCases: number[] }; departments: { name: string; cases: number; akiRate: number }[]; akiRate: number }
export interface AuthUser {
  id?: string
  username: string
  display_name?: string
  role: 'admin' | 'doctor'
  must_change_password?: boolean
}
export interface AuthStatus { authenticated: boolean; configured: boolean; user: AuthUser | null }

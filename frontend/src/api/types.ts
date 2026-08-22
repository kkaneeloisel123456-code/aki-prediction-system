export interface ShapContribution { feature: string; value: number; shap: number; direction: string }
export interface HealthResponse { status: string; model_loaded: boolean; n_features: number }
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

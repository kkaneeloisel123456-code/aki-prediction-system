import type {
  FeaturesResponse,
  HealthResponse,
  PerformanceResponse,
  PredictResponse,
  MetaResponse,
  CohortResponse,
  DashboardDemo,
} from "./types";

// FastAPI errors put a human-readable message in `detail`: either a plain
// string or (for 422 validation) an array of {loc, msg, type} objects.
// String() on the array would render "[object Object]".
function parseApiDetail(status: number, statusText: string, body: any): string {
  let detail = `${status} ${statusText}`;
  const d = body?.detail;
  if (typeof d === "string") detail = `${status}: ${d}`;
  else if (Array.isArray(d)) detail = `${status}: ${d[0]?.msg ?? JSON.stringify(d)}`;
  else if (d) detail = `${status}: ${JSON.stringify(d)}`;
  return detail;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      detail = parseApiDetail(res.status, res.statusText, await res.json());
    } catch {
      /* keep default message */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

// Shared error path for endpoints that return a Blob on success: read the
// JSON error body (if any) instead of showing a bare status code.
async function blobError(res: Response, fallback: string): Promise<Error> {
  let msg = `${fallback} (${res.status})`;
  try {
    msg = parseApiDetail(res.status, res.statusText, await res.json());
  } catch {
    /* keep default message */
  }
  return new Error(msg);
}

export const api = {
  health: () => request<HealthResponse>("/api/health"),
  features: () => request<FeaturesResponse>("/api/features"),
  predict: (features: Record<string, number>, patientId?: string) =>
    request<PredictResponse>("/api/predict", {
      method: "POST",
      body: JSON.stringify({ features, patient_id: patientId }),
    }),
  performance: () => request<PerformanceResponse>("/api/performance"),
  meta: () => request<MetaResponse>("/api/meta"),
  figures: () => request<string[]>("/api/figures"),
  figureUrl: (name: string) => `/api/figures/${encodeURIComponent(name)}`,
  cohort: () => request<CohortResponse>("/api/workstation/cohort"),
  dashboard: () => request<DashboardDemo>("/api/dashboard/demo"),
  imputation: () =>
    request<{
      count: number;
      features: Array<{ feature: string; median: number | null }>;
    }>("/api/data/imputation"),
  dataQuality: () => request<any>("/api/data/quality"),
  reportPdf: async (
    features: Record<string, number>,
    patientId?: string,
    overrideProb?: number,
  ) => {
    const res = await fetch("/api/report/pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        features,
        patient_id: patientId,
        override_prob: overrideProb,
      }),
    });
    if (!res.ok) throw await blobError(res, "PDF 生成失败");
    return res.blob();
  },
  csvUpload: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch("/api/predict/csv", { method: "POST", body: form });
    if (!res.ok) throw await blobError(res, "CSV 处理失败");
    return res.blob();
  },
};

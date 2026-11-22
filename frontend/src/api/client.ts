import type {
  FeaturesResponse,
  HealthResponse,
  PerformanceResponse,
  MetaResponse,
  AuthStatus,
} from "./types";

// FastAPI errors put a human-readable message in `detail`: either a plain
// string or (for 422 validation) an array of {loc, msg, type} objects.
const FIELD_LABELS: Record<string, string> = {
  birth_year: "出生年份", sex: "性别", mrn: "病历号", name: "姓名",
  password: "密码", new_password: "新密码", current_password: "当前密码",
  query_code: "查询码", case_ref: "就诊编号", occurred_at: "发生时间",
  diagnosis: "诊断", orders: "医嘱", capacity: "号源容量",
  certificate_last4: "证件号末四位", phone_last4: "手机号末四位",
  rating: "评分", content: "评价内容", username: "账号",
  display_name: "姓名", reason: "理由",
};

function validationDetail(d: any[]): string {
  const first = d[0] ?? {};
  const loc = Array.isArray(first.loc) ? first.loc.filter((part: any) => part !== "body") : [];
  const key = loc.length ? String(loc[loc.length - 1]) : "";
  const field = FIELD_LABELS[key] ?? (key || "提交内容");
  const msg = String(first.msg ?? "");
  if (msg.includes("at least")) return `${field}长度不足`;
  if (msg.includes("at most") || msg.toLowerCase().includes("too long")) return `${field}超出长度限制`;
  if (msg.includes("greater than or equal")) return `${field}取值过小`;
  if (msg.includes("less than or equal")) return `${field}取值过大`;
  if (msg.includes("valid integer")) return `${field}必须是整数`;
  if (msg.includes("valid string")) return `${field}格式不正确`;
  return `${field}填写有误`;
}

function parseApiDetail(status: number, statusText: string, body: any): string {
  let detail = `${status} ${statusText}`;
  const d = body?.detail;
  if (typeof d === "string") detail = d;
  else if (Array.isArray(d)) detail = `${status === 422 ? "提交内容有误：" : ""}${validationDetail(d)}`;
  else if (d) detail = JSON.stringify(d);
  return detail;
}

function cookie(name: string): string {
  const prefix = `${name}=`;
  return document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(prefix))
    ?.slice(prefix.length) ?? "";
}

function notifyUnauthorized(path: string, status: number) {
  if (status === 401 && !path.startsWith("/api/auth/") && !path.startsWith("/api/portal")) {
    window.dispatchEvent(new CustomEvent("aki:unauthorized"));
  }
  if (status === 403 && path.startsWith("/api/") && !path.startsWith("/api/portal")) {
    // Middleware uses 403 for a forced first-login password change; ordinary
    // permission failures are handled locally by the caller.
    window.dispatchEvent(new CustomEvent("aki:forbidden", { detail: path }));
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  if (method !== "GET" && method !== "HEAD" && method !== "OPTIONS") {
    const csrf = cookie("aki_csrf");
    if (csrf) headers.set("X-CSRF-Token", decodeURIComponent(csrf));
  }
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 15000);
  let res: Response;
  try {
    res = await fetch(path, {
      credentials: "same-origin",
      ...init,
      method,
      headers,
      signal: init.signal ?? controller.signal,
    });
  } catch (error: any) {
    if (error?.name === "AbortError") throw new Error("请求超时，请检查网络或稍后重试");
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
  if (!res.ok) {
    notifyUnauthorized(path, res.status);
    let detail = `${res.status} ${res.statusText}`;
    try {
      detail = parseApiDetail(res.status, res.statusText, await res.json());
    } catch {
      /* keep default message */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  const type = res.headers.get("content-type") ?? "";
  if (type.includes("application/json")) return (await res.json()) as T;
  return (await res.text()) as unknown as T;
}

async function blobError(res: Response, fallback: string): Promise<Error> {
  let msg = `${fallback} (${res.status})`;
  try {
    msg = parseApiDetail(res.status, res.statusText, await res.json());
  } catch {
    /* keep default message */
  }
  return new Error(msg);
}

async function download(path: string, fallback: string): Promise<Blob> {
  const res = await fetch(path, { credentials: "same-origin" });
  if (!res.ok) {
    notifyUnauthorized(path, res.status);
    throw await blobError(res, fallback);
  }
  return res.blob();
}

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export const api = {
  authStatus: () => request<AuthStatus>("/api/auth/status"),
  login: (username: string, password: string, remember: boolean) =>
    request<AuthStatus>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password, remember }),
    }),
  logout: () => request<AuthStatus>("/api/auth/logout", { method: "POST" }),
  changePassword: (current_password: string, new_password: string) =>
    request<any>("/api/auth/password", {
      method: "POST",
      body: JSON.stringify({ current_password, new_password }),
    }),

  health: () => request<HealthResponse>("/api/health"),
  features: () => request<FeaturesResponse>("/api/features"),
  performance: () => request<PerformanceResponse>("/api/performance"),
  meta: () => request<MetaResponse>("/api/meta"),
  figures: () => request<string[]>("/api/figures"),
  figureUrl: (name: string) => `/api/figures/${encodeURIComponent(name)}`,
  imputation: () =>
    request<{ count: number; features: Array<{ feature: string; median: number | null }> }>(
      "/api/data/imputation",
    ),
  dataQuality: () => request<any>("/api/data/quality"),

  dashboard: () => request<any>("/api/dashboard/summary"),
  workstation: () => request<any>("/api/workstation/summary"),

  patients: (query = "") => request<any>(`/api/patients${query ? `?${query}` : ""}`),
  createPatient: (payload: any) =>
    request<any>("/api/patients", { method: "POST", body: JSON.stringify(payload) }),
  patient: (id: string) => request<any>(`/api/patients/${id}`),
  updatePatient: (id: string, payload: any) =>
    request<any>(`/api/patients/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  addGrant: (id: string, payload: any) =>
    request<any>(`/api/patients/${id}/grants`, { method: "POST", body: JSON.stringify(payload) }),
  removeGrant: (id: string, doctorId: string) =>
    request<any>(`/api/patients/${id}/grants/${doctorId}`, { method: "DELETE" }),
  queryCode: (id: string) =>
    request<any>(`/api/patients/${id}/query-code`, { method: "POST" }),

  encounters: (patientId: string) => request<any>(`/api/patients/${patientId}/encounters`),
  createEncounter: (patientId: string, payload: any) =>
    request<any>(`/api/patients/${patientId}/encounters`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  encounter: (id: string) => request<any>(`/api/encounters/${id}`),
  updateEncounter: (id: string, payload: any) =>
    request<any>(`/api/encounters/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  saveDraft: (id: string, payload: any) =>
    request<any>(`/api/encounters/${id}/draft`, { method: "PUT", body: JSON.stringify(payload) }),
  deleteDraft: (id: string, draftVersion: number) =>
    request<any>(`/api/encounters/${id}/draft?draft_version=${draftVersion}`, { method: "DELETE" }),
  clinicalPredict: (id: string, payload: any) =>
    request<any>(`/api/encounters/${id}/predict`, { method: "POST", body: JSON.stringify(payload) }),
  review: (id: string, payload: any) =>
    request<any>(`/api/encounters/${id}/review`, { method: "POST", body: JSON.stringify(payload) }),
  checklist: (id: string, missingAck = false) =>
    request<any>(`/api/encounters/${id}/checklist?missing_ack=${missingAck}`),
  publish: (id: string, payload: any) =>
    request<any>(`/api/encounters/${id}/publish`, { method: "POST", body: JSON.stringify(payload) }),

  reports: (query = "") => request<any>(`/api/reports${query ? `?${query}` : ""}`),
  report: (id: string) => request<any>(`/api/reports/${id}`),
  reportPdf: (id: string) => download(`/api/reports/${id}/pdf`, "报告下载失败"),
  revokeReport: (id: string, reason: string) =>
    request<any>(`/api/reports/${id}/revoke`, { method: "POST", body: JSON.stringify({ reason }) }),

  adminUsers: () => request<any>("/api/admin/users"),
  createUser: (payload: any) =>
    request<any>("/api/admin/users", { method: "POST", body: JSON.stringify(payload) }),
  updateUser: (id: string, payload: any) =>
    request<any>(`/api/admin/users/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  doctors: () => request<any>("/api/doctors"),
  patientAccounts: () => request<any>("/api/admin/patient-accounts"),
  updatePatientAccount: (id: string, payload: any) =>
    request<any>(`/api/admin/patient-accounts/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  audit: (query = "") => request<any>(`/api/admin/audit${query ? `?${query}` : ""}`),
  system: () => request<any>("/api/admin/system"),
  backup: () => request<any>("/api/admin/backup", { method: "POST" }),

  slots: (doctorId = "") => request<any>(`/api/slots${doctorId ? `?doctor_id=${doctorId}` : ""}`),
  createSlot: (payload: any) =>
    request<any>("/api/slots", { method: "POST", body: JSON.stringify(payload) }),
  updateSlot: (id: string, payload: any) =>
    request<any>(`/api/slots/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  appointments: (query = "") => request<any>(`/api/appointments${query ? `?${query}` : ""}`),
  createAppointment: (payload: any) =>
    request<any>("/api/appointments", { method: "POST", body: JSON.stringify(payload) }),
  updateAppointment: (id: string, status: string) =>
    request<any>(`/api/appointments/${id}/status`, {
      method: "POST",
      body: JSON.stringify({ status }),
    }),
  feedback: (query = "") => request<any>(`/api/feedback${query ? `?${query}` : ""}`),
  moderateFeedback: (id: string, status: string) =>
    request<any>(`/api/feedback/${id}/moderate`, {
      method: "POST",
      body: JSON.stringify({ status }),
    }),

  importPreview: async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch("/api/imports/preview", {
      method: "POST",
      credentials: "same-origin",
      body: form,
      headers: {
        "X-CSRF-Token": decodeURIComponent(cookie("aki_csrf")),
      },
    });
    if (!res.ok) {
      notifyUnauthorized("/api/imports/preview", res.status);
      throw await blobError(res, "文件预览失败");
    }
    return res.json() as Promise<any>;
  },
  importCommit: (payload: any) =>
    request<any>("/api/imports/commit", { method: "POST", body: JSON.stringify(payload) }),

  portal: {
    status: () => request<any>("/api/portal/status"),
    register: (payload: any) =>
      request<any>("/api/portal/register", { method: "POST", body: JSON.stringify(payload) }),
    login: (username: string, password: string) =>
      request<any>("/api/portal/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      }),
    logout: () => request<any>("/api/portal/logout", { method: "POST" }),
    bind: (payload: any) =>
      request<any>("/api/portal/bind", { method: "POST", body: JSON.stringify(payload) }),
    query: (payload: any) =>
      request<any>("/api/portal/query", { method: "POST", body: JSON.stringify(payload) }),
    doctors: () => request<any>("/api/portal/doctors"),
    slots: (doctorId = "") => request<any>(`/api/portal/slots${doctorId ? `?doctor_id=${doctorId}` : ""}`),
    appointment: (payload: any) =>
      request<any>("/api/portal/appointments", { method: "POST", body: JSON.stringify(payload) }),
    cancelAppointment: (id: string, reason = "") =>
      request<any>(`/api/portal/appointments/${id}/cancel?reason=${encodeURIComponent(reason)}`, {
        method: "POST",
      }),
    appointments: () => request<any>("/api/portal/appointments"),
    feedback: (payload: any) =>
      request<any>("/api/portal/feedback", { method: "POST", body: JSON.stringify(payload) }),
    myFeedback: () => request<any>("/api/portal/feedback"),
    reports: () => request<any>("/api/portal/reports"),
    report: (id: string) => request<any>(`/api/portal/reports/${id}`),
    reportPdf: (id: string) => download(`/api/portal/reports/${id}/pdf`, "报告下载失败"),
  },
};

export { saveBlob };

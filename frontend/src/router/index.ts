import { createRouter, createWebHistory } from "vue-router";
import Dashboard from "../pages/DashboardPage.vue";
import Patients from "../pages/PatientsPage.vue";
import PatientDetail from "../pages/PatientDetailPage.vue";
import Encounter from "../pages/EncounterPage.vue";
import Reports from "../pages/ReportsPage.vue";
import ReportDetail from "../pages/ReportDetailPage.vue";
import Schedule from "../pages/SchedulePage.vue";
import Admin from "../pages/AdminPage.vue";
import Portal from "../pages/PortalPage.vue";
import Performance from "../pages/PerformancePage.vue";
import Batch from "../pages/BatchPage.vue";
import Governance from "../pages/GovernancePage.vue";
import Login from "../pages/LoginPage.vue";
import Register from "../pages/RegisterPage.vue";
import NotFound from "../pages/NotFoundPage.vue";
import { useAuth } from "../composables/useAuth";

const routes = [
  { path: "/register", component: Register, meta: { title: "医生注册", public: true } },
  { path: "/login", component: Login, meta: { title: "登录", public: true } },
  { path: "/portal", component: Portal, meta: { title: "患者服务", public: true } },
  { path: "/", component: Dashboard, meta: { title: "待评估" } },
  { path: "/patients", component: Patients, meta: { title: "患者" } },
  { path: "/patients/:id", component: PatientDetail, meta: { title: "患者病历" } },
  { path: "/encounters/:id", component: Encounter, meta: { title: "接诊与评估" } },
  { path: "/reports", component: Reports, meta: { title: "文书" } },
  { path: "/reports/:id", component: ReportDetail, meta: { title: "正式报告" } },
  { path: "/schedule", component: Schedule, meta: { title: "复查" } },
  { path: "/admin", component: Admin, meta: { title: "账号与审计", adminOnly: true } },
  { path: "/batch", component: Batch, meta: { title: "录入" } },
  { path: "/performance", component: Performance, meta: { title: "模型说明" } },
  { path: "/governance", component: Governance, meta: { title: "数据治理" } },
  // Backward-compatible redirects for bookmarks from the research prototype.
  { path: "/dashboard", redirect: "/" },
  { path: "/workstation", redirect: "/patients" },
  { path: "/report", redirect: "/reports" },
  { path: "/:catchAll(.*)", component: NotFound, meta: { title: "页面不存在", public: true } },
];
const router = createRouter({ history: createWebHistory(), routes });

router.beforeEach(async (to) => {
  const auth = useAuth();
  await auth.restore();
  if (to.meta.public) {
    // The patient portal has its own session and must remain reachable even
    // when a staff session happens to be present in the same browser.
    if (to.path === "/login" && auth.isAuthenticated.value) return { path: "/" };
    return true;
  }
  if (!auth.isAuthenticated.value) {
    return { path: "/login", query: { redirect: to.fullPath } };
  }
  if (to.meta.adminOnly && auth.user.value?.role !== "admin") {
    return { path: "/" };
  }
  return true;
});

router.afterEach((to) => {
  document.title = `${to.meta.title ?? "AKI"} · AKI 临床决策系统`;
});

export default router;

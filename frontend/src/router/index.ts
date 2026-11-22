import { createRouter, createWebHistory } from "vue-router";
import { defineComponent, h } from "vue";
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
import { useAuth } from "../composables/useAuth";

const NotFound = defineComponent({
  name: "NotFound",
  setup() {
    return () =>
      h("div", { style: "text-align:center;padding:60px 0" }, [
        h("div", { style: "font-size:42px;font-weight:800;color:var(--text-dim)" }, "404"),
        h("p", { style: "margin:10px 0 18px;color:var(--text-muted);font-size:13px" }, "页面不存在或链接已失效"),
        h("a", { href: "/", style: "color:var(--primary);font-size:13px" }, "返回工作台"),
      ]);
  },
});

const routes = [
  { path: "/login", component: Login, meta: { title: "登录", public: true } },
  { path: "/portal", component: Portal, meta: { title: "患者服务", public: true } },
  { path: "/", component: Dashboard, meta: { title: "临床工作台" } },
  { path: "/patients", component: Patients, meta: { title: "患者档案" } },
  { path: "/patients/:id", component: PatientDetail, meta: { title: "患者详情" } },
  { path: "/encounters/:id", component: Encounter, meta: { title: "接诊与报告" } },
  { path: "/reports", component: Reports, meta: { title: "报告中心" } },
  { path: "/reports/:id", component: ReportDetail, meta: { title: "正式报告" } },
  { path: "/schedule", component: Schedule, meta: { title: "预约与反馈" } },
  { path: "/admin", component: Admin, meta: { title: "账号与审计", adminOnly: true } },
  { path: "/batch", component: Batch, meta: { title: "批量导入" } },
  { path: "/performance", component: Performance, meta: { title: "模型性能" } },
  { path: "/governance", component: Governance, meta: { title: "数据治理" } },
  // Backward-compatible redirects for bookmarks from the research prototype.
  { path: "/dashboard", redirect: "/" },
  { path: "/workstation", redirect: "/patients" },
  { path: "/report", redirect: "/reports" },
  { path: "/:catchAll(.*)", component: NotFound, meta: { title: "页面不存在" } },
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

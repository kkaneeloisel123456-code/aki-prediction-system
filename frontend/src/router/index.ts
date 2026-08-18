import { createRouter, createWebHistory } from "vue-router";
import { defineComponent, h } from "vue";
import Home from "../pages/HomePage.vue";
import Performance from "../pages/PerformancePage.vue";
import Predict from "../pages/PredictPage.vue";
import Workstation from "../pages/WorkstationPage.vue";
import Dashboard from "../pages/DashboardPage.vue";
import Report from "../pages/ReportPage.vue";
import Governance from "../pages/GovernancePage.vue";
import Batch from "../pages/BatchPage.vue";

// Catch-all 404: unknown URLs used to render an empty shell (SPA fallback
// serves index.html), which looked broken during demos.
const NotFound = defineComponent({
  name: "NotFound",
  setup() {
    return () =>
      h("div", { style: "text-align:center;padding:60px 0" }, [
        h(
          "div",
          { style: "font-size:42px;font-weight:800;color:var(--text-dim)" },
          "404",
        ),
        h(
          "p",
          {
            style: "margin:10px 0 18px;color:var(--text-muted);font-size:13px",
          },
          "页面不存在或链接已失效",
        ),
        h(
          "a",
          { href: "/", style: "color:var(--primary);font-size:13px" },
          "返回首页",
        ),
      ]);
  },
});

const routes = [
  { path: "/", component: Home, meta: { title: "系统首页" } },
  { path: "/performance", component: Performance, meta: { title: "模型性能" } },
  { path: "/predict", component: Predict, meta: { title: "风险预测" } },
  {
    path: "/workstation",
    component: Workstation,
    meta: { title: "医生工作台" },
  },
  { path: "/dashboard", component: Dashboard, meta: { title: "管理仪表盘" } },
  { path: "/report", component: Report, meta: { title: "报告中心" } },
  { path: "/governance", component: Governance, meta: { title: "数据治理" } },
  { path: "/batch", component: Batch, meta: { title: "批量预测" } },
  {
    path: "/:catchAll(.*)",
    component: NotFound,
    meta: { title: "页面不存在" },
  },
];
export default createRouter({ history: createWebHistory(), routes });

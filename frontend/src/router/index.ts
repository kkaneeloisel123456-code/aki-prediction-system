import { createRouter, createWebHistory } from 'vue-router'
import Home from '../pages/HomePage.vue'
import Performance from '../pages/PerformancePage.vue'
import Predict from '../pages/PredictPage.vue'
import Workstation from '../pages/WorkstationPage.vue'
import Dashboard from '../pages/DashboardPage.vue'
import Report from '../pages/ReportPage.vue'
import Governance from '../pages/GovernancePage.vue'
import Batch from '../pages/BatchPage.vue'

const routes = [
  { path: '/', component: Home, meta: { title: '系统首页' } },
  { path: '/performance', component: Performance, meta: { title: '模型性能' } },
  { path: '/predict', component: Predict, meta: { title: '风险预测' } },
  { path: '/workstation', component: Workstation, meta: { title: '医生工作台' } },
  { path: '/dashboard', component: Dashboard, meta: { title: '管理仪表盘' } },
  { path: '/report', component: Report, meta: { title: '报告中心' } },
  { path: '/governance', component: Governance, meta: { title: '数据治理' } },
  { path: '/batch', component: Batch, meta: { title: '批量预测' } },
]
export default createRouter({ history: createWebHistory(), routes })

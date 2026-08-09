/**
 * 应用入口
 * 组装侧边栏 + 顶栏 + 路由 + 三个页面
 */
import { createSidebar, createTopbar } from './components/Sidebar.js';
import { register, startRouter } from './router.js';
import { DashboardPage } from './pages/Dashboard.js';
import { PredictPage } from './pages/Predict.js';
import { PerformancePage } from './pages/Performance.js';

// 挂载骨架
createSidebar();
createTopbar();

// 注册路由
register('dashboard', {
  title: '概览仪表盘',
  breadcrumb: 'AKI Prediction System · Dashboard',
  render: () => DashboardPage(),
});
register('predict', {
  title: '风险预测',
  breadcrumb: 'AKI Prediction System · Risk Assessment',
  render: () => PredictPage(),
});
register('performance', {
  title: '模型性能',
  breadcrumb: 'AKI Prediction System · Model Evaluation',
  render: () => PerformancePage(),
});

// 启动
startRouter('dashboard');
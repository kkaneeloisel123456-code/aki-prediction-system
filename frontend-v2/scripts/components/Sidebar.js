/**
 * 侧边栏组件
 * 纯函数式组件：返回 DOM 元素，不持有状态
 */
import { MODEL_META } from '../engine/features.js';

const NAV_ITEMS = [
  { route: 'dashboard',   label: '概览仪表盘',  icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6' },
  { route: 'predict',     label: '风险预测',    icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z' },
  { route: 'performance', label: '模型性能',    icon: 'M16 8v8m-4-5v5m-4-2v2m-2 4h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z' },
];

export function createSidebar() {
  const aside = document.querySelector('[data-sidebar]');

  aside.innerHTML = `
    <div class="sidebar__brand">
      <div class="sidebar__logo">AKI</div>
      <div>
        <div class="sidebar__title">智能预测系统</div>
        <div class="sidebar__subtitle">v2 · Clinical AI</div>
      </div>
    </div>
    <nav class="sidebar__nav">
      <div class="sidebar__nav-label">功能导航</div>
      ${NAV_ITEMS.map((item) => `
        <a class="nav-item" data-route="${item.route}" href="#${item.route}">
          <svg class="nav-item__icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8">
            <path stroke-linecap="round" stroke-linejoin="round" d="${item.icon}" />
          </svg>
          <span>${item.label}</span>
        </a>
      `).join('')}
    </nav>
    <div class="sidebar__footer">
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;">
        <span class="pulse-dot" style="background:var(--color-risk-low);"></span>
        <span>模型已加载</span>
      </div>
      AUC ${MODEL_META.auc} · ${MODEL_META.features} 特征<br/>
      白菜卷队 · 暑期数创 2026
    </div>
  `;

  return aside;
}

/** 顶栏组件 */
export function createTopbar() {
  const topbar = document.querySelector('[data-topbar]');
  topbar.innerHTML = `
    <div>
      <div class="topbar__title" data-topbar-title>概览仪表盘</div>
      <div class="topbar__breadcrumb" data-topbar-breadcrumb>AKI Prediction System</div>
    </div>
    <div class="topbar__actions">
      <div class="badge badge--neutral">
        <span class="pulse-dot" style="background:var(--color-risk-low);"></span>
        实时模式
      </div>
    </div>
  `;
  return topbar;
}
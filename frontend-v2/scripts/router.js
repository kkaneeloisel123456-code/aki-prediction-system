/**
 * 极简 hash 路由
 *
 * 路由表注册 + hashchange 监听，页面切换带过渡动画。
 * 不依赖任何路由库，约 40 行实现。
 */

const routes = new Map();
let currentRender = null;
const outlet = () => document.querySelector('[data-page-outlet]');

/**
 * 注册路由
 * @param {string} path hash 路径，如 'dashboard'
 * @param {{ title: string, breadcrumb: string, render: () => HTMLElement }} config
 */
export function register(path, config) {
  routes.set(path, config);
}

/** 启动路由：监听 hash 变化 + 首次渲染 */
export function startRouter(defaultPath = 'dashboard') {
  window.addEventListener('hashchange', render);
  // 首次加载如果没有 hash，跳转到默认页
  if (!location.hash) location.hash = defaultPath;
  else render();
}

function render() {
  const path = location.hash.slice(1) || 'dashboard';
  const route = routes.get(path) ?? routes.get('dashboard');
  const el = outlet();
  if (!el) return;

  // 页面退出动画
  el.style.opacity = '0';
  el.style.transform = 'translateY(8px)';

  setTimeout(() => {
    el.innerHTML = '';
    const page = route.render();
    page.classList.add('page-enter');
    el.appendChild(page);
    el.style.opacity = '1';
    el.style.transform = 'translateY(0)';
    el.style.transition = `opacity var(--duration-slow) var(--ease-out), transform var(--duration-slow) var(--ease-out)`;

    // 更新顶栏标题
    const titleEl = document.querySelector('[data-topbar-title]');
    const crumbEl = document.querySelector('[data-topbar-breadcrumb]');
    if (titleEl) titleEl.textContent = route.title;
    if (crumbEl) crumbEl.textContent = route.breadcrumb;

    // 更新侧边栏激活态
    document.querySelectorAll('.nav-item').forEach((item) => {
      item.classList.toggle('is-active', item.dataset.route === path);
    });

    currentRender = route;
  }, 150);
}
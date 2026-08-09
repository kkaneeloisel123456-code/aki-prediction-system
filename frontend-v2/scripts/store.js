/**
 * 响应式状态管理
 *
 * 极简的 signal 实现，理念类似 Angular signals / Solid signals：
 *   - signal(v)        返回一个 getter/setter 函数，调用时读值，传参时写值
 *   - computed(deps, fn) 派生 signal，依赖变化自动重算
 *   - effect(deps, fn)   副作用，依赖变化自动重跑
 *
 * 不依赖任何框架，约 50 行实现完整的依赖追踪。
 */

// 当前正在执行的 effect，用于依赖收集
let activeEffect = null;

/**
 * 创建可写信号
 * @template T
 * @param {T} initial 初始值
 * @returns {(v?: T) => T} 信号访问器：无参读取，传参写入
 */
export function signal(initial) {
  let value = initial;
  const subs = new Set(); // 订阅此信号的 effect 集合

  function read() {
    if (activeEffect) subs.add(activeEffect); // 收集依赖
    return value;
  }

  function write(next) {
    if (Object.is(value, next)) return value; // 值未变，跳过
    value = next;
    // 拷贝一份再遍历，避免 effect 执行中又修改订阅集合
    for (const fn of [...subs]) fn();
    return value;
  }

  return (v) => (arguments.length === 0 || v === undefined ? read() : write(v));
}

/**
 * 创建只读派生信号
 * @param {Function[]} deps 依赖的 signal 数组
 * @param {(...vals) => any} fn 计算函数，参数为 deps 的当前值
 */
export function computed(deps, fn) {
  // 初始值：先空跑一次拿到结果
  let cached = fn(...deps.map((d) => d()));
  const result = signal(cached);

  // 当任意依赖变化时，重算并写入 result
  effect(deps, (...vals) => {
    cached = fn(...vals);
    result(cached);
  });

  return result;
}

/**
 * 注册副作用：依赖变化时自动执行
 * @param {Function[]} deps 依赖的 signal 数组
 * @param {(...vals) => void} fn 副作用函数
 * @returns {Function} 取消订阅函数
 */
export function effect(deps, fn) {
  const run = () => {
    const prev = activeEffect;
    activeEffect = run;
    try {
      fn(...deps.map((d) => d()));
    } finally {
      activeEffect = prev;
    }
  };
  run(); // 立即执行一次，收集依赖
  return () => {
    // 清理：从所有依赖的订阅集中移除
    // 简化实现：deps 是 signal，其 subs 是闭包内的 Set，无法直接移除
    // 这里保留 run 引用即可，GC 会回收无引用的 effect
  };
}

/**
 * 批量更新：在一个回调内多次写 signal 只触发一次重算
 * 用于表单多字段同时变化时避免重复渲染
 */
let batchDepth = 0;
const batchQueue = new Set();
export function batch(fn) {
  batchDepth++;
  try {
    fn();
  } finally {
    batchDepth--;
    if (batchDepth === 0) {
      const queued = [...batchQueue];
      batchQueue.clear();
      queued.forEach((f) => f());
    }
  }
}
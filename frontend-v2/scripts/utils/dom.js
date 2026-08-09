/**
 * DOM 工具：函数式创建元素的轻量 helper
 * 替代 innerHTML 拼接字符串，避免 XSS 风险，支持事件绑定
 */
export function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, val] of Object.entries(props)) {
    if (key === 'class') node.className = val;
    else if (key === 'style' && typeof val === 'object') Object.assign(node.style, val);
    else if (key === 'dataset') Object.assign(node.dataset, val);
    else if (key.startsWith('on') && typeof val === 'function') {
      node.addEventListener(key.slice(2).toLowerCase(), val);
    } else if (val !== null && val !== undefined) {
      node.setAttribute(key, val);
    }
  }
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    node.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return node;
}

/** 清空元素 */
export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
  return node;
}
/**
 * SHAP 瀑布图组件
 *
 * 纯 SVG 绘制，展示 top-N 特征如何从 base value 推到最终预测值。
 * 红色=增加风险，绿色=降低风险，条带按 SHAP 值大小堆叠。
 */
const TOP_N = 10;

export function ShapWaterfall(contributions, baseValue, finalProb, container) {
  // 取绝对值最大的 TOP_N，其余归入"其他"
  const sorted = [...contributions].sort((a, b) => Math.abs(b.shap) - Math.abs(a.shap));
  const top = sorted.slice(0, TOP_N);
  const rest = sorted.slice(TOP_N);
  const restSum = rest.reduce((s, c) => s + c.shap, 0);

  const items = [...top];
  if (rest.length > 0) items.push({ label: `其他 ${rest.length} 项`, shap: restSum, isRest: true });

  // 计算瀑布图坐标
  // baseValue 是 logit，finalProb 是概率；我们用 logit 空间画瀑布
  const totalLogit = baseValue + items.reduce((s, i) => s + i.shap, 0);
  const minLogit = Math.min(baseValue, totalLogit);
  const maxLogit = Math.max(baseValue, totalLogit);
  const range = maxLogit - minLogit || 1;

  const W = 600, H = 420;
  const padL = 160, padR = 40, padT = 30, padB = 80;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;
  const barH = plotH / items.length * 0.7;
  const gap = plotH / items.length * 0.3;

  // x 坐标映射
  const xScale = (logit) => padL + ((logit - minLogit) / range) * plotW;

  // 从 baseValue 开始累加
  let currentLogit = baseValue;
  const bars = items.map((item) => {
    const startLogit = currentLogit;
    const endLogit = currentLogit + item.shap;
    currentLogit = endLogit;
    return { item, startLogit, endLogit };
  });

  const yPositions = items.map((_, i) => padT + i * (barH + gap) + gap / 2);

  container.innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" style="width:100%;">
      <!-- 标题 -->
      <text x="${padL}" y="18" font-size="12" font-weight="600" fill="var(--text-secondary)">
        SHAP 特征贡献瀑布图
      </text>
      <text x="${W - padR}" y="18" text-anchor="end" font-size="11" fill="var(--text-tertiary)">
        base logit ${baseValue.toFixed(2)} → final ${totalLogit.toFixed(2)} (p=${(finalProb*100).toFixed(1)}%)
      </text>

      <!-- 零线 -->
      <line x1="${xScale(baseValue)}" y1="${padT - 5}" x2="${xScale(baseValue)}" y2="${padT + plotH + 5}"
            stroke="var(--color-gray-300)" stroke-width="1" stroke-dasharray="3 3" />
      <text x="${xScale(baseValue)}" y="${H - padB + 20}" text-anchor="middle" font-size="10" fill="var(--text-tertiary)">
        Base
      </text>
      <text x="${xScale(totalLogit)}" y="${H - padB + 20}" text-anchor="middle" font-size="10" fill="var(--text-tertiary)">
        Final
      </text>

      <!-- 瀑布条 -->
      ${bars.map((bar, i) => {
        const y = yPositions[i];
        const x1 = xScale(Math.min(bar.startLogit, bar.endLogit));
        const x2 = xScale(Math.max(bar.startLogit, bar.endLogit));
        const w = Math.max(x2 - x1, 2);
        const isPositive = bar.item.shap > 0;
        const color = isPositive ? 'var(--color-risk-high)' : 'var(--color-risk-low)';
        const bgColor = isPositive ? 'var(--color-risk-high-bg)' : 'var(--color-risk-low-bg)';

        return `
          <!-- 连接线 -->
          ${i < bars.length - 1 ? `
            <line x1="${x2}" y1="${y + barH}" x2="${x2}" y2="${yPositions[i+1]}"
                  stroke="var(--color-gray-200)" stroke-width="1" stroke-dasharray="2 2" />
          ` : ''}

          <!-- 背景条 -->
          <rect x="${padL}" y="${y}" width="${plotW}" height="${barH}" rx="4"
                fill="${bgColor}" opacity="0.3" />

          <!-- 贡献条 -->
          <rect x="${x1}" y="${y}" width="${w}" height="${barH}" rx="4"
                fill="${color}" opacity="0.85"
                style="transition: opacity var(--duration-fast) var(--ease-out);"
                onmouseover="this.style.opacity='1'" onmouseout="this.style.opacity='0.85'">
            <title>${bar.item.label}: ${bar.item.shap >= 0 ? '+' : ''}${bar.item.shap.toFixed(3)}</title>
          </rect>

          <!-- 特征名 -->
          <text x="${padL - 8}" y="${y + barH/2 + 4}" text-anchor="end" font-size="11" fill="var(--text-secondary)">
            ${bar.item.label}
          </text>

          <!-- SHAP 值 -->
          <text x="${x2 + 6}" y="${y + barH/2 + 4}" font-size="10" font-weight="600"
                fill="${color}">
            ${bar.item.shap >= 0 ? '+' : ''}${bar.item.shap.toFixed(3)}
          </text>
        `;
      }).join('')}

      <!-- 图例 -->
      <g transform="translate(${padL}, ${H - 20})">
        <rect x="0" y="-8" width="12" height="12" rx="2" fill="var(--color-risk-high)" opacity="0.85" />
        <text x="16" y="2" font-size="10" fill="var(--text-tertiary)">增加风险</text>
        <rect x="80" y="-8" width="12" height="12" rx="2" fill="var(--color-risk-low)" opacity="0.85" />
        <text x="96" y="2" font-size="10" fill="var(--text-tertiary)">降低风险</text>
      </g>
    </svg>
  `;
}
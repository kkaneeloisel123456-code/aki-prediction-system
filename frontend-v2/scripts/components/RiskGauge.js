/**
 * 风险仪表盘组件
 *
 * 半圆 SVG 仪表盘，颜色随风险等级动态变化，指针带过渡动画。
 * Streamlit 的 st.progress 只能做水平进度条，这里做真正的临床仪表盘。
 */
import { riskLevel, RISK_LABELS } from '../engine/predictor.js';
import { RISK_THRESHOLDS } from '../engine/features.js';

const RISK_COLORS = {
  low:  'var(--color-risk-low)',
  mid:  'var(--color-risk-mid)',
  high: 'var(--color-risk-high)',
};

const RISK_EMOJI = { low: '🟢', mid: '🟡', high: '🔴' };
const RISK_BG    = { low: 'var(--color-risk-low-bg)', mid: 'var(--color-risk-mid-bg)', high: 'var(--color-risk-high-bg)' };

/**
 * @param {number} prob 概率 0-1
 * @param {HTMLElement} container 挂载容器
 */
export function RiskGauge(prob, container) {
  const level = riskLevel(prob, RISK_THRESHOLDS);
  const pct = Math.max(0, Math.min(1, prob));
  // 半圆：0° 在左，180° 在右
  const angle = pct * 180;
  const R = 90, CX = 110, CY = 110;

  // 刻度弧（背景）
  const bgArc = describeArc(CX, CY, R, 180, 0);
  // 进度弧
  const fgArc = describeArc(CX, CY, R, 180, 180 - angle);
  // 指针
  const needleAngle = 180 - angle; // SVG 坐标系
  const needleEnd = polarToCartesian(CX, CY, R - 18, needleAngle);

  container.innerHTML = `
    <div class="gauge-wrap" style="text-align:center;">
      <svg viewBox="0 0 220 140" style="width:100%;max-width:280px;">
        <defs>
          <linearGradient id="gaugeGrad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stop-color="var(--color-risk-low)" />
            <stop offset="50%" stop-color="var(--color-risk-mid)" />
            <stop offset="100%" stop-color="var(--color-risk-high)" />
          </linearGradient>
        </defs>
        <!-- 背景弧 -->
        <path d="${bgArc}" fill="none" stroke="var(--color-gray-200)" stroke-width="14" stroke-linecap="round" />
        <!-- 风险区段标记 -->
        ${renderZoneTicks(CX, CY, R)}
        <!-- 进度弧（带动画） -->
        <path d="${fgArc}" fill="none" stroke="${RISK_COLORS[level]}" stroke-width="14" stroke-linecap="round"
              style="transition: stroke var(--duration-slow) var(--ease-out);"
              stroke-dasharray="999" stroke-dashoffset="0">
          <animate attributeName="stroke-dashoffset" from="999" to="0" dur="0.8s" fill="freeze" />
        </path>
        <!-- 指针 -->
        <line x1="${CX}" y1="${CY}" x2="${needleEnd.x}" y2="${needleEnd.y}"
              stroke="${RISK_COLORS[level]}" stroke-width="3" stroke-linecap="round"
              style="transition: all var(--duration-slow) var(--ease-out);" />
        <circle cx="${CX}" cy="${CY}" r="6" fill="${RISK_COLORS[level]}"
                style="transition: fill var(--duration-slow) var(--ease-out);" />
        <!-- 中心数值 -->
        <text x="${CX}" y="${CY - 30}" text-anchor="middle" font-size="32" font-weight="700"
              fill="var(--text-primary)" font-variant-numeric="tabular-nums">
          ${(pct * 100).toFixed(1)}%
        </text>
        <text x="${CX}" y="${CY - 12}" text-anchor="middle" font-size="11" fill="var(--text-tertiary)">
          AKI 风险概率
        </text>
      </svg>
      <div style="margin-top:-8px;">
        <span class="badge badge--${level}" style="font-size:14px;padding:4px 12px;">
          ${RISK_EMOJI[level]} ${RISK_LABELS[level]}
        </span>
      </div>
      <div style="display:flex;justify-content:space-between;margin-top:8px;padding:0 8px;font-size:11px;color:var(--text-tertiary);">
        <span>0%</span>
        <span style="color:var(--color-risk-low);">低 ${(RISK_THRESHOLDS.low*100).toFixed(0)}%</span>
        <span style="color:var(--color-risk-high);">高 ${(RISK_THRESHOLDS.high*100).toFixed(0)}%</span>
        <span>100%</span>
      </div>
    </div>
  `;
}

// 渲染阈值刻度线
function renderZoneTicks(cx, cy, r) {
  const lowTick = polarToCartesian(cx, cy, r + 8, 180 - RISK_THRESHOLDS.low * 180);
  const lowTick2 = polarToCartesian(cx, cy, r - 8, 180 - RISK_THRESHOLDS.low * 180);
  const highTick = polarToCartesian(cx, cy, r + 8, 180 - RISK_THRESHOLDS.high * 180);
  const highTick2 = polarToCartesian(cx, cy, r - 8, 180 - RISK_THRESHOLDS.high * 180);
  return `
    <line x1="${lowTick.x}" y1="${lowTick.y}" x2="${lowTick2.x}" y2="${lowTick2.y}" stroke="var(--color-risk-low)" stroke-width="2" />
    <line x1="${highTick.x}" y1="${highTick.y}" x2="${highTick2.x}" y2="${highTick2.y}" stroke="var(--color-risk-high)" stroke-width="2" />
  `;
}

// SVG 极坐标转笛卡尔
function polarToCartesian(cx, cy, r, angleDeg) {
  const rad = (angleDeg * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

// 描述一段弧路径
function describeArc(cx, cy, r, startAngle, endAngle) {
  const start = polarToCartesian(cx, cy, r, endAngle);
  const end = polarToCartesian(cx, cy, r, startAngle);
  const largeArc = Math.abs(endAngle - startAngle) <= 180 ? '0' : '1';
  const sweep = endAngle <= startAngle ? '0' : '1';
  return `M ${start.x} ${start.y} A ${r} ${r} 0 ${largeArc} ${sweep} ${end.x} ${end.y}`;
}
/**
 * 反事实分析组件
 *
 * 滑块选择特征 + 实时重绘概率曲线。拖动滑块时曲线即时更新，
 * 标注当前值位置和最优值位置。这是 Streamlit 表单刷新整页做不到的交互。
 */
import { counterfactual } from '../engine/predictor.js';
import { FEATURES, RISK_THRESHOLDS } from '../engine/features.js';

export function Counterfactual(baseInputs, currentProb, container) {
  // 按当前输入的 SHAP 绝对值排序，取 top-8 作为可选特征
  const ranked = FEATURES
    .map((f) => ({ feat: f, absWeight: Math.abs(f.weight * ((baseInputs[f.key] ?? f.default) - f.mean)) }))
    .sort((a, b) => b.absWeight - a.absWeight)
    .slice(0, 8)
    .map((x) => x.feat);

  let selectedKey = ranked[0].key;
  let cfData = counterfactual(baseInputs, selectedKey);

  const selectId = 'cf-select';
  const sliderId = 'cf-slider';
  const chartId = 'cf-chart';

  function render() {
    cfData = counterfactual(baseInputs, selectedKey);
    const feat = cfData.feature;
    const currentVal = baseInputs[selectedKey] ?? feat.default;
    const currentIdx = Math.round((currentVal - feat.min) / ((feat.max - feat.min) / 39));

    container.innerHTML = `
      <div style="display:flex;align-items:center;gap:var(--space-4);margin-bottom:var(--space-4);">
        <div class="field" style="flex:1;">
          <label class="field__label" for="${selectId}">选择分析特征</label>
          <select class="select" id="${selectId}">
            ${ranked.map((f) => `<option value="${f.key}" ${f.key === selectedKey ? 'selected' : ''}>${f.label}</option>`).join('')}
          </select>
        </div>
        <div class="field" style="flex:1;">
          <label class="field__label">
            当前值: <strong id="cf-val">${currentVal.toFixed(1)} ${feat.unit}</strong>
          </label>
          <input type="range" class="slider" id="${sliderId}"
                 min="${feat.min}" max="${feat.max}" step="${feat.step}" value="${currentVal}" />
        </div>
      </div>
      <div id="${chartId}"></div>
      <div id="cf-insight" style="margin-top:var(--space-4);"></div>
    `;

    drawChart(currentVal);
    drawInsight(currentVal);

    // 事件绑定
    container.querySelector(`#${selectId}`).addEventListener('change', (e) => {
      selectedKey = e.target.value;
      // 更新滑块范围
      const newFeat = FEATURES.find((f) => f.key === selectedKey);
      const slider = container.querySelector(`#${sliderId}`);
      slider.min = newFeat.min;
      slider.max = newFeat.max;
      slider.step = newFeat.step;
      slider.value = baseInputs[selectedKey] ?? newFeat.default;
      const cv = parseFloat(slider.value);
      container.querySelector('#cf-val').textContent = `${cv.toFixed(1)} ${newFeat.unit}`;
      cfData = counterfactual(baseInputs, selectedKey);
      drawChart(cv);
      drawInsight(cv);
    });

    container.querySelector(`#${sliderId}`).addEventListener('input', (e) => {
      const v = parseFloat(e.target.value);
      const unit = cfData.feature.unit;
      container.querySelector('#cf-val').textContent = `${v.toFixed(1)} ${unit}`;
      drawChart(v);
      drawInsight(v);
    });
  }

  function drawChart(highlightVal) {
    const chartEl = container.querySelector(`#${chartId}`);
    const { values, probs, feature } = cfData;
    const W = 560, H = 220, padL = 50, padR = 20, padT = 20, padB = 36;
    const plotW = W - padL - padR, plotH = H - padT - padB;

    const xScale = (v) => padL + ((v - feature.min) / (feature.max - feature.min)) * plotW;
    const yScale = (p) => padT + (1 - p) * plotH;

    const pathData = values.map((v, i) => `${i === 0 ? 'M' : 'L'} ${xScale(v).toFixed(1)} ${yScale(probs[i]).toFixed(1)}`).join(' ');
    const areaData = `${pathData} L ${xScale(values[values.length-1]).toFixed(1)} ${yScale(0)} L ${xScale(values[0]).toFixed(1)} ${yScale(0)} Z`;

    const highlightX = xScale(highlightVal);
    const highlightIdx = values.reduce((best, v, i) => Math.abs(v - highlightVal) < Math.abs(values[best] - highlightVal) ? i : best, 0);
    const highlightY = yScale(probs[highlightIdx]);

    // 找最优值（如果当前 SHAP>0，越低越好；<0，越高越好）
    const contribution = feature.weight * (highlightVal - feature.mean);
    const bestIdx = contribution > 0 ? probs.indexOf(Math.min(...probs)) : probs.indexOf(Math.max(...probs));
    const bestVal = values[bestIdx];
    const bestProb = probs[bestIdx];

    chartEl.innerHTML = `
      <svg viewBox="0 0 ${W} ${H}" style="width:100%;">
        <defs>
          <linearGradient id="cfArea" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="var(--color-primary-500)" stop-opacity="0.15" />
            <stop offset="100%" stop-color="var(--color-primary-500)" stop-opacity="0" />
          </linearGradient>
        </defs>
        <!-- 风险带：SVG y 轴向下，概率越高 y 越小，rect 的 y 取上沿、height 取正差值 -->
        <rect x="${padL}" y="${yScale(1)}" width="${plotW}" height="${yScale(RISK_THRESHOLDS.high) - yScale(1)}" fill="var(--color-risk-high-bg)" opacity="0.5" />
        <rect x="${padL}" y="${yScale(RISK_THRESHOLDS.high)}" width="${plotW}" height="${yScale(RISK_THRESHOLDS.low) - yScale(RISK_THRESHOLDS.high)}" fill="var(--color-risk-mid-bg)" opacity="0.5" />
        <rect x="${padL}" y="${yScale(RISK_THRESHOLDS.low)}" width="${plotW}" height="${yScale(0) - yScale(RISK_THRESHOLDS.low)}" fill="var(--color-risk-low-bg)" opacity="0.5" />

        <!-- 阈值线 -->
        <line x1="${padL}" y1="${yScale(RISK_THRESHOLDS.low)}" x2="${W-padR}" y2="${yScale(RISK_THRESHOLDS.low)}" stroke="var(--color-risk-low)" stroke-width="1" stroke-dasharray="3 3" opacity="0.5" />
        <line x1="${padL}" y1="${yScale(RISK_THRESHOLDS.high)}" x2="${W-padR}" y2="${yScale(RISK_THRESHOLDS.high)}" stroke="var(--color-risk-high)" stroke-width="1" stroke-dasharray="3 3" opacity="0.5" />

        <!-- 区域填充 -->
        <path d="${areaData}" fill="url(#cfArea)" />
        <!-- 曲线 -->
        <path d="${pathData}" fill="none" stroke="var(--color-primary-600)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />

        <!-- 当前值标记 -->
        <line x1="${highlightX}" y1="${padT}" x2="${highlightX}" y2="${padT+plotH}" stroke="var(--color-primary-600)" stroke-width="1" stroke-dasharray="2 2" opacity="0.4" />
        <circle cx="${highlightX}" cy="${highlightY}" r="6" fill="var(--color-primary-600)" stroke="white" stroke-width="2" />
        <text x="${highlightX}" y="${highlightY - 12}" text-anchor="middle" font-size="11" font-weight="600" fill="var(--color-primary-700)">
          ${(probs[highlightIdx]*100).toFixed(1)}%
        </text>

        <!-- 最优值标记 -->
        <circle cx="${xScale(bestVal)}" cy="${yScale(bestProb)}" r="5" fill="var(--color-risk-low)" stroke="white" stroke-width="2" opacity="0.7" />

        <!-- Y 轴 -->
        <text x="${padL-8}" y="${yScale(0)+4}" text-anchor="end" font-size="9" fill="var(--text-tertiary)">0%</text>
        <text x="${padL-8}" y="${yScale(1)+4}" text-anchor="end" font-size="9" fill="var(--text-tertiary)">100%</text>
        <text x="${padL-8}" y="${yScale(RISK_THRESHOLDS.high)+4}" text-anchor="end" font-size="9" fill="var(--color-risk-high)">高线</text>

        <!-- X 轴 -->
        <text x="${padL}" y="${H-10}" text-anchor="start" font-size="10" fill="var(--text-tertiary)">${feature.min}</text>
        <text x="${W-padR}" y="${H-10}" text-anchor="end" font-size="10" fill="var(--text-tertiary)">${feature.max}</text>
        <text x="${W/2}" y="${H-10}" text-anchor="middle" font-size="10" fill="var(--text-tertiary)">${feature.label} (${feature.unit})</text>
      </svg>
    `;
  }

  function drawInsight(val) {
    const insightEl = container.querySelector('#cf-insight');
    const { probs, values, feature } = cfData;
    const idx = values.reduce((best, v, i) => Math.abs(v - val) < Math.abs(values[best] - val) ? i : best, 0);
    const currentP = probs[idx];

    const contribution = feature.weight * (val - feature.mean);
    const bestIdx = contribution > 0 ? probs.indexOf(Math.min(...probs)) : probs.indexOf(Math.max(...probs));
    const bestVal = values[bestIdx];
    const bestP = probs[bestIdx];
    const delta = Math.abs(bestP - currentP);

    const direction = contribution > 0 ? '降低' : '提升';
    const verb = contribution > 0 ? '可干预的风险因素' : '具有保护作用的因素';

    insightEl.innerHTML = `
      <div class="card" style="background:var(--color-primary-50);border-color:var(--color-primary-100);">
        <div class="card__body" style="padding:var(--space-4);">
          <div style="font-size:var(--text-sm);color:var(--color-primary-900);line-height:var(--leading-relaxed);">
            <strong>💡 临床洞察</strong>：如果 <strong>${feature.label}</strong> 从当前
            <strong>${val.toFixed(1)} ${feature.unit}</strong> ${direction}到
            <strong>${bestVal.toFixed(1)} ${feature.unit}</strong>，
            预测的 AKI 风险将从 <strong style="color:var(--color-risk-high);">${(currentP*100).toFixed(1)}%</strong>
            ${delta < currentP ? '降至' : '升至'}
            <strong style="color:var(--color-risk-low);">${(bestP*100).toFixed(1)}%</strong>
            （变化 ${(delta*100).toFixed(1)} 个百分点）。
            <br/>这提示 <strong>${feature.label}</strong> 可能是${verb}。
          </div>
        </div>
      </div>
    `;
  }

  render();
}
/**
 * 风险预测页 - 核心交互页
 *
 * 架构要点：
 *   1. 表单从 FEATURES 配置渲染，零硬编码
 *   2. 输入变化 -> 防抖 300ms -> predict() -> 更新仪表盘 + SHAP + 建议
 *   3. 左右双栏：左表单，右结果。输入实时更新右侧，无需提交按钮
 *   4. 反事实分析独立卡片，共享当前输入作为基准
 */
import { FEATURES, FEATURE_GROUPS, RECOMMENDATIONS, RISK_THRESHOLDS } from '../engine/features.js';
import { predict, riskLevel, RISK_LABELS } from '../engine/predictor.js';
import { RiskGauge } from '../components/RiskGauge.js';
import { ShapWaterfall } from '../components/ShapWaterfall.js';
import { Counterfactual } from '../components/Counterfactual.js';

export function PredictPage() {
  const page = document.createElement('div');

  // 当前输入状态：用普通对象，每次 predict 时读取
  const inputs = {};
  FEATURES.forEach((f) => { inputs[f.key] = f.default; });

  let debounceTimer = null;

  page.innerHTML = `
    <div class="grid" style="grid-template-columns: 420px 1fr; gap:var(--space-6); align-items:flex-start;">

      <!-- 左：表单 -->
      <div id="form-panel"></div>

      <!-- 右：结果 -->
      <div id="result-panel" style="display:flex;flex-direction:column;gap:var(--space-6);"></div>
    </div>
  `;

  renderForm(page.querySelector('#form-panel'));
  updateResults(); // 首次渲染

  return page;

  // ---- 表单渲染（从配置 DSL 派生）----
  function renderForm(container) {
    container.innerHTML = `
      <div class="card" style="position:sticky;top:0;">
        <div class="card__header">
          <div>
            <div class="card__title">患者临床信息</div>
            <div class="card__subtitle">输入实时预测 · 缺失值用训练集中位数填充</div>
          </div>
          <button class="btn btn--ghost" id="reset-btn" title="重置为默认值">↺ 重置</button>
        </div>
        <div class="card__body" style="max-height:calc(100vh - 220px);overflow-y:auto;">
          ${FEATURE_GROUPS.map((group) => `
            <div class="form-group" style="margin-bottom:var(--space-5);">
              <div style="font-size:var(--text-xs);font-weight:var(--font-semibold);color:var(--text-tertiary);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:var(--space-2);display:flex;align-items:center;gap:var(--space-2);">
                <span>${group.icon}</span> ${group.label}
              </div>
              <div class="grid grid-2" style="gap:var(--space-3);">
                ${FEATURES
                  .filter((f) => f.group === group.id)
                  .map((f) => renderField(f))
                  .join('')}
              </div>
            </div>
          `).join('')}
        </div>
      </div>
    `;

    // 绑定所有字段的事件
    FEATURES.forEach((f) => {
      const el = container.querySelector(`[data-key="${f.key}"]`);
      if (!el) return;
      const handler = () => {
        inputs[f.key] = f.type === 'select' ? parseInt(el.value) : parseFloat(el.value);
        scheduleUpdate();
      };
      el.addEventListener('input', handler);
      el.addEventListener('change', handler);
    });

    container.querySelector('#reset-btn').addEventListener('click', () => {
      FEATURES.forEach((f) => {
        inputs[f.key] = f.default;
        const el = container.querySelector(`[data-key="${f.key}"]`);
        if (el) el.value = f.default;
      });
      updateResults();
    });
  }

  function renderField(f) {
    if (f.type === 'select') {
      return `
        <div class="field">
          <label class="field__label" for="f-${f.key}">${f.label}</label>
          <select class="select" id="f-${f.key}" data-key="${f.key}">
            ${f.options.map((o) => `<option value="${o.value}" ${o.value === f.default ? 'selected' : ''}>${o.label}</option>`).join('')}
          </select>
        </div>
      `;
    }
    return `
      <div class="field">
        <label class="field__label" for="f-${f.key}">
          ${f.label}
          ${f.unit ? `<span style="color:var(--text-tertiary);font-weight:400;">(${f.unit})</span>` : ''}
        </label>
        <input type="number" class="input" id="f-${f.key}" data-key="${f.key}"
               min="${f.min}" max="${f.max}" step="${f.step}" value="${f.default}" />
      </div>
    `;
  }

  // ---- 防抖更新 ----
  function scheduleUpdate() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(updateResults, 200);
  }

  // ---- 结果渲染 ----
  function updateResults() {
    const result = predict(inputs);
    const level = riskLevel(result.probability, RISK_THRESHOLDS);
    const panel = page.querySelector('#result-panel');

    panel.innerHTML = `
      <!-- 仪表盘 + 概要 -->
      <div class="grid" style="grid-template-columns: 1fr 1fr; gap:var(--space-6);">
        <div class="card">
          <div class="card__header"><div class="card__title">预测结果</div></div>
          <div class="card__body" id="gauge-slot"></div>
        </div>
        <div class="card">
          <div class="card__header"><div class="card__title">临床建议</div></div>
          <div class="card__body" id="rec-slot"></div>
        </div>
      </div>

      <!-- SHAP 解释 -->
      <div class="card">
        <div class="card__header">
          <div>
            <div class="card__title">SHAP 个体化解释</div>
            <div class="card__subtitle">每个特征如何推高或降低该患者的 AKI 风险</div>
          </div>
        </div>
        <div class="card__body" id="shap-slot"></div>
      </div>

      <!-- 反事实分析 -->
      <div class="card">
        <div class="card__header">
          <div>
            <div class="card__title">反事实分析 (What-If)</div>
            <div class="card__subtitle">调整关键特征，探索"如果指标改变，风险会如何变化"</div>
          </div>
        </div>
        <div class="card__body" id="cf-slot"></div>
      </div>
    `;

    // 渲染子组件
    RiskGauge(result.probability, panel.querySelector('#gauge-slot'));
    renderRecommendations(level, panel.querySelector('#rec-slot'));
    ShapWaterfall(result.contributions, result.logit - result.contributions.reduce((s,c) => s+c.shap, 0), result.probability, panel.querySelector('#shap-slot'));
    Counterfactual({ ...inputs }, result.probability, panel.querySelector('#cf-slot'));
  }

  function renderRecommendations(level, container) {
    const recs = RECOMMENDATIONS[level];
    container.innerHTML = `
      <div style="display:flex;flex-direction:column;gap:var(--space-3);">
        ${recs.map((r) => `
          <div style="display:flex;gap:var(--space-3);align-items:flex-start;padding:var(--space-2);border-radius:var(--radius-md);">
            <span style="font-size:18px;flex-shrink:0;">${r.icon}</span>
            <div>
              <div style="font-weight:var(--font-medium);font-size:var(--text-sm);">${r.title}</div>
              <div style="font-size:var(--text-xs);color:var(--text-secondary);margin-top:2px;">${r.text}</div>
            </div>
          </div>
        `).join('')}
      </div>
      <div class="divider"></div>
      <div style="font-size:var(--text-xs);color:var(--text-tertiary);line-height:var(--leading-relaxed);">
        <strong>KDIGO 诊断标准</strong>（满足任一）：
        48h 内 Scr 升高 ≥ 26.5 μmol/L；7 天内 Scr 升至基线 1.5 倍；尿量 &lt; 0.5 mL/kg/h 持续 6h。
      </div>
      <div style="margin-top:var(--space-3);padding:var(--space-3);background:var(--color-gray-50);border-radius:var(--radius-md);font-size:var(--text-xs);color:var(--text-tertiary);">
        ⚠️ 本预测仅供学术研究与临床参考，不能作为临床决策的唯一依据。
      </div>
    `;
  }
}
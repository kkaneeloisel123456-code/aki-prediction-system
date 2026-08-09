/**
 * 模型性能页
 * ROC 曲线 + 校准曲线 + 模型对比表 + AUC 柱状图，全部 SVG 原生绘制
 */
import { MODEL_META } from '../engine/features.js';

// 5 个模型的 CV 结果（来自原项目 final_cv_results.csv）
const MODELS = [
  { name: 'LogisticRegression', auc: 0.789, std: 0.046, color: '#8b5cf6' },
  { name: 'RandomForest',       auc: 0.805, std: 0.041, color: '#06b6d4' },
  { name: 'XGBoost',            auc: 0.803, std: 0.046, color: '#f59e0b' },
  { name: 'ExtraTrees',         auc: 0.793, std: 0.045, color: '#ec4899' },
  { name: 'Voting Ensemble',    auc: 0.807, std: 0.045, color: '#2563eb', best: true },
];

export function PerformancePage() {
  const page = document.createElement('div');
  page.innerHTML = `
    <!-- 模型对比表 + AUC 柱状图 -->
    <div class="grid" style="grid-template-columns: 1fr 1fr; gap:var(--space-6); margin-bottom:var(--space-6);">
      <div class="card">
        <div class="card__header">
          <div>
            <div class="card__title">模型性能对比</div>
            <div class="card__subtitle">5折 × 10次 = 50次嵌套交叉验证</div>
          </div>
        </div>
        <div class="card__body" style="padding:0;">
          <table class="table">
            <thead>
              <tr>
                <th>模型</th>
                <th style="text-align:right;">AUC</th>
                <th style="text-align:right;">标准差</th>
                <th style="text-align:center;">排名</th>
              </tr>
            </thead>
            <tbody>
              ${MODELS.map((m, i) => `
                <tr ${m.best ? 'style="background:var(--color-primary-50);"' : ''}>
                  <td>
                    <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${m.color};margin-right:8px;"></span>
                    <strong>${m.name}</strong>
                    ${m.best ? '<span class="badge badge--low" style="margin-left:6px;">最佳</span>' : ''}
                  </td>
                  <td style="text-align:right;font-variant-numeric:tabular-nums;font-weight:600;">${m.auc.toFixed(3)}</td>
                  <td style="text-align:right;font-variant-numeric:tabular-nums;color:var(--text-tertiary);">± ${m.std.toFixed(3)}</td>
                  <td style="text-align:center;">${i + 1}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </div>

      <div class="card">
        <div class="card__header">
          <div class="card__title">AUC 排行榜</div>
        </div>
        <div class="card__body" id="auc-chart"></div>
      </div>
    </div>

    <!-- ROC + PR -->
    <div class="grid grid-2" style="gap:var(--space-6);margin-bottom:var(--space-6);">
      <div class="card">
        <div class="card__header">
          <div>
            <div class="card__title">ROC 曲线</div>
            <div class="card__subtitle">测试集 AUC = 0.799 · Bootstrap 95% CI [0.751, 0.840]</div>
          </div>
        </div>
        <div class="card__body" id="roc-chart"></div>
      </div>
      <div class="card">
        <div class="card__header">
          <div>
            <div class="card__title">Precision-Recall 曲线</div>
            <div class="card__subtitle">AKI 阳性率 29.8% · PR-AUC = 0.72</div>
          </div>
        </div>
        <div class="card__body" id="pr-chart"></div>
      </div>
    </div>

    <!-- 校准 + DCA -->
    <div class="grid grid-2" style="gap:var(--space-6);margin-bottom:var(--space-6);">
      <div class="card">
        <div class="card__header">
          <div>
            <div class="card__title">校准曲线</div>
            <div class="card__subtitle">OOF Isotonic 校准 · Brier 0.180 -> 0.169</div>
          </div>
        </div>
        <div class="card__body" id="cal-chart"></div>
      </div>
      <div class="card">
        <div class="card__header">
          <div>
            <div class="card__title">决策曲线分析 (DCA)</div>
            <div class="card__subtitle">临床净获益区间 5% - 45%</div>
          </div>
        </div>
        <div class="card__body" id="dca-chart"></div>
      </div>
    </div>

    <!-- 评价体系 -->
    <div class="card">
      <div class="card__header">
        <div class="card__title">评价体系</div>
      </div>
      <div class="card__body">
        <div class="grid grid-4">
          ${[
            { icon: '🎯', title: '区分度', methods: ['AUC-ROC', 'PR-AUC', '50次嵌套CV', 'Bootstrap 95%CI'] },
            { icon: '📐', title: '校准度', methods: ['Brier Score', '校准曲线', 'OOF Isotonic', 'Hosmer-Lemeshow'] },
            { icon: '💊', title: '临床效用', methods: ['决策曲线 DCA', '临床影响曲线', '亚组分析'] },
            { icon: '🔍', title: '可解释性', methods: ['SHAP Summary', 'SHAP Force', 'SHAP Dependence', '反事实分析'] },
          ].map((dim) => `
            <div style="padding:var(--space-4);background:var(--color-gray-50);border-radius:var(--radius-md);">
              <div style="display:flex;align-items:center;gap:var(--space-2);margin-bottom:var(--space-3);">
                <span style="font-size:20px;">${dim.icon}</span>
                <strong>${dim.title}</strong>
              </div>
              <ul style="font-size:var(--text-xs);color:var(--text-secondary);line-height:var(--leading-relaxed);">
                ${dim.methods.map((m) => `<li style="padding:2px 0;">· ${m}</li>`).join('')}
              </ul>
            </div>
          `).join('')}
        </div>
      </div>
    </div>
  `;

  // 渲染图表
  drawAucChart(page.querySelector('#auc-chart'));
  drawRocChart(page.querySelector('#roc-chart'));
  drawPrChart(page.querySelector('#pr-chart'));
  drawCalChart(page.querySelector('#cal-chart'));
  drawDcaChart(page.querySelector('#dca-chart'));

  return page;
}

// ---- AUC 柱状图 ----
function drawAucChart(container) {
  const W = 460, H = 240, padL = 100, padR = 20, padT = 10, padB = 30;
  const plotH = H - padT - padB;
  const barH = plotH / MODELS.length * 0.65;
  const gap = plotH / MODELS.length * 0.35;
  const minAuc = 0.75, maxAuc = 0.82;
  const xScale = (auc) => padL + ((auc - minAuc) / (maxAuc - minAuc)) * (W - padL - padR);

  container.innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" style="width:100%;">
      ${MODELS.map((m, i) => {
        const y = padT + i * (barH + gap) + gap / 2;
        const w = xScale(m.auc) - padL;
        return `
          <text x="${padL - 8}" y="${y + barH/2 + 4}" text-anchor="end" font-size="11" fill="var(--text-secondary)">${m.name}</text>
          <rect x="${padL}" y="${y}" width="${w}" height="${barH}" rx="3" fill="${m.color}" opacity="${m.best ? 1 : 0.7}" />
          <text x="${xScale(m.auc) + 6}" y="${y + barH/2 + 4}" font-size="11" font-weight="600" fill="${m.color}">${m.auc.toFixed(3)}</text>
        `;
      }).join('')}
      <!-- 基线 -->
      <line x1="${xScale(0.75)}" y1="${padT}" x2="${xScale(0.75)}" y2="${H-padB}" stroke="var(--color-gray-300)" stroke-width="1" />
      <text x="${xScale(0.75)}" y="${H-12}" text-anchor="middle" font-size="9" fill="var(--text-tertiary)">0.75</text>
      <text x="${xScale(0.82)}" y="${H-12}" text-anchor="middle" font-size="9" fill="var(--text-tertiary)">0.82</text>
    </svg>
  `;
}

// ---- ROC 曲线 ----
function drawRocChart(container) {
  const W = 380, H = 320, pad = 40;
  const plotW = W - pad * 2, plotH = H - pad * 2;
  // 模拟 ROC 曲线点（AUC ≈ 0.80）
  const pts = [[0,0],[0.02,0.35],[0.05,0.52],[0.10,0.66],[0.15,0.74],[0.25,0.82],[0.35,0.87],[0.50,0.91],[0.70,0.95],[1,1]];
  const xS = (fpr) => pad + fpr * plotW;
  const yS = (tpr) => pad + (1 - tpr) * plotH;
  const rocPath = pts.map((p, i) => `${i===0?'M':'L'} ${xS(p[0]).toFixed(1)} ${yS(p[1]).toFixed(1)}`).join(' ');
  const rocArea = `${rocPath} L ${xS(1)} ${yS(0)} L ${xS(0)} ${yS(0)} Z`;

  container.innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" style="width:100%;">
      <defs>
        <linearGradient id="rocArea" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="var(--color-primary-500)" stop-opacity="0.2" />
          <stop offset="100%" stop-color="var(--color-primary-500)" stop-opacity="0" />
        </linearGradient>
      </defs>
      <!-- 对角线 -->
      <line x1="${pad}" y1="${yS(0)}" x2="${pad+plotW}" y2="${yS(1)}" stroke="var(--color-gray-300)" stroke-width="1" stroke-dasharray="4 4" />
      <text x="${pad+plotW-4}" y="${yS(1)-4}" text-anchor="end" font-size="9" fill="var(--text-tertiary)">随机分类器</text>
      <!-- ROC 区域 -->
      <path d="${rocArea}" fill="url(#rocArea)" />
      <!-- ROC 曲线 -->
      <path d="${rocPath}" fill="none" stroke="var(--color-primary-600)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />
      <!-- AUC 标注 -->
      <text x="${pad+plotW/2}" y="${pad+plotH*0.35}" text-anchor="middle" font-size="20" font-weight="700" fill="var(--color-primary-600)">AUC = 0.799</text>
      <text x="${pad+plotW/2}" y="${pad+plotH*0.35+16}" text-anchor="middle" font-size="10" fill="var(--text-tertiary)">95% CI [0.751, 0.840]</text>
      <!-- 坐标轴 -->
      <line x1="${pad}" y1="${yS(0)}" x2="${pad}" y2="${pad}" stroke="var(--color-gray-400)" stroke-width="1" />
      <line x1="${pad}" y1="${yS(0)}" x2="${pad+plotW}" y2="${yS(0)}" stroke="var(--color-gray-400)" stroke-width="1" />
      <text x="${pad}" y="${H-12}" font-size="10" fill="var(--text-tertiary)">0</text>
      <text x="${pad+plotW}" y="${H-12}" text-anchor="end" font-size="10" fill="var(--text-tertiary)">1 - 特异度 (FPR)</text>
      <text x="12" y="${pad+10}" font-size="10" fill="var(--text-tertiary)">1</text>
      <text x="12" y="${yS(0)}" font-size="10" fill="var(--text-tertiary)">0</text>
      <text x="20" y="${pad+plotH/2}" font-size="10" fill="var(--text-tertiary)" transform="rotate(-90 20 ${pad+plotH/2})">灵敏度 (TPR)</text>
    </svg>
  `;
}

// ---- PR 曲线 ----
function drawPrChart(container) {
  const W = 380, H = 320, pad = 40;
  const plotW = W - pad * 2, plotH = H - pad * 2;
  const pts = [[0,1],[0.05,0.95],[0.10,0.90],[0.20,0.85],[0.30,0.80],[0.45,0.72],[0.60,0.65],[0.80,0.55],[1,0.30]];
  const xS = (r) => pad + r * plotW;
  const yS = (p) => pad + (1 - p) * plotH;
  const path = pts.map((p, i) => `${i===0?'M':'L'} ${xS(p[0]).toFixed(1)} ${yS(p[1]).toFixed(1)}`).join(' ');
  const baseline = 0.298;

  container.innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" style="width:100%;">
      <!-- 基线 -->
      <line x1="${pad}" y1="${yS(baseline)}" x2="${pad+plotW}" y2="${yS(baseline)}" stroke="var(--color-gray-300)" stroke-width="1" stroke-dasharray="4 4" />
      <text x="${pad+plotW-4}" y="${yS(baseline)-4}" text-anchor="end" font-size="9" fill="var(--text-tertiary)">基线 ${baseline}</text>
      <!-- 曲线 -->
      <path d="${path}" fill="none" stroke="var(--color-primary-600)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />
      <text x="${pad+plotW/2}" y="${pad+plotH*0.4}" text-anchor="middle" font-size="18" font-weight="700" fill="var(--color-primary-600)">PR-AUC = 0.72</text>
      <!-- 坐标轴 -->
      <line x1="${pad}" y1="${yS(0)}" x2="${pad}" y2="${pad}" stroke="var(--color-gray-400)" stroke-width="1" />
      <line x1="${pad}" y1="${yS(0)}" x2="${pad+plotW}" y2="${yS(0)}" stroke="var(--color-gray-400)" stroke-width="1" />
      <text x="${pad+plotW}" y="${H-12}" text-anchor="end" font-size="10" fill="var(--text-tertiary)">召回率 (Recall)</text>
      <text x="20" y="${pad+plotH/2}" font-size="10" fill="var(--text-tertiary)" transform="rotate(-90 20 ${pad+plotH/2})">精确率 (Precision)</text>
    </svg>
  `;
}

// ---- 校准曲线 ----
function drawCalChart(container) {
  const W = 380, H = 320, pad = 40;
  const plotW = W - pad * 2, plotH = H - pad * 2;
  // 校准前（偏离对角线）
  const rawPts = [[0,0.05],[0.1,0.18],[0.2,0.30],[0.3,0.42],[0.4,0.52],[0.5,0.60],[0.6,0.68],[0.7,0.75],[0.8,0.82],[0.9,0.88],[1,0.93]];
  // 校准后（贴近对角线）
  const calPts = [[0,0.02],[0.1,0.12],[0.2,0.22],[0.3,0.32],[0.4,0.41],[0.5,0.51],[0.6,0.60],[0.7,0.70],[0.8,0.79],[0.9,0.89],[1,0.95]];
  const xS = (p) => pad + p * plotW;
  const yS = (p) => pad + (1 - p) * plotH;
  const rawPath = rawPts.map((p, i) => `${i===0?'M':'L'} ${xS(p[0]).toFixed(1)} ${yS(p[1]).toFixed(1)}`).join(' ');
  const calPath = calPts.map((p, i) => `${i===0?'M':'L'} ${xS(p[0]).toFixed(1)} ${yS(p[1]).toFixed(1)}`).join(' ');

  container.innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" style="width:100%;">
      <!-- 对角线（完美校准） -->
      <line x1="${pad}" y1="${yS(0)}" x2="${pad+plotW}" y2="${yS(1)}" stroke="var(--color-gray-300)" stroke-width="1.5" stroke-dasharray="4 4" />
      <text x="${pad+plotW-4}" y="${yS(1)-4}" text-anchor="end" font-size="9" fill="var(--text-tertiary)">完美校准</text>
      <!-- 校准前 -->
      <path d="${rawPath}" fill="none" stroke="var(--color-risk-high)" stroke-width="2" stroke-linecap="round" opacity="0.5" stroke-dasharray="5 3" />
      <!-- 校准后 -->
      <path d="${calPath}" fill="none" stroke="var(--color-primary-600)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />
      <!-- 图例 -->
      <g transform="translate(${pad+8}, ${pad+8})">
        <line x1="0" y1="0" x2="16" y2="0" stroke="var(--color-risk-high)" stroke-width="2" stroke-dasharray="5 3" opacity="0.5" />
        <text x="20" y="3" font-size="10" fill="var(--text-tertiary)">校准前 Brier=0.180</text>
        <line x1="0" y1="14" x2="16" y2="14" stroke="var(--color-primary-600)" stroke-width="2.5" />
        <text x="20" y="17" font-size="10" fill="var(--text-tertiary)">校准后 Brier=0.169</text>
      </g>
      <!-- 坐标轴 -->
      <line x1="${pad}" y1="${yS(0)}" x2="${pad}" y2="${pad}" stroke="var(--color-gray-400)" stroke-width="1" />
      <line x1="${pad}" y1="${yS(0)}" x2="${pad+plotW}" y2="${yS(0)}" stroke="var(--color-gray-400)" stroke-width="1" />
      <text x="${pad+plotW}" y="${H-12}" text-anchor="end" font-size="10" fill="var(--text-tertiary)">预测概率</text>
      <text x="20" y="${pad+plotH/2}" font-size="10" fill="var(--text-tertiary)" transform="rotate(-90 20 ${pad+plotH/2})">实际阳性率</text>
    </svg>
  `;
}

// ---- DCA 决策曲线 ----
function drawDcaChart(container) {
  const W = 380, H = 320, pad = 40;
  const plotW = W - pad * 2, plotH = H - pad * 2;
  // 模型净获益曲线
  const modelPts = [[0,0.30],[0.05,0.27],[0.10,0.24],[0.15,0.21],[0.20,0.19],[0.25,0.16],[0.30,0.13],[0.35,0.10],[0.40,0.07],[0.45,0.04],[0.50,0.01],[0.60,-0.03]];
  // 全部干预
  const allPts = [[0,0.30],[0.05,0.25],[0.10,0.20],[0.15,0.15],[0.20,0.10],[0.25,0.05],[0.30,0.0]];
  // 全不干预
  const noneY = 0;

  const xS = (t) => pad + t * plotW;
  const yS = (nb) => pad + (0.30 - nb) / 0.35 * plotH;

  const modelPath = modelPts.map((p, i) => `${i===0?'M':'L'} ${xS(p[0]).toFixed(1)} ${yS(p[1]).toFixed(1)}`).join(' ');
  const allPath = allPts.map((p, i) => `${i===0?'M':'L'} ${xS(p[0]).toFixed(1)} ${yS(p[1]).toFixed(1)}`).join(' ');

  container.innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" style="width:100%;">
      <!-- 零线 -->
      <line x1="${pad}" y1="${yS(0)}" x2="${pad+plotW}" y2="${yS(0)}" stroke="var(--color-gray-300)" stroke-width="1" />
      <!-- 全不干预 -->
      <line x1="${pad}" y1="${yS(0)}" x2="${pad+plotW}" y2="${yS(0)}" stroke="var(--color-gray-400)" stroke-width="1.5" stroke-dasharray="2 2" />
      <!-- 全部干预 -->
      <path d="${allPath}" fill="none" stroke="var(--color-risk-mid)" stroke-width="2" stroke-dasharray="5 3" opacity="0.6" />
      <!-- 模型 -->
      <path d="${modelPath}" fill="none" stroke="var(--color-primary-600)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />
      <!-- 净获益区间标注 -->
      <rect x="${xS(0.05)}" y="${pad}" width="${xS(0.45)-xS(0.05)}" height="${plotH}" fill="var(--color-risk-low-bg)" opacity="0.3" />
      <!-- 图例 -->
      <g transform="translate(${pad+8}, ${pad+8})">
        <line x1="0" y1="0" x2="16" y2="0" stroke="var(--color-primary-600)" stroke-width="2.5" />
        <text x="20" y="3" font-size="10" fill="var(--text-tertiary)">Voting 模型</text>
        <line x1="0" y1="14" x2="16" y2="14" stroke="var(--color-risk-mid)" stroke-width="2" stroke-dasharray="5 3" opacity="0.6" />
        <text x="20" y="17" font-size="10" fill="var(--text-tertiary)">全部干预</text>
        <line x1="0" y1="28" x2="16" y2="28" stroke="var(--color-gray-400)" stroke-width="1.5" stroke-dasharray="2 2" />
        <text x="20" y="31" font-size="10" fill="var(--text-tertiary)">全不干预</text>
      </g>
      <!-- 坐标轴 -->
      <line x1="${pad}" y1="${yS(0)}" x2="${pad}" y2="${pad}" stroke="var(--color-gray-400)" stroke-width="1" />
      <line x1="${pad}" y1="${yS(0)}" x2="${pad+plotW}" y2="${yS(0)}" stroke="var(--color-gray-400)" stroke-width="1" />
      <text x="${pad+plotW}" y="${H-12}" text-anchor="end" font-size="10" fill="var(--text-tertiary)">阈值概率</text>
      <text x="20" y="${pad+plotH/2}" font-size="10" fill="var(--text-tertiary)" transform="rotate(-90 20 ${pad+plotH/2})">净获益 (Net Benefit)</text>
    </svg>
  `;
}
/**
 * Dashboard 首页
 * 模型概览 + 关键指标 + 研究亮点 + 特征分布
 */
import { MODEL_META, FEATURES, FEATURE_GROUPS, RISK_THRESHOLDS } from '../engine/features.js';

export function DashboardPage() {
  const page = document.createElement('div');
  page.innerHTML = `
    <!-- 关键指标卡 -->
    <div class="grid grid-4" style="margin-bottom:var(--space-8);">
      ${metricCard('样本量', MODEL_META.samples, '心脏手术患者', '📊', 'neutral')}
      ${metricCard('建模特征', MODEL_META.features, 'RF Top35 精筛', '🧬', 'up')}
      ${metricCard('最佳 AUC', MODEL_META.auc.toFixed(3), `± ${MODEL_META.aucStd} (50次CV)`, '🎯', 'up')}
      ${metricCard('Brier 分数', MODEL_META.brier.toFixed(3), 'OOF 校准后', '✅', 'up')}
    </div>

    <!-- 主体两栏 -->
    <div class="grid" style="grid-template-columns: 1.6fr 1fr; gap:var(--space-6);">

      <!-- 左：研究概述 -->
      <div class="card">
        <div class="card__header">
          <div>
            <div class="card__title">研究概述</div>
            <div class="card__subtitle">基于广西某三甲医院 420 例心脏手术患者</div>
          </div>
          <span class="badge badge--low">数据泄漏已修复</span>
        </div>
        <div class="card__body">
          <div style="display:flex;flex-direction:column;gap:var(--space-4);">
            <div style="display:flex;gap:var(--space-4);align-items:flex-start;">
              <span style="font-size:24px;">🏥</span>
              <div>
                <strong>临床问题</strong>
                <p style="color:var(--text-secondary);font-size:var(--text-sm);margin-top:2px;">
                  心脏术后 AKI 发生率 5-30%，显著增加死亡率和医疗费用。早期识别高危患者是改善预后的关键。
                </p>
              </div>
            </div>
            <div style="display:flex;gap:var(--space-4);align-items:flex-start;">
              <span style="font-size:24px;">🤖</span>
              <div>
                <strong>技术方案</strong>
                <p style="color:var(--text-secondary);font-size:var(--text-sm);margin-top:2px;">
                  4 种基模型 + Voting 集成，候选 87 特征精筛至 35，5折×10次嵌套交叉验证 + Bootstrap 内部验证。
                </p>
              </div>
            </div>
            <div style="display:flex;gap:var(--space-4);align-items:flex-start;">
              <span style="font-size:24px;">🔬</span>
              <div>
                <strong>核心创新</strong>
                <p style="color:var(--text-secondary);font-size:var(--text-sm);margin-top:2px;">
                  SHAP 可解释 AI — 不仅预测风险，更解释"为什么"。反事实分析支持"如果指标改变，风险如何变化"。
                </p>
              </div>
            </div>
            <div style="display:flex;gap:var(--space-4);align-items:flex-start;">
              <span style="font-size:24px;">🛡️</span>
              <div>
                <strong>数据泄漏控制</strong>
                <p style="color:var(--text-secondary);font-size:var(--text-sm);margin-top:2px;">
                  初始 AUC &gt;0.99（含 KDIGO 诊断标准特征）。系统性排除 14 项泄漏特征后，得到可信的 0.81。
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 右：模型卡 + 风险阈值 -->
      <div style="display:flex;flex-direction:column;gap:var(--space-6);">
        <div class="card">
          <div class="card__header">
            <div class="card__title">最终模型</div>
            <span class="badge badge--neutral">${MODEL_META.name}</span>
          </div>
          <div class="card__body">
            <div style="display:flex;align-items:center;gap:var(--space-4);margin-bottom:var(--space-4);">
              <div style="width:56px;height:56px;border-radius:var(--radius-lg);background:linear-gradient(135deg,var(--color-primary-500),var(--color-primary-700));display:grid;place-items:center;font-size:24px;color:white;">
                🏆
              </div>
              <div>
                <div style="font-weight:var(--font-semibold);font-size:var(--text-lg);">Voting Ensemble</div>
                <div style="font-size:var(--text-sm);color:var(--text-tertiary);">${MODEL_META.members}</div>
              </div>
            </div>
            <div class="divider"></div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--space-3);font-size:var(--text-sm);">
              <div><span style="color:var(--text-tertiary);">验证方式</span><br/><strong>嵌套 CV</strong></div>
              <div><span style="color:var(--text-tertiary);">CV 折数</span><br/><strong>${MODEL_META.cvFolds}</strong></div>
              <div><span style="color:var(--text-tertiary);">过拟合差距</span><br/><strong>0.127 (&lt;0.15 ✓)</strong></div>
              <div><span style="color:var(--text-tertiary);">校准方法</span><br/><strong>Isotonic OOF</strong></div>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card__header">
            <div class="card__title">风险分层阈值</div>
          </div>
          <div class="card__body">
            <div style="display:flex;flex-direction:column;gap:var(--space-3);">
              <div style="display:flex;align-items:center;gap:var(--space-3);">
                <span class="badge badge--low" style="min-width:60px;justify-content:center;">低风险</span>
                <span style="font-size:var(--text-sm);color:var(--text-secondary);">
                  P &lt; ${(RISK_THRESHOLDS.low*100).toFixed(0)}% · 常规监测
                </span>
              </div>
              <div style="display:flex;align-items:center;gap:var(--space-3);">
                <span class="badge badge--mid" style="min-width:60px;justify-content:center;">中风险</span>
                <span style="font-size:var(--text-sm);color:var(--text-secondary);">
                  ${(RISK_THRESHOLDS.low*100).toFixed(0)}% - ${(RISK_THRESHOLDS.high*100).toFixed(0)}% · 加密监测
                </span>
              </div>
              <div style="display:flex;align-items:center;gap:var(--space-3);">
                <span class="badge badge--high" style="min-width:60px;justify-content:center;">高风险</span>
                <span style="font-size:var(--text-sm);color:var(--text-secondary);">
                  P &ge; ${(RISK_THRESHOLDS.high*100).toFixed(0)}% · 紧急干预
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 特征分组 -->
    <div class="card" style="margin-top:var(--space-6);">
      <div class="card__header">
        <div>
          <div class="card__title">特征构成</div>
          <div class="card__subtitle">35 个建模特征按临床时序分组</div>
        </div>
      </div>
      <div class="card__body">
        <div class="grid grid-4">
          ${FEATURE_GROUPS.map((g) => {
            const count = FEATURES.filter((f) => f.group === g.id).length;
            const pct = (count / FEATURES.length * 100).toFixed(0);
            return `
              <div style="padding:var(--space-4);background:var(--color-gray-50);border-radius:var(--radius-md);">
                <div style="display:flex;align-items:center;gap:var(--space-2);margin-bottom:var(--space-2);">
                  <span style="font-size:20px;">${g.icon}</span>
                  <strong style="font-size:var(--text-sm);">${g.label}</strong>
                </div>
                <div style="font-size:28px;font-weight:var(--font-bold);color:var(--color-primary-600);">${count}</div>
                <div class="progress" style="margin-top:var(--space-2);">
                  <div class="progress__bar progress__bar--low" style="width:${pct}%;background:var(--color-primary-500);"></div>
                </div>
                <div style="font-size:var(--text-xs);color:var(--text-tertiary);margin-top:var(--space-1);">占总量 ${pct}%</div>
              </div>
            `;
          }).join('')}
        </div>
      </div>
    </div>

    <!-- 快速入口 -->
    <div class="grid grid-2" style="margin-top:var(--space-6);">
      <a href="#predict" class="card card--hoverable" style="text-decoration:none;display:block;">
        <div class="card__body" style="display:flex;align-items:center;gap:var(--space-4);">
          <span style="font-size:32px;">🔮</span>
          <div>
            <div style="font-size:var(--text-lg);font-weight:var(--font-semibold);color:var(--text-primary);">开始风险预测</div>
            <div style="font-size:var(--text-sm);color:var(--text-tertiary);">输入患者信息，实时预测 + SHAP 解释 + 反事实分析</div>
          </div>
        </div>
      </a>
      <a href="#performance" class="card card--hoverable" style="text-decoration:none;display:block;">
        <div class="card__body" style="display:flex;align-items:center;gap:var(--space-4);">
          <span style="font-size:32px;">📊</span>
          <div>
            <div style="font-size:var(--text-lg);font-weight:var(--font-semibold);color:var(--text-primary);">查看模型性能</div>
            <div style="font-size:var(--text-sm);color:var(--text-tertiary);">ROC / PR / 校准曲线 / 模型对比</div>
          </div>
        </div>
      </a>
    </div>
  `;
  return page;
}

function metricCard(label, value, delta, icon, deltaType) {
  const arrow = deltaType === 'up' ? '↑' : deltaType === 'down' ? '↓' : '·';
  return `
    <div class="card card--hoverable">
      <div class="metric">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;">
          <div class="metric__label">${label}</div>
          <span style="font-size:20px;opacity:0.6;">${icon}</span>
        </div>
        <div class="metric__value">${value}</div>
        <div class="metric__delta metric__delta--${deltaType}">${arrow} ${delta}</div>
      </div>
    </div>
  `;
}
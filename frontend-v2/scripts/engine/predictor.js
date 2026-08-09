/**
 * Mock 预测引擎
 *
 * 用线性 logit 模型模拟真实模型的预测行为：
 *   logit = BASELINE + Σ(weight_i × (value_i - mean_i))
 *   prob  = sigmoid(logit)
 *
 * SHAP 近似：对线性模型，SHAP_i = weight_i × (value_i - mean_i)，这是精确值。
 * 对树模型这是近似，但足以展示交互逻辑和可解释性叙事。
 *
 * 反事实分析：固定其他特征，扫描单个特征值范围，得到概率曲线。
 */

import { FEATURES, BASELINE_LOGIT } from './features.js';

const sigmoid = (x) => 1 / (1 + Math.exp(-x));

// 特征查找索引，避免每次线性查找
const FEATURE_MAP = new Map(FEATURES.map((f) => [f.key, f]));

/**
 * 计算预测概率
 * @param {Object} inputs 特征键值对象 { '年龄': 55, '术前Scr': 80, ... }
 * @returns {{ probability: number, logit: number, contributions: Array }}
 */
export function predict(inputs) {
  let logit = BASELINE_LOGIT;
  const contributions = [];

  for (const feat of FEATURES) {
    const val = inputs[feat.key] ?? feat.default;
    const contribution = feat.weight * (val - feat.mean);
    logit += contribution;
    contributions.push({
      key: feat.key,
      label: feat.label,
      value: val,
      weight: feat.weight,
      mean: feat.mean,
      shap: contribution, // 线性模型 SHAP = w*(x-E[x])
      unit: feat.unit,
    });
  }

  return {
    probability: sigmoid(logit),
    logit,
    contributions: contributions.sort((a, b) => Math.abs(b.shap) - Math.abs(a.shap)),
  };
}

/**
 * 反事实分析：扫描单个特征，返回概率曲线
 * @param {Object} baseInputs 基准输入（其他特征固定）
 * @param {string} featureKey 要扫描的特征键
 * @param {number} n 采样点数
 * @returns {{ values: number[], probs: number[], feature: Object }}
 */
export function counterfactual(baseInputs, featureKey, n = 40) {
  const feat = FEATURE_MAP.get(featureKey);
  if (!feat) return null;

  const { min, max } = feat;
  const step = (max - min) / (n - 1);
  const values = [];
  const probs = [];

  for (let i = 0; i < n; i++) {
    const v = min + step * i;
    values.push(v);
    probs.push(predict({ ...baseInputs, [featureKey]: v }).probability);
  }

  return { values, probs, feature: feat };
}

/**
 * 根据概率和阈值判定风险等级
 */
export function riskLevel(prob, thresholds) {
  if (prob < thresholds.low) return 'low';
  if (prob < thresholds.high) return 'mid';
  return 'high';
}

export const RISK_LABELS = { low: '低风险', mid: '中风险', high: '高风险' };
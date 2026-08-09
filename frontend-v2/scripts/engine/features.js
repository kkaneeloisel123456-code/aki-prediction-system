/**
 * 特征配置 DSL
 *
 * 这是整个应用的"单一事实来源"——表单 UI、预测引擎、SHAP 计算、
 * 反事实分析全部从这份配置派生。增删特征只需改这一处，无需触碰 UI 代码。
 *
 * 设计要点：
 *   - group: 表单分组（4 组，对应临床时序）
 *   - weight: mock 预测权重（正=风险因子，负=保护因子）
 *   - mean:   训练集中位数，SHAP 近似用 (value - mean) * weight
 *   - 整体 baseline logit ≈ -1.2，使中位数患者概率 ≈ 0.23（接近真实 AKI 基线发病率）
 */

export const FEATURE_GROUPS = [
  { id: 'basic', label: '患者基本信息', icon: '👤' },
  { id: 'preop', label: '术前实验室指标', icon: '🧪' },
  { id: 'intra', label: '术中 / ICU 入室', icon: '🏥' },
  { id: 'post',  label: '术后早期指标', icon: '📊' },
];

export const FEATURES = [
  // ---- 患者基本信息 ----
  { key: '年龄',         label: '年龄',          unit: '岁',     min: 18,  max: 100,  step: 1,    default: 55,  group: 'basic', weight: 0.045,  mean: 55 },
  { key: '性别',         label: '性别',          unit: '',       min: 1,   max: 2,    step: 1,    default: 1,   group: 'basic', weight: -0.15,  mean: 1.4, type: 'select', options: [{value:1,label:'男'},{value:2,label:'女'}] },
  { key: '高血压',       label: '高血压',        unit: '',       min: 0,   max: 1,    step: 1,    default: 0,   group: 'basic', weight: 0.28,   mean: 0.4, type: 'select', options:[{value:0,label:'否'},{value:1,label:'是'}] },
  { key: '糖尿病',       label: '糖尿病',        unit: '',       min: 0,   max: 1,    step: 1,    default: 0,   group: 'basic', weight: 0.35,   mean: 0.2, type: 'select', options:[{value:0,label:'否'},{value:1,label:'是'}] },
  { key: '冠心病',       label: '冠心病',        unit: '',       min: 0,   max: 1,    step: 1,    default: 0,   group: 'basic', weight: 0.22,   mean: 0.3, type: 'select', options:[{value:0,label:'否'},{value:1,label:'是'}] },
  { key: 'APACHEII',     label: 'APACHE II 评分',unit: '分',     min: 0,   max: 60,   step: 1,    default: 18,  group: 'basic', weight: 0.038,  mean: 18 },
  { key: '手术时间',     label: '手术时间',      unit: 'min',    min: 30,  max: 1440, step: 10,   default: 300, group: 'basic', weight: 0.0018, mean: 300 },

  // ---- 术前实验室指标 ----
  { key: '术前Scr',      label: '术前肌酐 Scr',  unit: 'μmol/L', min: 20,  max: 500,  step: 1,    default: 80,  group: 'preop', weight: 0.008,  mean: 80 },
  { key: '术前eGFR',     label: '术前 eGFR',     unit: '',       min: 10,  max: 150,  step: 1,    default: 90,  group: 'preop', weight: -0.012, mean: 90 },
  { key: '术前Alb',      label: '术前白蛋白',    unit: 'g/L',    min: 15,  max: 60,   step: 0.1,  default: 40,  group: 'preop', weight: -0.025, mean: 40 },
  { key: '术前Hb',       label: '术前血红蛋白',  unit: 'g/L',    min: 50,  max: 200,  step: 1,    default: 130, group: 'preop', weight: -0.004, mean: 130 },
  { key: '术前WBC',      label: '术前白细胞',    unit: 'x10⁹/L', min: 1,   max: 30,   step: 0.1,  default: 7,   group: 'preop', weight: 0.04,   mean: 7 },
  { key: '术前CRP',      label: '术前 CRP',      unit: 'mg/L',   min: 0,   max: 200,  step: 0.1,  default: 5,   group: 'preop', weight: 0.006,  mean: 5 },
  { key: '术前Lactate',  label: '术前乳酸',      unit: 'mmol/L', min: 0.1, max: 15,   step: 0.1,  default: 1.0, group: 'preop', weight: 0.15,   mean: 1.0 },
  { key: '术前BNP',      label: '术前 BNP',      unit: 'pg/mL',  min: 10,  max: 25000,step: 10,   default: 500, group: 'preop', weight: 0.00008,mean: 500 },
  { key: '术前NLR',      label: '术前 NLR',      unit: '',       min: 0.1, max: 30,   step: 0.1,  default: 3.0, group: 'preop', weight: 0.05,   mean: 3.0 },
  { key: '术前Urea',     label: '术前尿素',      unit: 'mmol/L', min: 1,   max: 25,   step: 0.1,  default: 5.5, group: 'preop', weight: 0.04,   mean: 5.5 },
  { key: '术前UA',       label: '术前尿酸',      unit: 'μmol/L', min: 100, max: 900,  step: 10,   default: 400, group: 'preop', weight: 0.001,  mean: 400 },

  // ---- 术中 / ICU 入室 ----
  { key: '术中失血量',   label: '术中失血量',    unit: 'mL',     min: 0,   max: 5000, step: 10,   default: 400, group: 'intra', weight: 0.0003,mean: 400 },
  { key: '术中尿量',     label: '术中尿量',      unit: 'mL',     min: 0,   max: 10000,step: 10,   default: 1000,group: 'intra', weight: -0.00015,mean:1000 },
  { key: '术中晶体液量', label: '术中晶体液',    unit: 'mL',     min: 0,   max: 5000, step: 10,   default: 700, group: 'intra', weight: 0.00005,mean: 700 },
  { key: 'ICUAdmSCr',    label: 'ICU入室Scr',    unit: 'μmol/L', min: 20,  max: 500,  step: 1,    default: 80,  group: 'intra', weight: 0.010, mean: 80 },
  { key: 'ICUAdmeGFR',   label: 'ICU入室eGFR',   unit: '',       min: 10,  max: 150,  step: 1,    default: 90,  group: 'intra', weight: -0.014,mean: 90 },

  // ---- 术后早期指标 ----
  { key: '术后hsTn',     label: '术后 hsTn',     unit: 'pg/mL',  min: 0,   max: 10000,step: 1,    default: 572, group: 'post',  weight: 0.00006,mean:572 },
  { key: '术后Lactate',  label: '术后乳酸',      unit: 'mmol/L', min: 0,   max: 20,   step: 0.1,  default: 4.7, group: 'post',  weight: 0.12,  mean: 4.7 },
  { key: '术后BNP',      label: '术后 BNP',      unit: 'pg/mL',  min: 0,   max: 50000,step: 10,   default: 1000,group: 'post',  weight: 0.00003,mean:1000 },
  { key: '术后CRP',      label: '术后 CRP',      unit: 'mg/L',   min: 0,   max: 300,  step: 0.1,  default: 60,  group: 'post',  weight: 0.003, mean: 60 },
  { key: '术后PLR',      label: '术后 PLR',      unit: '',       min: 20,  max: 1000, step: 1,    default: 200, group: 'post',  weight: 0.001, mean: 200 },
  { key: '术后Urea',     label: '术后尿素',      unit: 'mmol/L', min: 1,   max: 40,   step: 0.1,  default: 6.1, group: 'post',  weight: 0.05,  mean: 6.1 },
  { key: '术后BE',       label: '术后碱剩余',    unit: 'mmol/L', min: -20, max: 20,   step: 0.1,  default: -2.8,group: 'post',  weight: -0.08, mean: -2.8 },
  { key: '术后Alb',      label: '术后白蛋白',    unit: 'g/L',    min: 15,  max: 60,   step: 0.1,  default: 30,  group: 'post',  weight: -0.03, mean: 30 },
  { key: '术后PaO2',     label: '术后 PaO2',     unit: 'mmHg',   min: 30,  max: 600,  step: 1,    default: 169, group: 'post',  weight: -0.001,mean: 169 },
  { key: '术后PLT',      label: '术后血小板',    unit: 'x10⁹/L', min: 20,  max: 800,  step: 1,    default: 144, group: 'post',  weight: -0.001,mean: 144 },
  { key: '术后β2MG',     label: '术后 β2MG',     unit: 'mg/L',   min: 0,   max: 20,   step: 0.1,  default: 2.1, group: 'post',  weight: 0.08,  mean: 2.1 },
  { key: '术后Mb',       label: '术后肌红蛋白',  unit: 'ng/mL',  min: 0,   max: 5000, step: 1,    default: 308, group: 'post',  weight: 0.0002,mean: 308 },
];

// 模型 baseline logit，使中位数患者概率 ≈ 0.23
export const BASELINE_LOGIT = -1.2;

// 模型元信息（展示用）
export const MODEL_META = {
  name: 'Voting Ensemble',
  members: 'LR + RF + XGBoost + ExtraTrees',
  features: FEATURES.length,
  auc: 0.807,
  aucStd: 0.045,
  cvFolds: '5折 × 10次 = 50次嵌套CV',
  brier: 0.169,
  samples: 420,
};

// 风险分层阈值
export const RISK_THRESHOLDS = { low: 0.30, high: 0.60 };

// 临床建议库：按风险等级映射
export const RECOMMENDATIONS = {
  low: [
    { icon: '👁️', title: '常规监测', text: '每 12h 记录尿量，每日复查 Scr、eGFR' },
    { icon: '💧', title: '维持水化', text: '维持充足水化，避免肾毒性药物' },
    { icon: '📋', title: '复查计划', text: '术后第 1、3 天复查 Scr、eGFR' },
  ],
  mid: [
    { icon: '⏱️', title: '加密监测', text: '每 6h 监测尿量和 Scr 变化' },
    { icon: '🎯', title: '目标导向液体', text: '维持尿量 > 0.5 mL/kg/h' },
    { icon: '🔬', title: '每日复查', text: 'Scr、eGFR、电解质、血气' },
    { icon: '🩺', title: '肾内科会诊', text: '建议肾内科会诊评估' },
  ],
  high: [
    { icon: '⚠️', title: '持续监护', text: '每小时尿量 + 持续有创血压监测' },
    { icon: '🚨', title: 'KDIGO Bundle', text: '优化容量 + 停肾毒性药 + 维持肾灌注' },
    { icon: '⚡', title: '即刻复查', text: 'Scr、eGFR，考虑肾脏超声' },
    { icon: '🏥', title: '紧急会诊', text: '紧急肾内科会诊，准备 RRT 评估' },
  ],
};
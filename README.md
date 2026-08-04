# AKI 急性肾损伤智能预测系统

## 项目简介

基于广西某三甲医院临床数据（420例），利用多种机器学习算法构建急性肾损伤（AKI）预测模型。通过 SHAP 可解释性分析 + DCA 决策曲线 + 嵌套式交叉验证 + Bootstrap 内部验证，为临床决策提供透明、可信的个体化风险评估。最终部署为 Streamlit 在线临床决策支持系统。

**🏆 暑期数创 2026 · 白菜卷队 · 广西科技大学**

---

## 评委 / 新手快速启动（推荐）

1. 解压项目压缩包
2. 双击 `启动系统.bat`
3. 脚本会自动创建虚拟环境、安装依赖，并启动 Web 系统
4. 浏览器访问 https://aki-prediction.streamlit.app

也可以手动运行，见下方“快速开始”。

---

## 模型性能

| 指标 | 数值 |
|------|------|
| **5折×10次=50次嵌套CV AUC** | **0.8066 ± 0.0456** |
| 测试集 AUC | 0.799 |
| Bootstrap AUC (OOF，1000次) | 0.797 [0.752, 0.840] |
| OOF校准后 Brier | 0.168（原始 0.180） |
| 过拟合差距 | 0.127（可接受范围，<0.15） |
| 最佳模型 | Voting Ensemble (LR:2, RF:2, XGB:1, ET:1) |
| 使用特征 | 35 个 (RF重要性Top35) |
| 验证方式 | RepeatedStratifiedKFold 嵌套式 (5折 × 10次 = 50次评估) |

| 模型 | 50次CV AUC | 标准差 |
|------|-----------|--------|
| LogisticRegression | 0.790 | 0.046 |
| RandomForest | 0.806 | 0.042 |
| XGBoost | 0.802 | 0.047 |
| ExtraTrees | 0.794 | 0.045 |
| **Voting Ensemble** | **0.807** | **0.046** |

---

## 高级方法对比（Wave 1，2026-08-04）

新增 `run_advanced.py`，与 `run_clean.py` 共用同一套数据准备与泄漏规则。所有实验（调参、特征选择、交互项、Stacking/Blending）都在训练折内完成，统一用嵌套 CV 报告。

| 配置 | 25折AUC | 说明 |
|------|---------|------|
| **Voting (LR:2, RF:2, XGB:1, ET:1)** | **0.8070 ± 0.0433** | 当前最终模型 |
| LogisticRegression | 0.7928 ± 0.0457 | 固定正则化配置 |
| RandomForest | 0.8051 ± 0.0376 | 固定正则化配置 |
| XGBoost | 0.7999 ± 0.0435 | 固定正则化配置 |
| ExtraTrees | 0.7950 ± 0.0396 | 固定正则化配置 |
| Stacking | 0.7741 ± 0.0415 | 未超过 Voting |
| OOF加权 Blending | 0.7994 ± 0.0402 | 未超过 Voting |

### Optuna 贝叶斯调参（同一5折上对比，每折20 trials，内层3折CV）

| 模型 | 固定配置 AUC | Optuna 调优 AUC |
|------|-------------|----------------|
| LogisticRegression | 0.7890 | 0.7862 |
| RandomForest | 0.8000 | 0.7942 |
| XGBoost | 0.7863 | 0.7642 |
| ExtraTrees | 0.7955 | 0.7943 |
| Voting | 0.8020 | 保持固定权重 |

**结论**：420例/125事件下，Optuna 搜索并未显著超过手工强正则化配置；Voting 集成仍是最优，因此不更换最终模型，但该对比本身可作为方法严谨性证据写入报告。

### 特征选择与交互项

| 特征方案 | AUC（10折） | 中位特征数 |
|----------|-------------|-----------|
| RF Top35（当前方案） | 0.8073 ± 0.0402 | 30 |
| RF Top20 | 0.8006 ± 0.0380 | 20 |
| RFECV | 0.8060 ± 0.0336 | 67 |
| Boruta-lite | 0.8008 ± 0.0340 | 16 |

| 方案 | AUC（15折） |
|------|-------------|
| 无交互项（当前方案） | 0.8065 ± 0.0484 |
| 6个临床交互项 | 0.8070 ± 0.0476 |

**结论**：交互项增益约 +0.0005，RFECV 与 Top35 相当但特征更多。考虑到 EPV=3.6，保持当前 35 特征方案不变。

运行：`python run_advanced.py`

---

## Wave 2：填补 / 过采样 / 阈值 / 不确定性（2026-08-04）

新增 `run_wave2.py`。与 Wave 1 的差异是：Wave 2 使用**未做全局中位数填补的原始候选矩阵**，所有填补、缩放、筛选、过采样都在训练折内完成，避免隐含的全局填补泄漏。

### MICE 与中位数填补对比（5折 x 3次，训练折内拟合）

| 填补方案 | AUC | Brier |
|----------|-----|-------|
| 中位数填补（当前方案） | 0.8065 ± 0.0484 | 0.1784 |
| MICE（IterativeImputer） | 0.8052 ± 0.0473 | 0.1791 |

结论：MICE 未带来增益，中位数填补在 420 例规模下更简单、更稳定，保留现状。

### SMOTE 与 class_weight 对比（5折 x 3次）

| 配置 | AUC | Brier |
|------|-----|-------|
| XGB + scale_pos_weight（当前） | 0.7967 ± 0.0491 | 0.1701 |
| XGB + SMOTE（无权重） | 0.7861 ± 0.0439 | 0.1768 |
| LR + class_weight=balanced（当前） | 0.7958 ± 0.0492 | 0.1842 |
| LR + SMOTE（无权重） | 0.7929 ± 0.0460 | 0.1845 |

结论：SMOTE 未超过 class_weight / scale_pos_weight，保留现有类别权重策略。

### DCA 阈值推荐与成本效益（5折 OOF）

- 推荐决策阈值：**0.29**（模型净获益超过“全部干预”和“不干预”的最大增量点）
- OOF AUC：0.7967

| 干预成本/AKI成本 | 对应阈值 | 每千例真阳 | 每千例假阳 | 净获益差值/千例 |
|-----------------|---------|-----------|-----------|-----------------|
| 0.1 | 0.091 | 297.6 | 692.9 | +0.95 |
| 0.2 | 0.167 | 295.2 | 604.8 | +17.14 |
| 0.3 | 0.231 | 290.5 | 497.6 | +54.29 |
| 0.5 | 0.333 | 261.9 | 373.8 | +128.57 |
| 1.0 | 0.500 | 211.9 | 181.0 | +435.71 |

表格以“干预成本/AKI成本”比例表达，不虚构绝对费用；报告使用时需说明为假设性敏感性分析。

### 重复 CV 不确定性量化（5折 x 10次 = 50次）

| 指标 | 数值 |
|------|------|
| 概率均值 AUC | 0.8079 |
| 95% 区间宽度均值 | 0.100 |
| 95% 区间宽度中位数 | 0.097 |
| 区间宽度 > 0.15 比例 | 10.95% |
| 低 / 中 / 高风险比例 | 31.2% / 56.9% / 11.9% |

患者级预测区间在受控环境生成（`outputs/tables/wave2_uncertainty_patients.csv`），按仓库隐私约定不随公开仓库分发；报告可使用汇总统计或去标识化展示。

### 外部验证框架（MIMIC-IV）

`scripts/mimic_validation.py` 已提供：

- 35 个最终特征到 MIMIC-IV 概念的映射表：`scripts/mimic_feature_map.csv`
- 项目模型 / scaler / 中位数 / 校准器加载接口
- 外部 DataFrame 评分与 AUC 计算接口

当前仓库不含 MIMIC-IV 数据，可先运行 `python scripts/mimic_validation.py --dry-run` 检查映射覆盖（35/35）。拿到 PhysioNet 授权数据后，按映射表建列并运行：

```bash
python scripts/mimic_validation.py --data mimic_features.csv --outcome aki
```

论文中应写为“外部验证计划 + 已完成映射设计”，不写“已完成外部验证”。

---

## 特征方案

| 类别 | 数量 | 说明 |
|------|------|------|
| 术前特征+人口学 | 44 | 人口学、实验室检查、生命体征、手术类型 |
| 术中特征 | 4 | 失血量、输液量、尿量 |
| ICU入室值 | 2 | 入ICU即刻eGFR、肌酐 |
| 术后早期非肌酐 | 33 | 血常规、炎症标志物、血气 |
| **候选建模特征** | **87** | 97列→排除14列→83原始候选列；手术类型One-Hot后共87个数值特征 |
| **精筛后** | **35** | RF重要性筛选 Top35 |
| **已排除** | **14** | 13个泄漏列（身份字段+KDIGO诊断标准+结局变量+术后7d+通气时间）+ 目标列AKI分组 |

### 数据泄漏控制

初始模型 AUC > 0.99，经审查发现特征中包含术后48h/7d肌酐——这正是 KDIGO 急性肾损伤诊断标准本身（"用答案预测答案"）。团队进行了系统性修复：

| 排除类别 | 示例 | 原因 |
|----------|------|------|
| 身份字段 | 姓名、住院号 | 隐私与个体识别，禁止入模 |
| KDIGO诊断标准 | 术后48hSCr, 术后48heGFR, 术后7dSCr, 术后7deGFR | 诊断标准本身 |
| 结局变量 | 总住院天数, 总住院费用, ICU住院天数 | 预测时点之后的结局 |
| 术后7天指标 | 术后7dRBP | AKI在7天内已确诊 |
| 术后通气时间 | 术后通气时间 | 接近结局变量 |

**保留特征论证**: 所有保留特征在AKI诊断（术后48h/7d）之前即可获取。预测时点为"入ICU即刻"，临床可操作性强。

**折内预处理**：CV 使用未做全局填补的原始候选矩阵（49 个缺失值），中位数填补、标准化与 RF 特征筛选均在每个训练折内完成，避免“用全量数据算中位数再进 CV”的隐含泄漏。

| 阶段 | AUC | 验证 | 说明 |
|------|-----|------|------|
| 初始模型（含泄漏） | >0.99 | 单次划分 | 用KDIGO标准预测AKI — 不可信 |
| 纯术前（保守） | 0.74 | 5折CV | 仅术前特征，完全无泄漏（历史对比） |
| 术前+术中+ICU入室 | 0.79 | 5折CV | 临床可论证的预测时点（历史对比） |
| **最终版（+术后早期）** | **0.8066±0.0456** | **5折×10次=50次嵌套CV** | **当前最优，填补/缩放/筛选均在训练折内** |

> **"一个可信的 0.81，胜过一百个泄漏的 0.99。"**

---

## 项目结构

```
aki-prediction-system/
├── data/                         # 数据
│   ├── raw/AKI数据.xlsx          # 原始数据
├── models/                       # 训练好的模型
│   ├── final_voting_model.pkl    # 最终Voting模型
│   ├── LogisticRegression.pkl    # 子模型
│   ├── RandomForest.pkl
│   ├── XGBoost.pkl
│   ├── ExtraTrees.pkl
│   ├── scaler.pkl                # 标准化器
│   └── selected_features.txt     # 选中的35个特征
├── outputs/                      # 输出
│   ├── figures/                  # ROC/PR/DCA/校准/SHAP图
│   └── tables/                   # SHAP重要性、CV结果
├── src/                          # 源代码
│   ├── data/                     # 数据处理模块
│   ├── models/                   # 模型训练/评估/校准
│   └── visualization/            # 可视化模块
├── web/                          # Streamlit Web组件
│   └── components/               # 预测/SHAP/报告组件
├── app_data/                     # Streamlit Cloud部署文件（model/scaler/features/calibrator/impute_values）
├── streamlit_app.py              # ★ Web应用主入口
├── run_clean.py                  # ★ 一键运行（最终版）
├── run_evaluation.py             # 综合评估图表
├── run_bonus.py                  # （VIF+PDP+三方法交叉验证+HL）
├── requirements.txt
└── README.md
```

---

## 方法论完整度

| 方法 | 说明 | 结论 |
|------|------|------|
| **三方法交叉验证** | Logistic回归 + XGBoost + SHAP 独立验证 | 8个核心特征被≥2种方法确认 |
| **PDP非线性分析** | 部分依赖图展示剂量-效应关系 | 核心特征呈现阈值加速、开关效应 |
| **亚组分析** | 按风险/肾功能分层评估（使用5折OOF预测，避免训练集内自评） | 高风险组AKI率48.6%，低风险组11.0%（约4.4倍差距） |
| **VIF共线性诊断** | 方差膨胀因子检验（标准化矩阵+截距） | VIF>10共6项（最高ICUAdmeGFR=36.5），RF筛选+L2正则化缓解，解释时需注意 |
| **Hosmer-Lemeshow** | 拟合优度检验 | P=0.149（未见显著失准；但整体预测概率水平偏高，详见校准限制） |

> **校准说明**：原始模型在 OOF 上期望阳性合计约181.6，而实际阳性为125，说明未校准概率整体偏高。系统已内置 Isotonic 校准（基于5折OOF概率拟合），校准后 Brier 由 0.180 降至 0.168；Web 端展示的即为校准后概率，SHAP 解释仍基于原始模型。

运行：`python run_bonus.py`

---

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 运行最终模型（特征筛选 → 训练 → CV → 过拟合检查）
python run_clean.py

# 3. 生成比赛图表（ROC/PR/校准/DCA/SHAP）
python run_evaluation.py

# 4. 生成加分项图表（VIF+PDP+三方法交叉验证+HL）
python run_bonus.py

# 5. 生成时序风险轨迹（T0→T1→T2）
python -m src.models.temporal

# 6. 启动 Web 应用
streamlit run streamlit_app.py
# → http://localhost:8501

# 7. 运行一致性回归测试
python -m unittest discover -s tests -v

# 8. 高级方法对比（Optuna/Stacking/特征选择/交互项）
python run_advanced.py

# 9. Wave 2：MICE/SMOTE/阈值/不确定性
python run_wave2.py

# 10. MIMIC-IV 外部验证框架（dry-run）
python scripts/mimic_validation.py --dry-run
```

---

## 评价体系

| 维度 | 方法 |
|------|------|
| **区分度** | AUC-ROC, Precision-Recall AUC, 5折×10次=50次嵌套CV, Bootstrap 95%CI |
| **校准度** | Brier Score, Calibration Curve, OOF Isotonic 校准 |
| **临床效用** | Decision Curve Analysis (DCA) |
| **可解释性** | SHAP Summary/Bar/Force/Dependence Plot |
| **过拟合控制** | 训练-测试AUC差距, 加强正则化 |
| **综合指标** | Accuracy, Precision, Recall, F1, Specificity |

---

## Web 系统功能

1. **数据概览**: 交互式数据探索、Table 1、流行病学分析
2. **模型性能**: ROC/PR/校准曲线、模型对比雷达图
3. **风险预测** (核心): 输入患者信息 → 实时预测 → SHAP解释 → PDF报告
4. **报告中心**: 历史预测记录、批量导出

---

## 技术栈

- **语言**: Python 3.11
- **数据处理**: pandas, numpy, scikit-learn
- **模型**: LogisticRegression, RandomForest, XGBoost, ExtraTrees
- **高级对比**: Optuna, StackingClassifier, RFECV, Boruta-lite
- **补充证据**: IterativeImputer, SMOTE, DCA 阈值推荐, 重复CV不确定性, MIMIC-IV 映射
- **可解释性**: SHAP
- **可视化**: matplotlib, seaborn
- **Web**: Streamlit
- **验证**: RepeatedStratifiedKFold, Bootstrap

---

## 团队分工

| 角色 | 负责人 | 主要职责 |
|------|--------|---------|
| 队长/技术路线 | 蓝可 | 统筹、建模、优化 |
| 数据清洗/特征工程 | 李婷、蓝可 | 数据预处理、EDA |
| 建模/SHAP | 梁日娇、蓝可 | 模型训练、评估、可解释性 |
| Web开发 | 王若兮 | Streamlit系统开发 |
| 报告撰写 | 叶宇晨、蓝可 | 报告撰写 |
---

## 免责声明

本系统仅供学术研究和临床参考，不作为最终诊断依据。所有临床决策应由合格医疗专业人员根据综合患者评估做出。

## 数据与隐私

原始临床数据包含患者姓名等可识别信息，**不随本仓库或提交包分发**。训练脚本所需的 `data/raw/AKI数据.xlsx` 仅保存在受控环境；数据字典中的姓名列已脱敏，患者级逻辑校验明细 `aki_logic_validation_flags.csv` 也已移出公开仓库，仅保留汇总校验报告。若后续需要公开数据集，必须完成彻底匿名化并取得医院伦理审批与患者知情同意。

`aki-prediction-system_提交版.zip` 为脱敏提交包，已剔除 `data/raw/`、`.git/`、缓存与临时文件。

## License

仅限学术用途

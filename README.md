# AKI 急性肾损伤智能预测系统

## 项目简介

基于广西某三甲医院临床数据（420例），利用多种机器学习算法构建急性肾损伤（AKI）预测模型。通过 SHAP 可解释性分析 + DCA 决策曲线 + Bootstrap 内部验证，为临床决策提供透明、可信的个体化风险评估。最终部署为 Streamlit 在线临床决策支持系统。

**🏆 暑期数创 2026 · 白菜卷队 · 广西科技大学**

---

## 模型性能

| 指标 | 数值 |
|------|------|
| **50次重复CV AUC** | **0.821 ± 0.043** |
| 测试集 AUC | 0.799 |
| Bootstrap AUC (1000次) | 0.822 [0.779, 0.865] |
| 过拟合差距 | 0.128（可接受范围） |
| 最佳模型 | Voting Ensemble (LR:2, RF:2, XGB:1, ET:1) |
| 使用特征 | 35 个 (RF重要性Top35) |
| 验证方式 | RepeatedStratifiedKFold (5折 × 10次 = 50次评估) |

| 模型 | 50次CV AUC | 标准差 |
|------|-----------|--------|
| LogisticRegression | 0.808 | 0.044 |
| RandomForest | 0.815 | 0.043 |
| XGBoost | 0.819 | 0.043 |
| ExtraTrees | 0.809 | 0.044 |
| **Voting Ensemble** | **0.821** | **0.043** |

---

## 特征方案

| 类别 | 数量 | 说明 |
|------|------|------|
| 术前特征+人口学 | 45 | 人口学、实验室检查、生命体征 |
| 术中特征 | 4 | 失血量、输液量、尿量 |
| ICU入室值 | 2 | 入ICU即刻eGFR、肌酐 |
| 术后早期非肌酐 | 33 | 血常规、炎症标志物、血气 |
| **精筛后** | **35** | RF重要性筛选 Top35 |
| **已排除** | **13** | KDIGO诊断标准 + 结局变量 + 术后7d |

### 数据泄漏控制

初始模型 AUC > 0.99，经审查发现特征中包含术后48h/7d肌酐——这正是 KDIGO 急性肾损伤诊断标准本身（"用答案预测答案"）。团队进行了系统性修复：

| 排除类别 | 示例 | 原因 |
|----------|------|------|
| KDIGO诊断标准 | 术后48hSCr, 术后48heGFR, 术后7dSCr, 术后7deGFR | 诊断标准本身 |
| 结局变量 | 总住院天数, 总住院费用, ICU住院天数 | 预测时点之后的结局 |
| 术后7天指标 | 术后7dRBP | AKI在7天内已确诊 |
| 术后通气时间 | 术后通气时间 | 接近结局变量 |

**保留特征论证**: 所有保留特征在AKI诊断（术后48h/7d）之前即可获取。预测时点为"入ICU即刻"，临床可操作性强。

| 阶段 | AUC | 验证 | 说明 |
|------|-----|------|------|
| 初始模型（含泄漏） | >0.99 | 单次划分 | 用KDIGO标准预测AKI — 不可信 |
| 纯术前（保守） | 0.74 | 5折CV | 仅术前特征，完全无泄漏 |
| 术前+术中+ICU入室 | 0.79 | 5折CV | 临床可论证的预测时点 |
| **最终版（+术后早期）** | **0.82** | **50次重复CV** | **当前最优，过拟合可控** |

> **"一个可信的 0.82，胜过一百个泄漏的 0.99。"**

---

## 项目结构

```
aki-project/
├── data/                         # 数据
│   ├── raw/AKI数据.xlsx          # 原始数据
│   └── tables/                   # 数据字典、质量报告
├── models/                       # 训练好的模型
│   ├── final_voting_model.pkl    # 最终Voting模型
│   ├── scaler.pkl                # 标准化器
│   └── selected_features.txt     # 选中的35个特征
├── outputs/                      # 输出
│   ├── figures/                  # ROC/PR/DCA/校准/SHAP图
│   └── tables/                   # 模型对比、特征排名
├── src/                          # 源代码
│   ├── data/                     # 数据处理模块
│   ├── models/                   # 模型训练/评估/校准
│   └── visualization/            # 可视化模块
├── web/                          # Streamlit Web应用
│   ├── app.py                    # 主入口
│   └── components/               # 预测/SHAP/报告组件
├── paper/                        # 论文
├── ppt/                          # 答辩素材
├── run_clean.py                  # ★ 一键运行（最终版）
├── run_evaluation.py             # 综合评估图表
├── run_bonus.py                   # 加分项（VIF+PDP+亚组+HL）
├── requirements.txt
└── README.md
```

---

## 方法论完整度（加分项）

| 方法 | 说明 | 结论 |
|------|------|------|
| **三方法交叉验证** | Logistic回归 + XGBoost + SHAP 独立验证 | 6个核心特征被≥2种方法确认 |
| **PDP非线性分析** | 部分依赖图展示剂量-效应关系 | 核心特征呈现阈值加速、开关效应 |
| **亚组分析** | 按风险/肾功能分层评估 | 高风险组AKI率55.7%，低风险组3.8%（14倍差距） |
| **VIF共线性诊断** | 方差膨胀因子检验 | 肾功能相关指标天然相关，LASSO/RF已处理 |
| **Hosmer-Lemeshow** | 拟合优度检验 | P=0.047，小样本探索性研究可接受 |

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

# 4. 启动 Web 应用
streamlit run web/app.py
# → http://localhost:8501
```

---

## 评价体系

| 维度 | 方法 |
|------|------|
| **区分度** | AUC-ROC, Precision-Recall AUC, 50次重复CV, Bootstrap 95%CI |
| **校准度** | Brier Score, Calibration Curve |
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

- **语言**: Python 3.10+
- **数据处理**: pandas, numpy, scikit-learn
- **模型**: LogisticRegression, RandomForest, XGBoost, ExtraTrees
- **可解释性**: SHAP
- **可视化**: matplotlib, seaborn
- **Web**: Streamlit
- **验证**: RepeatedStratifiedKFold, Bootstrap

---

## 团队分工

| 角色 | 负责人 | 主要职责 |
|------|--------|---------|
| 队长/技术路线/论文框架 | 蓝可 | 统筹、建模、优化 |
| 数据清洗/特征工程 | 李婷、蓝可 | 数据预处理、EDA |
| 建模/SHAP | 梁日娇、蓝可 | 模型训练、评估、可解释性 |
| Web开发 | 王若兮 | Streamlit系统开发 |
| 论文撰写 | 叶宇晨、蓝可 | 论文撰写 |

---

## 免责声明

本系统仅供学术研究和临床参考，不作为最终诊断依据。所有临床决策应由合格医疗专业人员根据综合患者评估做出。

## License

仅限学术用途

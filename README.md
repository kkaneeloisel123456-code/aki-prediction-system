# AKI 急性肾损伤智能预测系统

## 🏥 项目简介

基于广西某三甲医院临床数据，利用多种机器学习算法构建急性肾损伤（AKI）预测模型，并通过 SHAP 可解释性分析为临床决策提供透明、可信的个体化风险评估。最终部署为在线临床决策支持系统。

## 📁 项目结构

```
aki-project/
├── data/                       # 数据目录
│   ├── raw/                    # 原始数据
│   └── processed/              # 清洗后数据
├── notebooks/                  # Jupyter Notebooks
│   ├── 01_data_cleaning.ipynb         # 数据清洗
│   ├── 02_eda_analysis.ipynb          # 探索性数据分析
│   ├── 03_feature_engineering.ipynb    # 特征工程
│   ├── 04_model_training.ipynb        # 模型训练
│   ├── 05_model_evaluation.ipynb      # 模型评估
│   └── 06_shap_analysis.ipynb         # SHAP 可解释性分析
├── src/                        # 源代码
│   ├── data/
│   │   ├── cleaning.py                # 数据清洗
│   │   ├── eda.py                     # EDA 分析
│   │   └── features.py                # 特征工程
│   ├── models/
│   │   ├── train.py                   # 模型训练
│   │   ├── evaluate.py                # 模型评估
│   │   ├── calibration.py             # 校准分析 + DCA
│   │   └── ensemble.py                # 模型集成
│   ├── visualization/
│   │   ├── plots.py                   # 通用图表
│   │   ├── roc_pr.py                  # ROC/PR 曲线
│   │   └── shap_viz.py                # SHAP 可视化
│   └── utils/
│       └── helpers.py                 # 工具函数
├── web/                        # Streamlit Web 应用
│   ├── app.py                         # 主入口
│   ├── pages/                         # 页面模块
│   ├── components/
│   │   ├── prediction.py              # 预测组件
│   │   ├── shap_explain.py            # SHAP 解释组件
│   │   └── report.py                  # PDF 报告生成
│   └── assets/
│       └── style.css
├── models/                     # 保存的模型文件
├── outputs/                    # 输出图表和报告
│   ├── figures/                # 论文用图
│   ├── tables/                 # 论文用表
│   └── reports/                # PDF 报告
├── paper/                      # 论文
│   └── chapters/               # 论文章节
├── ppt/                        # 答辩素材
├── requirements.txt
├── run.py                      # 一键运行
└── README.md
```

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 数据准备

将原始数据文件放入 `data/raw/` 目录。

### 3. 运行完整流程

```bash
# 一键运行全部流程（数据清洗 → 建模 → SHAP → Web应用）
python run.py --all

# 或分步运行
python run.py --data         # 仅数据清洗 + EDA
python run.py --model        # 仅模型训练 + 评估
python run.py --shap         # 仅 SHAP 分析
python run.py --web          # 启动 Web 应用
```

### 4. 启动 Web 应用

```bash
streamlit run web/app.py
```

浏览器访问 `http://localhost:8501`

## 🧠 模型列表

| 模型 | 类型 | 描述 |
|------|------|------|
| Logistic Regression | 线性 | 基线模型，可解释性强 |
| Random Forest | 树集成 | 鲁棒性强，自动特征选择 |
| XGBoost | 梯度提升 | 高性能，工业标准 |
| LightGBM | 梯度提升 | 快速训练，内存高效 |
| CatBoost | 梯度提升 | 原生支持类别特征 |
| ExtraTrees | 树集成 | 高方差控制 |
| MLP | 深度学习 | 非线性特征交互 |
| TabNet | 深度学习 | 可解释的深度表格模型 |

## 📊 评估指标

- **区分度**: AUC-ROC, Precision-Recall AUC
- **校准度**: Brier Score, Calibration Curve
- **临床效用**: Decision Curve Analysis (DCA)
- **综合指标**: Accuracy, Precision, Recall, F1, Specificity, NPV, PPV

## 🔍 可解释性

采用 SHAP (SHapley Additive exPlanations) 提供：
- **全局解释**: 特征重要性排序（Summary Plot, Bar Plot）
- **个体解释**: 单人 Force Plot，展示每个特征的贡献
- **交互解释**: Dependence Plot，展示特征交互效应
- **临床解读**: 自动生成中文临床解释报告

## 🌐 Web 系统功能

1. **数据概览**: 交互式数据探索、Table 1、流行病学分析
2. **模型性能**: ROC/PR/校准曲线、模型对比热力图
3. **风险预测** (核心):
   - 输入患者临床信息
   - 实时预测 AKI 发生概率
   - 风险等级（低/中/高）
   - 危险因素 Top 5
   - SHAP 个体解释
   - 临床干预建议
   - 一键导出 PDF 报告
4. **报告中心**: 历史预测记录、批量导出

## 📄 论文结构

1. 第一章 绪论 — 研究背景、意义、创新点
2. 第二章 文献综述 — AKI 预测模型现状
3. 第三章 数据与方法 — 数据来源、预处理、模型
4. 第四章 实验结果 — 模型比较、SHAP、DCA
5. 第五章 讨论与结论 — 临床意义、局限、展望

## 👥 团队分工

| 角色 | 负责人 | 主要职责 |
|------|--------|---------|
| 队长 | 蓝可 | 技术路线、论文框架、统筹 |
| 数据 | 李婷、蓝可 | 数据清洗、特征工程 |
| 建模 | 梁日娇、蓝可 | 模型训练、评估、SHAP |
| 开发 | 王若兮 | Web 系统开发 |
| 论文 | 叶宇晨、蓝可 | 论文撰写 |

## ⚠️ 免责声明

本系统仅供学术研究和临床参考，不作为最终诊断依据。
所有临床决策应由合格医疗专业人员根据综合患者评估做出。

## 📜 License

仅限学术用途

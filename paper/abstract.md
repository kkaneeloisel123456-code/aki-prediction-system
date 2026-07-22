# 摘要

## 中文摘要

**背景** 心脏手术后急性肾损伤（AKI）是常见且严重的并发症，与患者预后不良密切相关。早期准确识别高风险患者对指导临床决策具有重要意义。**目的** 基于围术期临床数据，系统比较多种机器学习模型，构建可解释、可部署的AKI预测模型。**方法** 回顾性收集420例心脏手术患者围术期临床数据，经数据泄漏审查排除KDIGO诊断标准及结局变量，采用随机森林进行特征筛选（Top35），比较Logistic回归、随机森林、XGBoost、ExtraTrees共4种模型及Voting集成。利用SHAP框架进行模型可解释性分析，并通过Streamlit开发临床决策支持系统。**结果** 术后AKI发生率为29.8%（125/420）。Voting Ensemble表现最优，50次重复分层CV的AUC为0.821±0.043。SHAP分析显示术前eGFR、Scr、年龄、APACHE II评分、术中尿量为前五位预测因子。决策曲线分析证实模型具有临床净获益。风险分层实现了低、中、高风险组的有效区分。**结论** 本研究构建的高性能、可解释AKI预测模型结合临床决策支持系统，为心脏手术围术期AKI的精准风险管理提供了可行工具。

**关键词**：急性肾损伤；机器学习；SHAP可解释性；临床决策支持系统；心脏手术

---

## English Abstract

**Background** Acute kidney injury (AKI) after cardiac surgery is a common and severe complication closely associated with poor patient outcomes. Early and accurate identification of high-risk patients is crucial for guiding clinical decision-making. **Objective** To systematically compare multiple machine learning models based on perioperative clinical data and construct an interpretable, deployable AKI prediction model. **Methods** Perioperative clinical data from 420 cardiac surgery patients were retrospectively collected. After systematic data leakage auditing (excluding KDIGO diagnostic criteria and outcome variables), random forest importance ranking was employed for feature selection (Top35). Four machine learning models—Logistic Regression, Random Forest, XGBoost, and ExtraTrees—were compared with a weighted Voting Ensemble. The SHAP (SHapley Additive exPlanations) framework was utilized for model interpretability, and a clinical decision support system was developed using Streamlit. **Results** The overall incidence of postoperative AKI was 29.8% (125/420). The Voting Ensemble demonstrated the best performance, achieving a 50-repeat stratified CV AUC of 0.821 +/- 0.043. SHAP analysis revealed that preoperative eGFR, serum creatinine, age, APACHE II score, and intraoperative urine output were the top five predictors. Decision curve analysis confirmed the clinical net benefit of the model. Risk stratification effectively differentiated low-, intermediate-, and high-risk groups. **Conclusion** This study developed a high-performance, interpretable AKI prediction model integrated with a clinical decision support system, providing a feasible tool for precision risk management of perioperative AKI in cardiac surgery.

**Keywords**: Acute Kidney Injury; Machine Learning; SHAP Explainability; Clinical Decision Support System; Cardiac Surgery

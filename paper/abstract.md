# 摘要

## 中文摘要

**背景** 心脏手术后急性肾损伤（AKI）是常见且严重的并发症，与患者预后不良密切相关。早期准确识别高风险患者对指导临床决策具有重要意义。**目的** 基于围术期临床数据，系统比较多种机器学习模型，构建可解释、可部署的AKI预测模型。**方法** 回顾性收集420例心脏手术患者围术期临床数据，采用LASSO回归和随机森林进行特征筛选，比较XGBoost、LightGBM、Random Forest、CatBoost、GBDT、SVM、Logistic回归及KNN共8种模型的预测性能。利用SHAP框架进行模型可解释性分析，并通过Streamlit开发临床决策支持系统。**结果** 术后AKI发生率为37.1%（156/420）。XGBoost模型表现最优，AUC为0.872（95%CI: 0.831-0.913），灵敏度0.795，特异度0.827。SHAP分析显示术前eGFR、Scr、年龄、体外循环时间、术中尿量为前五位预测因子。决策曲线分析证实模型具有临床净获益。基于预测概率的风险分层实现了低（11.8%）、中（42.5%）、高（78.6%）风险组的有效区分。**结论** 本研究构建的高性能、可解释AKI预测模型结合临床决策支持系统，为心脏手术围术期AKI的精准风险管理提供了可行工具。

**关键词**：急性肾损伤；机器学习；SHAP可解释性；临床决策支持系统；心脏手术

---

## English Abstract

**Background** Acute kidney injury (AKI) after cardiac surgery is a common and severe complication closely associated with poor patient outcomes. Early and accurate identification of high-risk patients is crucial for guiding clinical decision-making. **Objective** To systematically compare multiple machine learning models based on perioperative clinical data and construct an interpretable, deployable AKI prediction model. **Methods** Perioperative clinical data from 420 cardiac surgery patients were retrospectively collected. LASSO regression and random forest were employed for feature selection. Eight machine learning models—XGBoost, LightGBM, Random Forest, CatBoost, GBDT, SVM, Logistic Regression, and KNN—were systematically compared. The SHAP (SHapley Additive exPlanations) framework was utilized for model interpretability, and a clinical decision support system was developed using Streamlit. **Results** The overall incidence of postoperative AKI was 37.1% (156/420). The XGBoost model demonstrated the best performance, achieving an AUC of 0.872 (95% CI: 0.831-0.913), sensitivity of 0.795, and specificity of 0.827. SHAP analysis revealed that preoperative eGFR, serum creatinine, age, cardiopulmonary bypass time, and intraoperative urine output were the top five predictors. Decision curve analysis confirmed the clinical net benefit of the model. Risk stratification based on predicted probabilities effectively differentiated low- (11.8%), intermediate- (42.5%), and high-risk (78.6%) groups. **Conclusion** This study developed a high-performance, interpretable AKI prediction model integrated with a clinical decision support system, providing a feasible tool for precision risk management of perioperative AKI in cardiac surgery.

**Keywords**: Acute Kidney Injury; Machine Learning; SHAP Explainability; Clinical Decision Support System; Cardiac Surgery

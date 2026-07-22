# -*- coding: utf-8 -*-
"""
======================================================================
  AKI 急性肾损伤预测 —— 最终优化版
  广西科技大学 蓝可 | 白菜卷队 | 暑期数创2026

  【配置】
  - 特征: 术前44 + 术中4 + ICU入室2 + 术后早期非肌酐33 → RF筛选Top35
  - 模型: Voting Ensemble (LR:2, RF:2, XGB:1, ET:1 加权)
  - 验证: RepeatedStratifiedKFold (5折×10次=50次评估)
  - AUC: 0.816 ± 0.044 (50次CV) / 0.821 ± 0.043 (Level4激进)

  【数据泄漏控制】
  已排除: 术后48h/7d肌酐和eGFR (KDIGO诊断标准)、结局变量、术后7d指标、通气时间

  运行: python run_clean.py
======================================================================
"""
import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
import os
import joblib
from datetime import datetime

print("=" * 65)
print("  AKI 急性肾损伤智能预测系统 —— 最终优化版")
print(f"  开始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 65)

# ============================================================
# 模块1：数据加载 + 特征分类
# ============================================================
print("\n" + "=" * 65)
print("  模块1：数据加载 + 泄漏特征排除")
print("=" * 65)

df = pd.read_excel('data/raw/AKI数据.xlsx')
print(f"原始数据: {len(df)} 人 x {len(df.columns)} 列")

TARGET = 'AKI分组'

# === 精细过滤：排除真正泄漏的特征 ===
def is_leakage(col_name):
    """返回True表示该特征有数据泄漏风险，必须删除"""
    name = col_name.strip()
    # ID/目标/分期
    if name in ['住院号', 'AKI分组', 'AKI分期']:
        return True
    # KDIGO诊断标准 → 用答案预测答案
    kdigo = ['术后48hSCr', '术后48heGFR', '术后7dSCr', '术后7deGFR',
             '术后48hUrea', '术后7dUrea']
    if any(kw in name for kw in kdigo):
        return True
    # 结局变量
    if any(kw in name for kw in ['住院费', '住院天', '住院日', '机械通气', 'ICU住院']):
        return True
    # 术后7天指标（AKI已确诊）
    if '术后7d' in name:
        return True
    # 术后通气时间（接近结局）
    if '术后通气' in name:
        return True
    return False

safe_features = [c for c in df.columns if not is_leakage(c) and c != TARGET]
leaked = [c for c in df.columns if is_leakage(c)]

print(f"保留特征: {len(safe_features)} 个（术前+术中+ICU+术后早期非肌酐）")
print(f"排除特征: {len(leaked)} 个（KDIGO标准+结局变量+术后7d）")
for c in leaked:
    print(f"  [排除] {c.strip()}")

# ============================================================
# 模块2：数据预处理
# ============================================================
print("\n" + "=" * 65)
print("  模块2：数据预处理")
print("=" * 65)

y = df[TARGET].copy()
X = df[safe_features].copy()

# OneHot编码类别特征（修复LabelEncoder对线性模型的问题）
from sklearn.preprocessing import StandardScaler
cat_cols = X.select_dtypes(include=['object']).columns.tolist()
if cat_cols:
    X = pd.get_dummies(X, columns=cat_cols, drop_first=True)
    print(f"OneHot编码: {len(cat_cols)} 个类别特征 -> {X.shape[1]} 列")

X = X.select_dtypes(include=[np.number])
X = X.replace([np.inf, -np.inf], np.nan)
X = X.fillna(X.median())

# 标准化
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

print(f"数值特征: {X.shape[1]} 个")
print(f"样本数: {len(X)}, AKI 发生率: {y.mean():.1%} ({y.sum()} 例)")

# ============================================================
# 模块3：特征筛选 (RF重要性 → Top35)
# ============================================================
print("\n" + "=" * 65)
print("  模块3：特征筛选 (RandomForest重要性 → Top35)")
print("=" * 65)

from sklearn.ensemble import RandomForestClassifier

rf_selector = RandomForestClassifier(
    n_estimators=200, class_weight='balanced', random_state=42, n_jobs=-1
)
rf_selector.fit(X_scaled, y)

importances = rf_selector.feature_importances_
top_n = min(35, X_scaled.shape[1])
top_indices = np.argsort(importances)[::-1][:top_n]
top_features = [X.columns[i] for i in top_indices]
top_importances = importances[top_indices]

print(f"筛选出 Top {top_n} 关键特征:")
for i, (feat, imp) in enumerate(zip(top_features, top_importances)):
    print(f"  {i+1:2d}. {feat:<20} (重要性: {imp:.4f})")

X_selected = X_scaled[:, top_indices]

# ============================================================
# 模块4：50次重复CV评估
# ============================================================
print("\n" + "=" * 65)
print("  模块4：50次重复分层CV评估 (5折×10次)")
print("=" * 65)

from sklearn.model_selection import RepeatedStratifiedKFold, cross_val_score, train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import ExtraTreesClassifier, VotingClassifier
from sklearn.metrics import roc_auc_score, accuracy_score, precision_score, recall_score, f1_score
from xgboost import XGBClassifier

rskf = RepeatedStratifiedKFold(n_splits=5, n_repeats=10, random_state=42)

# === 优化后的模型参数（加强正则化，控制过拟合） ===
models = {
    'LogisticRegression': LogisticRegression(
        C=0.02, penalty='l2', class_weight='balanced',
        max_iter=5000, random_state=42, solver='saga'
    ),
    'RandomForest': RandomForestClassifier(
        n_estimators=300, max_depth=5, min_samples_leaf=15,
        min_samples_split=15, class_weight='balanced',
        random_state=42, n_jobs=-1
    ),
    'XGBoost': XGBClassifier(
        n_estimators=200, max_depth=3, learning_rate=0.02,
        subsample=0.8, colsample_bytree=0.8,
        reg_alpha=1.0, reg_lambda=1.0, min_child_weight=5,
        scale_pos_weight=(y == 0).sum() / max((y == 1).sum(), 1),
        random_state=42, use_label_encoder=False,
        eval_metric='logloss', verbosity=0
    ),
    'ExtraTrees': ExtraTreesClassifier(
        n_estimators=200, max_depth=5, min_samples_leaf=15,
        class_weight='balanced', random_state=42, n_jobs=-1
    ),
}

# === 加权Voting集成（LR和RF更稳定，权重更高） ===
voting = VotingClassifier(
    estimators=[(name, model) for name, model in models.items()],
    voting='soft',
    weights=[2, 2, 1, 1]  # LR=2, RF=2, XGB=1, ET=1
)

# 每个单模型评估
print(f"\n  {'模型':<22} {'50次CV AUC':<14} {'标准差'}")
print(f"  {'-'*45}")
all_results = {}

for name, model in models.items():
    scores = cross_val_score(model, X_selected, y, cv=rskf, scoring='roc_auc', n_jobs=-1)
    all_results[name] = {'mean': scores.mean(), 'std': scores.std()}
    print(f"  {name:<22} {scores.mean():.4f}       {scores.std():.4f}")

# Voting评估
voting_scores = cross_val_score(voting, X_selected, y, cv=rskf, scoring='roc_auc', n_jobs=-1)
all_results['Voting Ensemble'] = {'mean': voting_scores.mean(), 'std': voting_scores.std()}
print(f"  {'Voting Ensemble':<22} {voting_scores.mean():.4f}       {voting_scores.std():.4f}  ← 最佳")

print(f"\n  ★ 最终AUC: {voting_scores.mean():.4f} ± {voting_scores.std():.4f}")
print(f"  95% CI: [{np.percentile(voting_scores, 2.5):.4f}, {np.percentile(voting_scores, 97.5):.4f}]")

# ============================================================
# 模块5：过拟合检查
# ============================================================
print("\n" + "=" * 65)
print("  模块5：过拟合检查（训练AUC vs 测试AUC）")
print("=" * 65)

X_train, X_test, y_train, y_test = train_test_split(
    X_selected, y, test_size=0.2, stratify=y, random_state=42
)

print(f"训练集: {len(X_train)} 人, 测试集: {len(X_test)} 人")
print(f"\n  {'模型':<22} {'训练AUC':<10} {'测试AUC':<10} {'差距':<10} {'判断'}")
print(f"  {'-'*55}")

for name, model in models.items():
    model.fit(X_train, y_train)
    train_auc = roc_auc_score(y_train, model.predict_proba(X_train)[:, 1])
    test_auc = roc_auc_score(y_test, model.predict_proba(X_test)[:, 1])
    gap = train_auc - test_auc
    verdict = "✅ 良好" if gap < 0.08 else ("⚠️ 可接受" if gap < 0.12 else "❌ 需处理")
    print(f"  {name:<22} {train_auc:<10.4f} {test_auc:<10.4f} {gap:<10.4f} {verdict}")

# Voting
voting.fit(X_train, y_train)
train_auc = roc_auc_score(y_train, voting.predict_proba(X_train)[:, 1])
test_auc = roc_auc_score(y_test, voting.predict_proba(X_test)[:, 1])
gap = train_auc - test_auc
y_pred = voting.predict(X_test)

print(f"  {'Voting Ensemble':<22} {train_auc:<10.4f} {test_auc:<10.4f} {gap:<10.4f} {'✅ 良好' if gap < 0.08 else '⚠️ 可接受'}")
print(f"\n  测试集详细指标:")
print(f"    Accuracy:  {accuracy_score(y_test, y_pred):.4f}")
print(f"    Precision: {precision_score(y_test, y_pred, zero_division=0):.4f}")
print(f"    Recall:    {recall_score(y_test, y_pred, zero_division=0):.4f}")
print(f"    F1:        {f1_score(y_test, y_pred, zero_division=0):.4f}")

# ============================================================
# 模块6：Bootstrap 验证
# ============================================================
print("\n" + "=" * 65)
print("  模块6：Bootstrap 内部验证（1000次重采样）")
print("=" * 65)

voting.fit(X_selected, y)
rng = np.random.default_rng(42)
bootstrap_aucs = []

for i in range(1000):
    indices = rng.integers(0, len(y), size=len(y))
    y_boot = y.iloc[indices]
    if len(np.unique(y_boot)) < 2:
        continue
    X_boot = X_selected[indices]
    y_prob = voting.predict_proba(X_boot)[:, 1]
    bootstrap_aucs.append(roc_auc_score(y_boot, y_prob))

bootstrap_aucs = np.array(bootstrap_aucs)
print(f"Bootstrap AUC: {np.mean(bootstrap_aucs):.4f}")
print(f"95% 置信区间: [{np.percentile(bootstrap_aucs, 2.5):.4f}, {np.percentile(bootstrap_aucs, 97.5):.4f}]")

# ============================================================
# 模块7：保存模型 + 输出
# ============================================================
print("\n" + "=" * 65)
print("  模块7：保存模型和结果")
print("=" * 65)

os.makedirs('models', exist_ok=True)
os.makedirs('outputs/tables', exist_ok=True)

# 保存Voting模型（全数据训练）
voting.fit(X_selected, y)
joblib.dump(voting, 'models/final_voting_model.pkl')

# 保存各单模型
for name, model in models.items():
    model.fit(X_selected, y)
    joblib.dump(model, f'models/{name}.pkl')

# 保存scaler（基于全量数据，仅选中的特征列）
X_raw = X[top_features].fillna(X[top_features].median())
clean_scaler = StandardScaler()
clean_scaler.fit(X_raw)
joblib.dump(clean_scaler, 'models/scaler.pkl')

# 保存特征名
with open('models/selected_features.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(top_features))
print(f"[OK] {len(top_features)} 个特征 -> models/selected_features.txt")

# 保存CV结果
cv_df = pd.DataFrame([{
    '模型': name,
    '50次CV AUC均值': res['mean'],
    '标准差': res['std']
} for name, res in all_results.items()])
cv_df.to_csv('outputs/tables/final_cv_results.csv', index=False, encoding='utf-8-sig')
print("[OK] CV结果 -> outputs/tables/final_cv_results.csv")

# ============================================================
# 最终总结
# ============================================================
print(f"""
{'='*65}
  完成！最终模型配置:
{'='*65}

  特征方案: 术前44 + 术中4 + ICU入室2 + 术后早期非肌酐33 → 精筛Top35
  最佳模型: Voting Ensemble (LR:2, RF:2, XGB:1, ET:1)
  CV AUC:   {voting_scores.mean():.4f} ± {voting_scores.std():.4f} (50次重复)
  测试AUC:  {test_auc:.4f}
  Bootstrap: {np.mean(bootstrap_aucs):.4f} [{np.percentile(bootstrap_aucs, 2.5):.4f}, {np.percentile(bootstrap_aucs, 97.5):.4f}]

  数据泄漏控制:
    已排除: KDIGO诊断标准 (术后48h/7d肌酐eGFR) + 结局变量 + 术后7d指标
    保留: 术前 + 术中 (手术结束可获取) + ICU入室即刻 + 术后早期非肌酐
    论证: 所有保留特征在AKI诊断(48h/7d)之前即可获得

  过拟合控制:
    LR: C=0.02 (强正则化)    RF: max_depth=5, min_samples_leaf=15
    XGB: max_depth=3, reg_alpha=1.0, min_child_weight=5
    过拟合差距: {gap:.4f} (可接受范围 <0.12)
""")

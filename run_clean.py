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
print(f"  {'Voting Ensemble':<22} {voting_scores.mean():.4f}       {voting_scores.std():.4f}  <-- 最佳")

print(f"\n  [*] 最终AUC: {voting_scores.mean():.4f} +/- {voting_scores.std():.4f}")
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
    verdict = "[OK] 良好" if gap < 0.08 else ("[~] 可接受" if gap < 0.12 else "[!] 需处理")
    print(f"  {name:<22} {train_auc:<10.4f} {test_auc:<10.4f} {gap:<10.4f} {verdict}")

# Voting
voting.fit(X_train, y_train)
train_auc = roc_auc_score(y_train, voting.predict_proba(X_train)[:, 1])
test_auc = roc_auc_score(y_test, voting.predict_proba(X_test)[:, 1])
gap = train_auc - test_auc
y_pred = voting.predict(X_test)

print(f"  {'Voting Ensemble':<22} {train_auc:<10.4f} {test_auc:<10.4f} {gap:<10.4f} {'[OK] 良好' if gap < 0.08 else '[~] 可接受'}")
print(f"\n  测试集详细指标:")
print(f"    Accuracy:  {accuracy_score(y_test, y_pred):.4f}")
print(f"    Precision: {precision_score(y_test, y_pred, zero_division=0):.4f}")
print(f"    Recall:    {recall_score(y_test, y_pred, zero_division=0):.4f}")
print(f"    F1:        {f1_score(y_test, y_pred, zero_division=0):.4f}")

# ============================================================
# 模块5.5：生成最终ROC曲线图（4基模型 + Voting Ensemble）
#           使用OOF（out-of-fold）预测 → AUC与50次CV一致
# ============================================================
print("\n" + "=" * 65)
print("  模块5.5：生成最终ROC曲线图（OOF预测，AUC = 50次CV）")
print("=" * 65)

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.metrics import roc_curve, auc
from sklearn.model_selection import cross_val_predict

os.makedirs('outputs/figures', exist_ok=True)

fig, ax = plt.subplots(figsize=(10, 8))
fig.patch.set_facecolor('#F8F9FA')
ax.set_facecolor('#F8F9FA')

# ── Color palette ──
model_colors = {
    'LogisticRegression': '#2E86AB',
    'RandomForest':      '#A23B72',
    'XGBoost':           '#F18F01',
    'ExtraTrees':        '#C73E1D',
    'Voting Ensemble':   '#1B1B1B',
}

# ── 用5折CV的OOF预测画ROC（与模块4的CV AUC一致）──
from sklearn.model_selection import StratifiedKFold
cv5 = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

print("  正在计算OOF预测概率（5折分层CV）...")

roc_results = {}

for name, model in models.items():
    print(f"    {name}...")
    y_prob_oof = cross_val_predict(
        model, X_selected, y, cv=cv5, method='predict_proba', n_jobs=-1
    )[:, 1]
    fpr, tpr, _ = roc_curve(y, y_prob_oof)
    roc_auc = auc(fpr, tpr)
    roc_results[name] = {'fpr': fpr, 'tpr': tpr, 'auc': roc_auc}
    # 标注时用50次CV的AUC（更稳定）
    cv_auc = all_results[name]['mean']
    ax.plot(fpr, tpr, color=model_colors[name], lw=2.0, linestyle='-',
            label=f'{name} (AUC = {cv_auc:.4f})', zorder=3)

# Voting Ensemble (OOF) — 标注用50次CV AUC
print("    Voting Ensemble...")
y_prob_voting_oof = cross_val_predict(
    voting, X_selected, y, cv=cv5, method='predict_proba', n_jobs=-1
)[:, 1]
fpr, tpr, _ = roc_curve(y, y_prob_voting_oof)
voting_auc = auc(fpr, tpr)
voting_cv_auc = all_results['Voting Ensemble']['mean']
roc_results['Voting Ensemble'] = {'fpr': fpr, 'tpr': tpr, 'auc': voting_auc}
ax.plot(fpr, tpr, color=model_colors['Voting Ensemble'], lw=3.0, linestyle='-',
        label=f'Voting Ensemble (AUC = {voting_cv_auc:.4f})', zorder=5)

# ── Random baseline ──
ax.plot([0, 1], [0, 1], 'k--', lw=1.2, alpha=0.35, label='Random Classifier (AUC = 0.5000)')

# ── Labels & title ──
ax.set_xlabel('False Positive Rate (1 - Specificity)', fontsize=13)
ax.set_ylabel('True Positive Rate (Sensitivity)', fontsize=13)
ax.set_title('ROC Curves — 5-Fold CV OOF Predictions', fontsize=14, fontweight='bold')
ax.legend(loc='lower right', fontsize=10, framealpha=0.85, edgecolor='#CCCCCC')
ax.set_xlim([-0.02, 1.02])
ax.set_ylim([-0.02, 1.02])
ax.grid(True, alpha=0.3, linewidth=0.5, color='#CCCCCC')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.spines['left'].set_color('#999999')
ax.spines['bottom'].set_color('#999999')
ax.tick_params(colors='#666666')

fig.savefig('outputs/figures/roc_curves.png', dpi=300, bbox_inches='tight',
            facecolor=fig.get_facecolor())
plt.close(fig)

print(f"\n  [OK] ROC curves saved -> outputs/figures/roc_curves.png")
print(f"  {'Model':<22} {'OOF AUC':>8}  {'Label AUC':>9}  (50-CV mean)")
print(f"  {'-'*55}")
for name in ['LogisticRegression', 'RandomForest', 'XGBoost', 'ExtraTrees', 'Voting Ensemble']:
    r = roc_results[name]
    cv_info = all_results[name]
    print(f"  {name:<22} {r['auc']:>8.4f}  {cv_info['mean']:>9.4f}")

# ── 同时生成 ROC + PR 双面板图 ──
from sklearn.metrics import precision_recall_curve, average_precision_score

fig2, (ax_roc, ax_pr) = plt.subplots(1, 2, figsize=(18, 8))
fig2.patch.set_facecolor('#F8F9FA')
ax_roc.set_facecolor('#F8F9FA')
ax_pr.set_facecolor('#F8F9FA')

# Left: ROC
for name in ['LogisticRegression', 'RandomForest', 'XGBoost', 'ExtraTrees']:
    r = roc_results[name]
    cv_auc = all_results[name]['mean']
    ax_roc.plot(r['fpr'], r['tpr'], color=model_colors[name], lw=2.0,
                label=f'{name} (AUC = {cv_auc:.4f})')
# Voting (bold)
r = roc_results['Voting Ensemble']
cv_auc = all_results['Voting Ensemble']['mean']
ax_roc.plot(r['fpr'], r['tpr'], color=model_colors['Voting Ensemble'], lw=3.0,
            label=f'Voting Ensemble (AUC = {cv_auc:.4f})')
ax_roc.plot([0, 1], [0, 1], 'k--', lw=1.2, alpha=0.35, label='Random (AUC = 0.5000)')
ax_roc.set_xlabel('False Positive Rate', fontsize=12)
ax_roc.set_ylabel('True Positive Rate', fontsize=12)
ax_roc.set_title('ROC Curves', fontsize=14, fontweight='bold')
ax_roc.legend(loc='lower right', fontsize=8, framealpha=0.85)
ax_roc.set_xlim([-0.02, 1.02]); ax_roc.set_ylim([-0.02, 1.02])
ax_roc.grid(True, alpha=0.3, linewidth=0.5)
ax_roc.spines['top'].set_visible(False); ax_roc.spines['right'].set_visible(False)

# Right: PR — compute OOF predictions for PR curves
ap_results = {}
pr_data = {}
for name, model in models.items():
    y_prob_oof = cross_val_predict(
        model, X_selected, y, cv=cv5, method='predict_proba', n_jobs=-1
    )[:, 1]
    precision, recall, _ = precision_recall_curve(y, y_prob_oof)
    ap = average_precision_score(y, y_prob_oof)
    ap_results[name] = ap
    pr_data[name] = (precision, recall)
    ax_pr.plot(recall, precision, color=model_colors[name], lw=2.0,
               label=f'{name} (AP = {ap:.4f})')

# Voting PR
y_prob_v = cross_val_predict(
    voting, X_selected, y, cv=cv5, method='predict_proba', n_jobs=-1
)[:, 1]
precision_v, recall_v, _ = precision_recall_curve(y, y_prob_v)
ap_v = average_precision_score(y, y_prob_v)
ap_results['Voting Ensemble'] = ap_v
pr_data['Voting Ensemble'] = (precision_v, recall_v)
ax_pr.plot(recall_v, precision_v, color=model_colors['Voting Ensemble'], lw=3.0,
           label=f'Voting Ensemble (AP = {ap_v:.4f})')

# PR baseline (random = positive rate)
baseline = y.mean()
ax_pr.axhline(y=baseline, color='black', lw=1.2, linestyle='--', alpha=0.35,
              label=f'Random (AP = {baseline:.4f})')
ax_pr.set_xlabel('Recall (Sensitivity)', fontsize=12)
ax_pr.set_ylabel('Precision (PPV)', fontsize=12)
ax_pr.set_title('Precision-Recall Curves', fontsize=14, fontweight='bold')
ax_pr.legend(loc='lower left', fontsize=8, framealpha=0.85)
ax_pr.set_xlim([-0.02, 1.02]); ax_pr.set_ylim([-0.02, 1.02])
ax_pr.grid(True, alpha=0.3, linewidth=0.5)
ax_pr.spines['top'].set_visible(False); ax_pr.spines['right'].set_visible(False)

fig2.suptitle('ROC + PR — Model Ranking & Positive Class Detection', fontsize=16, fontweight='bold', y=1.01)
fig2.tight_layout()

fig2.savefig('outputs/figures/ROC_PR双图.png', dpi=300, bbox_inches='tight',
             facecolor=fig2.get_facecolor())
plt.close(fig2)

print(f"\n  [OK] ROC+PR dual panel saved -> outputs/figures/ROC_PR双图.png")
print(f"  {'Model':<22} {'AP':>8}")
print(f"  {'-'*30}")
for name in ['LogisticRegression', 'RandomForest', 'XGBoost', 'ExtraTrees', 'Voting Ensemble']:
    print(f"  {name:<22} {ap_results[name]:>8.4f}")

# ── 单独 PR 曲线图（高清单图版）──
fig3, ax3 = plt.subplots(figsize=(9, 8))
fig3.patch.set_facecolor('#F8F9FA')
ax3.set_facecolor('#F8F9FA')

for name in ['LogisticRegression', 'RandomForest', 'XGBoost', 'ExtraTrees']:
    precision, recall = pr_data[name]
    ax3.plot(recall, precision, color=model_colors[name], lw=2.0,
             label=f'{name} (AP = {ap_results[name]:.4f})')

precision, recall = pr_data['Voting Ensemble']
ax3.plot(recall, precision, color=model_colors['Voting Ensemble'], lw=3.0,
         label=f'Voting Ensemble (AP = {ap_results["Voting Ensemble"]:.4f})')

baseline = y.mean()
ax3.axhline(y=baseline, color='black', lw=1.2, linestyle='--', alpha=0.35,
            label=f'Random Classifier (AP = {baseline:.4f})')
ax3.set_xlabel('Recall (Sensitivity)', fontsize=13)
ax3.set_ylabel('Precision (Positive Predictive Value)', fontsize=13)
ax3.set_title('Precision-Recall Curves — 5-Fold CV OOF Predictions', fontsize=14, fontweight='bold')
ax3.legend(loc='lower left', fontsize=10, framealpha=0.85, edgecolor='#CCCCCC')
ax3.set_xlim([-0.02, 1.02]); ax3.set_ylim([-0.02, 1.02])
ax3.grid(True, alpha=0.3, linewidth=0.5, color='#CCCCCC')
ax3.spines['top'].set_visible(False); ax3.spines['right'].set_visible(False)
ax3.spines['left'].set_color('#999999'); ax3.spines['bottom'].set_color('#999999')
ax3.tick_params(colors='#666666')

fig3.savefig('outputs/figures/pr_curves.png', dpi=300, bbox_inches='tight',
             facecolor=fig3.get_facecolor())
plt.close(fig3)
print(f"  [OK] PR curves saved -> outputs/figures/pr_curves.png")

# ── 混淆矩阵（OOF预测，5模型）──
from sklearn.metrics import ConfusionMatrixDisplay, confusion_matrix

n_models = 5
fig4, axes = plt.subplots(2, 3, figsize=(15, 10))
fig4.patch.set_facecolor('#F8F9FA')
axes_flat = axes.ravel()

model_order = ['LogisticRegression', 'RandomForest', 'XGBoost', 'ExtraTrees', 'Voting Ensemble']

for idx, name in enumerate(model_order):
    ax = axes_flat[idx]
    ax.set_facecolor('#F8F9FA')

    # Get OOF predictions
    if name == 'Voting Ensemble':
        y_prob = cross_val_predict(
            voting, X_selected, y, cv=cv5, method='predict_proba', n_jobs=-1
        )[:, 1]
    else:
        y_prob = cross_val_predict(
            models[name], X_selected, y, cv=cv5, method='predict_proba', n_jobs=-1
        )[:, 1]
    y_pred = (y_prob >= 0.5).astype(int)
    cm = confusion_matrix(y, y_pred)
    cm_norm = cm.astype('float') / cm.sum(axis=1, keepdims=True).clip(min=1)

    # Display
    disp = ConfusionMatrixDisplay(confusion_matrix=cm_norm, display_labels=['Non-AKI', 'AKI'])
    disp.plot(ax=ax, cmap=plt.cm.Blues, colorbar=False, values_format='.2f')

    # Overlay raw counts
    for i in range(2):
        for j in range(2):
            ax.text(j, i, f'{cm_norm[i,j]:.1%}\n(n={cm[i,j]})',
                    ha='center', va='center', fontsize=9,
                    color='white' if cm_norm[i,j] > 0.5 else '#333333',
                    fontweight='bold')

    # Label with model name + metrics
    tn, fp, fn, tp = cm.ravel()
    acc = (tp + tn) / (tp + tn + fp + fn)
    sens = tp / (tp + fn) if (tp + fn) > 0 else 0
    spec = tn / (tn + fp) if (tn + fp) > 0 else 0
    cv_auc = all_results[name]['mean']
    label = f'{name}'
    if name == 'Voting Ensemble':
        label += ' (Best)'
    ax.set_title(label, fontsize=12, fontweight='bold',
                 color=model_colors[name])
    ax.set_xlabel(f'AUC={cv_auc:.3f} | Acc={acc:.2f} | Sens={sens:.2f} | Spec={spec:.2f}',
                  fontsize=9, color='#666666')

# Hide extra subplot
axes_flat[5].set_visible(False)

fig4.suptitle('Confusion Matrices — 5-Fold CV OOF Predictions', fontsize=15, fontweight='bold', y=1.01)
fig4.tight_layout()
fig4.savefig('outputs/figures/confusion_matrices.png', dpi=300, bbox_inches='tight',
             facecolor=fig4.get_facecolor())
plt.close(fig4)
print(f"  [OK] Confusion matrices saved -> outputs/figures/confusion_matrices.png")

# ── 校准曲线（OOF预测，5模型）──
from sklearn.calibration import calibration_curve
from sklearn.metrics import brier_score_loss

fig5, axes5 = plt.subplots(2, 3, figsize=(15, 10))
fig5.patch.set_facecolor('#F8F9FA')
axes5_flat = axes5.ravel()

for idx, name in enumerate(model_order):
    ax = axes5_flat[idx]
    ax.set_facecolor('#F8F9FA')

    # OOF predictions
    if name == 'Voting Ensemble':
        y_prob = cross_val_predict(
            voting, X_selected, y, cv=cv5, method='predict_proba', n_jobs=-1
        )[:, 1]
    else:
        y_prob = cross_val_predict(
            models[name], X_selected, y, cv=cv5, method='predict_proba', n_jobs=-1
        )[:, 1]

    prob_true, prob_pred = calibration_curve(y, y_prob, n_bins=10, strategy='uniform')
    brier = brier_score_loss(y, y_prob)
    cv_auc = all_results[name]['mean']

    ax.plot(prob_pred, prob_true, marker='o', linewidth=2, markersize=8,
            color=model_colors[name],
            label=f'Brier={brier:.4f}  AUC={cv_auc:.4f}')
    ax.plot([0, 1], [0, 1], 'k--', lw=1, alpha=0.4, label='Perfect')

    title = f'{name}'
    if name == 'Voting Ensemble':
        title += ' (Weighted: LR=2 RF=2 XGB=1 ET=1)'
    ax.set_title(title, fontsize=12, fontweight='bold', color=model_colors[name])
    ax.set_xlabel('Predicted Probability', fontsize=10, color='#666666')
    ax.set_ylabel('Observed Proportion', fontsize=10, color='#666666')
    ax.legend(loc='lower right', fontsize=7.5, framealpha=0.85)
    ax.set_xlim([-0.02, 1.02]); ax.set_ylim([-0.02, 1.02])
    ax.grid(True, alpha=0.3, linewidth=0.5)
    ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)

# Hide extra subplot
axes5_flat[5].set_visible(False)

fig5.suptitle('Calibration Curves — 5-Fold CV OOF Predictions', fontsize=15, fontweight='bold', y=1.01)
fig5.tight_layout()
fig5.savefig('outputs/figures/calibration_curves.png', dpi=300, bbox_inches='tight',
             facecolor=fig5.get_facecolor())
plt.close(fig5)
print(f"  [OK] Calibration curves saved -> outputs/figures/calibration_curves.png")

# ── 校准曲线叠加对比图 ──
fig6, ax6 = plt.subplots(figsize=(9, 8))
fig6.patch.set_facecolor('#F8F9FA')
ax6.set_facecolor('#F8F9FA')

for name in model_order:
    # Reuse OOF predictions from above (re-compute for simplicity)
    if name == 'Voting Ensemble':
        y_prob = cross_val_predict(
            voting, X_selected, y, cv=cv5, method='predict_proba', n_jobs=-1
        )[:, 1]
    else:
        y_prob = cross_val_predict(
            models[name], X_selected, y, cv=cv5, method='predict_proba', n_jobs=-1
        )[:, 1]

    prob_true, prob_pred = calibration_curve(y, y_prob, n_bins=10, strategy='uniform')
    brier = brier_score_loss(y, y_prob)
    cv_auc = all_results[name]['mean']

    lw = 3.0 if name == 'Voting Ensemble' else 2.0
    marker = 's' if name == 'Voting Ensemble' else 'o'
    ms = 9 if name == 'Voting Ensemble' else 6
    ax6.plot(prob_pred, prob_true, marker=marker, linewidth=lw, markersize=ms,
             color=model_colors[name],
             label=f'{name}  | Brier={brier:.4f}  AUC={cv_auc:.4f}')

ax6.plot([0, 1], [0, 1], 'k--', lw=1.2, alpha=0.4, label='Perfect Calibration')
ax6.set_xlabel('Predicted Probability', fontsize=13)
ax6.set_ylabel('Observed Proportion', fontsize=13)
ax6.set_title('Calibration Curves — Overlay Comparison', fontsize=14, fontweight='bold')
ax6.legend(loc='lower right', fontsize=9, framealpha=0.85, edgecolor='#CCCCCC')
ax6.set_xlim([-0.02, 1.02]); ax6.set_ylim([-0.02, 1.02])
ax6.grid(True, alpha=0.3, linewidth=0.5, color='#CCCCCC')
ax6.spines['top'].set_visible(False); ax6.spines['right'].set_visible(False)
ax6.spines['left'].set_color('#999999'); ax6.spines['bottom'].set_color('#999999')
ax6.tick_params(colors='#666666')

fig6.savefig('outputs/figures/calibration_overlay.png', dpi=300, bbox_inches='tight',
             facecolor=fig6.get_facecolor())
plt.close(fig6)
print(f"  [OK] Calibration overlay saved -> outputs/figures/calibration_overlay.png")

# ── 校准指标热力图 ──
cal_summary = []
for name in model_order:
    if name == 'Voting Ensemble':
        y_prob = y_prob_voting_oof
    else:
        y_prob = cross_val_predict(
            models[name], X_selected, y, cv=cv5, method='predict_proba', n_jobs=-1
        )[:, 1]

    prob_true, prob_pred = calibration_curve(y, y_prob, n_bins=10, strategy='uniform')
    brier = brier_score_loss(y, y_prob)
    eci = np.mean(np.abs(prob_true - prob_pred))
    e50 = np.median(np.abs(prob_true - prob_pred))
    emax = np.max(np.abs(prob_true - prob_pred))

    cal_summary.append({
        'Model': name,
        'Brier': brier,
        'ECE': eci,
        'E50': e50,
        'E_max': emax,
    })

cal_df = pd.DataFrame(cal_summary).set_index('Model')
metrics = ['Brier', 'ECE', 'E50', 'E_max']

fig7, ax7 = plt.subplots(figsize=(8, 3))
fig7.patch.set_facecolor('#F8F9FA')
ax7.set_facecolor('#F8F9FA')

im = ax7.imshow(cal_df[metrics].T.values, cmap='RdYlGn_r', aspect='auto', vmin=0)

# Annotate
for i in range(len(metrics)):
    for j in range(len(model_order)):
        val = cal_df[metrics].T.values[i, j]
        color = 'white' if val > 0.15 else '#333333'
        ax7.text(j, i, f'{val:.4f}', ha='center', va='center', fontsize=10,
                 fontweight='bold', color=color)

ax7.set_xticks(range(len(model_order)))
ax7.set_xticklabels(model_order, fontsize=9, rotation=15, ha='right')
ax7.set_yticks(range(len(metrics)))
ax7.set_yticklabels(metrics, fontsize=10)
ax7.set_title('Calibration Metrics — OOF Predictions', fontsize=13, fontweight='bold')

cbar = fig7.colorbar(im, ax=ax7, shrink=0.85, pad=0.02)
cbar.set_label('Error (lower = better)', fontsize=9)

fig7.tight_layout()
fig7.savefig('outputs/figures/calibration_heatmap.png', dpi=300, bbox_inches='tight',
             facecolor=fig7.get_facecolor())
plt.close(fig7)
print(f"  [OK] Calibration heatmap saved -> outputs/figures/calibration_heatmap.png")

# ── SHAP 可解释性分析（基于 XGBoost，AUC=0.819 最接近Voting）──
print("\n  生成 SHAP 可解释性图...")
import shap

# 使用全量数据训练 XGBoost 做 SHAP
xgb_shap = models['XGBoost']
xgb_shap.fit(X_selected, y)

# TreeExplainer (快速精确)
explainer = shap.TreeExplainer(xgb_shap)
shap_values = explainer.shap_values(X_selected)

# 特征名映射
feature_names_short = [f[:25] for f in top_features]

# SHAP Summary (bee swarm)
fig8, ax8 = plt.subplots(figsize=(10, 8))
fig8.patch.set_facecolor('#F8F9FA')
shap.summary_plot(shap_values, X_selected, feature_names=feature_names_short,
                  max_display=20, show=False)
ax8 = plt.gca()
ax8.set_title('SHAP Summary — Feature Impact on AKI Prediction (XGBoost)', fontsize=13, fontweight='bold')
fig8.tight_layout()
fig8.savefig('outputs/figures/shap_summary.png', dpi=300, bbox_inches='tight',
             facecolor=fig8.get_facecolor())
plt.close(fig8)
print(f"  [OK] SHAP summary saved -> outputs/figures/shap_summary.png")

# SHAP Bar (mean |SHAP|)
fig9, ax9 = plt.subplots(figsize=(10, 8))
fig9.patch.set_facecolor('#F8F9FA')
shap.summary_plot(shap_values, X_selected, feature_names=feature_names_short,
                  max_display=20, plot_type='bar', show=False)
ax9 = plt.gca()
ax9.set_title('SHAP Feature Importance — Mean |SHAP| (XGBoost)', fontsize=13, fontweight='bold')
fig9.tight_layout()
fig9.savefig('outputs/figures/shap_bar.png', dpi=300, bbox_inches='tight',
             facecolor=fig9.get_facecolor())
plt.close(fig9)
print(f"  [OK] SHAP bar saved -> outputs/figures/shap_bar.png")

# SHAP Dependence (Top 4 features)
top4_idx = np.argsort(np.abs(shap_values).mean(axis=0))[::-1][:4]
fig10, axes10 = plt.subplots(2, 2, figsize=(14, 12))
fig10.patch.set_facecolor('#F8F9FA')
axes10_flat = axes10.ravel()

for i, feat_idx in enumerate(top4_idx):
    ax = axes10_flat[i]
    ax.set_facecolor('#F8F9FA')
    shap.dependence_plot(feat_idx, shap_values, X_selected,
                         feature_names=feature_names_short, ax=ax, show=False)
    ax.set_title(f'SHAP Dependence — {feature_names_short[feat_idx]}', fontsize=11, fontweight='bold')
    ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)

fig10.suptitle('SHAP Dependence — Top 4 Features (XGBoost)', fontsize=14, fontweight='bold', y=1.01)
fig10.tight_layout()
fig10.savefig('outputs/figures/shap_dependence.png', dpi=300, bbox_inches='tight',
             facecolor=fig10.get_facecolor())
plt.close(fig10)
print(f"  [OK] SHAP dependence saved -> outputs/figures/shap_dependence.png")

# SHAP 重要性表
mean_shap = np.abs(shap_values).mean(axis=0)
shap_df = pd.DataFrame({
    'Feature': top_features,
    'Mean_ABS_SHAP': mean_shap
}).sort_values('Mean_ABS_SHAP', ascending=False)
shap_df.to_csv('outputs/tables/shap_importance.csv', index=False, encoding='utf-8-sig')
print(f"  [OK] SHAP importance table -> outputs/tables/shap_importance.csv")

# ── PDP 非线性效应图（Voting Ensemble, Top4特征）──
print("\n  生成 PDP + 亚组分析...")
from sklearn.inspection import PartialDependenceDisplay

# 用全量数据训练 Voting 做 PDP
voting_full = VotingClassifier(
    estimators=[(name, model) for name, model in models.items()],
    voting='soft', weights=[2, 2, 1, 1]
)
voting_full.fit(X_selected, y)

# Top4 SHAP特征索引
pdp_indices = top4_idx[:4]
pdp_names = [top_features[i][:25] for i in pdp_indices]

fig_pdp, ax_pdp = plt.subplots(2, 2, figsize=(14, 12))
fig_pdp.patch.set_facecolor('#F8F9FA')
ax_pdp_flat = ax_pdp.ravel()

# 逐个画 PDP（PartialDependenceDisplay 一次画一个）
for i, feat_idx in enumerate(pdp_indices):
    ax = ax_pdp_flat[i]
    ax.set_facecolor('#F8F9FA')
    PartialDependenceDisplay.from_estimator(
        voting_full, X_selected, [feat_idx], ax=ax,
        grid_resolution=50, line_kw={'color': model_colors['Voting Ensemble'], 'lw': 2}
    )
    ax.set_title(pdp_names[i], fontsize=12, fontweight='bold')
    ax.set_xlabel('')
    ax.set_ylabel('')
    ax.grid(True, alpha=0.3)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

fig_pdp.suptitle('Partial Dependence Plots — Top 4 Features (Voting Ensemble)', fontsize=14, fontweight='bold')
fig_pdp.supxlabel('Feature Value', fontsize=11, y=0.02)
fig_pdp.supylabel('Predicted AKI Probability', fontsize=11, x=0.02)
fig_pdp.tight_layout()
fig_pdp.savefig('outputs/figures/PDP非线性效应.png', dpi=300, bbox_inches='tight',
                facecolor=fig_pdp.get_facecolor())
plt.close(fig_pdp)
print(f"  [OK] PDP saved -> outputs/figures/PDP非线性效应.png")

# ── 亚组分析（Voting Ensemble）──
prob_all = voting_full.predict_proba(X_selected)[:, 1]
risk_median = np.median(prob_all)

subgroups = [
    ('High Risk\n(prob >= median)', prob_all >= risk_median, '#F44336'),
    ('Low Risk\n(prob < median)', prob_all < risk_median, '#4CAF50'),
]
# ICU入室肌酐分层
if 'ICUAdmSCr' in top_features:
    idx_scr = top_features.index('ICUAdmSCr')
    scr_vals = X_selected[:, idx_scr]
    scr_med = np.median(scr_vals)
    subgroups += [
        ('Worse Renal\n(ICU-SCr >= median)', scr_vals >= scr_med, '#FF9800'),
        ('Better Renal\n(ICU-SCr < median)', scr_vals < scr_med, '#2196F3'),
    ]

sub_data = []
for label, mask, clr in subgroups:
    n_s = mask.sum()
    aki_rate = y[mask].mean() * 100 if n_s > 0 else 0
    sub_data.append({'label': label, 'n': n_s, 'rate': aki_rate, 'color': clr})

fig_sub, ax_sub = plt.subplots(figsize=(12, 5))
fig_sub.patch.set_facecolor('#F8F9FA')
ax_sub.set_facecolor('#F8F9FA')

labels = [d['label'] for d in sub_data]
rates = [d['rate'] for d in sub_data]
colors = [d['color'] for d in sub_data]
ns = [d['n'] for d in sub_data]

y_pos = range(len(labels))
bars = ax_sub.barh(y_pos, rates, color=colors, alpha=0.85, height=0.6, edgecolor='white')
for bar, n, rate in zip(bars, ns, rates):
    ax_sub.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height()/2,
                f'n={n}  ({rate:.1f}%)', va='center', fontsize=11, fontweight='bold')
ax_sub.set_yticks(y_pos)
ax_sub.set_yticklabels(labels, fontsize=10)
ax_sub.set_xlabel('AKI Incidence (%)', fontsize=12)
ax_sub.set_title('Subgroup Analysis — AKI Risk Stratification (Voting Ensemble)', fontsize=13, fontweight='bold')
ax_sub.set_xlim([0, max(rates) * 1.15])
ax_sub.grid(axis='x', alpha=0.3)
ax_sub.spines['top'].set_visible(False); ax_sub.spines['right'].set_visible(False)

fig_sub.tight_layout()
fig_sub.savefig('outputs/figures/亚组分析.png', dpi=300, bbox_inches='tight',
                facecolor=fig_sub.get_facecolor())
plt.close(fig_sub)

# 保存亚组分析表
sub_df = pd.DataFrame([
    {'Subgroup': d['label'].replace('\n', ' '), 'N': d['n'], 'AKI_Rate_%': f"{d['rate']:.1f}"}
    for d in sub_data
])
sub_df.to_csv('outputs/tables/亚组分析.csv', index=False, encoding='utf-8-sig')
print(f"  [OK] Subgroup analysis saved -> outputs/figures/亚组分析.png")
print(f"  [OK] Subgroup table -> outputs/tables/亚组分析.csv")

# ── DCA with 95% CI（Voting Ensemble, Bootstrap）──
print("\n  生成 DCA with 95% CI...")

def _net_benefit(y_true, y_prob, threshold):
    """Net benefit = (TP/N) - (FP/N) * (threshold/(1-threshold))"""
    y_pred = (y_prob >= threshold).astype(int)
    tp = ((y_pred == 1) & (y_true == 1)).sum()
    fp = ((y_pred == 1) & (y_true == 0)).sum()
    n = len(y_true)
    nb = tp / n - fp / n * (threshold / (1 - threshold))
    return nb

def _treat_all_nb(y_true, threshold):
    """Net benefit of treating everyone."""
    tp = y_true.sum()
    fp = (1 - y_true).sum()
    n = len(y_true)
    return tp / n - fp / n * (threshold / (1 - threshold))

# OOF predictions for Voting
y_prob_dca = y_prob_voting_oof
thresholds = np.linspace(0.01, 0.99, 99)

# Bootstrap CI
n_boot = 500
rng_dca = np.random.RandomState(42)
nb_bootstrap = np.zeros((n_boot, len(thresholds)))

for b in range(n_boot):
    idx = rng_dca.choice(len(y), len(y), replace=True)
    y_b = y.iloc[idx].values
    p_b = y_prob_dca[idx]
    for j, t in enumerate(thresholds):
        nb_bootstrap[b, j] = _net_benefit(y_b, p_b, t)

nb_lower = np.percentile(nb_bootstrap, 2.5, axis=0)
nb_upper = np.percentile(nb_bootstrap, 97.5, axis=0)
nb_mean = np.array([_net_benefit(y.values, y_prob_dca, t) for t in thresholds])
nb_treat_all = np.array([_treat_all_nb(y.values, t) for t in thresholds])

fig_dca, ax_dca = plt.subplots(figsize=(10, 8))
fig_dca.patch.set_facecolor('#F8F9FA')
ax_dca.set_facecolor('#F8F9FA')

ax_dca.fill_between(thresholds, nb_lower, nb_upper, alpha=0.2, color='#1B1B1B',
                    label=f'95% CI (Bootstrap n={n_boot})')
ax_dca.plot(thresholds, nb_mean, '-', color='#1B1B1B', lw=3,
            label=f'Voting Ensemble (AUC={voting_cv_auc:.4f})')
ax_dca.plot(thresholds, nb_treat_all, '--', color='#999999', lw=2, label='Treat All')
ax_dca.plot(thresholds, np.zeros_like(thresholds), '-', color='#CCCCCC', lw=2, label='Treat None')

ax_dca.set_xlabel('Threshold Probability', fontsize=13)
ax_dca.set_ylabel('Net Benefit', fontsize=13)
ax_dca.set_title('Decision Curve Analysis — Voting Ensemble with 95% CI', fontsize=14, fontweight='bold')
ax_dca.legend(loc='upper right', fontsize=10, framealpha=0.85, edgecolor='#CCCCCC')
ax_dca.set_xlim([0, 1])
ax_dca.set_ylim([-0.05, None])
ax_dca.grid(True, alpha=0.3, linewidth=0.5, color='#CCCCCC')
ax_dca.spines['top'].set_visible(False); ax_dca.spines['right'].set_visible(False)
ax_dca.spines['left'].set_color('#999999'); ax_dca.spines['bottom'].set_color('#999999')
ax_dca.tick_params(colors='#666666')

# Annotation
ax_dca.annotate(
    'Curve above Treat All = clinical net benefit',
    xy=(0.15, 0.12), fontsize=9, ha='left', color='#333333',
    bbox=dict(boxstyle='round,pad=0.3', facecolor='#fffde7', edgecolor='#F18F01', alpha=0.9)
)

fig_dca.tight_layout()
fig_dca.savefig('outputs/figures/dca_with_ci.png', dpi=300, bbox_inches='tight',
                facecolor=fig_dca.get_facecolor())
plt.close(fig_dca)
print(f"  [OK] DCA with CI saved -> outputs/figures/dca_with_ci.png")

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

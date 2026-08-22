# -*- coding: utf-8 -*-
"""
比赛图表生成 —— 基于 run_clean.py 保存的最终模型

运行: python run_evaluation.py

直接加载 run_clean.py 输出的 models/*.pkl 和 models/selected_features.txt，
重建相同的 Top35 特征矩阵并用 5 折 OOF 预测生成比赛图表，
保证 ROC / PR / 校准 / DCA / SHAP 与最终 Voting Ensemble
(50次嵌套CV AUC=0.8096) 一致，不再使用旧版"仅术前特征"模型。
"""

import os
import warnings

warnings.filterwarnings('ignore')

import joblib

def _check_lfs(path):
    import sys
    if path.exists() and path.stat().st_size < 300:
        head = path.read_bytes()[:40]
        if head.startswith(b"version https://git-lfs"):
            sys.exit(
                f"Error: {path.name} is a Git LFS pointer ({path.stat().st_size} bytes). "
                "Run 'git lfs pull' or 'python run_clean.py' first."
            )

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use('Agg')
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt

from sklearn.metrics import (
    accuracy_score,
    auc,
    average_precision_score,
    brier_score_loss,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.calibration import calibration_curve
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.feature_selection import SelectFromModel
from sklearn.ensemble import RandomForestClassifier

from src.config import TARGET, is_leakage
from src.data.prepare import prepare_raw_numeric, prepare_training_data

import os as _os
from pathlib import Path as _Path
# 无论从哪个目录执行，产物都落到仓库根目录
_os.chdir(_Path(__file__).resolve().parent)

os.makedirs('outputs/figures', exist_ok=True)
os.makedirs('outputs/tables', exist_ok=True)

# 与 run_clean.py 保持一致的字体设置
for _font_path in [r'C:\Windows\Fonts\simhei.ttf', r'C:\Windows\Fonts\msyh.ttc']:
    try:
        if os.path.exists(_font_path):
            fm.fontManager.addfont(_font_path)
    except Exception:
        pass
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

BG = '#F8F9FA'
model_colors = {
    'LogisticRegression': '#2E86AB',
    'RandomForest': '#A23B72',
    'XGBoost': '#F18F01',
    'ExtraTrees': '#C73E1D',
    'Voting Ensemble': '#1B1B1B',
}
model_order = ['LogisticRegression', 'RandomForest', 'XGBoost', 'ExtraTrees', 'Voting Ensemble']

print('=' * 70)
print(' 比赛图表生成 —— 基于 run_clean.py 最终模型')
print('=' * 70)

# ---------------------------------------------------------------
# 1. 重建与 run_clean.py 完全一致的 Top35 特征矩阵
# ---------------------------------------------------------------
print('\n1/6 重建最终特征矩阵 (Top35)...')
df = pd.read_excel('data/raw/AKI数据.xlsx')
prep = prepare_training_data(df)
X = prep['X']
y = prep['y']
X_raw = prepare_raw_numeric(df)

# 最终模型在全量数据的缩放矩阵上完成特征筛选，图表沿用同一口径
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

with open('models/selected_features.txt', 'r', encoding='utf-8') as f:
    top_features = [line.rstrip('\r\n') for line in f if line.rstrip('\r\n')]

missing = [f for f in top_features if f not in X.columns]
if missing:
    raise SystemExit(f'selected_features.txt 与数据列不匹配: {missing}')

top_indices = np.array([X.columns.get_loc(f) for f in top_features], dtype=int)
X_selected = X_scaled[:, top_indices]
print(f'    样本 {len(y)} 例, 特征 {len(top_features)} 个, AKI 发生率 {y.mean():.1%}')


_cv_selector = RandomForestClassifier(
    n_estimators=200, class_weight='balanced', random_state=42, n_jobs=-1
)


def build_honest_pipeline(model):
    """Median impute + scale + RF Top35 inside every fold."""
    return Pipeline([
        ('imputer', SimpleImputer(strategy='median')),
        ('scaler', StandardScaler()),
        ('selector', SelectFromModel(_cv_selector, max_features=35, threshold=-np.inf)),
        ('model', model),
    ])

# ---------------------------------------------------------------
# 2. 加载 run_clean.py 保存的最终模型与 50次CV结果
# ---------------------------------------------------------------
print('\n2/6 加载 run_clean.py 保存的最终模型...')
models = {}
for name in ['LogisticRegression', 'RandomForest', 'XGBoost', 'ExtraTrees']:
    path = f'models/{name}.pkl'
    if not os.path.exists(path):
        raise SystemExit(f'缺少模型文件 {path}，请先运行 python run_clean.py')
    models[name] = joblib.load(path)
voting = joblib.load('models/final_voting_model.pkl')
models['Voting Ensemble'] = voting

cv_csv = 'outputs/tables/final_cv_results.csv'
if os.path.exists(cv_csv):
    cv_df = pd.read_csv(cv_csv, encoding='utf-8-sig')
    all_results = {
        row['模型']: {'mean': float(row['50次CV AUC均值']), 'std': float(row['标准差'])}
        for _, row in cv_df.iterrows()
    }
else:
    print('    [WARN] 未找到 final_cv_results.csv，用 5 折 CV 计算标签 AUC')
    cv5_temp = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    all_results = {}
    for name, model in models.items():
        from sklearn.model_selection import cross_val_score
        scores = cross_val_score(
            build_honest_pipeline(model), X_raw, y, cv=cv5_temp,
            scoring='roc_auc', n_jobs=1
        )
        all_results[name] = {'mean': scores.mean(), 'std': scores.std()}

voting_cv_auc = all_results['Voting Ensemble']['mean']
voting_cv_std = all_results['Voting Ensemble']['std']
print(f'    最终模型 Voting Ensemble: 50次嵌套CV AUC = {voting_cv_auc:.4f} ± {voting_cv_std:.4f}')

# ---------------------------------------------------------------
# 3. 5 折 OOF 预测（与 run_clean.py 图表同口径）
# ---------------------------------------------------------------
print('\n3/6 计算 5 折 OOF 预测...')
cv5 = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
y_prob_oof = {}
for name in model_order:
    print(f'    {name} ...')
    y_prob_oof[name] = cross_val_predict(
        build_honest_pipeline(models[name]), X_raw, y,
        cv=cv5, method='predict_proba', n_jobs=-1
    )[:, 1]

# ---------------------------------------------------------------
# 4. ROC / PR / 校准曲线
# ---------------------------------------------------------------
print('\n4/6 生成 ROC / PR / 校准曲线...')

fig, ax = plt.subplots(figsize=(10, 8))
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)
for name in model_order:
    fpr, tpr, _ = roc_curve(y, y_prob_oof[name])
    cv_auc = all_results[name]['mean']
    lw = 3.0 if name == 'Voting Ensemble' else 2.0
    zorder = 5 if name == 'Voting Ensemble' else 3
    ax.plot(fpr, tpr, color=model_colors[name], lw=lw, zorder=zorder,
            label=f'{name} (AUC = {cv_auc:.4f})')
ax.plot([0, 1], [0, 1], 'k--', lw=1.2, alpha=0.35,
        label='Random Classifier (AUC = 0.5000)')
ax.set_xlabel('False Positive Rate (1 - Specificity)', fontsize=13)
ax.set_ylabel('True Positive Rate (Sensitivity)', fontsize=13)
ax.set_title('ROC Curves — 5-Fold CV OOF Predictions', fontsize=14, fontweight='bold')
ax.legend(loc='lower right', fontsize=10, framealpha=0.85, edgecolor='#CCCCCC')
ax.set_xlim((-0.02, 1.02))
ax.set_ylim((-0.02, 1.02))
ax.grid(True, alpha=0.3, linewidth=0.5, color='#CCCCCC')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.spines['left'].set_color('#999999')
ax.spines['bottom'].set_color('#999999')
ax.tick_params(colors='#666666')
fig.savefig('outputs/figures/roc_curves.png', dpi=300, bbox_inches='tight',
            facecolor=fig.get_facecolor())
plt.close(fig)
print('    [OK] roc_curves.png')

fig, ax = plt.subplots(figsize=(9, 8))
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)
ap_results = {}
for name in model_order:
    precision, recall, _ = precision_recall_curve(y, y_prob_oof[name])
    ap = average_precision_score(y, y_prob_oof[name])
    ap_results[name] = ap
    lw = 3.0 if name == 'Voting Ensemble' else 2.0
    ax.plot(recall, precision, color=model_colors[name], lw=lw,
            label=f'{name} (AP = {ap:.4f})')
ax.axhline(y=y.mean(), color='black', lw=1.2, linestyle='--', alpha=0.35,
           label=f'Random Classifier (AP = {y.mean():.4f})')
ax.set_xlabel('Recall (Sensitivity)', fontsize=13)
ax.set_ylabel('Precision (Positive Predictive Value)', fontsize=13)
ax.set_title('Precision-Recall Curves — 5-Fold CV OOF Predictions', fontsize=14, fontweight='bold')
ax.legend(loc='lower left', fontsize=10, framealpha=0.85, edgecolor='#CCCCCC')
ax.set_xlim((-0.02, 1.02))
ax.set_ylim((-0.02, 1.02))
ax.grid(True, alpha=0.3, linewidth=0.5, color='#CCCCCC')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.spines['left'].set_color('#999999')
ax.spines['bottom'].set_color('#999999')
ax.tick_params(colors='#666666')
fig.savefig('outputs/figures/pr_curves.png', dpi=300, bbox_inches='tight',
            facecolor=fig.get_facecolor())
plt.close(fig)
print('    [OK] pr_curves.png')

fig, ax = plt.subplots(figsize=(9, 8))
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)
for name in model_order:
    prob_true, prob_pred = calibration_curve(y, y_prob_oof[name], n_bins=10, strategy='uniform')
    brier = brier_score_loss(y, y_prob_oof[name])
    cv_auc = all_results[name]['mean']
    lw = 3.0 if name == 'Voting Ensemble' else 2.0
    marker = 's' if name == 'Voting Ensemble' else 'o'
    ms = 9 if name == 'Voting Ensemble' else 6
    ax.plot(prob_pred, prob_true, marker=marker, linewidth=lw, markersize=ms,
            color=model_colors[name],
            label=f'{name} | Brier={brier:.4f} AUC={cv_auc:.4f}')
ax.plot([0, 1], [0, 1], 'k--', lw=1.2, alpha=0.4, label='Perfect Calibration')
ax.set_xlabel('Predicted Probability', fontsize=13)
ax.set_ylabel('Observed Proportion', fontsize=13)
ax.set_title('Calibration Curves — 5-Fold CV OOF Predictions', fontsize=14, fontweight='bold')
ax.legend(loc='lower right', fontsize=9, framealpha=0.85, edgecolor='#CCCCCC')
ax.set_xlim((-0.02, 1.02))
ax.set_ylim((-0.02, 1.02))
ax.grid(True, alpha=0.3, linewidth=0.5, color='#CCCCCC')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.spines['left'].set_color('#999999')
ax.spines['bottom'].set_color('#999999')
ax.tick_params(colors='#666666')
fig.savefig('outputs/figures/calibration_curves.png', dpi=300, bbox_inches='tight',
            facecolor=fig.get_facecolor())
fig.savefig('outputs/figures/calibration_overlay.png', dpi=300, bbox_inches='tight',
            facecolor=fig.get_facecolor())
plt.close(fig)
print('    [OK] calibration_curves.png / calibration_overlay.png')

# ---------------------------------------------------------------
# 5. DCA 决策曲线（Voting Ensemble, Bootstrap 95% CI）
# ---------------------------------------------------------------
print('\n5/6 生成 DCA 决策曲线...')


def net_benefit(y_true, y_prob, threshold):
    y_pred = (y_prob >= threshold).astype(int)
    tp = np.sum((y_true == 1) & (y_pred == 1))
    fp = np.sum((y_true == 0) & (y_pred == 1))
    n = len(y_true)
    return tp / n - fp / n * (threshold / (1 - threshold))


thresholds = np.linspace(0.01, 0.99, 99)
y_vals = np.asarray(y)
y_prob_v = y_prob_oof['Voting Ensemble']

n_boot = 500
rng = np.random.RandomState(42)
nb_boot = np.zeros((n_boot, len(thresholds)))
for b in range(n_boot):
    idx = rng.choice(len(y_vals), len(y_vals), replace=True)
    y_b = y_vals[idx]
    p_b = y_prob_v[idx]
    for j, t in enumerate(thresholds):
        nb_boot[b, j] = net_benefit(y_b, p_b, t)

nb_lower = np.percentile(nb_boot, 2.5, axis=0)
nb_upper = np.percentile(nb_boot, 97.5, axis=0)
nb_mean = np.array([net_benefit(y_vals, y_prob_v, t) for t in thresholds])
prevalence = float(np.mean(y_vals))
nb_treat_all = np.array([prevalence - (1 - prevalence) * t / (1 - t) for t in thresholds])

fig, ax = plt.subplots(figsize=(10, 8))
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)
ax.fill_between(thresholds, nb_lower, nb_upper, alpha=0.2, color='#1B1B1B',
                label=f'95% CI (Bootstrap n={n_boot})')
ax.plot(thresholds, nb_mean, '-', color='#1B1B1B', lw=3,
        label=f'Voting Ensemble (AUC={voting_cv_auc:.4f})')
ax.plot(thresholds, nb_treat_all, '--', color='#999999', lw=2, label='Treat All')
ax.plot(thresholds, np.zeros_like(thresholds), '-', color='#CCCCCC', lw=2, label='Treat None')
ax.set_xlabel('Threshold Probability', fontsize=13)
ax.set_ylabel('Net Benefit', fontsize=13)
ax.set_title('Decision Curve Analysis — Voting Ensemble with 95% CI', fontsize=14, fontweight='bold')
ax.legend(loc='upper right', fontsize=10, framealpha=0.85, edgecolor='#CCCCCC')
ax.set_xlim((0, 1))
ax.set_ylim(bottom=-0.05)  # top auto; tuple form rejects None in stubs
ax.grid(True, alpha=0.3, linewidth=0.5, color='#CCCCCC')
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)
ax.spines['left'].set_color('#999999')
ax.spines['bottom'].set_color('#999999')
ax.tick_params(colors='#666666')
fig.tight_layout()
for fname in ['dca_with_ci.png', 'dca_curve.png', 'decision_curve.png']:
    fig.savefig(f'outputs/figures/{fname}', dpi=300, bbox_inches='tight',
                facecolor=fig.get_facecolor())
plt.close(fig)
print('    [OK] dca_with_ci.png / dca_curve.png / decision_curve.png')

# ---------------------------------------------------------------
# 6. SHAP 可解释性（基于最终 XGBoost）
# ---------------------------------------------------------------
print('\n6/6 生成 SHAP 可解释性图...')
try:
    import shap

    xgb_model = models['XGBoost']
    xgb_model.fit(X_selected, y)
    explainer = shap.TreeExplainer(xgb_model)
    shap_values = explainer.shap_values(X_selected)
    feature_names_short = [f[:25] for f in top_features]

    fig, ax = plt.subplots(figsize=(10, 8))
    fig.patch.set_facecolor(BG)
    shap.summary_plot(shap_values, X_selected, feature_names=feature_names_short,
                      max_display=20, show=False)
    ax = plt.gca()
    ax.set_title('SHAP Summary — Feature Impact on AKI Prediction (XGBoost)',
                 fontsize=13, fontweight='bold')
    fig.tight_layout()
    fig.savefig('outputs/figures/shap_summary.png', dpi=300, bbox_inches='tight',
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print('    [OK] shap_summary.png')

    fig, ax = plt.subplots(figsize=(10, 8))
    fig.patch.set_facecolor(BG)
    shap.summary_plot(shap_values, X_selected, feature_names=feature_names_short,
                      max_display=20, plot_type='bar', show=False)
    ax = plt.gca()
    ax.set_title('SHAP Feature Importance — Mean |SHAP| (XGBoost)',
                 fontsize=13, fontweight='bold')
    fig.tight_layout()
    fig.savefig('outputs/figures/shap_bar.png', dpi=300, bbox_inches='tight',
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print('    [OK] shap_bar.png')

    mean_shap = np.abs(shap_values).mean(axis=0)
    shap_df = pd.DataFrame({
        'Feature': top_features,
        'Mean_ABS_SHAP': mean_shap,
    }).sort_values('Mean_ABS_SHAP', ascending=False)
    shap_df.to_csv('outputs/tables/shap_importance.csv', index=False, encoding='utf-8-sig')
    print('    [OK] shap_importance.csv')
except Exception as e:
    print(f'    [WARN] SHAP 生成失败: {e}')

# ---------------------------------------------------------------
# 汇总表：OOF 指标 + run_clean.py 官方 50次嵌套CV AUC
# ---------------------------------------------------------------
rows = []
for name in model_order:
    y_prob = y_prob_oof[name]
    y_pred = (y_prob >= 0.5).astype(int)
    rows.append({
        'Model': name,
        'OOF AUC': roc_auc_score(y, y_prob),
        '50xCV AUC (mean)': all_results[name]['mean'],
        '50xCV AUC (std)': all_results[name]['std'],
        'Accuracy': accuracy_score(y, y_pred),
        'Precision': precision_score(y, y_pred, zero_division=0),
        'Recall': recall_score(y, y_pred, zero_division=0),
        'F1': f1_score(y, y_pred, zero_division=0),
    })
summary_df = pd.DataFrame(rows).sort_values('50xCV AUC (mean)', ascending=False)
summary_df.to_csv('outputs/tables/model_summary_clean.csv', index=False, encoding='utf-8-sig')

print('\n' + '=' * 70)
print(' 完成！比赛图表已基于最终模型生成')
print(f' Voting Ensemble 50次嵌套CV AUC = {voting_cv_auc:.4f} ± {voting_cv_std:.4f}')
print('=' * 70)
print(summary_df.to_string(index=False))
print('\n生成文件:')
print('  outputs/figures/roc_curves.png')
print('  outputs/figures/pr_curves.png')
print('  outputs/figures/calibration_curves.png')
print('  outputs/figures/dca_with_ci.png / decision_curve.png')
print('  outputs/figures/shap_summary.png / shap_bar.png')
print('  outputs/tables/model_summary_clean.csv')

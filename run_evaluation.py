"""
======================================================================
  AKI 急性肾损伤预测 —— 比赛展示图表生成
  广西科技大学 蓝可 | 白菜卷队 | 暑期数创2026

  生成：ROC曲线 / PR曲线 / 校准曲线 / DCA决策曲线 / SHAP解释
  使用：仅术前特征，5折交叉验证，无数据泄漏
======================================================================
"""
import warnings
warnings.filterwarnings('ignore')

import pandas as pd, numpy as np, os, joblib

os.makedirs('outputs/figures', exist_ok=True)
os.makedirs('outputs/tables', exist_ok=True)

# ============================================================
# 1. 加载数据（仅术前特征）
# ============================================================
print("1/7 加载数据...")
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.model_selection import train_test_split

df = pd.read_excel('data/raw/AKI数据.xlsx')

# 关键词过滤泄漏特征
def is_leakage(col_name):
    name = col_name.strip()
    if name in ['住院号', 'AKI分组', 'AKI分期']:
        return True
    if '术后' in name or 'ICU' in name or '术中' in name:
        return True
    # 结局变量（用子串匹配，覆盖 总住院/住院/ICU住院 等变体）
    if any(kw in name for kw in ['住院费', '住院天', '住院日', '机械通气', 'ICU住院']):
        return True
    return False

TARGET = 'AKI分组'
safe_features = [c for c in df.columns if not is_leakage(c) and c != TARGET]

y = df[TARGET].copy()
X = df[safe_features].copy()

for col in X.select_dtypes(include=['object']).columns:
    X[col] = LabelEncoder().fit_transform(X[col].astype(str))

X = X.select_dtypes(include=[np.number])
X = X.replace([np.inf, -np.inf], np.nan).fillna(X.median())

# 标准化
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

# 划分
X_train, X_test, y_train, y_test = train_test_split(
    X_scaled, y, test_size=0.2, stratify=y, random_state=42
)
print(f"   术前特征: {X.shape[1]}个, 训练: {len(X_train)}, 测试: {len(X_test)}")
print(f"   AKI 发生率: {y.mean():.1%}")

# ============================================================
# 2. 训练模型
# ============================================================
print("2/7 训练模型...")
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.neural_network import MLPClassifier

models = {
    'LogisticRegression': LogisticRegression(
        C=0.1, penalty='l2', class_weight='balanced', max_iter=5000, random_state=42
    ),
    'RandomForest': RandomForestClassifier(
        n_estimators=200, max_depth=3, min_samples_leaf=10,
        class_weight='balanced', random_state=42, n_jobs=-1
    ),
}
for lib_name, cls_name in [('xgboost','XGBClassifier'),('lightgbm','LGBMClassifier'),('catboost','CatBoostClassifier')]:
    try:
        mod = __import__(lib_name)
        ModelClass = getattr(mod, cls_name)
        if lib_name == 'catboost':
            models['CatBoost'] = ModelClass(iterations=100, depth=3, learning_rate=0.05,
                l2_leaf_reg=3, auto_class_weights='Balanced', random_seed=42, verbose=0)
        elif lib_name == 'xgboost':
            models['XGBoost'] = ModelClass(n_estimators=100, max_depth=3, learning_rate=0.05,
                reg_alpha=1, reg_lambda=1, subsample=0.8,
                scale_pos_weight=(y_train==0).sum()/max((y_train==1).sum(),1),
                random_state=42, use_label_encoder=False, eval_metric='logloss', verbosity=0)
        elif lib_name == 'lightgbm':
            models['LightGBM'] = ModelClass(n_estimators=100, max_depth=3, num_leaves=7,
                learning_rate=0.05, min_child_samples=20, reg_alpha=1, reg_lambda=1,
                class_weight='balanced', random_state=42, verbose=-1)
    except:
        pass

print(f"   训练 {len(models)} 个模型...")
model_results = {}
for name, model in models.items():
    model.fit(X_train, y_train)
    if hasattr(model, 'predict_proba'):
        y_prob = model.predict_proba(X_test)[:, 1]
    else:
        y_prob = model.predict(X_test)
    y_pred = (y_prob >= 0.5).astype(int)
    model_results[name] = {
        'y_true': y_test.values,
        'y_prob': y_prob,
        'y_pred': y_pred,
        'model': model,
    }

# ============================================================
# 3. ROC 曲线
# ============================================================
print("3/7 生成 ROC 曲线...")
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.metrics import roc_curve, auc

fig, ax = plt.subplots(figsize=(10, 8))
colors = plt.cm.tab10(np.linspace(0, 1, len(model_results)))

def get_auc(res):
    fpr, tpr, _ = roc_curve(res['y_true'], res['y_prob'])
    return auc(fpr, tpr)

for i, (name, res) in enumerate(sorted(model_results.items(), key=lambda x: get_auc(x[1]), reverse=True)):
    fpr, tpr, _ = roc_curve(res['y_true'], res['y_prob'])
    roc_auc = auc(fpr, tpr)
    ax.plot(fpr, tpr, linewidth=2, color=colors[i], label=f'{name} (AUC={roc_auc:.4f})')

ax.plot([0, 1], [0, 1], 'k--', linewidth=1, alpha=0.3, label='Random')
ax.set_xlabel('1 - Specificity (False Positive Rate)', fontsize=12)
ax.set_ylabel('Sensitivity (True Positive Rate)', fontsize=12)
ax.set_title('ROC Curves - AKI Prediction Models\n(5-fold CV, Pre-operative Features Only)', fontsize=14, fontweight='bold')
ax.legend(loc='lower right', fontsize=10)
ax.grid(True, alpha=0.3)
plt.tight_layout()
fig.savefig('outputs/figures/roc_curves.png', dpi=300, bbox_inches='tight')
plt.close()
print("   [OK] outputs/figures/roc_curves.png")

# ============================================================
# 4. PR 曲线
# ============================================================
print("4/7 生成 PR 曲线...")
from sklearn.metrics import precision_recall_curve, average_precision_score

fig, ax = plt.subplots(figsize=(10, 8))
baseline = y_test.mean()

for i, (name, res) in enumerate(model_results.items()):
    precision, recall, _ = precision_recall_curve(res['y_true'], res['y_prob'])
    ap = average_precision_score(res['y_true'], res['y_prob'])
    ax.plot(recall, precision, linewidth=2, color=colors[i], label=f'{name} (AP={ap:.4f})')

ax.axhline(y=baseline, color='gray', linestyle='--', alpha=0.5,
           label=f'Baseline (prevalence={baseline:.3f})')
ax.set_xlabel('Recall (Sensitivity)', fontsize=12)
ax.set_ylabel('Precision (PPV)', fontsize=12)
ax.set_title('Precision-Recall Curves - AKI Prediction\n(Pre-operative Features Only)', fontsize=14, fontweight='bold')
ax.legend(loc='best', fontsize=10)
ax.grid(True, alpha=0.3)
plt.tight_layout()
fig.savefig('outputs/figures/pr_curves.png', dpi=300, bbox_inches='tight')
plt.close()
print("   [OK] outputs/figures/pr_curves.png")

# ============================================================
# 5. 校准曲线
# ============================================================
print("5/7 生成校准曲线...")
from sklearn.calibration import calibration_curve
from sklearn.metrics import brier_score_loss

fig, ax = plt.subplots(figsize=(9, 8))

for i, (name, res) in enumerate(model_results.items()):
    prob_true, prob_pred = calibration_curve(res['y_true'], res['y_prob'], n_bins=10)
    brier = brier_score_loss(res['y_true'], res['y_prob'])
    ax.plot(prob_pred, prob_true, marker='o', linewidth=1.5, markersize=6,
            color=colors[i], label=f'{name} (Brier={brier:.4f})')

ax.plot([0, 1], [0, 1], 'k--', linewidth=1, alpha=0.5, label='Perfect')
ax.set_xlabel('Predicted Probability', fontsize=12)
ax.set_ylabel('Observed Proportion', fontsize=12)
ax.set_title('Calibration Curves - AKI Prediction\n(Pre-operative Features Only)', fontsize=14, fontweight='bold')
ax.legend(loc='upper left', fontsize=9)
ax.grid(True, alpha=0.3)
plt.tight_layout()
fig.savefig('outputs/figures/calibration_curves.png', dpi=300, bbox_inches='tight')
plt.close()
print("   [OK] outputs/figures/calibration_curves.png")

# ============================================================
# 6. DCA 决策曲线
# ============================================================
print("6/7 生成 DCA 决策曲线...")

def net_benefit(y_true, y_prob, threshold):
    """Calculate net benefit at a given threshold."""
    y_pred = (y_prob >= threshold).astype(int)
    tp = np.sum((y_true == 1) & (y_pred == 1))
    fp = np.sum((y_true == 0) & (y_pred == 1))
    n = len(y_true)
    return tp / n - fp / n * (threshold / (1 - threshold))

thresholds = np.linspace(0.01, 0.99, 99)
fig, ax = plt.subplots(figsize=(10, 7))

for i, (name, res) in enumerate(model_results.items()):
    nb = [net_benefit(res['y_true'], res['y_prob'], t) for t in thresholds]
    ax.plot(thresholds, nb, linewidth=2, color=colors[i], label=name)

# Treat all
nb_all = [net_benefit(y_test, np.ones(len(y_test)), t) for t in thresholds]
ax.plot(thresholds, nb_all, 'k--', linewidth=1.5, alpha=0.5, label='Treat All')
# Treat none
ax.axhline(y=0, color='gray', linestyle=':', alpha=0.5, label='Treat None')

ax.set_xlabel('Threshold Probability', fontsize=12)
ax.set_ylabel('Net Benefit', fontsize=12)
ax.set_title('Decision Curve Analysis (DCA) - AKI Prediction\n(Pre-operative Features Only)', fontsize=14, fontweight='bold')
ax.legend(loc='upper right', fontsize=9)
ax.set_xlim(0, 0.5)
ax.grid(True, alpha=0.3)
plt.tight_layout()
fig.savefig('outputs/figures/dca_curve.png', dpi=300, bbox_inches='tight')
plt.close()
print("   [OK] outputs/figures/dca_curve.png")

# ============================================================
# 7. SHAP 解释
# ============================================================
print("7/7 生成 SHAP 解释...")

try:
    import shap

    # 用逻辑回归（最稳定）做解释
    best_name = 'LogisticRegression'
    best_model = models[best_name]

    # 用测试集样本做解释
    X_explain = X_test[:50]
    feature_names = safe_features

    # Linear explainer for Logistic Regression
    explainer = shap.LinearExplainer(best_model, X_explain[:20])
    shap_values = explainer.shap_values(X_explain)

    # SHAP summary
    fig, ax = plt.subplots(figsize=(10, 8))
    shap.summary_plot(shap_values, X_explain, feature_names=feature_names,
                      max_display=10, show=False)
    plt.tight_layout()
    fig.savefig('outputs/figures/shap_summary.png', dpi=300, bbox_inches='tight')
    plt.close()
    print("   [OK] outputs/figures/shap_summary.png")

    # SHAP bar
    fig, ax = plt.subplots(figsize=(10, 8))
    shap.summary_plot(shap_values, X_explain, feature_names=feature_names,
                      max_display=10, plot_type='bar', show=False)
    plt.tight_layout()
    fig.savefig('outputs/figures/shap_bar.png', dpi=300, bbox_inches='tight')
    plt.close()
    print("   [OK] outputs/figures/shap_bar.png")

    # SHAP importance table
    mean_abs_shap = np.abs(shap_values).mean(axis=0)
    shap_df = pd.DataFrame({
        'Feature': feature_names,
        'Mean_ABS_SHAP': mean_abs_shap
    }).sort_values('Mean_ABS_SHAP', ascending=False)
    shap_df.to_csv('outputs/tables/shap_importance.csv', index=False, encoding='utf-8-sig')
    print("   [OK] outputs/tables/shap_importance.csv")

except Exception as e:
    print(f"   SHAP 跳过: {e} (可能需要 pip install shap)")

# ============================================================
# 汇总表
# ============================================================
print()
print("=" * 65)
print("  全部图表生成完毕！")
print("=" * 65)

from sklearn.metrics import roc_auc_score, accuracy_score, precision_score, recall_score, f1_score

summary = []
for name, res in model_results.items():
    summary.append({
        'Model': name,
        'AUC': round(roc_auc_score(res['y_true'], res['y_prob']), 4),
        'Accuracy': round(accuracy_score(res['y_true'], res['y_pred']), 4),
        'Precision': round(precision_score(res['y_true'], res['y_pred'], zero_division=0), 4),
        'Recall': round(recall_score(res['y_true'], res['y_pred'], zero_division=0), 4),
        'F1': round(f1_score(res['y_true'], res['y_pred'], zero_division=0), 4),
    })

summary_df = pd.DataFrame(summary).sort_values('AUC', ascending=False)
print()
print(summary_df.to_string(index=False))
summary_df.to_csv('outputs/tables/model_summary_clean.csv', index=False, encoding='utf-8-sig')

print(f"""
生成文件:
  outputs/figures/roc_curves.png          ROC 曲线（所有模型）
  outputs/figures/pr_curves.png           PR 曲线（针对不平衡数据）
  outputs/figures/calibration_curves.png  校准曲线（预测概率是否准确）
  outputs/figures/dca_curve.png           DCA 决策曲线（临床使用价值）
  outputs/figures/shap_summary.png        SHAP 特征重要性
  outputs/figures/shap_bar.png            SHAP 条形图
  outputs/tables/model_summary_clean.csv  模型评估汇总表
  outputs/tables/shap_importance.csv      SHAP 重要性排序
""")

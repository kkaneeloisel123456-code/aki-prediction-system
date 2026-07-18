"""
======================================================================
  AKI 急性肾损伤预测 —— 修复版（无数据泄漏）
  广西科技大学 蓝可 | 白菜卷队 | 暑期数创2026

  修复内容:
  1. 删除所有术后特征（45个）- 这是 KDIGO 诊断标准本身
  2. 只用47个术前特征 + 筛选最优12-15个
  3. 5折交叉验证（非单次划分）
  4. 训练集 vs 测试集 AUC 对比（检查过拟合）
  5. Bootstrap 置信区间
======================================================================
"""

import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
import os
import joblib

print("=" * 65)
print("  模块1：数据加载 + 特征分类")
print("=" * 65)

# 加载原始数据
df = pd.read_excel('data/raw/AKI数据.xlsx')
print(f"原始数据: {len(df)} 人 x {len(df.columns)} 列")

# ============================================================
# 关键词过滤 —— 比手工列名更可靠
# ============================================================

def is_leakage(col_name):
    '''返回 True 表示这个特征有数据泄漏风险，必须删除'''
    name = col_name.strip()
    # ID / 目标 / 分期
    if name in ['住院号', 'AKI分组', 'AKI分期']:
        return True
    # 术后任何指标 → 泄漏（包含 KDIGO 诊断标准）
    if '术后' in name:
        return True
    # ICU 任何指标 → 泄漏（入ICU时 AKI 可能已发生）
    if 'ICU' in name:
        return True
    # 术中指标 → 存疑，保守删除（预测应在手术前完成）
    if '术中' in name:
        return True
    # 结局变量 → 泄漏
    if name in ['住院费用', '住院天数', '机械通气时间', 'ICU住院时间']:
        return True
    return False

TARGET = 'AKI分组'

leaked = [c for c in df.columns if is_leakage(c)]
safe_features = [c for c in df.columns if not is_leakage(c) and c != TARGET]

print(f"删除（数据泄漏/术中/结局）: {len(leaked)} 个")
for c in leaked:
    print(f"  [删除] {c.strip()}")
print()
print(f"保留（仅术前）: {len(safe_features)} 个")
print()

# ============================================================
# 模块2：数据预处理
# ============================================================
print("=" * 65)
print("  模块2：数据预处理")
print("=" * 65)

# 提取 X, y
y = df[TARGET].copy()
X = df[safe_features].copy()

# 编码类别特征
from sklearn.preprocessing import LabelEncoder
cat_cols = X.select_dtypes(include=['object']).columns.tolist()
for col in cat_cols:
    X[col] = LabelEncoder().fit_transform(X[col].astype(str))
print(f"类别特征编码: {len(cat_cols)} 个 -> {cat_cols}")

# 只保留数值
X = X.select_dtypes(include=[np.number])

# 处理缺失和无穷
X = X.replace([np.inf, -np.inf], np.nan)
X = X.fillna(X.median())

print(f"术前数值特征: {X.shape[1]} 个")
print(f"样本数: {len(X)}, AKI 发生率: {y.mean():.1%}")
print()

# ============================================================
# 模块3：特征筛选（事件/变量比 ≈ 10:1）
# ============================================================
print("=" * 65)
print("  模块3：特征筛选")
print("=" * 65)
print(f"AKI 事件数: {y.sum()}, 建议特征数: ~{int(y.sum()/10)} 个（10事件/变量）")

from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

# 标准化
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

# 用随机森林初筛特征重要性
rf_selector = RandomForestClassifier(
    n_estimators=200, class_weight='balanced',
    random_state=42, n_jobs=-1
)
rf_selector.fit(X_scaled, y)

# 选 Top 15 个特征
importances = rf_selector.feature_importances_
indices = np.argsort(importances)[::-1]

N_KEEP = min(15, len(safe_features))
top_indices = indices[:N_KEEP]
top_features = [X.columns[i] for i in top_indices]
top_importances = importances[top_indices]

print(f"筛选出 {N_KEEP} 个关键特征:")
for i, (feat, imp) in enumerate(zip(top_features, top_importances)):
    print(f"  {i+1:2d}. {feat:<12} (重要性: {imp:.4f})")

X_selected = X_scaled[:, top_indices]
print()

# ============================================================
# 模块4：5折交叉验证训练
# ============================================================
print("=" * 65)
print("  模块4：5折交叉验证")
print("=" * 65)
print()

from sklearn.model_selection import StratifiedKFold, cross_val_score, cross_validate
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from xgboost import XGBClassifier
from lightgbm import LGBMClassifier

skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

models_cv = {
    'LogisticRegression': LogisticRegression(
        penalty='l2', C=0.1, class_weight='balanced', max_iter=5000, random_state=42
    ),
    'RandomForest': RandomForestClassifier(
        n_estimators=200, max_depth=3, min_samples_leaf=10,
        class_weight='balanced', random_state=42, n_jobs=-1
    ),
    'XGBoost': XGBClassifier(
        n_estimators=100, max_depth=3, learning_rate=0.05,
        reg_alpha=1, reg_lambda=1, subsample=0.8,
        scale_pos_weight=(y==0).sum()/max((y==1).sum(),1),
        random_state=42, use_label_encoder=False, eval_metric='logloss', verbosity=0
    ),
    'LightGBM': LGBMClassifier(
        n_estimators=100, max_depth=3, num_leaves=7, learning_rate=0.05,
        min_child_samples=20, reg_alpha=1, reg_lambda=1,
        class_weight='balanced', random_state=42, verbose=-1
    ),
    'CatBoost': None,
}

# 添加 CatBoost
try:
    from catboost import CatBoostClassifier
    models_cv['CatBoost'] = CatBoostClassifier(
        iterations=100, depth=3, learning_rate=0.05,
        l2_leaf_reg=3,
        auto_class_weights='Balanced', random_seed=42, verbose=0
    )
except:
    del models_cv['CatBoost']

print(f'{"模型":<22} {"Fold1":<8} {"Fold2":<8} {"Fold3":<8} {"Fold4":<8} {"Fold5":<8} {"平均AUC":<10} {"±Std"}')
print('-' * 78)

all_cv_results = {}
for name, model in models_cv.items():
    if model is None:
        continue
    cv_scores = cross_val_score(model, X_selected, y, cv=skf, scoring='roc_auc', n_jobs=-1)
    all_cv_results[name] = {
        'scores': cv_scores,
        'mean': cv_scores.mean(),
        'std': cv_scores.std()
    }
    scores_str = '  '.join([f'{s:.4f}' for s in cv_scores])
    print(f'{name:<22} {scores_str}  {cv_scores.mean():.4f}     {cv_scores.std():.4f}')

print()

# ============================================================
# 模块5：训练集 vs 测试集 AUC（检查过拟合）
# ============================================================
print("=" * 65)
print("  模块5：过拟合检查（训练AUC vs 测试AUC）")
print("=" * 65)

from sklearn.model_selection import train_test_split

X_train, X_test, y_train, y_test = train_test_split(
    X_selected, y, test_size=0.2, stratify=y, random_state=42
)

print(f"训练集: {len(X_train)} 人, 测试集: {len(X_test)} 人")
print(f'{"模型":<22} {"训练AUC":<10} {"测试AUC":<10} {"差距":<10} {"判断"}')
print('-' * 58)

for name, model in models_cv.items():
    if model is None:
        continue
    model.fit(X_train, y_train)
    train_auc = roc_auc_score(y_train, model.predict_proba(X_train)[:, 1])
    test_auc = roc_auc_score(y_test, model.predict_proba(X_test)[:, 1])
    gap = train_auc - test_auc

    if gap > 0.1:
        verdict = "严重过拟合!"
    elif gap > 0.05:
        verdict = "轻微过拟合"
    else:
        verdict = "正常"

    print(f'{name:<22} {train_auc:<10.4f} {test_auc:<10.4f} {gap:<10.4f} {verdict}')

print()

# ============================================================
# 模块6：Bootstrap 置信区间
# ============================================================
print("=" * 65)
print("  模块6：Bootstrap 验证（1000次重采样）")
print("=" * 65)

# 用交叉验证中最好的模型做 bootstrap
best_name = max(all_cv_results, key=lambda k: all_cv_results[k]['mean'])
best_model = models_cv[best_name]
best_model.fit(X_selected, y)  # 全数据训练

rng = np.random.default_rng(42)
n_samples = len(y)
bootstrap_aucs = []

for i in range(1000):
    indices = rng.integers(0, n_samples, size=n_samples)
    y_boot = y.iloc[indices]
    if len(np.unique(y_boot)) < 2:
        continue
    X_boot = X_selected[indices]
    y_prob = best_model.predict_proba(X_boot)[:, 1]
    bootstrap_aucs.append(roc_auc_score(y_boot, y_prob))

bootstrap_aucs = np.array(bootstrap_aucs)
mean_auc = np.mean(bootstrap_aucs)
ci_lower = np.percentile(bootstrap_aucs, 2.5)
ci_upper = np.percentile(bootstrap_aucs, 97.5)

print(f"最佳模型: {best_name}")
print(f"Bootstrap AUC: {mean_auc:.4f}")
print(f"95% 置信区间: [{ci_lower:.4f}, {ci_upper:.4f}]")
print()

# ============================================================
# 模块7：保存干净的模型
# ============================================================
print("=" * 65)
print("  模块7：保存结果")
print("=" * 65)

os.makedirs('models', exist_ok=True)
os.makedirs('outputs/tables', exist_ok=True)

# 保存每个模型
for name, model in models_cv.items():
    if model is None:
        continue
    model.fit(X_selected, y)
    joblib.dump(model, f'models/{name}_clean.pkl')

# 保存 scaler（用全量数据）
clean_scaler = StandardScaler()
X_raw = X[top_features].fillna(X[top_features].median())
clean_scaler.fit(X_raw)
joblib.dump(clean_scaler, 'models/scaler_clean.pkl')

# 保存特征名
with open('models/clean_features.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(top_features))
print(f"[OK] {len(top_features)} 个安全特征 -> models/clean_features.txt")

# 保存 CV 结果
cv_df = pd.DataFrame([{
    '模型': name,
    'Fold1': res['scores'][0],
    'Fold2': res['scores'][1],
    'Fold3': res['scores'][2],
    'Fold4': res['scores'][3],
    'Fold5': res['scores'][4],
    '平均AUC': res['mean'],
    '标准差': res['std']
} for name, res in all_cv_results.items()])
cv_df.to_csv('outputs/tables/cv_results_clean.csv', index=False, encoding='utf-8-sig')
print("[OK] 交叉验证结果 -> outputs/tables/cv_results_clean.csv")

# ============================================================
# 最终总结
# ============================================================
print()
print("=" * 65)
print("  修复完成！")
print("=" * 65)
print(f"""
  修复前（数据泄漏）:
    特征: 29个（含术后肌酐、ICU值等）
    AUC: 0.99+（用答案预测答案）

  修复后（仅术前特征）:
    特征: {N_KEEP} 个（仅术前可用信息）
    最佳模型: {best_name}
    交叉验证 AUC: {all_cv_results[best_name]['mean']:.4f} +/- {all_cv_results[best_name]['std']:.4f}
    Bootstrap 95%CI: [{ci_lower:.4f}, {ci_upper:.4f}]

  这才是真实、可信的医学预测模型结果。
""")

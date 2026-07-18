"""
======================================================================
  AKI 急性肾损伤预测 —— 一键运行脚本
  广西科技大学 蓝可 | 白菜卷队 | 暑期数创2026
======================================================================

  这个文件会从数据开始，一步一步走到模型结果。
  你只需要在终端输入：
      python run_me.py

  每一步都有中文说明，跑完你就完全懂了。
  参考：去年一等奖作品的"代码模块+文字说明"格式
======================================================================
"""

import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
import os
import joblib

print("=" * 65)
print("  模块1：环境准备")
print("=" * 65)
print()
print("加载需要用到的 Python 库（sklearn, xgboost, lightgbm, catboost 等）")
print("如果某个库缺失，运行: pip install -r requirements.txt")

from sklearn.model_selection import train_test_split, RandomizedSearchCV
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import (
    roc_auc_score, accuracy_score, precision_score, recall_score, f1_score,
    confusion_matrix
)

# ======================================================================
# 模块1结束。这些 import 就是"工具箱"，后面训练、评估都要用到。
# ======================================================================

print("[OK] 环境准备完成")
print()

# ======================================================================
print("=" * 65)
print("  模块2：数据加载")
print("=" * 65)
print()
print("读取清洗后的数据（420个病人，96列原始特征）")
print("数据来源: data/processed/aki_cleaned_*.csv")
print("清洗步骤在 src/data/cleaning.py 中完成，包括：")
print("  - 缺失值填补")
print("  - 异常值处理")
print("  - 标准化（均值0，标准差1）")
print()

# 找到最新的清洗数据文件
files = sorted([f for f in os.listdir('data/processed') if f.endswith('.csv')])
data_file = f'data/processed/{files[-1]}'
print(f"使用文件: {data_file}")

df = pd.read_csv(data_file)
print(f"数据形状: {df.shape[0]} 个病人 × {df.shape[1]} 列")
print(f"AKI发生率: {df['AKI分组'].mean():.1%} (125/420)")
print()
print("[OK] 数据加载完成")
print()

# ======================================================================
print("=" * 65)
print("  模块3：特征准备")
print("=" * 65)
print()
print("这一步做三件事：")
print("  1. 分离特征(X)和标签(y)")
print("  2. 把文字特征转数字（如 '手术类型' -> 0,1,2...）")
print("  3. 从94个特征中选出最关键的29个")
print("  4. 用StandardScaler统一尺度")
print("  5. 80%训练 / 20%测试 分层划分")
print()

# 分离
target = 'AKI分组'
y = df[target]
drop_cols = [target]
if 'AKI分期' in df.columns:
    drop_cols.append('AKI分期')
X_all = df.drop(columns=drop_cols)

# 编码
if '手术类型' in X_all.columns:
    le = LabelEncoder()
    X_all['手术类型'] = le.fit_transform(X_all['手术类型'].astype(str))
    print(f"  手术类型编码: {dict(zip(le.classes_, range(len(le.classes_))))}")

X_all = X_all.select_dtypes(include=[np.number])
print(f"  数值特征: {X_all.shape[1]} 个")

# 特征选择
with open('outputs/tables/final_feature_list.txt', 'r', encoding='utf-8') as f:
    selected_features = [l.strip() for l in f if l.strip()]

X = X_all[selected_features].fillna(X_all[selected_features].median())
print(f"  选出的关键特征: {len(selected_features)} 个")
print(f"  特征名: {selected_features}")

# 标准化
scaler = StandardScaler()
X_scaled_array = scaler.fit_transform(X)
X_scaled = pd.DataFrame(X_scaled_array, columns=selected_features)
print(f"  标准化后: 均值≈0, 标准差≈1")

# 划分
X_train, X_test, y_train, y_test = train_test_split(
    X_scaled, y, test_size=0.2, stratify=y, random_state=42
)
print(f"  训练集: {len(X_train)} 个样本 (AKI占比 {y_train.mean():.1%})")
print(f"  测试集: {len(X_test)} 个样本 (AKI占比 {y_test.mean():.1%})")
print()
print("[OK] 特征准备完成")
print()

# ======================================================================
print("=" * 65)
print("  模块4：模型训练")
print("=" * 65)
print()
print("训练8个模型，每个都用 RandomizedSearchCV 调参")
print("评估指标: ROC-AUC（越大越好，1.0=完美，0.5=瞎猜）")
print()

models_to_train = {}

# --- 4.1 逻辑回归 ---
print("--- 4.1 逻辑回归 (Logistic Regression) ---")
print("最简单的线性模型，最大优势是可以看每个特征的影响方向")
from sklearn.linear_model import LogisticRegression
lr = LogisticRegression(penalty='l2', class_weight='balanced', max_iter=5000, random_state=42)
lr_cv = RandomizedSearchCV(lr, {'C': [0.001, 0.01, 0.1, 1, 10, 100]},
                           cv=5, scoring='roc_auc', n_iter=20, random_state=42, n_jobs=-1)
lr_cv.fit(X_train, y_train)
models_to_train['LogisticRegression'] = lr_cv.best_estimator_
print(f" 最佳C={lr_cv.best_params_['C']}, 交叉验证AUC={lr_cv.best_score_:.4f}")

# --- 4.2 随机森林 ---
print("--- 4.2 随机森林 (Random Forest) ---")
print("多棵决策树投票，每棵树随机选部分特征，防止过拟合")
from sklearn.ensemble import RandomForestClassifier
rf = RandomForestClassifier(class_weight='balanced', random_state=42, n_jobs=-1)
rf_params = {'n_estimators': [100, 200, 300], 'max_depth': [3, 5, 7, 10, None],
             'min_samples_split': [2, 5, 10]}
rf_cv = RandomizedSearchCV(rf, rf_params, cv=5, scoring='roc_auc',
                           n_iter=20, random_state=42, n_jobs=-1)
rf_cv.fit(X_train, y_train)
models_to_train['RandomForest'] = rf_cv.best_estimator_
print(f" 最佳参数={rf_cv.best_params_}, 交叉验证AUC={rf_cv.best_score_:.4f}")

# --- 4.3 XGBoost ---
print("--- 4.3 XGBoost ---")
print("经典梯度提升树，kaggle比赛常胜将军")
from xgboost import XGBClassifier
scale = (y_train == 0).sum() / max((y_train == 1).sum(), 1)
xgb = XGBClassifier(scale_pos_weight=scale, random_state=42, use_label_encoder=False,
                     eval_metric='logloss', verbosity=0)
xgb_params = {'n_estimators': [100, 200, 300], 'max_depth': [3, 5, 7],
              'learning_rate': [0.01, 0.05, 0.1], 'subsample': [0.8, 1.0]}
xgb_cv = RandomizedSearchCV(xgb, xgb_params, cv=5, scoring='roc_auc',
                            n_iter=20, random_state=42, n_jobs=-1)
xgb_cv.fit(X_train, y_train)
models_to_train['XGBoost'] = xgb_cv.best_estimator_
print(f" 最佳参数={xgb_cv.best_params_}, 交叉验证AUC={xgb_cv.best_score_:.4f}")

# --- 4.4 LightGBM ---
print("--- 4.4 LightGBM ---")
print("微软出的梯度提升，速度最快")
from lightgbm import LGBMClassifier
lgb = LGBMClassifier(class_weight='balanced', random_state=42, verbose=-1)
lgb_params = {'n_estimators': [100, 200, 300], 'max_depth': [3, 5, 7, -1],
              'learning_rate': [0.01, 0.05, 0.1], 'num_leaves': [15, 31, 63]}
lgb_cv = RandomizedSearchCV(lgb, lgb_params, cv=5, scoring='roc_auc',
                            n_iter=20, random_state=42, n_jobs=-1)
lgb_cv.fit(X_train, y_train)
models_to_train['LightGBM'] = lgb_cv.best_estimator_
print(f" 最佳参数={lgb_cv.best_params_}, 交叉验证AUC={lgb_cv.best_score_:.4f}")

# --- 4.5 CatBoost ---
print("--- 4.5 CatBoost ---")
print("Yandex出的梯度提升，处理类别特征最强")
from catboost import CatBoostClassifier
cb = CatBoostClassifier(auto_class_weights='Balanced', random_seed=42, verbose=0)
cb_params = {'iterations': [100, 200, 300], 'depth': [4, 6, 8],
             'learning_rate': [0.01, 0.05, 0.1]}
cb_cv = RandomizedSearchCV(cb, cb_params, cv=5, scoring='roc_auc',
                           n_iter=20, random_state=42, n_jobs=-1)
cb_cv.fit(X_train, y_train)
models_to_train['CatBoost'] = cb_cv.best_estimator_
print(f" 最佳参数={cb_cv.best_params_}, 交叉验证AUC={cb_cv.best_score_:.4f}")

# --- 4.6 ExtraTrees ---
print("--- 4.6 ExtraTrees (极端随机树) ---")
print("像随机森林但分裂点完全随机，更不容易过拟合")
from sklearn.ensemble import ExtraTreesClassifier
et = ExtraTreesClassifier(class_weight='balanced', random_state=42, n_jobs=-1)
et_params = {'n_estimators': [100, 200, 300], 'max_depth': [5, 7, 10, None],
             'min_samples_split': [2, 5]}
et_cv = RandomizedSearchCV(et, et_params, cv=5, scoring='roc_auc',
                           n_iter=20, random_state=42, n_jobs=-1)
et_cv.fit(X_train, y_train)
models_to_train['ExtraTrees'] = et_cv.best_estimator_
print(f" 最佳参数={et_cv.best_params_}, 交叉验证AUC={et_cv.best_score_:.4f}")

# --- 4.7 MLP (神经网络) ---
print("--- 4.7 MLP (多层感知机 / 神经网络) ---")
print("简单的深度学习模型")
from sklearn.neural_network import MLPClassifier
mlp = MLPClassifier(hidden_layer_sizes=(128, 64), early_stopping=True,
                    max_iter=2000, random_state=42)
mlp_params = {'hidden_layer_sizes': [(64, 32), (128, 64), (256, 128)],
              'alpha': [0.0001, 0.001, 0.01], 'learning_rate_init': [0.001, 0.01]}
mlp_cv = RandomizedSearchCV(mlp, mlp_params, cv=3, scoring='roc_auc',
                            n_iter=10, random_state=42, n_jobs=-1)
mlp_cv.fit(X_train, y_train)
models_to_train['MLP'] = mlp_cv.best_estimator_
print(f" 最佳参数={mlp_cv.best_params_}, 交叉验证AUC={mlp_cv.best_score_:.4f}")

# --- 4.8 TabNet ---
print("--- 4.8 TabNet ---")
print("Google提出的注意力机制深度学习，能自动选特征")
try:
    from pytorch_tabnet.tab_model import TabNetClassifier
    tabnet = TabNetClassifier(n_d=32, n_a=32, n_steps=5, verbose=0, seed=42)
    tabnet.fit(
        X_train.values, y_train.values,
        eval_set=[(X_test.values, y_test.values)],
        patience=20, max_epochs=100, batch_size=64
    )
    models_to_train['TabNet'] = tabnet
    print(f" TabNet训练完成")
except Exception as e:
    print(f" TabNet跳过（可能未安装）: {e}")

print()
print("[OK] 模型训练完成")
print()

# ======================================================================
print("=" * 65)
print("  模块5：模型评估")
print("=" * 65)
print()
print("在测试集上评估所有模型，6个指标：")
print("  AUC:       区分正负样本的能力（最重要）")
print("  Accuracy:  总正确率")
print("  Precision: 预测为阳性的样本中真的阳性的比例")
print("  Recall:    真的阳性中被正确找出的比例（不漏诊）")
print("  F1:        精确率和召回率的调和平均")
print("  特异性:    真的阴性中被正确找出的比例")
print()

results = []
for name, model in models_to_train.items():
    if name == 'TabNet':
        y_prob = model.predict_proba(X_test.values)[:, 1]
    else:
        y_prob = model.predict_proba(X_test)[:, 1]

    y_pred = (y_prob >= 0.5).astype(int)
    cm = confusion_matrix(y_test, y_pred)
    tn, fp, fn, tp = cm.ravel()

    result = {
        '模型': name,
        'AUC': round(roc_auc_score(y_test, y_prob), 4),
        'Accuracy': round(accuracy_score(y_test, y_pred), 4),
        'Precision': round(precision_score(y_test, y_pred, zero_division=0), 4),
        'Recall': round(recall_score(y_test, y_pred, zero_division=0), 4),
        'F1': round(f1_score(y_test, y_pred, zero_division=0), 4),
        '特异性': round(tn / (tn + fp) if (tn + fp) > 0 else 0, 4),
    }
    results.append(result)

result_df = pd.DataFrame(results).sort_values('AUC', ascending=False)
print(result_df.to_string(index=False))

# 找最佳模型
best = result_df.iloc[0]
print()
print(f">> 最佳模型: {best['模型']} (AUC={best['AUC']})")
print()

# ======================================================================
print("=" * 65)
print("  模块6：保存结果")
print("=" * 65)
print()

# 保存评估表
os.makedirs('outputs/tables', exist_ok=True)
result_df.to_csv('outputs/tables/model_results.csv', index=False, encoding='utf-8-sig')
print("[OK] 结果表 -> outputs/tables/model_results.csv")

# 保存模型和scaler
os.makedirs('models', exist_ok=True)
for name, model in models_to_train.items():
    if name == 'TabNet':
        model.save_model('models/TabNet')
    else:
        joblib.dump(model, f'models/{name}.pkl')

joblib.dump(scaler, 'models/scaler.pkl')
print("[OK] 模型和scaler -> models/")

# 保存特征名
with open('models/feature_names.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(selected_features))
print("[OK] 特征名 -> models/feature_names.txt")

print()
print("=" * 65)
print("  全部跑完！")
print("=" * 65)
print()
print(f"  数据:    420个病人 → 29个特征")
print(f"  模型:    训练了{len(models_to_train)}个")
print(f"  最佳:    {best['模型']} AUC={best['AUC']}")
print()
print("  启动Web应用: streamlit run web/app.py")
print()
print("  你现在完全理解了这个项目的流程！")

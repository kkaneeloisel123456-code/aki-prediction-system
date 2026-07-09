"""
AKI Prediction Project - Complete End-to-End Pipeline
Run this file to execute the entire pipeline from data to results.
"""
import sys, os, warnings, logging
warnings.filterwarnings('ignore')
logging.getLogger('matplotlib').setLevel(logging.ERROR)

sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split

# ============================================================
# Step 0: Setup
# ============================================================
print("=" * 70)
print("  AKI Prediction — Full Pipeline")
print("=" * 70)

OUTPUT_DIR = 'outputs'
MODEL_DIR = 'models'
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)

# ============================================================
# Step 1: Data Cleaning
# ============================================================
print("\n" + "=" * 70)
print("  STEP 1/5: Data Cleaning")
print("=" * 70)

from src.data.cleaning import run_full_cleaning_pipeline

cleaning_result = run_full_cleaning_pipeline(
    'data/raw/AKI数据.xlsx', 'data/processed/'
)
cleaned_path = cleaning_result.get('cleaned_file', None)
if cleaned_path is None:
    # Find the latest cleaned file
    import glob
    files = glob.glob('data/processed/aki_cleaned_*.csv')
    cleaned_path = sorted(files)[-1] if files else 'data/processed/aki_cleaned_20260708_161535.csv'

df = pd.read_csv(cleaned_path)
print(f"Loaded cleaned data: {df.shape}")

# ============================================================
# Step 2: EDA Analysis
# ============================================================
print("\n" + "=" * 70)
print("  STEP 2/5: Exploratory Data Analysis")
print("=" * 70)

from src.data.eda import run_full_eda

eda_results = run_full_eda(cleaned_path, OUTPUT_DIR)
print(f"EDA complete. AKI incidence: {eda_results.get('aki_incidence', 'N/A')}")

# ============================================================
# Step 3: Feature Engineering
# ============================================================
print("\n" + "=" * 70)
print("  STEP 3/5: Feature Engineering")
print("=" * 70)

from src.data.features import (
    run_full_feature_engineering, select_features_combined,
    encode_categorical_features, handle_imbalance
)
from sklearn.preprocessing import StandardScaler

target = 'AKI分组'

# Prepare data
if 'AKI分期' in df.columns:
    df_model = df.drop(columns=['AKI分期'])
else:
    df_model = df.copy()

y = df_model[target].copy()
X_all = df_model.drop(columns=[target])

# Encode categorical
categorical_cols = ['手术类型'] if '手术类型' in X_all.columns else []
if categorical_cols:
    X_all, encoders = encode_categorical_features(X_all, categorical_cols, method='label')
else:
    encoders = {}

# Keep only numeric
X_all = X_all.select_dtypes(include=[np.number])

# Feature selection
clinical_features = ['年龄', '术前Scr', '术前eGFR', 'APACHEII', '手术时间',
                      '术中尿量', '术中失血量', '高血压', '糖尿病']
selected_features, selection_summary = select_features_combined(
    X_all, y, clinical_features=clinical_features, random_state=42
)
print(f"Selected {len(selected_features)} features from {X_all.shape[1]}")

# Apply selection and scale
X_selected = X_all[selected_features].fillna(X_all[selected_features].median())
scaler = StandardScaler()
X_scaled = pd.DataFrame(scaler.fit_transform(X_selected), columns=selected_features)

# Save feature names
with open(f'{OUTPUT_DIR}/tables/final_feature_list.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(selected_features))

# ============================================================
# Step 4: Model Training (with all 8+ models)
# ============================================================
print("\n" + "=" * 70)
print("  STEP 4/5: Model Training & Evaluation")
print("=" * 70)

from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, brier_score_loss, confusion_matrix
)
import joblib

# Split BEFORE SMOTE (SMOTE only on training data)
X_train_raw, X_test, y_train_raw, y_test = train_test_split(
    X_scaled, y, test_size=0.2, random_state=42, stratify=y
)
print(f"Train: {X_train_raw.shape[0]}, Test: {X_test.shape[0]}")
print(f"Train AKI%: {y_train_raw.mean():.3f}, Test AKI%: {y_test.mean():.3f}")

# Apply SMOTE to training data only
X_train, y_train = handle_imbalance(
    X_train_raw, y_train_raw, method='smote', random_state=42
)

# ---- Train all models ----
all_models = {}
all_results = {}

# 1. Logistic Regression
print("\n--- Logistic Regression ---")
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import RandomizedSearchCV

lr = LogisticRegression(penalty='l2', class_weight='balanced', max_iter=5000, random_state=42)
lr_params = {'C': [0.01, 0.1, 1, 10, 100]}
lr_search = RandomizedSearchCV(lr, lr_params, cv=5, scoring='roc_auc', n_iter=20, random_state=42, n_jobs=-1)
lr_search.fit(X_train, y_train)
all_models['LogisticRegression'] = lr_search.best_estimator_
all_models['LogisticRegression'].fit(X_train, y_train)
print(f"  Best C={lr_search.best_params_['C']}, CV AUC={lr_search.best_score_:.4f}")

# 2. Random Forest
print("--- Random Forest ---")
from sklearn.ensemble import RandomForestClassifier
rf = RandomForestClassifier(class_weight='balanced', random_state=42, n_jobs=-1)
rf_params = {'n_estimators': [100, 200, 300], 'max_depth': [5, 7, 10, None], 'min_samples_split': [2, 5]}
rf_search = RandomizedSearchCV(rf, rf_params, cv=5, scoring='roc_auc', n_iter=20, random_state=42, n_jobs=-1)
rf_search.fit(X_train, y_train)
all_models['RandomForest'] = rf_search.best_estimator_
print(f"  Best params={rf_search.best_params_}, CV AUC={rf_search.best_score_:.4f}")

# 3. XGBoost
print("--- XGBoost ---")
try:
    from xgboost import XGBClassifier
    pos = y_train.sum()
    neg = len(y_train) - pos
    xgb = XGBClassifier(scale_pos_weight=neg/max(pos,1), random_state=42, use_label_encoder=False, eval_metric='logloss', verbosity=0)
    xgb_params = {'n_estimators': [100,200,300], 'max_depth': [3,5,7], 'learning_rate': [0.01,0.05,0.1], 'subsample': [0.8,1.0]}
    xgb_search = RandomizedSearchCV(xgb, xgb_params, cv=5, scoring='roc_auc', n_iter=20, random_state=42, n_jobs=-1)
    xgb_search.fit(X_train, y_train)
    all_models['XGBoost'] = xgb_search.best_estimator_
    print(f"  Best params={xgb_search.best_params_}, CV AUC={xgb_search.best_score_:.4f}")
except Exception as e:
    print(f"  XGBoost SKIPPED: {e}")

# 4. LightGBM
print("--- LightGBM ---")
try:
    from lightgbm import LGBMClassifier
    lgb = LGBMClassifier(class_weight='balanced', random_state=42, verbose=-1)
    lgb_params = {'n_estimators': [100,200,300], 'max_depth': [3,5,7,-1], 'learning_rate': [0.01,0.05,0.1], 'num_leaves': [15,31,63]}
    lgb_search = RandomizedSearchCV(lgb, lgb_params, cv=5, scoring='roc_auc', n_iter=20, random_state=42, n_jobs=-1)
    lgb_search.fit(X_train, y_train)
    all_models['LightGBM'] = lgb_search.best_estimator_
    print(f"  Best params={lgb_search.best_params_}, CV AUC={lgb_search.best_score_:.4f}")
except Exception as e:
    print(f"  LightGBM SKIPPED: {e}")

# 5. CatBoost
print("--- CatBoost ---")
try:
    from catboost import CatBoostClassifier
    cb = CatBoostClassifier(auto_class_weights='Balanced', random_seed=42, verbose=0)
    cb_params = {'iterations': [100,200,300], 'depth': [4,6,8], 'learning_rate': [0.01,0.05,0.1]}
    cb_search = RandomizedSearchCV(cb, cb_params, cv=5, scoring='roc_auc', n_iter=20, random_state=42, n_jobs=-1)
    cb_search.fit(X_train, y_train)
    all_models['CatBoost'] = cb_search.best_estimator_
    print(f"  Best params={cb_search.best_params_}, CV AUC={cb_search.best_score_:.4f}")
except Exception as e:
    print(f"  CatBoost SKIPPED: {e}")

# 6. ExtraTrees
print("--- ExtraTrees ---")
from sklearn.ensemble import ExtraTreesClassifier
et = ExtraTreesClassifier(class_weight='balanced', random_state=42, n_jobs=-1)
et_params = {'n_estimators': [100,200,300], 'max_depth': [5,7,10,None], 'min_samples_split': [2,5]}
et_search = RandomizedSearchCV(et, et_params, cv=5, scoring='roc_auc', n_iter=20, random_state=42, n_jobs=-1)
et_search.fit(X_train, y_train)
all_models['ExtraTrees'] = et_search.best_estimator_
print(f"  Best params={et_search.best_params_}, CV AUC={et_search.best_score_:.4f}")

# 7. MLP
print("--- MLP ---")
from sklearn.neural_network import MLPClassifier
mlp = MLPClassifier(hidden_layer_sizes=(128,64), early_stopping=True, max_iter=2000, random_state=42)
mlp_params = {'hidden_layer_sizes': [(64,32),(128,64),(256,128)], 'alpha': [0.0001,0.001,0.01], 'learning_rate_init': [0.001,0.01]}
mlp_search = RandomizedSearchCV(mlp, mlp_params, cv=3, scoring='roc_auc', n_iter=10, random_state=42, n_jobs=-1)
mlp_search.fit(X_train, y_train)
all_models['MLP'] = mlp_search.best_estimator_
print(f"  Best params={mlp_search.best_params_}, CV AUC={mlp_search.best_score_:.4f}")

# 8. TabNet (skip if not available)
print("--- TabNet ---")
try:
    from pytorch_tabnet.tab_model import TabNetClassifier
    tabnet = TabNetClassifier(n_d=32, n_a=32, n_steps=5, verbose=0, seed=42)
    tabnet.fit(X_train.values, y_train.values, eval_set=[(X_test.values, y_test.values)], patience=20, max_epochs=100, batch_size=64)
    all_models['TabNet'] = tabnet
    print(f"  TabNet trained successfully")
except Exception as e:
    print(f"  TabNet SKIPPED: {e}")

# ---- Evaluate all models ----
print("\n" + "=" * 70)
print("  Model Evaluation Results")
print("=" * 70)

eval_results = {}
for name, model in all_models.items():
    try:
        if name == 'TabNet':
            # TabNet requires numpy arrays
            X_eval = X_test.values
            y_prob = model.predict_proba(X_eval)[:, 1]
        elif hasattr(model, 'predict_proba'):
            y_prob = model.predict_proba(X_test)[:, 1]
        elif hasattr(model, 'predict'):
            y_prob = model.predict(X_test)
            if y_prob.ndim > 1:
                y_prob = y_prob[:, 1]
        else:
            continue

        y_pred = (y_prob >= 0.5).astype(int)

        auc = roc_auc_score(y_test, y_prob)
        acc = accuracy_score(y_test, y_pred)
        prec = precision_score(y_test, y_pred, zero_division=0)
        rec = recall_score(y_test, y_pred, zero_division=0)
        f1 = f1_score(y_test, y_pred, zero_division=0)
        brier = brier_score_loss(y_test, y_prob)
        tn, fp, fn, tp = confusion_matrix(y_test, y_pred).ravel()
        spec = tn / (tn + fp) if (tn + fp) > 0 else 0
        npv = tn / (tn + fn) if (tn + fn) > 0 else 0
        ppv = tp / (tp + fp) if (tp + fp) > 0 else 0

        eval_results[name] = {
            'y_true': y_test.values, 'y_prob': y_prob, 'y_pred': y_pred,
            'AUC': auc, 'Accuracy': acc, 'Precision': prec, 'Recall': rec,
            'F1': f1, 'Brier': brier, 'Specificity': spec, 'NPV': npv, 'PPV': ppv
        }

        print(f"{name:<22} AUC={auc:.4f}  F1={f1:.4f}  Brier={brier:.4f}  "
              f"Acc={acc:.4f}  Prec={prec:.4f}  Recall={rec:.4f}")

        # Save model
        if name == 'TabNet':
            model.save_model(f'{MODEL_DIR}/TabNet')
        else:
            joblib.dump(model, f'{MODEL_DIR}/{name}.pkl')

    except Exception as e:
        print(f"{name:<22} ERROR: {e}")

# Save evaluation table
eval_df = pd.DataFrame([{
    'Model': name,
    'AUC': r['AUC'], 'Accuracy': r['Accuracy'], 'Precision': r['Precision'],
    'Recall': r['Recall'], 'F1': r['F1'], 'Brier_Score': r['Brier'],
    'Specificity': r['Specificity'], 'NPV': r['NPV'], 'PPV': r['PPV']
} for name, r in eval_results.items()])
eval_df = eval_df.sort_values('AUC', ascending=False)
eval_df.to_csv(f'{OUTPUT_DIR}/tables/model_comparison.csv', index=False, encoding='utf-8-sig')
print(f"\nResults saved to {OUTPUT_DIR}/tables/model_comparison.csv")

# Save scaler and feature names for web app
joblib.dump(scaler, f'{MODEL_DIR}/scaler.pkl')
with open(f'{MODEL_DIR}/feature_names.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(selected_features))
print(f"Scaler & features saved to {MODEL_DIR}/")

# ============================================================
# Step 5: Generate All Evaluation Plots
# ============================================================
print("\n" + "=" * 70)
print("  STEP 5/5: Visualization & Reports")
print("=" * 70)

from src.models.evaluate import (
    plot_roc_curves, plot_pr_curves, plot_confusion_matrices,
    plot_calibration_curves, create_model_comparison_table
)
from src.models.calibration import (
    plot_calibration_curves_all as plot_cal_all,
    plot_decision_curve, plot_clinical_impact_curve,
    create_calibration_summary, analyze_risk_groups
)

# Prepare data for evaluation plots
model_results_dict = {}
for name, r in eval_results.items():
    model_results_dict[name] = {
        'y_true': r['y_true'],
        'y_prob': r['y_prob'],
        'y_pred': r['y_pred']
    }

# ROC curves
print("\nGenerating ROC curves...")
try:
    plot_roc_curves(model_results_dict, save_path='outputs/figures/roc_curves.png')
    print("  ROC curves saved")
except Exception as e:
    print(f"  ROC failed: {e}")

# PR curves
print("Generating PR curves...")
try:
    plot_pr_curves(model_results_dict, save_path='outputs/figures/pr_curves.png')
    print("  PR curves saved")
except Exception as e:
    print(f"  PR failed: {e}")

# Confusion matrices
print("Generating confusion matrices...")
try:
    plot_confusion_matrices(model_results_dict, save_path='outputs/figures/confusion_matrices.png')
    print("  Confusion matrices saved")
except Exception as e:
    print(f"  CM failed: {e}")

# Calibration curves
print("Generating calibration curves...")
try:
    plot_cal_all(model_results_dict, save_name='calibration_curves.png')
    print("  Calibration curves saved")
except Exception as e:
    print(f"  Calibration failed: {e}")

# DCA
print("Generating DCA...")
try:
    model_probs_dict = {n: r['y_prob'] for n, r in eval_results.items()}
    plot_decision_curve(y_test.values, model_probs_dict, save_name='decision_curve.png')
    print("  DCA saved")
except Exception as e:
    print(f"  DCA failed: {e}")

# Best model clinical impact
best_model_name = eval_df.iloc[0]['Model']
print(f"\nBest model: {best_model_name} (AUC={eval_df.iloc[0]['AUC']:.4f})")
try:
    plot_clinical_impact_curve(y_test.values, eval_results[best_model_name]['y_prob'],
                                save_name='clinical_impact_curve.png')
    print("  Clinical impact curve saved")
except Exception as e:
    print(f"  Clinical impact failed: {e}")

# Calibration summary & risk stratification
try:
    create_calibration_summary(model_results_dict, save_name='calibration_summary.csv')
    analyze_risk_groups(y_test.values, eval_results[best_model_name]['y_prob'],
                         save_name='risk_stratification.csv')
    print("  Calibration summary & risk stratification saved")
except Exception as e:
    print(f"  Summary failed: {e}")

# ============================================================
# Step 6: SHAP Analysis
# ============================================================
print("\n" + "=" * 70)
print("  BONUS: SHAP Analysis")
print("=" * 70)

try:
    import shap
    from src.visualization.shap_viz import (
        plot_shap_summary, plot_shap_bar, plot_shap_dependence,
        create_shap_importance_table, generate_clinical_interpretation,
        save_clinical_interpretation
    )

    best_model = all_models[best_model_name]

    # Determine model type for SHAP
    if best_model_name in ['XGBoost', 'LightGBM', 'CatBoost', 'RandomForest', 'ExtraTrees']:
        model_type = 'tree'
    elif best_model_name == 'LogisticRegression':
        model_type = 'linear'
    else:
        model_type = 'kernel'

    print(f"Computing SHAP for {best_model_name} (type={model_type})...")

    # Use a sample for explanation (SHAP is slow on large data)
    X_explain = X_test.iloc[:50] if len(X_test) > 50 else X_test

    if model_type == 'tree':
        explainer = shap.TreeExplainer(best_model)
        shap_values = explainer.shap_values(X_explain)
        if isinstance(shap_values, list):
            shap_values = shap_values[1]
    elif model_type == 'linear':
        explainer = shap.LinearExplainer(best_model, X_explain)
        shap_values = explainer.shap_values(X_explain)
    else:
        explainer = shap.KernelExplainer(best_model.predict_proba, shap.kmeans(X_explain, 20))
        shap_values = explainer.shap_values(X_explain)
        if isinstance(shap_values, list):
            shap_values = shap_values[1]

    # Generate SHAP plots
    plot_shap_summary(shap_values, X_explain, max_display=15, save_name='shap_summary.png')
    plot_shap_bar(shap_values, X_explain, max_display=15, save_name='shap_bar.png')
    plot_shap_dependence(shap_values, X_explain, list(X_explain.columns)[:5],
                         top_n=5, save_name='shap_dependence.png')

    # Feature importance
    importance_df = create_shap_importance_table(shap_values, X_explain,
                                                   save_name='shap_importance.csv')

    # Clinical interpretation
    clinical_notes = generate_clinical_interpretation(
        shap_values, X_explain, list(X_explain.columns), top_n=10
    )
    save_clinical_interpretation(clinical_notes, save_name='clinical_interpretation.md')

    print("  SHAP analysis complete!")

except Exception as e:
    print(f"  SHAP analysis failed (non-critical): {e}")
    import traceback
    traceback.print_exc()

# ============================================================
# Final Summary
# ============================================================
print("\n" + "=" * 70)
print("  PIPELINE COMPLETE!")
print("=" * 70)
print(f"""
Output files:
  - Cleaned data:        {cleaned_path}
  - Models:              {MODEL_DIR}/
  - Evaluation table:    {OUTPUT_DIR}/tables/model_comparison.csv
  - All figures:         {OUTPUT_DIR}/figures/
  - Feature list:        {OUTPUT_DIR}/tables/final_feature_list.txt
  - Data dictionary:     {OUTPUT_DIR}/tables/data_dictionary.csv
  - Risk stratification: {OUTPUT_DIR}/tables/risk_stratification.csv
  - SHAP importance:     {OUTPUT_DIR}/tables/shap_importance.csv
  - Clinical report:     {OUTPUT_DIR}/tables/clinical_interpretation.md

Best model: {best_model_name} (AUC = {eval_df.iloc[0]['AUC']:.4f})

To launch the web app:
    streamlit run web/app.py
""")

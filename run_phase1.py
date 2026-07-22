# -*- coding: utf-8 -*-
"""
======================================================================
  AKI 一等奖冲刺 —— Phase 1 核心评估管线
  广西科技大学 蓝可 | 白菜卷队 | 暑期数创 2026

  整合模块:
    1. 五折交叉验证 + 均值ROC置信带
    2. 模型消融实验
    3. DCA临床决策曲线
    4. SHAP分析 + 反事实解释
    5. 数据治理可视化
    6. Bootstrap AUC分布

  输出目录: outputs/phase1/
======================================================================
"""
import warnings
warnings.filterwarnings('ignore')

import os, sys, argparse
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier

# Model imports
try:
    from xgboost import XGBClassifier
    _XGB = True
except ImportError:
    _XGB = False

try:
    from lightgbm import LGBMClassifier
    _LGB = True
except ImportError:
    _LGB = False

try:
    from catboost import CatBoostClassifier
    _CB = True
except ImportError:
    _CB = False

# ---------------------------------------------------------------------------
# Output configuration
# ---------------------------------------------------------------------------
OUTPUT_DIR = str(PROJECT_ROOT / 'outputs' / 'phase1')
for d in [OUTPUT_DIR, f'{OUTPUT_DIR}/figures', f'{OUTPUT_DIR}/tables']:
    os.makedirs(d, exist_ok=True)

# ---------------------------------------------------------------------------
# Helper: Load and prepare data
# ---------------------------------------------------------------------------
def load_and_prepare_data():
    """Load AKI dataset and prepare features."""
    data_path = PROJECT_ROOT / 'data' / 'raw' / 'AKI数据.xlsx'
    if not data_path.exists():
        # Try alternate paths
        for alt in ['data/AKI数据.xlsx', 'data/AKI_data.xlsx']:
            alt_path = PROJECT_ROOT / alt
            if alt_path.exists():
                data_path = alt_path
                break
        else:
            raise FileNotFoundError("找不到AKI数据文件！请将数据放入 data/raw/AKI数据.xlsx")

    print(f"📂 加载数据: {data_path}")
    df = pd.read_excel(data_path)
    print(f"   原始数据: {df.shape[0]} 行 × {df.shape[1]} 列")

    # Target
    TARGET = 'AKI分组'
    if TARGET not in df.columns:
        raise ValueError(f"目标列 '{TARGET}' 不存在！可用列: {list(df.columns[:10])}...")

    # Exclude non-feature columns
    exclude_patterns = ['住院号', '姓名', 'ID', '编号']
    exclude_cols = [c for c in df.columns if any(p in c for p in exclude_patterns)]

    features = [c for c in df.columns if c not in exclude_cols and c != TARGET]
    y = df[TARGET].copy().astype(int)
    X = df[features].copy()

    # Handle categorical
    cat_cols = X.select_dtypes(include=['object']).columns.tolist()
    if cat_cols:
        print(f"   分类变量 ({len(cat_cols)}): {cat_cols}")
        X = pd.get_dummies(X, columns=cat_cols, drop_first=True)

    # Numeric only + fill missing
    X = X.select_dtypes(include=[np.number])
    X = X.replace([np.inf, -np.inf], np.nan)
    X = X.fillna(X.median())

    # Scale
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    feature_names = list(X.columns)

    print(f"   处理后: {X_scaled.shape[0]} 行 × {X_scaled.shape[1]} 列")
    print(f"   AKI发生率: {y.mean():.1%}")

    return X_scaled, y.values, feature_names, X, df


# ---------------------------------------------------------------------------
# 1. Cross-Validation Analysis
# ---------------------------------------------------------------------------
def run_cv_analysis(X, y, models_dict, feature_names):
    """Run 5-fold CV + Bootstrap AUC."""
    print("\n" + "=" * 70)
    print("📊 阶段 1/5: 交叉验证可信度分析")
    print("=" * 70)

    from src.models.cross_validate import run_full_cv_report
    results = run_full_cv_report(
        X, y, models_dict,
        n_splits=5, n_bootstrap=1000,
        output_dir=OUTPUT_DIR,
    )

    # Print key findings
    summary = results['summary_df']
    if not summary.empty:
        best_model = summary.iloc[0]
        print(f"\n  🏆 最佳模型: {best_model['模型 Model']}")
        print(f"     CV AUC = {best_model['CV AUC (均值)']:.4f} ± {best_model['CV AUC (标准差)']:.4f}")
        print(f"     Bootstrap 95% CI: [{best_model['95% CI 下限']:.4f}, {best_model['95% CI 上限']:.4f}]")

    return results


# ---------------------------------------------------------------------------
# 2. Ablation Study
# ---------------------------------------------------------------------------
def run_ablation_analysis(X, y, models_dict, feature_names):
    """Run feature ablation study."""
    print("\n" + "=" * 70)
    print("🔬 阶段 2/5: 消融实验分析")
    print("=" * 70)

    from src.models.ablation import run_full_ablation_report, auto_discover_feature_groups

    feature_groups = auto_discover_feature_groups(feature_names)

    results = run_full_ablation_report(
        X, y, models_dict, feature_names,
        feature_groups=feature_groups,
        cv=5, output_dir=OUTPUT_DIR,
    )

    return results


# ---------------------------------------------------------------------------
# 3. DCA Analysis
# ---------------------------------------------------------------------------
def run_dca_analysis(X, y, models_dict):
    """Run DCA + Calibration analysis."""
    print("\n" + "=" * 70)
    print("📈 阶段 3/5: DCA临床决策曲线分析")
    print("=" * 70)

    from src.models.calibration import (
        run_full_calibration_analysis,
        plot_decision_curve,
        plot_calibration_curves_overlay,
    )
    from sklearn.model_selection import train_test_split

    # Split data to get predictions
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )

    # Train models and get probabilities
    from sklearn.base import clone
    model_results_dict = {}
    for name, model in models_dict.items():
        try:
            model_clone = clone(model)
            model_clone.fit(X_train, y_train)
            if hasattr(model_clone, "predict_proba"):
                y_prob = model_clone.predict_proba(X_test)[:, 1]
            else:
                y_prob = model_clone.decision_function(X_test)
                y_prob = (y_prob - y_prob.min()) / max(y_prob.max() - y_prob.min(), 1e-10)
            y_pred = (y_prob >= 0.5).astype(int)
            model_results_dict[name] = {
                'y_true': y_test,
                'y_pred': y_pred,
                'y_prob': y_prob,
            }
        except Exception as e:
            print(f"  [WARN] {name} failed: {e}")

    # Run calibration pipeline
    cal_results = run_full_calibration_analysis(model_results_dict)

    # Also generate standalone DCA
    model_probs = {name: r['y_prob'] for name, r in model_results_dict.items()}
    fig_dca, _ = plot_decision_curve(
        y_test, model_probs,
        save_name=str(Path(OUTPUT_DIR) / 'figures' / 'dca_decision_curve.png'),
        show_ci=True,
    )
    import matplotlib.pyplot as plt
    plt.close(fig_dca)

    return cal_results


# ---------------------------------------------------------------------------
# 4. SHAP Analysis
# ---------------------------------------------------------------------------
def run_shap_analysis(X, y, models_dict, feature_names):
    """Run SHAP + counterfactual analysis."""
    print("\n" + "=" * 70)
    print("🧠 阶段 4/5: SHAP可解释性分析")
    print("=" * 70)

    import shap
    from src.visualization.shap_viz import (
        run_full_shap_analysis,
        compute_counterfactual_report,
        print_counterfactual_report,
    )

    # Use best model (first in dict) for SHAP
    best_name = list(models_dict.keys())[0]
    best_model = models_dict[best_name]
    X_df = pd.DataFrame(X, columns=feature_names)

    # Fit model
    from sklearn.base import clone
    best_model = clone(best_model)
    best_model.fit(X, y)

    # Determine model type for SHAP
    model_type = 'tree'
    if best_name == 'LogisticRegression':
        model_type = 'linear'

    # Run full SHAP
    shap_results = run_full_shap_analysis(
        best_model, X_df, y,
        model_type=model_type,
        feature_names=feature_names,
        top_n=15,
        patient_index=0,
    )

    # Counterfactual analysis
    if shap_results is not None and shap_results['shap_values'] is not None:
        print("\n--- 反事实解释 ---")
        cf_report = compute_counterfactual_report(
            best_model, X_df,
            shap_results['shap_values'],
            feature_names,
            patient_idx=0, top_n=5,
        )
        print_counterfactual_report(cf_report)

    return shap_results


# ---------------------------------------------------------------------------
# 5. Data Governance Visualization
# ---------------------------------------------------------------------------
def run_data_gov_visualization(df_raw):
    """Generate data governance figures."""
    print("\n" + "=" * 70)
    print("📋 阶段 5/5: 数据治理可视化")
    print("=" * 70)

    from src.visualization.data_governance import run_full_data_gov_report

    results = run_full_data_gov_report(
        df=df_raw,
        target_col='AKI分组',
        output_dir=OUTPUT_DIR,
    )

    return results


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description='AKI Phase 1 Evaluation Pipeline')
    parser.add_argument('--skip-cv', action='store_true', help='Skip CV analysis')
    parser.add_argument('--skip-ablation', action='store_true', help='Skip ablation study')
    parser.add_argument('--skip-dca', action='store_true', help='Skip DCA analysis')
    parser.add_argument('--skip-shap', action='store_true', help='Skip SHAP analysis')
    parser.add_argument('--skip-datagov', action='store_true', help='Skip data governance')
    parser.add_argument('--quick', action='store_true', help='Quick mode: use fewer models/iterations')
    args = parser.parse_args()

    print("=" * 70)
    print("  🏥 AKI 智能预警系统 — Phase 1 一等奖冲刺评估管线")
    print("  白菜卷队 · 广西科技大学 · 暑期数创 2026")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # ------------------------------------------------------------------
    # Load data
    # ------------------------------------------------------------------
    print("\n📂 Step 0: 数据加载与预处理...")
    X_scaled, y, feature_names, X_df, df_raw = load_and_prepare_data()

    # ------------------------------------------------------------------
    # Define models
    # ------------------------------------------------------------------
    n_iter = 20 if args.quick else 50
    n_bootstrap = 200 if args.quick else 1000

    models_dict = {
        'LogisticRegression': LogisticRegression(
            penalty='l2', class_weight='balanced',
            solver='liblinear', max_iter=2000, random_state=42,
        ),
        'RandomForest': RandomForestClassifier(
            n_estimators=200, class_weight='balanced',
            max_depth=7, random_state=42, n_jobs=-1,
        ),
    }

    if _XGB:
        pos_count = np.sum(y == 1)
        neg_count = np.sum(y == 0)
        models_dict['XGBoost'] = XGBClassifier(
            n_estimators=200, max_depth=5, learning_rate=0.1,
            scale_pos_weight=neg_count / max(pos_count, 1),
            use_label_encoder=False, eval_metric='logloss',
            random_state=42, verbosity=0,
        )

    if _LGB:
        models_dict['LightGBM'] = LGBMClassifier(
            n_estimators=200, num_leaves=31, max_depth=7,
            class_weight='balanced', random_state=42,
            verbosity=-1,
        )

    if _CB:
        models_dict['CatBoost'] = CatBoostClassifier(
            n_estimators=200, depth=6, learning_rate=0.1,
            auto_class_weights='Balanced',
            random_seed=42, verbose=0,
        )

    print(f"\n  ✅ 准备就绪: {len(models_dict)} 个模型, {X_scaled.shape[1]} 个特征")

    # ------------------------------------------------------------------
    # Run Phase 1 modules
    # ------------------------------------------------------------------
    results = {}

    if not args.skip_cv:
        results['cv'] = run_cv_analysis(X_scaled, y, models_dict, feature_names)

    if not args.skip_ablation:
        results['ablation'] = run_ablation_analysis(X_scaled, y, models_dict, feature_names)

    if not args.skip_dca:
        results['dca'] = run_dca_analysis(X_scaled, y, models_dict)

    if not args.skip_shap:
        results['shap'] = run_shap_analysis(X_scaled, y, models_dict, feature_names)

    if not args.skip_datagov:
        results['datagov'] = run_data_gov_visualization(df_raw)

    # ------------------------------------------------------------------
    # Final Summary
    # ------------------------------------------------------------------
    print("\n\n" + "=" * 70)
    print("  🎉 Phase 1 评估管线执行完毕！")
    print("=" * 70)
    print(f"\n  📁 所有输出文件: {OUTPUT_DIR}")
    print(f"     ├── figures/    (图表: CV ROC, Bootstrap, 消融热力图, DCA, SHAP, 数据治理)")
    print(f"     └── tables/     (表格: CV结果, 消融对比, 校准汇总)")
    print(f"\n  💡 下一步:")
    print(f"     1. 检查 outputs/phase1/figures/ 中的图表")
    print(f"     2. 将关键图表嵌入PPT (CV ROC, DCA, 消融热力图)")
    print(f"     3. 运行 streamlit run streamlit_app.py 查看Web系统")
    print(f"\n  🔗 Phase 2 预告: Stacking融合 + PDF报告增强 + 风险分层完善")
    print("=" * 70)


if __name__ == '__main__':
    main()

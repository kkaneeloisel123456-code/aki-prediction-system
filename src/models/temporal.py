# -*- coding: utf-8 -*-
"""
======================================================================
  AKI Phase 3 — 时序风险轨迹预测模块
  广西科技大学 蓝可 | 白菜卷队 | 暑期数创 2026

  核心思路：
    将跨时间点的临床特征组织为"伪时序"——
      术前 (T0) → 术中 (T1) → ICU入室早期 (T2)
    在每个时间点构建增量模型，展示风险预测如何随信息累积而演进。

  临床价值：
    模拟"患者旅途"中的风险认知变化，为动态风险重评估提供依据。

  输出：
    outputs/phase3/figures/risk_trajectory.png      — 人群风险轨迹
    outputs/phase3/figures/temporal_auc_gain.png   — 时序信息增益
    outputs/phase3/tables/temporal_results.csv     — 时序模型对比
======================================================================
"""
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from pathlib import Path
import os, sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False

from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.metrics import roc_auc_score

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ====================================================================
# Time-point feature classification
# ====================================================================

TEMPORAL_FEATURE_MAP = {
    'T0_术前': {
        'keywords': ['年龄', 'age', '性别', 'gender', '高血压', 'hypertension',
                     '糖尿病', 'diabetes', '冠心病', 'CHD', '心衰', 'heart failure',
                     '卒中', 'stroke', 'Scr', '肌酐', 'eGFR', 'BUN', 'UA',
                     'Alb', '白蛋白', 'Hb', '血红蛋白', 'WBC', 'PLT', 'NEUT',
                     'CRP', 'hsTn', 'BNP', '乳酸', 'lactate', 'SBP', 'DBP',
                     'APACHE', 'apache', '体重', 'weight', 'BMI',
                     'PLR', 'NLR', 'B2MG', 'RBP'],
        'label': 'Pre-op (T0)',
        'description': '术前基线评估 — 人口学 + 病史 + 实验室',
    },
    'T1_术中': {
        'keywords': ['手术类型', 'surgery', '手术时间', '体外循环', 'CPB',
                     '失血', 'blood_loss', '输液', 'crystalloid',
                     '尿量', 'urine_output', '麻醉', 'anesthesia'],
        'label': 'Intra-op (T1)',
        'description': '术中动态信息 — 手术特征 + 生理应激',
    },
    'T2_术后早期': {
        'keywords': ['术后', 'postop', 'ICU入室', 'ICU admission',
                     'SOFA', '入室', 'admission',
                     '通气', 'ventilat'],
        'label': 'Early Post-op (T2)',
        'description': 'ICU入室即刻 — 术后早期生理状态',
    },
}

# Features to explicitly EXCLUDE from T2 (outcome leakage)
T2_EXCLUDE_KEYWORDS = ['KDIGO', 'AKI分期', 'AKI分组', '48h', '7d', '7天',
                       '住院天数', '住院费用', 'ICU天数', '结局', '死亡',
                       'RRT', '透析', 'dialysis']


def auto_classify_features_temporal(feature_names):
    """
    Auto-classify features into time points based on keyword matching.

    Args:
        feature_names: List of feature name strings

    Returns:
        dict: {timepoint: [feature_indices]}
    """
    groups = {key: [] for key in TEMPORAL_FEATURE_MAP.keys()}
    unclassified = []

    for i, feat in enumerate(feature_names):
        classified = False
        # Check T2 first (most specific keywords)
        t2_info = TEMPORAL_FEATURE_MAP['T2_术后早期']
        excluded = False
        for kw in T2_EXCLUDE_KEYWORDS:
            if kw.lower() in feat.lower():
                excluded = True
                break
        if not excluded:
            for kw in t2_info['keywords']:
                if kw.lower() in feat.lower():
                    groups['T2_术后早期'].append(i)
                    classified = True
                    break

        if classified:
            continue

        # Check T1
        t1_info = TEMPORAL_FEATURE_MAP['T1_术中']
        for kw in t1_info['keywords']:
            if kw.lower() in feat.lower():
                groups['T1_术中'].append(i)
                classified = True
                break

        if classified:
            continue

        # Check T0 (default, most features are pre-op)
        t0_info = TEMPORAL_FEATURE_MAP['T0_术前']
        for kw in t0_info['keywords']:
            if kw.lower() in feat.lower():
                groups['T0_术前'].append(i)
                classified = True
                break

        if not classified:
            unclassified.append((i, feat))

    # Assign unclassified to T0 as default
    for i, feat in unclassified:
        groups['T0_术前'].append(i)

    # Remove duplicates and ensure no overlap
    seen = set()
    for key in ['T2_术后早期', 'T1_术中', 'T0_术前']:
        groups[key] = [i for i in groups[key] if i not in seen]
        seen.update(groups[key])

    return groups


def prepare_temporal_datasets(X, y, feature_names, cv=5, random_state=42):
    """
    Build incremental datasets at each time point.

    T0: 术前特征 only
    T0+T1: 术前 + 术中
    T0+T1+T2: 术前 + 术中 + 术后早期 (full model)

    Args:
        X: Feature matrix (numpy array, n_samples x n_features)
        y: Target array
        feature_names: List of feature names
        cv: CV folds for evaluation
        random_state: Random seed

    Returns:
        dict with datasets and evaluation results
    """
    groups = auto_classify_features_temporal(feature_names)

    datasets = {}
    cumulative_indices = []

    timepoints_order = ['T0_术前', 'T1_术中', 'T2_术后早期']
    for tp in timepoints_order:
        cumulative_indices.extend(groups.get(tp, []))
        cumulative_indices = sorted(set(cumulative_indices))

        if len(cumulative_indices) == 0:
            continue

        X_subset = X[:, cumulative_indices]
        subset_names = [feature_names[i] for i in cumulative_indices]

        datasets[tp] = {
            'X': X_subset,
            'y': y.copy(),
            'feature_indices': cumulative_indices,
            'feature_names': subset_names,
            'n_features': len(cumulative_indices),
            'timepoint_label': TEMPORAL_FEATURE_MAP[tp]['label'],
            'description': TEMPORAL_FEATURE_MAP[tp]['description'],
        }

    return datasets


def evaluate_temporal_models(datasets, cv=5, random_state=42):
    """
    Train and evaluate models at each temporal stage.

    Uses a consistent model (RandomForest) across all time points
    to isolate the effect of adding temporal information.

    Returns:
        DataFrame with AUC scores per time point
    """
    results = []

    for tp_key, ds in datasets.items():
        X_tp = ds['X']
        y_tp = ds['y']

        # Model with controlled complexity
        model = RandomForestClassifier(
            n_estimators=200, max_depth=5,
            min_samples_leaf=10, min_samples_split=10,
            class_weight='balanced', random_state=random_state, n_jobs=-1
        )

        # Stratified CV
        skf = StratifiedKFold(n_splits=cv, shuffle=True, random_state=random_state)
        aucs = cross_val_score(model, X_tp, y_tp, cv=skf, scoring='roc_auc')

        results.append({
            '时间点': TEMPORAL_FEATURE_MAP[tp_key]['label'],
            '特征数': ds['n_features'],
            'CV AUC均值': round(aucs.mean(), 4),
            'CV AUC标准差': round(aucs.std(), 4),
            '描述': TEMPORAL_FEATURE_MAP[tp_key]['description'],
        })

    results_df = pd.DataFrame(results)
    return results_df


def plot_temporal_auc_gain(results_df, save_path=None):
    """
    Plot AUC improvement as more temporal data is added.

    Shows the incremental predictive value of each clinical phase.
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    timepoints = results_df['时间点'].tolist()
    aucs = results_df['CV AUC均值'].tolist()
    auc_stds = results_df['CV AUC标准差'].tolist()
    n_features = results_df['特征数'].tolist()

    # Left: AUC gain bar chart
    colors = ['#3498db', '#e67e22', '#2ecc71']
    bars = ax1.bar(range(len(timepoints)), aucs, color=colors[:len(timepoints)],
                   edgecolor='white', linewidth=1.5, width=0.6)
    ax1.errorbar(range(len(timepoints)), aucs, yerr=auc_stds,
                 fmt='none', ecolor='#2c3e50', capsize=8, linewidth=1.5)

    # AUC gain labels
    for i in range(1, len(aucs)):
        gain = aucs[i] - aucs[i - 1]
        ax1.annotate(f'+{gain:.3f}',
                     xy=(i, aucs[i]), xytext=(i, aucs[i] + 0.02),
                     ha='center', fontsize=11, fontweight='bold',
                     color='#e74c3c',
                     arrowprops=dict(arrowstyle='->', color='#e74c3c', lw=1.5))

    ax1.set_xticks(range(len(timepoints)))
    ax1.set_xticklabels(timepoints, fontsize=10)
    ax1.set_ylabel('CV AUC-ROC', fontsize=12)
    ax1.set_title('Temporal AUC Gain (Incremental)', fontsize=13, fontweight='bold')
    ax1.set_ylim(min(aucs) - 0.05, max(aucs) + 0.05)
    ax1.grid(axis='y', alpha=0.3)

    # Value labels
    for bar, auc, std in zip(bars, aucs, auc_stds):
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.005,
                 f'{auc:.3f} +/- {std:.3f}', ha='center', fontsize=9, fontweight='bold')

    # Right: Feature accumulation
    ax2.fill_between(range(len(timepoints)), 0, n_features, alpha=0.3,
                     color='#9b59b6', step='mid')
    ax2.plot(range(len(timepoints)), n_features, 'o-', color='#8e44ad',
             linewidth=2.5, markersize=10, markerfacecolor='white')
    ax2.set_xticks(range(len(timepoints)))
    ax2.set_xticklabels(timepoints, fontsize=10)
    ax2.set_ylabel('Cumulative Features', fontsize=12)
    ax2.set_title('Feature Accumulation Over Time', fontsize=13, fontweight='bold')
    for i, nf in enumerate(n_features):
        ax2.annotate(str(nf), (i, nf), textcoords="offset points",
                     xytext=(0, 12), ha='center', fontsize=11, fontweight='bold')
    ax2.grid(axis='y', alpha=0.3)

    plt.suptitle('AKI Risk Prediction: Temporal Information Gain',
                 fontsize=15, fontweight='bold', y=1.02)
    plt.tight_layout()

    if save_path:
        os.makedirs(os.path.dirname(str(save_path)), exist_ok=True)
        fig.savefig(str(save_path), dpi=150, bbox_inches='tight', facecolor='white')
        plt.close(fig)
    else:
        return fig


def plot_risk_trajectory(models_dict, patient_X, patient_features,
                          temporal_groups, save_path=None):
    """
    Plot risk trajectory for a single patient across time points.

    Shows how risk assessment evolves from T0 through T2.

    Args:
        models_dict: {timepoint: fitted_model}
        patient_X: Full feature vector for one patient (1 x n_features)
        patient_features: List of all feature names
        temporal_groups: Output from auto_classify_features_temporal
        save_path: Path to save figure

    Returns:
        fig, trajectory data
    """
    fig, ax = plt.subplots(figsize=(10, 5))

    timepoints_order = ['T0_术前', 'T1_术中', 'T2_术后早期']
    tp_labels = [TEMPORAL_FEATURE_MAP[tp]['label'] for tp in timepoints_order]
    risks = []
    cumulative_features = []

    # Build cumulative indices for each time point
    all_features_used = set()
    for tp in timepoints_order:
        if tp in models_dict:
            # Get cumulative features up to this time point
            all_features_used.update(temporal_groups.get(tp, []))
            cum_indices = sorted(all_features_used)

            X_subset = patient_X[0, cum_indices].reshape(1, -1)
            model = models_dict[tp]
            if hasattr(model, 'predict_proba'):
                prob = model.predict_proba(X_subset)[0, 1]
            else:
                prob = float(model.predict(X_subset)[0])
            risks.append(prob)
        else:
            risks.append(np.nan)

    # Filter valid points
    valid = [(i, r, l) for i, (r, l) in enumerate(zip(risks, tp_labels)) if not np.isnan(r)]
    if not valid:
        return None, None

    x_vals = [v[0] for v in valid]
    y_vals = [v[1] for v in valid]
    labels = [v[2] for v in valid]

    # Time-point based risk zones
    zones = [
        (0, 0.2, '#27ae60', 'Low Risk'),
        (0.2, 0.4, '#85c943', 'Low-Medium'),
        (0.4, 0.7, '#f39c12', 'Medium-High'),
        (0.7, 1.0, '#e74c3c', 'High Risk'),
    ]
    for lo, hi, color, zone_label in zones:
        ax.axhspan(lo, hi, alpha=0.08, color=color)

    # Trajectory line
    ax.plot(x_vals, y_vals, 'o-', color='#2c3e50', linewidth=3,
            markersize=12, markerfacecolor='white', markeredgewidth=2,
            label='Risk Trajectory')

    # Annotate each point
    for i, (x, y, label) in enumerate(zip(x_vals, y_vals, labels)):
        ax.annotate(f'{label}\n{y:.1%}',
                    (x, y), textcoords="offset points",
                    xytext=(0, -30), ha='center', fontsize=10,
                    fontweight='bold', color='#2c3e50',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='white',
                             edgecolor='#bdc3c7', alpha=0.9))

    ax.set_xticks(x_vals)
    ax.set_xticklabels(labels, fontsize=11)
    ax.set_ylabel('Predicted AKI Risk', fontsize=13)
    ax.set_ylim(0, 1)
    ax.set_title('Individual Risk Trajectory Across Clinical Time Points',
                 fontsize=14, fontweight='bold')
    ax.grid(axis='y', alpha=0.3)

    # Risk zone legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor='#27ae60', alpha=0.2, label='Low Risk (<20%)'),
        Patch(facecolor='#85c943', alpha=0.2, label='Low-Medium (20-40%)'),
        Patch(facecolor='#f39c12', alpha=0.2, label='Medium-High (40-70%)'),
        Patch(facecolor='#e74c3c', alpha=0.2, label='High Risk (>70%)'),
    ]
    ax.legend(handles=[plt.Line2D([0], [0], color='#2c3e50', linewidth=3,
                                  marker='o', markersize=8, markerfacecolor='white')]
              + legend_elements,
              loc='upper left', fontsize=8)

    plt.tight_layout()

    if save_path:
        os.makedirs(os.path.dirname(str(save_path)), exist_ok=True)
        fig.savefig(str(save_path), dpi=150, bbox_inches='tight', facecolor='white')
        plt.close(fig)

    trajectory = [{'timepoint': l, 'risk': r} for r, l in zip(y_vals, labels)]
    return fig, trajectory


def run_full_temporal_analysis(X, y, feature_names, cv=5, random_state=42,
                                output_dir=None):
    """
    Complete temporal prediction pipeline.

    Args:
        X: Feature matrix (numpy array)
        y: Target array
        feature_names: List of feature names
        cv: CV folds
        random_state: Random seed
        output_dir: Output directory for figures and tables

    Returns:
        dict with results
    """
    if output_dir is None:
        output_dir = str(PROJECT_ROOT / 'outputs' / 'phase3')

    fig_dir = Path(output_dir) / 'figures'
    tab_dir = Path(output_dir) / 'tables'
    fig_dir.mkdir(parents=True, exist_ok=True)
    tab_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("  Temporal AKI Risk Prediction | Phase 3")
    print("=" * 70)
    print(f"  Data: N={len(y)}, Features={len(feature_names)}")
    print(f"  Time points: T0 (Pre-op) -> T1 (Intra-op) -> T2 (Early Post-op)")

    # Step 1: Classify features by time point
    print("\n[Step 1] Classifying features by clinical time point...")
    temporal_groups = auto_classify_features_temporal(feature_names)
    for tp, indices in temporal_groups.items():
        label = TEMPORAL_FEATURE_MAP[tp]['label']
        print(f"  {label}: {len(indices)} features")

    # Step 2: Build temporal datasets
    print("\n[Step 2] Building incremental datasets...")
    datasets = prepare_temporal_datasets(X, y, feature_names, cv=cv, random_state=random_state)

    # Step 3: Evaluate
    print("\n[Step 3] Evaluating models at each time point...")
    results_df = evaluate_temporal_models(datasets, cv=cv, random_state=random_state)

    # Step 4: Plot AUC gain
    print("\n[Step 4] Plotting temporal AUC gain...")
    plot_temporal_auc_gain(results_df, save_path=str(fig_dir / 'temporal_auc_gain.png'))

    # Step 5: Train full models and generate example trajectory
    print("\n[Step 5] Generating example risk trajectory...")
    models_dict = {}
    for tp_key, ds in datasets.items():
        model = RandomForestClassifier(
            n_estimators=200, max_depth=5, min_samples_leaf=10,
            min_samples_split=10, class_weight='balanced',
            random_state=random_state, n_jobs=-1
        )
        model.fit(ds['X'], ds['y'])
        models_dict[tp_key] = model

    # Generate trajectory for a medium-risk patient
    try:
        patient_idx = np.where(y == 1)[0][0] if np.sum(y == 1) > 0 else 0
        patient_X = X[patient_idx:patient_idx+1]
        plot_risk_trajectory(
            models_dict, patient_X, feature_names,
            temporal_groups,
            save_path=str(fig_dir / 'risk_trajectory.png')
        )
        print("  Risk trajectory saved.")
    except Exception as e:
        print(f"  [WARN] Trajectory plot failed: {e}")

    # Save table
    results_df.to_csv(str(tab_dir / 'temporal_results.csv'), index=False, encoding='utf-8-sig')

    # Print summary
    print("\n" + "=" * 70)
    print("  Temporal Analysis Complete")
    print("=" * 70)
    print(results_df.to_string(index=False))
    print(f"\n  Output: {output_dir}")

    return {
        'results_df': results_df,
        'datasets': datasets,
        'temporal_groups': temporal_groups,
        'models_dict': models_dict,
    }


if __name__ == '__main__':
    # Quick test
    print("Temporal prediction module loaded.")
    print(f"  {len(TEMPORAL_FEATURE_MAP)} time point categories defined.")
    for tp, info in TEMPORAL_FEATURE_MAP.items():
        print(f"  {info['label']}: {len(info['keywords'])} keywords")

"""
AKI Prediction Project - Calibration & Decision Curve Analysis
Calibration curves, DCA (Decision Curve Analysis), Clinical Impact Curve.
"""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.calibration import calibration_curve, CalibratedClassifierCV
from sklearn.metrics import brier_score_loss
from scipy.interpolate import interp1d
import warnings
warnings.filterwarnings('ignore')

import sys
sys.path.append('..')
from src.utils.helpers import (
    logger, FIGURES_DIR, TABLES_DIR,
    save_figure, save_table
)


# ============================================
# Calibration Curve
# ============================================
def plot_calibration_curve_single(y_true, y_prob, model_name, n_bins=10,
                                   save_name=None, ax=None):
    """Plot calibration curve for a single model."""
    prob_true, prob_pred = calibration_curve(y_true, y_prob, n_bins=n_bins, strategy='uniform')
    brier = brier_score_loss(y_true, y_prob)

    if ax is None:
        fig, ax = plt.subplots(figsize=(6, 6))
        standalone = True
    else:
        standalone = False

    ax.plot(prob_pred, prob_true, marker='o', linewidth=1.5, markersize=6,
            label=f'{model_name} (Brier={brier:.4f})')
    ax.plot([0, 1], [0, 1], 'k--', linewidth=1, alpha=0.5, label='Perfect Calibration')

    ax.set_xlabel('Predicted Probability', fontsize=12)
    ax.set_ylabel('Observed Proportion', fontsize=12)
    ax.set_title(f'Calibration Curve - {model_name}', fontsize=13, fontweight='bold')
    ax.legend(loc='lower right', fontsize=9)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.grid(True, alpha=0.3)

    if standalone and save_name:
        save_figure(ax.figure, save_name)

    return ax


def plot_calibration_curves_all(model_results_dict, n_bins=10,
                                 save_name='calibration_curves.png'):
    """
    Plot calibration curves for all models on one figure.

    Args:
        model_results_dict: {model_name: {'y_prob': ..., 'y_true': ...}}
    """
    n_models = len(model_results_dict)
    n_cols = min(3, n_models)
    n_rows = (n_models + n_cols - 1) // n_cols

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(n_cols * 5.5, n_rows * 5))
    if n_models == 1:
        axes = np.array([axes])
    axes = axes.flatten()

    for i, (name, results) in enumerate(model_results_dict.items()):
        plot_calibration_curve_single(
            results['y_true'], results['y_prob'], name,
            n_bins=n_bins, ax=axes[i]
        )

    # Hide unused subplots
    for j in range(i + 1, len(axes)):
        axes[j].set_visible(False)

    fig.suptitle('Calibration Curves - All Models', fontsize=16, fontweight='bold', y=1.01)
    plt.tight_layout()
    save_figure(fig, save_name)
    logger.info(f"Calibration curves saved: {save_name}")


def plot_calibration_curves_overlay(model_results_dict, n_bins=10,
                                     save_name='calibration_overlay.png'):
    """Overlay all calibration curves on one plot."""
    fig, ax = plt.subplots(figsize=(8, 7))

    colors = plt.cm.tab10(np.linspace(0, 1, len(model_results_dict)))

    for (name, results), color in zip(model_results_dict.items(), colors):
        prob_true, prob_pred = calibration_curve(
            results['y_true'], results['y_prob'], n_bins=n_bins, strategy='uniform'
        )
        brier = brier_score_loss(results['y_true'], results['y_prob'])
        ax.plot(prob_pred, prob_true, marker='o', linewidth=1.5, markersize=5,
                color=color, label=f'{name} (Brier={brier:.4f})')

    ax.plot([0, 1], [0, 1], 'k--', linewidth=1, alpha=0.5, label='Perfect')

    ax.set_xlabel('Predicted Probability')
    ax.set_ylabel('Observed Proportion')
    ax.set_title('Calibration Curves Comparison', fontsize=14, fontweight='bold')
    ax.legend(loc='lower right', fontsize=8)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.grid(True, alpha=0.3)

    save_figure(fig, save_name)


# ============================================
# Decision Curve Analysis (DCA)
# ============================================
def compute_net_benefit(y_true, y_prob, threshold):
    """
    Compute net benefit at a given threshold probability.

    Net Benefit = (TP - w * FP) / N
    where w = threshold / (1 - threshold)
    """
    y_pred = (y_prob >= threshold).astype(int)

    tp = np.sum((y_true == 1) & (y_pred == 1))
    fp = np.sum((y_true == 0) & (y_pred == 1))
    n = len(y_true)
    w = threshold / (1 - threshold)

    nb = (tp - w * fp) / n
    return nb


def compute_net_benefit_curve(y_true, y_prob, thresholds=None):
    """Compute net benefit across all thresholds."""
    if thresholds is None:
        thresholds = np.linspace(0.01, 0.99, 99)

    nb_treat_all = compute_treat_all_net_benefit(y_true, thresholds)

    net_benefits = []
    for t in thresholds:
        nb = compute_net_benefit(y_true, y_prob, t)
        net_benefits.append(nb)

    return np.array(thresholds), np.array(net_benefits), nb_treat_all


def compute_treat_all_net_benefit(y_true, thresholds):
    """Net benefit of treating all patients."""
    prevalence = np.mean(y_true)
    net_benefits = []
    for t in thresholds:
        nb = prevalence - (1 - prevalence) * (t / (1 - t))
        net_benefits.append(nb)
    return np.array(net_benefits)


def plot_decision_curve(y_true, model_probs_dict, thresholds=None,
                         save_name='decision_curve.png',
                         show_ci=True, n_bootstrap=200):
    """
    Plot Decision Curve Analysis (DCA) — Professional Medical Journal Style.

    Key features:
    - Professional color palette with clear model differentiation
    - Chinese/English bilingual labels
    - Clinical utility zone highlighted
    - Bootstrap CI for the best model (optional)
    - Net benefit summary at key thresholds

    Args:
        y_true: True labels
        model_probs_dict: {model_name: predicted_probabilities}
        thresholds: Threshold array (default: 0.01-0.99)
        show_ci: If True, add bootstrap CI for best model
        n_bootstrap: Number of bootstrap resamples for CI
    """
    if thresholds is None:
        thresholds = np.linspace(0.01, 0.99, 99)

    # Professional palette
    _DCA_COLORS = [
        '#2a78d6',  # blue
        '#1baf7a',  # aqua
        '#eda100',  # yellow
        '#e34948',  # red
        '#4a3aa7',  # violet
        '#eb6834',  # orange
        '#e87ba4',  # magenta
    ]

    fig, ax = plt.subplots(figsize=(11, 8))
    fig.patch.set_facecolor('#fcfcfb')
    ax.set_facecolor('#fcfcfb')

    # Treat None (reference, always 0)
    ax.plot(thresholds, np.zeros_like(thresholds), '-', color='#0b0b0b',
            linewidth=2.5, label='Treat None (全不干预)', alpha=0.85)

    # Treat All
    nb_treat_all = compute_treat_all_net_benefit(y_true, thresholds)
    ax.plot(thresholds, nb_treat_all, '--', color='#898781', linewidth=2,
            label='Treat All (全干预)', alpha=0.75)

    # Each model
    best_name = list(model_probs_dict.keys())[0] if model_probs_dict else None
    for i, (name, y_prob) in enumerate(model_probs_dict.items()):
        color = _DCA_COLORS[i % len(_DCA_COLORS)]
        _, net_benefits, _ = compute_net_benefit_curve(y_true, y_prob, thresholds)
        ax.plot(thresholds, net_benefits, '-', color=color,
                linewidth=2.5, label=name, alpha=0.92)

    # Bootstrap CI for best model
    if show_ci and best_name and len(model_probs_dict) > 0:
        best_prob = model_probs_dict[best_name]
        n = len(y_true)
        nb_bootstrap = np.zeros((n_bootstrap, len(thresholds)))
        rng = np.random.RandomState(42)

        for b in range(n_bootstrap):
            idx = rng.choice(n, n, replace=True)
            _, nb_vals, _ = compute_net_benefit_curve(
                y_true[idx], best_prob[idx], thresholds)
            nb_bootstrap[b] = nb_vals

        nb_lower = np.percentile(nb_bootstrap, 2.5, axis=0)
        nb_upper = np.percentile(nb_bootstrap, 97.5, axis=0)
        _, nb_mean, _ = compute_net_benefit_curve(y_true, best_prob, thresholds)

        ax.fill_between(thresholds, nb_lower, nb_upper,
                        alpha=0.12, color=_DCA_COLORS[0],
                        label=f'{best_name} 95% CI')

    # === Clinical utility zone ===
    # Shade region where model > treat-all (clinically useful)
    if best_name and len(model_probs_dict) > 0:
        best_prob = model_probs_dict[best_name]
        _, nb_model, _ = compute_net_benefit_curve(y_true, best_prob, thresholds)
        utility_mask = nb_model > nb_treat_all
        if np.any(utility_mask):
            util_start = thresholds[np.where(utility_mask)[0][0]]
            util_end = thresholds[np.where(utility_mask)[0][-1]]
            ax.axvspan(util_start, util_end, alpha=0.06, color='#1baf7a')
            ax.annotate(
                f'临床有用区域\nClinical Utility Zone\n({util_start:.2f} - {util_end:.2f})',
                xy=((util_start + util_end) / 2, ax.get_ylim()[1] * 0.85),
                fontsize=9, ha='center', color='#1baf7a',
                bbox=dict(boxstyle='round,pad=0.4', facecolor='white',
                          edgecolor='#1baf7a', alpha=0.85),
            )

    # === Axis labels ===
    ax.set_xlabel('风险阈值概率 Threshold Probability\n(反映医生对AKI的担忧程度)',
                  fontsize=12, color='#0b0b0b')
    ax.set_ylabel('净获益 Net Benefit', fontsize=12, color='#0b0b0b')
    ax.set_title('临床决策曲线分析 | Decision Curve Analysis (DCA)\n'
                 f'数据量 N={len(y_true)}, AKI患病率 {np.mean(y_true):.1%}',
                 fontsize=15, fontweight='bold', color='#0b0b0b')

    # === Legend ===
    ax.legend(loc='upper right', fontsize=9, framealpha=0.9,
              edgecolor='#e1e0d9', ncol=1)

    ax.set_xlim(0, 0.5)  # Clinically relevant range
    ax.grid(True, alpha=0.25, color='#e1e0d9', linewidth=0.5)

    # Style cleanup
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#c3c2b7')
    ax.spines['bottom'].set_color('#c3c2b7')
    ax.tick_params(colors='#898781')

    # === DCA Summary statistics ===
    summary_text = "📊 DCA 摘要 | Summary:\n"
    summary_text += f"━━━━━━━━━━━━━━━━━━\n"
    for i, (name, y_prob) in enumerate(model_probs_dict.items()):
        nb_at_20, _ = compute_net_benefit(y_true, y_prob, 0.2), None
        nb_20_val = compute_net_benefit(y_true, y_prob, 0.2)
        nb_all_20 = compute_treat_all_net_benefit(y_true, np.array([0.2]))[0]
        summary_text += f"{name}: NB@20%={nb_20_val:.4f}\n"

    ax.text(0.98, 0.98, summary_text, transform=ax.transAxes,
            fontsize=8, ha='right', va='top', fontfamily='monospace',
            bbox=dict(boxstyle='round,pad=0.4', facecolor='white',
                      edgecolor='#e1e0d9', alpha=0.9))

    # === Key insight annotation ===
    ax.annotate(
        '💡 曲线在"全干预"线之上 = 模型具有临床净获益\n'
        '📌 横轴反映临床决策的风险阈值偏好',
        xy=(0.02, 0.04), xycoords='axes fraction',
        fontsize=8, ha='left', va='bottom', color='#52514e',
        bbox=dict(boxstyle='round,pad=0.3', facecolor='#fffde7',
                  edgecolor='#eda100', alpha=0.85),
    )

    fig.tight_layout()
    save_figure(fig, save_name)
    logger.info(f"DCA saved: {save_name}")

    return fig, ax


def plot_decision_curve_with_confidence(model_probs_dict, y_true,
                                          n_bootstrap=200, thresholds=None,
                                          save_name='dca_with_ci.png'):
    """DCA with bootstrap confidence intervals for the best model."""
    if thresholds is None:
        thresholds = np.linspace(0.01, 0.99, 99)

    # Get the first (best) model
    best_name = list(model_probs_dict.keys())[0]
    best_prob = model_probs_dict[best_name]

    fig, ax = plt.subplots(figsize=(10, 7))

    # Bootstrap
    n = len(y_true)
    nb_bootstrap = np.zeros((n_bootstrap, len(thresholds)))
    rng = np.random.RandomState(42)

    for b in range(n_bootstrap):
        idx = rng.choice(n, n, replace=True)
        _, nb_vals, _ = compute_net_benefit_curve(y_true[idx], best_prob[idx], thresholds)
        nb_bootstrap[b] = nb_vals

    nb_lower = np.percentile(nb_bootstrap, 2.5, axis=0)
    nb_upper = np.percentile(nb_bootstrap, 97.5, axis=0)

    # Plot
    _, nb_mean, _ = compute_net_benefit_curve(y_true, best_prob, thresholds)
    ax.plot(thresholds, nb_mean, '-', color='#3498db', linewidth=2.5,
            label=f'{best_name} (Best Model)')
    ax.fill_between(thresholds, nb_lower, nb_upper, alpha=0.2, color='#3498db',
                    label=f'95% CI (Bootstrap n={n_bootstrap})')

    # Treat all / none
    nb_treat_all = compute_treat_all_net_benefit(y_true, thresholds)
    ax.plot(thresholds, nb_treat_all, '--', color='gray', linewidth=2,
            label='Treat All')
    ax.plot(thresholds, np.zeros_like(thresholds), '-', color='black',
            linewidth=2, label='Treat None')

    ax.set_xlabel('Threshold Probability', fontsize=12)
    ax.set_ylabel('Net Benefit', fontsize=12)
    ax.set_title(f'Decision Curve Analysis - {best_name}', fontsize=14, fontweight='bold')
    ax.legend(loc='best', fontsize=9)
    ax.set_xlim(0, 0.5)
    ax.grid(True, alpha=0.3)

    save_figure(fig, save_name)
    return fig, ax


# ============================================
# Clinical Impact Curve
# ============================================
def plot_clinical_impact_curve(y_true, y_prob, thresholds=None,
                                save_name='clinical_impact_curve.png'):
    """
    Plot Clinical Impact Curve showing number of high-risk patients
    and true positives at each threshold.
    """
    if thresholds is None:
        thresholds = np.linspace(0.01, 0.99, 199)

    n_total = len(y_true)
    n_positive = np.sum(y_true)

    n_high_risk = []
    n_true_positives = []

    for t in thresholds:
        y_pred = (y_prob >= t).astype(int)
        n_high_risk.append(np.sum(y_pred))
        n_true_positives.append(np.sum((y_true == 1) & (y_pred == 1)))

    n_high_risk = np.array(n_high_risk)
    n_true_positives = np.array(n_true_positives)

    fig, ax = plt.subplots(figsize=(10, 7))

    ax.plot(thresholds, n_high_risk, '-', color='#e74c3c', linewidth=2.5,
            label=f'Number High Risk (Predicted)')
    ax.plot(thresholds, n_true_positives, '-', color='#2ecc71', linewidth=2.5,
            label=f'Number True Positives (Actual)')

    ax.set_xlabel('Threshold Probability', fontsize=12)
    ax.set_ylabel('Number of Patients', fontsize=12)
    ax.set_title('Clinical Impact Curve', fontsize=14, fontweight='bold')
    ax.legend(loc='best', fontsize=10)
    ax.grid(True, alpha=0.3)

    # Cost:benefit ratio annotation
    ax.axvline(x=0.2, color='gray', linestyle=':', alpha=0.5)
    ax.text(0.21, ax.get_ylim()[1] * 0.9, 'Cost:Benefit = 1:4', fontsize=8, alpha=0.6)

    save_figure(fig, save_name)
    logger.info(f"Clinical Impact Curve saved: {save_name}")

    return fig, ax


# ============================================
# Calibration Summary Table
# ============================================
def create_calibration_summary(model_results_dict, n_bins=10,
                                save_name='calibration_summary.csv'):
    """
    Create calibration summary table: Brier Score, ECI, Eavg, etc.
    """
    summary = []

    for name, results in model_results_dict.items():
        y_true = results['y_true']
        y_prob = results['y_prob']

        # Brier score
        brier = brier_score_loss(y_true, y_prob)

        # Calibration curve data
        prob_true, prob_pred = calibration_curve(y_true, y_prob, n_bins=n_bins)

        # ECI (Estimated Calibration Index) = mean(abs(observed - predicted))
        eci = np.mean(np.abs(prob_true - prob_pred))

        # E50 = median calibration error
        e50 = np.median(np.abs(prob_true - prob_pred))

        # E_max = max calibration error
        emax = np.max(np.abs(prob_true - prob_pred))

        # Slope and intercept of calibration
        from scipy.stats import linregress
        if len(prob_true) >= 3:
            slope, intercept, r_value, p_value, std_err = linregress(prob_pred, prob_true)
        else:
            slope, intercept, p_value = np.nan, np.nan, np.nan

        summary.append({
            'Model': name,
            'Brier_Score': round(brier, 4),
            'ECI': round(eci, 4),
            'E50': round(e50, 4),
            'E_max': round(emax, 4),
            'Calibration_Slope': round(slope, 4) if not np.isnan(slope) else 'NA',
            'Calibration_Intercept': round(intercept, 4) if not np.isnan(intercept) else 'NA',
        })

    summary_df = pd.DataFrame(summary).sort_values('Brier_Score')
    save_table(summary_df, save_name)

    # Plot calibration summary heatmap
    plot_calibration_heatmap(summary_df)

    return summary_df


def plot_calibration_heatmap(summary_df, save_name='calibration_heatmap.png'):
    """Heatmap of calibration metrics across models."""
    metrics_cols = ['Brier_Score', 'ECI', 'E50', 'E_max']
    heatmap_data = summary_df.set_index('Model')[metrics_cols]

    fig, ax = plt.subplots(figsize=(10, max(4, len(summary_df) * 0.5)))
    sns.heatmap(heatmap_data, annot=True, fmt='.4f', cmap='RdYlGn_r',
                linewidths=0.5, ax=ax, cbar_kws={'label': 'Error'})
    ax.set_title('Calibration Metrics Comparison', fontsize=14, fontweight='bold')
    plt.tight_layout()
    save_figure(fig, save_name)


# ============================================
# Risk Stratification
# ============================================
def stratify_risk(y_prob, thresholds=None):
    """
    Stratify patients into risk groups.

    Args:
        y_prob: Predicted probabilities
        thresholds: List of cutoff values, default [0.3, 0.7] → Low/Medium/High

    Returns:
        risk_groups: Array of risk group labels
        risk_counts: Dict of counts per group
    """
    if thresholds is None:
        thresholds = [0.3, 0.7]

    thresholds = sorted(thresholds)
    groups = ['Low Risk', 'Medium Risk', 'High Risk'][:len(thresholds) + 1]

    risk_labels = np.full(len(y_prob), groups[-1], dtype=object)
    for i, t in enumerate(thresholds):
        if i == 0:
            risk_labels[y_prob < t] = groups[0]
        risk_labels[(y_prob >= thresholds[i - 1]) & (y_prob < t)] = groups[i]

    # Fix for first threshold
    risk_labels[y_prob < thresholds[0]] = groups[0]
    for i in range(len(thresholds) - 1):
        risk_labels[(y_prob >= thresholds[i]) & (y_prob < thresholds[i + 1])] = groups[i + 1]
    risk_labels[y_prob >= thresholds[-1]] = groups[-1]

    risk_counts = {g: int(np.sum(risk_labels == g)) for g in groups}

    return risk_labels, risk_counts


def analyze_risk_groups(y_true, y_prob, thresholds=None,
                         save_name='risk_stratification.csv'):
    """Analyze observed event rates in each risk group."""
    risk_labels, risk_counts = stratify_risk(y_prob, thresholds)

    analysis = []
    for group in np.unique(risk_labels):
        mask = risk_labels == group
        n = mask.sum()
        n_events = y_true[mask].sum()
        event_rate = n_events / n if n > 0 else 0
        avg_prob = y_prob[mask].mean() if n > 0 else 0

        analysis.append({
            'Risk_Group': group,
            'N': n,
            'Percent': round(n / len(y_true) * 100, 1),
            'AKI_Events': n_events,
            'Observed_Rate': round(event_rate, 3),
            'Mean_Predicted_Prob': round(avg_prob, 3),
        })

    analysis_df = pd.DataFrame(analysis)
    save_table(analysis_df, save_name)

    return analysis_df


# ============================================
# Full Calibration Pipeline
# ============================================
def run_full_calibration_analysis(model_results_dict, output_dir=None):
    """
    Run complete calibration and DCA analysis pipeline.

    Args:
        model_results_dict: {model_name: {'y_true': array, 'y_prob': array, ...}}
    """
    logger.info("=" * 60)
    logger.info("Starting Calibration & DCA Analysis Pipeline")
    logger.info("=" * 60)

    # 1. Calibration curves (grid + overlay)
    plot_calibration_curves_all(model_results_dict, n_bins=10)
    plot_calibration_curves_overlay(model_results_dict, n_bins=10)

    # 2. DCA
    model_probs_dict = {name: results['y_prob']
                        for name, results in model_results_dict.items()}
    y_true = list(model_results_dict.values())[0]['y_true']
    plot_decision_curve(y_true, model_probs_dict)

    # 3. DCA with CI for best model (first = highest AUC)
    plot_decision_curve_with_confidence(model_probs_dict, y_true)

    # 4. Clinical Impact Curve for best model
    best_name = list(model_results_dict.keys())[0]
    best_prob = model_results_dict[best_name]
    plot_clinical_impact_curve(y_true, best_prob)

    # 5. Calibration summary table
    summary_df = create_calibration_summary(model_results_dict)

    # 6. Risk stratification
    risk_df = analyze_risk_groups(y_true, best_prob,
                                   save_name='risk_stratification.csv')

    logger.info("Calibration & DCA analysis complete!")

    return {
        'calibration_summary': summary_df,
        'risk_stratification': risk_df,
    }


if __name__ == '__main__':
    print("Calibration module loaded successfully.")

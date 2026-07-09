"""
AKI Prediction Project - ROC & PR Curve Visualization
ROC curves, Precision-Recall curves, confusion matrices, F1-threshold plots.
"""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.metrics import (
    roc_curve, auc, precision_recall_curve, average_precision_score,
    confusion_matrix, ConfusionMatrixDisplay, f1_score
)
import warnings
warnings.filterwarnings('ignore')

import sys
sys.path.append('..')
from src.utils.helpers import logger, FIGURES_DIR, TABLES_DIR, save_figure, save_table


# ============================================
# ROC Curves
# ============================================
def plot_roc_curve_single(y_true, y_prob, model_name, ax=None, save_name=None):
    """Plot ROC curve for a single model."""
    fpr, tpr, thresholds = roc_curve(y_true, y_prob)
    roc_auc = auc(fpr, tpr)

    standalone = ax is None
    if standalone:
        fig, ax = plt.subplots(figsize=(7, 6))

    ax.plot(fpr, tpr, linewidth=2.5, label=f'{model_name} (AUC = {roc_auc:.4f})')
    ax.plot([0, 1], [0, 1], 'k--', linewidth=1, alpha=0.5, label='Random (AUC = 0.5)')
    ax.fill_between(fpr, tpr, alpha=0.1)

    ax.set_xlabel('False Positive Rate (1 - Specificity)', fontsize=11)
    ax.set_ylabel('True Positive Rate (Sensitivity)', fontsize=11)
    ax.set_title(f'ROC Curve - {model_name}', fontsize=13, fontweight='bold')
    ax.legend(loc='lower right', fontsize=9)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.grid(True, alpha=0.3)
    ax.set_aspect('equal')

    if standalone and save_name:
        save_figure(fig, save_name)

    return ax, roc_auc


def plot_roc_curves_all(model_results_dict, save_name='roc_curves.png',
                          figsize=(10, 8)):
    """
    Plot all models' ROC curves on one figure.

    Args:
        model_results_dict: {model_name: {'y_true': array, 'y_prob': array}}
    """
    fig, ax = plt.subplots(figsize=figsize)

    colors = plt.cm.tab10(np.linspace(0, 1, len(model_results_dict) + 1))
    results_summary = []

    for i, (name, results) in enumerate(sorted(model_results_dict.items(),
                                                 key=lambda x: auc(*roc_curve(x[1]['y_true'],
                                                                               x[1]['y_prob']))[:2],
                                                 reverse=True)):
        fpr, tpr, _ = roc_curve(results['y_true'], results['y_prob'])
        roc_auc = auc(fpr, tpr)

        ax.plot(fpr, tpr, linewidth=2, color=colors[i],
                label=f'{name} (AUC = {roc_auc:.4f})')

        results_summary.append({
            'Model': name,
            'AUC': round(roc_auc, 4)
        })

    ax.plot([0, 1], [0, 1], 'k--', linewidth=1, alpha=0.3, label='Random Classifier')

    # Zoom into top-left
    from mpl_toolkits.axes_grid1.inset_locator import inset_axes
    ax_inset = inset_axes(ax, width="35%", height="35%", loc='lower right',
                           bbox_to_anchor=(0, 0.05, 1, 1), bbox_transform=ax.transAxes)
    for i, (name, results) in enumerate(sorted(model_results_dict.items(),
                                                 key=lambda x: auc(*roc_curve(x[1]['y_true'],
                                                                               x[1]['y_prob']))[:2],
                                                 reverse=True)):
        fpr, tpr, _ = roc_curve(results['y_true'], results['y_prob'])
        ax_inset.plot(fpr, tpr, linewidth=1.5, color=colors[i], alpha=0.8)
    ax_inset.set_xlim(0, 0.3)
    ax_inset.set_ylim(0.7, 1.0)
    ax_inset.set_title('Zoom (FPR 0-0.3)', fontsize=7)
    ax_inset.grid(True, alpha=0.2)

    ax.set_xlabel('False Positive Rate (1 - Specificity)', fontsize=12)
    ax.set_ylabel('True Positive Rate (Sensitivity)', fontsize=12)
    ax.set_title('ROC Curves - All Models', fontsize=14, fontweight='bold')
    ax.legend(loc='lower right', fontsize=8)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.grid(True, alpha=0.3)

    save_figure(fig, save_name)

    # Save AUC summary
    auc_df = pd.DataFrame(results_summary).sort_values('AUC', ascending=False)
    save_table(auc_df, 'auc_summary.csv')

    return fig, ax, auc_df


# ============================================
# Precision-Recall Curves
# ============================================
def plot_pr_curve_single(y_true, y_prob, model_name, ax=None, save_name=None):
    """Plot Precision-Recall curve for a single model."""
    precision, recall, thresholds = precision_recall_curve(y_true, y_prob)
    ap = average_precision_score(y_true, y_prob)
    baseline = np.mean(y_true)

    standalone = ax is None
    if standalone:
        fig, ax = plt.subplots(figsize=(7, 6))

    ax.plot(recall, precision, linewidth=2.5, label=f'{model_name} (AP = {ap:.4f})')
    ax.axhline(y=baseline, color='gray', linestyle='--', alpha=0.5,
               label=f'Baseline (prevalence = {baseline:.3f})')
    ax.fill_between(recall, precision, alpha=0.1)

    ax.set_xlabel('Recall (Sensitivity)', fontsize=11)
    ax.set_ylabel('Precision (PPV)', fontsize=11)
    ax.set_title(f'Precision-Recall Curve - {model_name}', fontsize=13, fontweight='bold')
    ax.legend(loc='best', fontsize=9)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.grid(True, alpha=0.3)

    if standalone and save_name:
        save_figure(fig, save_name)

    return ax, ap


def plot_pr_curves_all(model_results_dict, save_name='pr_curves.png',
                        figsize=(10, 8)):
    """Plot all models' Precision-Recall curves on one figure."""
    fig, ax = plt.subplots(figsize=figsize)
    colors = plt.cm.tab10(np.linspace(0, 1, len(model_results_dict) + 1))

    for i, (name, results) in enumerate(model_results_dict.items()):
        precision, recall, _ = precision_recall_curve(results['y_true'], results['y_prob'])
        ap = average_precision_score(results['y_true'], results['y_prob'])

        ax.plot(recall, precision, linewidth=2, color=colors[i],
                label=f'{name} (AP = {ap:.4f})')

    baseline = np.mean(list(model_results_dict.values())[0]['y_true'])
    ax.axhline(y=baseline, color='gray', linestyle='--', alpha=0.5,
               label=f'Baseline ({baseline:.3f})')

    ax.set_xlabel('Recall (Sensitivity)', fontsize=12)
    ax.set_ylabel('Precision (PPV)', fontsize=12)
    ax.set_title('Precision-Recall Curves - All Models', fontsize=14, fontweight='bold')
    ax.legend(loc='best', fontsize=8)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.grid(True, alpha=0.3)

    save_figure(fig, save_name)
    return fig, ax


# ============================================
# Confusion Matrices
# ============================================
def plot_confusion_matrix_single(y_true, y_pred, model_name,
                                   threshold=0.5, ax=None, save_name=None):
    """Plot confusion matrix for a single model."""
    y_pred_binary = (y_pred >= threshold).astype(int) if y_pred.dtype != int else y_pred
    cm = confusion_matrix(y_true, y_pred_binary)

    standalone = ax is None
    if standalone:
        fig, ax = plt.subplots(figsize=(6, 5))

    # Normalized
    cm_normalized = cm.astype('float') / cm.sum(axis=1)[:, np.newaxis]

    disp = ConfusionMatrixDisplay(confusion_matrix=cm, display_labels=['Non-AKI', 'AKI'])
    disp.plot(ax=ax, cmap='Blues', colorbar=False, values_format='d')

    # Add percentages
    for i in range(2):
        for j in range(2):
            ax.text(j, i + 0.25, f'({cm_normalized[i, j]:.1%})',
                   ha='center', va='bottom', fontsize=8, color='gray')

    ax.set_title(f'Confusion Matrix - {model_name}', fontsize=13, fontweight='bold')

    if standalone and save_name:
        save_figure(fig, save_name)

    return ax, cm


def plot_confusion_matrices_grid(model_results_dict, threshold=0.5,
                                  save_name='confusion_matrices.png'):
    """Plot confusion matrices for all models in a grid."""
    n_models = len(model_results_dict)
    n_cols = min(3, n_models)
    n_rows = (n_models + n_cols - 1) // n_cols

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(n_cols * 5, n_rows * 4.5))
    if n_models == 1:
        axes = np.array([axes])
    axes = axes.flatten()

    for i, (name, results) in enumerate(model_results_dict.items()):
        # Use y_pred if available, otherwise threshold y_prob
        if 'y_pred' in results:
            y_pred = results['y_pred']
        else:
            y_pred = (results['y_prob'] >= threshold).astype(int)
        plot_confusion_matrix_single(results['y_true'], y_pred, name, ax=axes[i])

    for j in range(i + 1, len(axes)):
        axes[j].set_visible(False)

    fig.suptitle('Confusion Matrices - All Models', fontsize=16, fontweight='bold', y=1.01)
    plt.tight_layout()
    save_figure(fig, save_name)


# ============================================
# F1-Threshold Optimization
# ============================================
def plot_f1_threshold_curve(y_true, y_prob, save_name='f1_threshold.png'):
    """Plot F1 score vs. decision threshold to find optimal threshold."""
    thresholds = np.linspace(0.01, 0.99, 99)
    f1_scores = [f1_score(y_true, (y_prob >= t).astype(int)) for t in thresholds]

    optimal_threshold = thresholds[np.argmax(f1_scores)]
    optimal_f1 = max(f1_scores)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(thresholds, f1_scores, linewidth=2, color='#2ecc71')
    ax.axvline(optimal_threshold, color='red', linestyle='--', alpha=0.7,
               label=f'Optimal Threshold = {optimal_threshold:.2f} (F1 = {optimal_f1:.4f})')
    ax.fill_between(thresholds, f1_scores, alpha=0.1, color='#2ecc71')

    ax.set_xlabel('Decision Threshold', fontsize=12)
    ax.set_ylabel('F1 Score', fontsize=12)
    ax.set_title('F1 Score vs. Decision Threshold', fontsize=14, fontweight='bold')
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)

    save_figure(fig, save_name)
    return optimal_threshold, optimal_f1


# ============================================
# Metrics Bar Chart Comparison
# ============================================
def plot_metrics_comparison_bar(model_metrics, metrics=None,
                                  save_name='metrics_comparison.png'):
    """
    Grouped bar chart comparing models across metrics.

    Args:
        model_metrics: {model_name: {metric_name: value, ...}}
        metrics: List of metric names to include
    """
    if metrics is None:
        metrics = ['Accuracy', 'Precision', 'Recall', 'F1', 'AUC', 'Specificity']

    model_names = list(model_metrics.keys())
    n_models = len(model_names)
    n_metrics = len(metrics)

    fig, ax = plt.subplots(figsize=(max(10, n_metrics * 2), 6))

    x = np.arange(n_metrics)
    width = 0.8 / n_models
    colors = plt.cm.tab10(np.linspace(0, 1, n_models))

    for i, (model_name, scores) in enumerate(model_metrics.items()):
        values = [scores.get(m, 0) for m in metrics]
        offset = (i - n_models / 2 + 0.5) * width
        bars = ax.bar(x + offset, values, width, label=model_name, color=colors[i],
                      edgecolor='white', linewidth=0.5)

    ax.set_xticks(x)
    ax.set_xticklabels(metrics, fontsize=10)
    ax.set_ylabel('Score', fontsize=12)
    ax.set_ylim(0, 1)
    ax.set_title('Model Performance Comparison', fontsize=14, fontweight='bold')
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.12), ncol=min(4, n_models),
              fontsize=8)
    ax.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    save_figure(fig, save_name)


# ============================================
# Bootstrap AUC Distribution
# ============================================
def plot_bootstrap_auc_distribution(bootstrap_aucs, model_name,
                                     ci_lower, ci_upper,
                                     save_name='bootstrap_auc.png'):
    """Plot bootstrap AUC distribution with confidence intervals."""
    fig, ax = plt.subplots(figsize=(8, 5))

    ax.hist(bootstrap_aucs, bins=30, alpha=0.7, color='#3498db', edgecolor='white',
            density=True)
    ax.axvline(np.mean(bootstrap_aucs), color='#e74c3c', linewidth=2,
               label=f'Mean AUC = {np.mean(bootstrap_aucs):.4f}')
    ax.axvline(ci_lower, color='gray', linestyle='--', linewidth=1.5,
               label=f'95% CI: [{ci_lower:.4f}, {ci_upper:.4f}]')
    ax.axvline(ci_upper, color='gray', linestyle='--', linewidth=1.5)
    ax.fill_betweenx([0, ax.get_ylim()[1]], ci_lower, ci_upper, alpha=0.1, color='gray')

    ax.set_xlabel('AUC', fontsize=12)
    ax.set_ylabel('Density', fontsize=12)
    ax.set_title(f'Bootstrap AUC Distribution - {model_name}', fontsize=14, fontweight='bold')
    ax.legend(fontsize=10)

    save_figure(fig, save_name)


print("ROC/PR visualization module loaded successfully.")

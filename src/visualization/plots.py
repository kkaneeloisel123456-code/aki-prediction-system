"""
AKI Prediction Project - General Visualization Module
Distribution plots, box plots, heatmaps, comparison charts.
"""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.patches import Patch
import warnings
warnings.filterwarnings('ignore')

import sys
sys.path.append('..')
from src.utils.helpers import (
    logger, FIGURES_DIR, TABLES_DIR,
    save_figure, save_table, format_pvalue
)


# ============================================
# Distribution Plots
# ============================================
def plot_distribution_with_target(df, feature, target='AKI分组',
                                   save_name=None, ax=None):
    """Plot distribution of a feature split by target groups."""
    standalone = ax is None
    if standalone:
        fig, ax = plt.subplots(figsize=(8, 5))

    groups = df[target].unique()
    colors = ['#3498db', '#e74c3c']

    for i, group in enumerate(sorted(groups)):
        data = df[df[target] == group][feature].dropna()
        label = f'Non-AKI (n={len(data)})' if group == 0 else f'AKI (n={len(data)})'
        ax.hist(data, bins=30, alpha=0.6, color=colors[i], label=label, density=True)
        # KDE overlay
        if len(data) > 2:
            try:
                from scipy.stats import gaussian_kde
                kde = gaussian_kde(data)
                x_range = np.linspace(data.min(), data.max(), 200)
                ax.plot(x_range, kde(x_range), color=colors[i], linewidth=2)
            except Exception:
                pass

    ax.set_xlabel(feature, fontsize=11)
    ax.set_ylabel('Density', fontsize=11)
    ax.set_title(f'{feature} Distribution by AKI Group', fontsize=13, fontweight='bold')
    ax.legend(fontsize=9)

    if standalone and save_name:
        save_figure(fig, save_name)

    return ax


def plot_feature_boxplots(df, features, target='AKI分组',
                           n_cols=4, save_name='feature_boxplots.png'):
    """Grid of boxplots for multiple features by target group."""
    n_features = len(features)
    n_rows = (n_features + n_cols - 1) // n_cols

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(n_cols * 4, n_rows * 3.5))
    if n_features == 1:
        axes = np.array([axes])
    axes = axes.flatten()

    colors = ['#3498db', '#e74c3c']

    for i, feature in enumerate(features):
        bp = df.boxplot(column=feature, by=target, ax=axes[i],
                         patch_artist=True, return_type='dict')
        for patch, color in zip(axes[i].patches, colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.6)
        axes[i].set_title(feature, fontsize=10, fontweight='bold')
        axes[i].set_xlabel('')
        axes[i].set_ylabel('')

    for j in range(i + 1, len(axes)):
        axes[j].set_visible(False)

    fig.suptitle('Feature Distributions by AKI Group', fontsize=14, fontweight='bold', y=1.01)
    plt.tight_layout()
    save_figure(fig, save_name)


def plot_correlation_heatmap(df, features=None, top_n=30, method='pearson',
                              save_name='correlation_heatmap.png'):
    """Plot correlation heatmap for top features."""
    if features is None:
        features = df.select_dtypes(include=[np.number]).columns.tolist()
        # Remove target columns
        features = [f for f in features if f not in ['AKI分组', 'AKI分期']]

    # Take top_n features with highest variance
    variances = df[features].var().sort_values(ascending=False)
    top_features = variances.head(top_n).index.tolist()

    corr = df[top_features].corr(method=method)

    fig, ax = plt.subplots(figsize=(min(top_n * 0.35, 20), min(top_n * 0.35, 20)))
    mask = np.triu(np.ones_like(corr, dtype=bool), k=1)

    cmap = sns.diverging_palette(240, 10, as_cmap=True)
    sns.heatmap(corr, mask=mask, cmap=cmap, center=0, annot=False,
                square=True, linewidths=0.5, ax=ax,
                cbar_kws={'shrink': 0.5, 'label': 'Correlation'})

    ax.set_title(f'Feature Correlation Heatmap (Top {top_n} Features)', fontsize=14, fontweight='bold')
    ax.tick_params(axis='both', labelsize=7)
    plt.tight_layout()
    save_figure(fig, save_name)

    # Find high correlations
    high_corr_pairs = []
    for i in range(len(corr.columns)):
        for j in range(i):
            if abs(corr.iloc[i, j]) > 0.8:
                high_corr_pairs.append({
                    'Feature_1': corr.columns[j],
                    'Feature_2': corr.columns[i],
                    'Correlation': round(corr.iloc[i, j], 3)
                })

    if high_corr_pairs:
        high_corr_df = pd.DataFrame(high_corr_pairs)
        save_table(high_corr_df, 'high_correlation_pairs.csv')
        logger.info(f"Found {len(high_corr_pairs)} highly correlated pairs (|r| > 0.8)")

    return corr


# ============================================
# Missing Value Visualization
# ============================================
def plot_missing_matrix(df, save_name='missing_matrix.png'):
    """Plot missing value matrix using missingno."""
    try:
        import missingno as msno
        fig, ax = plt.subplots(figsize=(16, 8))
        msno.matrix(df, ax=ax, sparkline=False)
        ax.set_title('Missing Value Matrix', fontsize=14, fontweight='bold')
        save_figure(fig, save_name)
    except ImportError:
        logger.warning("missingno not installed. Skipping missing matrix plot.")


def plot_missing_bar(df, save_name='missing_bar.png'):
    """Plot missing value bar chart."""
    missing = df.isnull().sum()
    missing = missing[missing > 0].sort_values(ascending=False)

    if len(missing) == 0:
        logger.info("No missing values found.")
        return

    fig, ax = plt.subplots(figsize=(12, max(5, len(missing) * 0.3)))
    bars = ax.barh(range(len(missing)), missing.values / len(df) * 100, color='#e74c3c')
    ax.set_yticks(range(len(missing)))
    ax.set_yticklabels(missing.index)
    ax.set_xlabel('Missing Percentage (%)')
    ax.set_title('Missing Value Percentage by Column', fontsize=14, fontweight='bold')
    ax.invert_yaxis()

    for bar, pct in zip(bars, missing.values / len(df) * 100):
        ax.text(bar.get_width() + 0.3, bar.get_y() + bar.get_height() / 2,
                f'{pct:.1f}%', va='center', fontsize=8)

    save_figure(fig, save_name)


def plot_missing_heatmap(df, save_name='missing_heatmap.png'):
    """Plot missing value correlation heatmap."""
    try:
        import missingno as msno
        fig, ax = plt.subplots(figsize=(16, 10))
        msno.heatmap(df, ax=ax)
        ax.set_title('Missing Value Correlation Heatmap', fontsize=14, fontweight='bold')
        save_figure(fig, save_name)
    except ImportError:
        logger.warning("missingno not installed. Skipping missing heatmap.")


# ============================================
# Target Analysis
# ============================================
def plot_target_pie(y, labels=None, save_name='target_pie.png'):
    """Pie chart of target distribution."""
    if labels is None:
        labels = ['Non-AKI', 'AKI']

    counts = y.value_counts().sort_index()
    colors = ['#3498db', '#e74c3c']

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    # Pie chart
    wedges, texts, autotexts = ax1.pie(
        counts.values, labels=labels, autopct='%1.1f%%',
        colors=colors, startangle=90, explode=(0, 0.05)
    )
    for autotext in autotexts:
        autotext.set_fontweight('bold')
        autotext.set_fontsize(11)
    ax1.set_title('AKI Distribution', fontsize=14, fontweight='bold')

    # Bar chart
    bars = ax2.bar(labels, counts.values, color=colors, edgecolor='white', linewidth=1.5)
    for bar, count in zip(bars, counts.values):
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                 f'n={count}\n({count / len(y) * 100:.1f}%)',
                 ha='center', fontweight='bold')
    ax2.set_ylabel('Number of Patients')
    ax2.set_title('AKI Patient Count', fontsize=14, fontweight='bold')

    plt.tight_layout()
    save_figure(fig, save_name)


# ============================================
# Feature Importance Visualization
# ============================================
def plot_feature_importance(importance_df, top_n=20, title='Feature Importance',
                             save_name='feature_importance.png'):
    """Horizontal bar chart of feature importance."""
    importance_df = importance_df.sort_values('importance', ascending=True).tail(top_n)

    fig, ax = plt.subplots(figsize=(10, max(6, len(importance_df) * 0.35)))
    colors = plt.cm.Blues(np.linspace(0.4, 0.9, len(importance_df)))

    bars = ax.barh(range(len(importance_df)), importance_df['importance'].values, color=colors)
    ax.set_yticks(range(len(importance_df)))
    ax.set_yticklabels(importance_df['feature'].values)
    ax.set_xlabel('Importance')
    ax.set_title(title, fontsize=14, fontweight='bold')

    for bar, val in zip(bars, importance_df['importance'].values):
        ax.text(bar.get_width() + 0.002, bar.get_y() + bar.get_height() / 2,
                f'{val:.4f}', va='center', fontsize=8)

    save_figure(fig, save_name)


# ============================================
# Time-based Analysis
# ============================================
def plot_temporal_analysis(df, time_cols, target='AKI分组',
                            save_name='temporal_analysis.png'):
    """Plot temporal trends (e.g., lab values over time) by AKI group."""
    n_cols = min(3, len(time_cols))
    n_rows = (len(time_cols) + n_cols - 1) // n_cols

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(n_cols * 5, n_rows * 4))
    if len(time_cols) == 1:
        axes = np.array([axes])
    axes = axes.flatten()

    colors = ['#3498db', '#e74c3c']
    time_points = ['Pre-op', 'Post-op', '48h Post-op', '7d Post-op']

    for i, base_col in enumerate(time_cols):
        # Try to find all time points for this variable
        time_data = []
        for tp_label in [f'术前{base_col}', f'术后{base_col}', f'术后48h{base_col}', f'术后7d{base_col}']:
            if tp_label in df.columns:
                time_data.append(tp_label)

        if len(time_data) < 2:
            axes[i].text(0.5, 0.5, f'Insufficient time points\nfor {base_col}',
                        ha='center', va='center', transform=axes[i].transAxes)
            continue

        for group in [0, 1]:
            group_data = df[df[target] == group]
            means = [group_data[t].mean() for t in time_data]
            stds = [group_data[t].std() for t in time_data]
            x = range(len(time_data))
            label = 'Non-AKI' if group == 0 else 'AKI'
            axes[i].errorbar(x, means, yerr=stds, marker='o', linewidth=2,
                            markersize=8, capsize=5, color=colors[group],
                            label=label)

        axes[i].set_xticks(range(len(time_data)))
        axes[i].set_xticklabels([t.replace(base_col, '') for t in time_data], rotation=30)
        axes[i].set_title(base_col, fontweight='bold')
        axes[i].legend(fontsize=8)
        axes[i].grid(True, alpha=0.3)

    for j in range(i + 1, len(axes)):
        axes[j].set_visible(False)

    fig.suptitle('Temporal Trends of Key Variables by AKI Group', fontsize=14, fontweight='bold', y=1.01)
    plt.tight_layout()
    save_figure(fig, save_name)


# ============================================
# Multi-model Comparison Radar Chart
# ============================================
def plot_radar_chart(model_scores, metrics, save_name='radar_chart.png'):
    """
    Radar/spider chart comparing models across multiple metrics.

    Args:
        model_scores: {model_name: {metric: score, ...}}
        metrics: List of metric names
    """
    from math import pi

    n_metrics = len(metrics)
    angles = [n / float(n_metrics) * 2 * pi for n in range(n_metrics)]
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))

    colors = plt.cm.tab10(np.linspace(0, 1, len(model_scores)))

    for (model_name, scores), color in zip(model_scores.items(), colors):
        values = [scores.get(m, 0) for m in metrics]
        values += values[:1]
        ax.plot(angles, values, 'o-', linewidth=2, color=color, label=model_name, markersize=5)
        ax.fill(angles, values, alpha=0.1, color=color)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(metrics, fontsize=10)
    ax.set_ylim(0, 1)
    ax.set_yticks([0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_yticklabels(['0.2', '0.4', '0.6', '0.8', '1.0'], fontsize=7)
    ax.set_title('Model Performance Comparison', fontsize=14, fontweight='bold', pad=20)
    ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1), fontsize=8)

    save_figure(fig, save_name)


# ============================================
# Demographics Visualization
# ============================================
def plot_demographics(df, demo_cols, target='AKI分组',
                       save_name='demographics.png'):
    """Plot demographic variable distributions."""
    n_cols = min(3, len(demo_cols))
    n_rows = (len(demo_cols) + n_cols - 1) // n_cols

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(n_cols * 5, n_rows * 4))
    if len(demo_cols) == 1:
        axes = np.array([axes])
    axes = axes.flatten()

    for i, col in enumerate(demo_cols):
        if col not in df.columns:
            continue
        if df[col].nunique() <= 5:  # Categorical
            ct = pd.crosstab(df[col], df[target], normalize='index')
            ct.plot(kind='bar', ax=axes[i], color=['#3498db', '#e74c3c'], alpha=0.8)
            axes[i].set_ylabel('Proportion')
        else:
            for group, color in zip([0, 1], ['#3498db', '#e74c3c']):
                data = df[df[target] == group][col].dropna()
                axes[i].hist(data, bins=20, alpha=0.5, color=color,
                            label=f'AKI' if group == 1 else 'Non-AKI', density=True)
            axes[i].legend(fontsize=8)

        axes[i].set_title(col, fontweight='bold')
        axes[i].set_xlabel('')

    for j in range(i + 1, len(axes)):
        axes[j].set_visible(False)

    fig.suptitle('Demographic Variables by AKI Group', fontsize=14, fontweight='bold', y=1.01)
    plt.tight_layout()
    save_figure(fig, save_name)


print("General visualization module loaded successfully.")

# -*- coding: utf-8 -*-
"""
Generate ensemble comparison figure (Voting vs Stacking vs Blending)
from advanced_fixed_cv.csv (25-fold CV results).

Usage:
    python scripts/generate_ensemble_fig.py
"""
import matplotlib
matplotlib.use('Agg')
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils.helpers import FIGURES_DIR, TABLES_DIR, save_figure

HIGHLIGHT = '#e74c3c'
BASE_COLOR = '#5DADE2'


def main():
    df = pd.read_csv(TABLES_DIR / 'advanced_fixed_cv.csv')
    df = df.sort_values('AUC均值', ascending=False).reset_index(drop=True)

    fig, ax = plt.subplots(figsize=(11, 7))
    fig.patch.set_facecolor('#F8F9FA')
    ax.set_facecolor('#F8F9FA')

    colors = [HIGHLIGHT if name == 'Voting' else BASE_COLOR for name in df['配置']]
    x = np.arange(len(df))

    bars = ax.bar(x, df['AUC均值'], yerr=df['AUC标准差'],
                  capsize=5, color=colors, edgecolor='white', alpha=0.92,
                  error_kw=dict(ecolor='#666666', lw=1.2), width=0.62)

    for xi, (_, row) in zip(x, df.iterrows()):
        y_pos = row['AUC均值'] + row['AUC标准差'] + 0.004
        txt_color = HIGHLIGHT if row['配置'] == 'Voting' else '#333333'
        ax.text(float(xi), float(y_pos), f"{row['AUC均值']:.4f}\u00b1{row['AUC标准差']:.4f}",
                ha='center', va='bottom', fontsize=10, color=txt_color, fontweight='bold' if row['配置'] == 'Voting' else 'normal')

    best_auc = df['AUC均值'].max()
    ax.axhline(best_auc, color=HIGHLIGHT, ls='--', lw=1.1, alpha=0.45)
    ax.set_xticks(x)
    ax.set_xticklabels(df['配置'], fontsize=11)
    ax.set_ylim(df['AUC均值'].min() - 0.08, df['AUC均值'].max() + 0.07)
    ax.set_xlabel('Ensemble Strategy', fontsize=12)
    ax.set_ylabel('AUC (Mean ± SD)', fontsize=12)
    ax.set_title('Ensemble Strategy Comparison \u2014 25-Fold CV (Voting Highlighted)',
                 fontsize=14, fontweight='bold', pad=18)
    ax.grid(True, axis='y', alpha=0.3, linewidth=0.5, color='#CCCCCC')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.text(0.02, 0.97,
            f"Best: Voting Ensemble AUC = {best_auc:.4f}",
            transform=ax.transAxes, fontsize=11, color=HIGHLIGHT, fontweight='bold',
            ha='left', va='top')

    fig.tight_layout()
    save_figure(fig, 'ensemble_comparison.png')
    print(f"[OK] ensemble_comparison.png saved -> {FIGURES_DIR / 'ensemble_comparison.png'}")


if __name__ == '__main__':
    main()

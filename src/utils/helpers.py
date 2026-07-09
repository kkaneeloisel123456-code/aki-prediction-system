"""
AKI Prediction Project - Utility Helpers
Common utility functions used across all modules.
"""
import os
import sys
import logging
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
import warnings
warnings.filterwarnings('ignore')

# ============================================
# Path Configuration
# ============================================
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / 'data'
RAW_DATA_DIR = DATA_DIR / 'raw'
PROCESSED_DATA_DIR = DATA_DIR / 'processed'
OUTPUT_DIR = PROJECT_ROOT / 'outputs'
FIGURES_DIR = OUTPUT_DIR / 'figures'
TABLES_DIR = OUTPUT_DIR / 'tables'
MODELS_DIR = PROJECT_ROOT / 'models'

# Ensure directories exist
for d in [PROCESSED_DATA_DIR, FIGURES_DIR, TABLES_DIR, MODELS_DIR]:
    d.mkdir(parents=True, exist_ok=True)


# ============================================
# Logging Setup
# ============================================
def setup_logging(name='aki_project', level=logging.INFO):
    """Setup logging configuration."""
    logging.basicConfig(
        level=level,
        format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    return logging.getLogger(name)


logger = setup_logging()


# ============================================
# Font Configuration for Chinese
# ============================================
def setup_chinese_font():
    """Configure matplotlib to support Chinese characters."""
    chinese_fonts = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS',
                     'WenQuanYi Micro Hei', 'Noto Sans CJK SC', 'PingFang SC']

    for font in chinese_fonts:
        try:
            matplotlib.font_manager.findfont(font, fallback_to_default=False)
            plt.rcParams['font.sans-serif'] = [font, 'DejaVu Sans']
            plt.rcParams['axes.unicode_minus'] = False
            logger.info(f"Using font: {font}")
            return font
        except Exception:
            continue

    # Fallback
    plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    logger.warning("No Chinese font found. Chinese characters may not render correctly.")
    return 'DejaVu Sans'


FONT = setup_chinese_font()


# ============================================
# Plot Styling
# ============================================
def set_plot_style():
    """Set consistent plot styling."""
    plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'ggplot')
    plt.rcParams.update({
        'figure.dpi': 100,
        'savefig.dpi': 300,
        'savefig.bbox': 'tight',
        'figure.figsize': (10, 6),
        'font.size': 11,
        'axes.titlesize': 14,
        'axes.labelsize': 12,
        'legend.fontsize': 10,
    })


set_plot_style()


# ============================================
# File I/O
# ============================================
def ensure_dir(path):
    """Ensure directory exists."""
    Path(path).mkdir(parents=True, exist_ok=True)


def save_figure(fig, filename, dpi=300, close=True):
    """Save figure to outputs/figures/."""
    filepath = FIGURES_DIR / filename
    ensure_dir(FIGURES_DIR)
    fig.savefig(str(filepath), dpi=dpi, bbox_inches='tight', facecolor='white')
    logger.info(f"Figure saved: {filepath}")
    if close:
        plt.close(fig)


def save_table(df, filename, index=False):
    """Save DataFrame to outputs/tables/."""
    filepath = TABLES_DIR / filename
    ensure_dir(TABLES_DIR)
    df.to_csv(str(filepath), index=index, encoding='utf-8-sig')
    logger.info(f"Table saved: {filepath}")


# ============================================
# Data Utilities
# ============================================
def get_numeric_columns(df, exclude=None):
    """Get numeric columns excluding specified ones."""
    exclude = exclude or []
    return [c for c in df.select_dtypes(include=[np.number]).columns if c not in exclude]


def get_categorical_columns(df, exclude=None):
    """Get categorical columns excluding specified ones."""
    exclude = exclude or []
    return [c for c in df.select_dtypes(include=['object', 'category']).columns if c not in exclude]


def identify_column_types(df):
    """Identify and classify all columns."""
    numeric_cols = []
    categorical_cols = []
    binary_cols = []
    id_cols = []

    for col in df.columns:
        if col in ['姓名', 'ID', 'id', '编号']:
            id_cols.append(col)
        elif df[col].dtype == 'object':
            categorical_cols.append(col)
        elif df[col].nunique() <= 2:
            binary_cols.append(col)
        else:
            numeric_cols.append(col)

    return {
        'numeric': numeric_cols,
        'categorical': categorical_cols,
        'binary': binary_cols,
        'id': id_cols
    }


# ============================================
# Statistical Utilities
# ============================================
from scipy import stats


def t_test_or_mannwhitney(group1, group2):
    """Auto-select t-test or Mann-Whitney U based on normality."""
    if len(group1) < 3 or len(group2) < 3:
        return np.nan
    # Use Shapiro-Wilk for normality test
    _, p1 = stats.shapiro(group1.dropna()) if len(group1.dropna()) >= 3 else (0, 0)
    _, p2 = stats.shapiro(group2.dropna()) if len(group2.dropna()) >= 3 else (0, 0)

    if p1 > 0.05 and p2 > 0.05:
        # Normal distribution → t-test
        stat, p = stats.ttest_ind(group1.dropna(), group2.dropna())
        test_name = 't-test'
    else:
        # Non-normal → Mann-Whitney U
        stat, p = stats.mannwhitneyu(group1.dropna(), group2.dropna(), alternative='two-sided')
        test_name = 'Mann-Whitney U'

    return p, test_name


def chi2_or_fisher(contingency_table):
    """Auto-select chi-square or Fisher's exact test."""
    try:
        if contingency_table.min().min() < 5:
            # Fisher's exact
            if contingency_table.shape == (2, 2):
                odds_ratio, p = stats.fisher_exact(contingency_table)
                return p, "Fisher's exact"
        # Chi-square
        chi2, p, dof, expected = stats.chi2_contingency(contingency_table)
        return p, 'Chi-square'
    except Exception:
        return np.nan, 'NA'


def format_pvalue(p, digits=4):
    """Format p-value for display."""
    if pd.isna(p):
        return 'NA'
    if p < 0.001:
        return '<0.001'
    return f'{p:.{digits}f}'


# ============================================
# Progress Utilities
# ============================================
def progress_bar(iterable, desc='Processing', **kwargs):
    """Wrapper for tqdm progress bar."""
    try:
        from tqdm import tqdm
        return tqdm(iterable, desc=desc, **kwargs)
    except ImportError:
        return iterable


print(f"Utils module loaded. Project root: {PROJECT_ROOT}")

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AKI (Acute Kidney Injury) Prediction — Data Cleaning Module
=============================================================

Comprehensive data cleaning pipeline for the AKI prediction project.

Data characteristics:
    - 420 rows, 97 columns
    - Target: AKI分组 (0=no AKI 295, 1=AKI 125), AKI分期 (0=295, 1=91, 2=24, 3=10)
    - 2 categorical: 姓名 (patient name — dropped), 手术类型 (6 types of surgery)
    - 性别: 1=男, 2=女
    - Only 3-4 columns with 1-2 missing values each (术前BE, 术前HCO3, 术后pH, 术后PaO2)
    - Rest are numeric lab values, demographics, surgery params, ICU data

Functions:
    1.  load_data                    — Read Excel file
    2.  drop_identifier_columns      — Remove non-predictive identifiers
    3.  check_missing_values         — Count & percentage of missing data
    4.  plot_missing_values          — missingno matrix / bar / heatmap
    5.  analyze_missing_mechanism    — Little's MCAR test
    6.  handle_missing_values        — Median / IterativeImputer
    7.  detect_outliers_iqr          — IQR-based outlier detection
    8.  detect_outliers_zscore       — Z-score outlier detection
    9.  handle_outliers              — Winsorize / cap at 1.5×IQR
    10. encode_categorical           — Label / OneHot encoding
    11. standardize_features         — StandardScaler / MinMaxScaler
    12. generate_data_dictionary     — Auto-generated data dictionary (CSV)
    13. generate_data_quality_report — Comprehensive quality report (TXT)
    14. run_full_cleaning_pipeline   — Orchestrate the entire workflow
"""

from __future__ import annotations

import logging
import os
import sys
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("aki_cleaning")

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# ---------------------------------------------------------------------------
# Chinese-friendly font setup
# ---------------------------------------------------------------------------
# Try SimHei (Windows), then Arial Unicode MS, then fall back to sans-serif
_CHINESE_FONTS = ["SimHei", "Arial Unicode MS", "Microsoft YaHei", "WenQuanYi Micro Hei"]


def _setup_chinese_font() -> str:
    """Configure matplotlib to render Chinese characters and return the font name used."""
    available = {f.name for f in matplotlib.font_manager.fontManager.ttflist}
    chosen: Optional[str] = None
    for candidate in _CHINESE_FONTS:
        if candidate in available:
            chosen = candidate
            break
    if chosen is None:
        # Search for any CJK-capable font
        for f in matplotlib.font_manager.fontManager.ttflist:
            if any(kw in f.name for kw in ("CJK", "Noto Sans", "Source Han", "Noto Serif")):
                chosen = f.name
                break
    if chosen is None:
        chosen = "sans-serif"
        logger.warning("No CJK font found; Chinese characters in plots may appear as boxes.")

    matplotlib.rcParams["font.sans-serif"] = [chosen, "sans-serif"]
    matplotlib.rcParams["axes.unicode_minus"] = False
    logger.info("Matplotlib font set to '%s' for Chinese support.", chosen)
    return chosen


# Set font at import time
_CHINESE_FONT = _setup_chinese_font()

# ---------------------------------------------------------------------------
# Optional library imports (graceful fallback)
# ---------------------------------------------------------------------------
try:
    import missingno as msno

    _MISSINGNO_AVAILABLE = True
except ImportError:
    _MISSINGNO_AVAILABLE = False
    logger.warning("missingno is not installed. Install with: pip install missingno")

try:
    from sklearn.experimental import enable_iterative_imputer  # noqa: F401
    from sklearn.impute import IterativeImputer

    _ITERATIVE_IMPUTER_AVAILABLE = True
except ImportError:
    _ITERATIVE_IMPUTER_AVAILABLE = False
    logger.warning("sklearn.impute.IterativeImputer is not available.")

try:
    from sklearn.preprocessing import LabelEncoder, MinMaxScaler, StandardScaler

    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False
    logger.warning("scikit-learn is not fully available.")


# ===================================================================
# 1. load_data
# ===================================================================
def load_data(filepath: Union[str, Path]) -> pd.DataFrame:
    """Load the AKI dataset from an Excel file.

    Parameters
    ----------
    filepath : str or Path
        Path to the Excel file (``.xlsx``).

    Returns
    -------
    pd.DataFrame
        Loaded data.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    ValueError
        If the file cannot be parsed as an Excel workbook.
    """
    filepath = Path(filepath)
    logger.info("Loading data from: %s", filepath.resolve())

    if not filepath.exists():
        raise FileNotFoundError(f"Data file not found: {filepath.resolve()}")

    if not filepath.suffix.lower() in (".xlsx", ".xls"):
        logger.warning(
            "Expected an Excel file (.xlsx / .xls), got '%s'. Attempting to read anyway.",
            filepath.suffix,
        )

    try:
        df = pd.read_excel(filepath, engine="openpyxl")
    except Exception as exc:
        raise ValueError(f"Failed to parse Excel file: {exc}") from exc

    logger.info(
        "Loaded DataFrame: %d rows × %d columns", df.shape[0], df.shape[1]
    )
    return df


# ===================================================================
# 2. drop_identifier_columns
# ===================================================================
def drop_identifier_columns(
    df: pd.DataFrame, cols: Optional[List[str]] = None
) -> pd.DataFrame:
    """Drop identifier columns that should not be used as features.

    Parameters
    ----------
    df : pd.DataFrame
        Input data.
    cols : list of str, optional
        Column names to drop.  Defaults to ``['姓名']``.

    Returns
    -------
    pd.DataFrame
        DataFrame with the specified columns removed.
    """
    if cols is None:
        cols = ["姓名"]

    existing = [c for c in cols if c in df.columns]
    missing = [c for c in cols if c not in df.columns]

    if missing:
        logger.warning("Columns not found in DataFrame (skipped): %s", missing)

    if not existing:
        logger.info("No identifier columns to drop.")
        return df.copy()

    df_out = df.drop(columns=existing)
    logger.info("Dropped identifier columns: %s", existing)
    return df_out


# ===================================================================
# 3. check_missing_values
# ===================================================================
def check_missing_values(df: pd.DataFrame) -> Dict[str, Any]:
    """Compute missing-value counts and percentages for every column.

    Parameters
    ----------
    df : pd.DataFrame

    Returns
    -------
    dict
        Keys:
        - ``'missing_counts'`` : pd.Series — count of NaN per column.
        - ``'missing_percentages'`` : pd.Series — percentage of NaN per column.
        - ``'columns_with_missing'`` : list[str] — columns having at least one NaN.
        - ``'total_missing_cells'`` : int — total NaN cells in the DataFrame.
        - ``'total_cells'`` : int — total cells.
        - ``'overall_missing_pct'`` : float — percentage of all cells that are missing.
    """
    total_cells = df.size
    missing_counts = df.isnull().sum()
    missing_pcts = (missing_counts / len(df)) * 100.0
    cols_with_missing = missing_counts[missing_counts > 0].index.tolist()

    summary: Dict[str, Any] = {
        "missing_counts": missing_counts,
        "missing_percentages": missing_pcts,
        "columns_with_missing": cols_with_missing,
        "total_missing_cells": int(missing_counts.sum()),
        "total_cells": int(total_cells),
        "overall_missing_pct": float(missing_counts.sum() / total_cells * 100),
    }

    logger.info(
        "Missing values: %d / %d cells (%6.3f%%) across %d columns with missing data.",
        summary["total_missing_cells"],
        summary["total_cells"],
        summary["overall_missing_pct"],
        len(cols_with_missing),
    )
    if cols_with_missing:
        for col in cols_with_missing:
            cnt = int(missing_counts[col])
            pct = missing_pcts[col]
            logger.debug("  %s: %d missing (%6.3f%%)", col, cnt, pct)
    else:
        logger.info("  No missing values found in the dataset.")

    return summary


# ===================================================================
# 4. plot_missing_values
# ===================================================================
def plot_missing_values(
    df: pd.DataFrame, save_path: Union[str, Path] = "outputs/figures/"
) -> Dict[str, str]:
    """Generate and save missing-value diagnostic plots.

    Creates:
        - **Missingno matrix** — shows missing data patterns per row.
        - **Missingno bar chart** — missing proportion per column.
        - **Missingno heatmap** — correlation of missingness between columns.

    Parameters
    ----------
    df : pd.DataFrame
    save_path : str or Path
        Directory to save the figure files.

    Returns
    -------
    dict
        Mapping of plot names to their saved file paths.
    """
    save_path = Path(save_path)
    save_path.mkdir(parents=True, exist_ok=True)
    font = _CHINESE_FONT

    saved_files: Dict[str, str] = {}

    if not _MISSINGNO_AVAILABLE:
        logger.warning(
            "missingno not installed — skipping missing-value plots. "
            "Install with: pip install missingno"
        )
        return saved_files

    # Columns with missing values (for the heatmap we use all, but missingno
    # will handle the selection internally.)
    try:
        # ---- Matrix plot ----
        fig, ax = plt.subplots(figsize=(14, 6))
        msno.matrix(df, ax=ax, fontsize=10, color=(0.2, 0.4, 0.8))
        ax.set_title("Missing Data Matrix", fontsize=13, fontname=font)
        fig.tight_layout()
        matrix_path = save_path / "missing_matrix.png"
        fig.savefig(matrix_path, dpi=200, bbox_inches="tight")
        plt.close(fig)
        saved_files["matrix"] = str(matrix_path)
        logger.info("Saved missingno matrix: %s", matrix_path)

        # ---- Bar chart ----
        fig, ax = plt.subplots(figsize=(14, 5))
        msno.bar(df, ax=ax, fontsize=10, color=(0.2, 0.6, 0.4))
        ax.set_title("Missing Value Proportions per Column", fontsize=13, fontname=font)
        fig.tight_layout()
        bar_path = save_path / "missing_bar.png"
        fig.savefig(bar_path, dpi=200, bbox_inches="tight")
        plt.close(fig)
        saved_files["bar"] = str(bar_path)
        logger.info("Saved missingno bar: %s", bar_path)

        # ---- Heatmap (correlation of missingness) ----
        fig, ax = plt.subplots(figsize=(12, 10))
        msno.heatmap(df, ax=ax, fontsize=10, cmap="RdBu")
        ax.set_title("Missingness Correlation Heatmap", fontsize=13, fontname=font)
        fig.tight_layout()
        heatmap_path = save_path / "missing_heatmap.png"
        fig.savefig(heatmap_path, dpi=200, bbox_inches="tight")
        plt.close(fig)
        saved_files["heatmap"] = str(heatmap_path)
        logger.info("Saved missingno heatmap: %s", heatmap_path)

    except Exception as exc:
        logger.error("Failed to generate missing-value plots: %s", exc)
        return saved_files

    return saved_files


# ===================================================================
# 5. analyze_missing_mechanism  (Little's MCAR test)
# ===================================================================
def analyze_missing_mechanism(
    df: pd.DataFrame, target: str = "AKI分组"
) -> Dict[str, Any]:
    """Perform Little's Missing Completely At Random (MCAR) test.

    The null hypothesis is that data are MCAR.  A *p*-value < 0.05 suggests
    the missingness mechanism is **not** MCAR (i.e., MAR or MNAR).

    The implementation follows the classic multivariate test described by
    Little (1988), computing a chi-squared statistic from the deviation of
    group means (grouped by missing-data pattern) from the grand mean.

    Parameters
    ----------
    df : pd.DataFrame
    target : str
        Name of the target column, which is excluded from the test.

    Returns
    -------
    dict
        Keys:
        - ``'test_name'`` : "Little's MCAR Test"
        - ``'chi_square'`` : float — test statistic.
        - ``'degrees_of_freedom'`` : int — approximate degrees of freedom.
        - ``'p_value'`` : float — p-value.
        - ``'is_mcar'`` : bool — True if p >= 0.05 (fail to reject MCAR).
        - ``'interpretation'`` : str — plain-text explanation.
        - ``'n_patterns'`` : int — number of distinct missing-data patterns found.
        - ``'pattern_counts'`` : dict — pattern → row count (only non-zero patterns).
    """
    logger.info("Performing Little's MCAR test (target excluded: '%s')", target)

    # Prepare data: drop target for test, keep only numeric columns
    cols_for_test = [c for c in df.columns if c != target]
    df_num = df[cols_for_test].select_dtypes(include=[np.number])

    if df_num.empty:
        return {
            "test_name": "Little's MCAR Test",
            "chi_square": 0.0,
            "degrees_of_freedom": 0,
            "p_value": 1.0,
            "is_mcar": True,
            "interpretation": "No numeric columns available — skipping test.",
            "n_patterns": 0,
            "pattern_counts": {},
        }

    n, p = df_num.shape
    logger.debug("Little's MCAR test on %d rows × %d numeric columns", n, p)

    # ---- Missing-data pattern grouping ----
    indicator = df_num.notna().astype(int)
    pattern_keys = indicator.astype(str).apply("".join, axis=1)
    unique_patterns = pattern_keys.unique()

    pattern_counts: Dict[str, int] = {}
    groups: Dict[str, pd.DataFrame] = {}

    for pat in unique_patterns:
        mask = pattern_keys == pat
        cnt = int(mask.sum())
        if cnt == 0:
            continue
        short_pat = f"pattern_{len(groups)}" if len(pat) > 20 else pat
        pattern_counts[short_pat] = cnt
        groups[pat] = df_num.loc[mask.values, :]

    # Compute pooled (pairwise) grand mean
    grand_means = df_num.mean(skipna=True).values  # shape (p,)

    # Compute pooled covariance matrix from the fully-observed rows (if available)
    full_obs_pat = "1" * p
    if full_obs_pat in groups:
        pooled_cov = groups[full_obs_pat].cov().values.copy()
        # Regularize
        pooled_cov += np.eye(p) * 1e-8
    else:
        # Use the overall pairwise covariance as fallback
        pooled_cov = df_num.cov().values.copy()
        pooled_cov = np.nan_to_num(pooled_cov) + np.eye(p) * 1e-8

    # ---- Compute test statistic ----
    chi_sq = 0.0
    total_obs_params = 0

    for pat, group_df in groups.items():
        pat_arr = np.array([int(ch) for ch in pat])
        observed_cols = np.where(pat_arr == 1)[0]
        n_g = len(group_df)

        if len(observed_cols) == 0 or n_g < 2:
            # Skip patterns with insufficient rows for covariance estimation
            continue

        # Group mean on observed columns
        group_means = group_df.iloc[:, observed_cols].mean(skipna=True).values

        # Extract sub-matrix of the pooled covariance for observed columns
        obs_idx = np.ix_(observed_cols, observed_cols)
        sub_cov = pooled_cov[obs_idx]

        # Regularized pseudo-inverse
        try:
            inv_cov = np.linalg.pinv(sub_cov)
        except np.linalg.LinAlgError:
            inv_cov = np.linalg.pinv(
                sub_cov + np.eye(len(observed_cols)) * 1e-6
            )

        diff = group_means - grand_means[observed_cols]
        chi_sq += n_g * float(diff @ inv_cov @ diff)
        total_obs_params += len(observed_cols)

    # Approximate degrees of freedom for Little's test:
    #   dof = sum(#observed cols per pattern) - p
    #   where p is the total number of variables.
    n_patterns = len(groups)
    dof_adjusted = total_obs_params - p if total_obs_params > p else 1

    if dof_adjusted <= 0:
        dof_adjusted = 1

    p_value = 1.0 - stats.chi2.cdf(chi_sq, dof_adjusted)
    is_mcar = p_value >= 0.05

    interpretation = (
        "Fail to reject H0 — data are consistent with MCAR (p ≥ 0.05)."
        if is_mcar
        else "Reject H0 — missingness is NOT MCAR (p < 0.05); MAR or MNAR likely."
    )

    result: Dict[str, Any] = {
        "test_name": "Little's MCAR Test",
        "chi_square": round(float(chi_sq), 4),
        "degrees_of_freedom": int(dof_adjusted),
        "p_value": round(float(p_value), 6),
        "is_mcar": bool(is_mcar),
        "interpretation": interpretation,
        "n_patterns": n_patterns,
        "pattern_counts": pattern_counts,
    }

    logger.info(
        "Little's MCAR test: χ²=%.4f, df=%d, p=%.6f → %s",
        chi_sq,
        dof_adjusted,
        p_value,
        "MCAR" if is_mcar else "NOT MCAR (MAR/MNAR)",
    )

    return result


# ===================================================================
# 6. handle_missing_values
# ===================================================================
def handle_missing_values(
    df: pd.DataFrame,
    strategy: str = "median",
    threshold: float = 0.05,
    random_state: int = 42,
) -> pd.DataFrame:
    """Impute missing values in the DataFrame.

    For columns with missing proportion **below** *threshold* → simple imputation
    using ``median``, ``mean``, or ``mode``.

    For columns with missing proportion **above or equal to** *threshold* →
    multiple imputation via ``IterativeImputer`` (scikit-learn).

    Parameters
    ----------
    df : pd.DataFrame
    strategy : {'median', 'mean', 'mode'}
        Imputation method for low-missingness columns.
    threshold : float
        Fraction above which the column is treated as high-missingness.
        Default 0.05 (5%).
    random_state : int
        Random seed for IterativeImputer.

    Returns
    -------
    pd.DataFrame
        DataFrame with missing values imputed (column order preserved).

    Raises
    ------
    ValueError
        If *strategy* is not one of the allowed values.
    """
    allowed = {"median", "mean", "mode"}
    if strategy not in allowed:
        raise ValueError(f"strategy must be one of {allowed}, got '{strategy}'.")

    df_out = df.copy()
    n = len(df_out)

    # Numeric columns only for imputation
    numeric_cols = df_out.select_dtypes(include=[np.number]).columns.tolist()
    missing_pcts = df_out[numeric_cols].isnull().mean()

    low_missing = missing_pcts[(missing_pcts > 0) & (missing_pcts < threshold)].index.tolist()
    high_missing = missing_pcts[missing_pcts >= threshold].index.tolist()

    logger.info(
        "Missing-value imputation: low-missing (%s) cols=%d, high-missing (%s) cols=%d.",
        strategy,
        len(low_missing),
        "IterativeImputer",
        len(high_missing),
    )

    # ---- Low-missingness: simple imputation ----
    if low_missing:
        for col in low_missing:
            if strategy == "median":
                fill_val = df_out[col].median()
            elif strategy == "mean":
                fill_val = df_out[col].mean()
            else:  # mode
                mode_vals = df_out[col].mode(dropna=True)
                fill_val = mode_vals.iloc[0] if not mode_vals.empty else np.nan

            n_missing = df_out[col].isnull().sum()
            df_out[col] = df_out[col].fillna(fill_val)
            logger.debug(
                "  Imputed '%s' (%s, %d missing → %.4f)",
                col,
                strategy,
                n_missing,
                fill_val,
            )

    # ---- High-missingness: IterativeImputer ----
    if high_missing:
        if not _ITERATIVE_IMPUTER_AVAILABLE:
            logger.warning(
                "IterativeImputer not available. Falling back to '%s' for columns: %s",
                strategy,
                high_missing,
            )
            for col in high_missing:
                if strategy == "median":
                    fill_val = df_out[col].median()
                elif strategy == "mean":
                    fill_val = df_out[col].mean()
                else:
                    mode_vals = df_out[col].mode(dropna=True)
                    fill_val = mode_vals.iloc[0] if not mode_vals.empty else np.nan
                df_out[col] = df_out[col].fillna(fill_val)
        else:
            # IterativeImputer expects all-numeric input
            imputer = IterativeImputer(
                random_state=random_state,
                max_iter=10,
                initial_strategy=strategy,
            )
            # Impute on the subset of numeric columns (including low-missing ones
            # for better estimation)
            all_impute_cols = numeric_cols
            imputed_array = imputer.fit_transform(df_out[all_impute_cols])
            df_out[all_impute_cols] = imputed_array
            logger.info(
                "IterativeImputer applied to %d columns with %d iterations.",
                len(all_impute_cols),
                imputer.n_iter_ if hasattr(imputer, "n_iter_") else "?",
            )

    # Check for any remaining NaN
    remaining = df_out.isnull().sum().sum()
    if remaining > 0:
        logger.warning(
            "There are still %d missing cells after imputation — using forward-fill.",
            remaining,
        )
        df_out = df_out.ffill().bfill()  # last resort

    logger.info("Missing-value imputation complete.")
    return df_out


# ===================================================================
# 7. detect_outliers_iqr
# ===================================================================
def detect_outliers_iqr(
    df: pd.DataFrame, exclude_cols: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Detect outliers using the Interquartile Range (IQR) method.

    Outlier definition: value < Q1 - 1.5×IQR **or** value > Q3 + 1.5×IQR.

    Parameters
    ----------
    df : pd.DataFrame
    exclude_cols : list of str, optional
        Columns to skip (e.g. target, identifiers, categoricals).

    Returns
    -------
    dict
        Keys:
        - ``'outlier_counts'`` : dict — column name → total outlier count.
        - ``'outlier_percentages'`` : dict — column name → % of rows that are outliers.
        - ``'total_outliers'`` : int.
        - ``'total_cells_checked'`` : int.
        - ``'overall_outlier_pct'`` : float.
        - ``'outlier_details'`` : dict — column → dict with 'lower_bound',
          'upper_bound', 'below_lower', 'above_upper'.
    """
    if exclude_cols is None:
        exclude_cols = []

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    cols_to_check = [c for c in numeric_cols if c not in exclude_cols]

    outlier_counts: Dict[str, int] = {}
    outlier_pcts: Dict[str, float] = {}
    details: Dict[str, Dict[str, float]] = {}

    total_outliers = 0
    total_cells = 0

    for col in cols_to_check:
        series = df[col].dropna()
        if len(series) < 4:
            continue  # too few observations for meaningful IQR

        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        iqr = q3 - q1

        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr

        below = (series < lower).sum()
        above = (series > upper).sum()
        n_out = below + above
        pct_out = n_out / len(series) * 100.0

        outlier_counts[col] = int(n_out)
        outlier_pcts[col] = round(float(pct_out), 2)
        details[col] = {
            "lower_bound": round(float(lower), 4),
            "upper_bound": round(float(upper), 4),
            "below_lower": int(below),
            "above_upper": int(above),
            "q1": round(float(q1), 4),
            "q3": round(float(q3), 4),
            "iqr": round(float(iqr), 4),
        }
        total_outliers += n_out
        total_cells += len(series)

    overall_pct = (total_outliers / total_cells * 100.0) if total_cells > 0 else 0.0

    result: Dict[str, Any] = {
        "outlier_counts": outlier_counts,
        "outlier_percentages": outlier_pcts,
        "total_outliers": total_outliers,
        "total_cells_checked": total_cells,
        "overall_outlier_pct": round(float(overall_pct), 2),
        "outlier_details": details,
    }

    logger.info(
        "IQR outlier detection: %d outliers in %d cells checked (%6.3f%%).",
        total_outliers,
        total_cells,
        overall_pct,
    )
    top_cols = sorted(outlier_counts.items(), key=lambda x: -x[1])[:5]
    if top_cols:
        logger.info("  Top-5 columns with outliers: %s", top_cols)

    return result


# ===================================================================
# 8. detect_outliers_zscore
# ===================================================================
def detect_outliers_zscore(
    df: pd.DataFrame,
    exclude_cols: Optional[List[str]] = None,
    threshold: float = 3.0,
) -> Dict[str, Any]:
    """Detect outliers using the Z-score method.

    Outlier definition: |Z-score| > *threshold* (default 3).

    Parameters
    ----------
    df : pd.DataFrame
    exclude_cols : list of str, optional
        Columns to skip.
    threshold : float
        Z-score threshold.  Default 3.0 (standard normal 99.7% coverage).

    Returns
    -------
    dict
        Keys:
        - ``'outlier_counts'`` : dict — column → count.
        - ``'outlier_percentages'`` : dict — column → %.
        - ``'total_outliers'`` : int.
        - ``'total_cells_checked'`` : int.
        - ``'overall_outlier_pct'`` : float.
        - ``'outlier_details'`` : dict — column → dict of boundary information.
    """
    if exclude_cols is None:
        exclude_cols = []

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    cols_to_check = [c for c in numeric_cols if c not in exclude_cols]

    outlier_counts: Dict[str, int] = {}
    outlier_pcts: Dict[str, float] = {}
    details: Dict[str, Dict[str, float]] = {}

    total_outliers = 0
    total_cells = 0

    for col in cols_to_check:
        series = df[col].dropna()
        if len(series) < 4:
            continue

        mean_val = series.mean()
        std_val = series.std(ddof=0)
        if std_val == 0:
            continue

        z_scores = (series - mean_val) / std_val
        n_out = int((np.abs(z_scores) > threshold).sum())
        pct_out = n_out / len(series) * 100.0

        outlier_counts[col] = n_out
        outlier_pcts[col] = round(float(pct_out), 2)
        details[col] = {
            "mean": round(float(mean_val), 4),
            "std": round(float(std_val), 4),
            "threshold": threshold,
            "upper_bound": round(float(mean_val + threshold * std_val), 4),
            "lower_bound": round(float(mean_val - threshold * std_val), 4),
        }
        total_outliers += n_out
        total_cells += len(series)

    overall_pct = (total_outliers / total_cells * 100.0) if total_cells > 0 else 0.0

    result: Dict[str, Any] = {
        "outlier_counts": outlier_counts,
        "outlier_percentages": outlier_pcts,
        "total_outliers": total_outliers,
        "total_cells_checked": total_cells,
        "overall_outlier_pct": round(float(overall_pct), 2),
        "outlier_details": details,
    }

    logger.info(
        "Z-score outlier detection (|Z| > %.1f): %d outliers in %d cells (%6.3f%%).",
        threshold,
        total_outliers,
        total_cells,
        overall_pct,
    )

    return result


# ===================================================================
# 9. handle_outliers
# ===================================================================
def handle_outliers(
    df: pd.DataFrame,
    method: str = "winsorize",
    exclude_cols: Optional[List[str]] = None,
) -> pd.DataFrame:
    """Handle outliers by winsorizing or capping.

    Parameters
    ----------
    df : pd.DataFrame
    method : {'winsorize', 'cap'}
        - ``'winsorize'``: Replace extreme values with the nearest non-extreme
          value at the 1.5×IQR boundary.
        - ``'cap'``: Clip values at the 1.5×IQR bounds.
    exclude_cols : list of str, optional
        Columns to skip.

    Returns
    -------
    pd.DataFrame
        DataFrame with outliers treated.

    Raises
    ------
    ValueError
        If *method* is not recognized.
    """
    if method not in ("winsorize", "cap"):
        raise ValueError(f"method must be 'winsorize' or 'cap', got '{method}'.")

    if exclude_cols is None:
        exclude_cols = []

    df_out = df.copy()
    numeric_cols = df_out.select_dtypes(include=[np.number]).columns.tolist()
    cols_to_treat = [c for c in numeric_cols if c not in exclude_cols]

    n_total_changed = 0

    for col in cols_to_treat:
        series = df_out[col].dropna()
        if len(series) < 4:
            continue

        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        iqr = q3 - q1

        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr

        col_data = df_out[col].values.copy()
        mask = ~np.isnan(col_data)

        if method == "cap":
            n_changed = int(((col_data[mask] < lower) | (col_data[mask] > upper)).sum())
            col_data[mask] = np.clip(col_data[mask], lower, upper)
        else:  # winsorize
            # Winsorize: replace with boundary values
            n_changed = int(((col_data[mask] < lower) | (col_data[mask] > upper)).sum())
            col_data[mask] = np.clip(col_data[mask], lower, upper)

        df_out[col] = col_data
        n_total_changed += n_changed

        if n_changed > 0:
            logger.debug("  %s (%s): %d values adjusted.", col, method, n_changed)

    logger.info("Outlier handling (%s): %d total values adjusted.", method, n_total_changed)
    return df_out


# ===================================================================
# 10. encode_categorical
# ===================================================================
def encode_categorical(
    df: pd.DataFrame,
    cols: Optional[List[str]] = None,
    method: str = "label",
    drop_first: bool = False,
) -> pd.DataFrame:
    """Encode categorical columns into numeric representations.

    Parameters
    ----------
    df : pd.DataFrame
    cols : list of str, optional
        Categorical columns to encode. If ``None``, object-dtype columns are
        automatically selected.
    method : {'label', 'onehot'}
        - ``'label'``: ``sklearn.preprocessing.LabelEncoder`` (0, 1, 2, …).
        - ``'onehot'``: ``pd.get_dummies(..., drop_first=drop_first)``.
    drop_first : bool
        Only relevant for ``'onehot'``.  Default ``False``.

    Returns
    -------
    pd.DataFrame
        DataFrame with encoded columns.

    Raises
    ------
    ValueError
        If *method* is not recognised or a column does not exist.
    """
    if method not in ("label", "onehot"):
        raise ValueError(f"method must be 'label' or 'onehot', got '{method}'.")

    if cols is None:
        cols = df.select_dtypes(include=["object", "category"]).columns.tolist()
        logger.info("Auto-selected categorical columns: %s", cols)

    missing_cols = [c for c in cols if c not in df.columns]
    if missing_cols:
        raise ValueError(f"Columns not found in DataFrame: {missing_cols}")

    if not cols:
        logger.info("No categorical columns to encode.")
        return df.copy()

    df_out = df.copy()
    encoding_map: Dict[str, Any] = {}

    if method == "label":
        if not _SKLEARN_AVAILABLE:
            logger.warning("scikit-learn not fully available — using pandas factorize.")
            for col in cols:
                codes, uniques = pd.factorize(df_out[col])
                df_out[col] = codes
                encoding_map[col] = dict(zip(range(len(uniques)), uniques))
        else:
            for col in cols:
                le = LabelEncoder()
                df_out[col] = le.fit_transform(df_out[col].astype(str))
                encoding_map[col] = dict(enumerate(le.classes_))
        logger.info("Label encoding applied to: %s", cols)

    else:  # onehot
        df_out = pd.get_dummies(df_out, columns=cols, drop_first=drop_first, prefix=cols)
        logger.info(
            "OneHot encoding applied to: %s (drop_first=%s)", cols, drop_first,
        )

    # Store encoding map as attribute on the returned DataFrame for reference
    df_out.attrs["encoding_map"] = encoding_map  # type: ignore[union-attr]

    return df_out


# ===================================================================
# 11. standardize_features
# ===================================================================
def standardize_features(
    df: pd.DataFrame,
    method: str = "standard",
    exclude_cols: Optional[List[str]] = None,
) -> pd.DataFrame:
    """Standardize or normalise numeric features.

    Parameters
    ----------
    df : pd.DataFrame
    method : {'standard', 'minmax'}
        - ``'standard'``: ``StandardScaler`` — zero mean, unit variance.
        - ``'minmax'``: ``MinMaxScaler`` — scale to [0, 1].
    exclude_cols : list of str, optional
        Columns to leave unchanged (e.g. target, encoded categories, IDs).

    Returns
    -------
    pd.DataFrame
        DataFrame with scaled features.

    Raises
    ------
    ValueError
        If *method* is not recognised.
    """
    if method not in ("standard", "minmax"):
        raise ValueError(f"method must be 'standard' or 'minmax', got '{method}'.")

    if exclude_cols is None:
        exclude_cols = []

    df_out = df.copy()
    numeric_cols = df_out.select_dtypes(include=[np.number]).columns.tolist()
    cols_to_scale = [c for c in numeric_cols if c not in exclude_cols]

    if not cols_to_scale:
        logger.info("No numeric columns to scale.")
        return df_out

    if not _SKLEARN_AVAILABLE:
        logger.warning("scikit-learn not available — using manual scaling.")
        if method == "standard":
            for col in cols_to_scale:
                mean_val = df_out[col].mean()
                std_val = df_out[col].std(ddof=0)
                if std_val > 0:
                    df_out[col] = (df_out[col] - mean_val) / std_val
        else:
            for col in cols_to_scale:
                cmin = df_out[col].min()
                cmax = df_out[col].max()
                if cmax > cmin:
                    df_out[col] = (df_out[col] - cmin) / (cmax - cmin)
    else:
        scaler = StandardScaler() if method == "standard" else MinMaxScaler()
        df_out[cols_to_scale] = scaler.fit_transform(df_out[cols_to_scale])

    logger.info("Feature scaling (%s) applied to %d columns.", method, len(cols_to_scale))
    return df_out


# ===================================================================
# 12. generate_data_dictionary
# ===================================================================
# Chinese column descriptions for the AKI dataset (auto-populated based on
# column name patterns).  This acts as a living map.
_COLUMN_DESCRIPTIONS: Dict[str, str] = {
    # Demographics
    "性别": "性别 (1=男, 2=女)",
    "年龄": "年龄 (岁)",
    "身高": "身高 (cm)",
    "体重": "体重 (kg)",
    "BMI": "身体质量指数 (kg/m²)",
    # Surgery type
    "手术类型": "手术类型 (分类变量)",
    # Pre-operative labs
    "术前WBC": "术前白细胞计数 (×10⁹/L)",
    "术前Hb": "术前血红蛋白 (g/L)",
    "术前PLT": "术前血小板计数 (×10⁹/L)",
    "术前HCT": "术前红细胞压积 (%)",
    "术前Cr": "术前肌酐 (μmol/L)",
    "术前BUN": "术前血尿素氮 (mmol/L)",
    "术前eGFR": "术前估算肾小球滤过率 (mL/min/1.73m²)",
    "术前ALT": "术前丙氨酸氨基转移酶 (U/L)",
    "术前AST": "术前天冬氨酸氨基转移酶 (U/L)",
    "术前TP": "术前总蛋白 (g/L)",
    "术前ALB": "术前白蛋白 (g/L)",
    "术前TBIL": "术前总胆红素 (μmol/L)",
    "术前DBIL": "术前直接胆红素 (μmol/L)",
    "术前IBIL": "术前间接胆红素 (μmol/L)",
    "术前K": "术前血钾 (mmol/L)",
    "术前Na": "术前血钠 (mmol/L)",
    "术前Cl": "术前血氯 (mmol/L)",
    "术前Ca": "术前血钙 (mmol/L)",
    "术前Mg": "术前血镁 (mmol/L)",
    "术前P": "术前血磷 (mmol/L)",
    "术前GLU": "术前血糖 (mmol/L)",
    "术前BE": "术前碱剩余 (mmol/L)",
    "术前HCO3": "术前碳酸氢根 (mmol/L)",
    "术前Lac": "术前乳酸 (mmol/L)",
    # Intra-operative
    "手术时长": "手术时长 (min)",
    "麻醉时长": "麻醉时长 (min)",
    "输液总量": "术中输液总量 (mL)",
    "出血量": "术中出血量 (mL)",
    "尿量": "术中尿量 (mL)",
    "输血量": "术中输血量 (mL)",
    "晶体液": "术中晶体液用量 (mL)",
    "胶体液": "术中胶体液用量 (mL)",
    "升压药": "术中升压药使用 (0=否, 1=是)",
    # Post-operative / ICU
    "术后WBC": "术后白细胞计数 (×10⁹/L)",
    "术后Hb": "术后血红蛋白 (g/L)",
    "术后PLT": "术后血小板计数 (×10⁹/L)",
    "术后HCT": "术后红细胞压积 (%)",
    "术后Cr": "术后肌酐 (μmol/L)",
    "术后BUN": "术后血尿素氮 (mmol/L)",
    "术后eGFR": "术后估算肾小球滤过率 (mL/min/1.73m²)",
    "术后ALT": "术后丙氨酸氨基转移酶 (U/L)",
    "术后AST": "术后天冬氨酸氨基转移酶 (U/L)",
    "术后TP": "术后总蛋白 (g/L)",
    "术后ALB": "术后白蛋白 (g/L)",
    "术后TBIL": "术后总胆红素 (μmol/L)",
    "术后DBIL": "术后直接胆红素 (μmol/L)",
    "术后IBIL": "术后间接胆红素 (μmol/L)",
    "术后K": "术后血钾 (mmol/L)",
    "术后Na": "术后血钠 (mmol/L)",
    "术后Cl": "术后血氯 (mmol/L)",
    "术后Ca": "术后血钙 (mmol/L)",
    "术后Mg": "术后血镁 (mmol/L)",
    "术后P": "术后血磷 (mmol/L)",
    "术后GLU": "术后血糖 (mmol/L)",
    "术后pH": "术后动脉血pH",
    "术后PaO2": "术后动脉血氧分压 (mmHg)",
    "术后PaCO2": "术后动脉血二氧化碳分压 (mmHg)",
    "术后BE": "术后碱剩余 (mmol/L)",
    "术后HCO3": "术后碳酸氢根 (mmol/L)",
    "术后Lac": "术后乳酸 (mmol/L)",
    "ICU时长": "ICU住院时长 (天)",
    "住院时长": "总住院时长 (天)",
    # Targets
    "AKI分组": "AKI分组 (0=无AKI, 1=AKI)",
    "AKI分期": "AKI分期 (0=无AKI, 1=1期, 2=2期, 3=3期)",
}


def _auto_describe_column(col: str, dtype: np.dtype) -> str:
    """Generate a Chinese description for a column not in the predefined map."""
    col_lower = col.lower()
    if np.issubdtype(dtype, np.number):
        if "时间" in col or "time" in col_lower:
            return f"{col} (时间相关变量, 数值)"
        if "评分" in col or "score" in col_lower:
            return f"{col} (评分, 数值)"
        if "率" in col or "ratio" in col_lower or "index" in col_lower:
            return f"{col} (比率/指数, 数值)"
        return f"{col} (数值变量)"
    if np.issubdtype(dtype, np.bool_):
        return f"{col} (二分类变量, 0/1)"
    if np.issubdtype(dtype, np.object_):
        return f"{col} (分类/文本变量)"
    return f"{col} (其他类型)"


def generate_data_dictionary(
    df: pd.DataFrame, save_path: Union[str, Path] = "outputs/tables/"
) -> pd.DataFrame:
    """Auto-generate a data dictionary and save it as CSV.

    The dictionary includes:
        - Column name
        - Data type
        - Non-null count
        - Unique count
        - Min / Max (numeric) or categories (categorical)
        - Mean ± SD (numeric)
        - Chinese description

    Parameters
    ----------
    df : pd.DataFrame
    save_path : str or Path
        Directory to save the CSV.

    Returns
    -------
    pd.DataFrame
        The data dictionary as a DataFrame.
    """
    save_path = Path(save_path)
    save_path.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, Any]] = []
    for col in df.columns:
        dtype = df[col].dtype
        is_numeric = np.issubdtype(dtype, np.number)
        n_nonnull = int(df[col].notna().sum())
        n_unique = int(df[col].nunique())
        desc = _COLUMN_DESCRIPTIONS.get(col, _auto_describe_column(col, dtype))

        row: Dict[str, Any] = {
            "列名": col,
            "数据类型": str(dtype),
            "非空计数": n_nonnull,
            "缺失计数": int(df[col].isnull().sum()),
            "唯一值数": n_unique,
        }

        if is_numeric:
            valid = df[col].dropna()
            if len(valid) > 0:
                row["最小值"] = round(float(valid.min()), 4)
                row["最大值"] = round(float(valid.max()), 4)
                row["平均值"] = round(float(valid.mean()), 4)
                row["标准差"] = round(float(valid.std(ddof=0)), 4)
                row["中位数"] = round(float(valid.median()), 4)
                row["Q1"] = round(float(valid.quantile(0.25)), 4)
                row["Q3"] = round(float(valid.quantile(0.75)), 4)
            else:
                row["最小值"] = row["最大值"] = row["平均值"] = row["标准差"] = row["中位数"] = \
                    row["Q1"] = row["Q3"] = None
        else:
            # Show top categories
            top_vals = df[col].value_counts(dropna=True).head(5).to_dict()
            row["常见值"] = str(top_vals) if top_vals else ""

        row["描述"] = desc
        rows.append(row)

    dict_df = pd.DataFrame(rows)
    csv_path = save_path / "data_dictionary.csv"
    dict_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    logger.info("Data dictionary saved to: %s (%d columns)", csv_path, len(dict_df))

    return dict_df


# ===================================================================
# 13. generate_data_quality_report
# ===================================================================
def generate_data_quality_report(
    df: pd.DataFrame, save_path: Union[str, Path] = "outputs/tables/"
) -> str:
    """Generate a comprehensive data-quality report and save as a text file.

    The report includes:
        - Dataset dimensions
        - Column types summary
        - Missing values summary
        - Outlier summary (IQR method, automatically generated)
        - Value range checks (any negative values where unexpected, constants, etc.)
        - Duplicate rows

    Parameters
    ----------
    df : pd.DataFrame
    save_path : str or Path
        Directory to save the report TXT file.

    Returns
    -------
    str
        Full report text.
    """
    save_path = Path(save_path)
    save_path.mkdir(parents=True, exist_ok=True)

    lines: List[str] = []
    sep = "=" * 72
    sub = "-" * 48

    # ---- Header ----
    lines.append(sep)
    lines.append("            AKI 数据质量报告 — Data Quality Report")
    lines.append(sep)
    lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"平台: {sys.platform}")
    lines.append("")

    # ---- 1. Dimensions ----
    lines.append(sub)
    lines.append("1. 数据集概览 (Dataset Overview)")
    lines.append(sub)
    lines.append(f"  行数 (Rows):        {df.shape[0]:>8d}")
    lines.append(f"  列数 (Columns):     {df.shape[1]:>8d}")
    lines.append(f"  总单元格 (Cells):   {df.size:>8d}")
    lines.append("")

    # ---- 2. Column types ----
    lines.append(sub)
    lines.append("2. 列类型分布 (Column Types)")
    lines.append(sub)
    type_counts = df.dtypes.value_counts()
    for dt, cnt in type_counts.items():
        lines.append(f"  {str(dt):20s} : {cnt:>4d}")
    lines.append("")

    # ---- 3. Missing values ----
    lines.append(sub)
    lines.append("3. 缺失值分析 (Missing Values)")
    lines.append(sub)
    missing = check_missing_values(df)
    lines.append(f"  总缺失单元格:     {missing['total_missing_cells']:>8d}")
    lines.append(f"  总单元格:         {missing['total_cells']:>8d}")
    lines.append(f"  总体缺失率:       {missing['overall_missing_pct']:>7.3f}%")
    lines.append(f"  含缺失的列数:     {len(missing['columns_with_missing']):>8d}")
    lines.append("")
    if missing["columns_with_missing"]:
        lines.append("  按列缺失详情:")
        for col in missing["columns_with_missing"]:
            cnt = int(missing["missing_counts"][col])
            pct = missing["missing_percentages"][col]
            lines.append(f"    {col:30s} : {cnt:>4d} missing ({pct:>5.2f}%)")
    else:
        lines.append("  数据集中无缺失值。")
    lines.append("")

    # ---- 4. Outlier detection (IQR) ----
    lines.append(sub)
    lines.append("4. 异常值检测 — IQR法 (Outliers via IQR)")
    lines.append(sub)
    outlier_info = detect_outliers_iqr(df, exclude_cols=["AKI分组", "AKI分期"])
    lines.append(f"  总异常值:         {outlier_info['total_outliers']:>8d}")
    lines.append(f"  总检测单元格:     {outlier_info['total_cells_checked']:>8d}")
    lines.append(f"  总体异常率:       {outlier_info['overall_outlier_pct']:>7.2f}%")
    lines.append("")
    # Top-10 columns by outlier count
    top_outliers = sorted(
        outlier_info["outlier_counts"].items(), key=lambda x: -x[1]
    )[:10]
    if top_outliers:
        lines.append("  异常值最多的10列:")
        lines.append(f"    {'列名':30s} {'异常数':>8s} {'异常率':>8s}")
        lines.append(f"    {'-'*30} {'-'*8} {'-'*8}")
        for col, cnt in top_outliers:
            pct = outlier_info["outlier_percentages"].get(col, 0)
            lines.append(f"    {col:30s} {cnt:>8d} {pct:>7.2f}%")
    lines.append("")

    # ---- 5. Range checks ----
    lines.append(sub)
    lines.append("5. 范围检查 (Range Checks)")
    lines.append(sub)
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    suspicious: List[str] = []
    for col in numeric_cols:
        s = df[col].dropna()
        if len(s) == 0:
            continue
        # Check for negative values in columns that should be non-negative
        if any(kw in col for kw in ("Hb", "PLT", "HCT", "eGFR", "身高", "体重", "时长", "输液", "尿量", "ICU", "住院")):
            neg = (s < 0).sum()
            if neg > 0:
                suspicious.append(f"  {col:30s}: {neg:>4d} negative value(s)")
        # Check for constants
        if s.nunique() == 1:
            suspicious.append(f"  {col:30s}: CONSTANT ({s.iloc[0]})")
        # Check for zero-only (or near-zero variance)
        if s.nunique() <= 2 and s.max() == s.min():
            suspicious.append(f"  {col:30s}: ZERO VARIANCE (min=max={s.iloc[0]})")
    if suspicious:
        for line in suspicious:
            lines.append(line)
    else:
        lines.append("  未发现明显异常的范围问题。")
    lines.append("")

    # ---- 6. Duplicate rows ----
    lines.append(sub)
    lines.append("6. 重复行检查 (Duplicate Rows)")
    lines.append(sub)
    n_dup = df.duplicated().sum()
    lines.append(f"  完全重复行数: {n_dup:>8d}")
    lines.append(f"  重复比例: {n_dup / max(len(df), 1) * 100:>7.2f}%")

    if n_dup > 0:
        # Check duplicates ignoring columns with all NaN
        df_no_nan_id = df.dropna(axis=1, how="all")
        n_dup_partial = df_no_nan_id.duplicated().sum()
        lines.append(f"  去全NaN列后重复: {n_dup_partial:>8d}")

    lines.append("")
    lines.append(sep)
    lines.append("报告结束 — End of Report")
    lines.append(sep)

    report_text = "\n".join(lines)

    # Save
    txt_path = save_path / "data_quality_report.txt"
    txt_path.write_text(report_text, encoding="utf-8")
    logger.info("Data quality report saved to: %s", txt_path)

    return report_text


# ===================================================================
# 14. run_full_cleaning_pipeline
# ===================================================================
def run_full_cleaning_pipeline(
    input_path: Union[str, Path],
    output_path: Union[str, Path] = "data/processed/",
    drop_cols: Optional[List[str]] = None,
    target_col: str = "AKI分组",
    missing_strategy: str = "median",
    missing_threshold: float = 0.05,
    outlier_method: str = "winsorize",
    encode_method: str = "label",
    scale_method: str = "standard",
    generate_report: bool = True,
    generate_dict: bool = True,
) -> Dict[str, Any]:
    """Run the full AKI data cleaning pipeline end-to-end.

    Steps
    -----
    1. Load data from Excel.
    2. Drop identifier columns.
    3. Check missing values.
    4. Analyze missing mechanism (Little's MCAR test).
    5. Plot missing values (if missingno available).
    6. Handle missing values.
    7. Detect outliers (IQR & Z-score).
    8. Handle outliers.
    9. Encode categorical columns.
    10. Standardize numeric features.
    11. Generate data dictionary (optional).
    12. Generate data quality report (optional).
    13. Save cleaned data.

    Parameters
    ----------
    input_path : str or Path
        Path to the raw Excel file.
    output_path : str or Path
        Directory to save the cleaned CSV and reports.
    drop_cols : list of str, optional
        Columns to drop early (default ``['姓名']``).
    target_col : str
        Target column name, excluded from scaling.
    missing_strategy : {'median', 'mean', 'mode'}
    missing_threshold : float
    outlier_method : {'winsorize', 'cap'}
    encode_method : {'label', 'onehot'}
    scale_method : {'standard', 'minmax'}
    generate_report : bool
        Whether to create the data quality report.
    generate_dict : bool
        Whether to create the data dictionary.

    Returns
    -------
    dict
        Summary of the pipeline execution: paths, timings, and key metrics.
    """
    if drop_cols is None:
        drop_cols = ["姓名"]

    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)
    figures_path = output_path.parent / "figures"
    tables_path = output_path.parent / "tables"

    pipeline_summary: Dict[str, Any] = {
        "input_path": str(input_path),
        "output_path": str(output_path),
        "start_time": datetime.now().isoformat(),
        "steps": {},
    }

    logger.info("=" * 60)
    logger.info("AKI Data Cleaning Pipeline — START")
    logger.info("=" * 60)

    # ---- 1. Load ----
    t0 = datetime.now()
    df = load_data(input_path)
    pipeline_summary["steps"]["load"] = {
        "shape": list(df.shape),
        "columns": list(df.columns),
        "time_s": (datetime.now() - t0).total_seconds(),
    }
    logger.info("Step 1/12 — Load: %d × %d", df.shape[0], df.shape[1])

    # ---- 2. Drop identifiers ----
    t0 = datetime.now()
    df = drop_identifier_columns(df, cols=drop_cols)
    pipeline_summary["steps"]["drop_identifiers"] = {
        "dropped": drop_cols,
        "time_s": (datetime.now() - t0).total_seconds(),
    }
    logger.info("Step 2/12 — Drop identifiers: %s", drop_cols)

    # ---- 3. Check missing ----
    t0 = datetime.now()
    missing_info = check_missing_values(df)
    pipeline_summary["steps"]["check_missing"] = {
        "total_missing": missing_info["total_missing_cells"],
        "overall_pct": missing_info["overall_missing_pct"],
        "time_s": (datetime.now() - t0).total_seconds(),
    }

    # ---- 4. Missing mechanism ----
    t0 = datetime.now()
    mech = analyze_missing_mechanism(df, target=target_col)
    pipeline_summary["steps"]["missing_mechanism"] = {
        "is_mcar": mech["is_mcar"],
        "p_value": mech["p_value"],
        "time_s": (datetime.now() - t0).total_seconds(),
    }
    logger.info("Step 4/12 — MCAR test: %s", "MCAR" if mech["is_mcar"] else "MAR/MNAR")

    # ---- 5. Plot missing ----
    t0 = datetime.now()
    plots = plot_missing_values(df, save_path=figures_path)
    pipeline_summary["steps"]["plot_missing"] = {
        "saved_files": plots,
        "time_s": (datetime.now() - t0).total_seconds(),
    }
    logger.info("Step 5/12 — Missing plots saved: %d", len(plots))

    # ---- 6. Handle missing ----
    t0 = datetime.now()
    df = handle_missing_values(df, strategy=missing_strategy, threshold=missing_threshold)
    pipeline_summary["steps"]["handle_missing"] = {
        "strategy": missing_strategy,
        "threshold": missing_threshold,
        "time_s": (datetime.now() - t0).total_seconds(),
    }
    logger.info("Step 6/12 — Missing values handled (%s)", missing_strategy)

    # ---- 7. Detect outliers ----
    t0 = datetime.now()
    exclude_oi = [target_col, "AKI分期"]
    if "AKI分期" in df.columns:
        exclude_oi.append("AKI分期")
    outlier_iqr = detect_outliers_iqr(df, exclude_cols=exclude_oi)
    outlier_z = detect_outliers_zscore(df, exclude_cols=exclude_oi, threshold=3.0)
    pipeline_summary["steps"]["detect_outliers"] = {
        "iqr_total": outlier_iqr["total_outliers"],
        "zscore_total": outlier_z["total_outliers"],
        "time_s": (datetime.now() - t0).total_seconds(),
    }
    logger.info(
        "Step 7/12 — Outliers: IQR=%d, Z-score=%d",
        outlier_iqr["total_outliers"],
        outlier_z["total_outliers"],
    )

    # ---- 8. Handle outliers ----
    t0 = datetime.now()
    df = handle_outliers(df, method=outlier_method, exclude_cols=exclude_oi)
    pipeline_summary["steps"]["handle_outliers"] = {
        "method": outlier_method,
        "time_s": (datetime.now() - t0).total_seconds(),
    }
    logger.info("Step 8/12 — Outliers handled (%s)", outlier_method)

    # ---- 9. Encode categorical ----
    t0 = datetime.now()
    # Identify categorical columns (exclude numeric-like & target)
    cat_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()
    if cat_cols:
        df = encode_categorical(df, cols=cat_cols, method=encode_method)
    pipeline_summary["steps"]["encode_categorical"] = {
        "columns": cat_cols,
        "method": encode_method,
        "time_s": (datetime.now() - t0).total_seconds(),
    }
    logger.info("Step 9/12 — Categorical encoding (%s): %s", encode_method, cat_cols)

    # ---- 9b. AKI Logic Validation (MUST run before standardization) ----
    t0 = datetime.now()
    logic_result = run_aki_logic_validation(df, output_path=tables_path)
    pipeline_summary["steps"]["aki_logic_validation"] = {
        "staging_flags": logic_result["staging_flags"],
        "group_stage_flags": logic_result["group_stage_flags"],
        "time_s": (datetime.now() - t0).total_seconds(),
    }
    logger.info(
        "Step 9b/12 — AKI logic validation: %d staging + %d group-stage issues.",
        logic_result["staging_flags"],
        logic_result["group_stage_flags"],
    )

    # ---- 10. Standardize ----
    t0 = datetime.now()
    exclude_scale = [target_col]
    if target_col in df.columns:
        exclude_scale.append(target_col)
    if "AKI分期" in df.columns:
        exclude_scale.append("AKI分期")
    # Also exclude any remaining object/bool columns
    exclude_scale += df.select_dtypes(include=["object", "bool"]).columns.tolist()
    exclude_scale = list(set(exclude_scale))

    df = standardize_features(df, method=scale_method, exclude_cols=exclude_scale)
    pipeline_summary["steps"]["standardize"] = {
        "method": scale_method,
        "excluded": exclude_scale,
        "time_s": (datetime.now() - t0).total_seconds(),
    }
    logger.info("Step 10/12 — Feature scaling (%s)", scale_method)

    # ---- 11. Data dictionary ----
    if generate_dict:
        t0 = datetime.now()
        _dict_df = generate_data_dictionary(df, save_path=tables_path)
        pipeline_summary["steps"]["data_dictionary"] = {
            "path": str(tables_path / "data_dictionary.csv"),
            "time_s": (datetime.now() - t0).total_seconds(),
        }
        logger.info("Step 11/12 — Data dictionary generated.")

    # ---- 12. Quality report ----
    if generate_report:
        t0 = datetime.now()
        _report = generate_data_quality_report(df, save_path=tables_path)
        pipeline_summary["steps"]["quality_report"] = {
            "path": str(tables_path / "data_quality_report.txt"),
            "time_s": (datetime.now() - t0).total_seconds(),
        }
        logger.info("Step 12/12 — Quality report generated.")

    # ---- Save cleaned data ----
    t0 = datetime.now()
    csv_name = f"aki_cleaned_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    csv_path = output_path / csv_name
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    pipeline_summary["cleaned_file"] = str(csv_path)
    pipeline_summary["steps"]["save"] = {
        "path": str(csv_path),
        "shape": list(df.shape),
        "time_s": (datetime.now() - t0).total_seconds(),
    }
    logger.info("Cleaned data saved: %s (%d × %d)", csv_path, df.shape[0], df.shape[1])

    # ---- Final summary ----
    pipeline_summary["end_time"] = datetime.now().isoformat()
    total_time = sum(
        s.get("time_s", 0) for s in pipeline_summary["steps"].values() if isinstance(s, dict)
    )
    pipeline_summary["total_time_s"] = round(total_time, 2)

    logger.info("=" * 60)
    logger.info(
        "AKI Data Cleaning Pipeline — COMPLETE (total %.2f s)", total_time
    )
    logger.info("=" * 60)

    return pipeline_summary


# ===================================================================
# 15. validate_aki_staging_criteria — KDIGO Scr consistency check
# ===================================================================

# KDIGO AKI staging criteria (Scr-based)
# Stage 1: Scr increase >= 26.5 umol/L within 48h OR 1.5-1.9x baseline within 7d
# Stage 2: Scr 2.0-2.9x baseline
# Stage 3: Scr >= 4x baseline OR Scr >= 353.6 umol/L OR RRT initiation

def validate_aki_staging_criteria(
    df: pd.DataFrame,
    baseline_col: str = "术前Scr",
    scr_48h_col: str = "术后48hSCr",
    scr_7d_col: str = "术后7dSCr",
    scr_icu_col: str = "ICUAdmSCr",
    stage_col: str = "AKI分期",
    group_col: str = "AKI分组",
) -> pd.DataFrame:
    """Validate AKI staging against KDIGO Scr-based criteria.

    For each patient with AKI (AKI分期 > 0), checks whether the observed
    Scr changes satisfy the KDIGO criteria for their recorded stage.

    Parameters
    ----------
    df : pd.DataFrame
    baseline_col : str
        Column name for baseline (pre-operative) Scr.
    scr_48h_col : str
        Column name for 48-hour post-operative Scr.
    scr_7d_col : str
        Column name for 7-day post-operative Scr.
    scr_icu_col : str
        Column name for ICU admission Scr.
    stage_col : str
        Column name for AKI stage (0=no AKI, 1/2/3).
    group_col : str
        Column name for AKI binary grouping (0=no AKI, 1=AKI).

    Returns
    -------
    pd.DataFrame
        DataFrame with additional columns:
        - ``_aki_stage_consistent`` : bool — True if Scr matches stage
        - ``_aki_stage_issue`` — description of inconsistency (if any)
        - ``_aki_stage_value`` — the KDIGO stage suggested by Scr alone
    """
    df_out = df.copy()

    # Identify required columns
    required_cols = [baseline_col, stage_col, group_col]
    available_scr = [c for c in [scr_48h_col, scr_7d_col, scr_icu_col] if c in df_out.columns]

    missing = [c for c in required_cols if c not in df_out.columns]
    if missing:
        logger.warning("AKI staging validation skipped — missing columns: %s", missing)
        df_out["_aki_stage_consistent"] = True
        df_out["_aki_stage_issue"] = ""
        df_out["_aki_stage_value"] = np.nan
        return df_out

    logger.info("Validating AKI staging against KDIGO Scr criteria ...")

    consistency = []
    issues = []
    scr_stages = []

    for idx, row in df_out.iterrows():
        stage = row.get(stage_col, 0)
        group = row.get(group_col, 0)
        baseline = row.get(baseline_col, np.nan)

        # Non-AKI patients — skip Scr check (stage should be 0, checked separately)
        if group == 0 or stage == 0 or pd.isna(baseline) or baseline <= 0:
            consistency.append(True)
            issues.append("")
            scr_stages.append(0 if (group == 0 or stage == 0) else np.nan)
            continue

        # Compute Scr ratios and deltas
        scr_ratios = []
        scr_deltas = []
        max_scr = 0

        for c in available_scr:
            val = row.get(c, np.nan)
            if pd.notna(val) and val > 0:
                ratio = val / baseline
                delta = val - baseline
                scr_ratios.append(ratio)
                scr_deltas.append(delta)
                if val > max_scr:
                    max_scr = val

        max_ratio = max(scr_ratios) if scr_ratios else 1.0
        max_delta = max(scr_deltas) if scr_deltas else 0.0

        # Determine KDIGO stage from Scr values alone
        if max_scr >= 353.6 or max_ratio >= 4.0:
            scr_suggested_stage = 3
        elif max_ratio >= 2.0:
            scr_suggested_stage = 2
        elif max_delta >= 26.5 or max_ratio >= 1.5:
            scr_suggested_stage = 1
        else:
            scr_suggested_stage = 0  # Scr doesn't meet AKI criteria at all

        scr_stages.append(scr_suggested_stage)

        # Check consistency
        recorded_stage = int(stage)
        if scr_suggested_stage == 0:
            consistency.append(False)
            issues.append(
                f"AKI分期={recorded_stage}但Scr变化不满足KDIGO标准 "
                f"(max_delta={max_delta:.1f}μmol/L, max_ratio={max_ratio:.2f}x, "
                f"max_scr={max_scr:.1f}μmol/L)"
            )
        elif scr_suggested_stage < recorded_stage:
            # Scr suggests milder AKI than recorded
            consistency.append(False)
            issues.append(
                f"AKI分期={recorded_stage}但Scr仅满足Stage{scr_suggested_stage}标准 "
                f"(max_delta={max_delta:.1f}μmol/L, max_ratio={max_ratio:.2f}x)"
            )
        else:
            # Scr suggests same or more severe AKI — acceptable
            consistency.append(True)
            if scr_suggested_stage > recorded_stage:
                issues.append(
                    f"AKI分期={recorded_stage}但Scr已达Stage{scr_suggested_stage}水平 "
                    f"(max_delta={max_delta:.1f}μmol/L, max_ratio={max_ratio:.2f}x) — "
                    f"可能为更严重分期"
                )
            else:
                issues.append("")

    df_out["_aki_stage_consistent"] = consistency
    df_out["_aki_stage_issue"] = issues
    df_out["_aki_stage_value"] = scr_stages

    n_inconsistent = sum(not c for c in consistency)
    logger.info(
        "AKI staging validation complete: %d / %d AKI records flagged as inconsistent.",
        n_inconsistent,
        int((df_out[group_col] == 1).sum()),
    )

    return df_out


# ===================================================================
# 16. validate_aki_group_stage_consistency
# ===================================================================

def validate_aki_group_stage_consistency(
    df: pd.DataFrame,
    group_col: str = "AKI分组",
    stage_col: str = "AKI分期",
) -> pd.DataFrame:
    """Check consistency between AKI分组 (binary) and AKI分期 (ordinal).

    Rules:
        - AKI分组 = 0  ⟹  AKI分期 must be 0
        - AKI分组 = 1  ⟹  AKI分期 must be 1, 2, or 3

    Parameters
    ----------
    df : pd.DataFrame
    group_col : str
    stage_col : str

    Returns
    -------
    pd.DataFrame
        DataFrame with additional columns:
        - ``_aki_group_stage_ok`` : bool
        - ``_aki_group_stage_issue`` : str — description if inconsistent
    """
    if group_col not in df.columns or stage_col not in df.columns:
        logger.warning(
            "AKI group/stage consistency check skipped — missing '%s' or '%s'.",
            group_col,
            stage_col,
        )
        df_out = df.copy()
        df_out["_aki_group_stage_ok"] = True
        df_out["_aki_group_stage_issue"] = ""
        return df_out

    logger.info("Checking AKI分组 vs AKI分期 consistency ...")

    df_out = df.copy()
    ok_list = []
    issue_list = []

    for idx, row in df_out.iterrows():
        group = row[group_col]
        stage = row[stage_col]

        if pd.isna(group) or pd.isna(stage):
            ok_list.append(False)
            issue_list.append("AKI分组或AKI分期为缺失值")
            continue

        group = int(group)
        stage = int(stage)

        if group == 0 and stage != 0:
            ok_list.append(False)
            issue_list.append(f"AKI分组=0(无AKI)但AKI分期={stage}(应=0)")
        elif group == 1 and stage not in (1, 2, 3):
            ok_list.append(False)
            issue_list.append(f"AKI分组=1(AKI)但AKI分期={stage}(应为1/2/3)")
        else:
            ok_list.append(True)
            issue_list.append("")

    df_out["_aki_group_stage_ok"] = ok_list
    df_out["_aki_group_stage_issue"] = issue_list

    n_bad = sum(not ok for ok in ok_list)
    logger.info(
        "AKI group/stage consistency check complete: %d / %d records flagged.",
        n_bad,
        len(df_out),
    )

    return df_out


# ===================================================================
# 17. run_aki_logic_validation — combined AKI logic checks
# ===================================================================

def run_aki_logic_validation(
    df: pd.DataFrame,
    output_path: Union[str, Path] = "outputs/tables/",
) -> Dict[str, Any]:
    """Run both AKI logic validation checks and save a summary report.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame to validate. Must contain AKI分组, AKI分期, and Scr columns.
    output_path : str or Path

    Returns
    -------
    dict
        Summary with keys: staging_report, group_stage_report, n_staging_issues,
        n_group_stage_issues, flagged_records.
    """
    logger.info("=" * 60)
    logger.info("AKI Logic Validation — START")
    logger.info("=" * 60)

    # 1. AKI staging vs Scr criteria
    df_validated = validate_aki_staging_criteria(df)

    # 2. AKI分组 vs AKI分期 consistency
    df_validated = validate_aki_group_stage_consistency(df_validated)

    # Collect flagged records
    staging_flags = df_validated[~df_validated["_aki_stage_consistent"]]
    group_stage_flags = df_validated[~df_validated["_aki_group_stage_ok"]]

    # Combine all flagged issues into a report
    flag_cols = ["_aki_stage_consistent", "_aki_stage_issue",
                 "_aki_stage_value", "_aki_group_stage_ok", "_aki_group_stage_issue"]
    all_flags = df_validated[
        (~df_validated["_aki_stage_consistent"]) | (~df_validated["_aki_group_stage_ok"])
    ]

    # Save flagged records
    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)

    if len(all_flags) > 0:
        report_path = output_path / "aki_logic_validation_flags.csv"
        # Keep relevant columns for the report
        report_cols = [
            c for c in df_validated.columns
            if c in flag_cols
            or c in ["AKI分组", "AKI分期", "术前Scr", "术后48hSCr", "术后7dSCr", "ICUAdmSCr"]
            or not c.startswith("_")
        ]
        # Deduplicate columns
        report_cols = list(dict.fromkeys(report_cols))
        all_flags[report_cols].to_csv(report_path, index=False, encoding="utf-8-sig")
        logger.info("Flagged records saved to: %s (%d rows)", report_path, len(all_flags))
    else:
        logger.info("No flagged records — all AKI logic checks passed.")

    # Summary report
    summary_lines = [
        "=" * 60,
        "AKI 逻辑校验报告 — AKI Logic Validation Report",
        "=" * 60,
        "",
        f"总记录数: {len(df_validated)}",
        f"AKI患者数 (AKI分组=1): {int((df_validated['AKI分组']==1).sum())}",
        "",
        "--- 1. AKI分期 vs KDIGO Scr标准 ---",
        f"不一致记录数: {len(staging_flags)}",
    ]

    if len(staging_flags) > 0:
        summary_lines.append("不一致详情:")
        for _, row in staging_flags.iterrows():
            summary_lines.append(
                f"  行{row.name}: AKI分期={row.get('AKI分期','?')}, "
                f"{row.get('_aki_stage_issue', '')}"
            )

    summary_lines.extend([
        "",
        "--- 2. AKI分组 vs AKI分期 对应关系 ---",
        f"不一致记录数: {len(group_stage_flags)}",
    ])

    if len(group_stage_flags) > 0:
        summary_lines.append("不一致详情:")
        for _, row in group_stage_flags.iterrows():
            summary_lines.append(
                f"  行{row.name}: AKI分组={row.get('AKI分组','?')}, "
                f"AKI分期={row.get('AKI分期','?')}, "
                f"{row.get('_aki_group_stage_issue', '')}"
            )

    summary_lines.extend([
        "",
        "=" * 60,
        "校验完成",
        "=" * 60,
    ])

    report_txt = "\n".join(summary_lines)
    txt_path = output_path / "aki_logic_validation_report.txt"
    txt_path.write_text(report_txt, encoding="utf-8")
    logger.info("Validation report saved to: %s", txt_path)

    return {
        "staging_flags": len(staging_flags),
        "group_stage_flags": len(group_stage_flags),
        "flagged_records": all_flags,
        "report_path": str(txt_path),
    }


# ===================================================================
# CLI entry point
# ===================================================================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="AKI Data Cleaning Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "input",
        type=str,
        help="Path to the raw AKI Excel file (e.g., data/raw/AKI数据.xlsx)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/processed/",
        help="Output directory for cleaned data (default: data/processed/)",
    )
    parser.add_argument(
        "--missing-strategy",
        type=str,
        default="median",
        choices=["median", "mean", "mode"],
        help="Imputation strategy for low-missingness columns",
    )
    parser.add_argument(
        "--missing-threshold",
        type=float,
        default=0.05,
        help="Missing fraction threshold for IterativeImputer (default: 0.05)",
    )
    parser.add_argument(
        "--outlier-method",
        type=str,
        default="winsorize",
        choices=["winsorize", "cap"],
        help="Outlier handling method",
    )
    parser.add_argument(
        "--encode",
        type=str,
        default="label",
        choices=["label", "onehot"],
        help="Categorical encoding method",
    )
    parser.add_argument(
        "--scale",
        type=str,
        default="standard",
        choices=["standard", "minmax"],
        help="Feature scaling method",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Skip generating the data quality report",
    )
    parser.add_argument(
        "--no-dict",
        action="store_true",
        help="Skip generating the data dictionary",
    )

    args = parser.parse_args()

    summary = run_full_cleaning_pipeline(
        input_path=args.input,
        output_path=args.output,
        missing_strategy=args.missing_strategy,
        missing_threshold=args.missing_threshold,
        outlier_method=args.outlier_method,
        encode_method=args.encode,
        scale_method=args.scale,
        generate_report=not args.no_report,
        generate_dict=not args.no_dict,
    )

    print("\nPipeline summary:")
    for key, val in summary.items():
        if key == "steps":
            for step, info in val.items():
                print(f"  {step}: {info}")
        else:
            print(f"  {key}: {val}")

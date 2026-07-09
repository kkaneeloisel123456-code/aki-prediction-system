"""
Exploratory Data Analysis (EDA) Module for AKI Prediction Project.

Provides comprehensive EDA functions:
  - Table 1 generation (descriptive stats stratified by AKI group)
  - Univariate logistic regression analysis
  - Collinearity analysis (VIF + correlation heatmap)
  - Distribution plots by AKI group
  - AKI epidemiology analysis (incidence by age, surgery type, comorbidities)
  - Target distribution plots (pie + bar)
  - Pairwise feature analysis (scatter + correlation with target)
  - Full EDA pipeline orchestrator

All plots use SimHei font for Chinese text and are saved as 300dpi PNGs.
"""

import os
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats
from scipy.stats import chi2_contingency, fisher_exact, mannwhitneyu, ttest_ind
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from statsmodels.stats.outliers_influence import variance_inflation_factor
from statsmodels.tools.tools import add_constant

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# ---------------------------------------------------------------------------
# Global matplotlib / Chinese font setup
# ---------------------------------------------------------------------------

# Try to register SimHei (common on Windows) or fall back to a system sans-serif
_chinese_font_candidates = ["SimHei", "Microsoft YaHei", "WenQuanYi Micro Hei", "Noto Sans CJK SC"]

for _f in _chinese_font_candidates:
    try:
        plt.rcParams["font.sans-serif"] = [_f, "DejaVu Sans"]
        plt.rcParams["axes.unicode_minus"] = False
        # Quick probe
        fig, ax = plt.subplots()
        ax.set_title("测")  # test Chinese char
        plt.close(fig)
        break
    except Exception:
        continue

# Default seaborn style
sns.set_style("whitegrid")
sns.set_context("paper", font_scale=1.1)

# ---------------------------------------------------------------------------
# Column groupings for downstream use
# ---------------------------------------------------------------------------

DEFAULT_CONTINUOUS_VARS = [
    "年龄", "BMI", "术前肌酐", "术后肌酐峰值", "eGFR",
    "术前白细胞", "术后白细胞", "术前血红蛋白", "术后血红蛋白",
    "术前血小板", "术后血小板", "术前白蛋白", "术后白蛋白",
    "总住院天数", "ICU住院天数", "手术时长",
    "术前收缩压", "术前舒张压", "术前心率", "术前血氧饱和度",
]

DEFAULT_CATEGORICAL_VARS = [
    "性别", "高血压", "糖尿病", "冠心病", "手术类型", "AKI分期",
]

DEFAULT_BINARY_VARS = [
    "高血压", "糖尿病", "冠心病",
]

# Variables used in Table 1 (subset of interest)
TABLE1_VARS = [
    "年龄", "性别", "BMI", "总住院天数", "ICU住院天数",
    "术前肌酐", "术后肌酐峰值", "eGFR",
    "术前白细胞", "术后白细胞", "术前血红蛋白", "术后血红蛋白",
    "术前白蛋白", "术后白蛋白",
    "高血压", "糖尿病", "冠心病", "手术类型",
]


# ===================================================================
# 1. TABLE 1 — Descriptive statistics stratified by AKI group
# ===================================================================

def generate_table1(
    df: pd.DataFrame,
    target: str = "AKI分组",
    save_path: str = "outputs/tables/",
) -> pd.DataFrame:
    """Create Table 1: descriptive statistics stratified by AKI group.

    For continuous variables: mean ± SD (normally distributed) or
    median (IQR) (non-normal), with appropriate group comparison test
    (t-test or Mann-Whitney U).

    For categorical variables: n (%), with chi-square or Fisher's exact
    test p-value.

    Parameters
    ----------
    df : pd.DataFrame
        Input data containing *target* and variables of interest.
    target : str
        Column name for AKI group (0 = no AKI, 1 = AKI).
    save_path : str
        Directory where the formatted CSV will be saved.

    Returns
    -------
    pd.DataFrame
        Formatted Table 1 with columns:
        [Variable, Total (n=...), Non-AKI (n=...), AKI (n=...), p-value].
    """
    os.makedirs(save_path, exist_ok=True)

    # Determine which variables from TABLE1_VARS actually exist
    available_vars = [v for v in TABLE1_VARS if v in df.columns]

    # Separate continuous and categorical among available vars
    continuous_vars_in_data = [
        v for v in available_vars
        if v not in DEFAULT_CATEGORICAL_VARS and pd.api.types.is_numeric_dtype(df[v])
    ]
    categorical_vars_in_data = [
        v for v in available_vars
        if v in DEFAULT_CATEGORICAL_VARS or not pd.api.types.is_numeric_dtype(df[v])
    ]
    # Also include binary vars that are numeric (0/1) as categorical
    for v in DEFAULT_BINARY_VARS:
        if v in available_vars and v not in categorical_vars_in_data:
            categorical_vars_in_data.append(v)

    groups = sorted(df[target].dropna().unique())
    total_n = len(df)
    group_counts = {g: (df[target] == g).sum() for g in groups}

    rows = []

    # -- Continuous variables --
    for var in continuous_vars_in_data:
        data_total = df[var].dropna()
        rows.append(_format_continuous_row(var, data_total, df, target, groups))

    # -- Categorical variables --
    for var in categorical_vars_in_data:
        rows.append(_format_categorical_row(var, df, target, groups))

    result_df = pd.DataFrame(rows)

    # Build header columns
    col_name_total = f"Total (n={total_n})"
    col_name_non_aki = f"Non-AKI (n={group_counts.get(0, '?')})"
    col_name_aki = f"AKI (n={group_counts.get(1, '?')})"

    header_map = {
        "Variable": "Variable",
        "Total": col_name_total,
        "Group0": col_name_non_aki,
        "Group1": col_name_aki,
        "p_value": "p-value",
    }

    result_df.rename(columns=header_map, inplace=True)

    # Save
    csv_path = os.path.join(save_path, "table1.csv")
    result_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"[Table 1] Saved to {csv_path}")

    return result_df


def _check_normality(series: pd.Series) -> bool:
    """Quick normality check via Shapiro-Wilk (small n) or D'Agostino-Pearson."""
    n = len(series)
    if n < 3:
        return False
    if n <= 50:
        _, p = stats.shapiro(series)
    else:
        _, p = stats.normaltest(series)
    return p > 0.05


def _format_continuous_row(
    var: str,
    data_total: pd.Series,
    df: pd.DataFrame,
    target: str,
    groups: List,
) -> Dict:
    """Format a single continuous variable row for Table 1."""
    row = {"Variable": var}

    # Total column
    if _check_normality(data_total):
        row["Total"] = f"{data_total.mean():.2f} ± {data_total.std():.2f}"
    else:
        row["Total"] = f"{data_total.median():.2f} ({data_total.quantile(0.25):.2f}–{data_total.quantile(0.75):.2f})"

    # Per-group columns and test
    g0 = df.loc[df[target] == groups[0], var].dropna() if len(groups) > 0 else pd.Series(dtype=float)
    g1 = df.loc[df[target] == groups[1], var].dropna() if len(groups) > 1 else pd.Series(dtype=float)

    for gi, gdata in [(groups[0], g0), (groups[1], g1)]:
        if len(gdata) == 0:
            row[f"Group{gi}"] = "—"
            continue
        if _check_normality(gdata):
            row[f"Group{gi}"] = f"{gdata.mean():.2f} ± {gdata.std():.2f}"
        else:
            row[f"Group{gi}"] = f"{gdata.median():.2f} ({gdata.quantile(0.25):.2f}–{gdata.quantile(0.75):.2f})"

    # Statistical test
    if len(g0) > 1 and len(g1) > 1:
        both_normal = _check_normality(g0) and _check_normality(g1)
        if both_normal:
            _, p_val = ttest_ind(g0, g1, equal_var=False)
        else:
            _, p_val = mannwhitneyu(g0, g1, alternative="two-sided")
        row["p_value"] = _format_p(p_val)
    else:
        row["p_value"] = "—"

    return row


def _format_categorical_row(
    var: str,
    df: pd.DataFrame,
    target: str,
    groups: List,
) -> Dict:
    """Format a single categorical variable row for Table 1."""
    # Drop rows where target is missing
    sub = df[[var, target]].dropna()
    if sub.empty:
        return {"Variable": var, "Total": "—", "Group0": "—", "Group1": "—", "p_value": "—"}

    row = {"Variable": var}
    total_n = len(sub)

    # Total counts
    value_counts = sub[var].value_counts()
    row["Total"] = "; ".join(
        [f"{k}: {v} ({v / total_n * 100:.1f}%)" for k, v in value_counts.items()]
    )

    # Per-group
    for gi in groups:
        mask = sub[target] == gi
        gsub = sub.loc[mask, var]
        g_n = len(gsub)
        if g_n == 0:
            row[f"Group{gi}"] = "—"
            continue
        vc = gsub.value_counts()
        row[f"Group{gi}"] = "; ".join(
            [f"{k}: {v} ({v / g_n * 100:.1f}%)" for k, v in vc.items()]
        )

    # Chi-square or Fisher
    try:
        ct = pd.crosstab(sub[var], sub[target])
        if ct.size == 0:
            row["p_value"] = "—"
        else:
            # If any expected cell < 5, use Fisher
            if ct.shape == (2, 2):
                # 2x2 table
                _, p_val = fisher_exact(ct)
                row["p_value"] = _format_p(p_val)
            else:
                # Larger table: use chi-square
                _, p_val, _, expected = chi2_contingency(ct)
                if (expected < 5).any():
                    # Fallback: simulate Fisher (or just report chi2 p with note)
                    row["p_value"] = _format_p(p_val) + " †"
                else:
                    row["p_value"] = _format_p(p_val)
    except Exception:
        row["p_value"] = "—"

    return row


def _format_p(p: float) -> str:
    """Format p-value for display."""
    if p < 0.001:
        return "<0.001"
    return f"{p:.3f}"


# ===================================================================
# 2. UNIVARIATE ANALYSIS — Logistic regression for each variable
# ===================================================================

def univariate_analysis(
    df: pd.DataFrame,
    target: str = "AKI分组",
    save_path: str = "outputs/figures/",
) -> pd.DataFrame:
    """Run univariate logistic regression for each numeric variable.

    Returns a table with OR, 95% CI, and p-value for each predictor.

    Parameters
    ----------
    df : pd.DataFrame
        Input data.
    target : str
        Target column (0/1).
    save_path : str
        Directory to save results CSV.

    Returns
    -------
    pd.DataFrame
        Columns: Variable, OR, CI_lower, CI_upper, p_value, n.
    """
    os.makedirs(save_path, exist_ok=True)

    # Identify numeric predictors (exclude target itself and non-predictive text cols)
    exclude_defaults = {target, "姓名", "AKI分期", "ID", "id", "PatientID"}
    numeric_cols = [
        c for c in df.columns
        if c not in exclude_defaults
        and pd.api.types.is_numeric_dtype(df[c])
        and df[c].nunique() > 1
    ]

    results = []
    for col in numeric_cols:
        sub = df[[col, target]].dropna()
        if sub.empty or sub[target].nunique() < 2:
            continue
        X = sub[[col]].values
        y = sub[target].values

        # Standardize for OR comparability
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        try:
            model = LogisticRegression(solver="lbfgs", max_iter=1000)
            model.fit(X_scaled, y)
            coef = model.coef_[0][0]
            OR = np.exp(coef)

            # Approximate CI using std err from statsmodels
            import statsmodels.api as sm
            X_sm = add_constant(X_scaled)
            logit = sm.Logit(y, X_sm)
            try:
                fit = logit.fit(disp=False, maxiter=1000)
                se = fit.bse.iloc[1]
                ci_low = np.exp(coef - 1.96 * se)
                ci_high = np.exp(coef + 1.96 * se)
                p_val = fit.pvalues.iloc[1]
            except Exception:
                # Fallback: rough approximate
                se = np.sqrt(1 / (sub[col].var() * len(sub)))
                ci_low = np.exp(coef - 1.96 * se)
                ci_high = np.exp(coef + 1.96 * se)
                p_val = model.predict_proba(X_scaled)  # dummy
                _, p_val = stats.pearsonr(X_scaled.flatten(), y)

            results.append({
                "Variable": col,
                "OR": round(OR, 4),
                "CI_lower": round(ci_low, 4),
                "CI_upper": round(ci_high, 4),
                "p_value": _format_p(p_val),
                "n": len(sub),
            })
        except Exception as e:
            print(f"  [Warn] Univariate failed for {col}: {e}")
            continue

    result_df = pd.DataFrame(results)
    result_df.sort_values("p_value", inplace=True)

    csv_path = os.path.join(save_path, "univariate_analysis.csv")
    result_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"[Univariate] Saved to {csv_path}")

    return result_df


# ===================================================================
# 3. COLLINEARITY ANALYSIS — VIF + correlation heatmap
# ===================================================================

def collinearity_analysis(
    df: pd.DataFrame,
    exclude_cols: Optional[List[str]] = None,
    save_path: str = "outputs/figures/",
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Compute VIF for numeric features and plot a correlation heatmap.

    Parameters
    ----------
    df : pd.DataFrame
        Input data.
    exclude_cols : list of str, optional
        Columns to exclude (e.g., target, ID).
    save_path : str
        Directory to save outputs.

    Returns
    -------
    vif_df : pd.DataFrame
        VIF values for each feature (sorted descending).
    high_corr_pairs : pd.DataFrame
        Pairs with |r| > 0.8.
    """
    os.makedirs(save_path, exist_ok=True)

    if exclude_cols is None:
        exclude_cols = ["AKI分组", "姓名", "AKI分期", "ID", "id"]

    # Numeric columns to analyse
    numeric_cols = [
        c for c in df.columns
        if c not in exclude_cols
        and pd.api.types.is_numeric_dtype(df[c])
        and df[c].nunique() > 1
    ]

    # Drop rows with any NaN in these columns
    sub = df[numeric_cols].dropna()
    if sub.empty:
        print("[Collinearity] No valid numeric columns after dropping NaNs.")
        return pd.DataFrame(), pd.DataFrame()

    # --- VIF ---
    X = add_constant(sub)
    vif_data = pd.DataFrame()
    vif_data["Feature"] = sub.columns
    vif_data["VIF"] = [
        variance_inflation_factor(X.values, i + 1)  # +1 because add_constant adds first col
        for i in range(len(sub.columns))
    ]
    vif_data.sort_values("VIF", ascending=False, inplace=True)
    vif_data.reset_index(drop=True, inplace=True)

    vif_csv = os.path.join(save_path, "vif_values.csv")
    vif_data.to_csv(vif_csv, index=False, encoding="utf-8-sig")
    print(f"[Collinearity] VIF table saved to {vif_csv}")

    # --- Correlation heatmap (top 30 by variance / VIF) ---
    top30 = vif_data.head(30)["Feature"].tolist()
    top30 = [c for c in top30 if c in sub.columns]
    corr = sub[top30].corr(method="pearson")

    fig, ax = plt.subplots(figsize=(14, 12))
    mask = np.triu(np.ones_like(corr, dtype=bool), k=1)
    sns.heatmap(
        corr, mask=mask, annot=False, fmt=".2f",
        cmap="RdBu_r", center=0, vmin=-1, vmax=1,
        square=True, linewidths=0.3, cbar_kws={"shrink": 0.8},
        ax=ax,
    )
    ax.set_title("Correlation Heatmap (Top 30 Features)", fontsize=14, fontweight="bold")
    plt.xticks(rotation=45, ha="right", fontsize=8)
    plt.yticks(fontsize=8)
    plt.tight_layout()

    heatmap_path = os.path.join(save_path, "correlation_heatmap.png")
    fig.savefig(heatmap_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"[Collinearity] Heatmap saved to {heatmap_path}")

    # --- Flag high-correlation pairs ---
    high_pairs = []
    corr_vals = corr.unstack().reset_index()
    corr_vals.columns = ["Var1", "Var2", "Correlation"]
    corr_vals = corr_vals[corr_vals["Var1"] != corr_vals["Var2"]]
    corr_vals["AbsCorr"] = corr_vals["Correlation"].abs()
    high = corr_vals[corr_vals["AbsCorr"] > 0.8].copy()
    # Remove duplicates (A, B) and (B, A)
    high["sorted_pair"] = high.apply(
        lambda r: tuple(sorted([r["Var1"], r["Var2"]])), axis=1
    )
    high.drop_duplicates(subset="sorted_pair", inplace=True)
    high.drop(columns="sorted_pair", inplace=True)
    high.sort_values("AbsCorr", ascending=False, inplace=True)
    high_pairs_df = high.reset_index(drop=True)

    pairs_csv = os.path.join(save_path, "high_correlation_pairs.csv")
    high_pairs_df.to_csv(pairs_csv, index=False, encoding="utf-8-sig")
    print(f"[Collinearity] High-correlation pairs saved to {pairs_csv}")

    return vif_data, high_pairs_df


# ===================================================================
# 4. DISTRIBUTION PLOTS — Histogram + KDE or boxplot by AKI group
# ===================================================================

def plot_distributions(
    df: pd.DataFrame,
    vars: List[str],
    target: str = "AKI分组",
    save_path: str = "outputs/figures/",
) -> None:
    """Plot histogram + KDE (or boxplot) for each var, split by AKI group.

    Max 16 variables per figure — creates multiple figures if needed.

    Parameters
    ----------
    df : pd.DataFrame
        Input data.
    vars : list of str
        Variable names to plot.
    target : str
        Column name for AKI group.
    save_path : str
        Directory to save figure PNGs.
    """
    os.makedirs(save_path, exist_ok=True)
    available = [v for v in vars if v in df.columns]
    if not available:
        print("[Distributions] No valid variables to plot.")
        return

    # Split into chunks of 16
    chunk_size = 16
    chunks = [available[i:i + chunk_size] for i in range(0, len(available), chunk_size)]

    for chunk_idx, var_chunk in enumerate(chunks):
        n_vars = len(var_chunk)
        n_cols = 4
        n_rows = int(np.ceil(n_vars / n_cols))

        fig, axes = plt.subplots(n_rows, n_cols, figsize=(5 * n_cols, 4 * n_rows))
        axes = axes.flatten()

        for idx, var in enumerate(var_chunk):
            ax = axes[idx]
            sub = df[[var, target]].dropna()
            if sub.empty:
                ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
                continue

            g0 = sub.loc[sub[target] == 0, var]
            g1 = sub.loc[sub[target] == 1, var]

            # Decide: use KDE if enough data points (> 5 per group)
            use_kde = len(g0) > 5 and len(g1) > 5

            if use_kde:
                # Histogram + KDE
                bins = min(30, max(10, int(np.sqrt(len(sub)))))
                ax.hist(g0, bins=bins, alpha=0.5, color="#3498db", label="Non-AKI", density=True)
                ax.hist(g1, bins=bins, alpha=0.5, color="#e74c3c", label="AKI", density=True)
                # KDE overlay
                try:
                    kde0 = stats.gaussian_kde(g0)
                    kde1 = stats.gaussian_kde(g1)
                    x_range = np.linspace(sub[var].min(), sub[var].max(), 200)
                    ax.plot(x_range, kde0(x_range), color="#2980b9", lw=2)
                    ax.plot(x_range, kde1(x_range), color="#c0392b", lw=2)
                except Exception:
                    pass
            else:
                # Boxplot
                bp = ax.boxplot(
                    [g0.values, g1.values],
                    labels=["Non-AKI", "AKI"],
                    patch_artist=True,
                    widths=0.4,
                )
                if bp["boxes"]:
                    bp["boxes"][0].set_facecolor("#3498db")
                    bp["boxes"][1].set_facecolor("#e74c3c")

            ax.set_title(var, fontsize=11, fontweight="bold")
            ax.set_xlabel("")
            ax.set_ylabel("Density" if use_kde else "Value")
            if use_kde:
                ax.legend(fontsize=8)

        # Hide unused subplots
        for j in range(n_vars, len(axes)):
            axes[j].set_visible(False)

        plt.suptitle(
            f"Distribution by AKI Group — Set {chunk_idx + 1}",
            fontsize=14, fontweight="bold", y=1.02,
        )
        plt.tight_layout()

        fname = f"distributions_set_{chunk_idx + 1}.png"
        figpath = os.path.join(save_path, fname)
        fig.savefig(figpath, dpi=300, bbox_inches="tight")
        plt.close(fig)
        print(f"[Distributions] Saved {figpath}")


# ===================================================================
# 5. AKI EPIDEMIOLOGY ANALYSIS
# ===================================================================

def aki_epidemiology_analysis(
    df: pd.DataFrame,
    save_path: str = "outputs/figures/",
) -> Dict[str, Union[float, pd.DataFrame]]:
    """Analyze AKI incidence overall, by age, surgery type, and comorbidities.

    Parameters
    ----------
    df : pd.DataFrame
        Input data with 'AKI分组' and relevant columns.
    save_path : str
        Directory to save figures.

    Returns
    -------
    dict
        Key findings with incidence rates and DataFrames.
    """
    os.makedirs(save_path, exist_ok=True)

    target = "AKI分组"
    findings = {}

    # ---- 5a. Overall incidence ----
    total = len(df)
    aki_count = df[target].sum()
    incidence_rate = aki_count / total
    findings["overall_incidence"] = round(incidence_rate, 4)
    findings["aki_count"] = int(aki_count)
    findings["total_count"] = total
    print(f"[Epidemiology] Overall AKI incidence: {aki_count}/{total} = {incidence_rate:.2%}")

    # ---- 5b. By age group ----
    if "年龄" in df.columns:
        age_bins = [0, 40, 50, 60, 70, 200]
        age_labels = ["<40", "40–49", "50–59", "60–69", "70+"]
        df_age = df.copy()
        df_age["age_group"] = pd.cut(df_age["年龄"], bins=age_bins, labels=age_labels, right=False)
        age_incidence = (
            df_age.groupby("age_group", observed=True)[target]
            .agg(aki_count="sum", total="count")
            .reset_index()
        )
        age_incidence["incidence"] = (age_incidence["aki_count"] / age_incidence["total"] * 100).round(2)
        findings["incidence_by_age"] = age_incidence

        # Bar chart
        fig, ax = plt.subplots(figsize=(8, 5))
        bars = ax.bar(
            age_incidence["age_group"].astype(str),
            age_incidence["incidence"],
            color="#3498db",
            edgecolor="white",
        )
        for bar, val in zip(bars, age_incidence["incidence"]):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                    f"{val:.1f}%", ha="center", va="bottom", fontsize=10)
        ax.set_title("AKI Incidence by Age Group", fontsize=13, fontweight="bold")
        ax.set_xlabel("Age Group")
        ax.set_ylabel("AKI Incidence (%)")
        ax.set_ylim(0, max(age_incidence["incidence"]) * 1.2 + 5)
        plt.tight_layout()
        figpath = os.path.join(save_path, "incidence_by_age.png")
        fig.savefig(figpath, dpi=300, bbox_inches="tight")
        plt.close(fig)
        print(f"[Epidemiology] Age incidence plot saved to {figpath}")

    # ---- 5c. By surgery type ----
    surgery_col = "手术类型"
    if surgery_col in df.columns:
        surg_incidence = (
            df.groupby(surgery_col)[target]
            .agg(aki_count="sum", total="count")
            .reset_index()
        )
        surg_incidence["incidence"] = (surg_incidence["aki_count"] / surg_incidence["total"] * 100).round(2)
        surg_incidence.sort_values("incidence", ascending=False, inplace=True)
        findings["incidence_by_surgery"] = surg_incidence

        fig, ax = plt.subplots(figsize=(10, 5))
        bars = ax.bar(
            surg_incidence[surgery_col].astype(str),
            surg_incidence["incidence"],
            color="#2ecc71",
            edgecolor="white",
        )
        for bar, val in zip(bars, surg_incidence["incidence"]):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
                    f"{val:.1f}%", ha="center", va="bottom", fontsize=9)
        ax.set_title("AKI Incidence by Surgery Type", fontsize=13, fontweight="bold")
        ax.set_xlabel("Surgery Type")
        ax.set_ylabel("AKI Incidence (%)")
        plt.xticks(rotation=30, ha="right")
        plt.tight_layout()
        figpath = os.path.join(save_path, "incidence_by_surgery.png")
        fig.savefig(figpath, dpi=300, bbox_inches="tight")
        plt.close(fig)
        print(f"[Epidemiology] Surgery incidence plot saved to {figpath}")

    # ---- 5d. By comorbidities ----
    comorbidity_cols = [c for c in ["高血压", "糖尿病", "冠心病"] if c in df.columns]
    if comorbidity_cols:
        cm_data = []
        for col in comorbidity_cols:
            sub = df[[col, target]].dropna()
            for val in sorted(sub[col].unique()):
                mask = sub[col] == val
                aki_n = mask.sum()  # actually count of rows where col==val
                aki_cases = sub.loc[mask, target].sum()
                total_n = mask.sum()
                label = f"{col}={int(val)}" if isinstance(val, (int, float)) and val == val else f"{col}={val}"
                cm_data.append({
                    "Comorbidity": label,
                    "aki_count": aki_cases,
                    "total": total_n,
                    "incidence": round(aki_cases / total_n * 100, 2) if total_n > 0 else 0,
                })
        cm_df = pd.DataFrame(cm_data)
        findings["incidence_by_comorbidity"] = cm_df

        fig, ax = plt.subplots(figsize=(8, 5))
        x_pos = np.arange(len(cm_df))
        colors = ["#e74c3c" if "=1" in r["Comorbidity"] else "#3498db" for _, r in cm_df.iterrows()]
        bars = ax.bar(x_pos, cm_df["incidence"], color=colors, edgecolor="white")
        ax.set_xticks(x_pos)
        ax.set_xticklabels(cm_df["Comorbidity"], rotation=25, ha="right")
        for bar, val in zip(bars, cm_df["incidence"]):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
                    f"{val:.1f}%", ha="center", va="bottom", fontsize=9)
        ax.set_title("AKI Incidence by Comorbidity", fontsize=13, fontweight="bold")
        ax.set_ylabel("AKI Incidence (%)")
        plt.tight_layout()
        figpath = os.path.join(save_path, "incidence_by_comorbidity.png")
        fig.savefig(figpath, dpi=300, bbox_inches="tight")
        plt.close(fig)
        print(f"[Epidemiology] Comorbidity incidence plot saved to {figpath}")

        # Combined bar chart
        fig, axes = plt.subplots(1, len(comorbidity_cols), figsize=(5 * len(comorbidity_cols), 4))
        if len(comorbidity_cols) == 1:
            axes = [axes]
        for ax_idx, col in enumerate(comorbidity_cols):
            sub = df[[col, target]].dropna()
            ct = pd.crosstab(sub[col], sub[target])
            ct_pct = ct.div(ct.sum(axis=1), axis=0) * 100
            ct_pct.plot(kind="bar", ax=axes[ax_idx], color=["#3498db", "#e74c3c"], edgecolor="white", legend=False)
            axes[ax_idx].set_title(f"AKI by {col}", fontsize=11, fontweight="bold")
            axes[ax_idx].set_xlabel(col)
            axes[ax_idx].set_ylabel("Percentage (%)")
            axes[ax_idx].legend(["Non-AKI", "AKI"], fontsize=8)
            axes[ax_idx].set_xticklabels(axes[ax_idx].get_xticklabels(), rotation=0)
        plt.suptitle("AKI Distribution by Comorbidity", fontsize=13, fontweight="bold")
        plt.tight_layout()
        figpath = os.path.join(save_path, "incidence_by_comorbidity_stacked.png")
        fig.savefig(figpath, dpi=300, bbox_inches="tight")
        plt.close(fig)
        print(f"[Epidemiology] Comorbidity stacked plot saved to {figpath}")

    # ---- 5e. AKI stage distribution ----
    stage_col = "AKI分期"
    if stage_col in df.columns:
        stage_dist = df[stage_col].value_counts().sort_index().reset_index()
        stage_dist.columns = [stage_col, "count"]
        stage_dist["percentage"] = (stage_dist["count"] / stage_dist["count"].sum() * 100).round(2)
        findings["stage_distribution"] = stage_dist

        fig, ax = plt.subplots(figsize=(7, 5))
        bars = ax.bar(
            stage_dist[stage_col].astype(str),
            stage_dist["count"],
            color=sns.color_palette("Blues_r", len(stage_dist)),
            edgecolor="white",
        )
        for bar, val in zip(bars, stage_dist["count"]):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                    str(val), ha="center", va="bottom", fontsize=10)
        ax.set_title("AKI Stage Distribution", fontsize=13, fontweight="bold")
        ax.set_xlabel("AKI Stage")
        ax.set_ylabel("Count")
        plt.tight_layout()
        figpath = os.path.join(save_path, "aki_stage_distribution.png")
        fig.savefig(figpath, dpi=300, bbox_inches="tight")
        plt.close(fig)
        print(f"[Epidemiology] AKI stage plot saved to {figpath}")

    return findings


# ===================================================================
# 6. TARGET DISTRIBUTION — Pie + Bar
# ===================================================================

def plot_target_distribution(
    df: pd.DataFrame,
    target: str = "AKI分组",
    save_path: str = "outputs/figures/",
) -> None:
    """Plot pie chart (AKI vs non-AKI) and bar chart of AKI stages.

    Parameters
    ----------
    df : pd.DataFrame
        Input data.
    target : str
        Target column.
    save_path : str
        Directory to save figures.
    """
    os.makedirs(save_path, exist_ok=True)

    # ---- Pie chart ----
    counts = df[target].value_counts().sort_index()
    labels = ["Non-AKI (0)", "AKI (1)"] if len(counts) == 2 else [str(k) for k in counts.index]
    colors_pie = ["#3498db", "#e74c3c"]

    fig, ax = plt.subplots(figsize=(6, 6))
    wedges, texts, autotexts = ax.pie(
        counts.values,
        labels=labels,
        autopct="%1.1f%%",
        startangle=90,
        colors=colors_pie[: len(counts)],
        explode=[0.02] * len(counts),
        shadow=False,
        textprops={"fontsize": 11},
    )
    for at in autotexts:
        at.set_fontweight("bold")
    ax.set_title("AKI vs Non-AKI Distribution", fontsize=14, fontweight="bold")
    plt.tight_layout()
    pie_path = os.path.join(save_path, "target_pie.png")
    fig.savefig(pie_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"[Target] Pie chart saved to {pie_path}")

    # ---- Bar chart of AKI stages ----
    stage_col = "AKI分期"
    if stage_col in df.columns:
        stage_counts = df[stage_col].value_counts().sort_index()
        fig, ax = plt.subplots(figsize=(7, 5))
        bars = ax.bar(
            stage_counts.index.astype(str),
            stage_counts.values,
            color=sns.color_palette("RdYlBu_r", len(stage_counts)),
            edgecolor="white",
        )
        for bar, val in zip(bars, stage_counts.values):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
                    str(val), ha="center", va="bottom", fontsize=10)
        ax.set_title("AKI Stage Distribution", fontsize=13, fontweight="bold")
        ax.set_xlabel("AKI Stage")
        ax.set_ylabel("Count")
        plt.tight_layout()
        stage_path = os.path.join(save_path, "target_stage_bar.png")
        fig.savefig(stage_path, dpi=300, bbox_inches="tight")
        plt.close(fig)
        print(f"[Target] Stage bar chart saved to {stage_path}")

    # -- Also a simple count bar if no stage column --
    if stage_col not in df.columns:
        fig, ax = plt.subplots(figsize=(6, 5))
        bars = ax.bar(
            labels,
            counts.values,
            color=colors_pie[: len(counts)],
            edgecolor="white",
        )
        for bar, val in zip(bars, counts.values):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
                    f"{val} ({val / len(df) * 100:.1f}%)", ha="center", va="bottom", fontsize=10)
        ax.set_title("AKI Group Counts", fontsize=13, fontweight="bold")
        ax.set_ylabel("Count")
        plt.tight_layout()
        bar_path = os.path.join(save_path, "target_bar.png")
        fig.savefig(bar_path, dpi=300, bbox_inches="tight")
        plt.close(fig)
        print(f"[Target] Bar chart saved to {bar_path}")


# ===================================================================
# 7. PAIRWISE FEATURE ANALYSIS — Scatter plots by AKI group
# ===================================================================

def pairwise_feature_analysis(
    df: pd.DataFrame,
    features: List[str],
    target: str = "AKI分组",
) -> pd.DataFrame:
    """Scatter plots for top features colored by AKI group + pairwise correlations.

    Parameters
    ----------
    df : pd.DataFrame
        Input data.
    features : list of str
        Feature names to plot pair-wise.
    target : str
        Target column.

    Returns
    -------
    pd.DataFrame
        Pairwise correlations with target for the requested features.
    """
    available = [f for f in features if f in df.columns and pd.api.types.is_numeric_dtype(df[f])]
    if not available:
        print("[Pairwise] No valid numeric features provided.")
        return pd.DataFrame()

    # Limit to a manageable number for pairwise plots
    plot_vars = available[:6]  # max 6 for a readable pairplot
    if len(available) > 6:
        print(f"[Pairwise] Limiting pairwise plot to first 6 features ({len(available)} provided).")

    # ---- Pairwise scatter plot with seaborn ----
    if len(plot_vars) >= 2 and len(plot_vars) <= 6:
        plot_df = df[plot_vars + [target]].dropna()
        if not plot_df.empty:
            # Map target to categorical for hue
            plot_df["AKI_Group"] = plot_df[target].map({0: "Non-AKI", 1: "AKI"}).fillna("Unknown")
            colors = {"Non-AKI": "#3498db", "AKI": "#e74c3c"}

            g = sns.PairGrid(
                plot_df,
                vars=plot_vars,
                hue="AKI_Group",
                palette=colors,
                diag_sharey=False,
                height=2.5,
            )
            g.map_upper(sns.scatterplot, s=15, alpha=0.6)
            g.map_lower(sns.kdeplot, fill=True, alpha=0.3, thresh=0.05)
            g.map_diag(sns.histplot, alpha=0.5, bins=20, kde=True)
            g.add_legend(title="", bbox_to_anchor=(1.05, 0.5), loc="center left")
            g.fig.suptitle(
                "Pairwise Feature Analysis by AKI Group",
                fontsize=14, fontweight="bold", y=1.02,
            )
            g.fig.tight_layout()

            save_dir = "outputs/figures/"
            os.makedirs(save_dir, exist_ok=True)
            figpath = os.path.join(save_dir, "pairwise_scatter.png")
            g.fig.savefig(figpath, dpi=300, bbox_inches="tight")
            plt.close(g.fig)
            print(f"[Pairwise] Pairplot saved to {figpath}")

    # ---- Correlation with target ----
    corr_results = []
    for f in available:
        sub = df[[f, target]].dropna()
        if len(sub) < 10:
            continue
        r_val, p_val = stats.pearsonr(sub[f], sub[target])
        corr_results.append({
            "Feature": f,
            "Pearson_r": round(r_val, 4),
            "p_value": _format_p(p_val),
        })

    corr_df = pd.DataFrame(corr_results)
    corr_df.sort_values("Pearson_r", key=abs, ascending=False, inplace=True)
    corr_df.reset_index(drop=True, inplace=True)

    # Also save
    save_dir = "outputs/figures/"
    os.makedirs(save_dir, exist_ok=True)
    csv_path = os.path.join(save_dir, "pairwise_correlation_with_target.csv")
    corr_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"[Pairwise] Correlation table saved to {csv_path}")

    return corr_df


# ===================================================================
# 8. FULL EDA PIPELINE
# ===================================================================

def run_full_eda(
    input_path: str,
    output_dir: str = "outputs/",
) -> Dict[str, object]:
    """Orchestrate the complete EDA pipeline.

    Parameters
    ----------
    input_path : str
        Path to the input CSV / Excel file.
    output_dir : str
        Root output directory (subdirectories: tables/, figures/).

    Returns
    -------
    dict
        Summary of key findings from the EDA.
    """
    print("=" * 60)
    print("  AKI Prediction — Full EDA Pipeline")
    print("=" * 60)

    # Resolve paths
    output_dir = os.path.abspath(output_dir)
    tables_dir = os.path.join(output_dir, "tables")
    figures_dir = os.path.join(output_dir, "figures")
    os.makedirs(tables_dir, exist_ok=True)
    os.makedirs(figures_dir, exist_ok=True)

    # ---- Load data ----
    print(f"\n[1] Loading data from: {input_path}")
    ext = Path(input_path).suffix.lower()
    if ext == ".csv":
        df = pd.read_csv(input_path, encoding="utf-8-sig")
    elif ext in (".xls", ".xlsx"):
        df = pd.read_excel(input_path)
    else:
        raise ValueError(f"Unsupported file format: {ext}")

    print(f"    Shape: {df.shape}")
    print(f"    Columns: {list(df.columns)}")

    # Drop 姓名 if present
    if "姓名" in df.columns:
        df = df.drop(columns=["姓名"])
        print("    Dropped column: 姓名")

    target = "AKI分组"
    if target not in df.columns:
        raise KeyError(f"Target column '{target}' not found in data.")

    # Determine data types
    print(f"\n[2] Target distribution:")
    aki_counts = df[target].value_counts().sort_index()
    for k, v in aki_counts.items():
        print(f"    {k}: {v} ({v / len(df) * 100:.1f}%)")

    # ---- Collect findings ----
    findings: Dict[str, object] = {}
    findings["data_shape"] = df.shape
    findings["target_counts"] = aki_counts.to_dict()

    # ---- 1. Table 1 ----
    print(f"\n[3] Generating Table 1 ...")
    table1 = generate_table1(df, target=target, save_path=tables_dir)
    findings["table1_preview"] = table1.iloc[:5, :].to_dict("records")

    # ---- 2. Univariate analysis ----
    print(f"\n[4] Running univariate logistic regression ...")
    univariate = univariate_analysis(df, target=target, save_path=figures_dir)
    if not univariate.empty:
        top_vars = univariate.head(10)["Variable"].tolist()
        findings["top_univariate_predictors"] = top_vars
    else:
        findings["top_univariate_predictors"] = []

    # ---- 3. Collinearity ----
    print(f"\n[5] Collinearity analysis ...")
    exclude_cols = [target, "AKI分期", "姓名", "ID", "id", "PatientID"]
    vif_df, high_corr_pairs = collinearity_analysis(
        df, exclude_cols=exclude_cols, save_path=figures_dir
    )

    if not vif_df.empty:
        high_vif = vif_df[vif_df["VIF"] > 10]
        findings["high_vif_count"] = len(high_vif)
        findings["high_vif_features"] = high_vif["Feature"].tolist() if not high_vif.empty else []
    else:
        findings["high_vif_count"] = 0
        findings["high_vif_features"] = []

    findings["high_corr_pairs_count"] = len(high_corr_pairs) if not high_corr_pairs.empty else 0

    # ---- 4. Distributions ----
    print(f"\n[6] Plotting distributions ...")
    dist_vars = [v for v in DEFAULT_CONTINUOUS_VARS if v in df.columns]
    if dist_vars:
        plot_distributions(df, vars=dist_vars, target=target, save_path=figures_dir)

    # ---- 5. Epidemiology ----
    print(f"\n[7] AKI epidemiology analysis ...")
    epi_findings = aki_epidemiology_analysis(df, save_path=figures_dir)
    for k, v in epi_findings.items():
        if isinstance(v, (int, float)):
            findings[f"epi_{k}"] = v

    # ---- 6. Target distribution plots ----
    print(f"\n[8] Target distribution plots ...")
    plot_target_distribution(df, target=target, save_path=figures_dir)

    # ---- 7. Pairwise analysis (top univariate features) ----
    print(f"\n[9] Pairwise feature analysis ...")
    top_features = findings.get("top_univariate_predictors", [])
    if top_features:
        pairwise_features = top_features[:10]
        corr_with_target = pairwise_feature_analysis(
            df, features=pairwise_features, target=target
        )
        if not corr_with_target.empty:
            findings["top_correlations_with_target"] = corr_with_target.head(5).to_dict("records")

    # ---- Summary ----
    print("\n" + "=" * 60)
    print("  EDA Complete — Key Findings")
    print("=" * 60)
    print(f"  Total patients: {findings['data_shape'][0]}")
    print(f"  Features: {findings['data_shape'][1]}")
    print(f"  AKI incidence: {findings.get('epi_overall_incidence', '?')}")
    print(f"  High-VIF features (>10): {findings.get('high_vif_count', '?')}")
    print(f"  High-correlation pairs: {findings.get('high_corr_pairs_count', '?')}")
    print(f"  Top predictors: {findings.get('top_univariate_predictors', [])[:5]}")
    print(f"\n  Outputs saved to: {output_dir}")
    print(f"    Tables: {tables_dir}")
    print(f"    Figures: {figures_dir}")
    print("=" * 60)

    return findings

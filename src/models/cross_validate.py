"""
AKI Prediction Project — Cross-Validation Trustworthiness Module
=================================================================
一等奖核心模块：五折交叉验证 + 均值ROC置信带 + Bootstrap置信区间

Provides:
    1. run_stratified_kfold_cv  — 五折CV + 每折AUC + 均值±标准差
    2. plot_cv_roc_curves       — 均值ROC曲线 + ±1std半透明置信带
    3. plot_cv_auc_distribution — Bootstrap AUC分布 + 95%CI
    4. create_cv_summary_table  — CV汇总表（医学期刊风格）

Author: 白菜卷队 · 广西科技大学 · 暑期数创 2026
"""

from __future__ import annotations

import os
import warnings
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import (
    roc_auc_score,
    roc_curve,
    auc,
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    brier_score_loss,
)
from sklearn.base import BaseEstimator

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Style & Palette
# ---------------------------------------------------------------------------
_PALETTE = [
    "#2a78d6",  # blue
    "#1baf7a",  # aqua
    "#eda100",  # yellow
    "#e34948",  # red
    "#4a3aa7",  # violet
    "#eb6834",  # orange
    "#e87ba4",  # magenta
    "#008300",  # green
]

_SURFACE = "#fcfcfb"
_PRIMARY_INK = "#0b0b0b"
_SECONDARY_INK = "#52514e"
_MUTED = "#898781"
_GRIDLINE = "#e1e0d9"
_BASELINE = "#c3c2b7"

# Try Chinese font
_CHINESE_FONTS = [
    "Microsoft YaHei", "SimHei", "WenQuanYi Micro Hei",
    "Noto Sans CJK SC", "PingFang SC", "sans-serif",
]
_FONT_CANDIDATES: List[str] = []
for fname in _CHINESE_FONTS:
    try:
        from matplotlib import font_manager
        font_manager.findfont(fname, fallback_to_default=False)
        _FONT_CANDIDATES.append(fname)
    except Exception:
        pass
_FONT_CANDIDATES.extend(["sans-serif", "DejaVu Sans"])

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": _FONT_CANDIDATES,
    "axes.unicode_minus": False,
    "figure.dpi": 150,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
})


# ============================================================================
# 1. Stratified K-Fold Cross-Validation
# ============================================================================

def run_stratified_kfold_cv(
    X: np.ndarray,
    y: np.ndarray,
    models_dict: Dict[str, BaseEstimator],
    n_splits: int = 5,
    random_state: int = 42,
    metrics: Optional[List[str]] = None,
) -> pd.DataFrame:
    """Run stratified 5-fold CV for each model and return per-fold scores.

    Parameters
    ----------
    X : np.ndarray of shape (n_samples, n_features)
    y : np.ndarray of shape (n_samples,)
    models_dict : dict of {model_name: fitted_or_unfitted_estimator}
    n_splits : int, default=5
    random_state : int, default=42
    metrics : list of str, optional
        Default: ['auc', 'accuracy', 'precision', 'recall', 'f1', 'brier']

    Returns
    -------
    pd.DataFrame
        Columns: Model, Fold, AUC, Accuracy, Precision, Recall, F1, Brier
    """
    if metrics is None:
        metrics = ["auc", "accuracy", "precision", "recall", "f1", "brier"]

    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=random_state)
    rows = []

    for model_name, model in models_dict.items():
        fold_aucs = []
        fold_scores: Dict[str, List[float]] = {m: [] for m in metrics}

        for fold_idx, (train_idx, val_idx) in enumerate(skf.split(X, y), 1):
            X_train_fold, X_val_fold = X[train_idx], X[val_idx]
            y_train_fold, y_val_fold = y[train_idx], y[val_idx]

            try:
                # Clone and fit
                from sklearn.base import clone
                model_clone = clone(model)
                model_clone.fit(X_train_fold, y_train_fold)

                if hasattr(model_clone, "predict_proba"):
                    y_prob = model_clone.predict_proba(X_val_fold)[:, 1]
                else:
                    y_prob = model_clone.decision_function(X_val_fold)
                    y_prob = (y_prob - y_prob.min()) / max(y_prob.max() - y_prob.min(), 1e-10)

                y_pred = (y_prob >= 0.5).astype(int)

                # Compute metrics
                auc_val = roc_auc_score(y_val_fold, y_prob)
                fold_aucs.append(auc_val)

                row = {
                    "Model": model_name,
                    "Fold": f"Fold {fold_idx}",
                    "AUC": round(auc_val, 4),
                }
                if "accuracy" in metrics:
                    row["Accuracy"] = round(accuracy_score(y_val_fold, y_pred), 4)
                if "precision" in metrics:
                    row["Precision"] = round(precision_score(y_val_fold, y_pred, zero_division=0), 4)
                if "recall" in metrics:
                    row["Recall"] = round(recall_score(y_val_fold, y_pred, zero_division=0), 4)
                if "f1" in metrics:
                    row["F1"] = round(f1_score(y_val_fold, y_pred, zero_division=0), 4)
                if "brier" in metrics:
                    row["Brier"] = round(brier_score_loss(y_val_fold, y_prob), 4)
                rows.append(row)

            except Exception as exc:
                print(f"  [WARN] {model_name} Fold {fold_idx} failed: {exc}")
                rows.append({
                    "Model": model_name,
                    "Fold": f"Fold {fold_idx}",
                    "AUC": np.nan,
                })

        # Add mean row
        if fold_aucs:
            mean_row = {"Model": model_name, "Fold": "Mean ± Std"}
            valid_aucs = [a for a in fold_aucs if not np.isnan(a)]
            if valid_aucs:
                mean_auc = np.mean(valid_aucs)
                std_auc = np.std(valid_aucs)
                mean_row["AUC"] = f"{mean_auc:.4f} ± {std_auc:.4f}"
            rows.append(mean_row)

    return pd.DataFrame(rows)


# ============================================================================
# 2. CV ROC Curves with Confidence Band
# ============================================================================

def plot_cv_roc_curves(
    X: np.ndarray,
    y: np.ndarray,
    models_dict: Dict[str, BaseEstimator],
    n_splits: int = 5,
    random_state: int = 42,
    save_path: str = "",
    figsize: Tuple[int, int] = (10, 8),
) -> Figure:
    """Plot mean ROC curves with ±1 std confidence bands from CV folds.

    For each model, trains on n_splits folds and plots:
    - Mean ROC curve (solid line)
    - ±1 standard deviation band (translucent fill)
    - AUC mean ± std in legend

    Parameters
    ----------
    X, y : arrays
    models_dict : dict of {name: estimator}
    n_splits : int
    random_state : int
    save_path : str
    figsize : tuple

    Returns
    -------
    matplotlib.figure.Figure
    """
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=random_state)
    mean_fpr = np.linspace(0, 1, 100)

    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_facecolor(_SURFACE)
    ax.set_facecolor(_SURFACE)

    # Random guess diagonal
    ax.plot([0, 1], [0, 1], "k--", lw=1.5, alpha=0.4, label="Random (AUC = 0.50)")

    for i, (model_name, model) in enumerate(models_dict.items()):
        color = _PALETTE[i % len(_PALETTE)]
        tprs = []
        aucs = []

        for fold_idx, (train_idx, val_idx) in enumerate(skf.split(X, y)):
            X_train_fold, X_val_fold = X[train_idx], X[val_idx]
            y_train_fold, y_val_fold = y[train_idx], y[val_idx]

            try:
                from sklearn.base import clone
                model_clone = clone(model)
                model_clone.fit(X_train_fold, y_train_fold)

                if hasattr(model_clone, "predict_proba"):
                    y_prob = model_clone.predict_proba(X_val_fold)[:, 1]
                else:
                    y_prob = model_clone.decision_function(X_val_fold)
                    y_prob = (y_prob - y_prob.min()) / max(y_prob.max() - y_prob.min(), 1e-10)

                fpr, tpr, _ = roc_curve(y_val_fold, y_prob)
                interp_tpr = np.interp(mean_fpr, fpr, tpr)
                interp_tpr[0] = 0.0
                tprs.append(interp_tpr)
                aucs.append(roc_auc_score(y_val_fold, y_prob))

                # Plot individual fold (thin, translucent)
                ax.plot(fpr, tpr, color=color, lw=0.6, alpha=0.25)
            except Exception:
                continue

        if tprs:
            mean_tpr = np.mean(tprs, axis=0)
            mean_tpr[-1] = 1.0
            mean_auc = auc(mean_fpr, mean_tpr)

            std_tpr = np.std(tprs, axis=0)
            tpr_upper = np.minimum(mean_tpr + std_tpr, 1.0)
            tpr_lower = np.maximum(mean_tpr - std_tpr, 0.0)

            auc_mean = np.mean(aucs)
            auc_std = np.std(aucs)

            # Mean ROC (bold)
            ax.plot(mean_fpr, mean_tpr, color=color, lw=2.5,
                    label=f"{model_name} (AUC = {auc_mean:.3f} ± {auc_std:.3f})")

            # ±1 std band
            ax.fill_between(mean_fpr, tpr_lower, tpr_upper,
                           color=color, alpha=0.15)

    # Axis labels (Chinese-English bilingual)
    ax.set_xlabel("1 - Specificity (False Positive Rate)",
                  color=_PRIMARY_INK, fontsize=12)
    ax.set_ylabel("Sensitivity (True Positive Rate)",
                  color=_PRIMARY_INK, fontsize=12)
    ax.set_title(f"{n_splits}-Fold Cross-Validation ROC Curves\n"
                 f"Mean ± 1 Std (N = {X.shape[0]})",
                 color=_PRIMARY_INK, fontsize=14, fontweight="bold")

    ax.legend(loc="lower right", framealpha=0.9, edgecolor=_GRIDLINE, fontsize=8)
    ax.set_xlim([-0.02, 1.02])
    ax.set_ylim([-0.02, 1.02])
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(_BASELINE)
    ax.spines["bottom"].set_color(_BASELINE)
    ax.tick_params(colors=_MUTED)
    ax.grid(True, alpha=0.35, color=_GRIDLINE, linewidth=0.5)
    ax.set_aspect("equal")

    # Annotation: clinical significance zone
    ax.annotate(
        "临床常用阈值区域\n(Clinical Decision Zone)",
        xy=(0.15, 0.85), fontsize=8, color=_MUTED,
        bbox=dict(boxstyle="round,pad=0.3", facecolor="#fffde7",
                  edgecolor=_GRIDLINE, alpha=0.8),
    )

    fig.tight_layout()

    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        fig.savefig(save_path, dpi=300, facecolor=fig.get_facecolor())
        print(f"  CV ROC curves saved: {save_path}")

    return fig


# ============================================================================
# 3. Bootstrap AUC Distribution Plot
# ============================================================================

def plot_cv_auc_distribution(
    X: np.ndarray,
    y: np.ndarray,
    models_dict: Dict[str, BaseEstimator],
    n_bootstrap: int = 1000,
    random_state: int = 42,
    save_path: str = "",
    figsize: Tuple[int, int] = (12, 5),
) -> Figure:
    """Plot bootstrap AUC distributions for all models with 95% CI.

    This is THE plot that makes reviewers trust your model.
    医学期刊级别的Bootstrap验证图。

    Parameters
    ----------
    X, y : arrays
    models_dict : dict
    n_bootstrap : int, default=1000
    random_state : int
    save_path : str
    figsize : tuple

    Returns
    -------
    matplotlib.figure.Figure
    """
    from sklearn.base import clone

    n_models = len(models_dict)
    fig, axes = plt.subplots(1, n_models, figsize=figsize, squeeze=False)
    axes = axes[0]
    fig.patch.set_facecolor(_SURFACE)

    if n_models == 1:
        axes = np.array([axes])

    rng = np.random.default_rng(random_state)
    n_samples = len(y)

    summary_rows = []

    for ax, (model_name, model) in zip(axes, models_dict.items()):
        ax.set_facecolor(_SURFACE)

        # Bootstrap
        bootstrap_aucs = []
        model_clone = clone(model)

        # Fit on full data first
        try:
            model_clone.fit(X, y)
        except Exception:
            continue

        for _ in range(n_bootstrap):
            indices = rng.integers(0, n_samples, size=n_samples)
            X_boot, y_boot = X[indices], y[indices]

            if len(np.unique(y_boot)) < 2:
                continue

            try:
                if hasattr(model_clone, "predict_proba"):
                    y_prob = model_clone.predict_proba(X_boot)[:, 1]
                else:
                    y_prob = model_clone.decision_function(X_boot)
                    y_prob = (y_prob - y_prob.min()) / max(y_prob.max() - y_prob.min(), 1e-10)
                bootstrap_aucs.append(roc_auc_score(y_boot, y_prob))
            except Exception:
                continue

        if len(bootstrap_aucs) < 100:
            ax.text(0.5, 0.5, "Not enough\nvalid samples", ha="center", va="center",
                   transform=ax.transAxes, color=_MUTED)
            continue

        auc_arr = np.array(bootstrap_aucs)
        mean_auc = np.mean(auc_arr)
        ci_lower = np.percentile(auc_arr, 2.5)
        ci_upper = np.percentile(auc_arr, 97.5)
        color = _PALETTE[list(models_dict.keys()).index(model_name) % len(_PALETTE)]

        # Histogram
        ax.hist(auc_arr, bins=35, alpha=0.7, color=color, edgecolor="white",
                density=True, linewidth=0.3)

        # Mean line
        ax.axvline(mean_auc, color="#e34948", lw=2, linestyle="-",
                  label=f"Mean AUC = {mean_auc:.4f}")

        # CI lines
        ax.axvline(ci_lower, color=_MUTED, lw=1.5, linestyle="--", alpha=0.8)
        ax.axvline(ci_upper, color=_MUTED, lw=1.5, linestyle="--", alpha=0.8)

        # CI fill
        ylim = ax.get_ylim()
        ax.fill_betweenx([0, ylim[1]], ci_lower, ci_upper, alpha=0.1, color=color)

        # Text annotation
        ax.text(0.98, 0.95,
                f"AUC = {mean_auc:.3f}\n95% CI: [{ci_lower:.3f}, {ci_upper:.3f}]",
                transform=ax.transAxes, ha="right", va="top",
                fontsize=8, bbox=dict(boxstyle="round,pad=0.3",
                                      facecolor="white", edgecolor=_GRIDLINE, alpha=0.9))

        ax.set_title(model_name, color=_PRIMARY_INK, fontsize=11, fontweight="bold")
        ax.set_xlabel("AUC", color=_SECONDARY_INK, fontsize=9)
        ax.set_ylabel("Density", color=_SECONDARY_INK, fontsize=9)
        ax.legend(loc="upper left", fontsize=7, framealpha=0.8)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.tick_params(colors=_MUTED, labelsize=8)

        summary_rows.append({
            "Model": model_name,
            "Mean_AUC": round(mean_auc, 4),
            "CI_Lower": round(ci_lower, 4),
            "CI_Upper": round(ci_upper, 4),
            "CI_Width": round(ci_upper - ci_lower, 4),
            "N_Bootstrap": len(bootstrap_aucs),
        })

    fig.suptitle(f"Bootstrap AUC Distribution (n = {n_bootstrap}, 95% CI)",
                 color=_PRIMARY_INK, fontsize=14, fontweight="bold", y=1.02)
    fig.tight_layout()

    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        fig.savefig(save_path, dpi=300, facecolor=fig.get_facecolor())
        print(f"  Bootstrap AUC distribution saved: {save_path}")

    return fig


# ============================================================================
# 4. CV Summary Table (Medical Journal Style)
# ============================================================================

def create_cv_summary_table(
    X: np.ndarray,
    y: np.ndarray,
    models_dict: Dict[str, BaseEstimator],
    n_splits: int = 5,
    n_bootstrap: int = 1000,
    random_state: int = 42,
    save_path: str = "",
) -> pd.DataFrame:
    """Create a comprehensive CV summary table.

    Columns: Model, CV_AUC_Mean, CV_AUC_Std, Bootstrap_AUC_Mean,
             AUC_95CI_Lower, AUC_95CI_Upper, Brier_Mean

    This is the ONE table that should go in your PPT.
    """
    from sklearn.base import clone

    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=random_state)
    rng = np.random.default_rng(random_state)
    n_samples = len(y)

    rows = []
    for model_name, model in models_dict.items():
        # --- CV AUC ---
        cv_aucs = []
        cv_briers = []
        for train_idx, val_idx in skf.split(X, y):
            X_tr, X_val = X[train_idx], X[val_idx]
            y_tr, y_val = y[train_idx], y[val_idx]

            try:
                model_clone = clone(model)
                model_clone.fit(X_tr, y_tr)
                if hasattr(model_clone, "predict_proba"):
                    y_prob = model_clone.predict_proba(X_val)[:, 1]
                else:
                    y_prob = model_clone.decision_function(X_val)
                    y_prob = (y_prob - y_prob.min()) / max(y_prob.max() - y_prob.min(), 1e-10)

                cv_aucs.append(roc_auc_score(y_val, y_prob))
                cv_briers.append(brier_score_loss(y_val, y_prob))
            except Exception:
                continue

        # --- Bootstrap ---
        model_clone = clone(model)
        try:
            model_clone.fit(X, y)
        except Exception:
            continue

        boot_aucs = []
        for _ in range(n_bootstrap):
            indices = rng.integers(0, n_samples, size=n_samples)
            y_boot = y[indices]
            if len(np.unique(y_boot)) < 2:
                continue
            try:
                if hasattr(model_clone, "predict_proba"):
                    y_prob = model_clone.predict_proba(X[indices])[:, 1]
                else:
                    y_prob = model_clone.decision_function(X[indices])
                    y_prob = (y_prob - y_prob.min()) / max(y_prob.max() - y_prob.min(), 1e-10)
                boot_aucs.append(roc_auc_score(y_boot, y_prob))
            except Exception:
                continue

        boot_arr = np.array(boot_aucs)

        rows.append({
            "模型 Model": model_name,
            "CV AUC (均值)": round(np.mean(cv_aucs), 4) if cv_aucs else np.nan,
            "CV AUC (标准差)": round(np.std(cv_aucs), 4) if cv_aucs else np.nan,
            "Bootstrap AUC": round(np.mean(boot_arr), 4) if len(boot_arr) > 0 else np.nan,
            "95% CI 下限": round(np.percentile(boot_arr, 2.5), 4) if len(boot_arr) > 0 else np.nan,
            "95% CI 上限": round(np.percentile(boot_arr, 97.5), 4) if len(boot_arr) > 0 else np.nan,
            "Brier Score": round(np.mean(cv_briers), 4) if cv_briers else np.nan,
        })

    df = pd.DataFrame(rows)
    if "CV AUC (均值)" in df.columns:
        df = df.sort_values("CV AUC (均值)", ascending=False).reset_index(drop=True)

    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        df.to_csv(save_path, index=False, encoding="utf-8-sig")
        print(f"  CV summary table saved: {save_path}")

    return df


# ============================================================================
# 5. Run Full CV Report
# ============================================================================

def run_full_cv_report(
    X: np.ndarray,
    y: np.ndarray,
    models_dict: Dict[str, BaseEstimator],
    n_splits: int = 5,
    n_bootstrap: int = 1000,
    random_state: int = 42,
    output_dir: str = "outputs/",
) -> Dict[str, Any]:
    """Run the complete CV trustworthiness analysis pipeline.

    Generates:
    1. Per-fold CV results table → outputs/tables/cv_fold_results.csv
    2. Mean ROC curves with CI bands → outputs/figures/cv_roc_with_ci.png
    3. Bootstrap AUC distributions → outputs/figures/bootstrap_auc_dist.png
    4. Summary table → outputs/tables/cv_summary.csv

    Returns
    -------
    dict with keys: fold_results_df, summary_df, figures
    """
    print("=" * 70)
    print("🔬 交叉验证可信度分析 | CV Trustworthiness Analysis")
    print("=" * 70)
    print(f"  数据量: N = {X.shape[0]}, 特征数: {X.shape[1]}")
    print(f"  模型数: {len(models_dict)}")
    print(f"  CV折数: {n_splits}, Bootstrap: {n_bootstrap}")
    print("-" * 70)

    os.makedirs(os.path.join(output_dir, "tables"), exist_ok=True)
    os.makedirs(os.path.join(output_dir, "figures"), exist_ok=True)

    # 1. Per-fold CV
    print("\n📊 Step 1/4: 五折交叉验证...")
    fold_df = run_stratified_kfold_cv(X, y, models_dict, n_splits=n_splits,
                                       random_state=random_state)
    fold_path = os.path.join(output_dir, "tables", "cv_fold_results.csv")
    fold_df.to_csv(fold_path, index=False, encoding="utf-8-sig")

    # Print fold results nicely
    print("\n  Per-Fold AUC:")
    for model_name in models_dict:
        model_rows = fold_df[fold_df["Model"] == model_name]
        fold_aucs = model_rows[model_rows["Fold"] != "Mean ± Std"]["AUC"].dropna()
        if len(fold_aucs) > 0:
            auc_str = " | ".join(f"{a:.4f}" for a in fold_aucs)
            print(f"    {model_name:<20}: {auc_str}  → Mean = {np.mean(fold_aucs):.4f} ± {np.std(fold_aucs):.4f}")

    # 2. CV ROC curves with CI bands
    print("\n📈 Step 2/4: 绘制CV ROC曲线(置信带)...")
    roc_path = os.path.join(output_dir, "figures", "cv_roc_with_ci.png")
    fig_roc = plot_cv_roc_curves(X, y, models_dict, n_splits=n_splits,
                                  random_state=random_state, save_path=roc_path)
    plt.close(fig_roc)

    # 3. Bootstrap AUC distribution
    print("\n🎯 Step 3/4: Bootstrap AUC分布...")
    boot_path = os.path.join(output_dir, "figures", "bootstrap_auc_dist.png")
    fig_boot = plot_cv_auc_distribution(X, y, models_dict, n_bootstrap=n_bootstrap,
                                         random_state=random_state, save_path=boot_path)
    plt.close(fig_boot)

    # 4. Summary table
    print("\n📋 Step 4/4: 生成汇总表...")
    summary_path = os.path.join(output_dir, "tables", "cv_summary.csv")
    summary_df = create_cv_summary_table(X, y, models_dict, n_splits=n_splits,
                                          n_bootstrap=n_bootstrap,
                                          random_state=random_state,
                                          save_path=summary_path)

    # Print summary
    print("\n" + "=" * 70)
    print("✅ CV分析完成 | CV Analysis Complete")
    print("=" * 70)
    print(summary_df.to_string(index=False))
    print(f"\n  📁 输出文件:")
    print(f"     {fold_path}")
    print(f"     {roc_path}")
    print(f"     {boot_path}")
    print(f"     {summary_path}")

    return {
        "fold_results_df": fold_df,
        "summary_df": summary_df,
        "figures": {
            "cv_roc": roc_path,
            "bootstrap_auc": boot_path,
        },
    }


# ============================================================================
if __name__ == "__main__":
    print("Cross-validation trustworthiness module loaded successfully.")
    print("Usage: from src.models.cross_validate import run_full_cv_report")

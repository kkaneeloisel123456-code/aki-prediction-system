"""
AKI Prediction Project — Ablation Study Module
===============================================
一等奖核心模块：模型消融实验，证明"为什么你的方法好？"

Features:
    1. run_ablation_study       — 按特征组跑消融实验
    2. plot_ablation_heatmap    — 模型×特征组AUC热力图
    3. plot_ablation_barchart   — 消融对比柱状图
    4. run_full_ablation_report — 一键消融分析管线

复用: src/models/train.py 的 cross_validate_model()
      src/models/evaluate.py 的 compute_all_metrics()

Author: 白菜卷队 · 广西科技大学 · 暑期数创 2026
"""

from __future__ import annotations

import os
import warnings
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from sklearn.base import BaseEstimator, clone
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import roc_auc_score

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Style & Palette
# ---------------------------------------------------------------------------
_PALETTE = [
    "#2a78d6", "#1baf7a", "#eda100", "#e34948",
    "#4a3aa7", "#eb6834", "#e87ba4", "#008300",
]

_SURFACE = "#fcfcfb"
_PRIMARY_INK = "#0b0b0b"
_SECONDARY_INK = "#52514e"
_MUTED = "#898781"
_GRIDLINE = "#e1e0d9"
_BASELINE = "#c3c2b7"

try:
    from matplotlib import font_manager
    for fname in ["Microsoft YaHei", "SimHei", "PingFang SC", "sans-serif"]:
        try:
            font_manager.findfont(fname, fallback_to_default=False)
            plt.rcParams["font.sans-serif"] = [fname, "DejaVu Sans"]
            break
        except Exception:
            pass
except Exception:
    pass
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 150
plt.rcParams["savefig.dpi"] = 300
plt.rcParams["savefig.bbox"] = "tight"


# ============================================================================
# 1. Ablation Feature Groups
# ============================================================================

def auto_discover_feature_groups(
    feature_names: List[str],
    X: Optional[pd.DataFrame] = None,
) -> Dict[str, List[str]]:
    """Auto-discover feature groups from feature name patterns.

    Groups detected by prefix/suffix matching:
    - 基础人口学变量 (年龄, 性别, BMI, etc.)
    - 术前实验室指标 (术前Scr, 术前eGFR, etc.)
    - 术中指标 (手术时间, 术中失血量, etc.)
    - 术后指标 (ICU*, 术后*, etc.)
    - 肾功能相关 (Scr, eGFR, BUN, UA, etc.)
    - 炎症/免疫 (CRP, WBC, NLR, etc.)
    - 合并症 (高血压, 糖尿病, etc.)

    Returns
    -------
    dict of {group_name: [feature_names]}
    """
    groups: Dict[str, List[str]] = {
        "基础人口学变量": [],
        "术前实验室指标": [],
        "术中指标": [],
        "术后指标": [],
        "肾功能相关": [],
        "炎症/免疫指标": [],
        "合并症": [],
        "其他": [],
    }

    for f in feature_names:
        f_str = str(f)
        # Demographics
        if any(kw in f_str for kw in ["年龄", "性别", "BMI", "体重", "身高"]):
            groups["基础人口学变量"].append(f_str)
        # Pre-op labs
        elif "术前" in f_str and not any(kw in f_str for kw in ["术中", "术后"]):
            groups["术前实验室指标"].append(f_str)
        # Intra-op
        elif any(kw in f_str for kw in ["术中", "手术时间", "失血", "尿量",
                                          "晶体", "胶体", "麻醉"]):
            groups["术中指标"].append(f_str)
        # Post-op / ICU
        elif any(kw in f_str for kw in ["术后", "ICU", "通气"]):
            groups["术后指标"].append(f_str)
        # Renal function
        elif any(kw in f_str for kw in ["Scr", "肌酐", "eGFR", "BUN",
                                          "尿素", "UA", "尿酸", "尿量",
                                          "KIM", "NGAL", "CysC"]):
            groups["肾功能相关"].append(f_str)
        # Inflammation / immune
        elif any(kw in f_str for kw in ["CRP", "WBC", "NLR", "PLR",
                                          "白细胞", "中性", "淋巴",
                                          "PCT", "IL"]):
            groups["炎症/免疫指标"].append(f_str)
        # Comorbidities
        elif any(kw in f_str for kw in ["高血压", "糖尿病", "冠心病",
                                          "心衰", "COPD", "CKD"]):
            groups["合并症"].append(f_str)
        else:
            groups["其他"].append(f_str)

    # Remove empty groups
    groups = {k: v for k, v in groups.items() if v}

    # Add "所有特征" group
    groups["所有特征 (All Features)"] = list(feature_names)

    # Add "Top SHAP特征" if we have > 20 features
    if len(feature_names) > 20:
        groups["排除肾功能指标"] = [f for f in feature_names
                               if f not in groups.get("肾功能相关", [])]

    return groups


# ============================================================================
# 2. Run Ablation Study
# ============================================================================

def run_ablation_study(
    X: np.ndarray,
    y: np.ndarray,
    model: BaseEstimator,
    feature_names: List[str],
    feature_groups: Optional[Dict[str, List[str]]] = None,
    cv: int = 5,
    random_state: int = 42,
) -> pd.DataFrame:
    """Run ablation study: train model with different feature subsets.

    For each feature group, extracts the corresponding subset of X columns,
    retrains the model using 5-fold CV, and records mean AUC ± std.

    Parameters
    ----------
    X : np.ndarray of shape (n_samples, n_features)
        Full feature matrix.
    y : np.ndarray of shape (n_samples,)
        Binary target.
    model : BaseEstimator
        Model to evaluate (fitted or unfitted — will be cloned each time).
    feature_names : list of str
        Column names corresponding to X columns.
    feature_groups : dict of {group_name: [feature_names]}, optional
        If None, auto-discovers groups via auto_discover_feature_groups().
    cv : int, default=5
    random_state : int, default=42

    Returns
    -------
    pd.DataFrame with columns:
        Feature_Group, N_Features, Features_Preview,
        Mean_AUC, Std_AUC, Delta_vs_Full
    """
    if feature_groups is None:
        feature_groups = auto_discover_feature_groups(feature_names)

    # If X is DataFrame, convert to numpy for indexing
    if isinstance(X, pd.DataFrame):
        X_np = X.values
        col_map = {name: idx for idx, name in enumerate(X.columns)}
    else:
        X_np = X
        col_map = {name: idx for idx, name in enumerate(feature_names)}

    skf = StratifiedKFold(n_splits=cv, shuffle=True, random_state=random_state)
    rows = []

    # First pass: find "all features" AUC for delta calculation
    full_auc = None

    for group_name, group_features in feature_groups.items():
        # Map feature names to column indices
        indices = [col_map[f] for f in group_features if f in col_map]
        if len(indices) == 0:
            continue

        X_sub = X_np[:, indices]
        fold_aucs = []

        for train_idx, val_idx in skf.split(X_sub, y):
            X_tr, X_val = X_sub[train_idx], X_sub[val_idx]
            y_tr, y_val = y[train_idx], y[val_idx]

            try:
                model_clone = clone(model)
                model_clone.fit(X_tr, y_tr)

                if hasattr(model_clone, "predict_proba"):
                    y_prob = model_clone.predict_proba(X_val)[:, 1]
                else:
                    y_prob = model_clone.decision_function(X_val)
                    y_prob = (y_prob - y_prob.min()) / max(y_prob.max() - y_prob.min(), 1e-10)

                fold_aucs.append(roc_auc_score(y_val, y_prob))
            except Exception as exc:
                print(f"  [WARN] {group_name} fold failed: {exc}")
                continue

        if fold_aucs:
            mean_auc = np.mean(fold_aucs)
            std_auc = np.std(fold_aucs)

            if group_name == "所有特征 (All Features)" or "All" in group_name:
                full_auc = mean_auc

            preview = ", ".join(group_features[:5])
            if len(group_features) > 5:
                preview += f" ... (+{len(group_features) - 5})"

            rows.append({
                "特征组 Feature Group": group_name,
                "特征数 N_Features": len(indices),
                "特征预览": preview,
                "Mean AUC": round(mean_auc, 4),
                "Std AUC": round(std_auc, 4),
            })

    # Compute delta vs full
    df = pd.DataFrame(rows)
    if full_auc is not None:
        df["Delta vs Full"] = df["Mean AUC"].apply(
            lambda x: round(x - full_auc, 4)
        )
    df = df.sort_values("Mean AUC", ascending=False).reset_index(drop=True)

    return df


def run_multi_model_ablation(
    X: np.ndarray,
    y: np.ndarray,
    models_dict: Dict[str, BaseEstimator],
    feature_names: List[str],
    feature_groups: Optional[Dict[str, List[str]]] = None,
    cv: int = 5,
    random_state: int = 42,
) -> Dict[str, pd.DataFrame]:
    """Run ablation study across multiple models.

    Returns dict of {model_name: ablation_df}.
    """
    results = {}
    for model_name, model in models_dict.items():
        print(f"  Running ablation for {model_name}...")
        df = run_ablation_study(
            X, y, model, feature_names,
            feature_groups=feature_groups,
            cv=cv, random_state=random_state,
        )
        results[model_name] = df
    return results


# ============================================================================
# 3. Ablation Visualization
# ============================================================================

def plot_ablation_barchart(
    ablation_df: pd.DataFrame,
    model_name: str = "Model",
    save_path: str = "",
    figsize: Tuple[int, int] = (10, 7),
) -> Figure:
    """Plot ablation study as horizontal bar chart with error bars.

    Parameters
    ----------
    ablation_df : pd.DataFrame from run_ablation_study()
    model_name : str
    save_path : str
    figsize : tuple

    Returns
    -------
    matplotlib.figure.Figure
    """
    df = ablation_df.sort_values("Mean AUC", ascending=True)

    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_facecolor(_SURFACE)
    ax.set_facecolor(_SURFACE)

    groups = df["特征组 Feature Group"].values
    aucs = df["Mean AUC"].values
    stds = df["Std AUC"].values
    n_features = df["特征数 N_Features"].values

    # Color by feature count: more features = darker
    max_n = max(n_features) if len(n_features) > 0 else 1
    colors = []
    for n in n_features:
        if n >= max_n * 0.9:
            colors.append(_PALETTE[0])  # blue for full/near-full
        elif n >= max_n * 0.5:
            colors.append(_PALETTE[1])  # aqua for medium
        else:
            colors.append(_PALETTE[3])  # red for sparse

    # Highlight "all features" row
    for i, g in enumerate(groups):
        if "All" in g or "所有" in g:
            colors[i] = "#e34948"  # red highlight

    bars = ax.barh(range(len(groups)), aucs, xerr=stds,
                   color=colors, edgecolor="white", linewidth=0.5,
                   capsize=3, alpha=0.9)

    # Annotate with N features
    for i, (auc, n) in enumerate(zip(aucs, n_features)):
        ax.text(auc + 0.01, i, f"n={n}", va="center",
                fontsize=9, color=_SECONDARY_INK)

    # Reference line at full model AUC
    if "All" in str(groups[-1]) or "所有" in str(groups[-1]):
        full_auc_val = aucs[-1]
        ax.axvline(full_auc_val, color=_MUTED, linestyle="--", lw=1.5, alpha=0.6,
                   label=f"Full Model AUC = {full_auc_val:.4f}")

    ax.set_yticks(range(len(groups)))
    ax.set_yticklabels(groups, fontsize=10, color=_PRIMARY_INK)
    ax.set_xlabel("AUC (5-Fold CV Mean ± Std)", color=_PRIMARY_INK, fontsize=12)
    ax.set_title(f"消融实验 | Ablation Study — {model_name}\n不同特征子集的预测性能对比",
                 color=_PRIMARY_INK, fontsize=14, fontweight="bold")

    # Legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=_PALETTE[0], label="特征数较多 (≥90%)"),
        Patch(facecolor=_PALETTE[1], label="特征数中等 (50-90%)"),
        Patch(facecolor=_PALETTE[3], label="特征数较少 (<50%)"),
        Patch(facecolor="#e34948", label="全特征模型 (Full Model)"),
    ]
    ax.legend(handles=legend_elements, loc="lower right", fontsize=8,
              framealpha=0.8, edgecolor=_GRIDLINE)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(_BASELINE)
    ax.spines["bottom"].set_color(_BASELINE)
    ax.tick_params(colors=_MUTED)
    ax.grid(True, alpha=0.3, color=_GRIDLINE, linewidth=0.5, axis="x")

    fig.tight_layout()

    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        fig.savefig(save_path, dpi=300, facecolor=fig.get_facecolor())
        print(f"  Ablation bar chart saved: {save_path}")

    return fig


def plot_ablation_heatmap(
    multi_model_results: Dict[str, pd.DataFrame],
    save_path: str = "",
    figsize: Optional[Tuple[int, int]] = None,
) -> Figure:
    """Plot multi-model ablation results as a heatmap.

    Rows = feature groups, Columns = models, Values = AUC.
    Sorted by mean AUC across models.

    Parameters
    ----------
    multi_model_results : dict of {model_name: ablation_df}
    save_path : str
    figsize : tuple, optional

    Returns
    -------
    matplotlib.figure.Figure
    """
    # Build pivot table
    records = []
    for model_name, df in multi_model_results.items():
        for _, row in df.iterrows():
            records.append({
                "Model": model_name,
                "Feature_Group": row["特征组 Feature Group"],
                "AUC": row["Mean AUC"],
                "N_Features": row["特征数 N_Features"],
            })

    pivot_df = pd.DataFrame(records)
    heatmap_data = pivot_df.pivot_table(
        values="AUC", index="Feature_Group", columns="Model", aggfunc="mean"
    )

    # Sort rows by mean AUC across models
    row_order = heatmap_data.mean(axis=1).sort_values(ascending=False).index.tolist()
    heatmap_data = heatmap_data.loc[row_order]

    n_rows, n_cols = heatmap_data.shape
    if figsize is None:
        figsize = (max(8, n_cols * 2.5), max(5, n_rows * 0.6))

    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_facecolor(_SURFACE)
    ax.set_facecolor(_SURFACE)

    # Determine color range
    vmin = heatmap_data.values.min()
    vmax = heatmap_data.values.max()

    im = ax.imshow(heatmap_data.values, aspect="auto", cmap="RdYlGn",
                   vmin=vmin - 0.02, vmax=vmax + 0.02, interpolation="nearest")

    # Annotate cells
    for i in range(n_rows):
        for j in range(n_cols):
            val = heatmap_data.values[i, j]
            if not np.isnan(val):
                text_color = "white" if val < vmin + (vmax - vmin) * 0.5 else _PRIMARY_INK
                ax.text(j, i, f"{val:.3f}", ha="center", va="center",
                       fontsize=10, fontweight="bold", color=text_color)

    ax.set_xticks(range(n_cols))
    ax.set_xticklabels(heatmap_data.columns, rotation=30, ha="right",
                       fontsize=10, color=_PRIMARY_INK)
    ax.set_yticks(range(n_rows))
    ax.set_yticklabels(heatmap_data.index, fontsize=10, color=_PRIMARY_INK)
    ax.set_title("消融实验热力图 | Ablation Study Heatmap\n模型 × 特征组 AUC对比",
                 color=_PRIMARY_INK, fontsize=14, fontweight="bold")

    # Colorbar
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("AUC", color=_PRIMARY_INK, fontsize=10)
    cbar.ax.tick_params(colors=_MUTED)
    cbar.outline.set_visible(False)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()

    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        fig.savefig(save_path, dpi=300, facecolor=fig.get_facecolor())
        print(f"  Ablation heatmap saved: {save_path}")

    return fig


# ============================================================================
# 4. Model Comparison for Ablation (消融 + 模型组合)
# ============================================================================

def create_ablation_comparison_table(
    multi_model_results: Dict[str, pd.DataFrame],
    save_path: str = "",
) -> pd.DataFrame:
    """Create a master comparison table: models × feature groups.

    Returns wide-format DataFrame suitable for papers.
    """
    rows = []
    for model_name, df in multi_model_results.items():
        for _, row in df.iterrows():
            rows.append({
                "模型 Model": model_name,
                "特征组 Feature Group": row["特征组 Feature Group"],
                "特征数": row["特征数 N_Features"],
                "AUC (5-fold CV)": row["Mean AUC"],
                "AUC Std": row["Std AUC"],
                "Δ vs Full Model": row.get("Delta vs Full", ""),
            })

    result_df = pd.DataFrame(rows)

    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        result_df.to_csv(save_path, index=False, encoding="utf-8-sig")
        print(f"  Ablation comparison table saved: {save_path}")

    return result_df


# ============================================================================
# 5. Run Full Ablation Report
# ============================================================================

def run_full_ablation_report(
    X: np.ndarray,
    y: np.ndarray,
    models_dict: Dict[str, BaseEstimator],
    feature_names: List[str],
    feature_groups: Optional[Dict[str, List[str]]] = None,
    cv: int = 5,
    random_state: int = 42,
    output_dir: str = "outputs/",
) -> Dict[str, Any]:
    """Run the complete ablation study pipeline.

    Generates:
    1. Per-model ablation bar charts → outputs/figures/ablation_{model}.png
    2. Multi-model ablation heatmap → outputs/figures/ablation_heatmap.png
    3. Comparison table → outputs/tables/ablation_results.csv

    Returns
    -------
    dict with keys: results, comparison_df, figures
    """
    print("=" * 70)
    print("🔬 消融实验分析 | Ablation Study Analysis")
    print("=" * 70)
    print(f"  数据量: N = {X.shape[0]}, 特征数: {X.shape[1]}")
    print(f"  模型数: {len(models_dict)}")
    print(f"  CV折数: {cv}")

    if feature_groups is None:
        feature_groups = auto_discover_feature_groups(feature_names)
        print(f"  自动发现特征组: {list(feature_groups.keys())}")
    print("-" * 70)

    os.makedirs(os.path.join(output_dir, "tables"), exist_ok=True)
    os.makedirs(os.path.join(output_dir, "figures"), exist_ok=True)

    # 1. Run ablation for each model
    print("\n📊 Step 1/3: 逐模型消融实验...")
    results = run_multi_model_ablation(
        X, y, models_dict, feature_names,
        feature_groups=feature_groups,
        cv=cv, random_state=random_state,
    )

    # 2. Per-model bar charts
    print("\n📈 Step 2/3: 绘制消融柱状图...")
    for model_name, df in results.items():
        save_name = f"ablation_{model_name.lower().replace(' ', '_')}.png"
        fig = plot_ablation_barchart(
            df, model_name=model_name,
            save_path=os.path.join(output_dir, "figures", save_name),
        )
        plt.close(fig)

    # 3. Multi-model heatmap
    heatmap_path = os.path.join(output_dir, "figures", "ablation_heatmap.png")
    fig_heat = plot_ablation_heatmap(results, save_path=heatmap_path)
    plt.close(fig_heat)

    # 4. Comparison table
    print("\n📋 Step 3/3: 生成汇总表...")
    table_path = os.path.join(output_dir, "tables", "ablation_results.csv")
    comparison_df = create_ablation_comparison_table(results, save_path=table_path)

    # Print summary
    print("\n" + "=" * 70)
    print("✅ 消融实验完成 | Ablation Study Complete")
    print("=" * 70)

    # Show key insight
    for model_name, df in results.items():
        full_row = df[df["特征组 Feature Group"].str.contains("All|所有", na=False)]
        if not full_row.empty:
            full_auc = full_row["Mean AUC"].values[0]
            print(f"\n  {model_name}: Full Model AUC = {full_auc:.4f}")

    print(f"\n  💡 关键洞察: 消融实验证明了各组特征的独立贡献，")
    print(f"     回答了'为什么你的方法好？'这个一等奖答辩必问问题。")
    print(f"\n  📁 输出文件:")
    print(f"     {output_dir}figures/ablation_*.png")
    print(f"     {heatmap_path}")
    print(f"     {table_path}")

    return {
        "results": results,
        "comparison_df": comparison_df,
        "figures": {
            "heatmap": heatmap_path,
            "per_model": [os.path.join(output_dir, "figures",
                         f"ablation_{name.lower().replace(' ', '_')}.png")
                         for name in results],
        },
    }


# ============================================================================
if __name__ == "__main__":
    print("Ablation study module loaded successfully.")
    print("Usage: from src.models.ablation import run_full_ablation_report")

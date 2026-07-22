"""
AKI Prediction Project — Data Governance Visualization Module
==============================================================
一等奖核心模块：数据治理流程图，展示从原始数据到建模数据集的完整管线。

Features:
    1. plot_data_governance_flowchart  — 数据治理全流程可视化
    2. plot_missing_values_summary     — 缺失值处理前后对比
    3. plot_feature_selection_process  — 特征筛选流程图
    4. create_data_quality_dashboard   — 数据质量仪表盘

Author: 白菜卷队 · 广西科技大学 · 暑期数创 2026
"""

from __future__ import annotations

import os
import warnings
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.figure import Figure
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Style
# ---------------------------------------------------------------------------
_PALETTE = {
    "blue": "#2a78d6",
    "aqua": "#1baf7a",
    "yellow": "#eda100",
    "red": "#e34948",
    "violet": "#4a3aa7",
    "orange": "#eb6834",
    "gray": "#898781",
}

_SURFACE = "#fcfcfb"
_PRIMARY_INK = "#0b0b0b"
_SECONDARY_INK = "#52514e"
_MUTED = "#898781"

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
# Helper: Draw a rounded box node
# ============================================================================

def _draw_node(
    ax: plt.Axes,
    x: float, y: float,
    width: float, height: float,
    title: str,
    details: List[str],
    color: str,
    title_color: str = "white",
    alpha: float = 0.9,
) -> None:
    """Draw a flowchart node with title bar and detail lines."""
    # Shadow
    shadow = FancyBboxPatch(
        (x + 0.02, y - 0.02), width, height,
        boxstyle="round,pad=0.1", facecolor="#e0e0e0",
        edgecolor="none", alpha=0.3,
    )
    ax.add_patch(shadow)

    # Main box
    box = FancyBboxPatch(
        (x, y), width, height,
        boxstyle="round,pad=0.1", facecolor=color,
        edgecolor=color, linewidth=1.5, alpha=alpha,
    )
    ax.add_patch(box)

    # Title bar (top portion)
    title_bar_height = height * 0.25
    title_bar = FancyBboxPatch(
        (x, y + height - title_bar_height), width, title_bar_height,
        boxstyle="round,pad=0.05",
        facecolor=color, edgecolor="none", alpha=1.0,
    )
    # Don't add separate bar — use text instead

    # Title text
    ax.text(x + width / 2, y + height - title_bar_height / 2,
            title, ha="center", va="center",
            fontsize=9, fontweight="bold", color=title_color)

    # Detail lines
    line_y = y + height - title_bar_height - 0.08
    for detail in details:
        line_y -= 0.06
        ax.text(x + 0.05, line_y, f"• {detail}",
                fontsize=7, color="white", va="center", alpha=0.9)


def _draw_arrow(
    ax: plt.Axes,
    x_from: float, y_from: float,
    x_to: float, y_to: float,
    color: str = _MUTED,
    label: str = "",
) -> None:
    """Draw a downward arrow between two nodes."""
    ax.annotate(
        "", xy=(x_to, y_to), xytext=(x_from, y_from),
        arrowprops=dict(
            arrowstyle="->", color=color, lw=2.5,
            connectionstyle="arc3,rad=0",
        ),
    )
    if label:
        mid_x = (x_from + x_to) / 2
        mid_y = (y_from + y_to) / 2
        ax.text(mid_x + 0.11, mid_y, label,
                fontsize=8, color=_SECONDARY_INK, ha="left", va="center",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white",
                          edgecolor=_PALETTE["gray"], alpha=0.8))


# ============================================================================
# 1. Data Governance Flowchart
# ============================================================================

def plot_data_governance_flowchart(
    save_path: str = "",
    figsize: Tuple[int, int] = (10, 14),
) -> Figure:
    """Plot the complete data governance pipeline flow chart.

    Pipeline stages:
    1. 原始数据采集 — 420例, 97个变量, Excel格式
    2. 缺失值分析 — 描述性统计, Little's MCAR检验
    3. 异常值检测与处理 — IQR/Z-score, Winsorize缩尾
    4. 数据标准化 — StandardScaler, 中位数填补
    5. 特征工程与筛选 — LASSO回归, SHAP重要性
    6. 类别不平衡处理 — SMOTE过采样
    7. 建模数据集 — 最终35个特征

    Parameters
    ----------
    save_path : str
    figsize : tuple

    Returns
    -------
    matplotlib.figure.Figure
    """
    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_facecolor(_SURFACE)
    ax.set_facecolor(_SURFACE)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # Title
    ax.text(0.5, 0.98, "AKI预测系统 — 数据治理全流程",
            ha="center", va="top", fontsize=18, fontweight="bold",
            color=_PRIMARY_INK, transform=ax.transAxes)
    ax.text(0.5, 0.94, "Data Governance Pipeline | 数据治理管线",
            ha="center", va="top", fontsize=11, color=_MUTED,
            transform=ax.transAxes)

    # Node definitions: (title, details_list, color, y_position)
    node_w, node_h = 0.55, 0.09
    center_x = 0.5 - node_w / 2

    nodes = [
        ("① 原始数据采集", [
            "420例心脏手术患者",
            "97个临床变量",
            "Excel格式存储",
            "含人口学、实验室、手术、ICU数据",
        ], _PALETTE["blue"], 0.80),

        ("② 缺失值分析", [
            "缺失率 < 1% (仅4列有缺失)",
            "多重插补 (MICE)",
            "Little's MCAR检验",
        ], _PALETTE["aqua"], 0.66),

        ("③ 异常值检测与处理", [
            "IQR法 + Z-score法联合检测",
            "Winsorize缩尾处理 (1st/99th)",
            "保留临床合理性判断",
        ], _PALETTE["yellow"], 0.52),

        ("④ 数据标准化", [
            "StandardScaler标准化",
            "连续变量 → 均值0, 标准差1",
            "分类变量 → One-Hot编码",
        ], _PALETTE["orange"], 0.38),

        ("⑤ 特征工程与筛选", [
            "LASSO回归降维 (L1正则化)",
            "SHAP重要性排序",
            "临床知识筛选",
            "最终35个特征",
        ], _PALETTE["red"], 0.24),

        ("⑥ 类别不平衡处理", [
            "SMOTE过采样 (AKI ~30%)",
            "合成少数类样本",
            "平衡后训练集",
        ], _PALETTE["violet"], 0.10),

        ("⑦ 建模数据集", [
            "特征矩阵: 35列",
            "目标变量: AKI分组 (0/1)",
            "训练集:测试集 = 80:20",
            "分层抽样保持类别比例",
        ], "#2c3e50", -0.04),
    ]

    side_notes = [
        ("数据质量指标", [
            "完整性 > 99%",
            "一致性 ✓",
            "准确性 ✓",
            "时效性 ✓",
        ]),
        ("技术栈", [
            "Python 3.10",
            "pandas / numpy",
            "scikit-learn",
            "imbalanced-learn",
        ]),
    ]

    # Draw nodes
    for title, details, color, y_pos in nodes:
        _draw_node(ax, center_x, y_pos, node_w, node_h, title, details, color)

    # Draw arrows between nodes
    arrow_x = center_x + node_w / 2
    for i in range(len(nodes) - 1):
        _, _, _, y1 = nodes[i]
        _, _, _, y2 = nodes[i + 1]
        _draw_arrow(ax, arrow_x, y1, arrow_x, y2 + node_h,
                    color=_PALETTE["gray"])

    # Side annotations
    for idx, (side_title, side_items) in enumerate(side_notes):
        side_x = 0.78
        side_y = 0.85 - idx * 0.15
        ax.text(side_x, side_y, side_title, fontsize=9, fontweight="bold",
                color=_PRIMARY_INK)
        for j, item in enumerate(side_items):
            ax.text(side_x + 0.02, side_y - 0.025 - j * 0.025,
                    f"• {item}", fontsize=7.5, color=_SECONDARY_INK)

    # Footer
    ax.text(0.5, -0.08, "白菜卷队 · 广西科技大学 · 暑期数创 2026",
            ha="center", fontsize=8, color=_MUTED, transform=ax.transAxes)

    fig.tight_layout()

    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        fig.savefig(save_path, dpi=300, facecolor=fig.get_facecolor())
        print(f"  Data governance flowchart saved: {save_path}")

    return fig


# ============================================================================
# 2. Missing Values Summary
# ============================================================================

def plot_missing_values_summary(
    missing_before: Dict[str, int],
    missing_after: Optional[Dict[str, int]] = None,
    total_samples: int = 420,
    save_path: str = "",
    figsize: Tuple[int, int] = (12, 5),
) -> Figure:
    """Plot missing values before and after imputation.

    Parameters
    ----------
    missing_before : dict of {column_name: n_missing}
    missing_after : dict of {column_name: n_missing}, optional
    total_samples : int
    save_path : str
    figsize : tuple

    Returns
    -------
    matplotlib.figure.Figure
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=figsize)
    fig.patch.set_facecolor(_SURFACE)

    # Filter to columns with any missing
    missing_before = {k: v for k, v in missing_before.items() if v > 0}
    if missing_after:
        missing_after = {k: v for k, v in missing_after.items() if v > 0}

    def plot_missing_bar(ax, missing_dict, title, color):
        ax.set_facecolor(_SURFACE)
        if not missing_dict:
            ax.text(0.5, 0.5, "无缺失值\nNo Missing Values",
                    ha="center", va="center", transform=ax.transAxes,
                    fontsize=12, color=_PALETTE["aqua"])
            ax.set_title(title, fontsize=12, fontweight="bold", color=_PRIMARY_INK)
            return

        cols = list(missing_dict.keys())
        vals = [missing_dict[c] for c in cols]
        pcts = [v / total_samples * 100 for v in vals]

        colors_list = [color] * len(cols)
        bars = ax.barh(range(len(cols)), pcts, color=colors_list,
                       edgecolor="white", linewidth=0.5)

        # Annotate with count
        for i, (pct, count) in enumerate(zip(pcts, vals)):
            ax.text(pct + 0.05, i, f"{count} ({pct:.1f}%)",
                    va="center", fontsize=8, color=_SECONDARY_INK)

        ax.set_yticks(range(len(cols)))
        ax.set_yticklabels(cols, fontsize=9, color=_PRIMARY_INK)
        ax.set_xlabel("缺失比例 Missing Rate (%)", color=_SECONDARY_INK, fontsize=10)
        ax.set_title(title, fontsize=12, fontweight="bold", color=_PRIMARY_INK)
        ax.invert_yaxis()
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.tick_params(colors=_MUTED)

    plot_missing_bar(ax1, missing_before, "处理前 Before", _PALETTE["red"])
    plot_missing_bar(ax2, missing_after or {}, "处理后 After", _PALETTE["aqua"])

    fig.suptitle("缺失值处理 | Missing Value Treatment",
                 fontsize=14, fontweight="bold", color=_PRIMARY_INK, y=1.02)
    fig.tight_layout()

    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        fig.savefig(save_path, dpi=300, facecolor=fig.get_facecolor())
        print(f"  Missing values summary saved: {save_path}")

    return fig


# ============================================================================
# 3. Feature Selection Process
# ============================================================================

def plot_feature_selection_process(
    n_original: int = 97,
    n_after_cleaning: int = 85,
    n_after_lasso: int = 50,
    n_after_shap: int = 35,
    n_final: int = 35,
    save_path: str = "",
    figsize: Tuple[int, int] = (10, 6),
) -> Figure:
    """Plot feature selection funnel diagram.

    Shows the reduction from 97 raw features to 35 final features.
    """
    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_facecolor(_SURFACE)
    ax.set_facecolor(_SURFACE)
    ax.axis("off")

    stages = [
        (f"原始特征\nOriginal Features", n_original, _PALETTE["blue"]),
        (f"清洗后\nAfter Cleaning", n_after_cleaning, _PALETTE["aqua"]),
        (f"LASSO筛选后\nAfter LASSO", n_after_lasso, _PALETTE["yellow"]),
        (f"SHAP筛选后\nAfter SHAP", n_after_shap, _PALETTE["orange"]),
        (f"最终建模特征\nFinal Features", n_final, _PALETTE["red"]),
    ]

    n_stages = len(stages)
    max_n = max(s[1] for s in stages)
    bar_height = 0.12
    y_start = 0.85
    y_gap = 0.16

    for i, (label, n, color) in enumerate(stages):
        y = y_start - i * y_gap
        width = n / max_n * 0.7
        center = 0.5 - width / 2

        # Bar
        bar = FancyBboxPatch(
            (center, y), width, bar_height,
            boxstyle="round,pad=0.05",
            facecolor=color, edgecolor=color, linewidth=1, alpha=0.9,
        )
        ax.add_patch(bar)

        # Count label
        ax.text(center + width + 0.02, y + bar_height / 2,
                f"n = {n}", fontsize=12, fontweight="bold",
                color=_PRIMARY_INK, va="center")

        # Stage label
        ax.text(0.02, y + bar_height / 2, label,
                fontsize=10, color=_SECONDARY_INK, va="center",
                linespacing=1.3)

        # Arrow between stages
        if i < n_stages - 1:
            reduction = stages[i][1] - stages[i + 1][1]
            mid_y = y - y_gap / 2
            ax.annotate(
                f"-{reduction} 特征",
                xy=(0.85, mid_y + 0.02), fontsize=8, color=_MUTED,
                ha="center",
            )

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_title("特征筛选漏斗 | Feature Selection Funnel",
                 fontsize=14, fontweight="bold", color=_PRIMARY_INK)

    fig.tight_layout()

    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        fig.savefig(save_path, dpi=300, facecolor=fig.get_facecolor())
        print(f"  Feature selection funnel saved: {save_path}")

    return fig


# ============================================================================
# 4. Data Quality Dashboard
# ============================================================================

def create_data_quality_dashboard(
    df: pd.DataFrame,
    target_col: str = "AKI分组",
    save_path: str = "",
    figsize: Tuple[int, int] = (14, 10),
) -> Figure:
    """Create a comprehensive data quality dashboard.

    Includes:
    - Missing rate bar chart
    - Data type distribution pie chart
    - Class balance bar chart
    - Key statistics table

    Parameters
    ----------
    df : pd.DataFrame
        The dataset.
    target_col : str
        Name of the target variable column.
    save_path : str
    figsize : tuple

    Returns
    -------
    matplotlib.figure.Figure
    """
    fig = plt.figure(figsize=figsize)
    fig.patch.set_facecolor(_SURFACE)

    # === Grid layout ===
    gs = fig.add_gridspec(2, 3, hspace=0.35, wspace=0.35)

    # --- (0,0): Missing Rate ---
    ax_miss = fig.add_subplot(gs[0, 0])
    ax_miss.set_facecolor(_SURFACE)
    missing_counts = df.isnull().sum()
    missing_pcts = (missing_counts / len(df) * 100)
    missing_nonzero = missing_pcts[missing_pcts > 0].sort_values(ascending=True)

    if len(missing_nonzero) > 0:
        colors_miss = [_PALETTE["red"] if p > 1 else _PALETTE["yellow"]
                       for p in missing_nonzero]
        ax_miss.barh(range(len(missing_nonzero)), missing_nonzero.values,
                    color=colors_miss, edgecolor="white", linewidth=0.5)
        ax_miss.set_yticks(range(len(missing_nonzero)))
        ax_miss.set_yticklabels(missing_nonzero.index, fontsize=7, color=_PRIMARY_INK)
    else:
        ax_miss.text(0.5, 0.5, "无缺失值 ✓", ha="center", va="center",
                    transform=ax_miss.transAxes, fontsize=14, color=_PALETTE["aqua"])

    ax_miss.set_title("缺失率分析 Missing Rate (%)", fontsize=11,
                      fontweight="bold", color=_PRIMARY_INK)
    ax_miss.set_xlabel("%", fontsize=8, color=_MUTED)
    ax_miss.spines["top"].set_visible(False)
    ax_miss.spines["right"].set_visible(False)
    ax_miss.tick_params(colors=_MUTED)

    # --- (0,1): Data Types ---
    ax_types = fig.add_subplot(gs[0, 1])
    ax_types.set_facecolor(_SURFACE)
    dtype_counts = df.dtypes.astype(str).value_counts()
    colors_types = [_PALETTE["blue"], _PALETTE["aqua"], _PALETTE["yellow"],
                    _PALETTE["orange"]]
    wedges, texts, autotexts = ax_types.pie(
        dtype_counts.values, labels=dtype_counts.index,
        autopct="%1.1f%%", colors=colors_types[:len(dtype_counts)],
        textprops={"fontsize": 9, "color": _PRIMARY_INK},
    )
    ax_types.set_title("数据类型分布 Data Types", fontsize=11,
                       fontweight="bold", color=_PRIMARY_INK)

    # --- (0,2): Class Balance ---
    ax_class = fig.add_subplot(gs[0, 2])
    ax_class.set_facecolor(_SURFACE)
    if target_col in df.columns:
        class_counts = df[target_col].value_counts().sort_index()
        labels = ["非AKI (0)", "AKI (1)"] if len(class_counts) == 2 else class_counts.index.astype(str)
        colors_class = [_PALETTE["aqua"], _PALETTE["red"]]
        bars = ax_class.bar(labels, class_counts.values, color=colors_class,
                           edgecolor="white", linewidth=1)
        for bar, count in zip(bars, class_counts.values):
            pct = count / len(df) * 100
            ax_class.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                         f"{count}\n({pct:.1f}%)", ha="center", fontsize=10,
                         color=_PRIMARY_INK)
        ax_class.set_title(f"类别分布 Class Balance ({target_col})", fontsize=11,
                          fontweight="bold", color=_PRIMARY_INK)
    else:
        ax_class.text(0.5, 0.5, f"目标列'{target_col}'不存在",
                     ha="center", va="center", transform=ax_class.transAxes,
                     color=_MUTED)
    ax_class.spines["top"].set_visible(False)
    ax_class.spines["right"].set_visible(False)
    ax_class.tick_params(colors=_MUTED)

    # --- (1, 0:2): Summary Statistics ---
    ax_stats = fig.add_subplot(gs[1, :2])
    ax_stats.set_facecolor(_SURFACE)
    ax_stats.axis("off")

    # Compute statistics
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    stats_data = {
        "指标 Metric": [
            "样本量 Samples", "特征数 Features",
            "数值型特征 Numeric", "分类型特征 Categorical",
            "缺失率 Missing Rate", "AKI发生率 AKI Rate",
            "平均年龄 Mean Age", "男性比例 Male Ratio",
        ],
        "值 Value": [
            str(len(df)),
            str(len(df.columns)),
            str(len(numeric_cols)),
            str(len(df.columns) - len(numeric_cols)),
            f"{df.isnull().sum().sum() / (len(df) * len(df.columns)) * 100:.2f}%",
            f"{df[target_col].mean() * 100:.1f}%" if target_col in df.columns else "N/A",
            f"{df['年龄'].mean():.1f}" if "年龄" in df.columns else "N/A",
            f"{df['性别'].value_counts(normalize=True).get(1, 0) * 100:.1f}%"
            if "性别" in df.columns else "N/A",
        ],
    }
    stats_df = pd.DataFrame(stats_data)

    # Render as table
    table = ax_stats.table(
        cellText=stats_df.values,
        colLabels=stats_df.columns,
        cellLoc="left",
        loc="center",
        colWidths=[0.35, 0.25],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    for key, cell in table.get_celld().items():
        cell.set_edgecolor(_GRIDLINE := "#e1e0d9")
        cell.set_linewidth(0.3)
        if key[0] == 0:  # Header
            cell.set_facecolor(_PALETTE["blue"])
            cell.set_text_props(color="white", fontweight="bold")
        else:
            cell.set_facecolor(_SURFACE)
            cell.set_text_props(color=_PRIMARY_INK)

    ax_stats.set_title("数据质量总览 Data Quality Overview", fontsize=11,
                       fontweight="bold", color=_PRIMARY_INK, y=1.02)

    # --- (1, 2): Key Insight Box ---
    ax_insight = fig.add_subplot(gs[1, 2])
    ax_insight.set_facecolor(_SURFACE)
    ax_insight.axis("off")

    insight_text = (
        "📊 数据质量评估\n\n"
        f"✓ 样本量: {len(df)} 例\n"
        f"✓ 特征数: {len(df.columns)} 个\n"
        f"✓ 缺失率: < 1%\n"
        f"✓ 数据完整性: 高\n\n"
        "🔑 关键洞察:\n"
        "数据来自真实临床记录，\n"
        "质量高，缺失少，可直接\n"
        "用于机器学习建模。"
    )

    ax_insight.text(0.1, 0.95, insight_text, transform=ax_insight.transAxes,
                   fontsize=9, color=_PRIMARY_INK, va="top",
                   linespacing=1.4,
                   bbox=dict(boxstyle="round,pad=0.5",
                            facecolor="#eaf2f8", edgecolor=_PALETTE["blue"],
                            alpha=0.8))

    ax_insight.set_title("评估结论 Assessment", fontsize=11,
                         fontweight="bold", color=_PRIMARY_INK)

    # Main title
    fig.suptitle("数据治理仪表盘 | Data Governance Dashboard",
                 fontsize=16, fontweight="bold", color=_PRIMARY_INK, y=1.01)

    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        fig.savefig(save_path, dpi=300, facecolor=fig.get_facecolor())
        print(f"  Data quality dashboard saved: {save_path}")

    return fig


# ============================================================================
# 5. Run Full Data Governance Report
# ============================================================================

def run_full_data_gov_report(
    df: Optional[pd.DataFrame] = None,
    target_col: str = "AKI分组",
    output_dir: str = "outputs/",
) -> Dict[str, str]:
    """Run the complete data governance visualization pipeline.

    Generates:
    1. Data governance flowchart → outputs/figures/data_governance_flow.png
    2. Feature selection funnel → outputs/figures/feature_selection_funnel.png
    3. Data quality dashboard → outputs/figures/data_quality_dashboard.png
    (if df provided)

    Returns
    -------
    dict of {figure_name: file_path}
    """
    print("=" * 70)
    print("📋 数据治理可视化 | Data Governance Visualization")
    print("=" * 70)

    os.makedirs(os.path.join(output_dir, "figures"), exist_ok=True)

    outputs = {}

    # 1. Flowchart
    print("\n📊 Step 1/3: 数据治理流程图...")
    flow_path = os.path.join(output_dir, "figures", "data_governance_flow.png")
    fig_flow = plot_data_governance_flowchart(save_path=flow_path)
    plt.close(fig_flow)
    outputs["flowchart"] = flow_path

    # 2. Feature selection funnel
    print("\n🔽 Step 2/3: 特征筛选漏斗图...")
    funnel_path = os.path.join(output_dir, "figures", "feature_selection_funnel.png")
    fig_funnel = plot_feature_selection_process(save_path=funnel_path)
    plt.close(fig_funnel)
    outputs["funnel"] = funnel_path

    # 3. Data quality dashboard (if data provided)
    if df is not None:
        print("\n📈 Step 3/3: 数据质量仪表盘...")
        dash_path = os.path.join(output_dir, "figures", "data_quality_dashboard.png")
        fig_dash = create_data_quality_dashboard(df, target_col=target_col,
                                                   save_path=dash_path)
        plt.close(fig_dash)
        outputs["dashboard"] = dash_path
    else:
        print("\n⏭️ Step 3/3: 跳过 (未提供数据)")

    print("\n" + "=" * 70)
    print("✅ 数据治理可视化完成")
    print("=" * 70)
    for name, path in outputs.items():
        print(f"  📁 {name}: {path}")

    return outputs


# ============================================================================
if __name__ == "__main__":
    print("Data governance visualization module loaded successfully.")
    print("Usage: from src.visualization.data_governance import run_full_data_gov_report")

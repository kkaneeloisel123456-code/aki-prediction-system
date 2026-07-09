"""
Model Evaluation Module

Provides comprehensive evaluation metrics, visualization, and statistical comparison
functions for binary classification models.

All plots use Chinese-friendly fonts, professional styling, and 300dpi output.
"""

import os
import warnings
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
from matplotlib import font_manager
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from scipy.stats import norm
from sklearn.calibration import calibration_curve
from sklearn.metrics import (
    accuracy_score,
    auc,
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.preprocessing import label_binarize

warnings.filterwarnings("ignore", category=UserWarning)

# ---------------------------------------------------------------------------
# Font & style setup — Chinese-friendly
# ---------------------------------------------------------------------------

# Attempt to register common Chinese fonts; fall back to sans-serif if unavailable.
_CHINESE_FONTS = [
    "Microsoft YaHei",        # Windows
    "SimHei",                 # Windows
    "WenQuanYi Micro Hei",    # Linux
    "Noto Sans CJK SC",       # cross-platform
    "Source Han Sans SC",     # cross-platform
    "PingFang SC",            # macOS
]

_FONT_CANDIDATES: List[str] = []
for fname in _CHINESE_FONTS:
    try:
        font_manager.findfont(fname, fallback_to_default=False)
        _FONT_CANDIDATES.append(fname)
    except Exception:
        pass

# Always keep a usable fallback
_FONT_CANDIDATES.extend(["sans-serif", "DejaVu Sans"])

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": _FONT_CANDIDATES,
        "axes.unicode_minus": False,
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.15,
    }
)

# Palette (light mode) from dataviz skill reference
_PALETTE = [
    "#2a78d6",  # blue
    "#1baf7a",  # aqua
    "#eda100",  # yellow
    "#008300",  # green
    "#4a3aa7",  # violet
    "#e34948",  # red
    "#e87ba4",  # magenta
    "#eb6834",  # orange
]

_SURFACE = "#fcfcfb"
_PRIMARY_INK = "#0b0b0b"
_SECONDARY_INK = "#52514e"
_MUTED = "#898781"
_GRIDLINE = "#e1e0d9"
_BASELINE = "#c3c2b7"

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

_AVAILABLE_METRICS = {
    "accuracy": accuracy_score,
    "precision": precision_score,
    "recall": recall_score,
    "f1": f1_score,
    "specificity": None,  # handled inline
    "npv": None,  # handled inline
    "ppv": precision_score,  # same as precision
}


def _format_metrics(metrics_dict: Dict[str, float]) -> Dict[str, float]:
    """Round all values in a metrics dict to 4 decimal places."""
    return {k: round(float(v), 4) for k, v in metrics_dict.items()}


def _get_optimal_threshold_metric(y_true: np.ndarray, y_prob: np.ndarray, metric: str) -> Tuple[float, float]:
    """Return (best_threshold, best_value) for a given threshold-optimised metric."""
    thresholds = np.linspace(0.01, 0.99, 199)
    best_val, best_th = 0.0, 0.5
    for th in thresholds:
        y_pred = (y_prob >= th).astype(int)
        if metric == "f1":
            val = f1_score(y_true, y_pred)
        elif metric == "accuracy":
            val = accuracy_score(y_true, y_pred)
        elif metric == "precision":
            val = precision_score(y_true, y_pred, zero_division=0)
        elif metric == "recall":
            val = recall_score(y_true, y_pred)
        elif metric == "youden":
            tnr = np.sum((y_true == 0) & (y_pred == 0)) / max(np.sum(y_true == 0), 1)
            tpr = np.sum((y_true == 1) & (y_pred == 1)) / max(np.sum(y_true == 1), 1)
            val = tpr + tnr - 1
        else:
            raise ValueError(f"Unsupported metric: {metric}")
        if val > best_val:
            best_val = val
            best_th = th
    return best_th, best_val


# ---------------------------------------------------------------------------
# 1. compute_all_metrics
# ---------------------------------------------------------------------------


def compute_all_metrics(
    y_true: np.ndarray, y_pred: np.ndarray, y_prob: np.ndarray
) -> Dict[str, float]:
    """Compute a comprehensive set of binary classification metrics.

    Parameters
    ----------
    y_true : numpy.ndarray
        Ground-truth binary labels (0/1).
    y_pred : numpy.ndarray
        Predicted binary labels (0/1).
    y_prob : numpy.ndarray
        Predicted probabilities for the positive class.

    Returns
    -------
    dict
        Dictionary with keys: accuracy, precision, recall, f1, auc_roc,
        specificity, npv, ppv, brier_score. All values rounded to 4 decimals.
    """
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    y_prob = np.asarray(y_prob)

    cm = confusion_matrix(y_true, y_pred)
    tn, fp, fn, tp = cm.ravel()

    metrics = {
        "accuracy": accuracy_score(y_true, y_pred),
        "precision": precision_score(y_true, y_pred, zero_division=0),
        "recall": recall_score(y_true, y_pred, zero_division=0),
        "f1": f1_score(y_true, y_pred, zero_division=0),
        "auc_roc": roc_auc_score(y_true, y_prob),
        "specificity": tn / max((tn + fp), 1),
        "npv": tn / max((tn + fn), 1),
        "ppv": tp / max((tp + fp), 1),
        "brier_score": brier_score_loss(y_true, y_prob),
    }
    return _format_metrics(metrics)


# ---------------------------------------------------------------------------
# 2. compute_confidence_intervals
# ---------------------------------------------------------------------------


def compute_confidence_intervals(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_prob: np.ndarray,
    metrics: Optional[List[str]] = None,
    n_bootstrap: int = 1000,
    ci: float = 0.95,
    random_state: int = 42,
) -> Dict[str, Tuple[float, float, float]]:
    """Bootstrap confidence intervals for specified metrics.

    Parameters
    ----------
    y_true : numpy.ndarray
        Ground-truth labels.
    y_pred : numpy.ndarray
        Predicted labels.
    y_prob : numpy.ndarray
        Predicted probabilities.
    metrics : list of str, optional
        Metrics to bootstrap. Defaults to ['auc_roc', 'accuracy', 'f1', 'precision', 'recall'].
    n_bootstrap : int
        Number of bootstrap resamples (default 1000).
    ci : float
        Confidence level (default 0.95).
    random_state : int
        Random seed for reproducibility.

    Returns
    -------
    dict
        Mapping {metric: (mean, ci_lower, ci_upper)}.
    """
    if metrics is None:
        metrics = ["auc_roc", "accuracy", "f1", "precision", "recall"]

    rng = np.random.default_rng(random_state)
    n = len(y_true)
    results: Dict[str, List[float]] = {m: [] for m in metrics}

    for _ in range(n_bootstrap):
        idx = rng.integers(0, n, size=n)
        y_true_b = y_true[idx]
        y_pred_b = y_pred[idx]
        y_prob_b = y_prob[idx]

        # Skip if only one class present
        if len(np.unique(y_true_b)) < 2:
            continue

        for m in metrics:
            if m == "auc_roc":
                val = roc_auc_score(y_true_b, y_prob_b)
            elif m == "accuracy":
                val = accuracy_score(y_true_b, y_pred_b)
            elif m == "f1":
                val = f1_score(y_true_b, y_pred_b, zero_division=0)
            elif m == "precision":
                val = precision_score(y_true_b, y_pred_b, zero_division=0)
            elif m == "recall":
                val = recall_score(y_true_b, y_pred_b, zero_division=0)
            elif m == "specificity":
                tn, fp, fn, tp = confusion_matrix(y_true_b, y_pred_b).ravel()
                val = tn / max((tn + fp), 1)
            elif m == "npv":
                tn, fp, fn, tp = confusion_matrix(y_true_b, y_pred_b).ravel()
                val = tn / max((tn + fn), 1)
            elif m == "brier_score":
                val = brier_score_loss(y_true_b, y_prob_b)
            else:
                continue
            results[m].append(val)

    alpha = 1.0 - ci
    ci_dict: Dict[str, Tuple[float, float, float]] = {}
    for m in metrics:
        arr = np.array(results[m])
        if len(arr) < 2:
            ci_dict[m] = (0.0, 0.0, 0.0)
            continue
        mean = float(np.mean(arr))
        lower = float(np.percentile(arr, 100 * alpha / 2))
        upper = float(np.percentile(arr, 100 * (1 - alpha / 2)))
        ci_dict[m] = (round(mean, 4), round(lower, 4), round(upper, 4))

    return ci_dict


# ---------------------------------------------------------------------------
# 3. plot_roc_curves
# ---------------------------------------------------------------------------


def plot_roc_curves(
    model_results_dict: Dict[str, Dict[str, np.ndarray]],
    save_path: str,
) -> Figure:
    """Plot ROC curves for multiple models on a single figure.

    Parameters
    ----------
    model_results_dict : dict
        Mapping {model_name: {'y_true': ..., 'y_prob': ...}}.
    save_path : str
        Path to save the figure (e.g. 'outputs/roc_curves.png').

    Returns
    -------
    matplotlib.figure.Figure
    """
    fig, ax = plt.subplots(figsize=(8, 7))
    fig.patch.set_facecolor(_SURFACE)
    ax.set_facecolor(_SURFACE)

    # Random-guess diagonal
    ax.plot([0, 1], [0, 1], "k--", lw=1.5, alpha=0.5, label="Random (AUC = 0.5)")

    for i, (model_name, res) in enumerate(model_results_dict.items()):
        y_true = np.asarray(res["y_true"])
        y_prob = np.asarray(res["y_prob"])
        color = _PALETTE[i % len(_PALETTE)]

        fpr, tpr, _ = roc_curve(y_true, y_prob)
        roc_auc = roc_auc_score(y_true, y_prob)

        ax.plot(
            fpr, tpr, color=color, lw=2, label=f"{model_name} (AUC = {roc_auc:.4f})"
        )

    ax.set_xlabel("False Positive Rate (1 - Specificity)", color=_PRIMARY_INK, fontsize=11)
    ax.set_ylabel("True Positive Rate (Sensitivity)", color=_PRIMARY_INK, fontsize=11)
    ax.set_title("ROC Curves", color=_PRIMARY_INK, fontsize=13, fontweight="bold")
    ax.legend(loc="lower right", framealpha=0.85, edgecolor=_GRIDLINE)
    ax.set_xlim([-0.02, 1.02])
    ax.set_ylim([-0.02, 1.02])
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(_BASELINE)
    ax.spines["bottom"].set_color(_BASELINE)
    ax.tick_params(colors=_MUTED)
    ax.grid(True, alpha=0.35, color=_GRIDLINE, linewidth=0.5)

    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    fig.savefig(save_path, dpi=300, facecolor=fig.get_facecolor())
    plt.close(fig)
    return fig


# ---------------------------------------------------------------------------
# 4. plot_pr_curves
# ---------------------------------------------------------------------------


def plot_pr_curves(
    model_results_dict: Dict[str, Dict[str, np.ndarray]],
    save_path: str,
) -> Figure:
    """Plot Precision-Recall curves for multiple models on a single figure.

    Parameters
    ----------
    model_results_dict : dict
        Mapping {model_name: {'y_true': ..., 'y_prob': ...}}.
    save_path : str
        Path to save the figure.

    Returns
    -------
    matplotlib.figure.Figure
    """
    fig, ax = plt.subplots(figsize=(8, 7))
    fig.patch.set_facecolor(_SURFACE)
    ax.set_facecolor(_SURFACE)

    for i, (model_name, res) in enumerate(model_results_dict.items()):
        y_true = np.asarray(res["y_true"])
        y_prob = np.asarray(res["y_prob"])
        color = _PALETTE[i % len(_PALETTE)]

        precision, recall, _ = precision_recall_curve(y_true, y_prob)
        ap = average_precision_score(y_true, y_prob)

        ax.plot(
            recall,
            precision,
            color=color,
            lw=2,
            label=f"{model_name} (AP = {ap:.4f})",
        )

    # Baseline
    pos_ratio = np.mean(list(res["y_true"] for res in model_results_dict.values()))
    if isinstance(pos_ratio, list):
        pos_ratio = pos_ratio[0] if len(pos_ratio) > 0 else 0.5
    ax.axhline(y=pos_ratio, color=_MUTED, linestyle="--", lw=1.5, alpha=0.6, label=f"Baseline ({pos_ratio:.3f})")

    ax.set_xlabel("Recall (Sensitivity)", color=_PRIMARY_INK, fontsize=11)
    ax.set_ylabel("Precision (PPV)", color=_PRIMARY_INK, fontsize=11)
    ax.set_title("Precision-Recall Curves", color=_PRIMARY_INK, fontsize=13, fontweight="bold")
    ax.legend(loc="lower left", framealpha=0.85, edgecolor=_GRIDLINE)
    ax.set_xlim([-0.02, 1.02])
    ax.set_ylim([-0.02, 1.02])
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(_BASELINE)
    ax.spines["bottom"].set_color(_BASELINE)
    ax.tick_params(colors=_MUTED)
    ax.grid(True, alpha=0.35, color=_GRIDLINE, linewidth=0.5)

    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    fig.savefig(save_path, dpi=300, facecolor=fig.get_facecolor())
    plt.close(fig)
    return fig


# ---------------------------------------------------------------------------
# 5. plot_confusion_matrices
# ---------------------------------------------------------------------------


def plot_confusion_matrices(
    model_results_dict: Dict[str, Dict[str, np.ndarray]],
    save_path: str,
) -> Figure:
    """Plot confusion matrices for all models in a grid layout.

    Each subplot shows raw counts and normalised (percentage) values.

    Parameters
    ----------
    model_results_dict : dict
        Mapping {model_name: {'y_true': ..., 'y_pred': ...}}.
    save_path : str
        Path to save the figure.

    Returns
    -------
    matplotlib.figure.Figure
    """
    n_models = len(model_results_dict)
    if n_models == 0:
        raise ValueError("model_results_dict is empty")

    # Determine grid layout
    if n_models <= 4:
        n_cols = min(n_models, 2)
        n_rows = int(np.ceil(n_models / n_cols))
    else:
        n_cols = 3
        n_rows = int(np.ceil(n_models / n_cols))

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(5 * n_cols, 4.5 * n_rows))
    fig.patch.set_facecolor(_SURFACE)

    axes_flat = np.atleast_1d(axes).ravel()

    for idx, (model_name, res) in enumerate(model_results_dict.items()):
        ax = axes_flat[idx]
        ax.set_facecolor(_SURFACE)

        y_true = np.asarray(res["y_true"])
        y_pred = np.asarray(res["y_pred"])
        cm = confusion_matrix(y_true, y_pred)
        cm_norm = cm.astype("float") / cm.sum(axis=1, keepdims=True).clip(min=1)

        # Annotate with both raw and normalised
        labels = np.empty_like(cm, dtype=object)
        for i in range(cm.shape[0]):
            for j in range(cm.shape[1]):
                labels[i, j] = f"{cm[i, j]}\n({cm_norm[i, j]:.1%})"

        im = ax.imshow(cm, interpolation="nearest", cmap="Blues", vmin=0, vmax=cm.max() * 1.1)
        ax.set_title(model_name, color=_PRIMARY_INK, fontsize=11, fontweight="bold")

        tick_labels = ["Negative (0)", "Positive (1)"]
        ax.set_xticks([0, 1])
        ax.set_yticks([0, 1])
        ax.set_xticklabels(tick_labels, color=_SECONDARY_INK, fontsize=9)
        ax.set_yticklabels(tick_labels, color=_SECONDARY_INK, fontsize=9)
        ax.set_xlabel("Predicted", color=_PRIMARY_INK, fontsize=10)
        ax.set_ylabel("Actual", color=_PRIMARY_INK, fontsize=10)

        for i in range(cm.shape[0]):
            for j in range(cm.shape[1]):
                color = "white" if cm[i, j] > cm.max() * 0.5 else _PRIMARY_INK
                ax.text(j, i, labels[i, j], ha="center", va="center", fontsize=9, color=color)

        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color(_BASELINE)
        ax.spines["bottom"].set_color(_BASELINE)

    # Hide unused subplots
    for idx in range(n_models, len(axes_flat)):
        axes_flat[idx].set_visible(False)

    fig.suptitle(
        "Confusion Matrices",
        color=_PRIMARY_INK,
        fontsize=14,
        fontweight="bold",
        y=1.01,
    )
    fig.tight_layout()

    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    fig.savefig(save_path, dpi=300, facecolor=fig.get_facecolor())
    plt.close(fig)
    return fig


# ---------------------------------------------------------------------------
# 6. plot_calibration_curves
# ---------------------------------------------------------------------------


def plot_calibration_curves(
    model_results_dict: Dict[str, Dict[str, np.ndarray]],
    n_bins: int = 10,
    save_path: str = "",
) -> Figure:
    """Plot calibration curves with a predicted-probability histogram.

    Parameters
    ----------
    model_results_dict : dict
        Mapping {model_name: {'y_true': ..., 'y_prob': ...}}.
    n_bins : int
        Number of bins for calibration curve (default 10).
    save_path : str
        Path to save the figure.

    Returns
    -------
    matplotlib.figure.Figure
    """
    fig = plt.figure(figsize=(10, 7))
    fig.patch.set_facecolor(_SURFACE)

    # Upper: calibration curves
    ax_calib = fig.add_subplot(2, 1, 1)
    ax_calib.set_facecolor(_SURFACE)

    # Perfect calibration diagonal
    ax_calib.plot([0, 1], [0, 1], "k--", lw=1.5, alpha=0.5, label="Perfectly calibrated")

    for i, (model_name, res) in enumerate(model_results_dict.items()):
        y_true = np.asarray(res["y_true"])
        y_prob = np.asarray(res["y_prob"])
        color = _PALETTE[i % len(_PALETTE)]
        brier = brier_score_loss(y_true, y_prob)

        prob_true, prob_pred = calibration_curve(y_true, y_prob, n_bins=n_bins, strategy="uniform")
        ax_calib.plot(
            prob_pred,
            prob_true,
            marker="o",
            color=color,
            lw=2,
            markersize=6,
            label=f"{model_name} (Brier = {brier:.4f})",
        )

    ax_calib.set_xlabel("Mean Predicted Probability", color=_PRIMARY_INK, fontsize=11)
    ax_calib.set_ylabel("Fraction of Positives", color=_PRIMARY_INK, fontsize=11)
    ax_calib.set_title("Calibration Curves", color=_PRIMARY_INK, fontsize=13, fontweight="bold")
    ax_calib.legend(loc="lower right", framealpha=0.85, edgecolor=_GRIDLINE, fontsize=8)
    ax_calib.set_xlim([-0.02, 1.02])
    ax_calib.set_ylim([-0.02, 1.02])
    ax_calib.spines["top"].set_visible(False)
    ax_calib.spines["right"].set_visible(False)
    ax_calib.spines["left"].set_color(_BASELINE)
    ax_calib.spines["bottom"].set_color(_BASELINE)
    ax_calib.tick_params(colors=_MUTED)
    ax_calib.grid(True, alpha=0.35, color=_GRIDLINE, linewidth=0.5)

    # Lower: histogram of predicted probabilities
    ax_hist = fig.add_subplot(2, 1, 2)
    ax_hist.set_facecolor(_SURFACE)

    for i, (model_name, res) in enumerate(model_results_dict.items()):
        y_prob = np.asarray(res["y_prob"])
        color = _PALETTE[i % len(_PALETTE)]
        ax_hist.hist(
            y_prob,
            bins=n_bins,
            alpha=0.35,
            color=color,
            label=model_name,
            edgecolor=color,
            linewidth=0.8,
        )

    ax_hist.set_xlabel("Predicted Probability", color=_PRIMARY_INK, fontsize=11)
    ax_hist.set_ylabel("Count", color=_PRIMARY_INK, fontsize=11)
    ax_hist.set_title("Predicted Probability Distribution", color=_PRIMARY_INK, fontsize=11, fontweight="bold")
    ax_hist.legend(loc="upper center", framealpha=0.85, edgecolor=_GRIDLINE, fontsize=8)
    ax_hist.spines["top"].set_visible(False)
    ax_hist.spines["right"].set_visible(False)
    ax_hist.spines["left"].set_color(_BASELINE)
    ax_hist.spines["bottom"].set_color(_BASELINE)
    ax_hist.tick_params(colors=_MUTED)
    ax_hist.grid(True, alpha=0.35, color=_GRIDLINE, linewidth=0.5, axis="y")

    fig.tight_layout()

    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        fig.savefig(save_path, dpi=300, facecolor=fig.get_facecolor())
        plt.close(fig)
    return fig


# ---------------------------------------------------------------------------
# 7. create_model_comparison_table
# ---------------------------------------------------------------------------


def create_model_comparison_table(
    model_results_dict: Dict[str, Dict[str, np.ndarray]],
    save_path: str = "outputs/tables/",
) -> pd.DataFrame:
    """Create and save a master model comparison table.

    Computes all metrics for every model, sorts by AUC descending, highlights
    the best value per metric, and saves as CSV.

    Parameters
    ----------
    model_results_dict : dict
        Mapping {model_name: {'y_true': ..., 'y_pred': ..., 'y_prob': ...}}.
    save_path : str
        Directory path to save the table CSV.

    Returns
    -------
    pd.DataFrame
        Comparison table sorted by AUC descending.
    """
    rows = []
    for model_name, res in model_results_dict.items():
        y_true = np.asarray(res["y_true"])
        y_pred = np.asarray(res["y_pred"])
        y_prob = np.asarray(res.get("y_prob", y_pred))

        metrics = compute_all_metrics(y_true, y_pred, y_prob)
        metrics["model"] = model_name
        rows.append(metrics)

    df = pd.DataFrame(rows)
    # Reorder columns so model is first
    cols = ["model"] + [c for c in df.columns if c != "model"]
    df = df[cols]

    # Sort by AUC descending
    if "auc_roc" in df.columns:
        df = df.sort_values("auc_roc", ascending=False).reset_index(drop=True)

    csv_path = ""
    if save_path is not None:
        os.makedirs(save_path, exist_ok=True)
        csv_path = os.path.join(save_path, "model_comparison.csv")
        df.to_csv(csv_path, index=False)

    # Print a text summary with highlighting indicators
    print("=" * 100)
    print("MODEL COMPARISON TABLE (sorted by AUC-ROC descending)")
    print("=" * 100)

    # Identify best values per numeric metric
    numeric_cols = [c for c in df.columns if c != "model"]
    best_rows: Dict[str, int] = {}
    for col in numeric_cols:
        if col in ("brier_score",):
            # Lower is better
            best_rows[col] = df[col].idxmin()
        else:
            best_rows[col] = df[col].idxmax()

    # Build formatted print output
    col_widths = {c: max(len(c), df[c].astype(str).str.len().max()) for c in df.columns}
    col_widths["model"] = max(col_widths["model"], len("model"))

    header = " | ".join(c.ljust(col_widths[c]) for c in df.columns)
    print(header)
    print("-" * len(header))

    for idx, row in df.iterrows():
        parts = []
        for c in df.columns:
            val_str = f"{row[c]:.4f}" if c != "model" else str(row[c])
            if c != "model" and idx == best_rows.get(c, -1):
                val_str = f"*{val_str}*"  # mark best
            parts.append(val_str.ljust(col_widths[c]))
        print(" | ".join(parts))

    print("=" * 100)
    if save_path:
        print(f"\nTable saved to: {csv_path}")
    print("* marks the best value per metric (Brier lower is better; others higher is better)")

    return df


# ---------------------------------------------------------------------------
# 8. plot_model_comparison_heatmap
# ---------------------------------------------------------------------------


def plot_model_comparison_heatmap(
    model_results_dict: Dict[str, Dict[str, np.ndarray]],
    metrics: Optional[List[str]] = None,
    save_path: str = "",
) -> Figure:
    """Plot a heatmap of models x metrics, colour-coded and sorted by AUC.

    Parameters
    ----------
    model_results_dict : dict
        Mapping {model_name: {'y_true': ..., 'y_pred': ..., 'y_prob': ...}}.
    metrics : list of str, optional
        Metrics to include. Defaults to all non-model columns.
    save_path : str
        Path to save the figure.

    Returns
    -------
    matplotlib.figure.Figure
    """
    df = create_model_comparison_table(model_results_dict, save_path=None)  # type: ignore[arg-type]

    if metrics is None:
        metrics = [
            "accuracy",
            "precision",
            "recall",
            "f1",
            "auc_roc",
            "specificity",
            "npv",
            "ppv",
            "brier_score",
        ]

    # Filter to metrics that actually exist
    metrics = [m for m in metrics if m in df.columns]

    plot_df = df.set_index("model")[metrics]

    # For heatmap we want the raw numeric values
    fig, ax = plt.subplots(figsize=(max(8, len(metrics) * 1.5), max(5, len(plot_df) * 0.8)))
    fig.patch.set_facecolor(_SURFACE)
    ax.set_facecolor(_SURFACE)

    # Use a blue sequential colormap
    im = ax.imshow(plot_df.values, aspect="auto", cmap="YlOrRd", interpolation="nearest")

    # Annotate cells
    for i in range(plot_df.shape[0]):
        for j in range(plot_df.shape[1]):
            val = plot_df.values[i, j]
            text_color = "white" if plot_df.values[i, j] > plot_df.values.max() * 0.7 else _PRIMARY_INK
            ax.text(j, i, f"{val:.4f}", ha="center", va="center", fontsize=9, color=text_color)

    ax.set_xticks(range(len(metrics)))
    ax.set_xticklabels(metrics, rotation=45, ha="right", fontsize=10, color=_PRIMARY_INK)
    ax.set_yticks(range(len(plot_df.index)))
    ax.set_yticklabels(plot_df.index, fontsize=10, color=_PRIMARY_INK)
    ax.set_title("Model Comparison Heatmap", color=_PRIMARY_INK, fontsize=13, fontweight="bold")

    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.ax.tick_params(colors=_MUTED)
    cbar.outline.set_visible(False)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(_BASELINE)
    ax.spines["bottom"].set_color(_BASELINE)

    fig.tight_layout()

    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        fig.savefig(save_path, dpi=300, facecolor=fig.get_facecolor())
        plt.close(fig)
    return fig


# ---------------------------------------------------------------------------
# 9. plot_radar_chart
# ---------------------------------------------------------------------------


def plot_radar_chart(
    model_results_dict: Dict[str, Dict[str, np.ndarray]],
    metrics: Optional[List[str]] = None,
    save_path: str = "",
) -> Figure:
    """Plot a radar (spider) chart comparing models across multiple metrics.

    Parameters
    ----------
    model_results_dict : dict
        Mapping {model_name: {'y_true': ..., 'y_pred': ..., 'y_prob': ...}}.
    metrics : list of str, optional
        Metrics to include. At least 3 recommended.
    save_path : str
        Path to save the figure.

    Returns
    -------
    matplotlib.figure.Figure
    """
    df = create_model_comparison_table(model_results_dict, save_path=None)  # type: ignore[arg-type]

    if metrics is None:
        metrics = ["accuracy", "precision", "recall", "f1", "auc_roc", "specificity", "npv"]
    metrics = [m for m in metrics if m in df.columns]

    n_metrics = len(metrics)
    if n_metrics < 3:
        raise ValueError("At least 3 metrics are required for a radar chart.")

    # Normalise each metric to [0, 1] for fair comparison
    plot_df = df.set_index("model")[metrics].copy()
    for col in plot_df.columns:
        col_min, col_max = plot_df[col].min(), plot_df[col].max()
        if col_max > col_min:
            plot_df[col] = (plot_df[col] - col_min) / (col_max - col_min)
        else:
            plot_df[col] = 0.5

    angles = np.linspace(0, 2 * np.pi, n_metrics, endpoint=False).tolist()
    angles += angles[:1]  # close the polygon

    fig, ax = plt.subplots(figsize=(9, 9), subplot_kw={"projection": "polar"})
    fig.patch.set_facecolor(_SURFACE)

    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(metrics, fontsize=10, color=_PRIMARY_INK)

    # Draw y-labels
    ax.set_rlabel_position(30)
    ax.tick_params(colors=_MUTED, labelsize=8)
    ax.set_ylim(0, 1)
    ax.set_yticks([0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_yticklabels(["0.2", "0.4", "0.6", "0.8", "1.0"], color=_MUTED, fontsize=8)
    ax.set_title("Model Comparison Radar Chart", color=_PRIMARY_INK, fontsize=13, fontweight="bold", pad=20)

    # Grid styling
    ax.grid(True, color=_GRIDLINE, linewidth=0.5, alpha=0.6)
    ax.spines["polar"].set_color(_BASELINE)

    for i, (model_name, row) in enumerate(plot_df.iterrows()):
        values = row.values.tolist()
        values += values[:1]
        color = _PALETTE[i % len(_PALETTE)]
        ax.plot(angles, values, color=color, lw=2, label=model_name)
        ax.fill(angles, values, color=color, alpha=0.08)

    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), framealpha=0.85, edgecolor=_GRIDLINE, fontsize=9)

    fig.tight_layout()

    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        fig.savefig(save_path, dpi=300, facecolor=fig.get_facecolor())
        plt.close(fig)
    return fig


# ---------------------------------------------------------------------------
# 10. compare_models_statistical — DeLong test
# ---------------------------------------------------------------------------


def _delong_roc_variance(y_true: np.ndarray, y_prob: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Compute the covariance matrix for AUC using DeLong's method.

    Parameters
    ----------
    y_true : numpy.ndarray
        Binary ground-truth labels.
    y_prob : numpy.ndarray
        Predicted probabilities.

    Returns
    -------
    auc : float
        AUC value.
    var : float
        Variance of AUC.
    """
    # Adapted from the Sun & Xu (2014) DeLong implementation
    y_true = y_true.ravel()
    y_prob = y_prob.ravel()
    n1 = int(np.sum(y_true))
    n2 = int(len(y_true) - n1)

    if n1 == 0 or n2 == 0:
        return 0.5, 0.0

    # Rank the data
    order = np.argsort(y_prob)
    y_true_sorted = y_true[order]
    y_prob_sorted = y_prob[order]

    # Compute the AUC
    auc_val = roc_auc_score(y_true, y_prob)

    # DeLong components
    # Compute the placement values
    pos_idx = np.where(y_true_sorted == 1)[0]
    neg_idx = np.where(y_true_sorted == 0)[0]

    # Theta10: for each positive, fraction of negatives with lower score
    theta10 = np.zeros(n1)
    for i, p_idx in enumerate(pos_idx):
        theta10[i] = np.sum(y_prob_sorted[neg_idx] < y_prob_sorted[p_idx]) / n2
        theta10[i] += 0.5 * np.sum(y_prob_sorted[neg_idx] == y_prob_sorted[p_idx]) / n2

    # Theta01: for each negative, fraction of positives with higher score
    theta01 = np.zeros(n2)
    for i, n_idx in enumerate(neg_idx):
        theta01[i] = np.sum(y_prob_sorted[pos_idx] > y_prob_sorted[n_idx]) / n1
        theta01[i] += 0.5 * np.sum(y_prob_sorted[pos_idx] == y_prob_sorted[n_idx]) / n1

    # Variance components
    var10 = np.var(theta10, ddof=1)
    var01 = np.var(theta01, ddof=1)

    variance = var10 / n1 + var01 / n2
    return auc_val, variance


def _delong_roc_test(
    y_true: np.ndarray, y_prob1: np.ndarray, y_prob2: np.ndarray
) -> float:
    """Perform DeLong's test for comparing two ROC curves.

    Parameters
    ----------
    y_true : numpy.ndarray
        Binary ground-truth labels.
    y_prob1 : numpy.ndarray
        Predicted probabilities from model 1.
    y_prob2 : numpy.ndarray
        Predicted probabilities from model 2.

    Returns
    -------
    float
        Two-sided p-value.
    """
    auc1, var1 = _delong_roc_variance(y_true, y_prob1)
    auc2, var2 = _delong_roc_variance(y_true, y_prob2)

    # Covariance between the two AUCs
    y_true = y_true.ravel()
    y_prob1 = y_prob1.ravel()
    y_prob2 = y_prob2.ravel()

    n1 = int(np.sum(y_true))
    n2 = int(len(y_true) - n1)

    order1 = np.argsort(y_prob1)
    order2 = np.argsort(y_prob2)

    y_true_sorted1 = y_true[order1]
    y_prob_sorted1 = y_prob1[order1]
    y_true_sorted2 = y_true[order2]
    y_prob_sorted2 = y_prob2[order2]

    pos_idx1 = np.where(y_true_sorted1 == 1)[0]
    neg_idx1 = np.where(y_true_sorted1 == 0)[0]
    pos_idx2 = np.where(y_true_sorted2 == 1)[0]
    neg_idx2 = np.where(y_true_sorted2 == 0)[0]

    # Theta10 for both
    theta10_1 = np.zeros(n1)
    for i, p_idx in enumerate(pos_idx1):
        theta10_1[i] = np.sum(y_prob_sorted1[neg_idx1] < y_prob_sorted1[p_idx]) / n2
        theta10_1[i] += 0.5 * np.sum(y_prob_sorted1[neg_idx1] == y_prob_sorted1[p_idx]) / n2

    theta10_2 = np.zeros(n1)
    for i, p_idx in enumerate(pos_idx2):
        theta10_2[i] = np.sum(y_prob_sorted2[neg_idx2] < y_prob_sorted2[p_idx]) / n2
        theta10_2[i] += 0.5 * np.sum(y_prob_sorted2[neg_idx2] == y_prob_sorted2[p_idx]) / n2

    # Theta01 for both
    theta01_1 = np.zeros(n2)
    for i, n_idx in enumerate(neg_idx1):
        theta01_1[i] = np.sum(y_prob_sorted1[pos_idx1] > y_prob_sorted1[n_idx]) / n1
        theta01_1[i] += 0.5 * np.sum(y_prob_sorted1[pos_idx1] == y_prob_sorted1[n_idx]) / n1

    theta01_2 = np.zeros(n2)
    for i, n_idx in enumerate(neg_idx2):
        theta01_2[i] = np.sum(y_prob_sorted2[pos_idx2] > y_prob_sorted2[n_idx]) / n1
        theta01_2[i] += 0.5 * np.sum(y_prob_sorted2[pos_idx2] == y_prob_sorted2[n_idx]) / n1

    # Covariance
    S10 = np.cov(theta10_1, theta10_2, ddof=1)
    S01 = np.cov(theta01_1, theta01_2, ddof=1)

    covar = S10[0, 1] / n1 + S01[0, 1] / n2
    se = np.sqrt(max(var1 + var2 - 2 * covar, 1e-10))
    z = (auc1 - auc2) / se
    p_value = 2 * norm.sf(abs(z))
    return p_value


def compare_models_statistical(
    y_true: np.ndarray,
    models_probs_dict: Dict[str, np.ndarray],
    test: str = "delong",
) -> pd.DataFrame:
    """Perform statistical comparison of model AUCs.

    Parameters
    ----------
    y_true : numpy.ndarray
        Binary ground-truth labels.
    models_probs_dict : dict
        Mapping {model_name: predicted_probabilities}.
    test : str
        Statistical test to use ('delong' only currently).

    Returns
    -------
    pd.DataFrame
        Pairwise p-values matrix (models x models).
    """
    model_names = list(models_probs_dict.keys())
    n_models = len(model_names)
    p_values = np.ones((n_models, n_models))

    for i in range(n_models):
        for j in range(i + 1, n_models):
            p = _delong_roc_test(
                y_true,
                models_probs_dict[model_names[i]],
                models_probs_dict[model_names[j]],
            )
            p_values[i, j] = p
            p_values[j, i] = p

    df_p = pd.DataFrame(p_values, index=model_names, columns=model_names)

    print("\nDeLong Test — Pairwise p-values (AUC comparison)")
    print("H0: AUCs are equal (p < 0.05 indicates significant difference)")
    print(df_p.to_string(float_format=lambda x: f"{x:.4f}"))

    return df_p


# ---------------------------------------------------------------------------
# 11. find_optimal_threshold
# ---------------------------------------------------------------------------


def find_optimal_threshold(
    y_true: np.ndarray, y_prob: np.ndarray, metric: str = "f1"
) -> Tuple[float, float]:
    """Find the optimal classification threshold that maximises a given metric.

    Parameters
    ----------
    y_true : numpy.ndarray
        Binary ground-truth labels.
    y_prob : numpy.ndarray
        Predicted probabilities.
    metric : str
        Metric to maximise. One of 'f1', 'accuracy', 'precision', 'recall',
        'youden'.

    Returns
    -------
    threshold : float
        Optimal threshold value.
    metric_value : float
        Value of the metric at the optimal threshold.
    """
    return _get_optimal_threshold_metric(np.asarray(y_true), np.asarray(y_prob), metric)


# ---------------------------------------------------------------------------
# 12. evaluate_with_threshold
# ---------------------------------------------------------------------------


def evaluate_with_threshold(
    y_true: np.ndarray, y_prob: np.ndarray, threshold: float
) -> Dict[str, float]:
    """Evaluate model metrics using a custom probability threshold.

    Parameters
    ----------
    y_true : numpy.ndarray
        Binary ground-truth labels.
    y_prob : numpy.ndarray
        Predicted probabilities.
    threshold : float
        Classification threshold (0 <= threshold <= 1).

    Returns
    -------
    dict
        Full metrics dictionary at the given threshold.
    """
    y_pred = (np.asarray(y_prob) >= threshold).astype(int)
    return compute_all_metrics(y_true, y_pred, y_prob)


# ---------------------------------------------------------------------------
# 13. run_full_evaluation
# ---------------------------------------------------------------------------


def run_full_evaluation(
    models_dict: Dict[str, Any],
    X_test: np.ndarray,
    y_test: np.ndarray,
    output_dir: str = "outputs/",
) -> Dict[str, Any]:
    """Orchestrate a full evaluation pipeline across multiple models.

    For each model in ``models_dict``, obtains predictions (and probabilities
    if available), computes all metrics, generates all comparison plots and
    tables, and returns a summary dictionary.

    Parameters
    ----------
    models_dict : dict
        Mapping {model_name: model_object}. Each model must have a ``predict``
        method; if it also has ``predict_proba``, probabilities are used for
        ROC/PR/threshold-dependent metrics.
    X_test : numpy.ndarray
        Test features.
    y_test : numpy.ndarray
        Test ground-truth labels.
    output_dir : str
        Root output directory for figures and tables.

    Returns
    -------
    dict
        Summary containing model-wise metrics, comparison table, CI results,
        statistical test results, and paths to saved files.
    """
    y_test = np.asarray(y_test)
    results_dict: Dict[str, Dict[str, np.ndarray]] = {}
    models_probs: Dict[str, np.ndarray] = {}

    for model_name, model in models_dict.items():
        print(f"  Evaluating {model_name} ...")

        # Predict class labels
        y_pred = model.predict(X_test)
        results_dict[model_name] = {"y_true": y_test, "y_pred": y_pred}

        # Predict probabilities if available
        if hasattr(model, "predict_proba"):
            y_prob = model.predict_proba(X_test)[:, 1]
        else:
            # Fallback: use decision_function
            if hasattr(model, "decision_function"):
                y_prob = model.decision_function(X_test)
                # Normalise to [0, 1] via min-max if not already probabilities
                y_prob = (y_prob - y_prob.min()) / max((y_prob.max() - y_prob.min()), 1e-10)
            else:
                y_prob = y_pred.astype(float)

        results_dict[model_name]["y_prob"] = y_prob
        models_probs[model_name] = y_prob

    # Create output directories
    plots_dir = os.path.join(output_dir, "plots")
    tables_dir = os.path.join(output_dir, "tables")
    os.makedirs(plots_dir, exist_ok=True)
    os.makedirs(tables_dir, exist_ok=True)

    # ---- 1. Compute all metrics per model ----
    print("\n" + "=" * 60)
    print("INDIVIDUAL MODEL METRICS")
    print("=" * 60)
    model_metrics: Dict[str, Dict[str, float]] = {}
    for model_name, res in results_dict.items():
        metrics = compute_all_metrics(res["y_true"], res["y_pred"], res["y_prob"])
        model_metrics[model_name] = metrics
        print(f"\n  {model_name}:")
        for k, v in metrics.items():
            print(f"    {k}: {v}")

    # ---- 2. Confidence intervals ----
    print("\n" + "-" * 60)
    print("BOOTSTRAP CONFIDENCE INTERVALS (95%)")
    print("-" * 60)
    ci_results: Dict[str, Dict[str, Tuple[float, float, float]]] = {}
    for model_name, res in results_dict.items():
        ci = compute_confidence_intervals(res["y_true"], res["y_pred"], res["y_prob"])
        ci_results[model_name] = ci
        print(f"\n  {model_name}:")
        for m, (mean_val, lo, hi) in ci.items():
            print(f"    {m}: {mean_val} [{lo}, {hi}]")

    # ---- 3. Plots ----
    print("\n" + "-" * 60)
    print("GENERATING PLOTS")
    print("-" * 60)

    plot_paths: Dict[str, str] = {}

    # ROC curves
    roc_path = os.path.join(plots_dir, "roc_curves.png")
    plot_roc_curves(results_dict, roc_path)
    plot_paths["roc_curves"] = roc_path
    print(f"  ROC curves saved: {roc_path}")

    # PR curves
    pr_path = os.path.join(plots_dir, "pr_curves.png")
    plot_pr_curves(results_dict, pr_path)
    plot_paths["pr_curves"] = pr_path
    print(f"  PR curves saved: {pr_path}")

    # Confusion matrices
    cm_path = os.path.join(plots_dir, "confusion_matrices.png")
    plot_confusion_matrices(results_dict, cm_path)
    plot_paths["confusion_matrices"] = cm_path
    print(f"  Confusion matrices saved: {cm_path}")

    # Calibration curves
    cal_path = os.path.join(plots_dir, "calibration_curves.png")
    plot_calibration_curves(results_dict, save_path=cal_path)
    plot_paths["calibration_curves"] = cal_path
    print(f"  Calibration curves saved: {cal_path}")

    # Heatmap
    heatmap_path = os.path.join(plots_dir, "comparison_heatmap.png")
    plot_model_comparison_heatmap(results_dict, save_path=heatmap_path)
    plot_paths["heatmap"] = heatmap_path
    print(f"  Heatmap saved: {heatmap_path}")

    # Radar chart
    radar_path = os.path.join(plots_dir, "radar_chart.png")
    try:
        plot_radar_chart(results_dict, save_path=radar_path)
        plot_paths["radar_chart"] = radar_path
        print(f"  Radar chart saved: {radar_path}")
    except ValueError as e:
        print(f"  Radar chart skipped: {e}")

    # ---- 4. Comparison table ----
    print("\n" + "-" * 60)
    print("MODEL COMPARISON TABLE")
    print("-" * 60)
    comparison_df = create_model_comparison_table(results_dict, save_path=tables_dir)

    # ---- 5. Statistical comparison ----
    print("\n" + "-" * 60)
    print("STATISTICAL COMPARISON (DeLong Test)")
    print("-" * 60)
    delong_df = compare_models_statistical(y_test, models_probs)
    delong_path = os.path.join(tables_dir, "delong_test_pvalues.csv")
    delong_df.to_csv(delong_path)
    print(f"  DeLong p-values saved: {delong_path}")

    # ---- 6. Optimal thresholds ----
    print("\n" + "-" * 60)
    print("OPTIMAL THRESHOLDS (by F1)")
    print("-" * 60)
    threshold_results: Dict[str, Dict[str, float]] = {}
    for model_name, res in results_dict.items():
        best_th, best_f1 = find_optimal_threshold(res["y_true"], res["y_prob"], metric="f1")
        th_metrics = evaluate_with_threshold(res["y_true"], res["y_prob"], best_th)
        threshold_results[model_name] = {
            "optimal_threshold": round(best_th, 4),
            "best_f1": round(best_f1, 4),
            "threshold_metrics": th_metrics,
        }
        print(f"  {model_name}: best threshold = {best_th:.4f} (F1 = {best_f1:.4f})")

    # ---- Summary ----
    summary = {
        "n_models": len(models_dict),
        "model_metrics": model_metrics,
        "confidence_intervals": ci_results,
        "comparison_table": comparison_df,
        "delong_test": delong_df,
        "optimal_thresholds": threshold_results,
        "plot_paths": plot_paths,
        "table_paths": {
            "comparison": os.path.join(tables_dir, "model_comparison.csv"),
            "delong": delong_path,
        },
    }

    print("\n" + "=" * 60)
    print("EVALUATION COMPLETE")
    print("=" * 60)
    print(f"  Plots:   {plots_dir}")
    print(f"  Tables:  {tables_dir}")
    print(f"  Models:  {summary['n_models']}")

    return summary


# ---------------------------------------------------------------------------
# Legacy / convenience aliases
# ---------------------------------------------------------------------------

evaluate_model = compute_all_metrics

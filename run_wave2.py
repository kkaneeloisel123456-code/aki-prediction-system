# -*- coding: utf-8 -*-
"""
AKI 高级方法对比 Wave 2

覆盖四项补充证据：
1. MICE 与中位数填补对比（训练折内拟合）
2. SMOTE 与 class_weight 对比（训练折内过采样）
3. DCA 决策阈值推荐与成本效益表
4. 重复 CV 的不确定性区间（每患者 95% 概率区间）

运行:
    python run_wave2.py             # 默认：3折重复 + 10次不确定性
    python run_wave2.py --quick     # 快速版

输出:
    outputs/tables/wave2_*.csv
    outputs/figures/wave2_threshold_nb.png
"""

from __future__ import annotations

import argparse
import warnings
from datetime import datetime
from functools import partial
from pathlib import Path

warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
from imblearn.over_sampling import SMOTE
from imblearn.pipeline import Pipeline as ImbPipeline
from sklearn.base import clone
from sklearn.experimental import enable_iterative_imputer  # noqa: F401
from sklearn.feature_selection import SelectFromModel
from sklearn.impute import IterativeImputer, SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import RepeatedStratifiedKFold, StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

import run_advanced as ra
from src.config import TARGET
from src.data.prepare import prepare_raw_numeric, prepare_training_data


ROOT = Path(__file__).resolve().parent
OUT_TABLES = ROOT / 'outputs' / 'tables'
OUT_FIGURES = ROOT / 'outputs' / 'figures'
OUT_TABLES.mkdir(parents=True, exist_ok=True)
OUT_FIGURES.mkdir(parents=True, exist_ok=True)


def manual_cv_auc_brier(X, y, pipeline_factory, cv):
    """逐折 fit/predict，同时计算 AUC 与 Brier，避免 scorer 协议差异。"""
    aucs, briers = [], []
    for tr_idx, te_idx in cv.split(X, y):
        pipe = pipeline_factory()
        pipe.fit(X.iloc[tr_idx], y.iloc[tr_idx])
        proba = pipe.predict_proba(X.iloc[te_idx])[:, 1]
        aucs.append(roc_auc_score(y.iloc[te_idx], proba))
        briers.append(brier_score_loss(y.iloc[te_idx], proba))
    return np.asarray(aucs), np.asarray(briers)


def summarize_auc_brier(name, aucs, briers, **extra):
    row = {
        '配置': name,
        'CV折数': len(aucs),
        'AUC均值': round(float(np.mean(aucs)), 4),
        'AUC标准差': round(float(np.std(aucs)), 4),
        'Brier均值': round(float(np.mean(briers)), 4),
        'Brier标准差': round(float(np.std(briers)), 4),
    }
    row.update({k: round(float(v), 4) if isinstance(v, (int, float)) else v
                for k, v in extra.items()})
    return row


# ----------------------------------------------------------------------
# 1. MICE 与中位数填补对比
# ----------------------------------------------------------------------
def make_impute_pipeline(y, imputer):
    return Pipeline([
        ('imputer', imputer),
        ('scaler', StandardScaler()),
        ('selector', SelectFromModel(clone(ra.SELECTOR_RF), max_features=35)),
        ('model', ra.make_voting(y)),
    ])


def run_imputation_comparison(X, y, repeats):
    cv = RepeatedStratifiedKFold(n_splits=5, n_repeats=repeats, random_state=42)
    rows = []
    for name, imputer in [
        ('median_baseline', SimpleImputer(strategy='median')),
        ('MICE_IterativeImputer', IterativeImputer(
            max_iter=10, random_state=42, imputation_order='ascending')),
    ]:
        factory = partial(make_impute_pipeline, y=y, imputer=imputer)
        aucs, briers = manual_cv_auc_brier(X, y, factory, cv)
        rows.append(summarize_auc_brier(name, aucs, briers))
        print(f'  {name}: AUC={np.mean(aucs):.4f} ± {np.std(aucs):.4f}, '
              f'Brier={np.mean(briers):.4f}')
    df = pd.DataFrame(rows)
    df.to_csv(OUT_TABLES / 'wave2_imputation.csv', index=False, encoding='utf-8-sig')
    return df


# ----------------------------------------------------------------------
# 2. SMOTE 与 class_weight 对比
# ----------------------------------------------------------------------
def make_xgb(y, scale_pos_weight):
    return XGBClassifier(
        n_estimators=200, max_depth=3, learning_rate=0.02,
        subsample=0.8, colsample_bytree=0.8,
        reg_alpha=1.0, reg_lambda=1.0, min_child_weight=5,
        scale_pos_weight=scale_pos_weight, random_state=42,
        use_label_encoder=False, eval_metric='logloss', verbosity=0,
    )


def make_lr(class_weight):
    return LogisticRegression(
        C=0.02, penalty='l2', class_weight=class_weight,
        max_iter=5000, random_state=42, solver='saga',
    )


def make_smote_pipeline(y, model, use_smote):
    steps = [
        ('imputer', SimpleImputer(strategy='median')),
        ('scaler', StandardScaler()),
        ('selector', SelectFromModel(clone(ra.SELECTOR_RF), max_features=35)),
    ]
    if use_smote:
        steps.append(('smote', SMOTE(random_state=42)))
    steps.append(('model', model))
    return ImbPipeline(steps)


def run_smote_comparison(X, y, repeats):
    cv = RepeatedStratifiedKFold(n_splits=5, n_repeats=repeats, random_state=42)
    pos_weight = (y == 0).sum() / max((y == 1).sum(), 1)
    configs = [
        ('XGB_baseline_scale_pos_weight',
         make_smote_pipeline(y, make_xgb(y, pos_weight), False)),
        ('XGB_SMOTE_no_scale_pos_weight',
         make_smote_pipeline(y, make_xgb(y, 1.0), True)),
        ('LR_baseline_class_weight_balanced',
         make_smote_pipeline(y, make_lr('balanced'), False)),
        ('LR_SMOTE_no_class_weight',
         make_smote_pipeline(y, make_lr(None), True)),
    ]
    rows = []
    for name, pipe in configs:
        aucs, briers = manual_cv_auc_brier(
            X, y, lambda p=pipe: clone(p), cv)
        rows.append(summarize_auc_brier(name, aucs, briers))
        print(f'  {name}: AUC={np.mean(aucs):.4f} ± {np.std(aucs):.4f}, '
              f'Brier={np.mean(briers):.4f}')
    df = pd.DataFrame(rows)
    df.to_csv(OUT_TABLES / 'wave2_smote.csv', index=False, encoding='utf-8-sig')
    return df


# ----------------------------------------------------------------------
# 3. 决策阈值与成本效益
# ----------------------------------------------------------------------
def net_benefit(y_true, y_prob, threshold):
    y_pred = (y_prob >= threshold).astype(int)
    tp = int(((y_pred == 1) & (y_true == 1)).sum())
    fp = int(((y_pred == 1) & (y_true == 0)).sum())
    n = len(y_true)
    return tp / n - fp / n * (threshold / (1 - threshold)), tp, fp


def compute_voting_oof(X, y, cv):
    oof = np.zeros(len(y))
    for tr_idx, te_idx in cv.split(X, y):
        pipe = ra.build_pipeline(ra.make_voting(y))
        pipe.fit(X.iloc[tr_idx], y.iloc[tr_idx])
        oof[te_idx] = pipe.predict_proba(X.iloc[te_idx])[:, 1]
    return oof


def run_threshold_and_cost_benefit(X, y):
    cv5 = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    y_arr = np.asarray(y)
    oof = compute_voting_oof(X, y, cv5)
    n = len(y_arr)

    grid = np.arange(0.05, 0.81, 0.01)
    rows = []
    for t in grid:
        nb, tp, fp = net_benefit(y_arr, oof, t)
        treat_all = y_arr.mean() - (1 - y_arr.mean()) * (t / (1 - t))
        rows.append({
            '阈值': round(float(t), 2),
            '净获益_模型': round(float(nb), 4),
            '净获益_全部干预': round(float(treat_all), 4),
            '净获益_差值': round(float(nb - treat_all), 4),
            '真阳例数': tp,
            '假阳例数': fp,
            '每千例_真阳': round(tp / n * 1000, 1),
            '每千例_假阳': round(fp / n * 1000, 1),
        })
    table = pd.DataFrame(rows)
    table.to_csv(OUT_TABLES / 'wave2_threshold.csv', index=False, encoding='utf-8-sig')

    candidates = table[table['阈值'] <= 0.5].copy()
    default_best = np.maximum(0, candidates['净获益_全部干预'].to_numpy())
    incremental = candidates['净获益_模型'].to_numpy() - default_best
    pos_mask = incremental > 0
    if np.any(pos_mask):
        recommended = float(candidates.loc[candidates.index[pos_mask], '阈值'].iloc[
            np.argmax(incremental[pos_mask])])
    else:
        recommended = 0.3
    summary = pd.DataFrame([{
        '推荐阈值': recommended,
        'OOF_AUC': round(float(roc_auc_score(y_arr, oof)), 4),
        'AKI率': round(float(y_arr.mean()), 4),
    }])
    summary.to_csv(OUT_TABLES / 'wave2_threshold_summary.csv',
                   index=False, encoding='utf-8-sig')

    # 成本效益敏感性表（不虚构绝对费用，用“干预成本/AKI成本”比例表达）
    cb_rows = []
    for ratio in [0.1, 0.2, 0.3, 0.5, 1.0]:
        t = ratio / (1 + ratio)
        nb, tp, fp = net_benefit(y_arr, oof, t)
        treat_all = y_arr.mean() - (1 - y_arr.mean()) * ratio
        cb_rows.append({
            '干预成本占AKI成本比例': ratio,
            '对应决策阈值': round(float(t), 3),
            '每千例_真阳': round(tp / n * 1000, 1),
            '每千例_假阳': round(fp / n * 1000, 1),
            '净获益差值_每千例_AKI成本单位': round(float((nb - treat_all) * 1000), 2),
        })
    cb_df = pd.DataFrame(cb_rows)
    cb_df.to_csv(OUT_TABLES / 'wave2_cost_benefit.csv', index=False, encoding='utf-8-sig')

    _plot_threshold(table, recommended)
    print(f'  推荐阈值: {recommended:.2f}, OOF AUC: {summary.iloc[0]["OOF_AUC"]:.4f}')
    return table, cb_df, recommended


def _plot_threshold(table, recommended):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(10, 7))
    ax.plot(table['阈值'], table['净获益_模型'], color='#1B1B1B', lw=2.5,
            label='Model (Voting OOF)')
    ax.plot(table['阈值'], table['净获益_全部干预'], '--', color='#999999', lw=2,
            label='Treat All')
    ax.axhline(0, color='#CCCCCC', lw=1.5, label='Treat None')
    positive = table[
        (table['净获益_模型'] > 0) &
        (table['净获益_模型'] > table['净获益_全部干预'])
    ]
    if len(positive):
        ax.axvspan(positive['阈值'].min(), positive['阈值'].max(),
                   color='#F18F01', alpha=0.12, label='Model > Treat All')
    ax.axvline(recommended, color='#C73E1D', ls=':', lw=2,
               label=f'Recommended = {recommended:.2f}')
    ax.set_xlabel('Decision Threshold', fontsize=12)
    ax.set_ylabel('Net Benefit', fontsize=12)
    ax.set_title('DCA Threshold Recommendation (Voting, 5-Fold OOF)',
                 fontsize=13, fontweight='bold')
    ax.legend(loc='upper right', fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT_FIGURES / 'wave2_threshold_nb.png', dpi=300,
                bbox_inches='tight', facecolor='white')
    plt.close(fig)


# ----------------------------------------------------------------------
# 4. 重复 CV 不确定性量化
# ----------------------------------------------------------------------
def run_uncertainty_quantification(X, y, repeats):
    cv = RepeatedStratifiedKFold(n_splits=5, n_repeats=repeats, random_state=42)
    preds = [[] for _ in range(len(y))]
    for tr_idx, te_idx in cv.split(X, y):
        pipe = ra.build_pipeline(ra.make_voting(y))
        pipe.fit(X.iloc[tr_idx], y.iloc[tr_idx])
        proba = pipe.predict_proba(X.iloc[te_idx])[:, 1]
        for idx, prob in zip(te_idx, proba):
            preds[int(idx)].append(float(prob))

    means = np.array([np.mean(v) for v in preds])
    lowers = np.array([
        np.percentile(v, 2.5) if len(v) > 1 else float(v[0]) for v in preds
    ])
    uppers = np.array([
        np.percentile(v, 97.5) if len(v) > 1 else float(v[0]) for v in preds
    ])
    widths = uppers - lowers
    bands = np.where(
        means < 0.3, '低风险(<0.3)',
        np.where(means < 0.7, '中风险(0.3-0.7)', '高风险(>=0.7)'),
    )
    patient_df = pd.DataFrame({
        '患者序号': np.arange(len(y)),
        'AKI': np.asarray(y),
        '概率均值': np.round(means, 4),
        '95%CI下限': np.round(lowers, 4),
        '95%CI上限': np.round(uppers, 4),
        '区间宽度': np.round(widths, 4),
        '风险分层': bands,
    })
    patient_df.to_csv(OUT_TABLES / 'wave2_uncertainty_patients.csv',
                      index=False, encoding='utf-8-sig')

    summary_rows = [
        ('重复CV折数', 5 * repeats),
        ('概率均值AUC', round(float(roc_auc_score(np.asarray(y), means)), 4)),
        ('区间宽度均值', round(float(np.mean(widths)), 4)),
        ('区间宽度中位数', round(float(np.median(widths)), 4)),
        ('区间宽度P90', round(float(np.percentile(widths, 90)), 4)),
        ('宽度>0.15比例', round(float((widths > 0.15).mean()), 4)),
        ('宽度>0.20比例', round(float((widths > 0.20).mean()), 4)),
        ('低风险比例', round(float((means < 0.3).mean()), 4)),
        ('中风险比例', round(float(((means >= 0.3) & (means < 0.7)).mean()), 4)),
        ('高风险比例', round(float((means >= 0.7).mean()), 4)),
    ]
    summary_df = pd.DataFrame(summary_rows, columns=['指标', '数值'])
    summary_df.to_csv(OUT_TABLES / 'wave2_uncertainty_summary.csv',
                      index=False, encoding='utf-8-sig')
    for metric, value in summary_rows:
        print(f'  {metric}: {value}')
    return patient_df, summary_df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--quick', action='store_true')
    parser.add_argument('--repeats', type=int, default=3,
                        help='MICE/SMOTE 对比的重复次数')
    parser.add_argument('--uncertainty-repeats', type=int, default=10,
                        help='不确定性量化的重复次数')
    args = parser.parse_args()
    if args.quick:
        args.repeats = 1
        args.uncertainty_repeats = 3

    print('=' * 70)
    print('  AKI Wave 2：填补 / 过采样 / 阈值 / 不确定性')
    print(f'  开始: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print('=' * 70)

    df = pd.read_excel(ROOT / 'data' / 'raw' / 'AKI数据.xlsx')
    prep = prepare_training_data(df)
    y = prep['y']
    X = prepare_raw_numeric(df)
    missing = int(X.isna().sum().sum())
    print(f'样本 {len(y)} 例, 候选特征 {X.shape[1]} 个, '
          f'原始缺失值 {missing} 个, AKI 率 {y.mean():.1%}')
    print('所有填补 / 缩放 / 筛选均在训练折内完成，不使用全局中位数。')

    print(f'\n[1/4] MICE vs 中位数填补（5折 x {args.repeats}次）')
    run_imputation_comparison(X, y, args.repeats)

    print(f'\n[2/4] SMOTE vs class_weight（5折 x {args.repeats}次）')
    run_smote_comparison(X, y, args.repeats)

    print('\n[3/4] DCA 阈值推荐与成本效益（5折 OOF）')
    run_threshold_and_cost_benefit(X, y)

    print(f'\n[4/4] 重复 CV 不确定性（5折 x {args.uncertainty_repeats}次）')
    run_uncertainty_quantification(X, y, args.uncertainty_repeats)

    print('\n' + '=' * 70)
    print('  Wave 2 完成')
    print('=' * 70)


if __name__ == '__main__':
    main()

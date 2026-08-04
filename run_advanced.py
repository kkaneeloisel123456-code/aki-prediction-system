# -*- coding: utf-8 -*-
"""
AKI 高级方法对比实验（Wave 1）

与 run_clean.py 共用同一套数据准备与泄漏规则，所有新增方法（调参、
特征选择、特征交互、Stacking/Blending）都在交叉验证的训练折内完成，
最终统一用嵌套 CV AUC 报告，避免选择偏差。

运行:
    python run_advanced.py            # 完整对比（默认参数）
    python run_advanced.py --quick    # 快速版（减少折数与 trials）

输出:
    outputs/tables/advanced_fixed_cv.csv
    outputs/tables/advanced_tuning_summary.csv
    outputs/tables/advanced_tuning_params.json
    outputs/tables/advanced_feature_selection.csv
    outputs/tables/advanced_interactions.csv
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import warnings
from datetime import datetime
from pathlib import Path

warnings.filterwarnings('ignore')

import numpy as np
import optuna
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin, TransformerMixin, clone
from sklearn.ensemble import (
    ExtraTreesClassifier,
    RandomForestClassifier,
    StackingClassifier,
    VotingClassifier,
)
from sklearn.feature_selection import RFECV, SelectFromModel
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import (
    RepeatedStratifiedKFold,
    StratifiedKFold,
    cross_val_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from src.config import TARGET
from src.data.prepare import prepare_raw_numeric, prepare_training_data

optuna.logging.set_verbosity(optuna.logging.WARNING)


ROOT = Path(__file__).resolve().parent
OUT_TABLES = ROOT / 'outputs' / 'tables'
OUT_TABLES.mkdir(parents=True, exist_ok=True)

SELECTOR_RF = RandomForestClassifier(
    n_estimators=200, class_weight='balanced', random_state=42, n_jobs=-1
)


# ----------------------------------------------------------------------
# 折内特征工程与选择器
# ----------------------------------------------------------------------
class ClinicalInteractionTransformer(BaseEstimator, TransformerMixin):
    """在每折训练数据上追加临床交互列，之后统一填补/标准化/筛选。"""

    def __init__(self, pairs):
        self.pairs = pairs
        self.feature_names_ = []

    def fit(self, X, y=None):
        self.feature_names_ = list(X.columns)
        return self

    def transform(self, X):
        if isinstance(X, pd.DataFrame):
            df = X.copy()
        else:
            df = pd.DataFrame(X, columns=self.feature_names_)
        for a, b in self.pairs:
            if a in df.columns and b in df.columns:
                name = f'{a}__x__{b}'
                df[name] = df[a].astype(float) * df[b].astype(float)
        return df


class ShadowBorutaSelector(BaseEstimator, TransformerMixin):
    """Boruta-lite：用 shadow permutation 判定真实特征重要性是否超过随机特征。"""

    def __init__(
        self,
        estimator=None,
        n_iterations=5,
        max_features=35,
        hit_ratio=0.6,
        random_state=42,
    ):
        self.estimator = estimator
        self.n_iterations = n_iterations
        self.max_features = max_features
        self.hit_ratio = hit_ratio
        self.random_state = random_state

    def fit(self, X, y):
        X = np.asarray(X)
        y = np.asarray(y)
        rng = np.random.RandomState(self.random_state)
        base = self.estimator or RandomForestClassifier(
            n_estimators=150, class_weight='balanced',
            random_state=self.random_state, n_jobs=-1,
        )
        hits = np.zeros(X.shape[1], dtype=int)
        mean_imp = np.zeros(X.shape[1])
        for _ in range(self.n_iterations):
            shadow = np.column_stack([
                rng.permutation(X[:, j]) for j in range(X.shape[1])
            ])
            est = clone(base)
            est.fit(np.hstack([X, shadow]), y)
            imp = est.feature_importances_
            real = imp[:X.shape[1]]
            shadow_max = imp[X.shape[1]:].max()
            hits[real > shadow_max] += 1
            mean_imp += real
        mean_imp /= self.n_iterations
        keep = hits >= max(1, int(np.ceil(self.n_iterations * self.hit_ratio)))
        if not np.any(keep):
            keep = np.argsort(mean_imp)[::-1][: min(self.max_features, X.shape[1])]
            mask = np.zeros(X.shape[1], dtype=bool)
            mask[keep] = True
            keep = mask
        else:
            order = np.argsort(mean_imp)[::-1]
            chosen = order[keep[order]][: self.max_features]
            mask = np.zeros(X.shape[1], dtype=bool)
            mask[chosen] = True
            keep = mask
        self.support_ = keep
        self.n_features_ = int(keep.sum())
        return self

    def transform(self, X):
        return np.asarray(X)[:, self.support_]


def build_selector(name: str):
    if name == 'top35':
        return SelectFromModel(clone(SELECTOR_RF), max_features=35)
    if name == 'top20':
        return SelectFromModel(clone(SELECTOR_RF), max_features=20)
    if name == 'rfecv':
        return RFECV(
            estimator=RandomForestClassifier(
                n_estimators=100, class_weight='balanced',
                random_state=42, n_jobs=-1,
            ),
            step=5,
            cv=3,
            scoring='roc_auc',
            min_features_to_select=20,
            n_jobs=1,
        )
    if name == 'boruta_lite':
        return ShadowBorutaSelector(max_features=35, random_state=42)
    raise ValueError(f'unknown selector: {name}')


def build_pipeline(model, selector='top35', interactions=None):
    steps = []
    if interactions:
        steps.append(('interactions', ClinicalInteractionTransformer(interactions)))
    steps.append(('imputer', SimpleImputer(strategy='median')))
    steps.append(('scaler', StandardScaler()))
    steps.append(('selector', build_selector(selector)))
    steps.append(('model', model))
    return Pipeline(steps)


def count_selected_features(selector, X_sample):
    """返回选择器实际保留的特征数（兼容 SelectFromModel / RFECV / 自定义选择器）。"""
    if hasattr(selector, 'get_support'):
        try:
            return int(np.asarray(selector.get_support()).sum())
        except Exception:
            pass
    if hasattr(selector, 'support_') and getattr(selector, 'support_', None) is not None:
        return int(np.asarray(selector.support_).sum())
    if hasattr(selector, 'n_features_') and getattr(selector, 'n_features_', None) is not None:
        return int(selector.n_features_)
    return int(np.asarray(selector.transform(X_sample)).shape[1])


# ----------------------------------------------------------------------
# 模型构造
# ----------------------------------------------------------------------
def make_base_models(y):
    pos_weight = (y == 0).sum() / max((y == 1).sum(), 1)
    return {
        'LogisticRegression': LogisticRegression(
            C=0.02, penalty='l2', class_weight='balanced',
            max_iter=5000, random_state=42, solver='saga',
        ),
        'RandomForest': RandomForestClassifier(
            n_estimators=300, max_depth=5, min_samples_leaf=15,
            min_samples_split=15, class_weight='balanced',
            random_state=42, n_jobs=-1,
        ),
        'XGBoost': XGBClassifier(
            n_estimators=200, max_depth=3, learning_rate=0.02,
            subsample=0.8, colsample_bytree=0.8,
            reg_alpha=1.0, reg_lambda=1.0, min_child_weight=5,
            scale_pos_weight=pos_weight, random_state=42,
            use_label_encoder=False, eval_metric='logloss', verbosity=0,
        ),
        'ExtraTrees': ExtraTreesClassifier(
            n_estimators=200, max_depth=5, min_samples_leaf=15,
            class_weight='balanced', random_state=42, n_jobs=-1,
        ),
    }


def make_voting(y):
    models = make_base_models(y)
    return VotingClassifier(
        estimators=[(name, m) for name, m in models.items()],
        voting='soft',
        weights=[2, 2, 1, 1],
    )


def make_stacking(y):
    models = make_base_models(y)
    return StackingClassifier(
        estimators=[(name, m) for name, m in models.items()],
        final_estimator=LogisticRegression(C=0.1, max_iter=3000, random_state=42),
        cv=3,
        stack_method='predict_proba',
        n_jobs=1,
    )


def _weight_grid(n_models, step=0.2):
    vals = np.arange(0, 1.0001, step)
    grid = []
    for w in itertools.product(vals, repeat=n_models):
        if abs(sum(w) - 1.0) < 1e-6:
            grid.append(list(w))
    return grid


class BlendingClassifier(BaseEstimator, ClassifierMixin):
    """OOF 加权 Blending：内层 OOF 上网格搜索非负权重，再在完整训练折内拟合基模型。"""

    _estimator_type = "classifier"

    def __init__(self, estimators, inner_cv=3, random_state=42):
        self.estimators = estimators
        self.inner_cv = inner_cv
        self.random_state = random_state

    def fit(self, X, y):
        X = np.asarray(X)
        y = np.asarray(y)
        self.classes_ = np.unique(y)
        self.n_features_in_ = X.shape[1]
        inner = StratifiedKFold(
            n_splits=self.inner_cv, shuffle=True, random_state=self.random_state
        )
        oof = np.zeros((len(y), len(self.estimators)))
        for tr, te in inner.split(X, y):
            for j, m in enumerate(self.estimators):
                m_clone = clone(m)
                m_clone.fit(X[tr], y[tr])
                oof[te, j] = m_clone.predict_proba(X[te])[:, 1]

        best_w, best_auc = None, -1.0
        for w in _weight_grid(len(self.estimators)):
            score = roc_auc_score(y, oof @ np.asarray(w))
            if score > best_auc:
                best_auc, best_w = score, w
        self.weights_ = np.asarray(best_w)
        self.inner_auc_ = best_auc
        self.base_models_ = [clone(m).fit(X, y) for m in self.estimators]
        return self

    def predict_proba(self, X):
        X = np.asarray(X)
        p = np.column_stack([
            m.predict_proba(X)[:, 1] for m in self.base_models_
        ]) @ self.weights_
        return np.column_stack([1.0 - p, p])

    def predict(self, X):
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)


def make_blending(y):
    models = list(make_base_models(y).values())
    return BlendingClassifier(estimators=models, inner_cv=3, random_state=42)


# ----------------------------------------------------------------------
# Optuna 调参（内层 CV 在训练折内进行）
# ----------------------------------------------------------------------
def suggest_params(model_name, trial, y):
    if model_name == 'LogisticRegression':
        return {
            'C': trial.suggest_float('C', 1e-3, 10.0, log=True),
            'penalty': trial.suggest_categorical('penalty', ['l1', 'l2']),
            'class_weight': trial.suggest_categorical('class_weight', ['balanced', None]),
            'solver': 'saga',
            'max_iter': 5000,
        }
    if model_name in ('RandomForest', 'ExtraTrees'):
        return {
            'n_estimators': trial.suggest_int('n_estimators', 100, 300, step=50),
            'max_depth': trial.suggest_int('max_depth', 3, 8),
            'min_samples_leaf': trial.suggest_int('min_samples_leaf', 5, 30, step=5),
            'min_samples_split': trial.suggest_int('min_samples_split', 5, 30, step=5),
            'max_features': trial.suggest_categorical('max_features', ['sqrt', 'log2', None]),
            'class_weight': trial.suggest_categorical('class_weight', ['balanced', None]),
            'random_state': 42,
        }
    if model_name == 'XGBoost':
        return {
            'n_estimators': trial.suggest_int('n_estimators', 100, 300, step=50),
            'max_depth': trial.suggest_int('max_depth', 2, 6),
            'learning_rate': trial.suggest_float('learning_rate', 0.005, 0.15, log=True),
            'subsample': trial.suggest_float('subsample', 0.6, 1.0),
            'colsample_bytree': trial.suggest_float('colsample_bytree', 0.6, 1.0),
            'reg_alpha': trial.suggest_float('reg_alpha', 1e-3, 5.0, log=True),
            'reg_lambda': trial.suggest_float('reg_lambda', 1e-3, 5.0, log=True),
            'min_child_weight': trial.suggest_int('min_child_weight', 1, 10),
            'scale_pos_weight': (y == 0).sum() / max((y == 1).sum(), 1),
            'random_state': 42,
        }
    raise ValueError(model_name)


def build_model(model_name, params):
    if model_name == 'LogisticRegression':
        params = dict(params)
        params.setdefault('solver', 'saga')
        params.setdefault('max_iter', 5000)
        params.setdefault('random_state', 42)
        return LogisticRegression(**params)
    if model_name == 'RandomForest':
        return RandomForestClassifier(**params, n_jobs=-1)
    if model_name == 'ExtraTrees':
        return ExtraTreesClassifier(**params, n_jobs=-1)
    if model_name == 'XGBoost':
        return XGBClassifier(
            **params,
            use_label_encoder=False,
            eval_metric='logloss',
            verbosity=0,
        )
    raise ValueError(model_name)


def nested_tune_and_evaluate(model_name, X, y, outer_cv, n_trials, inner_splits=3):
    aucs = []
    inner_aucs = []
    params_list = []
    for fold_no, (tr_idx, te_idx) in enumerate(outer_cv.split(X, y), start=1):
        X_tr, X_te = X.iloc[tr_idx], X.iloc[te_idx]
        y_tr, y_te = y.iloc[tr_idx], y.iloc[te_idx]

        def objective(trial):
            params = suggest_params(model_name, trial, y_tr)
            pipe = build_pipeline(build_model(model_name, params))
            inner = StratifiedKFold(
                n_splits=inner_splits, shuffle=True, random_state=42
            )
            scores = cross_val_score(
                pipe, X_tr, y_tr, cv=inner, scoring='roc_auc', n_jobs=1
            )
            return float(scores.mean())

        study = optuna.create_study(
            direction='maximize',
            sampler=optuna.samplers.TPESampler(seed=42 + fold_no),
        )
        study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
        best = study.best_params
        pipe = build_pipeline(build_model(model_name, best))
        pipe.fit(X_tr, y_tr)
        auc = roc_auc_score(y_te, pipe.predict_proba(X_te)[:, 1])
        aucs.append(float(auc))
        inner_aucs.append(float(study.best_value))
        params_list.append(best)
        print(
            f'    fold {fold_no}/{len(list(outer_cv.split(X, y)))}: '
            f'inner CV AUC={study.best_value:.4f}, outer AUC={auc:.4f}'
        )
    return aucs, inner_aucs, params_list


# ----------------------------------------------------------------------
# 汇总与保存
# ----------------------------------------------------------------------
def summarize_scores(name, aucs, **extra):
    row = {
        '配置': name,
        'CV折数': len(aucs),
        'AUC均值': round(float(np.mean(aucs)), 4),
        'AUC标准差': round(float(np.std(aucs)), 4),
    }
    row.update({k: round(float(v), 4) if isinstance(v, (int, float)) else v
                for k, v in extra.items()})
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--quick', action='store_true', help='快速版（减少折数与 trials）')
    parser.add_argument('--repeats', type=int, default=5, help='固定配置对比的重复次数')
    parser.add_argument('--tune-repeats', type=int, default=1, help='调参外折重复次数')
    parser.add_argument('--tune-trials', type=int, default=20, help='每个外折的 Optuna trials')
    parser.add_argument('--fs-repeats', type=int, default=2, help='特征选择对比重复次数')
    parser.add_argument('--interaction-repeats', type=int, default=3, help='交互项对比重复次数')
    args = parser.parse_args()

    if args.quick:
        args.repeats = 3
        args.tune_repeats = 1
        args.tune_trials = 15
        args.fs_repeats = 1
        args.interaction_repeats = 2

    print('=' * 70)
    print('  AKI 高级方法对比（Wave 1）')
    print(f'  开始: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print('=' * 70)

    df = pd.read_excel(ROOT / 'data' / 'raw' / 'AKI数据.xlsx')
    prep = prepare_training_data(df)
    y = prep['y']
    X = prepare_raw_numeric(df)
    missing = int(X.isna().sum().sum())
    print(f'样本 {len(y)} 例, 候选数值特征 {X.shape[1]} 个, AKI 率 {y.mean():.1%}')
    print(f'原始缺失值 {missing} 个，所有 CV 在训练折内填补/缩放/筛选')

    all_rows = []

    # ---------------------------------------------------------------
    # 1. 固定配置对比：LR/RF/XGB/ET/Voting/Stacking/Blending
    # ---------------------------------------------------------------
    print('\n[1/4] 固定配置嵌套 CV 对比（5折 x %d次）' % args.repeats)
    cv_fixed = RepeatedStratifiedKFold(
        n_splits=5, n_repeats=args.repeats, random_state=42
    )
    candidates = {
        'LogisticRegression': make_base_models(y)['LogisticRegression'],
        'RandomForest': make_base_models(y)['RandomForest'],
        'XGBoost': make_base_models(y)['XGBoost'],
        'ExtraTrees': make_base_models(y)['ExtraTrees'],
        'Voting': make_voting(y),
        'Stacking': make_stacking(y),
        'Blending': make_blending(y),
    }
    fixed_rows = []
    for name, model in candidates.items():
        print(f'  {name} ...')
        if name == 'Blending':
            # 自定义 Blending 没有实现 sklearn 1.9 的 tags 协议，
            # cross_val_score 会把 predict_proba 的二维输出原样交给
            # roc_auc_score，因此这里按同样的外折手动评分。
            scores = []
            for tr_idx, te_idx in cv_fixed.split(X, y):
                pipe = build_pipeline(model)
                pipe.fit(X.iloc[tr_idx], y.iloc[tr_idx])
                scores.append(roc_auc_score(
                    y.iloc[te_idx], pipe.predict_proba(X.iloc[te_idx])[:, 1]
                ))
            scores = np.asarray(scores)
        else:
            pipe = build_pipeline(model)
            scores = cross_val_score(
                pipe, X, y, cv=cv_fixed, scoring='roc_auc', n_jobs=1
            )
        fixed_rows.append(summarize_scores(name, scores))
        print(f'    AUC = {scores.mean():.4f} ± {scores.std():.4f}')
    fixed_df = pd.DataFrame(fixed_rows)
    fixed_df.to_csv(OUT_TABLES / 'advanced_fixed_cv.csv', index=False, encoding='utf-8-sig')
    all_rows.append(('固定配置对比', fixed_df))

    # ---------------------------------------------------------------
    # 2. Optuna 贝叶斯调参（嵌套 CV：调参只在训练折内做）
    # ---------------------------------------------------------------
    print(f'\n[2/4] Optuna 调参（5折 x {args.tune_repeats}次, 每折 {args.tune_trials} trials, 内层3折CV）')
    cv_tune = RepeatedStratifiedKFold(
        n_splits=5, n_repeats=args.tune_repeats, random_state=42
    )
    n_tune_folds = 5 * args.tune_repeats
    tune_rows = []
    params_store = {}
    for model_name in ['LogisticRegression', 'RandomForest', 'XGBoost', 'ExtraTrees']:
        print(f'  {model_name} ...')
        aucs, inner_aucs, params_list = nested_tune_and_evaluate(
            model_name, X, y, cv_tune, args.tune_trials, inner_splits=3
        )
        params_store[model_name] = params_list
        tune_rows.append(summarize_scores(
            model_name, aucs,
            内层CV_AUC均值=np.mean(inner_aucs),
            每折最优参数=json.dumps(params_list, ensure_ascii=False),
        ))
        print(f'    外层 AUC = {np.mean(aucs):.4f} ± {np.std(aucs):.4f}')
    tune_df = pd.DataFrame(tune_rows)
    tune_df.to_csv(OUT_TABLES / 'advanced_tuning_summary.csv', index=False, encoding='utf-8-sig')
    (OUT_TABLES / 'advanced_tuning_params.json').write_text(
        json.dumps(params_store, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    all_rows.append(('Optuna 调参', tune_df))

    # ---------------------------------------------------------------
    # 3. 特征选择对比（Voting 固定配置 + 不同折内选择器）
    # ---------------------------------------------------------------
    print(f'\n[3/4] 特征选择对比（5折 x {args.fs_repeats}次）')
    cv_fs = RepeatedStratifiedKFold(
        n_splits=5, n_repeats=args.fs_repeats, random_state=42
    )
    selectors = ['top35', 'top20', 'rfecv', 'boruta_lite']
    fs_rows = []
    for sel_name in selectors:
        aucs, n_feats = [], []
        for tr_idx, te_idx in cv_fs.split(X, y):
            X_tr, X_te = X.iloc[tr_idx], X.iloc[te_idx]
            y_tr, y_te = y.iloc[tr_idx], y.iloc[te_idx]
            pipe = build_pipeline(make_voting(y), selector=sel_name)
            pipe.fit(X_tr, y_tr)
            sel = pipe.named_steps['selector']
            n_feats.append(count_selected_features(sel, X_tr.iloc[:1]))
            aucs.append(roc_auc_score(y_te, pipe.predict_proba(X_te)[:, 1]))
        fs_rows.append(summarize_scores(
            sel_name, aucs, 中位特征数=float(np.median(n_feats)),
        ))
        print(f'  {sel_name}: AUC={np.mean(aucs):.4f} ± {np.std(aucs):.4f}, 中位特征={np.median(n_feats)}')
    fs_df = pd.DataFrame(fs_rows)
    fs_df.to_csv(OUT_TABLES / 'advanced_feature_selection.csv', index=False, encoding='utf-8-sig')
    all_rows.append(('特征选择对比', fs_df))

    # ---------------------------------------------------------------
    # 4. 临床交互项对比
    # ---------------------------------------------------------------
    print(f'\n[4/4] 临床交互项对比（5折 x {args.interaction_repeats}次）')
    cv_inter = RepeatedStratifiedKFold(
        n_splits=5, n_repeats=args.interaction_repeats, random_state=42
    )
    interaction_pairs = [
        ('术前eGFR', '年龄'),
        ('ICUAdmSCr', '手术时间'),
        ('术后β2MG', '术后CRP'),
        ('APACHEII', '手术时间'),
        ('术中失血量', '手术时间'),
        ('术前Scr', '年龄'),
    ]
    pairs_available = [(a, b) for a, b in interaction_pairs
                       if a in X.columns and b in X.columns]
    print(f'  可用交互对: {pairs_available}')
    inter_rows = []
    for label, interactions in [
        ('baseline_no_interaction', None),
        ('with_6_clinical_interactions', pairs_available),
    ]:
        aucs, n_feats = [], []
        for tr_idx, te_idx in cv_inter.split(X, y):
            X_tr, X_te = X.iloc[tr_idx], X.iloc[te_idx]
            y_tr, y_te = y.iloc[tr_idx], y.iloc[te_idx]
            pipe = build_pipeline(make_voting(y), interactions=interactions)
            pipe.fit(X_tr, y_tr)
            n_feats.append(count_selected_features(
                pipe.named_steps['selector'], X_tr.iloc[:1]
            ))
            aucs.append(roc_auc_score(y_te, pipe.predict_proba(X_te)[:, 1]))
        inter_rows.append(summarize_scores(label, aucs))
        print(f'  {label}: AUC={np.mean(aucs):.4f} ± {np.std(aucs):.4f}')
    inter_df = pd.DataFrame(inter_rows)
    inter_df.to_csv(OUT_TABLES / 'advanced_interactions.csv', index=False, encoding='utf-8-sig')
    all_rows.append(('交互项对比', inter_df))

    print('\n' + '=' * 70)
    print('  Wave 1 完成')
    for title, table in all_rows:
        print(f'\n[{title}]')
        print(table.to_string(index=False))
    print(f'\n结束: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')


if __name__ == '__main__':
    main()

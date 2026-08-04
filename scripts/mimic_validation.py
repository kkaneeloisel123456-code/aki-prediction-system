# -*- coding: utf-8 -*-
"""
MIMIC-IV 外部验证框架

说明：
- MIMIC-IV 需要 PhysioNet 授权与数据下载，当前仓库不含外部数据。
- 本脚本提供最终 35 特征的 MIMIC-IV 概念映射、项目模型加载、
  外部评分与 AUC 计算接口，用于“外部验证计划”章节的落地准备。

用法：
    python scripts/mimic_validation.py --dry-run
    python scripts/mimic_validation.py --data external.csv --outcome aki
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent.parent


def load_feature_map(path: Path | None = None) -> dict[str, str]:
    """从 CSV 读取 project_feature -> mimic_concept 映射。"""
    path = path or ROOT / 'scripts' / 'mimic_feature_map.csv'
    df = pd.read_csv(path, encoding='utf-8-sig')
    return dict(zip(df['project_feature'], df['mimic_concept']))


def load_project_artifacts(project_root: Path | None = None) -> dict:
    """加载模型、scaler、特征清单与中位数填补值。"""
    root = Path(project_root) if project_root else ROOT
    feat_path = root / 'app_data' / 'features.txt'
    if not feat_path.exists():
        feat_path = root / 'models' / 'selected_features.txt'
    features = [
        line.strip() for line in feat_path.read_text(encoding='utf-8').splitlines()
        if line.strip()
    ]
    model_path = root / 'app_data' / 'final_model.joblib'
    if not model_path.exists():
        model_path = root / 'models' / 'final_voting_model.pkl'
    scaler_path = root / 'app_data' / 'scaler.joblib'
    if not scaler_path.exists():
        scaler_path = root / 'models' / 'scaler.pkl'
    cal_path = root / 'app_data' / 'calibrator.joblib'
    if not cal_path.exists():
        cal_path = root / 'models' / 'calibrator.pkl'
    impute_path = root / 'app_data' / 'impute_values.json'

    artifacts = {
        'features': features,
        'model': joblib.load(model_path),
        'scaler': joblib.load(scaler_path),
        'calibrator': joblib.load(cal_path) if cal_path.exists() else None,
        'impute_values': json.loads(impute_path.read_text(encoding='utf-8')),
    }
    return artifacts


def prepare_external_frame(
    mimic_df: pd.DataFrame,
    feature_map: dict[str, str],
    artifacts: dict,
) -> pd.DataFrame:
    """把外部 DataFrame 映射到项目 35 特征，并用项目学习中位数填补缺失。"""
    features = artifacts['features']
    out = pd.DataFrame(index=mimic_df.index)
    for feature in features:
        concept = feature_map.get(feature, feature)
        if concept in mimic_df.columns:
            out[feature] = pd.to_numeric(mimic_df[concept], errors='coerce')
        elif feature in mimic_df.columns:
            out[feature] = pd.to_numeric(mimic_df[feature], errors='coerce')
        else:
            out[feature] = np.nan
    medians = artifacts['impute_values']
    for feature in features:
        if feature in medians:
            out[feature] = out[feature].fillna(medians[feature])
    return out[features]


def score_mimic(
    mimic_df: pd.DataFrame,
    artifacts: dict,
    feature_map: dict[str, str],
    outcome_col: str | None = None,
) -> pd.DataFrame:
    """在外部数据上输出原始概率与校准概率，可选计算 AUC。"""
    features = artifacts['features']
    X = prepare_external_frame(mimic_df, feature_map, artifacts)
    X_scaled = artifacts['scaler'].transform(X[features])
    raw_prob = artifacts['model'].predict_proba(X_scaled)[:, 1]
    cal_prob = raw_prob.copy()
    if artifacts['calibrator'] is not None:
        cal_prob = artifacts['calibrator'].predict(raw_prob.reshape(-1, 1))
    result = pd.DataFrame({
        'raw_probability': raw_prob,
        'calibrated_probability': cal_prob,
    }, index=mimic_df.index)
    if outcome_col is not None and outcome_col in mimic_df.columns:
        from sklearn.metrics import roc_auc_score
        y = pd.to_numeric(mimic_df[outcome_col], errors='coerce')
        mask = y.notna()
        result['outcome'] = y
        if mask.sum() > 1:
            result.loc[mask, 'external_auc_raw'] = roc_auc_score(
                y[mask].astype(int), raw_prob[mask.values]
            )
            result.loc[mask, 'external_auc_calibrated'] = roc_auc_score(
                y[mask].astype(int), cal_prob[mask.values]
            )
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true',
                        help='只打印特征映射覆盖情况')
    parser.add_argument('--data', type=str, default=None,
                        help='外部 CSV/Parquet 路径')
    parser.add_argument('--outcome', type=str, default=None,
                        help='外部数据中的 AKI 结局列名')
    args = parser.parse_args()

    feature_map = load_feature_map()
    artifacts = load_project_artifacts()
    features = artifacts['features']
    mapped = [f for f in features if feature_map.get(f) is not None]
    unmapped = [f for f in features if feature_map.get(f) is None]

    print('=' * 70)
    print('  MIMIC-IV 外部验证框架')
    print('=' * 70)
    print(f'  项目最终特征: {len(features)}')
    print(f'  已映射 MIMIC 概念: {len(mapped)}')
    if unmapped:
        print(f'  未映射: {unmapped}')

    if args.dry_run or args.data is None:
        print('\n[DRY-RUN] 未执行外部评分。')
        print('准备 MIMIC-IV 数据时应按 scripts/mimic_feature_map.csv 的')
        print('mimic_concept 列建列，并补充 outcome 列（KDIGO 48h/7d AKI）。')
        print('然后运行: python scripts/mimic_validation.py --data <file> '
              '--outcome aki')
        return

    data_path = Path(args.data)
    if data_path.suffix.lower() == '.parquet':
        ext_df = pd.read_parquet(data_path)
    else:
        ext_df = pd.read_csv(data_path, encoding='utf-8-sig')
    result = score_mimic(ext_df, artifacts, feature_map, args.outcome)
    out_path = ROOT / 'outputs' / 'tables' / 'mimic_external_validation.csv'
    result.to_csv(out_path, encoding='utf-8-sig')
    print(f'  已保存: {out_path}')
    if args.outcome is not None and args.outcome in ext_df.columns:
        col = 'external_auc_raw'
        if col in result.columns:
            auc_raw = result[col].dropna().iloc[0]
            print(f'  外部验证 AUC (raw): {auc_raw}')


if __name__ == '__main__':
    main()

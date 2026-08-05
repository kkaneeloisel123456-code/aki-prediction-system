# -*- coding: utf-8 -*-
"""MIMIC-IV 外部验证管线自测（合成数据，非真实外部验证）

重要声明：
    本脚本使用【合成数据】验证“外部 DataFrame → 映射 → 填补 → 评分 → AUC”的
    端到端管线可用性。输出【不是】外部验证证据，不得作为外部验证结果写入报告。
    真实外部验证需 PhysioNet 授权数据（scripts/mimic_extract.sql 提取后，
    运行 python scripts/mimic_validation.py --data <file> --outcome outcome_aki）。

用法：
    python scripts/mimic_pipeline_self_test.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

import mimic_validation  # noqa: E402

RNG = np.random.RandomState(42)
N = 300

# 每个 MIMIC 概念的合成分布（base=非AKI均值, shift=AKI病例偏移, scale=噪声）
SPEC = {
    'creatinine_icu_first':      (1.0, 0.45, 0.15),
    'egfr_icu_first':            (80.0, -22.0, 12.0),
    'egfr_preop':                (82.0, -18.0, 12.0),
    'troponin_preop':            (0.05, 0.10, 0.03),
    'troponin_postop':           (0.8, 1.6, 0.4),
    'beta2_microglobulin_postop':(2.4, 1.4, 0.6),
    'beta2_microglobulin_preop': (2.0, 0.6, 0.5),
    'myoglobin_postop':          (90.0, 120.0, 40.0),
    'lactate_postop':            (1.6, 1.4, 0.7),
    'bun_postop':                (22.0, 18.0, 8.0),
    'uric_acid_postop':          (5.6, 1.6, 1.4),
    'monocyte_postop':           (0.6, 0.25, 0.2),
    'platelet_postop':           (180.0, -35.0, 50.0),
    'platelet_preop':            (205.0, -20.0, 55.0),
    'wbc_preop':                 (8.2, 3.0, 2.5),
    'retinol_binding_protein_preop': (42.0, -10.0, 12.0),
    'crp_postop':                (35.0, 55.0, 20.0),
    'albumin_postop':            (3.3, -0.4, 0.5),
    'base_excess_postop':        (-0.5, -2.5, 2.0),
    'neutrophil_preop':          (6.4, 2.4, 2.2),
    'bnp_preop':                 (320.0, 500.0, 220.0),
    'bnp_postop':                (900.0, 1500.0, 600.0),
    'creatine_kinase_mb_preop':  (6.0, 5.0, 3.0),
    'creatine_kinase_preop':     (150.0, 120.0, 80.0),
    'creatinine_preop':          (0.9, 0.35, 0.2),
    'lymphocyte_preop':          (1.7, 0.3, 0.5),
    'lymphocyte_postop':         (1.4, 0.25, 0.45),
    'pao2_preop':                (85.0, -8.0, 12.0),
    'pao2_postop':               (95.0, -25.0, 22.0),
    'sbp_preop':                 (128.0, -10.0, 15.0),
    'apache_ii':                 (12.0, 9.0, 4.5),
    'crystalloid_volume':        (1500.0, 800.0, 600.0),
    'case_duration':             (4.5, 1.2, 1.0),
    'estimated_blood_loss':      (600.0, 400.0, 300.0),
    'crp_albumin_ratio_postop':  (10.5, 16.0, 6.0),
    'plr_preop':                 (130.0, 30.0, 40.0),
    'plr_postop':                (150.0, 20.0, 45.0),
    'lmr_preop':                 (3.0, 0.8, 1.0),
    'ckmb_ck_ratio_preop':       (0.045, 0.02, 0.015),
}

# 结果恒为 1.0（AKI 时升高）的列——用于保证合成信号方向正确
UP_HIGH = {'troponin_preop', 'troponin_postop', 'myoglobin_postop', 'lactate_postop',
           'bun_postop', 'uric_acid_postop', 'crp_postop', 'bnp_preop', 'bnp_postop',
           'creatine_kinase_mb_preop', 'creatine_kinase_preop', 'apache_ii',
           'crystalloid_volume', 'case_duration', 'estimated_blood_loss',
           'crp_albumin_ratio_postop', 'plr_preop', 'plr_postop',
           'creatinine_icu_first', 'creatinine_preop', 'ckmb_ck_ratio_preop',
           'beta2_microglobulin_postop', 'beta2_microglobulin_preop',
           'monocyte_postop', 'wbc_preop', 'neutrophil_preop'}


def make_synthetic_frame(feature_map: dict[str, str]) -> pd.DataFrame:
    """按映射概念名生成合成外部表（含 outcome_aki）。"""
    concepts = list(dict.fromkeys(feature_map.values()))
    df = pd.DataFrame({'subject_id': np.arange(1, N + 1)})
    y = (RNG.rand(N) < 0.30).astype(int)          # 30% AKI
    df['outcome_aki'] = y
    for c in concepts:
        if c not in SPEC:
            continue
        base, shift, scale = SPEC[c]
        mean = base + (shift if c in UP_HIGH else 0.0) * y
        vals = np.abs(RNG.normal(mean, scale))    # 取绝对值保证正值域
        if c in ('egfr_icu_first', 'egfr_preop', 'albumin_postop', 'pao2_preop', 'pao2_postop',
                 'sbp_preop', 'platelet_preop', 'platelet_postop',
                 'retinol_binding_protein_preop', 'base_excess_postop'):
            vals = base + shift * y + RNG.normal(0, scale, N)  # 允许下降方向
        df[c] = vals
        # 10% 随机缺失，验证学习中位数填补路径
        miss = RNG.rand(N) < 0.10
        df.loc[miss, c] = np.nan
    return df


def main() -> None:
    feature_map = mimic_validation.load_feature_map()
    artifacts = mimic_validation.load_project_artifacts()
    features = artifacts['features']

    # 1) 映射覆盖检查
    mapped = [f for f in features if feature_map.get(f)]
    unmapped = [f for f in features if feature_map.get(f) is None]
    print('=' * 66)
    print('  MIMIC-IV 管线自测（合成数据 / SIMULATION ONLY）')
    print('=' * 66)
    print(f'  项目特征: {len(features)} / 已映射: {len(mapped)}')
    if unmapped:
        print(f'  未映射: {unmapped}')

    # 2) 合成外部表
    df = make_synthetic_frame(feature_map)
    concepts = [c for c in df.columns if c != 'outcome_aki' and c != 'subject_id']
    present = sum(1 for f in features if feature_map.get(f) in df.columns)
    print(f'  合成表: {len(df)} 行 / {len(concepts)} 概念列 / 特征可定位: {present}/{len(features)}')

    # 3) 端到端评分（真实模型 + 真实学习中位数填补）
    res = mimic_validation.score_mimic(df, artifacts, feature_map,
                                       outcome_col='outcome_aki')
    y = df['outcome_aki'].astype(int).values
    from sklearn.metrics import roc_auc_score
    auc_raw = roc_auc_score(y, res['raw_probability'].values)
    auc_cal = roc_auc_score(y, res['calibrated_probability'].values)

    # 4) 输出（明确标注 SYNTHETIC）
    out_tab = ROOT / 'outputs' / 'tables'
    out_tab.mkdir(parents=True, exist_ok=True)
    out_df = pd.DataFrame({
        'subject_id': df['subject_id'],
        'outcome_aki': y,
        'raw_probability': res['raw_probability'].values,
        'calibrated_probability': res['calibrated_probability'].values,
    })
    out_df.to_csv(out_tab / 'mimic_pipeline_self_test.csv',
                  index=False, encoding='utf-8-sig')

    lines = [
        'MIMIC-IV 外部验证管线自测报告（合成数据 / SIMULATION ONLY）',
        '=' * 66,
        '声明：本结果由【合成数据】生成，仅用于验证管线端到端可用性，',
        '不是外部验证证据，不得作为外部验证结果写入报告。',
        '真实外部验证：PhysioNet 授权数据 -> scripts/mimic_extract.sql 提取',
        '  -> python scripts/mimic_validation.py --data <file> --outcome outcome_aki',
        '-' * 66,
        f'项目特征数            : {len(features)}',
        f'映射覆盖              : {len(mapped)}/{len(features)}',
        f'合成表可定位特征列     : {present}/{len(features)}',
        f'合成样本数            : {len(df)}',
        f'合成 AUC (raw)        : {auc_raw:.4f}  （管线自检阈值 >0.60）',
        f'合成 AUC (calibrated) : {auc_cal:.4f}',
        '说明：AUC 高仅代表合成数据内嵌了风险信号，与真实外部表现无关。',
    ]
    report = '\n'.join(lines) + '\n'
    (out_tab / 'mimic_pipeline_self_test_report.txt').write_text(
        report, encoding='utf-8')
    print(report)
    ok = auc_raw > 0.60 and present == len(features) and len(unmapped) == 0
    print('管线自检:', 'PASS' if ok else 'CHECK NEEDED')


if __name__ == '__main__':
    main()

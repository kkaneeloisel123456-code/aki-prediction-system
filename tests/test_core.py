# -*- coding: utf-8 -*-
"""Regression tests for shared config, cleaning, and web-input consistency."""

import os
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import RISK_HIGH, RISK_LOW, is_leakage
from src.data.prepare import (
    CLINICAL_RANGES,
    flag_impossible_values,
    normalize_columns,
    prepare_training_data,
)
from src.models.calibration import RISK_HIGH as CAL_RISK_HIGH
from src.models.calibration import RISK_LOW as CAL_RISK_LOW
from src.web_inputs import MODEL_FEATURE_INPUT_KEYS, OUTCOME_INPUT_KEYS


class LeakageRulesTest(unittest.TestCase):
    def test_identifier_and_target_excluded(self):
        self.assertTrue(is_leakage('姓名'))
        self.assertTrue(is_leakage('住院号'))
        self.assertTrue(is_leakage('AKI分组'))
        self.assertTrue(is_leakage('AKI分期'))

    def test_kdigo_and_outcomes_excluded(self):
        for col in ['术后48hSCr', '术后7deGFR', '术后48hUrea']:
            self.assertTrue(is_leakage(col), col)
        for col in ['总住院天数', '总住院费用', 'ICU住院天数', '术后通气时间']:
            self.assertTrue(is_leakage(col), col)

    def test_early_postop_features_kept(self):
        for col in ['术后β2MG', '术后Mb', '术后hsTn', '术后Lactate', '术后Urea']:
            self.assertFalse(is_leakage(col), col)


class ClinicalRangeTest(unittest.TestCase):
    def test_impossible_values_flagged_as_nan(self):
        df = pd.DataFrame({
            '术前K ': [4.0, 132.0, 3.5],
            '术后pH': [7.35, 0.35, 7.4],
            '术前SBP': [120.0, 1338.0, 130.0],
            'AKI分组': [0, 1, 0],
        })
        cleaned, flags = flag_impossible_values(df)
        self.assertEqual(len(flags), 3)
        self.assertTrue(np.isnan(cleaned.loc[1, '术前K ']))
        self.assertTrue(np.isnan(cleaned.loc[1, '术后pH']))
        self.assertTrue(np.isnan(cleaned.loc[1, '术前SBP']))

    def test_common_labs_have_ranges(self):
        for col in ['术前K', '术前CRP', '术前Hb', '术前PaO2', '术后pH']:
            self.assertIn(col, CLINICAL_RANGES)


class PrepareDataTest(unittest.TestCase):
    def test_normalize_columns_strips_spaces(self):
        df = pd.DataFrame({'术前PaO2 ': [100.0]})
        out = normalize_columns(df)
        self.assertIn('术前PaO2', out.columns)

    def test_prepare_drops_identifier_and_keeps_numeric(self):
        df = pd.DataFrame({
            '姓名': ['张三', '李四', '王五'],
            '手术类型': ['A', 'B', 'A'],
            '术前K': [4.0, 132.0, 3.5],
            '术前Scr': [80.0, 90.0, 85.0],
            'AKI分组': [0, 1, 0],
        })
        prep = prepare_training_data(df)
        self.assertEqual(len(prep['y']), 3)
        self.assertNotIn('姓名', prep['X'].columns)
        self.assertIn('术前K', prep['X'].columns)
        # Impossible value should be median-imputed, not left at 132.
        self.assertLess(prep['X']['术前K'].max(), 20)
        dummy_cols = [c for c in prep['X'].columns if c.startswith('手术类型_')]
        self.assertTrue(dummy_cols)
        self.assertTrue(np.issubdtype(prep['X'][dummy_cols[0]].dtype, np.unsignedinteger))


class WebInputConsistencyTest(unittest.TestCase):
    def test_no_outcome_keys_in_model_inputs(self):
        for key in OUTCOME_INPUT_KEYS:
            self.assertNotIn(key, MODEL_FEATURE_INPUT_KEYS)

    def test_all_model_features_have_form_inputs(self):
        feat_path = Path(__file__).resolve().parent.parent / 'app_data' / 'features.txt'
        if not feat_path.exists():
            self.skipTest('app_data/features.txt not generated yet')
        model_features = [
            line.strip() for line in feat_path.read_text(encoding='utf-8').splitlines()
            if line.strip()
        ]
        missing = [f for f in model_features if f not in MODEL_FEATURE_INPUT_KEYS]
        self.assertEqual(missing, [])
        extra = [f for f in MODEL_FEATURE_INPUT_KEYS if f not in model_features]
        self.assertEqual(extra, [])


class RiskThresholdConsistencyTest(unittest.TestCase):
    def test_single_source_of_thresholds(self):
        self.assertEqual(RISK_LOW, CAL_RISK_LOW)
        self.assertEqual(RISK_HIGH, CAL_RISK_HIGH)
        self.assertLess(RISK_LOW, RISK_HIGH)


class RepoConsistencyTest(unittest.TestCase):
    ROOT = Path(__file__).resolve().parent.parent

    def test_app_data_features_match_models(self):
        app = self.ROOT / 'app_data' / 'features.txt'
        models = self.ROOT / 'models' / 'selected_features.txt'
        if not app.exists() or not models.exists():
            self.skipTest('feature files not generated yet')
        app_feats = [l.strip() for l in app.read_text(encoding='utf-8').splitlines() if l.strip()]
        model_feats = [l.strip() for l in models.read_text(encoding='utf-8').splitlines() if l.strip()]
        self.assertEqual(app_feats, model_feats)

    def test_official_pairwise_csv_schema(self):
        path = self.ROOT / 'outputs' / 'figures' / 'pairwise_correlation_with_target.csv'
        if not path.exists():
            self.skipTest('pairwise CSV not generated yet')
        df = pd.read_csv(path, encoding='utf-8-sig')
        for col in ['Rank', 'Feature', 'Pearson_r', 'P_value', 'Direction', 'Significance']:
            self.assertIn(col, df.columns)

    def test_legacy_prediction_component_removed(self):
        self.assertFalse((self.ROOT / 'web' / 'components' / 'prediction.py').exists())


if __name__ == '__main__':
    unittest.main()

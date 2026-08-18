# -*- coding: utf-8 -*-
"""Wave 1 高级方法对比模块的轻量回归测试。"""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import run_advanced as ra


class AdvancedBenchmarkTest(unittest.TestCase):
    def test_selector_names_buildable(self):
        for name in ['top35', 'top20', 'rfecv', 'boruta_lite']:
            selector = ra.build_selector(name)
            self.assertIsNotNone(selector)

    def test_count_selected_features_after_fit(self):
        rng = np.random.RandomState(1)
        X = pd.DataFrame(rng.randn(60, 6), columns=[f'f{i}' for i in range(6)])
        y = pd.Series(rng.randint(0, 2, size=60))
        selector = ra.build_selector('top35')
        selector.fit(np.asarray(X), np.asarray(y))
        count = ra.count_selected_features(selector, X.iloc[:1])
        self.assertGreater(count, 0)
        self.assertLessEqual(count, 6)

    def test_blending_fits_and_returns_probability(self):
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.linear_model import LogisticRegression

        rng = np.random.RandomState(0)
        X = pd.DataFrame(rng.randn(80, 5), columns=[f'f{i}' for i in range(5)])
        y = pd.Series([0] * 40 + [1] * 40)
        blender = ra.BlendingClassifier(
            estimators=[
                LogisticRegression(max_iter=200, random_state=42),
                RandomForestClassifier(n_estimators=10, random_state=42),
            ],
            inner_cv=2,
            random_state=42,
        )
        blender.fit(np.asarray(X), np.asarray(y))
        proba = blender.predict_proba(np.asarray(X))
        self.assertEqual(proba.shape[1], 2)
        self.assertTrue(np.all((proba >= 0) & (proba <= 1)))


if __name__ == '__main__':
    unittest.main()

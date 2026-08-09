# -*- coding: utf-8 -*-
"""Wave 2 模块的轻量回归测试。"""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import run_wave2 as rw


class Wave2HelpersTest(unittest.TestCase):
    def test_prepare_raw_numeric_keeps_missing_values(self):
        df = pd.DataFrame({
            '姓名': ['a'],
            '手术类型': ['A'],
            '术前K': [np.nan],
            'AKI分组': [0],
        })
        X = rw.prepare_raw_numeric(df)
        self.assertIn('术前K', X.columns)
        self.assertTrue(X['术前K'].isna().any())

    def test_net_benefit_formula(self):
        y = np.array([1, 1, 0, 0])
        proba = np.array([0.9, 0.8, 0.3, 0.2])
        nb, tp, fp = rw.net_benefit(y, proba, 0.5)
        self.assertEqual((tp, fp), (2, 0))
        self.assertAlmostEqual(nb, 0.5)


if __name__ == '__main__':
    unittest.main()

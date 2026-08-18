# -*- coding: utf-8 -*-
"""Shared data-preparation helpers for all entry scripts.

The final pipeline used by ``run_clean.py``, ``run_evaluation.py`` and
``run_bonus.py`` lives here so that feature counts, leakage exclusions,
clinical range checks, and categorical encoding cannot drift between scripts.
"""

from __future__ import annotations

import os
import shutil
from typing import Dict, List, Tuple, TypedDict

import numpy as np
import pandas as pd

from src.config import TARGET, is_leakage


class PreparedData(TypedDict):
    """Return type of :func:`prepare_training_data`.

    Declared explicitly (instead of ``Dict[str, object]``) so callers keep
    precise types — otherwise ``for c in prep['leaked']`` raises
    "object is not iterable" type errors.
    """

    df_clean: pd.DataFrame
    X: pd.DataFrame
    y: pd.Series
    leaked: List[str]
    flags: pd.DataFrame
    impute_values: Dict[str, float]


# Clinically plausible bounds. Values outside these bounds are treated as
# entry errors and replaced with NaN (then median-imputed downstream).
CLINICAL_RANGES: Dict[str, Tuple[float, float]] = {
    '年龄': (18, 100),
    'APACHEII': (0, 50),
    '手术时间': (30, 1440),
    '术中失血量': (0, 5000),
    '术中晶体液量': (0, 10000),
    '术中胶体液量': (0, 10000),
    '术中尿量': (0, 10000),
    '术前SBP': (60, 250),
    '术后SBP': (60, 250),
    '术前DBP': (30, 130),
    '术后DBP': (30, 130),
    '术前K': (2.0, 7.0),
    '术后K': (2.0, 7.0),
    '术前Na': (115, 165),
    '术后Na': (115, 165),
    '术前Cl': (85, 130),
    '术后Cl': (85, 130),
    '术前Ca': (1.5, 3.5),
    '术后Ca': (1.5, 3.5),
    '术前Mg': (0.3, 3.0),
    '术后Mg': (0.3, 3.0),
    '术前P': (0.3, 4.0),
    '术后P': (0.3, 4.0),
    '术前GLU': (1.0, 40.0),
    '术后GLU': (1.0, 40.0),
    '术前pH': (7.0, 7.6),
    '术后pH': (7.0, 7.6),
    '术前PaO2': (30, 600),
    '术后PaO2': (30, 600),
    '术前PaCO2': (15, 150),
    '术后PaCO2': (15, 150),
    '术前BE': (-20, 20),
    '术后BE': (-20, 20),
    '术前HCO3': (10, 45),
    '术后HCO3': (10, 45),
    '术前Lactate': (0, 20),
    '术后Lactate': (0, 20),
    '术前CRP': (0, 300),
    '术后CRP': (0, 300),
    '术前WBC': (1, 50),
    '术后WBC': (1, 50),
    '术前Hb': (40, 220),
    '术后Hb': (40, 220),
    '术前PLT': (20, 800),
    '术后PLT': (20, 800),
    '术前Scr': (20, 500),
    '术后Scr': (20, 500),
    'ICUAdmSCr': (20, 500),
    '术前eGFR': (5, 200),
    '术后eGFR': (5, 200),
    'ICUAdmeGFR': (5, 200),
    '术前Urea': (1, 40),
    '术后Urea': (1, 40),
    '术前UA': (50, 1000),
    '术后UA': (50, 1000),
    '术前BNP': (0, 50000),
    '术后BNP': (0, 50000),
}


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Strip surrounding whitespace from every column name."""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df


def flag_impossible_values(
    df: pd.DataFrame,
    ranges: Dict[str, Tuple[float, float]] | None = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Replace physiologically impossible values with NaN.

    Returns the cleaned frame plus a report DataFrame with one row per
    out-of-range value (row index, column, value, min, max).
    """
    df = df.copy()
    ranges = ranges or CLINICAL_RANGES
    flags = []

    for col in df.columns:
        key = str(col).strip()
        if key not in ranges:
            continue
        lo, hi = ranges[key]
        s = pd.to_numeric(df[col], errors='coerce')
        invalid = (s < lo) | (s > hi)
        if invalid.any():
            for idx in df.index[invalid]:
                flags.append({
                    'row': idx,
                    'column': col,
                    'value': s.loc[idx],
                    'min': lo,
                    'max': hi,
                })
            df.loc[invalid, col] = np.nan

    flags_df = pd.DataFrame(flags)
    return df, flags_df


def prepare_training_data(
    df: pd.DataFrame,
    target: str = TARGET,
) -> PreparedData:
    """Shared preprocessing for training/evaluation scripts.

    Returns a dict with:
      - ``df_clean``: column names normalized, impossible values as NaN
      - ``X``: numeric matrix (global median-imputed), including one-hot dummies
      - ``y``: target Series
      - ``leaked``: excluded column names
      - ``flags``: clinical range violation report
      - ``impute_values``: median per numeric column
    """
    df = normalize_columns(df)
    df_clean, flags = flag_impossible_values(df)

    leaked = [c for c in df_clean.columns if is_leakage(c) and c != target]
    y = df_clean[target].copy()
    X = prepare_raw_numeric(df_clean, target=target)
    impute_values: Dict[str, float] = {
        str(col): float(val) for col, val in X.median().items()
    }
    X = X.fillna(X.median())

    return PreparedData(
        df_clean=df_clean,
        X=X,
        y=y,
        leaked=leaked,
        flags=flags,
        impute_values=impute_values,
    )


def prepare_raw_numeric(
    df: pd.DataFrame,
    target: str = TARGET,
) -> pd.DataFrame:
    """Return the candidate numeric matrix with missing values preserved.

    Validation pipelines that claim fold-contained imputation should use this
    matrix instead of ``prepare_training_data()['X']``, which is already
    median-imputed with full-data medians.
    """
    df = normalize_columns(df)
    df_clean, _ = flag_impossible_values(df)
    safe = [c for c in df_clean.columns if not is_leakage(c) and c != target]
    X = df_clean[safe].copy()

    cat_cols = [
        c for c in X.columns
        if (
            pd.api.types.is_object_dtype(X[c])
            or pd.api.types.is_string_dtype(X[c])
            or isinstance(X[c].dtype, pd.CategoricalDtype)
        )
    ]
    if cat_cols:
        X = pd.get_dummies(X, columns=cat_cols, drop_first=True, dtype=np.uint8)

    X = X.select_dtypes(include=[np.number])
    X = X.replace([np.inf, -np.inf], np.nan)
    return X


def save_app_data(
    voting,
    scaler,
    top_features: List[str],
    impute_values: Dict[str, float],
    calibrator=None,
    app_data_dir: str = 'app_data',
) -> None:
    """Write the deployment copies loaded by the FastAPI backend.

    Artifacts are written to a staging directory first and swapped in only
    after every file is complete, so an interrupted training run can never
    leave a mixed set (e.g. a new calibrator paired with an old model)
    that the backend would silently load on its next restart.
    """
    import json
    from pathlib import Path

    import joblib

    out = Path(app_data_dir)
    staging = out.with_name(out.name + '_staging')
    backup = out.with_name(out.name + '_backup')

    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    joblib.dump(voting, staging / 'final_model.joblib')
    joblib.dump(scaler, staging / 'scaler.joblib')
    if calibrator is not None:
        joblib.dump(calibrator, staging / 'calibrator.joblib')
    elif (out / 'calibrator.joblib').is_file():
        # Keep the previously deployed calibrator rather than dropping it.
        shutil.copy2(out / 'calibrator.joblib', staging / 'calibrator.joblib')
    (staging / 'features.txt').write_text('\n'.join(top_features), encoding='utf-8')
    medians = {k: float(v) for k, v in impute_values.items() if k in set(top_features)}
    (staging / 'impute_values.json').write_text(
        json.dumps(medians, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    # Preserve non-artifact files (e.g. the app_data README) across swaps.
    if out.is_dir():
        for extra in out.iterdir():
            if extra.is_file() and not (staging / extra.name).exists():
                shutil.copy2(extra, staging / extra.name)

    # Atomic swap: current -> backup, staging -> current, then drop backup.
    if backup.exists():
        shutil.rmtree(backup)
    if out.exists():
        os.replace(out, backup)
    try:
        os.replace(staging, out)
    except OSError:
        if backup.exists() and not out.exists():
            os.replace(backup, out)  # restore the previous deployment
        raise
    if backup.exists():
        shutil.rmtree(backup)

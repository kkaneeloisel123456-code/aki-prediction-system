"""
AKI Prediction Project — Model Training Module

Comprehensive training, evaluation, and tuning functions for binary classification
on an AKI (Acute Kidney Injury) dataset with ~420 rows and ~30-50 features.

Target column: `AKI分组`  (0 = negative, 1 = positive, ~30% prevalence)

Libraries: sklearn, xgboost, lightgbm, catboost, imbalanced-learn, joblib
"""

from __future__ import annotations

import logging
import os
import warnings
from typing import Any, Dict, List, Optional, Tuple, Union

import joblib
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.ensemble import (
    ExtraTreesClassifier,
    RandomForestClassifier,
)
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import (
    GridSearchCV,
    RandomizedSearchCV,
    StratifiedKFold,
    train_test_split,
)
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import LabelEncoder, OneHotEncoder, StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.metrics import roc_auc_score

# XGBoost / LightGBM / CatBoost
try:
    from xgboost import XGBClassifier
    _XGB_AVAILABLE = True
except ImportError:
    XGBClassifier = None  # type: ignore
    _XGB_AVAILABLE = False

try:
    from lightgbm import LGBMClassifier
    _LGBM_AVAILABLE = True
except ImportError:
    LGBMClassifier = None  # type: ignore
    _LGBM_AVAILABLE = False

try:
    from catboost import CatBoostClassifier
    _CATBOOST_AVAILABLE = True
except ImportError:
    CatBoostClassifier = None  # type: ignore
    _CATBOOST_AVAILABLE = False

# Optional: TabNet
try:
    from pytorch_tabnet.tab_model import TabNetClassifier
    _TABNET_AVAILABLE = True
except ImportError:
    TabNetClassifier = None  # type: ignore
    _TABNET_AVAILABLE = False

# Imbalanced-learn
try:
    from imblearn.over_sampling import ADASYN, SMOTE, RandomOverSampler
    from imblearn.under_sampling import RandomUnderSampler
    from imblearn.combine import SMOTEENN
    _IMBALANCED_AVAILABLE = True
except ImportError:
    _IMBALANCED_AVAILABLE = False

warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")
warnings.filterwarnings("ignore", category=FutureWarning)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 1. Train / Test Split
# ---------------------------------------------------------------------------

def train_test_split_data(
    X: Union[np.ndarray, pd.DataFrame],
    y: Union[np.ndarray, pd.Series],
    test_size: float = 0.2,
    stratify: bool = True,
    random_state: int = 42,
) -> Tuple:
    """Stratified train / test split.

    Parameters
    ----------
    X : array-like of shape (n_samples, n_features)
        Feature matrix.
    y : array-like of shape (n_samples,)
        Binary target.
    test_size : float, default=0.2
        Proportion of samples to hold out for testing.
    stratify : bool, default=True
        Whether to preserve class proportions in the split.
    random_state : int, default=42
        Random seed for reproducibility.

    Returns
    -------
    X_train, X_test, y_train, y_test
    """
    if stratify:
        stratify_arr = y
    else:
        stratify_arr = None

    return train_test_split(
        X,
        y,
        test_size=test_size,
        random_state=random_state,
        stratify=stratify_arr,
    )


# ---------------------------------------------------------------------------
# 2. Preprocessing Pipeline
# ---------------------------------------------------------------------------

def create_preprocessing_pipeline(
    numeric_features: List[str],
    categorical_features: Optional[List[str]] = None,
) -> Pipeline:
    """Create a scikit-learn Pipeline for numeric and categorical preprocessing.

    Numeric: ``SimpleImputer(strategy='median')`` → ``StandardScaler()``
    Categorical: ``OneHotEncoder(handle_unknown='ignore')``

    Parameters
    ----------
    numeric_features : list of str
        Column names of numeric features.
    categorical_features : list of str, optional
        Column names of categorical features.

    Returns
    -------
    sklearn.pipeline.Pipeline
    """
    from sklearn.compose import ColumnTransformer

    if categorical_features is None:
        categorical_features = []

    numeric_transformer = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )

    categorical_transformer = Pipeline(
        steps=[
            (
                "onehot",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
            )
        ]
    )

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric_transformer, numeric_features),
            ("cat", categorical_transformer, categorical_features),
        ]
    )

    return Pipeline(steps=[("preprocessor", preprocessor)])


# ---------------------------------------------------------------------------
# Helper: default param grids
# ---------------------------------------------------------------------------

_DEFAULT_PARAMS_LR = {"C": [0.001, 0.01, 0.1, 1, 10, 100]}
_DEFAULT_PARAMS_RF = {
    "n_estimators": [100, 200, 300, 500],
    "max_depth": [3, 5, 7, 10, None],
    "min_samples_split": [2, 5, 10],
    "min_samples_leaf": [1, 2, 4],
}
_DEFAULT_PARAMS_XGB = {
    "learning_rate": [0.01, 0.05, 0.1, 0.2],
    "max_depth": [3, 4, 5, 6, 7],
    "n_estimators": [100, 200, 300, 500],
    "subsample": [0.6, 0.8, 1.0],
    "colsample_bytree": [0.6, 0.8, 1.0],
}
_DEFAULT_PARAMS_LGBM = {
    "learning_rate": [0.01, 0.05, 0.1, 0.2],
    "num_leaves": [15, 31, 63, 127],
    "max_depth": [-1, 3, 5, 7, 10],
    "n_estimators": [100, 200, 300, 500],
    "subsample": [0.6, 0.8, 1.0],
    "colsample_bytree": [0.6, 0.8, 1.0],
    "min_child_samples": [5, 10, 20],
}
_DEFAULT_PARAMS_CATBOOST = {
    "learning_rate": [0.01, 0.05, 0.1, 0.2],
    "depth": [4, 6, 8, 10],
    "n_estimators": [100, 200, 300, 500],
    "subsample": [0.6, 0.8, 1.0],
    "colsample_bylevel": [0.6, 0.8, 1.0],
    "l2_leaf_reg": [1, 3, 5, 7, 9],
}
_DEFAULT_PARAMS_ET = {
    "n_estimators": [100, 200, 300, 500],
    "max_depth": [3, 5, 7, 10, None],
    "min_samples_split": [2, 5, 10],
    "min_samples_leaf": [1, 2, 4],
}
_DEFAULT_PARAMS_MLP = {
    "hidden_layer_sizes": [
        (64,),
        (128,),
        (64, 32),
        (128, 64),
        (128, 64, 32),
    ],
    "alpha": [0.0001, 0.001, 0.01],
    "learning_rate_init": [0.001, 0.01],
}


def _make_param_prefix(prefix: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Prefix param keys for use inside a Pipeline."""
    return {f"{prefix}__{k}": v for k, v in params.items()}


# ---------------------------------------------------------------------------
# 3. Logistic Regression
# ---------------------------------------------------------------------------

def train_logistic_regression(
    X_train: np.ndarray,
    X_test: np.ndarray,
    y_train: np.ndarray,
    y_test: np.ndarray,
    cv: int = 5,
    param_grid: Optional[Dict[str, Any]] = None,
    n_iter: int = 50,
) -> Dict[str, Any]:
    """Train logistic regression with L2 penalty, class_weight='balanced',
    and GridSearchCV over the C parameter.

    Returns
    -------
    dict with keys: model, predictions, probabilities, cv_scores
    """
    result: Dict[str, Any] = {
        "model": None,
        "predictions": None,
        "probabilities": None,
        "cv_scores": None,
        "best_params": None,
        "best_score": None,
    }
    try:
        if param_grid is None:
            param_grid = _DEFAULT_PARAMS_LR

        lr = LogisticRegression(
            penalty="l2",
            class_weight="balanced",
            solver="liblinear",
            max_iter=2000,
            random_state=42,
        )

        grid = GridSearchCV(
            lr,
            param_grid=param_grid,
            cv=cv,
            scoring="roc_auc",
            n_jobs=-1,
        )
        grid.fit(X_train, y_train)

        best_model = grid.best_estimator_
        preds = best_model.predict(X_test)
        probs = best_model.predict_proba(X_test)[:, 1]

        result["model"] = best_model
        result["predictions"] = preds
        result["probabilities"] = probs
        result["cv_scores"] = grid.cv_results_
        result["best_params"] = grid.best_params_
        result["best_score"] = grid.best_score_
        logger.info(
            "LogisticRegression done  best_score=%.4f  params=%s",
            grid.best_score_,
            grid.best_params_,
        )
    except Exception as exc:
        logger.error("LogisticRegression failed: %s", exc, exc_info=True)

    return result


# ---------------------------------------------------------------------------
# 4. Random Forest
# ---------------------------------------------------------------------------

def train_random_forest(
    X_train: np.ndarray,
    X_test: np.ndarray,
    y_train: np.ndarray,
    y_test: np.ndarray,
    cv: int = 5,
    param_grid: Optional[Dict[str, Any]] = None,
    n_iter: int = 50,
) -> Dict[str, Any]:
    """Train RandomForestClassifier with class_weight='balanced'
    and RandomizedSearchCV.

    Returns
    -------
    dict with keys: model, predictions, probabilities, cv_scores, feature_importance
    """
    result: Dict[str, Any] = {
        "model": None,
        "predictions": None,
        "probabilities": None,
        "cv_scores": None,
        "feature_importance": None,
        "best_params": None,
        "best_score": None,
    }
    try:
        if param_grid is None:
            param_grid = _DEFAULT_PARAMS_RF

        rf = RandomForestClassifier(
            class_weight="balanced",
            random_state=42,
        )

        search = RandomizedSearchCV(
            rf,
            param_distributions=param_grid,
            n_iter=n_iter,
            cv=cv,
            scoring="roc_auc",
            n_jobs=-1,
            random_state=42,
        )
        search.fit(X_train, y_train)

        best_model = search.best_estimator_
        preds = best_model.predict(X_test)
        probs = best_model.predict_proba(X_test)[:, 1]

        result["model"] = best_model
        result["predictions"] = preds
        result["probabilities"] = probs
        result["cv_scores"] = search.cv_results_
        result["feature_importance"] = best_model.feature_importances_
        result["best_params"] = search.best_params_
        result["best_score"] = search.best_score_
        logger.info(
            "RandomForest done  best_score=%.4f  params=%s",
            search.best_score_,
            search.best_params_,
        )
    except Exception as exc:
        logger.error("RandomForest failed: %s", exc, exc_info=True)

    return result


# ---------------------------------------------------------------------------
# 5. XGBoost
# ---------------------------------------------------------------------------

def train_xgboost(
    X_train: np.ndarray,
    X_test: np.ndarray,
    y_train: np.ndarray,
    y_test: np.ndarray,
    cv: int = 5,
    param_grid: Optional[Dict[str, Any]] = None,
    n_iter: int = 50,
) -> Dict[str, Any]:
    """Train XGBClassifier with ``scale_pos_weight`` for imbalance
    and RandomizedSearchCV.

    Returns
    -------
    dict with keys: model, predictions, probabilities, cv_scores, feature_importance
    """
    result: Dict[str, Any] = {
        "model": None,
        "predictions": None,
        "probabilities": None,
        "cv_scores": None,
        "feature_importance": None,
        "best_params": None,
        "best_score": None,
    }
    if not _XGB_AVAILABLE:
        logger.warning("XGBoost is not installed; skipping.")
        return result

    try:
        if param_grid is None:
            param_grid = _DEFAULT_PARAMS_XGB

        # Compute scale_pos_weight from training data
        pos_count = np.sum(y_train == 1)
        neg_count = np.sum(y_train == 0)
        scale_pos_weight = neg_count / max(pos_count, 1)

        xgb = XGBClassifier(
            scale_pos_weight=scale_pos_weight,
            use_label_encoder=False,
            eval_metric="logloss",
            random_state=42,
            verbosity=0,
        )

        search = RandomizedSearchCV(
            xgb,
            param_distributions=param_grid,
            n_iter=n_iter,
            cv=cv,
            scoring="roc_auc",
            n_jobs=-1,
            random_state=42,
        )
        search.fit(X_train, y_train)

        best_model = search.best_estimator_
        preds = best_model.predict(X_test)
        probs = best_model.predict_proba(X_test)[:, 1]

        result["model"] = best_model
        result["predictions"] = preds
        result["probabilities"] = probs
        result["cv_scores"] = search.cv_results_
        result["feature_importance"] = best_model.feature_importances_
        result["best_params"] = search.best_params_
        result["best_score"] = search.best_score_
        logger.info(
            "XGBoost done  best_score=%.4f  params=%s",
            search.best_score_,
            search.best_params_,
        )
    except Exception as exc:
        logger.error("XGBoost failed: %s", exc, exc_info=True)

    return result


# ---------------------------------------------------------------------------
# 6. LightGBM
# ---------------------------------------------------------------------------

def train_lightgbm(
    X_train: np.ndarray,
    X_test: np.ndarray,
    y_train: np.ndarray,
    y_test: np.ndarray,
    cv: int = 5,
    param_grid: Optional[Dict[str, Any]] = None,
    n_iter: int = 50,
) -> Dict[str, Any]:
    """Train LGBMClassifier with class_weight='balanced' and RandomizedSearchCV.

    Returns
    -------
    dict with keys: model, predictions, probabilities, cv_scores, feature_importance
    """
    result: Dict[str, Any] = {
        "model": None,
        "predictions": None,
        "probabilities": None,
        "cv_scores": None,
        "feature_importance": None,
        "best_params": None,
        "best_score": None,
    }
    if not _LGBM_AVAILABLE:
        logger.warning("LightGBM is not installed; skipping.")
        return result

    try:
        if param_grid is None:
            param_grid = _DEFAULT_PARAMS_LGBM

        lgbm = LGBMClassifier(
            class_weight="balanced",
            random_state=42,
            verbosity=-1,
        )

        search = RandomizedSearchCV(
            lgbm,
            param_distributions=param_grid,
            n_iter=n_iter,
            cv=cv,
            scoring="roc_auc",
            n_jobs=-1,
            random_state=42,
        )
        search.fit(X_train, y_train)

        best_model = search.best_estimator_
        preds = best_model.predict(X_test)
        probs = best_model.predict_proba(X_test)[:, 1]

        result["model"] = best_model
        result["predictions"] = preds
        result["probabilities"] = probs
        result["cv_scores"] = search.cv_results_
        result["feature_importance"] = best_model.feature_importances_
        result["best_params"] = search.best_params_
        result["best_score"] = search.best_score_
        logger.info(
            "LightGBM done  best_score=%.4f  params=%s",
            search.best_score_,
            search.best_params_,
        )
    except Exception as exc:
        logger.error("LightGBM failed: %s", exc, exc_info=True)

    return result


# ---------------------------------------------------------------------------
# 7. CatBoost
# ---------------------------------------------------------------------------

def train_catboost(
    X_train: np.ndarray,
    X_test: np.ndarray,
    y_train: np.ndarray,
    y_test: np.ndarray,
    cv: int = 5,
    param_grid: Optional[Dict[str, Any]] = None,
    n_iter: int = 50,
) -> Dict[str, Any]:
    """Train CatBoostClassifier with ``auto_class_weights`` and
    RandomizedSearchCV.

    Returns
    -------
    dict with keys: model, predictions, probabilities, cv_scores, feature_importance
    """
    result: Dict[str, Any] = {
        "model": None,
        "predictions": None,
        "probabilities": None,
        "cv_scores": None,
        "feature_importance": None,
        "best_params": None,
        "best_score": None,
    }
    if not _CATBOOST_AVAILABLE:
        logger.warning("CatBoost is not installed; skipping.")
        return result

    try:
        if param_grid is None:
            param_grid = _DEFAULT_PARAMS_CATBOOST

        cb = CatBoostClassifier(
            auto_class_weights="Balanced",
            random_seed=42,
            verbose=0,
        )

        search = RandomizedSearchCV(
            cb,
            param_distributions=param_grid,
            n_iter=n_iter,
            cv=cv,
            scoring="roc_auc",
            n_jobs=-1,
            random_state=42,
        )
        search.fit(X_train, y_train)

        best_model = search.best_estimator_
        preds = best_model.predict(X_test)
        probs = best_model.predict_proba(X_test)[:, 1]

        result["model"] = best_model
        result["predictions"] = preds
        result["probabilities"] = probs
        result["cv_scores"] = search.cv_results_
        result["feature_importance"] = best_model.feature_importances_
        result["best_params"] = search.best_params_
        result["best_score"] = search.best_score_
        logger.info(
            "CatBoost done  best_score=%.4f  params=%s",
            search.best_score_,
            search.best_params_,
        )
    except Exception as exc:
        logger.error("CatBoost failed: %s", exc, exc_info=True)

    return result


# ---------------------------------------------------------------------------
# 8. Extra Trees
# ---------------------------------------------------------------------------

def train_extra_trees(
    X_train: np.ndarray,
    X_test: np.ndarray,
    y_train: np.ndarray,
    y_test: np.ndarray,
    cv: int = 5,
    param_grid: Optional[Dict[str, Any]] = None,
    n_iter: int = 50,
) -> Dict[str, Any]:
    """Train ExtraTreesClassifier with class_weight='balanced'
    and RandomizedSearchCV.

    Returns
    -------
    dict with keys: model, predictions, probabilities, cv_scores, feature_importance
    """
    result: Dict[str, Any] = {
        "model": None,
        "predictions": None,
        "probabilities": None,
        "cv_scores": None,
        "feature_importance": None,
        "best_params": None,
        "best_score": None,
    }
    try:
        if param_grid is None:
            param_grid = _DEFAULT_PARAMS_ET

        et = ExtraTreesClassifier(
            class_weight="balanced",
            random_state=42,
        )

        search = RandomizedSearchCV(
            et,
            param_distributions=param_grid,
            n_iter=n_iter,
            cv=cv,
            scoring="roc_auc",
            n_jobs=-1,
            random_state=42,
        )
        search.fit(X_train, y_train)

        best_model = search.best_estimator_
        preds = best_model.predict(X_test)
        probs = best_model.predict_proba(X_test)[:, 1]

        result["model"] = best_model
        result["predictions"] = preds
        result["probabilities"] = probs
        result["cv_scores"] = search.cv_results_
        result["feature_importance"] = best_model.feature_importances_
        result["best_params"] = search.best_params_
        result["best_score"] = search.best_score_
        logger.info(
            "ExtraTrees done  best_score=%.4f  params=%s",
            search.best_score_,
            search.best_params_,
        )
    except Exception as exc:
        logger.error("ExtraTrees failed: %s", exc, exc_info=True)

    return result


# ---------------------------------------------------------------------------
# 9. MLP (sklearn neural network)
# ---------------------------------------------------------------------------

def train_mlp(
    X_train: np.ndarray,
    X_test: np.ndarray,
    y_train: np.ndarray,
    y_test: np.ndarray,
    cv: int = 5,
    param_grid: Optional[Dict[str, Any]] = None,
    n_iter: int = 50,
) -> Dict[str, Any]:
    """Train MLPClassifier (sklearn) with hyperparameter tuning.

    Returns
    -------
    dict with keys: model, predictions, probabilities, cv_scores
    """
    result: Dict[str, Any] = {
        "model": None,
        "predictions": None,
        "probabilities": None,
        "cv_scores": None,
        "best_params": None,
        "best_score": None,
    }
    try:
        if param_grid is None:
            param_grid = _DEFAULT_PARAMS_MLP

        mlp = MLPClassifier(
            max_iter=2000,
            early_stopping=True,
            random_state=42,
        )

        search = RandomizedSearchCV(
            mlp,
            param_distributions=param_grid,
            n_iter=n_iter,
            cv=cv,
            scoring="roc_auc",
            n_jobs=-1,
            random_state=42,
        )
        search.fit(X_train, y_train)

        best_model = search.best_estimator_
        preds = best_model.predict(X_test)
        probs = best_model.predict_proba(X_test)[:, 1]

        result["model"] = best_model
        result["predictions"] = preds
        result["probabilities"] = probs
        result["cv_scores"] = search.cv_results_
        result["best_params"] = search.best_params_
        result["best_score"] = search.best_score_
        logger.info(
            "MLP done  best_score=%.4f  params=%s",
            search.best_score_,
            search.best_params_,
        )
    except Exception as exc:
        logger.error("MLP failed: %s", exc, exc_info=True)

    return result


# ---------------------------------------------------------------------------
# 10. TabNet
# ---------------------------------------------------------------------------

def train_tabnet(
    X_train: np.ndarray,
    X_test: np.ndarray,
    y_train: np.ndarray,
    y_test: np.ndarray,
    max_epochs: int = 200,
    patience: int = 20,
    batch_size: int = 32,
) -> Dict[str, Any]:
    """Train TabNetClassifier (pytorch-tabnet).

    Falls back gracefully if the library is not installed.

    Returns
    -------
    dict with keys: model, predictions, probabilities
    """
    result: Dict[str, Any] = {
        "model": None,
        "predictions": None,
        "probabilities": None,
    }
    if not _TABNET_AVAILABLE:
        logger.warning(
            "pytorch_tabnet is not installed; skipping TabNet training. "
            "Install with: pip install pytorch-tabnet"
        )
        return result

    try:
        # TabNet expects 2D numpy arrays; ensure label encoding starts at 0
        le = LabelEncoder()
        y_train_enc = le.fit_transform(y_train)
        y_test_enc = le.transform(y_test)

        model = TabNetClassifier(
            n_d=32,
            n_a=32,
            n_steps=5,
            gamma=1.5,
            lambda_sparse=0.0,
            optimizer_fn="torch.optim.Adam",
            optimizer_params={"lr": 0.005, "weight_decay": 1e-5},
            scheduler_params={"step_size": 50, "gamma": 0.9},
            scheduler_fn="torch.optim.lr_scheduler.StepLR",
            mask_type="entmax",
        )

        model.fit(
            X_train,
            y_train_enc,
            eval_set=[(X_test, y_test_enc)],
            max_epochs=max_epochs,
            patience=patience,
            batch_size=batch_size,
            virtual_batch_size=16,
            num_workers=0,
            drop_last=False,
        )

        preds = model.predict(X_test)
        probs = model.predict_proba(X_test)[:, 1]

        # Decode predictions back to original labels if needed
        result["model"] = model
        result["predictions"] = preds
        result["probabilities"] = probs
        logger.info("TabNet training completed successfully.")
    except Exception as exc:
        logger.error("TabNet failed: %s", exc, exc_info=True)

    return result


# ---------------------------------------------------------------------------
# 11. Cross-validate a model
# ---------------------------------------------------------------------------

def cross_validate_model(
    model: BaseEstimator,
    X: np.ndarray,
    y: np.ndarray,
    cv: int = 5,
    scoring: Optional[List[str]] = None,
) -> Dict[str, str]:
    """Perform StratifiedKFold cross-validation and return mean +/- std
    for each metric.

    Parameters
    ----------
    model : sklearn-compatible estimator
    X : array-like
    y : array-like
    cv : int, default=5
        Number of folds.
    scoring : list of str, optional
        Metric names recognised by ``sklearn.model_selection.cross_validate``.
        Defaults to ``['accuracy','precision','recall','f1','roc_auc']``.

    Returns
    -------
    dict of ``{metric_name: "mean ± std"}``
    """
    if scoring is None:
        scoring = ["accuracy", "precision", "recall", "f1", "roc_auc"]

    from sklearn.model_selection import cross_validate as _cross_validate

    result: Dict[str, str] = {}
    try:
        skf = StratifiedKFold(n_splits=cv, shuffle=True, random_state=42)

        cv_results = _cross_validate(
            model,
            X,
            y,
            cv=skf,
            scoring=scoring,
            n_jobs=-1,
            error_score="raise",
        )

        for metric in scoring:
            key = f"test_{metric}"
            if key in cv_results:
                scores = cv_results[key]
                mean_val = np.mean(scores)
                std_val = np.std(scores)
                result[metric] = f"{mean_val:.4f} +/- {std_val:.4f}"
            else:
                result[metric] = "N/A"
    except Exception as exc:
        logger.error("Cross-validation failed: %s", exc, exc_info=True)
        for metric in scoring:
            result[metric] = f"error: {exc}"

    return result


# ---------------------------------------------------------------------------
# 12. Bootstrap evaluation (AUC confidence intervals)
# ---------------------------------------------------------------------------

def bootstrap_evaluate(
    model: BaseEstimator,
    X: np.ndarray,
    y: np.ndarray,
    n_iterations: int = 1000,
    random_seed: int = 42,
) -> Dict[str, float]:
    """Bootstrap resampling to compute AUC and its 95% confidence interval.

    Parameters
    ----------
    model : fitted sklearn-compatible estimator
    X : array-like
    y : array-like
    n_iterations : int, default=1000
        Number of bootstrap replicates.
    random_seed : int, default=42

    Returns
    -------
    dict with keys: mean_auc, ci_lower, ci_upper
    """
    result: Dict[str, float] = {
        "mean_auc": 0.0,
        "ci_lower": 0.0,
        "ci_upper": 0.0,
    }
    try:
        rng = np.random.default_rng(random_seed)
        n_samples = len(y)
        auc_scores = np.empty(n_iterations)

        for i in range(n_iterations):
            indices = rng.integers(0, n_samples, size=n_samples)
            if len(np.unique(y[indices])) < 2:
                auc_scores[i] = np.nan
                continue

            X_boot = X[indices]
            y_boot = y[indices]

            y_prob = model.predict_proba(X_boot)[:, 1]
            auc_scores[i] = roc_auc_score(y_boot, y_prob)

        valid_scores = auc_scores[~np.isnan(auc_scores)]
        if len(valid_scores) < 100:
            logger.warning(
                "Only %d / %d valid bootstrap samples; CI may be unreliable.",
                len(valid_scores),
                n_iterations,
            )

        mean_auc = float(np.mean(valid_scores))
        ci_lower = float(np.percentile(valid_scores, 2.5))
        ci_upper = float(np.percentile(valid_scores, 97.5))

        result["mean_auc"] = mean_auc
        result["ci_lower"] = ci_lower
        result["ci_upper"] = ci_upper
        logger.info(
            "Bootstrap AUC: %.4f  (95%% CI: %.4f – %.4f)",
            mean_auc,
            ci_lower,
            ci_upper,
        )
    except Exception as exc:
        logger.error("Bootstrap evaluation failed: %s", exc, exc_info=True)

    return result


# ---------------------------------------------------------------------------
# 13. Handle class imbalance
# ---------------------------------------------------------------------------

def handle_class_imbalance(
    X_train: np.ndarray,
    y_train: np.ndarray,
    method: str = "smote",
    random_state: int = 42,
) -> Tuple[np.ndarray, np.ndarray]:
    """Resample the training set to address class imbalance.

    Supported ``method`` values:

    - ``'smote'``        — SMOTE oversampling
    - ``'adasyn'``       — ADASYN adaptive oversampling
    - ``'random_over'``  — RandomOverSampler
    - ``'random_under'`` — RandomUnderSampler
    - ``'smoteenn'``     — SMOTE + Edited Nearest Neighbours (hybrid)

    Parameters
    ----------
    X_train : array-like
        Training features.
    y_train : array-like
        Training labels.
    method : str, default='smote'
        Resampling strategy name.
    random_state : int, default=42

    Returns
    -------
    X_resampled, y_resampled
    """
    if not _IMBALANCED_AVAILABLE:
        logger.warning(
            "imbalanced-learn is not installed; returning original data. "
            "Install with: pip install imbalanced-learn"
        )
        return X_train, y_train

    sampler_map = {
        "smote": SMOTE(random_state=random_state),
        "adasyn": ADASYN(random_state=random_state),
        "random_over": RandomOverSampler(random_state=random_state),
        "random_under": RandomUnderSampler(random_state=random_state),
        "smoteenn": SMOTEENN(random_state=random_state),
    }

    if method not in sampler_map:
        logger.warning(
            "Unknown imbalance method '%s'; falling back to SMOTE. "
            "Available: %s",
            method,
            list(sampler_map.keys()),
        )
        method = "smote"

    sampler = sampler_map[method]
    X_res, y_res = sampler.fit_resample(X_train, y_train)

    before = dict(zip(*np.unique(y_train, return_counts=True)))
    after = dict(zip(*np.unique(y_res, return_counts=True)))
    logger.info(
        "Resampling '%s': before=%s  after=%s", method, before, after
    )

    return X_res, y_res


# ---------------------------------------------------------------------------
# 14. Generic hyperparameter tuning
# ---------------------------------------------------------------------------

def hyperparameter_tuning(
    model: BaseEstimator,
    param_grid: Dict[str, Any],
    X_train: np.ndarray,
    y_train: np.ndarray,
    cv: int = 5,
    scoring: str = "roc_auc",
    n_iter: int = 50,
    random_state: int = 42,
) -> Dict[str, Any]:
    """Run RandomizedSearchCV with the given model and parameter grid.

    Parameters
    ----------
    model : sklearn-compatible estimator
    param_grid : dict
        Hyperparameter search space.
    X_train, y_train : training data.
    cv : int, default=5
    scoring : str, default='roc_auc'
    n_iter : int, default=50
    random_state : int, default=42

    Returns
    -------
    dict with keys: best_model, best_params, best_score
    """
    result: Dict[str, Any] = {
        "best_model": None,
        "best_params": None,
        "best_score": None,
    }
    try:
        search = RandomizedSearchCV(
            model,
            param_distributions=param_grid,
            n_iter=n_iter,
            cv=cv,
            scoring=scoring,
            n_jobs=-1,
            random_state=random_state,
        )
        search.fit(X_train, y_train)

        result["best_model"] = search.best_estimator_
        result["best_params"] = search.best_params_
        result["best_score"] = search.best_score_

        logger.info(
            "HP tuning  best_score=%.4f  params=%s",
            search.best_score_,
            search.best_params_,
        )
    except Exception as exc:
        logger.error("Hyperparameter tuning failed: %s", exc, exc_info=True)

    return result


# ---------------------------------------------------------------------------
# 15. Save / Load
# ---------------------------------------------------------------------------

def save_model(model: BaseEstimator, path: str) -> str:
    """Save a trained model to disk via ``joblib.dump``.

    Parameters
    ----------
    model : estimator
        Fitted sklearn-compatible model.
    path : str
        Destination file path (should end with ``.joblib`` or ``.pkl``).

    Returns
    -------
    str
        The absolute path the model was saved to.
    """
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    joblib.dump(model, path)
    logger.info("Model saved to %s", path)
    return os.path.abspath(path)


def load_model(path: str) -> Any:
    """Load a saved model from disk via ``joblib.load``.

    Parameters
    ----------
    path : str
        Path to the serialised model file.

    Returns
    -------
    estimator
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Model file not found: {path}")

    model = joblib.load(path)
    logger.info("Model loaded from %s", path)
    return model


# ---------------------------------------------------------------------------
# 16. Full orchestration — train all models
# ---------------------------------------------------------------------------

def run_full_model_training(
    X: np.ndarray,
    y: np.ndarray,
    output_dir: str = "models/",
    cv: int = 5,
    use_smote: bool = True,
    smote_method: str = "smote",
    n_iter: int = 50,
    test_size: float = 0.2,
    random_state: int = 42,
    verbose: bool = True,
) -> Dict[str, Dict[str, Any]]:
    """Orchestrate training of all available models.

    Steps
    -----
    1. Stratified train / test split.
    2. Optional SMOTE resampling on the training set.
    3. Train each model variant with hyperparameter tuning.
    4. Save each model to ``output_dir``.
    5. Aggregate and return results.

    Parameters
    ----------
    X : array-like of shape (n_samples, n_features)
        Full feature matrix.
    y : array-like of shape (n_samples,)
        Binary target.
    output_dir : str, default='models/'
        Directory where model artefacts are saved.
    cv : int, default=5
        Number of cross-validation folds for tuning.
    use_smote : bool, default=True
        Whether to apply resampling for class imbalance.
    smote_method : str, default='smote'
        Resampling method (see :func:`handle_class_imbalance`).
    n_iter : int, default=50
        Number of random-search iterations (where applicable).
    test_size : float, default=0.2
        Hold-out fraction for final evaluation.
    random_state : int, default=42
    verbose : bool, default=True
        If True, print summary table after training.

    Returns
    -------
    dict
        Nested dictionary keyed by model name; each value is the result dict
        from the corresponding ``train_*`` function.
    """
    if verbose:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        )

    results: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # 1. Split
    # ------------------------------------------------------------------
    logger.info("Splitting data (test_size=%.2f, stratify=True)", test_size)
    X_train, X_test, y_train, y_test = train_test_split_data(
        X, y, test_size=test_size, stratify=True, random_state=random_state
    )
    logger.info(
        "Train size: %d  |  Test size: %d  |  Train pos ratio: %.3f",
        len(X_train),
        len(X_test),
        y_train.mean(),
    )

    # ------------------------------------------------------------------
    # 2. Handle imbalance on the training fold
    # ------------------------------------------------------------------
    if use_smote and _IMBALANCED_AVAILABLE:
        logger.info("Applying '%s' resampling to training set ...", smote_method)
        X_train_res, y_train_res = handle_class_imbalance(
            X_train, y_train, method=smote_method, random_state=random_state
        )
    else:
        X_train_res, y_train_res = X_train, y_train
        if use_smote and not _IMBALANCED_AVAILABLE:
            logger.warning(
                "imbalanced-learn not installed; skipping resampling."
            )

    # ------------------------------------------------------------------
    # 3. Train each model
    # ------------------------------------------------------------------
    os.makedirs(output_dir, exist_ok=True)

    # --- Logistic Regression ---
    logger.info("=" * 60)
    logger.info("Training LogisticRegression ...")
    result_lr = train_logistic_regression(
        X_train_res, X_test, y_train_res, y_test, cv=cv, n_iter=n_iter
    )
    if result_lr["model"] is not None:
        save_model(result_lr["model"], os.path.join(output_dir, "logistic_regression.joblib"))
    results["LogisticRegression"] = result_lr

    # --- Random Forest ---
    logger.info("=" * 60)
    logger.info("Training RandomForest ...")
    result_rf = train_random_forest(
        X_train_res, X_test, y_train_res, y_test, cv=cv, n_iter=n_iter
    )
    if result_rf["model"] is not None:
        save_model(result_rf["model"], os.path.join(output_dir, "random_forest.joblib"))
    results["RandomForest"] = result_rf

    # --- XGBoost ---
    logger.info("=" * 60)
    logger.info("Training XGBoost ...")
    result_xgb = train_xgboost(
        X_train_res, X_test, y_train_res, y_test, cv=cv, n_iter=n_iter
    )
    if result_xgb["model"] is not None:
        save_model(result_xgb["model"], os.path.join(output_dir, "xgboost.joblib"))
    results["XGBoost"] = result_xgb

    # --- LightGBM ---
    logger.info("=" * 60)
    logger.info("Training LightGBM ...")
    result_lgbm = train_lightgbm(
        X_train_res, X_test, y_train_res, y_test, cv=cv, n_iter=n_iter
    )
    if result_lgbm["model"] is not None:
        save_model(result_lgbm["model"], os.path.join(output_dir, "lightgbm.joblib"))
    results["LightGBM"] = result_lgbm

    # --- CatBoost ---
    logger.info("=" * 60)
    logger.info("Training CatBoost ...")
    result_cb = train_catboost(
        X_train_res, X_test, y_train_res, y_test, cv=cv, n_iter=n_iter
    )
    if result_cb["model"] is not None:
        save_model(result_cb["model"], os.path.join(output_dir, "catboost.joblib"))
    results["CatBoost"] = result_cb

    # --- Extra Trees ---
    logger.info("=" * 60)
    logger.info("Training ExtraTrees ...")
    result_et = train_extra_trees(
        X_train_res, X_test, y_train_res, y_test, cv=cv, n_iter=n_iter
    )
    if result_et["model"] is not None:
        save_model(result_et["model"], os.path.join(output_dir, "extra_trees.joblib"))
    results["ExtraTrees"] = result_et

    # --- MLP ---
    logger.info("=" * 60)
    logger.info("Training MLP ...")
    result_mlp = train_mlp(
        X_train_res, X_test, y_train_res, y_test, cv=cv, n_iter=n_iter
    )
    if result_mlp["model"] is not None:
        save_model(result_mlp["model"], os.path.join(output_dir, "mlp.joblib"))
    results["MLP"] = result_mlp

    # --- TabNet ---
    logger.info("=" * 60)
    logger.info("Training TabNet ...")
    result_tabnet = train_tabnet(
        X_train_res, X_test, y_train_res, y_test
    )
    if result_tabnet["model"] is not None:
        save_model(result_tabnet["model"], os.path.join(output_dir, "tabnet.zip"))
    results["TabNet"] = result_tabnet

    # ------------------------------------------------------------------
    # 4. Summary
    # ------------------------------------------------------------------
    if verbose:
        _print_summary(results, y_test)

    return results


def _print_summary(
    results: Dict[str, Dict[str, Any]],
    y_test: np.ndarray,
) -> None:
    """Print a row-per-model comparison table."""
    from sklearn.metrics import (
        accuracy_score,
        precision_score,
        recall_score,
        f1_score,
        roc_auc_score,
    )

    header = f"{'Model':<22} {'AUC':<8} {'Acc':<8} {'Prec':<8} {'Recall':<8} {'F1':<8}"
    sep = "-" * len(header)
    print("\n" + sep)
    print(header)
    print(sep)

    for model_name, res in results.items():
        if res.get("probabilities") is None:
            print(f"{model_name:<22} {'SKIP':<8}")
            continue

        preds = res.get("predictions")
        probs = res.get("probabilities")

        if preds is None or len(preds) == 0:
            print(f"{model_name:<22} {'SKIP':<8}")
            continue

        try:
            auc = roc_auc_score(y_test, probs)
            acc = accuracy_score(y_test, preds)
            prec = precision_score(y_test, preds, zero_division=0)
            rec = recall_score(y_test, preds, zero_division=0)
            f1 = f1_score(y_test, preds, zero_division=0)
            print(
                f"{model_name:<22} {auc:<8.4f} {acc:<8.4f} {prec:<8.4f} "
                f"{rec:<8.4f} {f1:<8.4f}"
            )
        except Exception as exc:
            print(f"{model_name:<22} {'ERR':<8} ({exc})")

    print(sep + "\n")


# ---------------------------------------------------------------------------
# Convenience: __all__
# ---------------------------------------------------------------------------

__all__ = [
    "train_test_split_data",
    "create_preprocessing_pipeline",
    "train_logistic_regression",
    "train_random_forest",
    "train_xgboost",
    "train_lightgbm",
    "train_catboost",
    "train_extra_trees",
    "train_mlp",
    "train_tabnet",
    "cross_validate_model",
    "bootstrap_evaluate",
    "handle_class_imbalance",
    "hyperparameter_tuning",
    "save_model",
    "load_model",
    "run_full_model_training",
]

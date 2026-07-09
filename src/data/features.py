"""
AKI Prediction Project - Feature Engineering Module
LASSO selection, feature encoding, class imbalance handling, feature importance.
"""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import warnings
warnings.filterwarnings('ignore')

from sklearn.linear_model import LassoCV, LogisticRegression
from sklearn.preprocessing import StandardScaler, LabelEncoder, OneHotEncoder
from sklearn.feature_selection import SelectFromModel, RFE, mutual_info_classif
from sklearn.ensemble import RandomForestClassifier
from imblearn.over_sampling import SMOTE, ADASYN, RandomOverSampler
from imblearn.under_sampling import RandomUnderSampler
from imblearn.combine import SMOTEENN
import joblib

import sys
sys.path.append('..')
from src.utils.helpers import (
    logger, FIGURES_DIR, TABLES_DIR, MODELS_DIR,
    save_figure, save_table, get_numeric_columns, progress_bar
)


# ============================================
# LASSO Feature Selection
# ============================================
def lasso_feature_selection(X, y, cv=5, random_state=42, save_path=None):
    """
    Perform LASSO (L1 regularization) feature selection.

    Args:
        X: Feature matrix (should be scaled)
        y: Target variable
        cv: Cross-validation folds
        random_state: Random seed
        save_path: Path to save LASSO path plot

    Returns:
        selected_features: List of selected feature names
        lasso_model: Fitted LassoCV model
        feature_coefs: Dict of feature -> coefficient
    """
    logger.info("Running LASSO feature selection...")

    # Standardize features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    X_scaled = pd.DataFrame(X_scaled, columns=X.columns)

    # Fit LassoCV
    lasso = LassoCV(cv=cv, random_state=random_state, max_iter=5000)
    lasso.fit(X_scaled, y)

    # Get coefficients
    coef_df = pd.DataFrame({
        'feature': X.columns,
        'coefficient': lasso.coef_
    })
    coef_df = coef_df[coef_df['coefficient'] != 0].sort_values('coefficient', key=abs, ascending=False)

    selected_features = coef_df['feature'].tolist()
    logger.info(f"LASSO selected {len(selected_features)} features from {X.shape[1]}")

    # Plot LASSO path
    if save_path:
        fig, ax = plt.subplots(figsize=(10, 6))
        alphas = lasso.alphas_
        coef_paths = lasso.path(X_scaled, y, alphas=lasso.alphas_)[1].T
        for i in range(min(30, coef_paths.shape[1])):
            ax.plot(alphas, coef_paths[:, i], alpha=0.3)
        ax.axvline(lasso.alpha_, color='red', linestyle='--', label=f'Best alpha: {lasso.alpha_:.4f}')
        ax.set_xscale('log')
        ax.set_xlabel('Alpha (log scale)')
        ax.set_ylabel('Coefficients')
        ax.set_title('LASSO Regularization Path')
        ax.legend()
        save_figure(fig, 'lasso_path.png')

    # Plot coefficient importance
    fig, ax = plt.subplots(figsize=(10, max(6, len(coef_df) * 0.3)))
    colors = ['#e74c3c' if c < 0 else '#2ecc71' for c in coef_df['coefficient']]
    ax.barh(range(len(coef_df)), coef_df['coefficient'].values, color=colors)
    ax.set_yticks(range(len(coef_df)))
    ax.set_yticklabels(coef_df['feature'].values)
    ax.axvline(0, color='black', linewidth=0.5)
    ax.set_xlabel('LASSO Coefficient')
    ax.set_title('LASSO Feature Coefficients')
    ax.invert_yaxis()
    save_figure(fig, 'lasso_coefficients.png')

    return selected_features, lasso, dict(zip(coef_df['feature'], coef_df['coefficient']))


# ============================================
# Feature Encoding
# ============================================
def encode_categorical_features(df, categorical_cols, method='label'):
    """
    Encode categorical features.

    Args:
        df: DataFrame
        categorical_cols: List of categorical column names
        method: 'label' for LabelEncoder, 'onehot' for OneHotEncoder

    Returns:
        df_encoded: Encoded DataFrame
        encoders: Dict of column -> encoder object
    """
    df_encoded = df.copy()
    encoders = {}

    for col in categorical_cols:
        if col not in df.columns:
            continue

        if method == 'label':
            le = LabelEncoder()
            df_encoded[col] = le.fit_transform(df[col].astype(str))
            encoders[col] = le
            logger.info(f"Label encoded '{col}': {dict(zip(le.classes_, le.transform(le.classes_)))}")

        elif method == 'onehot':
            # Create dummies and drop first to avoid multicollinearity
            dummies = pd.get_dummies(df[col], prefix=col, drop_first=True)
            df_encoded = pd.concat([df_encoded.drop(columns=[col]), dummies], axis=1)
            encoders[col] = dummies.columns.tolist()
            logger.info(f"OneHot encoded '{col}': created {len(dummies.columns)} dummy variables")

    return df_encoded, encoders


def encode_binary_features(df, binary_cols):
    """
    Ensure binary columns are 0/1 encoded.
    Maps 1/2 → 0/1 for gender-like columns, handles other mappings.
    """
    df_encoded = df.copy()
    for col in binary_cols:
        if col not in df.columns:
            continue
        unique_vals = sorted(df[col].dropna().unique())
        if unique_vals == [1, 2]:
            df_encoded[col] = df[col].map({1: 1, 2: 0})  # Male=1, Female=0
            logger.info(f"Binary column '{col}' confirmed 0/1: 1→1, 2→0")
    return df_encoded


# ============================================
# Class Imbalance Handling
# ============================================
def handle_imbalance(X, y, method='smote', random_state=42):
    """
    Handle class imbalance using various resampling techniques.

    Args:
        X: Feature matrix
        y: Target variable
        method: 'smote', 'adasyn', 'random_over', 'random_under', 'smoteenn'
        random_state: Random seed

    Returns:
        X_resampled, y_resampled
    """
    logger.info(f"Handling class imbalance with: {method}")
    logger.info(f"Before: {dict(y.value_counts())}")

    samplers = {
        'smote': SMOTE(random_state=random_state),
        'adasyn': ADASYN(random_state=random_state),
        'random_over': RandomOverSampler(random_state=random_state),
        'random_under': RandomUnderSampler(random_state=random_state),
        'smoteenn': SMOTEENN(random_state=random_state),
    }

    if method not in samplers:
        logger.warning(f"Unknown method '{method}'. Using SMOTE.")
        method = 'smote'

    sampler = samplers[method]
    X_resampled, y_resampled = sampler.fit_resample(X, y)

    logger.info(f"After: {dict(pd.Series(y_resampled).value_counts())}")

    return X_resampled, y_resampled


# ============================================
# Feature Importance (Multiple Methods)
# ============================================
def compute_feature_importance_rf(X, y, random_state=42):
    """Compute feature importance using Random Forest."""
    rf = RandomForestClassifier(n_estimators=200, random_state=random_state, n_jobs=-1)
    rf.fit(X, y)

    importance_df = pd.DataFrame({
        'feature': X.columns,
        'importance': rf.feature_importances_
    }).sort_values('importance', ascending=False)

    return importance_df


def compute_mutual_information(X, y, random_state=42):
    """Compute mutual information between features and target."""
    mi = mutual_info_classif(X, y, random_state=random_state)

    mi_df = pd.DataFrame({
        'feature': X.columns,
        'mutual_information': mi
    }).sort_values('mutual_information', ascending=False)

    return mi_df


def compute_univariate_importance(X, y):
    """Compute univariate feature importance (OR and p-value from logistic regression)."""
    results = []

    for col in X.columns:
        try:
            X_col = X[[col]].fillna(X[col].median())
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X_col)

            lr = LogisticRegression(penalty=None, max_iter=1000)
            lr.fit(X_scaled, y)

            # Odds ratio per standard deviation
            or_val = np.exp(lr.coef_[0][0])

            # P-value from statsmodels-like approach (using sklearn coef_)
            from scipy import stats
            import statsmodels.api as sm
            X_sm = sm.add_constant(X_scaled)
            model_sm = sm.Logit(y, X_sm)
            result = model_sm.fit(disp=0)
            p_val = result.pvalues[1]

            results.append({
                'feature': col,
                'odds_ratio': round(or_val, 4),
                'p_value': round(p_val, 4)
            })
        except Exception as e:
            results.append({
                'feature': col,
                'odds_ratio': np.nan,
                'p_value': np.nan
            })

    return pd.DataFrame(results).sort_values('p_value')


# ============================================
# Combined Feature Selection
# ============================================
def select_features_combined(X, y,
                              lasso_cv=5,
                              rf_threshold=0.01,
                              mi_top_k=30,
                              clinical_features=None,
                              random_state=42):
    """
    Combined feature selection using LASSO + RF + Mutual Information + Clinical input.

    Args:
        clinical_features: List of clinically important features to always include

    Returns:
        final_features: List of final selected features
        selection_summary: DataFrame with selection status for all features
    """
    logger.info("Running combined feature selection...")
    clinical_features = clinical_features or []

    # Standardize
    scaler = StandardScaler()
    X_scaled = pd.DataFrame(scaler.fit_transform(X), columns=X.columns)

    # 1. LASSO selection
    lasso_features, _, _ = lasso_feature_selection(X_scaled, y, cv=lasso_cv, random_state=random_state)

    # 2. Random Forest importance
    rf_importance = compute_feature_importance_rf(X_scaled, y, random_state)
    rf_features = rf_importance[rf_importance['importance'] >= rf_threshold]['feature'].tolist()

    # 3. Mutual Information
    mi_importance = compute_mutual_information(X_scaled, y, random_state)
    mi_features = mi_importance.head(mi_top_k)['feature'].tolist()

    # 4. Univariate (p < 0.05)
    uv_df = compute_univariate_importance(X_scaled, y)
    uv_features = uv_df[uv_df['p_value'] < 0.05]['feature'].tolist()

    # Combine: selected by >=2 methods OR clinically important
    all_features = X.columns.tolist()
    selection_summary = pd.DataFrame({'feature': all_features})
    selection_summary['LASSO'] = selection_summary['feature'].isin(lasso_features)
    selection_summary['RF'] = selection_summary['feature'].isin(rf_features)
    selection_summary['MI'] = selection_summary['feature'].isin(mi_features)
    selection_summary['Univariate'] = selection_summary['feature'].isin(uv_features)
    selection_summary['Clinical'] = selection_summary['feature'].isin(clinical_features)
    selection_summary['n_methods'] = selection_summary[['LASSO', 'RF', 'MI', 'Univariate']].sum(axis=1)
    selection_summary['selected'] = (selection_summary['n_methods'] >= 2) | selection_summary['Clinical']

    final_features = selection_summary[selection_summary['selected']]['feature'].tolist()

    logger.info(f"Combined selection: {len(final_features)} features out of {len(all_features)}")
    logger.info(f"  LASSO: {len(lasso_features)}, RF: {len(rf_features)}, "
                f"MI: {len(mi_features)}, UV: {len(uv_features)}, "
                f"Clinical: {len(clinical_features)}")

    # Save selection summary
    save_table(selection_summary, 'feature_selection_summary.csv')

    # Plot
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))

    # RF importance
    top_rf = rf_importance.head(20)
    axes[0].barh(range(len(top_rf)), top_rf['importance'].values, color='#3498db')
    axes[0].set_yticks(range(len(top_rf)))
    axes[0].set_yticklabels(top_rf['feature'].values, fontsize=8)
    axes[0].set_title('Random Forest Feature Importance')
    axes[0].invert_yaxis()

    # MI
    top_mi = mi_importance.head(20)
    axes[1].barh(range(len(top_mi)), top_mi['mutual_information'].values, color='#2ecc71')
    axes[1].set_yticks(range(len(top_mi)))
    axes[1].set_yticklabels(top_mi['feature'].values, fontsize=8)
    axes[1].set_title('Mutual Information')
    axes[1].invert_yaxis()

    # Venn-like: selection method overlap
    methods = ['LASSO', 'RF\n(imp>0.01)', 'MI\n(Top30)', 'Univariate\n(p<0.05)']
    counts = [sum(selection_summary['LASSO']), sum(selection_summary['RF']),
              sum(selection_summary['MI']), sum(selection_summary['Univariate'])]
    bars = axes[2].bar(methods, counts, color=['#e74c3c', '#3498db', '#2ecc71', '#f39c12'])
    axes[2].set_ylabel('Number of Features')
    axes[2].set_title('Features Selected by Each Method')
    for bar, count in zip(bars, counts):
        axes[2].text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5, str(count),
                     ha='center', fontweight='bold')

    plt.tight_layout()
    save_figure(fig, 'feature_selection_overview.png')

    return final_features, selection_summary


# ============================================
# Feature Engineering Pipeline
# ============================================
def run_full_feature_engineering(df, target='AKI分组',
                                  categorical_cols=None,
                                  clinical_features=None,
                                  imbalance_method='smote',
                                  random_state=42):
    """
    Run the full feature engineering pipeline.

    Args:
        df: Cleaned DataFrame
        target: Target column name
        categorical_cols: List of categorical columns to encode
        clinical_features: List of clinically must-include features
        imbalance_method: Method for handling class imbalance
        random_state: Random seed

    Returns:
        X_final: Final feature matrix
        y: Target variable
        feature_list: List of selected features
        encoders: Dict of fitted encoders
        scaler: Fitted StandardScaler
    """
    logger.info("=" * 60)
    logger.info("Starting Feature Engineering Pipeline")
    logger.info("=" * 60)

    # Separate target
    y = df[target].copy()
    X = df.drop(columns=[target, 'AKI分期'], errors='ignore')

    categorical_cols = categorical_cols or []
    # Remove target from categorical if present
    categorical_cols = [c for c in categorical_cols if c in X.columns]

    # 1. Encode categorical features
    if categorical_cols:
        X, encoders = encode_categorical_features(X, categorical_cols, method='label')
    else:
        encoders = {}

    # 2. Ensure only numeric columns
    X = X.select_dtypes(include=[np.number])

    # 3. Handle remaining NaN (should be minimal after cleaning)
    X = X.fillna(X.median())

    # 4. Feature selection
    clinical_features = [c for c in (clinical_features or []) if c in X.columns]
    selected_features, selection_summary = select_features_combined(
        X, y, clinical_features=clinical_features, random_state=random_state
    )

    if len(selected_features) == 0:
        logger.warning("No features selected! Using all features.")
        selected_features = X.columns.tolist()

    X_selected = X[selected_features]

    # 5. Scale features
    scaler = StandardScaler()
    X_scaled = pd.DataFrame(
        scaler.fit_transform(X_selected),
        columns=selected_features,
        index=X_selected.index
    )

    # 6. Handle class imbalance (only on training data - caller should handle split)
    X_balanced, y_balanced = handle_imbalance(X_scaled, y, method=imbalance_method, random_state=random_state)

    # Save feature list
    with open(TABLES_DIR / 'final_feature_list.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(selected_features))

    logger.info(f"Feature engineering complete. Final features: {len(selected_features)}")
    logger.info(f"After balancing: {X_balanced.shape[0]} samples")

    return X_balanced, y_balanced, selected_features, encoders, scaler


if __name__ == '__main__':
    print("Feature engineering module loaded successfully.")

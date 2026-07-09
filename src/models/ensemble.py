"""
AKI Prediction Project - Model Ensemble Module
Stacking, Voting, and weighted model combination.
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import VotingClassifier, StackingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.metrics import roc_auc_score
import joblib
import warnings
warnings.filterwarnings('ignore')

import sys
sys.path.append('..')
from src.utils.helpers import logger, MODELS_DIR, save_figure
import matplotlib.pyplot as plt


def create_voting_ensemble(models_dict, weights=None, voting='soft'):
    """
    Create a voting ensemble from multiple trained models.

    Args:
        models_dict: {name: model} dict
        weights: List of weights for each model (best models get higher weight)
        voting: 'soft' for probability averaging, 'hard' for majority vote

    Returns:
        VotingClassifier
    """
    estimators = [(name, model) for name, model in models_dict.items()
                  if hasattr(model, 'predict_proba')]

    if len(estimators) < 2:
        logger.warning("Need at least 2 models with predict_proba for voting ensemble.")
        return None

    if weights is None:
        weights = [1.0] * len(estimators)

    ensemble = VotingClassifier(
        estimators=estimators,
        voting=voting,
        weights=weights,
        n_jobs=-1
    )

    logger.info(f"Created {voting} voting ensemble with {len(estimators)} models")
    return ensemble


def create_stacking_ensemble(base_models_dict, cv=5, random_state=42):
    """
    Create a stacking ensemble using Logistic Regression as meta-learner.

    Args:
        base_models_dict: {name: model} dict for base learners
        cv: Cross-validation folds for meta-feature generation
        random_state: Random seed

    Returns:
        StackingClassifier
    """
    estimators = [(name, model) for name, model in base_models_dict.items()
                  if hasattr(model, 'predict_proba')]

    if len(estimators) < 2:
        logger.warning("Need at least 2 base models for stacking.")
        return None

    meta_learner = LogisticRegression(
        penalty='l2', C=1.0, class_weight='balanced',
        max_iter=1000, random_state=random_state
    )

    ensemble = StackingClassifier(
        estimators=estimators,
        final_estimator=meta_learner,
        cv=StratifiedKFold(n_splits=cv, shuffle=True, random_state=random_state),
        stack_method='predict_proba',
        n_jobs=-1
    )

    logger.info(f"Created stacking ensemble: {len(estimators)} base models + LR meta-learner")
    return ensemble


def evaluate_ensemble(ensemble, X_train, X_test, y_train, y_test, ensemble_name='Ensemble'):
    """
    Evaluate ensemble model and compare with individual models.
    """
    # Train ensemble
    ensemble.fit(X_train, y_train)

    # Predict
    y_prob = ensemble.predict_proba(X_test)[:, 1]
    y_pred = ensemble.predict(X_test)

    # Metrics
    from src.models.evaluate import compute_all_metrics
    metrics = compute_all_metrics(y_test, y_pred, y_prob)

    logger.info(f"{ensemble_name} Results:")
    for metric, value in metrics.items():
        logger.info(f"  {metric}: {value:.4f}")

    return ensemble, metrics


def compare_individual_vs_ensemble(models_dict, X_train, X_test, y_train, y_test,
                                     ensemble_method='both', save_fig=True):
    """
    Compare individual model AUCs with voting and stacking ensembles.
    """
    results = {}

    # Evaluate individual models
    for name, model in models_dict.items():
        if not hasattr(model, 'predict_proba'):
            continue
        try:
            model.fit(X_train, y_train)
            y_prob = model.predict_proba(X_test)[:, 1]
            auc = roc_auc_score(y_test, y_prob)
            results[name] = {'type': 'Individual', 'auc': auc}
        except Exception as e:
            logger.warning(f"Failed to evaluate {name}: {e}")

    # Voting ensemble
    if ensemble_method in ['voting', 'both']:
        try:
            # Use top 3 models for voting
            top_models = sorted(results.items(), key=lambda x: x[1]['auc'], reverse=True)[:3]
            top_dict = {name: models_dict[name] for name, _ in top_models}

            voting_ens = create_voting_ensemble(top_dict, voting='soft')
            if voting_ens:
                voting_ens.fit(X_train, y_train)
                y_prob = voting_ens.predict_proba(X_test)[:, 1]
                auc = roc_auc_score(y_test, y_prob)
                results['Voting (Top3)'] = {'type': 'Ensemble', 'auc': auc}
        except Exception as e:
            logger.warning(f"Voting ensemble failed: {e}")

    # Stacking ensemble
    if ensemble_method in ['stacking', 'both']:
        try:
            stacking_ens = create_stacking_ensemble(models_dict, cv=5)
            if stacking_ens:
                stacking_ens.fit(X_train, y_train)
                y_prob = stacking_ens.predict_proba(X_test)[:, 1]
                auc = roc_auc_score(y_test, y_prob)
                results['Stacking'] = {'type': 'Ensemble', 'auc': auc}
        except Exception as e:
            logger.warning(f"Stacking ensemble failed: {e}")

    # Plot comparison
    if save_fig:
        plot_ensemble_comparison(results)

    return results


def plot_ensemble_comparison(results, save_name='ensemble_comparison.png'):
    """Bar chart comparing individual models vs ensemble."""
    fig, ax = plt.subplots(figsize=(10, 6))

    names = list(results.keys())
    aucs = [results[n]['auc'] for n in names]
    types = [results[n]['type'] for n in names]

    colors = ['#e74c3c' if t == 'Ensemble' else '#3498db' for t in types]

    bars = ax.barh(range(len(names)), aucs, color=colors, edgecolor='white')
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names)
    ax.set_xlabel('AUC-ROC', fontsize=12)
    ax.set_title('Individual Models vs Ensemble Comparison', fontsize=14, fontweight='bold')
    ax.invert_yaxis()

    # Add value labels
    for bar, auc in zip(bars, aucs):
        ax.text(bar.get_width() + 0.002, bar.get_y() + bar.get_height() / 2,
                f'{auc:.4f}', va='center', fontsize=9, fontweight='bold')

    # Legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor='#3498db', label='Individual Model'),
        Patch(facecolor='#e74c3c', label='Ensemble'),
    ]
    ax.legend(handles=legend_elements, loc='lower right')

    plt.tight_layout()
    save_figure(fig, save_name)

    return fig


def weighted_model_averaging(model_probs_dict, weights=None):
    """
    Weighted average of model probabilities.

    Args:
        model_probs_dict: {model_name: probabilities_array}
        weights: Dict of model weights (higher = more important)

    Returns:
        Averaged probabilities
    """
    if weights is None:
        weights = {name: 1.0 for name in model_probs_dict}

    total_weight = sum(weights.values())
    norm_weights = {k: v / total_weight for k, v in weights.items()}

    avg_prob = np.zeros_like(list(model_probs_dict.values())[0])
    for name, probs in model_probs_dict.items():
        avg_prob += norm_weights.get(name, 0) * probs

    return avg_prob


def find_optimal_model_weights(model_probs_dict, y_true):
    """
    Find optimal weights for model averaging using simple grid search.
    Maximizes AUC.
    """
    model_names = list(model_probs_dict.keys())
    n_models = len(model_names)

    if n_models < 2:
        return {model_names[0]: 1.0}

    best_weights = None
    best_auc = 0

    # Simple grid search over weight combinations
    # For efficiency, only tune top 3 models
    top_models = model_names[:min(3, n_models)]

    for w1 in np.linspace(0.3, 1.0, 8):
        for w2 in np.linspace(0.1, 0.7, 7):
            if len(top_models) > 2:
                w3 = 1.0 - w1 - w2
                if w3 < 0.05:
                    continue
                weights = {top_models[0]: w1, top_models[1]: w2, top_models[2]: w3}
            else:
                w3 = 1.0 - w1
                weights = {top_models[0]: w1, top_models[1]: w3}

            # Apply weights to remaining models
            for name in model_names:
                if name not in weights:
                    weights[name] = 0

            avg_prob = weighted_model_averaging(model_probs_dict, weights)
            auc = roc_auc_score(y_true, avg_prob)

            if auc > best_auc:
                best_auc = auc
                best_weights = weights.copy()

    logger.info(f"Optimal weights found. AUC: {best_auc:.4f}")
    for name, w in best_weights.items():
        logger.info(f"  {name}: {w:.3f}")

    return best_weights


if __name__ == '__main__':
    print("Ensemble module loaded successfully.")

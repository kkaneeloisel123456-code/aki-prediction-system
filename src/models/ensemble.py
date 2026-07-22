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


# ====================================================================
# Phase 2: Full Ensemble Pipeline
# ====================================================================
def run_full_ensemble_pipeline(X, y, models_dict, feature_names=None, cv=5,
                                n_bootstrap=500, random_state=42, output_dir=None):
    """
    Comprehensive ensemble pipeline for Phase 2.

    Steps:
      1. Rank base models by CV AUC, select top 3
      2. Grid search meta-learner (LR, Ridge, RF final estimator)
      3. Build Voting, Stacking, and Weighted Avg ensembles
      4. Evaluate all methods with bootstrap CI
      5. Generate comparison visualization

    Args:
        X: Feature matrix (numpy array or DataFrame)
        y: Target array
        models_dict: {model_name: model_instance}
        feature_names: Optional list of feature names
        cv: Cross-validation folds
        n_bootstrap: Bootstrap iterations for CI
        random_state: Random seed
        output_dir: Directory for saving outputs

    Returns:
        results: Dict with ensemble models, metrics, and comparison
    """
    from sklearn.model_selection import train_test_split, StratifiedKFold
    from sklearn.linear_model import LogisticRegression, RidgeClassifier
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import roc_auc_score, brier_score_loss
    from src.models.cross_validate import run_stratified_kfold_cv

    # Ensure numpy arrays
    if hasattr(X, 'values'):
        X_arr = X.values
    else:
        X_arr = X
    if hasattr(y, 'values'):
        y_arr = y.values
    else:
        y_arr = y

    # ---- Step 1: Rank base models by CV AUC ----
    print("\n" + "=" * 70)
    print("  Stacking Ensemble Pipeline | Phase 2")
    print("=" * 70)
    print(f"  Data: N={len(X_arr)}, Features={X_arr.shape[1]}")
    print(f"  Models: {len(models_dict)}, CV={cv}")

    # Quick 5-fold CV to rank models
    cv_scores = {}
    skf = StratifiedKFold(n_splits=cv, shuffle=True, random_state=random_state)
    for name, model in models_dict.items():
        try:
            scores = []
            for tr_idx, val_idx in skf.split(X_arr, y_arr):
                model_clone = type(model)(**{k: v for k, v in model.get_params().items()
                                            if k not in ['random_state', 'random_seed']})
                # Set random state if available
                if 'random_state' in model.get_params():
                    model_clone.set_params(random_state=random_state)
                model_clone.fit(X_arr[tr_idx], y_arr[tr_idx])
                if hasattr(model_clone, 'predict_proba'):
                    prob = model_clone.predict_proba(X_arr[val_idx])[:, 1]
                else:
                    prob = model_clone.decision_function(X_arr[val_idx])
                    from sklearn.preprocessing import MinMaxScaler
                    prob = MinMaxScaler().fit_transform(prob.reshape(-1, 1)).ravel()
                scores.append(roc_auc_score(y_arr[val_idx], prob))
            cv_scores[name] = np.mean(scores)
        except Exception as e:
            print(f"  [WARN] {name} CV failed: {e}")
            cv_scores[name] = 0

    # Select top 3
    ranked = sorted(cv_scores.items(), key=lambda x: x[1], reverse=True)
    top3_names = [n for n, _ in ranked[:3]]
    top3_models = {n: models_dict[n] for n in top3_names}
    print(f"  Top 3 Base Models: {top3_names}")

    # Train-test split for ensemble evaluation
    X_tr, X_te, y_tr, y_te = train_test_split(
        X_arr, y_arr, test_size=0.2, stratify=y_arr, random_state=random_state
    )

    # ---- Step 2: Grid search meta-learner for Stacking ----
    print("\n  [Step 2] Grid search meta-learner...")
    meta_candidates = {
        'LR_l2': LogisticRegression(penalty='l2', C=1.0, class_weight='balanced', max_iter=2000, random_state=random_state),
        'LR_l1': LogisticRegression(penalty='l1', solver='saga', C=1.0, class_weight='balanced', max_iter=2000, random_state=random_state),
        'Ridge': RidgeClassifier(alpha=1.0, class_weight='balanced', random_state=random_state),
    }

    best_meta_name = None
    best_meta_auc = 0
    best_meta_model = None

    for meta_name, meta_model in meta_candidates.items():
        try:
            estimators = [(n, type(models_dict[n])(**{k: v for k, v in models_dict[n].get_params().items()
                                if k not in ['random_state', 'random_seed']}))
                         for n in top3_names]
            for est_name, est in estimators:
                if 'random_state' in est.get_params():
                    est.set_params(random_state=random_state)

            from sklearn.ensemble import StackingClassifier as SC
            stack = SC(
                estimators=estimators,
                final_estimator=meta_model,
                cv=StratifiedKFold(n_splits=cv, shuffle=True, random_state=random_state),
                stack_method='predict_proba',
                n_jobs=-1,
            )
            stack.fit(X_tr, y_tr)
            prob = stack.predict_proba(X_te)[:, 1]
            auc = roc_auc_score(y_te, prob)
            print(f"    {meta_name}: AUC = {auc:.4f}")
            if auc > best_meta_auc:
                best_meta_auc = auc
                best_meta_name = meta_name
                best_meta_model = stack
        except Exception as e:
            print(f"    [WARN] {meta_name} failed: {e}")

    print(f"  Best meta-learner: {best_meta_name} (AUC={best_meta_auc:.4f})")

    # ---- Step 3: Build all ensemble methods ----
    print("\n  [Step 3] Building ensembles...")

    # 3a. Voting Ensemble
    voting_ens = create_voting_ensemble(top3_models, voting='soft')
    if voting_ens:
        voting_ens.fit(X_tr, y_tr)

    # 3b. Stacking Ensemble (best meta-learner from grid search)
    stacking_ens = best_meta_model  # Already fitted

    # 3c. Weighted Average
    model_probs = {}
    for name in top3_names:
        m = type(models_dict[name])(**{k: v for k, v in models_dict[name].get_params().items()
                                       if k not in ['random_state', 'random_seed']})
        if 'random_state' in m.get_params():
            m.set_params(random_state=random_state)
        m.fit(X_tr, y_tr)
        model_probs[name] = m.predict_proba(X_te)[:, 1]
    opt_weights = find_optimal_model_weights(model_probs, y_te)
    weighted_prob = weighted_model_averaging(model_probs, opt_weights)

    # ---- Step 4: Evaluate all methods with Bootstrap CI ----
    print("\n  [Step 4] Bootstrap evaluation...")
    evaluation = {}

    # Voting
    if voting_ens:
        v_prob = voting_ens.predict_proba(X_te)[:, 1]
        v_auc = roc_auc_score(y_te, v_prob)
        v_brier = brier_score_loss(y_te, v_prob)
        v_ci = _bootstrap_auc_ci(voting_ens, X_arr, y_arr, n_bootstrap, random_state)
        evaluation['Voting (Top3)'] = {'AUC': v_auc, 'Brier': v_brier, 'CI': v_ci}

    # Stacking
    s_prob = stacking_ens.predict_proba(X_te)[:, 1] if stacking_ens else None
    if s_prob is not None:
        s_auc = roc_auc_score(y_te, s_prob)
        s_brier = brier_score_loss(y_te, s_prob)
        s_ci = _bootstrap_auc_ci(stacking_ens, X_arr, y_arr, n_bootstrap, random_state)
        evaluation[f'Stacking ({best_meta_name})'] = {'AUC': s_auc, 'Brier': s_brier, 'CI': s_ci}

    # Weighted Avg
    w_auc = roc_auc_score(y_te, weighted_prob)
    w_brier = brier_score_loss(y_te, weighted_prob)
    # Bootstrap for weighted avg
    w_ci = _bootstrap_auc_ci_weighted(model_probs, X_arr, y_arr, opt_weights, n_bootstrap, random_state)
    evaluation['Weighted Avg'] = {'AUC': w_auc, 'Brier': w_brier, 'CI': w_ci}

    # Top individual models
    for name in top3_names[:2]:
        m_prob = model_probs.get(name)
        if m_prob is not None:
            evaluation[f'{name} (Single)'] = {
                'AUC': roc_auc_score(y_te, m_prob),
                'Brier': brier_score_loss(y_te, m_prob),
                'CI': (cv_scores.get(name, 0) - 0.02, cv_scores.get(name, 0) + 0.02),
            }

    # ---- Step 5: Plot comparison ----
    print("\n  [Step 5] Generating comparison plot...")
    plot_ensemble_comparison_v2(evaluation, output_dir)

    # Print summary
    print("\n" + "=" * 70)
    print("  Ensemble Pipeline Complete")
    print("=" * 70)
    for method, metrics in sorted(evaluation.items(), key=lambda x: x[1]['AUC'], reverse=True):
        ci_str = f"95% CI [{metrics['CI'][0]:.3f}, {metrics['CI'][1]:.3f}]"
        print(f"  {method:25s}: AUC={metrics['AUC']:.4f}  Brier={metrics['Brier']:.4f}  {ci_str}")

    return {
        'evaluation': evaluation,
        'top3_models': top3_names,
        'voting_ensemble': voting_ens,
        'stacking_ensemble': stacking_ens,
        'optimal_weights': opt_weights,
        'best_meta_learner': best_meta_name,
    }


def _bootstrap_auc_ci(model, X, y, n_bootstrap=500, random_state=42):
    """Bootstrap AUC confidence interval for a fitted model."""
    rng = np.random.RandomState(random_state)
    aucs = []
    n = len(y)
    for _ in range(n_bootstrap):
        idx = rng.randint(0, n, n)
        X_boot, y_boot = X[idx], y[idx]
        try:
            if hasattr(model, 'predict_proba'):
                prob = model.predict_proba(X_boot)[:, 1]
            else:
                prob = model.decision_function(X_boot)
                prob = (prob - prob.min()) / max(prob.max() - prob.min(), 1e-10)
            aucs.append(roc_auc_score(y_boot, prob))
        except:
            continue

    if len(aucs) < 10:
        return (np.nan, np.nan)
    return (np.percentile(aucs, 2.5), np.percentile(aucs, 97.5))


def _bootstrap_auc_ci_weighted(model_probs, X, y, weights, n_bootstrap=500, random_state=42):
    """Bootstrap AUC CI for weighted average ensemble."""
    rng = np.random.RandomState(random_state)
    aucs = []
    n = len(y)
    for _ in range(n_bootstrap):
        idx = rng.randint(0, n, n)
        y_boot = y[idx]
        # For weighted avg, just resample the precomputed probs
        probs_boot = {k: v[idx] for k, v in model_probs.items()}
        avg = weighted_model_averaging(probs_boot, weights)
        aucs.append(roc_auc_score(y_boot, avg))

    if len(aucs) < 10:
        return (np.nan, np.nan)
    return (np.percentile(aucs, 2.5), np.percentile(aucs, 97.5))


def plot_ensemble_comparison_v2(evaluation, output_dir=None):
    """
    Enhanced ensemble comparison plot with CI error bars.
    """
    fig, ax = plt.subplots(figsize=(12, 6))

    methods = list(evaluation.keys())
    aucs = [evaluation[m]['AUC'] for m in methods]
    ci_lowers = [max(0, evaluation[m]['CI'][0]) for m in methods]
    ci_uppers = [min(1, evaluation[m]['CI'][1]) for m in methods]

    # Separate single models from ensembles
    colors = []
    for m in methods:
        if '(Single)' in m:
            colors.append('#95a5a6')  # Gray for single models
        elif 'Stacking' in m:
            colors.append('#e74c3c')  # Red for stacking
        elif 'Voting' in m:
            colors.append('#3498db')  # Blue for voting
        elif 'Weighted' in m:
            colors.append('#f39c12')  # Orange for weighted
        else:
            colors.append('#2ecc71')  # Green for other

    # Sort by AUC
    sorted_idx = np.argsort(aucs)
    methods_sorted = [methods[i] for i in sorted_idx]
    aucs_sorted = [aucs[i] for i in sorted_idx]
    colors_sorted = [colors[i] for i in sorted_idx]
    ci_low_sorted = [ci_lowers[i] for i in sorted_idx]
    ci_high_sorted = [ci_uppers[i] for i in sorted_idx]

    # Error bars
    xerr_low = [a - l for a, l in zip(aucs_sorted, ci_low_sorted)]
    xerr_high = [h - a for a, h in zip(aucs_sorted, ci_high_sorted)]

    y_pos = range(len(methods_sorted))
    bars = ax.barh(y_pos, aucs_sorted, color=colors_sorted, edgecolor='white',
                   xerr=[xerr_low, xerr_high], capsize=3, alpha=0.9)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(methods_sorted, fontsize=11)
    ax.set_xlabel('AUC-ROC', fontsize=13)
    ax.set_title('Ensemble Methods Comparison (with 95% Bootstrap CI)', fontsize=14, fontweight='bold')
    ax.invert_yaxis()

    # Value labels
    for i, (auc, method) in enumerate(zip(aucs_sorted, methods_sorted)):
        ax.text(auc + 0.003, i, f'{auc:.4f}', va='center', fontsize=10, fontweight='bold')

    # Legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor='#95a5a6', label='Single Model'),
        Patch(facecolor='#3498db', label='Voting Ensemble'),
        Patch(facecolor='#e74c3c', label='Stacking Ensemble'),
        Patch(facecolor='#f39c12', label='Weighted Average'),
    ]
    ax.legend(handles=legend_elements, loc='lower right', fontsize=9)
    ax.grid(axis='x', alpha=0.2)
    plt.tight_layout()

    if output_dir:
        save_path = Path(output_dir) / 'figures' / 'ensemble_comparison.png' if not str(output_dir).endswith('.png') else output_dir
        os.makedirs(os.path.dirname(str(save_path)), exist_ok=True)
        fig.savefig(str(save_path), dpi=150, bbox_inches='tight', facecolor='white')
        print(f"  Ensemble comparison saved: {save_path}")
        plt.close(fig)
    else:
        return fig


def compare_all_ensembles(X, y, models_dict, cv=5, random_state=42, output_dir=None):
    """
    Head-to-head comparison: Voting vs Stacking vs Weighted Avg.
    Wraps run_full_ensemble_pipeline with simplified API.
    """
    return run_full_ensemble_pipeline(
        X, y, models_dict, cv=cv, random_state=random_state, output_dir=output_dir
    )


if __name__ == '__main__':
    print("Ensemble module loaded successfully.")

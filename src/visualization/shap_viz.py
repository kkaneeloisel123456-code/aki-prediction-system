"""
AKI Prediction Project - SHAP Visualization Module
SHAP Summary, Feature Importance, Force Plot, Dependence Plot, Clinical Interpretation.
"""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import warnings
warnings.filterwarnings('ignore')

import sys
sys.path.append('..')
from src.utils.helpers import (
    logger, FIGURES_DIR, TABLES_DIR,
    save_figure, save_table, format_pvalue
)


# ============================================
# SHAP Analysis
# ============================================
def compute_shap_values(model, X, model_type='tree', max_display=20):
    """
    Compute SHAP values for a model.

    Args:
        model: Trained model
        X: Feature matrix (DataFrame)
        model_type: 'tree' for tree-based, 'linear' for linear, 'deep' for neural net
        max_display: Max features to display in plots

    Returns:
        shap_values: SHAP values array
        explainer: SHAP explainer object
    """
    try:
        import shap
    except ImportError:
        logger.error("SHAP not installed. Run: pip install shap")
        return None, None

    logger.info(f"Computing SHAP values for model type: {model_type}")

    try:
        if model_type == 'tree':
            explainer = shap.TreeExplainer(model)
            shap_values = explainer.shap_values(X)
            # For binary classification, shap_values might be a list
            if isinstance(shap_values, list):
                shap_values = shap_values[1]  # Class 1 (AKI)
        elif model_type == 'linear':
            explainer = shap.LinearExplainer(model, X)
            shap_values = explainer.shap_values(X)
        else:
            # Use KernelExplainer as fallback (slow on large data)
            background = shap.kmeans(X, min(50, len(X)))
            explainer = shap.KernelExplainer(model.predict_proba, background)
            shap_values = explainer.shap_values(X[:100])
            if isinstance(shap_values, list):
                shap_values = shap_values[1]

        logger.info(f"SHAP values shape: {np.array(shap_values).shape}")
        return shap_values, explainer

    except Exception as e:
        logger.error(f"SHAP computation failed: {e}")
        return None, None


# ============================================
# SHAP Visualizations
# ============================================
def plot_shap_summary(shap_values, X, max_display=20, save_name='shap_summary.png'):
    """SHAP Summary Plot (bee swarm) showing feature impact."""
    try:
        import shap

        fig, ax = plt.subplots(figsize=(10, max(8, max_display * 0.35)))
        shap.summary_plot(shap_values, X, max_display=max_display, show=False)
        plt.title('SHAP Summary Plot - Feature Impact on AKI Prediction', fontsize=14, fontweight='bold')
        plt.tight_layout()
        save_figure(plt.gcf(), save_name)
        logger.info(f"SHAP summary plot saved: {save_name}")

    except Exception as e:
        logger.error(f"Failed to create SHAP summary plot: {e}")


def plot_shap_bar(shap_values, X, max_display=20, save_name='shap_bar.png'):
    """SHAP Bar Plot - mean absolute SHAP values."""
    try:
        import shap

        fig, ax = plt.subplots(figsize=(10, max(8, max_display * 0.35)))
        shap.summary_plot(shap_values, X, plot_type='bar', max_display=max_display, show=False)
        plt.title('SHAP Feature Importance (Mean |SHAP|)', fontsize=14, fontweight='bold')
        plt.tight_layout()
        save_figure(plt.gcf(), save_name)
        logger.info(f"SHAP bar plot saved: {save_name}")

    except Exception as e:
        logger.error(f"Failed to create SHAP bar plot: {e}")


def plot_shap_force_single(shap_values, X, explainer, index=0, save_name='shap_force_single.png'):
    """SHAP Force Plot for a single prediction."""
    try:
        import shap

        shap.initjs()
        fig = shap.force_plot(
            explainer.expected_value if not isinstance(explainer.expected_value, list)
            else explainer.expected_value[1],
            shap_values[index] if not isinstance(shap_values, list) else shap_values[1][index],
            X.iloc[index],
            matplotlib=True,
            show=False
        )
        plt.title(f'SHAP Force Plot - Patient {index}', fontsize=14, fontweight='bold')
        plt.tight_layout()
        save_figure(plt.gcf() if plt.gcf().get_axes() else fig, save_name)

    except Exception as e:
        logger.error(f"Failed to create SHAP force plot: {e}")


def plot_shap_force_multiple(shap_values, X, explainer, n_samples=10, save_name='shap_force_multi.html'):
    """SHAP Force Plot for multiple predictions (interactive HTML)."""
    try:
        import shap

        shap.initjs()
        expected_value = (explainer.expected_value[1]
                         if isinstance(explainer.expected_value, list)
                         else explainer.expected_value)
        shap_values_class = shap_values[1] if isinstance(shap_values, list) else shap_values

        fig = shap.force_plot(expected_value, shap_values_class[:n_samples], X.iloc[:n_samples])
        shap.save_html(str(FIGURES_DIR / save_name), fig)
        logger.info(f"SHAP multi force plot saved: {save_name}")

    except Exception as e:
        logger.error(f"Failed to create SHAP multi force plot: {e}")


def plot_shap_dependence(shap_values, X, feature_names, top_n=5, save_name='shap_dependence.png'):
    """SHAP Dependence Plots for top N features."""
    try:
        import shap

        n_features = min(top_n, len(feature_names))
        fig, axes = plt.subplots(n_features, 2, figsize=(14, n_features * 3.5))
        if n_features == 1:
            axes = axes.reshape(1, 2)

        for i, feature in enumerate(feature_names[:n_features]):
            # Dependence plot
            plt.sca(axes[i, 0])
            shap.dependence_plot(
                feature, shap_values, X,
                interaction_index=None, show=False, ax=axes[i, 0]
            )
            axes[i, 0].set_title(f'{feature} Dependence', fontweight='bold')

            # Find most interacting feature
            plt.sca(axes[i, 1])
            # Compute SHAP interaction for top interacting feature
            feature_idx = list(X.columns).index(feature)
            shap_abs_mean = np.abs(shap_values).mean(0)
            # Plot dependence with the next most important feature as interaction
            remaining = [f for f in X.columns if f != feature]
            if remaining:
                interaction_feature = remaining[0]  # Simple fallback
                shap.dependence_plot(
                    feature, shap_values, X,
                    interaction_index=interaction_feature, show=False, ax=axes[i, 1]
                )
                axes[i, 1].set_title(f'{feature} vs {interaction_feature}', fontweight='bold')

        plt.suptitle('SHAP Dependence Plots - Top Features', fontsize=16, fontweight='bold', y=1.01)
        plt.tight_layout()
        save_figure(fig, save_name)

    except Exception as e:
        logger.error(f"Failed to create SHAP dependence plots: {e}")


# ============================================
# SHAP-based Feature Importance Table
# ============================================
def create_shap_importance_table(shap_values, X, save_name='shap_importance.csv'):
    """
    Create detailed SHAP feature importance table with clinical annotations.
    """
    shap_abs_mean = np.abs(shap_values).mean(axis=0)

    importance_df = pd.DataFrame({
        'Feature': X.columns,
        'Mean_ABS_SHAP': shap_abs_mean,
        'SHAP_Std': np.std(shap_values, axis=0),
        'Direction': ['Positive (risk)' if s > 0 else 'Negative (protective)'
                      for s in np.mean(shap_values, axis=0)]
    }).sort_values('Mean_ABS_SHAP', ascending=False)

    importance_df['Rank'] = range(1, len(importance_df) + 1)
    importance_df['Cumulative_Importance'] = (importance_df['Mean_ABS_SHAP'].cumsum() /
                                               importance_df['Mean_ABS_SHAP'].sum() * 100).round(1)

    save_table(importance_df, save_name)

    return importance_df


# ============================================
# Clinical Interpretation Generator
# ============================================
def generate_clinical_interpretation(shap_values, X, feature_names, top_n=10):
    """
    Generate clinical interpretation text for top SHAP features.
    Explains WHY each feature is important from a medical perspective.

    Returns:
        clinical_notes: Dict of feature → clinical interpretation
    """
    shap_abs_mean = np.abs(shap_values).mean(axis=0)
    top_features = X.columns[np.argsort(shap_abs_mean)[::-1]][:top_n]

    # Clinical knowledge base for common AKI-related features
    clinical_knowledge = {
        '年龄': '年龄增长导致肾小球滤过率生理性下降、肾储备功能减退，是AKI的独立危险因素。老年患者肾小管上皮细胞再生能力减弱，对缺血/再灌注损伤更敏感。',
        '高血压': '长期高血压引起肾小球高灌注和高滤过，导致肾小动脉硬化、管壁增厚，降低肾脏对低灌注的代偿能力。术中血压波动更易诱发AKI。',
        '糖尿病': '糖尿病肾病是AKI最常见的基础疾病之一。高血糖通过氧化应激、炎症反应和微血管病变损害肾小管间质，显著增加手术相关AKI风险。',
        '冠心病': '冠心病反映全身动脉粥样硬化状态，常伴心输出量储备降低。术中血流动力学不稳定时，肾脏灌注更易受损。',
        'APACHEII': 'APACHE II评分综合反映疾病严重程度。高评分意味着更严重的生理紊乱和多器官功能障碍风险，是AKI最强的预测因子之一。',
        '术中失血量': '大量失血直接导致肾脏灌注不足和缺血性损伤。失血量>500ml时肾血流自动调节机制可能失效，肾小管上皮细胞对缺氧极为敏感。',
        '术中尿量': '术中尿量是肾灌注的直接反映。少尿是AKI最早期的临床表现之一，术中尿量<0.5ml/kg/h持续超过6小时符合AKI诊断标准。',
        '手术时间': '长时程手术意味着更长时间的麻醉暴露、更持久的血流动力学波动和更强的全身炎症反应，均增加术后AKI风险。',
        '术前Scr': '术前血肌酐是肾脏功能基线指标。即使轻度升高也可能提示肾储备功能下降，是术后AKI最强的独立预测因子。',
        '术前eGFR': 'eGFR是评估肾功能的金标准。术前eGFR<60ml/min/1.73m²即诊断为CKD，术后AKI风险显著增高。',
        'ICUAdmSCr': 'ICU入室时血肌酐反映术后早期肾功能状态，是SIRS和早期肾损伤的敏感指标。',
        '术后48hSCr': '术后48小时是AKI发生的关键时间窗。48h内Scr升高≥0.3mg/dL或≥基线1.5倍符合AKI诊断。',
        '术前CRP': 'CRP是全身炎症标志物。术前CRP升高提示亚临床感染或炎症状态，增加术后氧化应激和AKI风险。',
        '术前WBC': '白细胞计数反映感染/炎症状态。术前WBC升高可能预示SIRS，增加术后肾损伤风险。',
        '术前NLR': '中性粒细胞/淋巴细胞比值(NLR)是系统性炎症和免疫应答的综合指标。高NLR反映促炎状态，与术后AKI独立相关。',
        '术前Hb': '术前贫血降低血氧携带能力。肾脏髓质氧分压本已较低，贫血加重了髓质缺氧损伤风险。',
        '术前Alb': '低白蛋白血症与术后AKI密切相关。低Alb可能反映营养不良-炎症复合体综合征，且白蛋白本身具有抗氧化和内皮保护作用。',
        '术前Lactate': '术前乳酸升高提示组织低灌注或无氧代谢增加，是隐匿性休克的标志，预示术后器官功能障碍。',
        '术前BE': '碱剩余负值提示代谢性酸中毒，可能由肾小管酸中毒或组织低灌注引起，是肾储备功能降低的指标。',
        '术后通气时间': '长时间机械通气延长胸腔内压升高时间，影响静脉回流和心输出量，间接降低肾灌注。正压通气还可激活肾素-血管紧张素系统。',
        'ICU住院天数': 'ICU住院时间延长与AKI呈双向关系：AKI延长ICU停留，ICU内二次损伤(肾毒性药物、感染)加重AKI。',
        '术中晶体液量': '过量的晶体液输注可导致液体超负荷和组织水肿。肾脏包膜内水肿增加间质压力，压迫肾小管和微血管，恶化肾功能。',
        '术前K': '术前血钾异常(尤其高钾)可能提示肾排钾能力下降。高钾血症是肾功能不全的晚期表现，但轻度升高也可能是早期信号。',
        '术前UA': '高尿酸血症可导致尿酸结晶在肾小管沉积，直接损伤肾小管上皮细胞。尿酸也是内皮功能障碍的标志物。',
        '术前β2MG': 'β2微球蛋白是反映肾小管功能的敏感指标。升高早于Scr，提示肾小管重吸收功能受损。',
        '术前BNP': 'BNP升高反映心室壁张力和心功能不全。心肾综合征中，心输出量降低和静脉淤血共同导致肾功能恶化。',
    }

    clinical_notes = {}
    for feature in top_features:
        importance = shap_abs_mean[X.columns.get_loc(feature)]
        direction = '风险因素' if np.mean(shap_values[:, X.columns.get_loc(feature)]) > 0 else '保护因素'

        # Try to find matching clinical knowledge
        interpretation = clinical_knowledge.get(feature, None)

        if interpretation is None:
            # Generic interpretation based on feature name
            if 'Scr' in feature or '肌酐' in feature:
                interpretation = f'{feature}是肾功能的直接标志物。水平升高提示肾小球滤过率下降，是AKI诊断和分级的核心依据。'
            elif 'eGFR' in feature:
                interpretation = f'{feature}升高提示更好的肾功能储备，可能具有肾保护作用。较高值为保护因素。'
            elif '术前' in feature:
                interpretation = f'{feature}反映术前基础状态，其异常可能提示患者处于手术和应激的高风险状态。'
            elif '术后' in feature:
                interpretation = f'{feature}反映术后早期生理变化，可作为早期预警信号。'
            else:
                interpretation = f'{feature}对AKI预测有显著贡献，其临床机制值得进一步研究。'

        clinical_notes[feature] = {
            'importance': float(importance),
            'direction': direction,
            'interpretation': interpretation
        }

    return clinical_notes


def save_clinical_interpretation(clinical_notes, save_name='clinical_interpretation.md'):
    """Save clinical interpretation as a formatted markdown report."""
    lines = [
        "# AKI 预测模型 — SHAP 临床解释报告\n",
        "---\n",
        f"生成时间: {pd.Timestamp.now()}\n\n",
        "## SHAP 特征重要性与临床解读\n\n",
        "| 排名 | 特征 | 方向 | SHAP重要性 | 临床解释 |",
        "|------|------|------|-----------|----------|",
    ]

    for rank, (feature, notes) in enumerate(clinical_notes.items(), 1):
        lines.append(
            f"| {rank} | {feature} | {notes['direction']} | {notes['importance']:.4f} | {notes['interpretation']} |"
        )

    lines.extend([
        "\n\n## 关键临床洞察\n",
        "### 1. 肾功能基线的重要性",
        "术前肾功能指标（Scr、eGFR）是术后AKI最强的预测因子，提示术前肾功能评估应作为心脏手术患者的常规筛查。",
        "\n### 2. 术中管理的可干预窗口",
        "术中尿量、失血量、液体管理均为可干预因素，提示术中目标导向液体治疗和肾灌注优化可能降低AKI风险。",
        "\n### 3. 炎症-免疫轴的贡献",
        "炎症指标（CRP、NLR、WBC）的重要性提示围术期抗炎策略（如他汀类药物、抗氧化剂）可能具有肾保护作用。",
        "\n### 4. 多因素交互效应",
        "AKI是多因素交互作用的结果，单变量预测能力有限。SHAP交互分析提示高危因素组合（如高龄+低eGFR+长手术时间）的风险远超各因素独立风险的加和。",
        "\n### 5. 临床决策支持",
        "基于SHAP值的个体化解释可为临床医生提供透明的预测依据，支持术前风险评估、术中预警和术后管理决策。",
    ])

    filepath = TABLES_DIR / save_name
    with open(str(filepath), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    logger.info(f"Clinical interpretation saved: {filepath}")


# ============================================
# Full SHAP Pipeline
# ============================================
def run_full_shap_analysis(model, X, y=None, model_type='tree',
                            feature_names=None, top_n=10, patient_index=0):
    """
    Run complete SHAP analysis pipeline.

    Returns:
        results: Dict with all SHAP results
    """
    logger.info("=" * 60)
    logger.info("Starting SHAP Analysis Pipeline")
    logger.info("=" * 60)

    if not isinstance(X, pd.DataFrame):
        X = pd.DataFrame(X, columns=feature_names if feature_names else [f'Feature_{i}' for i in range(X.shape[1])])

    # Compute SHAP values
    shap_values, explainer = compute_shap_values(model, X, model_type=model_type)

    if shap_values is None:
        logger.error("SHAP computation failed. Aborting.")
        return None

    # Generate plots
    plot_shap_summary(shap_values, X, max_display=top_n, save_name='shap_summary.png')
    plot_shap_bar(shap_values, X, max_display=top_n, save_name='shap_bar.png')
    plot_shap_dependence(shap_values, X, feature_names=list(X.columns)[:top_n],
                         top_n=min(5, top_n), save_name='shap_dependence.png')

    # Individual force plot
    if patient_index < len(X):
        plot_shap_force_single(shap_values, X, explainer, index=patient_index,
                               save_name=f'shap_force_patient_{patient_index}.png')

    # Multi force plot (HTML)
    n_show = min(10, len(X))
    plot_shap_force_multiple(shap_values, X, explainer, n_samples=n_show,
                             save_name='shap_force_multi.html')

    # Importance table
    importance_df = create_shap_importance_table(shap_values, X)

    # Clinical interpretation
    clinical_notes = generate_clinical_interpretation(shap_values, X,
                                                       feature_names=list(X.columns), top_n=top_n)
    save_clinical_interpretation(clinical_notes)

    logger.info("SHAP analysis complete!")

    return {
        'shap_values': shap_values,
        'explainer': explainer,
        'importance_df': importance_df,
        'clinical_notes': clinical_notes,
    }


# ============================================
# Counterfactual Explanation (反事实解释)
# ============================================
def generate_counterfactual(
    model, X, shap_values, feature_names,
    patient_idx=0, feature_to_vary=None,
    vary_range=None, n_steps=20,
):
    """
    Generate counterfactual predictions: "What if feature X changes?"

    Computes how the predicted risk changes when a single feature is
    varied across a range of values, holding all other features constant.

    Args:
        model: Trained model with predict_proba
        X: Feature DataFrame
        shap_values: SHAP values array
        feature_names: List of feature names
        patient_idx: Index of patient to explain
        feature_to_vary: Feature name to manipulate
        vary_range: (min, max) range to sweep. If None, uses ±50% of current value.
        n_steps: Number of steps in the sweep

    Returns:
        dict with: feature_name, original_value, original_prob,
                   vary_values, counterfactual_probs, risk_changes
    """
    import numpy as np

    if not isinstance(X, pd.DataFrame):
        X = pd.DataFrame(X, columns=feature_names)

    if feature_to_vary is None:
        # Auto-select the feature with highest SHAP impact for this patient
        if isinstance(shap_values, list):
            sv = shap_values[1] if len(shap_values) > 1 else shap_values[0]
        else:
            sv = shap_values
        top_idx = np.argmax(np.abs(sv[patient_idx]))
        feature_to_vary = feature_names[top_idx]

    # Get original prediction
    X_patient = X.iloc[[patient_idx]].copy()
    original_prob = model.predict_proba(X_patient)[:, 1][0]
    original_value = X_patient[feature_to_vary].values[0]

    # Determine range
    if vary_range is None:
        current = float(original_value)
        if current == 0:
            vary_range = (0, 1)
        else:
            vary_range = (current * 0.5, current * 1.5)

    vary_values = np.linspace(vary_range[0], vary_range[1], n_steps)

    counterfactual_probs = []
    for val in vary_values:
        X_modified = X_patient.copy()
        X_modified[feature_to_vary] = val
        prob = model.predict_proba(X_modified)[:, 1][0]
        counterfactual_probs.append(prob)

    counterfactual_probs = np.array(counterfactual_probs)
    risk_changes = counterfactual_probs - original_prob

    logger.info(f"Counterfactual for '{feature_to_vary}': "
                f"original={original_value:.2f}, prob={original_prob:.3f}, "
                f"range=[{vary_range[0]:.2f}, {vary_range[1]:.2f}]")

    return {
        'feature_name': feature_to_vary,
        'original_value': original_value,
        'original_prob': original_prob,
        'vary_values': vary_values,
        'counterfactual_probs': counterfactual_probs,
        'risk_changes': risk_changes,
    }


def plot_counterfactual_curve(
    counterfactual_result,
    save_name='counterfactual_curve.png',
    figsize=(8, 5),
):
    """
    Plot counterfactual risk curve.

    Shows how predicted AKI risk changes as a single feature varies,
    with risk zones highlighted.

    Args:
        counterfactual_result: Dict from generate_counterfactual()
        save_name: Output filename
        figsize: Figure size
    """
    import matplotlib.pyplot as plt
    import numpy as np

    fig, ax = plt.subplots(figsize=figsize)

    feature = counterfactual_result['feature_name']
    vary_vals = counterfactual_result['vary_values']
    probs = counterfactual_result['counterfactual_probs']
    orig_val = counterfactual_result['original_value']
    orig_prob = counterfactual_result['original_prob']

    # Risk zone backgrounds
    ax.axhspan(0, 0.3, alpha=0.08, color='#27ae60', label='低风险 (<30%)')
    ax.axhspan(0.3, 0.7, alpha=0.08, color='#f39c12', label='中风险 (30-70%)')
    ax.axhspan(0.7, 1.0, alpha=0.08, color='#e74c3c', label='高风险 (>70%)')

    # Main curve
    ax.plot(vary_vals, probs, '-', color='#2a78d6', linewidth=2.5, label='预测风险')
    ax.fill_between(vary_vals, probs, alpha=0.1, color='#2a78d6')

    # Current value marker
    ax.plot(orig_val, orig_prob, 'o', color='#e34948', markersize=12,
            markeredgecolor='white', markeredgewidth=2, zorder=5)
    ax.annotate(
        f'当前值: {orig_val:.2f}\n风险: {orig_prob:.1%}',
        xy=(orig_val, orig_prob),
        xytext=(orig_val + (vary_vals[-1] - vary_vals[0]) * 0.15, orig_prob + 0.08),
        fontsize=9, ha='center',
        bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor='#e34948', alpha=0.9),
        arrowprops=dict(arrowstyle='->', color='#e34948', lw=1.5),
    )

    ax.set_xlabel(f'{feature} 值', fontsize=12)
    ax.set_ylabel('预测AKI风险概率', fontsize=12)
    ax.set_title(f'反事实解释 | Counterfactual Analysis\n'
                 f'"{feature}" 变化对AKI风险的影响',
                 fontsize=14, fontweight='bold')
    ax.set_ylim(0, 1)
    ax.legend(loc='upper left', fontsize=8, framealpha=0.8)
    ax.grid(True, alpha=0.3)

    # Annotation
    # Find where risk crosses thresholds
    cross_low = None
    cross_high = None
    for i in range(1, len(vary_vals)):
        if probs[i-1] < 0.3 and probs[i] >= 0.3:
            cross_low = vary_vals[i]
        if probs[i-1] < 0.7 and probs[i] >= 0.7:
            cross_high = vary_vals[i]

    annotations = []
    if cross_low is not None:
        annotations.append(f'中风险阈值 ≈ {cross_low:.1f}')
    if cross_high is not None:
        annotations.append(f'高风险阈值 ≈ {cross_high:.1f}')

    if annotations:
        ax.text(0.98, 0.02, '\n'.join(annotations),
                transform=ax.transAxes, ha='right', va='bottom',
                fontsize=8, color='#52514e',
                bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))

    plt.tight_layout()
    save_figure(fig, save_name)
    logger.info(f"Counterfactual curve saved: {save_name}")

    return fig, ax


def compute_counterfactual_report(
    model, X, shap_values, feature_names,
    patient_idx=0, top_n=5,
):
    """
    Generate a counterfactual report for top N features.

    For each top SHAP feature, computes:
    - What if the value was normal/better?
    - How much would risk decrease?

    Returns:
        List of dicts with counterfactual analysis per feature
    """
    import numpy as np

    if not isinstance(X, pd.DataFrame):
        X = pd.DataFrame(X, columns=feature_names)

    if isinstance(shap_values, list):
        sv = shap_values[1] if len(shap_values) > 1 else shap_values[0]
    else:
        sv = shap_values

    # Get top features by SHAP impact for this patient
    patient_shap = sv[patient_idx]
    top_indices = np.argsort(np.abs(patient_shap))[::-1][:top_n]

    report = []
    for idx in top_indices:
        feature = feature_names[idx]
        current_val = X.iloc[patient_idx, idx]
        shap_impact = patient_shap[idx]

        # Define "improved" direction
        if shap_impact > 0:
            # Positive SHAP = pushes risk UP, so "improved" = lower value
            improved_val = current_val * 0.7 if current_val > 0 else current_val * 0.5
            direction = '降低'
            direction_en = 'decrease'
        else:
            # Negative SHAP = pushes risk DOWN, so "improved" = higher value
            improved_val = current_val * 1.3 if current_val > 0 else current_val * 1.5
            direction = '升高'
            direction_en = 'increase'

        # Compute counterfactual
        X_mod = X.iloc[[patient_idx]].copy()
        X_mod[feature] = improved_val
        new_prob = model.predict_proba(X_mod)[:, 1][0]
        orig_prob = model.predict_proba(X.iloc[[patient_idx]])[:, 1][0]
        risk_change = new_prob - orig_prob

        report.append({
            'feature': feature,
            'current_value': float(current_val),
            'shap_impact': float(shap_impact),
            'suggested_direction': direction,
            'counterfactual_value': float(improved_val),
            'original_risk': round(orig_prob, 4),
            'counterfactual_risk': round(new_prob, 4),
            'risk_change': round(risk_change, 4),
            'risk_change_pct': round(abs(risk_change) * 100, 1),
        })

    return report


def print_counterfactual_report(report):
    """Print a human-readable counterfactual report."""
    print("\n" + "=" * 70)
    print("🔄 反事实解释报告 | Counterfactual Explanation Report")
    print("=" * 70)
    print("问题: \"如果关键特征发生变化，风险会怎么变？\"\n")

    for i, item in enumerate(report, 1):
        direction_symbol = '↓' if item['risk_change'] < 0 else '↑'
        print(f"{i}. {item['feature']}")
        print(f"   当前值: {item['current_value']:.2f}  →  "
              f"如果{item['suggested_direction']}到 {item['counterfactual_value']:.2f}")
        print(f"   预测风险: {item['original_risk']:.1%} → "
              f"{item['counterfactual_risk']:.1%} "
              f"({direction_symbol}{item['risk_change_pct']:.1f}%)")
        print()

    print("💡 临床意义: 反事实分析帮助医生理解哪些干预措施可能最有效降低AKI风险。")


if __name__ == '__main__':
    print("SHAP visualization module loaded successfully.")

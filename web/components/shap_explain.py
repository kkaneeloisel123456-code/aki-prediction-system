"""
AKI Prediction System - SHAP Explanation Component
Handles SHAP force plots, summary plots, and clinical interpretation for the web app.
"""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st
import shap
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.utils.helpers import logger


def compute_shap_for_prediction(model, X, feature_names, model_type='tree'):
    """
    Compute SHAP values for a single prediction.

    Args:
        model: Trained model
        X: Single sample DataFrame
        feature_names: List of feature names
        model_type: 'tree', 'linear', or 'deep'

    Returns:
        shap_values: SHAP values for the prediction
        expected_value: Base value
    """
    try:
        if model_type == 'tree':
            explainer = shap.TreeExplainer(model)
            shap_values = explainer.shap_values(X)
            expected_value = explainer.expected_value

            if isinstance(shap_values, list):
                # Binary classification - take class 1
                shap_values = shap_values[1]
                expected_value = expected_value[1] if isinstance(expected_value, list) else expected_value

        elif model_type == 'linear':
            explainer = shap.LinearExplainer(model, X)
            shap_values = explainer.shap_values(X)
            expected_value = explainer.expected_value

        else:
            # Fallback
            logger.warning(f"Unknown model_type: {model_type}, using KernelExplainer")
            explainer = shap.Explainer(model)
            shap_values = explainer(X)
            expected_value = explainer.expected_value

        return shap_values, expected_value

    except Exception as e:
        logger.error(f"SHAP computation failed: {e}")
        return None, None


def create_shap_force_plot_html(shap_values, expected_value, X, feature_names):
    """Create SHAP force plot as HTML for Streamlit display."""
    try:
        import shap
        shap.initjs()

        if isinstance(shap_values, np.ndarray) and shap_values.ndim == 2:
            shap_values = shap_values[0]

        expected_val = (expected_value
                       if not isinstance(expected_value, (list, np.ndarray))
                       else expected_value[1] if hasattr(expected_value, '__len__') and len(expected_value) > 1
                       else expected_value)

        # Create Explanation object
        exp = shap.Explanation(
            values=shap_values,
            base_values=expected_val,
            data=X.values[0] if hasattr(X, 'values') else X,
            feature_names=feature_names
        )

        # Generate HTML
        html = shap.plots.force(exp, show=False, matplotlib=False)
        return html

    except Exception as e:
        logger.error(f"Force plot creation failed: {e}")
        return None


def create_shap_waterfall_plot(shap_values, expected_value, X, feature_names,
                                max_display=10):
    """Create SHAP waterfall plot showing feature contributions."""
    try:
        if isinstance(shap_values, np.ndarray) and shap_values.ndim == 2:
            shap_values = shap_values[0]

        expected_val = (expected_value
                       if not isinstance(expected_value, (list, np.ndarray))
                       else expected_value[1] if hasattr(expected_value, '__len__') and len(expected_value) > 1
                       else expected_value)

        fig, ax = plt.subplots(figsize=(8, max(6, max_display * 0.35)))

        # Sort features by absolute SHAP value
        abs_shap = np.abs(shap_values)
        top_indices = np.argsort(abs_shap)[-max_display:]

        features = [feature_names[i] for i in top_indices]
        values = shap_values[top_indices]

        # Create horizontal bar chart
        colors = ['#e74c3c' if v > 0 else '#3498db' for v in values]

        y_pos = range(len(features))
        ax.barh(y_pos, values, color=colors, alpha=0.8, edgecolor='white')

        # Add base value line
        ax.axvline(x=expected_val, color='gray', linestyle='--', alpha=0.5,
                  label=f'Base value: {expected_val:.3f}')

        ax.set_yticks(y_pos)
        ax.set_yticklabels(features)
        ax.set_xlabel('SHAP Value (Impact on Prediction)')
        ax.set_title('Feature Contributions to AKI Risk Prediction', fontweight='bold')
        ax.legend(loc='lower right')
        ax.axvline(x=0, color='black', linewidth=0.5)

        plt.tight_layout()
        return fig

    except Exception as e:
        logger.error(f"Waterfall plot creation failed: {e}")
        return None


def get_clinical_explanation(feature, shap_value, direction):
    """
    Generate natural language clinical explanation for a SHAP value.

    Args:
        feature: Feature name
        shap_value: SHAP value (magnitude and direction)
        direction: 'positive' (increases risk) or 'negative' (decreases risk)

    Returns:
        explanation: Chinese clinical explanation string
    """
    explanations = {
        '年龄': {
            'positive': '年龄较大增加了AKI风险。随着年龄增长，肾小球滤过率生理性下降，肾储备功能减退。',
            'negative': '年龄较轻是保护因素，肾脏储备功能较好。',
        },
        'APACHEII': {
            'positive': 'APACHE II评分较高提示病情较重，多器官功能障碍风险增加。',
            'negative': 'APACHE II评分较低提示病情较轻，总体预后较好。',
        },
        '术前Scr': {
            'positive': '术前血肌酐升高可能提示肾储备功能下降或已存在肾损伤，显著增加AKI风险。',
            'negative': '术前血肌酐正常提示基线肾功能良好。',
        },
        '术前eGFR': {
            'positive': '术前eGFR降低是CKD的标志，术后AKI风险显著增加。',
            'negative': '术前eGFR正常提示肾功能储备充足，是重要的保护因素。',
        },
        '术中失血量': {
            'positive': '术中大量失血导致肾灌注不足和缺血性损伤，增加AKI风险。',
            'negative': '术中失血量少，肾脏灌注维持良好。',
        },
        '手术时间': {
            'positive': '手术时间较长意味着更长时间的麻醉和血流动力学波动。',
            'negative': '手术时间较短，手术创伤和应激反应较小。',
        },
        '术前CRP': {
            'positive': '术前CRP升高提示存在炎症状态，增加术后氧化应激和肾损伤风险。',
            'negative': '术前CRP正常提示无显著炎症反应。',
        },
        '术前NLR': {
            'positive': '高NLR反映促炎状态，与术后AKI独立相关。',
            'negative': 'NLR正常提示免疫平衡状态良好。',
        },
    }

    # Generic fallback
    if feature not in explanations:
        if 'Scr' in feature or '肌酐' in feature:
            return '血肌酐是评估肾功能的核心指标。' + ('升高增加AKI风险。' if direction == 'positive' else '正常范围内有助于降低风险。')
        if 'eGFR' in feature:
            return 'eGFR反映肾小球滤过功能。' + ('降低是AKI的重要危险因素。' if direction == 'positive' else '正常是保护因素。')
        return '该特征' + ('增加了' if direction == 'positive' else '降低了') + 'AKI风险，贡献度为{:.4f}。'.format(abs(shap_value))

    exp = explanations[feature].get(direction, explanations[feature].get('positive', ''))
    return exp


def render_shap_explanation_ui(prob, shap_values, expected_value, X, feature_names):
    """Render complete SHAP explanation UI in Streamlit."""
    st.markdown("### 🔍 个体化风险解释 (SHAP)")

    col1, col2 = st.columns([2, 1])

    with col1:
        # Waterfall plot
        waterfall_fig = create_shap_waterfall_plot(
            shap_values, expected_value, X, feature_names
        )
        if waterfall_fig:
            st.pyplot(waterfall_fig)
        else:
            st.warning("SHAP图表生成失败。请确认模型已正确训练。")

    with col2:
        st.markdown("#### 📊 风险贡献分解")
        st.markdown(f"**基线风险:** {expected_value:.3f}")

        # Top contributing features
        if isinstance(shap_values, np.ndarray):
            if shap_values.ndim == 2:
                vals = shap_values[0]
            else:
                vals = shap_values
        else:
            vals = np.array(shap_values)

        top_idx = np.argsort(np.abs(vals))[-5:][::-1]

        for rank, idx in enumerate(top_idx, 1):
            feat = feature_names[idx] if idx < len(feature_names) else f'F{idx}'
            val = vals[idx]
            direction = '🔴' if val > 0 else '🟢'
            impact = '增加风险' if val > 0 else '降低风险'

            with st.expander(f"{direction} #{rank}: {feat} ({impact}, |SHAP|={abs(val):.4f})"):
                explanation = get_clinical_explanation(feat, val, 'positive' if val > 0 else 'negative')
                st.write(explanation)

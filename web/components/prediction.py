"""
AKI Prediction System - Prediction Component
Handles model inference, risk stratification, and result formatting.
"""
import numpy as np
import pandas as pd
import joblib
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.utils.helpers import logger


def load_model_and_scaler(model_name='xgboost'):
    """Load trained model and associated preprocessor."""
    model_dir = Path(__file__).parent.parent.parent / 'models'
    model_path = model_dir / f'{model_name}.pkl'
    scaler_path = model_dir / 'scaler.pkl'
    feature_path = model_dir / 'feature_names.txt'

    model = None
    scaler = None
    feature_names = None

    if model_path.exists():
        model = joblib.load(model_path)
        logger.info(f"Loaded model: {model_name}")

    if scaler_path.exists():
        scaler = joblib.load(scaler_path)

    if feature_path.exists():
        with open(feature_path) as f:
            feature_names = [line.strip() for line in f]

    return model, scaler, feature_names


def prepare_input_data(input_dict, feature_names, scaler=None):
    """
    Prepare input data for model prediction.
    Converts input dict to scaled feature vector.
    """
    # Create feature vector
    features = {}
    for name in feature_names:
        if name in input_dict:
            features[name] = input_dict[name]
        else:
            features[name] = 0  # Default for missing features

    X = pd.DataFrame([features])

    if scaler is not None:
        try:
            # Only scale numeric columns
            numeric_cols = X.select_dtypes(include=[np.number]).columns
            X[numeric_cols] = scaler.transform(X[numeric_cols])
        except Exception as e:
            logger.warning(f"Scaling failed: {e}")

    return X


def predict_aki(model, X, threshold=0.5):
    """
    Predict AKI risk.
    Returns probability, prediction, and class.
    """
    if hasattr(model, 'predict_proba'):
        prob = model.predict_proba(X)[:, 1][0]
    else:
        prob = float(model.predict(X)[0])

    pred = int(prob >= threshold)
    risk_level = get_risk_level(prob)

    return prob, pred, risk_level


def get_risk_level(probability, low_threshold=0.3, high_threshold=0.7):
    """Classify risk level."""
    if probability < low_threshold:
        return 'Low'
    elif probability < high_threshold:
        return 'Medium'
    else:
        return 'High'


def get_top_risk_factors(model, X, feature_names, shap_values=None, top_n=5):
    """
    Extract top risk factors from SHAP values or feature importance.
    """
    if shap_values is not None:
        # Use SHAP for individual explanation
        feature_impact = np.abs(shap_values[0])
        top_indices = np.argsort(feature_impact)[::-1][:top_n]

        factors = []
        for idx in top_indices:
            factors.append({
                'feature': feature_names[idx],
                'importance': float(feature_impact[idx]),
                'direction': 'positive' if shap_values[0][idx] > 0 else 'negative'
            })
        return factors

    # Fallback: model feature importance
    if hasattr(model, 'feature_importances_'):
        importance = model.feature_importances_
        top_indices = np.argsort(importance)[::-1][:top_n]

        factors = []
        for idx in top_indices:
            factors.append({
                'feature': feature_names[idx] if feature_names else f'Feature_{idx}',
                'importance': float(importance[idx]),
                'direction': 'positive'
            })
        return factors

    return [{'feature': 'Model not available', 'importance': 0, 'direction': 'N/A'}]


# ============================================
# Clinical Recommendations Database
# ============================================
CLINICAL_RECOMMENDATIONS = {
    'Low': {
        'summary': '患者AKI风险较低，建议常规监测。',
        'monitoring': [
            '术后每12小时记录尿量',
            '术后第1、3天复查Scr和eGFR',
            '关注血流动力学变化'
        ],
        'prevention': [
            '维持充足水化',
            '避免使用肾毒性药物（NSAIDs、氨基糖苷类、造影剂）',
            '维持MAP > 65 mmHg'
        ],
        'follow_up': '如出现少尿（<0.5ml/kg/h 持续>6h）或Scr升高，及时复查。',
        'kdigo_stage': 'KDIGO Stage 0 — No AKI',
    },
    'Medium': {
        'summary': '患者存在中度AKI风险，建议加强监测并启动预防性干预。',
        'monitoring': [
            '每6小时监测尿量及Scr变化趋势',
            '每日复查Scr、eGFR、电解质',
            '持续监测血流动力学（CVP、MAP）',
            '监测血气分析（pH、HCO3、Lactate）'
        ],
        'prevention': [
            '目标导向液体治疗，维持尿量 > 0.5 ml/kg/h',
            '审慎使用利尿剂，避免容量不足',
            '优化心输出量，维持肾脏灌注',
            '请肾内科会诊评估'
        ],
        'follow_up': '持续监测至术后72小时，如病情加重按高风险方案处理。',
        'kdigo_stage': 'KDIGO Stage 1 Risk',
    },
    'High': {
        'summary': '⚠️ 患者AKI高风险！建议立即启动全面干预，多学科协作管理。',
        'monitoring': [
            '每小时记录尿量，必要时留置导尿管',
            '持续有创动脉血压监测',
            '每4-6小时复查Scr、eGFR、电解质',
            '每日肾脏超声评估'
        ],
        'prevention': [
            '启动KDIGO Bundle：优化容量状态 + 停用肾毒性药物 + 维持肾灌注压',
            '功能性血流动力学监测指导液体管理',
            '严格血糖控制（110-150 mg/dL）',
            '考虑使用肾脏保护药物'
        ],
        'follow_up': '紧急肾内科会诊，准备RRT（肾脏替代治疗）评估。ICU监护。',
        'kdigo_stage': 'KDIGO Stage 2-3 Risk — High Alert',
    },
}

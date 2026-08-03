# -*- coding: utf-8 -*-
"""Shared project configuration and leakage rules.

All entry scripts import from here so the feature scheme, outcome exclusions,
and risk thresholds stay consistent across training, evaluation, and the web app.
"""

TARGET = 'AKI分组'

# Identifiers that must never enter the model.
ID_COLUMNS = ['住院号', '姓名']

# KDIGO creatinine-based diagnostic features: using these to predict AKI is
# "answering with the answer", so they are always excluded.
KDIGO_LEAK_COLUMNS = [
    '术后48hSCr', '术后48heGFR',
    '术后7dSCr', '术后7deGFR',
    '术后48hUrea', '术后7dUrea',
]

# Outcome / post-outcome features not available at the ICU-admission prediction
# point (and often equal to the endpoint itself).
OUTCOME_KEYWORDS = ['住院费', '住院天', '住院日', '机械通气', 'ICU住院']
POST_7D_KEYWORD = '术后7d'
VENTILATION_KEYWORD = '术后通气'

# Unified risk bands used by the web UI, PDF report, and risk-report module.
RISK_LOW = 0.3
RISK_HIGH = 0.7


def is_leakage(col_name) -> bool:
    """Return True for features that must be excluded from modeling."""
    name = str(col_name).strip()
    if name in ID_COLUMNS or name in (TARGET, 'AKI分期'):
        return True
    if any(kw in name for kw in KDIGO_LEAK_COLUMNS):
        return True
    if any(kw in name for kw in OUTCOME_KEYWORDS):
        return True
    if POST_7D_KEYWORD in name:
        return True
    if VENTILATION_KEYWORD in name:
        return True
    return False


def classify_feature_timing(col_name) -> str:
    """Classify a feature as preop / intraop / ICU / postop for reporting."""
    name = str(col_name).strip()
    if name.startswith('ICU'):
        return 'icu'
    if name.startswith('术中'):
        return 'intraop'
    if name.startswith('术后'):
        return 'postop'
    return 'preop'


# -*- coding: utf-8 -*-
"""Shared project configuration and leakage rules.

All entry scripts import from here so the feature scheme, outcome exclusions,
and risk thresholds stay consistent across training, evaluation, and the web app.
"""

import re

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

# The literal list above only catches the exact spellings in the current
# workbook. These patterns close the gap: a rename such as 术后48h肌酐, a case
# change such as 术后48hSCR, or a newly collected 是否行RRT column used to sail
# straight into the feature matrix (measured: adding one 术后48h肌酐 column took
# honest CV AUC from 0.72 to 0.93 while is_leakage() still returned False).
# Matched case-insensitively against the whitespace-stripped name.
LEAK_PATTERNS = [
    # Any AKI/KDIGO grading or diagnosis column is the label itself.
    r'(aki|kdigo)\s*[_-]?\s*(分组|分期|分级|阶段|诊断|stage|grade|group)',
    r'^(是否)?(发生|出现)?aki$',
    r'^kdigo$',
    # Post-operative creatinine in any spelling, plus derived ratios/deltas.
    r'(术后|postop|post[_-]?op).*(scr|肌酐|egfr)',
    r'(scr|肌酐|egfr).*(升高|下降|变化|倍数|比值|峰值|最高|最低|delta|ratio|change)',
    r'(升高|下降|变化|倍数|比值|峰值|最高).*(scr|肌酐|egfr)',
    # Renal replacement therapy is a KDIGO stage-3 criterion, i.e. an outcome.
    r'(rrt|crrt|hemodialysis|血液净化|透析|肾脏?替代)',
    # Post-operative urine output is the other KDIGO criterion.
    r'(术后|postop).*(尿量|urine)',
    # Hard endpoints.
    r'死亡|mortality|survival|生存|临床结局|随访结局',
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
    if name in ID_COLUMNS or '姓名' in name or '住院号' in name or name in (TARGET, 'AKI分期'):
        return True
    if any(kw in name for kw in KDIGO_LEAK_COLUMNS):
        return True
    if any(kw in name for kw in OUTCOME_KEYWORDS):
        return True
    if POST_7D_KEYWORD in name or '术后7天' in name:
        return True
    if VENTILATION_KEYWORD in name:
        return True
    # Pattern pass: catches spelling/case variants the literal lists miss.
    # Whitespace is removed first so "AKI 分组" and "术后48h SCr" are caught too.
    compact = re.sub(r'\s+', '', name).casefold()
    if any(re.search(p, compact) for p in LEAK_PATTERNS):
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


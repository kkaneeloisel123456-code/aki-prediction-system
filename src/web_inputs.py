# -*- coding: utf-8 -*-
"""Single source of truth for the web prediction form's model-feature inputs."""

# Every one of the 35 model features must have a corresponding input in the
# Web form.  Keeping the list here lets tests catch drift between the
# trained feature file and the UI.
MODEL_FEATURE_INPUT_KEYS = [
    'ICUAdmSCr',
    '术后β2MG',
    'ICUAdmeGFR',
    '术前hsTn',
    '术后Mb',
    '术后Lactate',
    '术后hsTn',
    '手术时间',
    '术后Urea',
    '术前β2MG',
    '术前SBP',
    '术后UA',
    '术后MONO',
    '术前PLR',
    '术后PaO2',
    '术后PLR',
    '术后PLT',
    '术前eGFR',
    '术前WBC',
    'APACHEII',
    '术中晶体液量',
    '术前RBP',
    '术后CRP',
    '术前PLT',
    '术后Alb',
    '术中失血量',
    '术前PaO2',
    '术后CAR',
    '术后BE',
    '术前NEUT',
    '术前BNP',
    '术前CKMBCK',
    '术前LMR',
    '术后BNP',
    '术前Scr',
]

# Fields that used to be collected by the form but are outcome/post-outcome
# variables.  They must never be requested at the ICU-admission prediction point.
OUTCOME_INPUT_KEYS = ['总住院天数', '总住院费用', 'ICU住院天数', '术后通气时间']

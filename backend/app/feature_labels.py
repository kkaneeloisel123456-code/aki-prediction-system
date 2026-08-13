# -*- coding: utf-8 -*-
"""Chinese display labels, units and reference info for the 35 model features."""
from __future__ import annotations

FEATURE_LABELS = {
    "ICUAdmSCr":  ("ICU 入院肌酐", "μmol/L", "参考 44–133", "number"),
    "ICUAdmeGFR": ("ICU 入院 eGFR", "mL/min/1.73m²", "由肌酐估算", "number"),
    "术前Scr":     ("术前肌酐", "μmol/L", "参考 44–133", "number"),
    "术前eGFR":    ("术前 eGFR", "mL/min/1.73m²", "≥90 正常", "number"),
    "术前SBP":     ("术前收缩压", "mmHg", "参考 90–140", "number"),
    "术前WBC":     ("术前白细胞", "×10⁹/L", "参考 3.5–9.5", "number"),
    "术前NEUT":    ("术前中性粒细胞", "×10⁹/L", "参考 1.8–6.3", "number"),
    "术前PLT":     ("术前血小板", "×10⁹/L", "参考 125–350", "number"),
    "术前PLR":     ("术前 PLR", "", "血小板/淋巴细胞比值", "number"),
    "术前LMR":     ("术前 LMR", "", "淋巴细胞/单核细胞比值", "number"),
    "术前β2MG":    ("术前 β2 微球蛋白", "mg/L", "参考 1.0–3.0", "number"),
    "术前hsTn":    ("术前高敏肌钙蛋白", "pg/mL", "升高提示心肌损伤", "number"),
    "术前BNP":     ("术前 BNP", "pg/mL", "<100 正常", "number"),
    "术前CKMBCK":  ("术前 CK-MB/CK 比值", "", "参考 <0.05", "number"),
    "术前RBP":     ("术前视黄醇结合蛋白", "mg/L", "参考 25–70", "number"),
    "术前PaO2":    ("术前氧分压", "mmHg", "参考 80–100", "number"),
    "APACHEII":    ("APACHE II 评分", "分", "0–71，越高越重", "number"),
    "手术时间":     ("手术时间", "min", "", "number"),
    "术中失血量":   ("术中失血量", "mL", "", "number"),
    "术中晶体液量": ("术中晶体液量", "mL", "", "number"),
    "术后Lactate": ("术后乳酸", "mmol/L", "参考 0.5–2.2", "number"),
    "术后β2MG":    ("术后 β2 微球蛋白", "mg/L", "", "number"),
    "术后Mb":      ("术后肌红蛋白", "ng/mL", "参考 <70", "number"),
    "术后Urea":    ("术后尿素", "mmol/L", "参考 2.9–8.2", "number"),
    "术后UA":      ("术后尿酸", "μmol/L", "参考 208–428", "number"),
    "术后Alb":     ("术后白蛋白", "g/L", "参考 35–55", "number"),
    "术后BE":      ("术后碱剩余", "mmol/L", "参考 -3–+3", "number"),
    "术后hsTn":    ("术后高敏肌钙蛋白", "pg/mL", "", "number"),
    "术后BNP":     ("术后 BNP", "pg/mL", "", "number"),
    "术后CRP":     ("术后 C 反应蛋白", "mg/L", "<10 正常", "number"),
    "术后CAR":     ("术后 CRP/Alb 比值", "", "炎症/营养指标", "number"),
    "术后MONO":    ("术后单核细胞", "×10⁹/L", "参考 0.1–0.6", "number"),
    "术后PaO2":    ("术后氧分压", "mmHg", "参考 80–100", "number"),
    "术后PLT":     ("术后血小板", "×10⁹/L", "参考 125–350", "number"),
    "术后PLR":     ("术后 PLR", "", "血小板/淋巴细胞比值", "number"),
}

def get_label(name: str) -> dict:
    info = FEATURE_LABELS.get(name)
    if info:
        label, unit, ref, ftype = info
        return {"label": label, "unit": unit, "reference": ref, "input": ftype}
    return {"label": name, "unit": "", "reference": "", "input": "number"}

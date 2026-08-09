# -*- coding: utf-8 -*-
"""Generate an AKI risk PDF report from a prediction result."""
from __future__ import annotations

import io
from datetime import datetime
from typing import Any, Dict, List

from .config import CJK_FONT


def _setup_font(pdf):
    """Register the bundled CJK font so Linux/Cloud renders Chinese."""
    if CJK_FONT.exists():
        pdf.add_font("CJK", "", str(CJK_FONT))
        pdf.add_font("CJK", "B", str(CJK_FONT))
        return "CJK"
    # As a last resort on a fully Chinese-capable system (no bundled font):
    # fall back to a core font. Chinese may not render.
    return "Helvetica"


def generate_pdf(patient: Dict[str, Any], result: Dict[str, Any]) -> bytes:
    """Return PDF bytes for one prediction.

    patient: {'id', 'name', 'age', ...} metadata (only id/age used).
    result: output of predictor.predict().
    """
    from fpdf import FPDF

    pdf = FPDF()
    font = _setup_font(pdf)
    pdf.add_page()

    prob = result["probability"]
    band = result["risk_level"]
    colors = {"高": (231, 76, 60), "中": (243, 156, 18), "低": (39, 174, 96)}
    r, g, b = colors.get(band, (128, 128, 128))

    pdf.set_font(font, "B", 20)
    pdf.cell(0, 12, "急性肾损伤（AKI）风险预测报告", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font(font, "", 10)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    pdf.cell(0, 7, f"报告时间：{now}", align="C", new_x="LMARGIN", new_y="NEXT")
    pid = patient.get("id") or patient.get("patient_id") or "N/A"
    pdf.cell(0, 7, f"患者编号：{pid}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)

    # Risk box
    pdf.set_fill_color(r, g, b)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font(font, "B", 28)
    pdf.cell(0, 22, f"{band}风险  {prob*100:.1f}%", align="C", fill=True,
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)
    pdf.set_font(font, "", 9)
    note = "（概率已做OOF Isotonic校准）" if result.get("calibrated") else ""
    pdf.cell(0, 6, f"风险分层：低<0.30 / 中0.30–0.70 / 高≥0.70   {note}",
             align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)

    # SHAP top contributors
    shap: List[Dict[str, Any]] = result.get("shap_values", [])[:12]
    if shap:
        pdf.set_font(font, "B", 13)
        pdf.cell(0, 10, "主要影响因素（SHAP）", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(font, "", 10)
        pdf.cell(70, 8, "特征", border=1)
        pdf.cell(35, 8, "当前值", border=1, align="C")
        pdf.cell(35, 8, "贡献方向", border=1, align="C")
        pdf.cell(40, 8, "SHAP值", border=1, align="C", new_x="LMARGIN", new_y="NEXT")
        for item in shap:
            direction = "↑ 升高风险" if item["direction"] == "risk" else "↓ 降低风险"
            pdf.cell(70, 7, str(item["feature"])[:24], border=1)
            pdf.cell(35, 7, f"{item['value']:.2f}", border=1, align="C")
            pdf.cell(35, 7, direction, border=1, align="C")
            pdf.cell(40, 7, f"{item['shap']:+.4f}", border=1, align="C",
                     new_x="LMARGIN", new_y="NEXT")
        pdf.ln(6)

    pdf.set_font(font, "", 8)
    pdf.set_text_color(128, 128, 128)
    pdf.multi_cell(0, 4,
        "免责声明：本报告由AI预测系统生成，仅供学术研究与临床参考，"
        "不能作为临床决策的唯一依据，请以主治医生判断为准。")

    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()

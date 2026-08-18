# -*- coding: utf-8 -*-
"""Generate an AKI risk PDF report from a prediction result."""
from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Font resolution (self-contained, no cross-module Path variable needed)
# ---------------------------------------------------------------------------

# pdf.py lives at  backend/app/pdf.py
# parent       -> backend/app
# parent.parent -> backend
_FONTS_DIR: Path = Path(__file__).resolve().parent.parent / "assets" / "fonts"

_FONT_CANDIDATES: list[Path] = [
    _FONTS_DIR / "CJK-Regular.ttf",        # SimHei – thicker strokes
    _FONTS_DIR / "NotoSansSC-Regular.ttf",
    Path(r"C:/Windows/Fonts/simhei.ttf"),
    Path(r"C:/Windows/Fonts/NotoSansSC-VF.ttf"),
]


def _resolve_font() -> Path:
    """Return the first existing CJK TTF font path from the candidate list."""
    for p in _FONT_CANDIDATES:
        if p.exists():
            return p
    return _FONT_CANDIDATES[0]  # may not exist; _setup_font falls back to Helvetica


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _setup_font(pdf) -> str:
    """Register the CJK TTF font and return the font family name.

    fpdf2 needs TTF for correct Unicode / CJK glyph advance-width metrics.
    OTF is silently accepted but produces wrong widths -> text overlap, so it
    is intentionally excluded. Falls back to 'Helvetica' (ASCII-only) when no
    TTF font file is available.
    """
    font_path = _resolve_font()
    if font_path.exists() and font_path.suffix.lower() == ".ttf":
        pdf.add_font("CJK", style="", fname=str(font_path))
        pdf.add_font("CJK", style="B", fname=str(font_path))
        return "CJK"
    # Helvetica cannot render Chinese and would crash mid-report with an
    # encoding exception - fail fast with an actionable message instead.
    raise RuntimeError(
        "未找到中文字体（backend/assets/fonts/*.ttf 或系统 simhei.ttf），无法生成中文 PDF。"
    )


def _effective_width(pdf) -> float:
    """Return the usable line width in mm (page width minus both margins)."""
    return pdf.w - pdf.l_margin - pdf.r_margin


def _risk_color(band: str) -> tuple[int, int, int]:
    """Return (R, G, B) for the risk band."""
    return {"高": (192, 57, 43), "中": (211, 84, 0), "低": (39, 174, 96)}.get(
        band, (100, 100, 100)
    )


def _risk_label_en(band: str) -> str:
    return {"高": "HIGH RISK", "中": "MODERATE RISK", "低": "LOW RISK"}.get(band, band)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_pdf(patient: Dict[str, Any], result: Dict[str, Any]) -> bytes:
    """Return PDF bytes for one AKI prediction.

    Args:
        patient: dict with keys 'id', 'age', etc.  Only 'id' is required.
        result:  output of predictor.predict(), must contain at least
                 'probability', 'risk_level', 'shap_values', 'calibrated'.
    """
    from fpdf import FPDF

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(left=20, top=20, right=20)
    pdf.set_auto_page_break(auto=True, margin=20)
    font = _setup_font(pdf)
    pdf.add_page()

    W = _effective_width(pdf)  # ~170 mm for A4 with 20 mm margins

    prob: float = result["probability"]
    band: str = result["risk_level"]
    r, g, b = _risk_color(band)
    pid: str = str(patient.get("id") or patient.get("patient_id") or "N/A")
    now: str = datetime.now().strftime("%Y-%m-%d %H:%M")
    calibrated: bool = bool(result.get("calibrated", False))

    # -----------------------------------------------------------------------
    # Header: title + meta
    # -----------------------------------------------------------------------
    pdf.set_font(font, "B", 18)
    pdf.set_text_color(30, 30, 60)
    pdf.cell(W, 10, "急性肾损伤（AKI）风险预测报告", align="C",
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    pdf.set_font(font, "", 9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(W, 6, f"报告时间：{now}    患者编号：{pid}", align="C",
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    # -----------------------------------------------------------------------
    # Risk banner
    # -----------------------------------------------------------------------
    pdf.set_fill_color(r, g, b)
    pdf.set_text_color(255, 255, 255)

    pdf.set_font(font, "B", 22)
    pdf.cell(W, 18,
             f"{band}风险   {prob * 100:.1f}%   ({_risk_label_en(band)})",
             align="C", fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    pdf.set_text_color(80, 80, 80)
    pdf.set_font(font, "", 8)
    note = "（概率已做 OOF Isotonic 校准）" if calibrated else "（未校准原始概率）"
    pdf.cell(W, 5,
             f"风险分层阈值：低 < 0.30  /  中 0.30-0.70  /  高 >= 0.70   {note}",
             align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)

    # -----------------------------------------------------------------------
    # Progress bar (visual probability gauge)
    # -----------------------------------------------------------------------
    bar_h = 5
    pdf.set_fill_color(220, 220, 220)
    pdf.rect(pdf.l_margin, pdf.get_y(), W, bar_h, style="F")
    pdf.set_fill_color(r, g, b)
    if prob > 0:
        pdf.rect(pdf.l_margin, pdf.get_y(), W * prob, bar_h, style="F")
    pdf.ln(bar_h + 4)

    # -----------------------------------------------------------------------
    # SHAP top contributors table
    # -----------------------------------------------------------------------
    shap_items: List[Dict[str, Any]] = result.get("shap_values", [])[:12]
    if shap_items:
        pdf.set_text_color(30, 30, 60)
        pdf.set_font(font, "B", 12)
        pdf.cell(W, 8, "主要影响因素（SHAP 贡献值，基于 XGBoost 子模型）",
                 new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

        col: list[float] = [W * 0.38, W * 0.17, W * 0.25, W * 0.20]
        row_h = 7

        # Header row
        pdf.set_font(font, "B", 9)
        pdf.set_fill_color(50, 50, 90)
        pdf.set_text_color(255, 255, 255)
        for i, hdr in enumerate(["特征名称", "当前值", "贡献方向", "SHAP 值"]):
            pdf.cell(col[i], row_h, hdr, border=0, align="C", fill=True)
        pdf.ln(row_h)

        # Data rows
        pdf.set_font(font, "", 9)
        for idx, item in enumerate(shap_items):
            fill_row = idx % 2 == 0
            bg = (245, 248, 255) if fill_row else (255, 255, 255)
            pdf.set_fill_color(*bg)
            pdf.set_text_color(40, 40, 40)

            direction = "升高风险" if item["direction"] == "risk" else "降低风险"
            dir_color: tuple[int, int, int] = (180, 30, 30) if item["direction"] == "risk" else (30, 140, 60)

            # Feature name – truncate to safe char count
            feat_str = str(item["feature"])
            max_chars = max(8, int(col[0] / 3.5))
            if len(feat_str) > max_chars:
                feat_str = feat_str[: max_chars - 1] + "..."

            pdf.cell(col[0], row_h, feat_str, border="B", align="L", fill=True)

            try:
                val_str = f"{float(item['value']):.2f}"
            except (TypeError, ValueError):
                val_str = str(item["value"])
            pdf.cell(col[1], row_h, val_str, border="B", align="C", fill=True)

            pdf.set_text_color(*dir_color)
            pdf.cell(col[2], row_h, direction, border="B", align="C", fill=True)

            pdf.set_text_color(40, 40, 40)
            pdf.cell(col[3], row_h, f"{item['shap']:+.4f}", border="B", align="C",
                     fill=True, new_x="LMARGIN", new_y="NEXT")

        pdf.ln(8)

    # -----------------------------------------------------------------------
    # Clinical notes
    # -----------------------------------------------------------------------
    pdf.set_text_color(30, 30, 60)
    pdf.set_font(font, "B", 11)
    pdf.cell(W, 7, "临床参考建议", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)

    tips: Dict[str, List[str]] = {
        "高": [
            "立即通知肾内科/ICU团队会诊评估",
            "每2小时监测尿量，每6小时复查 Scr/eGFR/电解质",
            "目标导向液体治疗，维持尿量 > 0.5 ml/kg/h",
            "避免肾毒性药物（NSAIDs、氨基糖苷类等）",
            "评估是否需要肾脏替代治疗（RRT）准备",
        ],
        "中": [
            "密切观察，每6小时监测尿量和 Scr 变化",
            "目标导向液体治疗，维持尿量 > 0.5 ml/kg/h",
            "每日复查 Scr、eGFR、电解质、血气",
            "避免肾毒性药物",
        ],
        "低": [
            "常规监测，每日复查肾功能指标",
            "保持充分水化，维持尿量 > 0.5 ml/kg/h",
            "如出现尿量减少或 Scr 升高，及时升级监测级别",
        ],
    }

    pdf.set_font(font, "", 9)
    pdf.set_text_color(50, 50, 50)
    for tip in tips.get(band, tips["低"]):
        pdf.cell(5, 6, "-")
        pdf.cell(W - 5, 6, tip, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    # -----------------------------------------------------------------------
    # Model info box
    # -----------------------------------------------------------------------
    pdf.set_font(font, "", 8)
    pdf.set_text_color(120, 120, 120)
    pdf.set_fill_color(245, 245, 248)
    for line in [
        "模型：Voting Ensemble (LR×2 + RF×2 + XGB×1 + ET×1) | 特征：35 个 (RF Top35)",
        "验证：5折×10次=50次嵌套CV  AUC = 0.8096 +/- 0.0428 | Bootstrap 95%CI [0.754, 0.842]",
        "校准：OOF Isotonic 回归 | 校准后 Brier = 0.168",
    ]:
        pdf.cell(W, 5, line, align="C", fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    # -----------------------------------------------------------------------
    # Footer disclaimer
    # -----------------------------------------------------------------------
    pdf.set_font(font, "", 8)
    pdf.set_text_color(160, 160, 160)
    pdf.multi_cell(
        W, 4,
        "【免责声明】本报告由 AKI 智能预测系统自动生成，仅供学术研究与临床参考，"
        "不能作为临床诊断或治疗决策的唯一依据。"
        "所有临床决策应由具备资质的医疗专业人员结合患者整体情况综合判断。",
        align="C",
    )

    # -----------------------------------------------------------------------
    # Output
    # -----------------------------------------------------------------------
    buf = io.BytesIO()
    buf.write(pdf.output())
    return buf.getvalue()

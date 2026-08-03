"""
AKI Prediction System - PDF Report Generation Component
Auto-generates individualized AKI risk assessment reports.
"""
import os
from pathlib import Path
from datetime import datetime
import numpy as np
import matplotlib.pyplot as plt
from fpdf import FPDF
import sys
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.utils.helpers import logger

CN_RISK_LEVEL = {
    'Low': '低风险',
    'Low-Medium': '低-中风险',
    'Medium': '中风险',
    'Medium-High': '中-高风险',
    'High': '高风险',
}

CN_RECOMMENDATIONS = {
    '低风险': {
        'monitoring': ['每 12 小时记录尿量', '术后第 1、3 天复查血肌酐与 eGFR', '常规监测血流动力学状态'],
        'prevention': ['维持充足液体入量', '避免肾毒性药物（NSAIDs、氨基糖苷类、造影剂）', '维持平均动脉压 > 65 mmHg'],
        'follow_up': '若出现少尿（<0.5 ml/kg/h 超过 6 小时）或血肌酐升高，需升级监测。',
        'patient_note': '您的 AKI 风险较低。请按医嘱保持饮水，避免自行服用止痛或消炎药物，并关注术后尿量。',
    },
    '低-中风险': {
        'monitoring': ['每 8-12 小时监测尿量', '每日复查血肌酐、eGFR 与电解质', '记录液体出入量'],
        'prevention': ['目标导向液体治疗', '核查并停用潜在肾毒性药物', '维持肾脏灌注压'],
        'follow_up': '至少监测至术后第 3 天。',
        'patient_note': '您的 AKI 风险处于低-中水平。请配合医护人员记录尿量，出现尿量明显减少或水肿时及时告知。',
    },
    '中风险': {
        'monitoring': ['每 6 小时监测尿量', '每日复查血肌酐、eGFR、电解质与血气', '持续监测血流动力学（CVP、MAP）'],
        'prevention': ['目标导向液体治疗，维持尿量 > 0.5 ml/kg/h', '谨慎使用利尿剂，避免血容量不足', '优化心输出量，维持肾脏灌注', '建议请肾内科会诊'],
        'follow_up': '监测至术后第 5 天，病情加重时升级监护。',
        'patient_note': '您的 AKI 风险为中等水平。请严格遵医嘱，勿擅自停药或加药，尤其避免使用止痛药、退烧药等可能伤肾的药物。',
    },
    '中-高风险': {
        'monitoring': ['留置尿管，每小时记录尿量', '每 12 小时复查血肌酐与 eGFR', '有创动脉血压监测', '每日肾脏超声评估'],
        'prevention': ['启动 KDIGO Bundle：优化容量 + 停用肾毒性药物 + 维持肾脏灌注', '功能性血流动力学监测指导液体管理', '严格血糖控制', '强烈建议肾内科会诊'],
        'follow_up': '建议 ICU 级别监测，准备肾脏替代治疗条件。',
        'patient_note': '您的 AKI 风险偏高。医护人员会加强监护，请配合治疗，若出现尿量明显减少、恶心、水肿或呼吸困难，请立即告知医护人员。',
    },
    '高风险': {
        'monitoring': ['每小时记录尿量（必须留置尿管）', '持续有创动脉血压监测', '每 4-6 小时复查血肌酐、eGFR、电解质', '每日肾脏超声', '持续心电监护'],
        'prevention': ['全面启动 KDIGO Bundle', '功能性血流动力学监测', '严格血糖控制', '评估肾脏保护药物', '启动多学科团队'],
        'follow_up': '急诊肾内科会诊，准备肾脏替代治疗，建议 ICU 收治。',
        'patient_note': '您的 AKI 风险较高。请理解并配合强化监护和干预措施，这是保护肾功能的重要时期。',
    },
}


def _get(info, *keys, default='N/A'):
    """从 patient_info 中按多个候选键取值。"""
    for key in keys:
        if key in info and info[key] not in (None, '', 'N/A'):
            return info[key]
    return default


# ============================================
# Chinese PDF Report Generator
# ============================================
class AKIReportPDF(FPDF):
    """Custom PDF class with Chinese support and AKI report template."""

    def __init__(self):
        super().__init__('P', 'mm', 'A4')
        # Add Unicode font for Chinese
        self._setup_fonts()
        self.set_auto_page_break(True, 20)

    def _setup_fonts(self):
        """Setup Chinese-capable fonts."""
        # Try common Chinese font paths on Windows
        font_paths = [
            'C:/Windows/Fonts/simhei.ttf',
            'C:/Windows/Fonts/msyh.ttf',
            'C:/Windows/Fonts/simsun.ttc',
            '/System/Library/Fonts/PingFang.ttc',
            '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
        ]

        for path in font_paths:
            if os.path.exists(path):
                self.add_font('CJK', '', path, uni=True)
                self.add_font('CJK', 'B', path, uni=True)
                logger.info(f"Using font: {path}")
                return

        logger.warning("No CJK font found. Chinese characters may not render.")
        self.add_font('CJK', '', 'Helvetica')

    def header(self):
        """Page header."""
        self.set_font('CJK', 'B', 10)
        self.set_text_color(52, 152, 219)
        self.cell(0, 8, '急性肾损伤（AKI）风险预测评估报告', align='C', new_x="LMARGIN", new_y="NEXT")
        self.line(self.get_x(), self.get_y(), self.get_x() + 190, self.get_y())
        self.ln(3)

    def footer(self):
        """Page footer."""
        self.set_y(-15)
        self.set_font('CJK', '', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 8, f'第 {self.page_no()} 页 / 共 {{nb}} 页 | AKI 智能预测系统生成', align='C')

    def write_report(self, patient_info, prediction_result, risk_factors, recommendations, shap_fig=None,
                      counterfactual=None, risk_report=None):
        """
        Generate complete AKI risk assessment report.

        Args:
            patient_info: Dict with patient demographics
            prediction_result: Dict with probability, risk_level
            risk_factors: List of (feature, importance, direction)
            recommendations: Dict with clinical recommendations
            shap_fig: Matplotlib figure for SHAP explanation
            counterfactual: Dict with counterfactual analysis results
            risk_report: Dict from generate_risk_report() (Phase 2)
        """
        self.alias_nb_pages()

        prob = prediction_result.get('probability', 0)

        # ====== Cover Section ======
        self.add_page()
        self.ln(20)

        # Gauge chart (Phase 2)
        gauge_path = Path(__file__).parent.parent.parent / 'outputs' / 'tmp_gauge.png'
        try:
            gauge_fig = plot_risk_gauge(prob, save_path=str(gauge_path))
            if gauge_path.exists():
                self.image(str(gauge_path), x=55, w=100)
        except Exception:
            pass

        self.ln(5)
        self.set_font('CJK', 'B', 28)
        self.set_text_color(44, 62, 80)
        self.cell(0, 12, '急性肾损伤（AKI）风险预测评估报告', align='C', new_x="LMARGIN", new_y="NEXT")
        self.ln(3)
        self.set_font('CJK', '', 13)
        self.set_text_color(127, 140, 141)
        self.cell(0, 8, 'AI 辅助预测 + SHAP 可解释分析', align='C', new_x="LMARGIN", new_y="NEXT")
        self.ln(10)

        # Horizontal line
        self.set_draw_color(52, 152, 219)
        self.set_line_width(0.5)
        self.line(40, self.get_y(), 170, self.get_y())
        self.ln(8)

        # Patient ID and date
        self.set_font('CJK', '', 10)
        self.set_text_color(0, 0, 0)
        self.cell(0, 7, f"报告生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}", align='C', new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 7, f"患者编号：{patient_info.get('id', 'N/A')}", align='C', new_x="LMARGIN", new_y="NEXT")

        # Stars + KDIGO
        if risk_report:
            self.ln(3)
            self.set_font('CJK', 'B', 11)
            stars = risk_report.get('stars_display', '')
            self.cell(
                0, 8,
                f'风险程度：{stars}  |  {risk_report.get("risk_grade", risk_report.get("kdigo_stage", ""))}',
                align='C', new_x="LMARGIN", new_y="NEXT",
            )

        self.ln(10)

        # Risk level badge
        risk_colors = {
            '低风险': (39, 174, 96),
            '中风险': (243, 156, 18),
            '高风险': (231, 76, 60),
        }
        risk_text = prediction_result.get('risk_level', '低风险')
        risk_text = CN_RISK_LEVEL.get(risk_text, risk_text)
        color = risk_colors.get(risk_text, (39, 174, 96))

        self.set_fill_color(*color)
        self.set_text_color(255, 255, 255)
        self.set_font('CJK', 'B', 20)
        self.cell(0, 15, f'风险等级：{risk_text}', align='C', fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(3)
        self.set_font('CJK', 'B', 32)
        self.cell(0, 18, f'{prob:.1%}', align='C', fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(12)

        # 模型验证信息
        self.set_font('CJK', '', 10)
        self.set_text_color(127, 140, 141)
        model_auc = prediction_result.get('model_auc')
        if model_auc:
            auc_text = f'模型：Voting Ensemble | 50次嵌套CV AUC = {model_auc}'
        else:
            auc_text = '模型：Voting Ensemble | 50次嵌套CV验证'
        self.cell(0, 6, auc_text, align='C', new_x="LMARGIN", new_y="NEXT")
        self.ln(6)

        # ====== Patient Information ======
        self.set_text_color(0, 0, 0)
        self.set_font('CJK', 'B', 14)
        self.set_fill_color(236, 240, 241)
        self.cell(0, 10, '1. 患者基本信息', fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(5)

        self.set_font('CJK', '', 10)
        info_items = [
            ('年龄', _get(patient_info, 'age', '年龄')),
            ('性别', _get(patient_info, 'gender', '性别')),
            ('手术类型', _get(patient_info, 'surgery_type', 'surgery', '手术类型')),
            ('APACHE II 评分', _get(patient_info, 'apache_ii', 'APACHE II', 'APACHE II 评分')),
            ('高血压', _get(patient_info, 'hypertension', '高血压', default='未提供')),
            ('糖尿病', _get(patient_info, 'diabetes', '糖尿病', default='未提供')),
            ('手术时长', f"{_get(patient_info, 'surgery_time', '手术时间', default='N/A')} min"),
        ]

        col_width = 95
        for i in range(0, len(info_items), 2):
            self.set_font('CJK', 'B', 10)
            self.cell(30, 8, info_items[i][0] + ':')
            self.set_font('CJK', '', 10)
            self.cell(65, 8, str(info_items[i][1]))
            if i + 1 < len(info_items):
                self.set_font('CJK', 'B', 10)
                self.cell(30, 8, info_items[i+1][0] + ':')
                self.set_font('CJK', '', 10)
                self.cell(65, 8, str(info_items[i+1][1]))
            self.ln(7)

        self.ln(5)

        # ====== Key Lab Results ======
        self.set_font('CJK', 'B', 14)
        self.set_fill_color(236, 240, 241)
        self.cell(0, 10, '2. 关键检验指标', fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(5)

        lab_keys = ['preop_scr', 'preop_egfr', 'preop_alb', 'preop_hb', 'preop_wbc',
                     'preop_crp', 'preop_lactate', 'preop_nlr', 'preop_bnp']
        lab_labels = ['血肌酐（Scr）', 'eGFR', '白蛋白', '血红蛋白', '白细胞（WBC）',
                      'C反应蛋白（CRP）', '乳酸', 'NLR', 'BNP']
        lab_units = ['μmol/L', 'ml/min/1.73m2', 'g/L', 'g/L', '×10^9/L',
                      'mg/L', 'mmol/L', '', 'pg/mL']

        # Table header
        self.set_font('CJK', 'B', 9)
        self.set_fill_color(52, 152, 219)
        self.set_text_color(255, 255, 255)
        self.cell(70, 7, '检验项目', border=1, fill=True)
        self.cell(40, 7, '数值', border=1, fill=True, align='C')
        self.cell(40, 7, '单位', border=1, fill=True, align='C')
        self.cell(40, 7, '参考范围', border=1, fill=True, align='C')
        self.ln()

        self.set_text_color(0, 0, 0)
        for key, label, unit in zip(lab_keys, lab_labels, lab_units):
            value = patient_info.get(key, 'N/A')
            self.set_font('CJK', '', 9)
            self.cell(70, 7, f'  {label}', border=1)
            self.cell(40, 7, str(value), border=1, align='C')
            self.cell(40, 7, unit, border=1, align='C')
            self.cell(40, 7, '', border=1, align='C')
            self.ln()

        self.ln(8)

        # ====== Risk Factors ======
        self.set_font('CJK', 'B', 14)
        self.set_fill_color(236, 240, 241)
        self.cell(0, 10, '3. 主要风险因素（SHAP）', fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(5)

        self.set_font('CJK', 'B', 9)
        self.set_fill_color(231, 76, 60)
        self.set_text_color(255, 255, 255)
        self.cell(15, 7, '序号', border=1, fill=True, align='C')
        self.cell(60, 7, '风险因素', border=1, fill=True)
        self.cell(40, 7, '影响方向', border=1, fill=True, align='C')
        self.cell(75, 7, '临床解读', border=1, fill=True)
        self.ln()

        self.set_text_color(0, 0, 0)
        for rank, factor in enumerate(risk_factors[:5], 1):
            self.set_font('CJK', '', 9)
            self.cell(15, 12, str(rank), border=1, align='C')
            self.cell(60, 12, f' {factor[0]}', border=1)
            direction_cn = '风险升高 (+)' if factor[2] in ('positive', 'risk_increasing') else '保护因素 (-)'
            self.cell(40, 12, direction_cn, border=1, align='C')

            # Clinical interpretation
            from web.components.shap_explain import get_clinical_explanation
            direction_key = 'positive' if factor[2] in ('positive', 'risk_increasing') else 'negative'
            explanation = get_clinical_explanation(factor[0], factor[1], direction_key)
            self.set_font('CJK', '', 7)
            self.cell(75, 12, explanation[:80], border=1)
            self.ln()

        self.ln(8)

        # ====== SHAP Explanation ======
        if shap_fig is not None:
            self.set_font('CJK', 'B', 14)
            self.set_fill_color(236, 240, 241)
            self.cell(0, 10, '4. AI 可解释分析（SHAP）', fill=True, new_x="LMARGIN", new_y="NEXT")
            self.ln(5)

            # Save SHAP figure temporarily and insert
            tmp_path = Path(__file__).parent.parent.parent / 'outputs' / 'tmp_shap.png'
            shap_fig.savefig(tmp_path, dpi=150, bbox_inches='tight')
            self.image(str(tmp_path), x=20, w=170)
            self.ln(5)

        # ====== Clinical Recommendations ======
        self.add_page()
        cn_recs = CN_RECOMMENDATIONS.get(risk_text, CN_RECOMMENDATIONS['中风险'])
        self.set_font('CJK', 'B', 14)
        self.set_fill_color(236, 240, 241)
        self.cell(0, 10, '5. 临床管理建议', fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(8)

        sections = ['monitoring', 'prevention']
        section_titles = ['监测建议', '预防策略']

        for section, title in zip(sections, section_titles):
            self.set_font('CJK', 'B', 12)
            self.set_text_color(41, 128, 185)
            self.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
            self.ln(2)

            items = cn_recs.get(section, [])
            for item in items:
                self.set_font('CJK', '', 10)
                self.set_text_color(0, 0, 0)
                self.cell(5, 6, '')
                self.cell(5, 6, chr(183))
                self.cell(0, 6, item, new_x="LMARGIN", new_y="NEXT")
            self.ln(5)

        # Follow-up
        self.set_font('CJK', 'B', 12)
        self.set_text_color(41, 128, 185)
        self.cell(0, 8, '随访建议', new_x="LMARGIN", new_y="NEXT")
        self.ln(2)
        self.set_font('CJK', '', 10)
        self.set_text_color(0, 0, 0)
        self.multi_cell(0, 6, cn_recs.get('follow_up', ''))

        self.ln(8)

        # ====== 患者须知 ======
        self.set_font('CJK', 'B', 14)
        self.set_fill_color(236, 240, 241)
        self.cell(0, 10, '患者须知（通俗解读）', fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(5)
        self.set_fill_color(234, 248, 242)
        self.set_draw_color(39, 174, 96)
        self.set_font('CJK', '', 10)
        self.set_text_color(0, 0, 0)
        self.multi_cell(0, 6, cn_recs.get('patient_note', ''), fill=True)
        self.ln(3)
        self.set_font('CJK', '', 9)
        self.set_text_color(127, 140, 141)
        self.multi_cell(0, 5,
            '本报告中的“风险”是统计学预测结果，不等同于确诊。'
            '请以主治医生的判断为准，不要因报告内容自行停药、加药或改变治疗方案。'
            '如果出现尿量明显减少、尿色异常、水肿、恶心或呼吸困难，请立即告知医护人员。'
        )

        self.ln(8)

        # ====== Counterfactual Analysis (Phase 2) ======
        if counterfactual:
            self.set_font('CJK', 'B', 14)
            self.set_fill_color(236, 240, 241)
            self.cell(0, 10, '6. 反事实分析（假设干预）', fill=True, new_x="LMARGIN", new_y="NEXT")
            self.ln(5)

            cf_feature = counterfactual.get('feature', 'Unknown')
            cf_current = counterfactual.get('current_value', 'N/A')
            cf_target = counterfactual.get('target_value', 'N/A')
            cf_current_risk = counterfactual.get('current_risk', prob)
            cf_target_risk = counterfactual.get('target_risk', prob)
            cf_delta = counterfactual.get('risk_change', 0)

            self.set_font('CJK', '', 10)
            self.set_text_color(0, 0, 0)

            # Summary box
            self.set_fill_color(234, 242, 248)
            self.set_draw_color(52, 152, 219)
            cf_text = (
                f'若将“{cf_feature}”从 {cf_current} 调整至 {cf_target}，'
                f'预测 AKI 风险将从 {cf_current_risk:.1%} 变化为 {cf_target_risk:.1%}'
                f'（变化 {cf_delta:+.1%}）。'
            )
            self.set_font('CJK', 'B', 10)
            self.multi_cell(0, 7, cf_text, fill=True)

            self.ln(5)
            self.set_font('CJK', '', 9)
            self.multi_cell(0, 5,
                '临床解读：\n'
                f'调整“{cf_feature}”后预测风险变化 {abs(cf_delta):.1%}。'
                '该指标可能是可干预的风险因素，针对其进行临床干预'
                '（如容量管理、药物调整等）有助于降低 AKI 风险。'
            )

            # Additional counterfactual scenarios
            cf_scenarios = counterfactual.get('scenarios', [])
            if cf_scenarios:
                self.ln(5)
                self.set_font('CJK', 'B', 10)
                self.cell(0, 7, '其他干预场景：', new_x="LMARGIN", new_y="NEXT")
                self.ln(3)
                for scenario in cf_scenarios[:3]:
                    self.set_font('CJK', '', 9)
                    self.cell(5, 5, '')
                    self.cell(5, 5, chr(183))
                    self.multi_cell(0, 5, scenario)

            self.ln(5)

        # ====== KDIGO Reference ======
        self.set_font('CJK', 'B', 14)
        self.set_fill_color(236, 240, 241)
        kdigo_num = '7' if counterfactual else '6'
        self.cell(0, 10, f'{kdigo_num}. KDIGO 急性肾损伤诊断标准（参考）', fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(5)
        self.set_font('CJK', '', 9)
        self.multi_cell(0, 5,
            "AKI 诊断标准（满足以下任意一条即可）：\n"
            "· 48 小时内血肌酐升高 ≥ 0.3 mg/dL（≥ 26.5 μmol/L）；或\n"
            "· 7 天内血肌酐升至基线值的 ≥ 1.5 倍；或\n"
            "· 尿量 < 0.5 ml/kg/h 持续 6 小时。\n\n"
            "KDIGO 分期：\n"
            "· 1 期：血肌酐升高至基线 1.5-1.9 倍，或升高 ≥ 0.3 mg/dL，或尿量 < 0.5 ml/kg/h 持续 6-12 小时\n"
            "· 2 期：血肌酐升高至基线 2.0-2.9 倍，或尿量 < 0.5 ml/kg/h 持续 ≥ 12 小时\n"
            "· 3 期：血肌酐升高至基线 3.0 倍，或 ≥ 4.0 mg/dL，或开始肾脏替代治疗，或尿量 < 0.3 ml/kg/h 持续 ≥ 24 小时"
        )

        # ====== Disclaimer ======
        self.ln(10)
        self.set_font('CJK', '', 8)
        self.set_text_color(149, 165, 166)
        self.multi_cell(0, 4,
            '免责声明：本报告由 AI 预测系统自动生成，仅供学术研究与临床参考，'
            '不能作为临床决策的唯一依据。所有临床决策应由具备资质的医护人员'
            '结合患者全面情况进行判断。'
        )


def plot_risk_gauge(probability, save_path=None):
    """
    Generate a risk gauge chart (matplotlib) for embedding in PDF.

    Args:
        probability: Predicted AKI probability (0-1)
        save_path: Optional path to save the figure

    Returns:
        matplotlib figure
    """
    import matplotlib.pyplot as plt
    from matplotlib.patches import Wedge, Circle, FancyBboxPatch
    import numpy as np

    fig, ax = plt.subplots(figsize=(6, 4), subplot_kw={'projection': None})
    ax.set_xlim(-2, 2)
    ax.set_ylim(-0.5, 2.5)
    ax.axis('off')

    # Risk zone colors
    zones = [
        (0.0, 0.3, '#27ae60', '低风险'),
        (0.3, 0.7, '#f39c12', '中风险'),
        (0.7, 1.0, '#e74c3c', '高风险'),
    ]

    # Draw gauge arc (semi-circle)
    center = (0, 0)
    radius = 1.8
    for start, end, color, label in zones:
        theta1 = 180 - start * 180
        theta2 = 180 - end * 180
        wedge = Wedge(center, radius, theta2, theta1, width=0.4,
                      facecolor=color, edgecolor='white', alpha=0.85)
        ax.add_patch(wedge)

    # Draw tick marks
    for pct in [0, 0.3, 0.7, 1.0]:
        angle_rad = np.radians(180 - pct * 180)
        r_inner = radius - 0.4
        r_outer = radius
        x1, y1 = center[0] + r_inner * np.cos(angle_rad), center[1] + r_inner * np.sin(angle_rad)
        x2, y2 = center[0] + r_outer * np.cos(angle_rad), center[1] + r_outer * np.sin(angle_rad)
        ax.plot([x1, x2], [y1, y2], 'w-', linewidth=1.5)
        # Label
        lx = center[0] + (r_outer + 0.3) * np.cos(angle_rad)
        ly = center[1] + (r_outer + 0.3) * np.sin(angle_rad)
        ax.text(lx, ly, f'{pct:.0%}', ha='center', va='center', fontsize=8, fontweight='bold')

    # Draw needle
    needle_angle = 180 - probability * 180
    needle_rad = np.radians(needle_angle)
    needle_len = radius - 0.1
    nx, ny = center[0] + needle_len * np.cos(needle_rad), center[1] + needle_len * np.sin(needle_rad)
    ax.annotate('', xy=(nx, ny), xytext=center,
                arrowprops=dict(arrowstyle='->', color='#2c3e50', lw=3))

    # Center circle
    circle = Circle(center, 0.12, facecolor='#2c3e50', edgecolor='white', linewidth=2)
    ax.add_patch(circle)

    # Risk probability text
    risk_pct = f'{probability:.1%}'
    if probability < 0.3:
        risk_label = '低风险'
    else:
        risk_label = '中风险' if probability < 0.7 else '高风险'

    ax.text(0, -0.35, risk_label, ha='center', va='center', fontsize=16, fontweight='bold', color='#2c3e50')
    ax.text(0, -0.65, f'AKI 预测概率：{risk_pct}', ha='center', va='center', fontsize=11, color='#7f8c8d')

    plt.tight_layout()

    if save_path:
        os.makedirs(os.path.dirname(str(save_path)), exist_ok=True)
        fig.savefig(str(save_path), dpi=150, bbox_inches='tight', facecolor='white')
        plt.close(fig)

    return fig


def plot_risk_waterfall_chart(shap_values, feature_names, expected_value, save_path=None, top_n=10):
    """
    Generate a SHAP waterfall-style bar chart for PDF embedding.

    Args:
        shap_values: Array of SHAP values for one prediction
        feature_names: List of feature names
        expected_value: Base expected value
        save_path: Optional save path
        top_n: Number of top features to show

    Returns:
        matplotlib figure
    """
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(9, max(5, top_n * 0.35)))

    abs_sv = np.abs(shap_values)
    top_idx = np.argsort(abs_sv)[-top_n:]
    top_feats = [feature_names[i] if i < len(feature_names) else f'F{i}' for i in top_idx]
    top_vals = shap_values[top_idx]
    colors = ['#e74c3c' if v > 0 else '#2ecc71' for v in top_vals]

    ax.barh(range(len(top_feats)), top_vals[::-1], color=colors[::-1],
            alpha=0.85, edgecolor='white', height=0.7)
    ax.set_yticks(range(len(top_feats)))
    ax.set_yticklabels(top_feats[::-1], fontsize=9)
    ax.axvline(x=0, color='black', linewidth=0.5)
    ax.axvline(x=expected_value, color='gray', linestyle='--', alpha=0.5,
              label=f'Base Value: {expected_value:.3f}')
    ax.set_xlabel('SHAP Value (Impact on Prediction)', fontsize=11)
    ax.set_title('SHAP Feature Contribution', fontsize=13, fontweight='bold')
    ax.legend(fontsize=8, loc='lower right')
    ax.grid(axis='x', alpha=0.2)
    plt.tight_layout()

    if save_path:
        os.makedirs(os.path.dirname(str(save_path)), exist_ok=True)
        fig.savefig(str(save_path), dpi=150, bbox_inches='tight', facecolor='white')
        plt.close(fig)

    return fig


def generate_pdf_report(patient_info, prediction_result, risk_factors,
                         recommendations, shap_fig=None, output_path=None,
                         counterfactual=None, risk_report=None):
    """
    Generate and save PDF report.

    Args:
        patient_info: Dict with patient demographics and lab values
        prediction_result: Dict with 'probability' and 'risk_level'
        risk_factors: List of (feature, importance, direction) tuples
        recommendations: Dict with clinical recommendations
        shap_fig: Optional matplotlib figure for SHAP explanation
        output_path: Output file path

    Returns:
        output_path: Path to generated PDF
    """
    if output_path is None:
        output_dir = Path(__file__).parent.parent.parent / 'outputs' / 'reports'
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f'AKI_Report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'

    pdf = AKIReportPDF()
    pdf.write_report(patient_info, prediction_result, risk_factors, recommendations,
                     shap_fig, counterfactual, risk_report)

    pdf.output(str(output_path))
    logger.info(f"PDF report generated: {output_path}")

    return output_path


if __name__ == '__main__':
    # Test report generation
    test_patient = {
        'id': 'TEST001', 'age': 65, 'gender': 'Male',
        'surgery_type': 'Cardiac Valve Surgery', 'apache_ii': 22,
        'hypertension': 'Yes', 'diabetes': 'No', 'surgery_time': 380,
        'preop_scr': 105, 'preop_egfr': 65, 'preop_alb': 38,
        'preop_hb': 125, 'preop_wbc': 8.5, 'preop_crp': 12,
        'preop_lactate': 1.8, 'preop_nlr': 4.2, 'preop_bnp': 850,
    }
    test_result = {'probability': 0.65, 'risk_level': 'Medium'}
    test_factors = [
        ('APACHE II (>20)', 0.85, 'positive'),
        ('Age (>60)', 0.72, 'positive'),
        ('Pre-op eGFR (<60)', 0.68, 'positive'),
        ('Pre-op Scr (>100)', 0.55, 'positive'),
    ]
    test_recs = {
        'monitoring': ['Monitor urine output every 6h', 'Check Scr daily'],
        'prevention': ['Goal-directed fluid therapy', 'Avoid nephrotoxic drugs'],
        'follow_up': 'Continue monitoring for 72h post-op.',
    }
    # Test counterfactual
    test_cf = {
        'feature': 'Pre-op Scr',
        'current_value': 105,
        'target_value': 80,
        'current_risk': 0.65,
        'target_risk': 0.45,
        'risk_change': -0.20,
        'scenarios': [
            'If Scr decreases from 105 to 80 umol/L, risk drops from 65% to 45%',
            'If APACHE II decreases from 22 to 15, risk drops from 65% to 52%',
        ],
    }

    path = generate_pdf_report(test_patient, test_result, test_factors, test_recs,
                                counterfactual=test_cf)
    print(f"Test report generated: {path}")

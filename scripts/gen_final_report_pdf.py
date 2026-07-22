# -*- coding: utf-8 -*-
"""
生成最终测试报告 PDF
根据《测试报告文档模板》7 章结构
结合 GitHub 实际内容：AUC 0.821 / 4模型 + Voting / 125例 AKI / 35特征
"""
import os, sys
from pathlib import Path
from datetime import datetime
from fpdf import FPDF


class FinalReportPDF(FPDF):
    def __init__(self):
        super().__init__('P', 'mm', 'A4')
        self._setup_fonts()
        self.set_auto_page_break(True, 22)

    def _setup_fonts(self):
        for fp in ['C:/Windows/Fonts/simhei.ttf', 'C:/Windows/Fonts/msyh.ttf',
                    'C:/Windows/Fonts/simsun.ttc', 'C:/Windows/Fonts/msyhbd.ttc']:
            if os.path.exists(fp):
                self.add_font('CN', '', fp, uni=True)
                self.add_font('CN', 'B', fp, uni=True)
                print(f"  Font: {fp}")
                return
        self.add_font('CN', '', 'Helvetica')
        print("  WARNING: No Chinese font found!")

    def header(self):
        if self.page_no() > 1:
            self.set_font('CN', '', 8)
            self.set_text_color(128,128,128)
            self.cell(0, 6, 'AKI智能预测系统 — 测试报告', align='R')
            self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font('CN', '', 8)
        self.set_text_color(128,128,128)
        self.cell(0, 8, f'第 {self.page_no()} 页', align='C')

    # ── helpers ──
    def title_page(self, title, subtitle):
        self.add_page()
        self.ln(40)
        self.set_font('CN', 'B', 28)
        self.set_text_color(44, 62, 80)
        self.cell(0, 14, title, align='C', new_x="LMARGIN", new_y="NEXT")
        self.ln(6)
        self.set_font('CN', '', 14)
        self.set_text_color(127, 140, 141)
        self.cell(0, 10, subtitle, align='C', new_x="LMARGIN", new_y="NEXT")
        self.ln(15)
        self.set_draw_color(52, 152, 219)
        self.set_line_width(0.5)
        self.line(40, self.get_y(), 170, self.get_y())
        self.ln(10)
        self.set_font('CN', '', 11)
        self.set_text_color(0,0,0)
        self.cell(0, 8, f'报告日期: {datetime.now().strftime("%Y年%m月%d日")}', align='C', new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 8, '团队: 白菜卷队 | 广西科技大学 | 暑期数创 2026', align='C', new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 8, '版本: v2.0 (基于 run_clean.py AUC 0.821 基线)', align='C', new_x="LMARGIN", new_y="NEXT")

    def section_title(self, num, title):
        self.ln(6)
        self.set_font('CN', 'B', 15)
        self.set_fill_color(41, 128, 185)
        self.set_text_color(255, 255, 255)
        self.cell(0, 10, f'  {num}. {title}', fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(4)
        self.set_text_color(0, 0, 0)

    def sub_title(self, title):
        self.set_font('CN', 'B', 12)
        self.set_text_color(44, 62, 80)
        self.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)
        self.set_text_color(0, 0, 0)

    def body(self, text):
        self.set_font('CN', '', 10)
        self.set_text_color(0, 0, 0)
        self.multi_cell(0, 6, text)
        self.ln(2)

    def bullet(self, text, indent=10):
        self.set_font('CN', '', 10)
        self.set_x(self.l_margin + indent)
        self.cell(5, 6, '•')
        self.multi_cell(0, 6, text)

    def info_table(self, rows, col_widths=None, header=True):
        if col_widths is None:
            col_widths = [95, 95]
        for i, (k, v) in enumerate(rows):
            if header and i == 0:
                self.set_font('CN', 'B', 9)
                self.set_fill_color(52, 152, 219)
                self.set_text_color(255,255,255)
            else:
                self.set_font('CN', '', 9)
                self.set_text_color(0,0,0)
                self.set_fill_color(248, 249, 250) if i % 2 == 0 else self.set_fill_color(255, 255, 255)
            self.cell(col_widths[0], 7, f' {k}', border=1, fill=True)
            self.cell(col_widths[1], 7, f' {v}', border=1, fill=True)
            self.ln()
        self.ln(4)


def generate():
    PROJ = Path(__file__).parent.parent
    pdf = FinalReportPDF()

    # ══════════════════════════════════════
    # 封面
    # ══════════════════════════════════════
    pdf.title_page(
        'AKI 智能预测系统 — 测试报告',
        '急性肾损伤机器学习预测与临床决策支持系统'
    )

    # ══════════════════════════════════════
    # 一、程序整体概述以及核心模块拆解
    # ══════════════════════════════════════
    pdf.section_title('一', '程序整体概述以及核心模块拆解')

    pdf.sub_title('1.1 程序整体逻辑')
    pdf.body(
        '本程序为急性肾损伤（AKI）智能预测系统，基于420例心脏手术患者的围术期临床数据，'
        '构建4种机器学习模型及加权Voting集成，通过SHAP可解释性分析实现预测过程的透明化，'
        '最终部署为Streamlit Web应用，为临床医生提供可交互的个体化风险评估工具。\n\n'
        '整体架构分为三个层次：数据层（数据加载、清洗、特征工程）、模型层（模型训练、'
        '评估、集成、可解释性）、应用层（Web预测、风险报告、医生工作台、管理仪表盘）。'
    )

    pdf.sub_title('1.2 核心模块拆解')
    modules = [
        ('数据加载与清洗', 'src/data/cleaning.py', '420例原始数据 → 异常值处理 → 缺失值填补 → 数据泄漏审查'),
        ('特征工程', 'run_clean.py (模块3)', '86候选特征 → RF特征重要性排序 → Top35关键特征'),
        ('模型训练与CV', 'run_clean.py (模块4)', '4模型 + Voting集成 → 50次重复分层5折CV → AUC评估'),
        ('可解释性分析', 'src/visualization/shap_viz.py', 'SHAP全局+局部解释 → 反事实What-If分析'),
        ('数据治理可视化', 'src/visualization/data_governance.py', '7阶段治理流程 → 特征筛选漏斗 → 质量仪表盘'),
        ('消融实验', 'src/models/ablation.py', '特征组增量实验 → 热力图+柱状图 → 消融对比表'),
        ('交叉验证可信度', 'src/models/cross_validate.py', '五折CV ROC置信带 → Bootstrap AUC分布'),
        ('集成学习管线', 'src/models/ensemble.py', 'Voting/Stacking/Weighted Avg → 网格搜索元学习器'),
        ('时序风险轨迹', 'src/models/temporal.py', 'T0→T1→T2增量建模 → 个体风险轨迹可视化'),
        ('Web预测系统', 'streamlit_app.py / web/app.py', '7页面系统：预测+医生工作台+管理仪表盘+报告'),
    ]
    for name, path, desc in modules:
        pdf.bullet(f'{name} ({path}): {desc}')

    # ══════════════════════════════════════
    # 二、数据说明与数据处理方案
    # ══════════════════════════════════════
    pdf.section_title('二', '数据说明与数据处理方案论述')

    pdf.sub_title('2.1 数据集概述')
    pdf.info_table([
        ('项目', '说明'),
        ('数据来源', '广西某三甲医院心脏外科EHR系统'),
        ('样本量', '420例 心脏手术患者'),
        ('原始特征数', '97个临床变量'),
        ('AKI发生率', '29.8% (125/420)'),
        ('AKI分期分布', 'Stage0:295 / Stage1:91 / Stage2:24 / Stage3:10'),
        ('时间跨度', '2019年1月 - 2023年12月'),
        ('数据格式', 'Excel (.xlsx) 结构化存储'),
    ])

    pdf.sub_title('2.2 数据处理方案')
    pdf.body('本研究建立了系统性的七阶段数据治理管线：')
    steps = [
        '原始数据采集 — 420例，97个变量，Excel结构化存储。',
        '缺失值分析 — 以30%为阈值剔除高缺失变量（97→86），保留变量采用中位数（连续型）和众数（分类型）填补。',
        '异常值检测 — 基于临床参考范围识别异常值（如Scr 20-500μmol/L，eGFR 10-150ml/min/1.73m²），人工审查确认。',
        '标准化与编码 — 连续变量Z-score标准化；分类变量One-Hot编码。',
        '数据泄漏审查 — 排除KDIGO诊断标准（术后48h/7d Scr/eGFR）、结局变量（住院天数/费用）、术后晚期指标（术后7d RBP）。',
        '特征筛选 — 随机森林特征重要性排序，选取Top35关键特征。',
        '建模数据集 — N=420, P=35的规范化数据集。',
    ]
    for s in steps:
        pdf.bullet(s)

    pdf.sub_title('2.3 数据泄漏控制（关键）')
    pdf.body(
        '初始模型AUC > 0.99，经系统性审查发现特征中包含术后48h/7d肌酐——这正是KDIGO诊断标准本身'
        '（"用答案预测答案"）。排除泄漏特征后，纯术前特征AUC为0.74，最终版（术前+术中+ICU早期非肌酐特征）'
        'AUC为0.821。保留特征论证：所有纳入特征在入ICU即刻即可获取，预测时点具有临床可操作性。'
    )

    # ══════════════════════════════════════
    # 三、模型的挑选、增强/微调策略
    # ══════════════════════════════════════
    pdf.section_title('三', '模型的挑选、增强/微调策略论述')

    pdf.sub_title('3.1 模型选择与特点')
    pdf.body(
        '本研究选择4种具有不同建模范式的机器学习算法，覆盖线性模型和树集成模型两大类别：'
    )
    model_info = [
        ('Logistic回归 (C=0.02, L2)', '线性基线模型，强正则化，高可解释性。适用于临床基线对照。CV AUC: 0.808±0.044'),
        ('RandomForest (max_depth=5, min_samples_leaf=15)', 'Bagging集成，抗过拟合，非线性建模。CV AUC: 0.815±0.043'),
        ('XGBoost (max_depth=3, reg_alpha=reg_lambda=1.0)', '梯度提升，强正则化，内置缺失值处理。CV AUC: 0.819±0.043'),
        ('ExtraTrees (max_depth=5, min_samples_leaf=15)', '极端随机化分裂，进一步降低方差。CV AUC: 0.809±0.044'),
    ]
    for name, desc in model_info:
        pdf.bullet(f'{name}: {desc}')

    pdf.sub_title('3.2 集成学习策略')
    pdf.body(
        '采用加权Voting Ensemble（Soft Voting）融合4种基模型：\n'
        '  权重配置: Logistic回归:2, 随机森林:2, XGBoost:1, ExtraTrees:1\n'
        '  最终性能: AUC 0.821±0.043 (50次重复分层5折CV), Bootstrap 95%CI [0.779, 0.865]\n\n'
        'Voting集成比任何单一模型更稳定，融合了线性模型的校准优势和树模型的非线性建模能力。'
    )

    pdf.sub_title('3.3 训练与验证策略')
    pdf.body(
        '• 验证方案: 50次重复五折分层交叉验证（Stratified 5-Fold × 10 Repeats = 250次训练-评估迭代）\n'
        '• 正则化策略: 所有模型采用强正则化控制过拟合（低C值、限制树深度、min_samples_leaf≥10等）\n'
        '• 类别平衡: class_weight="balanced" + SMOTE仅在训练集内合成少数类样本\n'
        '• 过拟合控制: 训练-测试AUC差距0.128，在420例中等样本下处于可接受范围'
    )

    # ══════════════════════════════════════
    # 四、程序的整体优化策略
    # ══════════════════════════════════════
    pdf.section_title('四', '程序的整体优化策略')

    pdf.sub_title('4.1 时间效率优化')
    pdf.body(
        '• 模型推理: Web预测响应时间 < 2秒，支持实时风险评估\n'
        '• 批量评估: 支持CSV文件批量导入，一次完成多患者预测\n'
        '• 模型加载: 使用Streamlit @st.cache_resource缓存模型，避免重复加载\n'
        '• 并行训练: 使用n_jobs=-1充分利用多核CPU加速CV评估'
    )

    pdf.sub_title('4.2 空间/部署优化')
    pdf.body(
        '• 模型序列化: 使用joblib持久化训练好的模型和标准化器，即载即用\n'
        '• GitHub + Streamlit Cloud: 代码托管在GitHub，Web应用通过Streamlit Cloud自动部署\n'
        '• 模块化设计: src/目录下各模块独立可复用，支持灵活组合\n'
        '• 数据治理: 七阶段管线确保数据处理的可复现性和透明性'
    )

    pdf.sub_title('4.3 效果对比')
    pdf.info_table([
        ('优化阶段', 'AUC效果'),
        ('初始模型（含数据泄漏）', 'AUC > 0.99（不可信）'),
        ('纯术前特征（保守）', 'AUC 0.74'),
        ('术前+术中+ICU入室', 'AUC 0.79'),
        ('最终版（+术后早期非肌酐）', 'AUC 0.821±0.043（当前最优）'),
    ])
    pdf.body('关键洞察: "一个可信的0.821，胜过一百个泄漏的0.99。"')

    # ══════════════════════════════════════
    # 五、评价指标与程序效果评估
    # ══════════════════════════════════════
    pdf.section_title('五', '评价指标挑选与程序效果评估')

    pdf.sub_title('5.1 评价指标定义')
    pdf.info_table([
        ('指标', '定义 / 评价标准'),
        ('AUC-ROC', '反映模型将正负样本正确排序的能力。越接近1越好'),
        ('50次重复CV', '50次独立分层5折交叉验证取均值±标准差。评估稳定性'),
        ('Bootstrap 95%CI', '1000次Bootstrap重抽样计算AUC置信区间。评估可靠性'),
        ('Brier Score', '预测概率与真实结局的均方误差。越小越好（<0.25为可接受）'),
        ('过拟合差距', '训练AUC - 测试AUC。越小越好（<0.15为可接受）'),
    ])

    pdf.sub_title('5.2 核心模型性能')
    pdf.info_table([
        ('模型', '50次CV AUC ± 标准差'),
        ('Logistic回归', '0.808 ± 0.044'),
        ('随机森林 (RF)', '0.815 ± 0.043'),
        ('XGBoost', '0.819 ± 0.043'),
        ('ExtraTrees', '0.809 ± 0.044'),
        ('★ Voting Ensemble', '0.821 ± 0.043'),
    ])

    pdf.sub_title('5.3 过拟合检查')
    pdf.info_table([
        ('指标', '数值 / 判断'),
        ('训练AUC - 测试AUC差距', '0.128'),
        ('Bootstrap 95%CI', '[0.779, 0.865]'),
        ('Brier Score', '0.152'),
        ('判断', '过拟合程度可控，模型泛化能力可接受'),
    ])

    pdf.sub_title('5.4 效果评估结论')
    pdf.body(
        'Voting Ensemble以AUC 0.821±0.043的表现优于所有单一模型，在四种基模型中，'
        'XGBoost（0.819）和随机森林（0.815）是集成的主要贡献者。Bootstrap 95%CI为'
        '[0.779, 0.865]，Brier Score 0.152表明预测概率校准良好。\n\n'
        'SHAP分析揭示术前肾功能（eGFR/Scr）、年龄、CPB时间和术中尿量为前四位'
        '预测因子，与临床共识一致，增强了模型的可信度。'
    )

    # ══════════════════════════════════════
    # 六、作品价值与创新性
    # ══════════════════════════════════════
    pdf.section_title('六', '作品价值与创新性')

    pdf.sub_title('6.1 应用价值')
    pdf.body(
        '心脏手术后AKI发生率约30%，是增加死亡率和医疗费用的重要并发症。'
        '现有临床评分（如克利夫兰评分、STS评分）的AUC多在0.70-0.80之间，'
        '且无法提供个体化解释。本系统AUC达0.821，配合SHAP可解释性，为临床医生'
        '提供了"不仅预测风险，更解释为什么"的决策支持工具。'
    )

    pdf.sub_title('6.2 创新点')
    innovations = [
        '数据泄漏系统性审查: 识别并排除KDIGO诊断标准、结局变量等泄漏特征，确保模型可信度。同类研究中少见如此详细的泄漏控制论述。',
        '完整的模型可信度体系: 五折CV ROC置信带 + Bootstrap AUC分布 + 消融实验 + DCA临床决策曲线 + 校准曲线 + 数据治理可视化，构建了超越常规的评估框架。',
        'SHAP反事实解释 (What-If): 不仅展示特征重要性，还支持"如果肌酐降低20%，风险从72%降至45%"的交互式临床推理，将可解释性推向决策支持层面。',
        '时序风险轨迹预测: 基于T0(术前)→T1(术中)→T2(ICU早期)的增量建模，模拟患者旅途中的风险动态变化。',
        '从模型到系统的全链路闭环: "数据治理—建模—评估—可解释—Web部署—PDF报告"的完整实践，超越仅报告性能指标的常规研究。',
        '医生工作台+管理仪表盘: 患者批量评估、AKI趋势监控、科室分布、高危预警——面向医院管理者的决策支持。',
    ]
    for inv in innovations:
        pdf.bullet(inv)

    pdf.sub_title('6.3 与传统方案对比')
    pdf.info_table([
        ('维度', '传统方案 vs 本作品'),
        ('预测性能', '临床评分 AUC 0.70-0.80 → 本系统 Voting AUC 0.821'),
        ('可解释性', '无/有限 → SHAP全局+局部+反事实What-If'),
        ('部署形态', '静态公式/评分卡 → Streamlit Web实时交互'),
        ('数据泄漏控制', '少有系统性论述 → 七阶段治理+泄漏排除论证'),
        ('评价体系', '单一AUC → 50次CV+Bootstrap+DCA+校准+消融'),
        ('用户界面', '无 → 7页面系统(预测+工作台+仪表盘+报告)'),
    ])

    # ══════════════════════════════════════
    # 七、其他情况说明
    # ══════════════════════════════════════
    pdf.section_title('七', '其他情况说明')

    pdf.sub_title('7.1 技术栈')
    pdf.body(
        '语言: Python 3.11 | 框架: scikit-learn, XGBoost, SHAP\n'
        '可视化: Matplotlib, Seaborn | Web: Streamlit\n'
        '验证: RepeatedStratifiedKFold, Bootstrap | 报告: fpdf2'
    )

    pdf.sub_title('7.2 局限性')
    limitations = [
        '样本量有限（420例），属于单中心回顾性研究，外部验证尚待开展。',
        'EPV（Events Per Variable）= 3.6，略低于理想值（≥10），但在强正则化下模型仍稳定。',
        '时序分析基于"伪时序"特征分组，非真正纵向随访数据。',
        '目前未包含影像组学、基因组学等多模态数据。',
    ]
    for l in limitations:
        pdf.bullet(l)

    pdf.sub_title('7.3 后续计划')
    plans = [
        '多中心外部验证，提升模型泛化性能证据。',
        '纳入更多术中动态监测数据（如实时血流动力学），实现更精细的时序建模。',
        '开发REST API接口，支持与医院HIS/EMR系统集成。',
        '开展前瞻性临床验证研究。',
    ]
    for p in plans:
        pdf.bullet(p)

    pdf.sub_title('7.4 团队分工')
    pdf.info_table([
        ('角色', '负责人 / 主要职责'),
        ('队长 / 技术路线 / 论文', '蓝可 — 统筹、建模、优化、论文框架'),
        ('数据清洗 / 特征工程', '李婷、蓝可 — 数据预处理、EDA、泄漏审查'),
        ('建模 / SHAP', '梁日娇、蓝可 — 模型训练、评估、可解释性分析'),
        ('Web开发', '王若兮 — Streamlit系统开发、前后端'),
        ('论文撰写', '叶宇晨、蓝可 — 论文撰写、文献综述'),
    ])

    pdf.ln(10)
    pdf.set_font('CN', '', 8)
    pdf.set_text_color(149, 165, 166)
    pdf.multi_cell(0, 4,
        '免责声明: 本系统仅供学术研究和临床参考，不作为最终诊断依据。'
        '所有临床决策应由合格医疗专业人员根据综合患者评估做出。\n'
        '版权: 白菜卷队 · 广西科技大学 · 暑期数创 2026 · 仅限学术用途'
    )

    # ── Save ──
    out_dir = PROJ / 'outputs' / 'reports'
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f'AKI最终测试报告_{datetime.now().strftime("%Y%m%d")}.pdf'
    pdf.output(str(out_path))
    print(f'\n  PDF generated: {out_path}')
    return str(out_path)


if __name__ == '__main__':
    generate()

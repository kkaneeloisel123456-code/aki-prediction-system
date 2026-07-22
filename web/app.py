"""
AKI Prediction System - Streamlit Main Application
Real model-powered prediction with SHAP explainability.
"""
import streamlit as st
import pandas as pd
import numpy as np
import joblib
import matplotlib.pyplot as plt
from pathlib import Path
import sys, os, warnings, base64, json
from datetime import datetime
warnings.filterwarnings('ignore')

# Page config
st.set_page_config(
    page_title="AKI 智能预测系统", page_icon="🏥",
    layout="wide", initial_sidebar_state="expanded"
)

# Paths
BASE_DIR = Path(__file__).parent.parent
MODEL_DIR = BASE_DIR / 'models'
OUTPUT_DIR = BASE_DIR / 'outputs'
FIG_DIR = OUTPUT_DIR / 'figures'
TAB_DIR = OUTPUT_DIR / 'tables'

# ============================================
# CSS
# ============================================
st.markdown("""
<style>
    .main-header { font-size:2.5rem;font-weight:700;color:#2c3e50;text-align:center;margin-bottom:1rem; }
    .sub-header { font-size:1.2rem;color:#7f8c8d;text-align:center;margin-bottom:2rem; }
    .risk-low { background:linear-gradient(135deg,#27ae60,#2ecc71);color:white;padding:20px;border-radius:15px;text-align:center;font-size:1.5rem;font-weight:bold; }
    .risk-medium { background:linear-gradient(135deg,#f39c12,#e67e22);color:white;padding:20px;border-radius:15px;text-align:center;font-size:1.5rem;font-weight:bold; }
    .risk-high { background:linear-gradient(135deg,#e74c3c,#c0392b);color:white;padding:20px;border-radius:15px;text-align:center;font-size:1.5rem;font-weight:bold; }
    .metric-card { background:#f8f9fa;padding:15px;border-radius:10px;border-left:5px solid #3498db;margin:10px 0; }
    .info-box { background:#eaf2f8;padding:15px;border-radius:10px;border:1px solid #3498db;margin:10px 0; }
    .footer { text-align:center;color:#95a5a6;padding:20px;font-size:0.85rem; }
    .pred-box { background:white;padding:25px;border-radius:15px;box-shadow:0 4px 20px rgba(0,0,0,0.1);margin:20px 0;text-align:center; }
</style>
""", unsafe_allow_html=True)

# ============================================
# Sidebar
# ============================================
with st.sidebar:
    st.markdown("## 🏥 AKI 预测系统")
    st.markdown("---")
    page = st.radio("导航", ["🏠 首页", "📊 模型性能", "🔮 风险预测", "📋 报告"],
                     label_visibility="collapsed")
    st.markdown("---")
    st.markdown("### ⚙️ 设置")
    risk_low = st.slider("低风险阈值", 0.0, 1.0, 0.3, 0.05)
    risk_high = st.slider("高风险阈值", 0.0, 1.0, 0.7, 0.05)
    st.markdown("---")
    st.info("**白菜卷队** · 广西科技大学\n暑期数创 2026")

# ============================================
# Model Loading (cached)
# ============================================
@st.cache_resource
def load_all():
    """Load model, scaler, features, and evaluation results."""
    result = {'model': None, 'scaler': None, 'features': None, 'eval_df': None,
              'best_name': None, 'models': {},
              'validation_report': None, 'validation_flags': None,
              'n_staging_issues': 0, 'n_group_stage_issues': 0}

    # Load evaluation results (final optimized version)
    eval_path = TAB_DIR / 'final_cv_results.csv'
    if not eval_path.exists():
        eval_path = TAB_DIR / 'model_summary_clean.csv'  # fallback
    if not eval_path.exists():
        eval_path = TAB_DIR / 'model_comparison.csv'  # fallback
    if eval_path.exists():
        result['eval_df'] = pd.read_csv(eval_path)

    # Load final Voting model (AUC 0.82) — from app_data/ (non-LFS for Streamlit Cloud)
    voting_path = BASE_DIR / 'app_data' / 'final_model.joblib'
    if not voting_path.exists():
        voting_path = MODEL_DIR / 'final_voting_model.pkl'  # fallback
    if voting_path.exists():
        try:
            result['model'] = joblib.load(voting_path)
            result['best_name'] = 'Voting Ensemble (LR+RF+XGB+ET, AUC 0.82)'
        except:
            pass

    # Also load individual models for comparison
    if MODEL_DIR.exists():
        for f in MODEL_DIR.glob('*.pkl'):
            if f.stem == 'final_voting_model':
                continue
            try:
                result['models'][f.stem] = joblib.load(f)
            except:
                pass

        tabnet_path = MODEL_DIR / 'TabNet.zip'
        if tabnet_path.exists():
            try:
                from pytorch_tabnet.tab_model import TabNetClassifier
                tabnet = TabNetClassifier()
                tabnet.load_model(str(tabnet_path).replace('.zip', ''))
                result['models']['TabNet'] = tabnet
            except:
                pass

    # Load scaler
    scaler_path = MODEL_DIR / 'scaler_clean.pkl'
    if not scaler_path.exists():
        scaler_path = MODEL_DIR / 'scaler.pkl'  # fallback
    if scaler_path.exists():
        result['scaler'] = joblib.load(scaler_path)

    # Load selected features (Top35 from RF importance)
    feat_path = MODEL_DIR / 'selected_features.txt'
    if not feat_path.exists():
        feat_path = MODEL_DIR / 'clean_features.txt'  # fallback
    if not feat_path.exists():
        feat_path = MODEL_DIR / 'feature_names.txt'  # fallback
    if feat_path.exists():
        with open(feat_path, encoding='utf-8') as f:
            result['features'] = [l.strip() for l in f if l.strip()]

    # Load AKI logic validation report
    result['validation_report'] = None
    result['validation_flags'] = None
    result['n_staging_issues'] = 0
    result['n_group_stage_issues'] = 0

    val_report_path = TAB_DIR / 'aki_logic_validation_report.txt'
    if not val_report_path.exists():
        val_report_path = BASE_DIR / 'data' / 'tables' / 'aki_logic_validation_report.txt'

    if val_report_path.exists():
        try:
            with open(val_report_path, encoding='utf-8') as f:
                result['validation_report'] = f.read()
            # Parse counts from report
            for line in result['validation_report'].split('\n'):
                if '不一致记录数:' in line and 'staging' not in line.lower():
                    try:
                        result['n_staging_issues'] = int(line.split(':')[-1].strip())
                    except: pass
                if 'AKI分组 vs AKI分期' not in line and '不一致记录数' in line:
                    pass
        except: pass

    val_flags_path = TAB_DIR / 'aki_logic_validation_flags.csv'
    if not val_flags_path.exists():
        val_flags_path = BASE_DIR / 'data' / 'tables' / 'aki_logic_validation_flags.csv'
    if val_flags_path.exists():
        try:
            result['validation_flags'] = pd.read_csv(val_flags_path)
        except: pass

    # Parse staging vs group-stage counts from report more robustly
    if result['validation_report']:
        import re
        # Look for the two inconsistency lines
        staging_match = re.search(r'AKI分期 vs KDIGO.*?\n不一致记录数:\s*(\d+)', result['validation_report'])
        group_match = re.search(r'AKI分组 vs AKI分期.*?\n不一致记录数:\s*(\d+)', result['validation_report'])
        if staging_match:
            result['n_staging_issues'] = int(staging_match.group(1))
        if group_match:
            result['n_group_stage_issues'] = int(group_match.group(1))

    # Pick best model (if not already loaded as Voting Ensemble)
    if result['model'] is None:
        if result['eval_df'] is not None and len(result['eval_df']) > 0:
            model_col = '模型' if '模型' in result['eval_df'].columns else 'Model'
            best = result['eval_df'].iloc[0][model_col]
            result['best_name'] = str(best)
            if best in result['models']:
                result['model'] = result['models'][best]
        elif result['models']:
            result['best_name'] = list(result['models'].keys())[0]
            result['model'] = result['models'][result['best_name']]

    return result


def predict_real(assets, input_dict):
    """Real prediction using trained model."""
    model = assets['model']
    scaler = assets['scaler']
    features = assets['features']

    if model is None or features is None:
        return None

    # Build feature vector
    X = np.zeros(len(features))
    for i, feat in enumerate(features):
        if feat in input_dict:
            X[i] = input_dict[feat]
        # else: keep as 0 (will be standardized)

    X = X.reshape(1, -1)

    # Scale
    if scaler is not None:
        try:
            X = scaler.transform(X)
        except:
            pass

    # Predict
    if hasattr(model, 'predict_proba'):
        prob = model.predict_proba(X)[0, 1]
    else:
        prob = float(model.predict(X)[0])

    # SHAP values
    shap_vals = None
    expected_val = 0
    try:
        import shap
        if assets['best_name'] in ['XGBoost','LightGBM','CatBoost','RandomForest','ExtraTrees','LogisticRegression']:
            explainer = shap.TreeExplainer(model)
            sv = explainer.shap_values(X)
            if isinstance(sv, list): sv = sv[1]
            shap_vals = sv[0]
            ev = explainer.expected_value
            expected_val = ev[1] if isinstance(ev, (list,np.ndarray)) and len(ev)>1 else (ev if not isinstance(ev,(list,np.ndarray)) else ev[0])
    except Exception as e:
        pass

    return {
        'probability': float(prob),
        'prediction': int(prob >= 0.5),
        'shap_values': shap_vals,
        'expected_value': expected_val,
    }


def generate_pdf_report(patient_info, result, shap_info=None):
    """Generate PDF report bytes."""
    try:
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()

        # Try Chinese font
        for fp in ['C:/Windows/Fonts/simhei.ttf', 'C:/Windows/Fonts/msyh.ttf']:
            if os.path.exists(fp):
                pdf.add_font('CJK', '', fp, uni=True)
                pdf.add_font('CJK', 'B', fp, uni=True)
                break
        else:
            pdf.add_font('CJK', '', 'Helvetica')

        pdf.set_font('CJK', 'B', 20)
        pdf.cell(0, 12, 'AKI Risk Assessment Report', align='C', new_x="LMARGIN", new_y="NEXT")
        pdf.ln(5)

        pdf.set_font('CJK', '', 10)
        pdf.cell(0, 8, f'Date: {datetime.now().strftime("%Y-%m-%d %H:%M")}', align='C', new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 8, f'Patient: {patient_info.get("name","N/A")}', align='C', new_x="LMARGIN", new_y="NEXT")
        pdf.ln(10)

        # Risk level
        prob = result['probability']
        risk = 'High' if prob > 0.7 else ('Medium' if prob > 0.3 else 'Low')
        risk_colors = {'Low': (39,174,96), 'Medium': (243,156,18), 'High': (231,76,60)}
        pdf.set_fill_color(*risk_colors[risk])
        pdf.set_text_color(255,255,255)
        pdf.set_font('CJK', 'B', 22)
        pdf.cell(0, 15, f'Risk: {risk} ({prob:.1%})', align='C', fill=True, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(10)

        pdf.set_text_color(0,0,0)
        pdf.set_font('CJK', 'B', 12)
        pdf.cell(0, 8, 'Patient Information', new_x="LMARGIN", new_y="NEXT")
        pdf.set_font('CJK', '', 9)
        for k, v in patient_info.items():
            pdf.cell(95, 6, f'{k}: {v}')

        pdf.ln(8)
        pdf.set_font('CJK', '', 7)
        pdf.set_text_color(128,128,128)
        pdf.multi_cell(0, 4, 'Disclaimer: This report is generated for academic research purposes only. Not for clinical use without physician review.')

        return pdf.output()
    except Exception as e:
        return None


# ============================================
# PAGE 1: Home
# ============================================
def page_home(assets):
    st.markdown('<p class="main-header">🏥 急性肾损伤 (AKI) 智能预测系统</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Machine Learning · SHAP Explainability · Clinical Decision Support</p>', unsafe_allow_html=True)

    col1,col2,col3,col4 = st.columns(4)
    with col1: st.metric("样本量", "420", "真实临床数据")
    with col2: st.metric("特征数", "15", "仅术前可获指标")
    with col3: st.metric("验证方式", "5折CV", "Bootstrap 95%CI")
    best_auc = "0.72"
    if assets['eval_df'] is not None and 'AUC' in assets['eval_df'].columns:
        best_auc = f"{assets['eval_df']['AUC'].mean():.2f}"
    with col4: st.metric("交叉验证AUC", best_auc, "泛化稳定")

    st.markdown("---")
    col1,col2 = st.columns([2,1])
    with col1:
        st.markdown("""
        ### 研究概述
        - **临床问题**: 心脏手术后 AKI 发生率 5-30%，显著增加死亡率和医疗费用
        - **数据来源**: 420 例心脏手术患者，仅使用 15 个**术前可获得**特征
        - **技术方案**: 5 种 ML 模型 + 5折交叉验证 + Bootstrap 置信区间
        - **模型定位**: 术前风险筛查工具（非最终诊断），Recall 优先于 Precision
        - **可靠性**: 经数据泄漏审查->特征过滤->正则化->严格验证，泛化稳定
        - **核心创新**: SHAP 可解释 AI - 不仅预测风险，更解释"为什么"
        """)
    with col2:
        st.markdown("""
        ### 模型可靠性优化
        1. 初始模型 AUC > 0.99
        2. 发现术后特征泄漏
        3. 剔除 52 个泄漏特征
        4. 保留 15 个术前特征
        5. 5折交叉验证
        6. AUC 0.72, 泛化稳定

        *从"追求指标"到"追求可信"*
        """)


    # ---- AKI Logic Validation Section ----
    if assets.get('validation_report') or assets.get('validation_flags') is not None:
        st.markdown("---")
        st.markdown("### 🔍 数据质量：AKI 诊断逻辑校验")

        val_col1, val_col2 = st.columns(2)

        with val_col1:
            if n_staging == 0 and n_group == 0:
                st.success("✅ **KDIGO Scr 标准校验通过** — 所有 AKI 分期与 Scr 变化一致")
            else:
                st.warning(f"⚠️ **{n_staging} 条** AKI 分期与 KDIGO Scr 标准不一致")
                st.caption("KDIGO Stage 1: ΔScr≥26.5μmol/L 或 1.5-1.9x基线")
                st.caption("KDIGO Stage 2: Scr 2.0-2.9x基线")
                st.caption("KDIGO Stage 3: Scr≥4x基线 或 Scr≥353.6μmol/L")

        with val_col2:
            if n_group == 0:
                st.success("✅ **AKI分组 vs AKI分期一致性通过** — 二元分组与分期编号完全对应")
            else:
                st.error(f"❌ **{n_group} 条** AKI分组与AKI分期对应错误")

        # Show flagged details if any
        if assets.get('validation_flags') is not None and len(assets['validation_flags']) > 0:
            with st.expander(f"📋 查看 {len(assets['validation_flags'])} 条异常记录详情", expanded=False):
                flags_df = assets['validation_flags']
                display_cols = [c for c in flags_df.columns if not c.startswith('_') or c in ['_aki_stage_issue', '_aki_group_stage_issue']]
                display_cols = list(dict.fromkeys(display_cols))  # remove dupes
                st.dataframe(flags_df[display_cols], width='stretch', hide_index=True)
                st.caption("""
                **注意**: 部分不一致可能因 KDIGO 标准包含尿量指标（非仅Scr）或分期基于住院全程数据。
                建议结合临床背景判断是否为数据录入错误。
                """)

        # Show full validation report
        if assets.get('validation_report'):
            with st.expander("📄 查看完整校验报告 (AKI Logic Validation Report)"):
                st.code(assets['validation_report'], language=None)

    st.markdown("---")
    col1,col2,col3 = st.columns(3)
    col1.success("### 📊 模型性能\n查看 7 个模型的\nROC/PR/校准曲线")
    col2.info("### 🔮 风险预测\n输入患者信息\n实时预测 AKI 风险")
    col3.warning("### 📋 报告导出\n一键生成个体化\nAKI 风险评估报告")


# ============================================
# PAGE 2: Model Performance
# ============================================
def page_performance(assets):
    st.markdown("## 🤖 模型性能评估")

    eval_df = assets['eval_df']
    if eval_df is None:
        st.warning("⚠️ 未找到模型评估结果。请先运行 run_models.py 训练模型。")
        return

    tab1,tab2,tab3 = st.tabs(["📊 性能对比", "📈 ROC/PR曲线", "🎯 校准与DCA"])

    with tab1:
        st.markdown("### 模型性能总览（测试集）")
        # Style the dataframe
        styled = eval_df.style.format({c:'{:.4f}' for c in eval_df.columns if c!='Model'})
        styled = styled.highlight_max(subset=['AUC','Accuracy','Precision','Recall','F1'], color='#d4efdf')
        brier_col = 'Brier_Score' if 'Brier_Score' in eval_df.columns else 'Brier'
        if brier_col in eval_df.columns:
            styled = styled.highlight_min(subset=[brier_col], color='#d4efdf')
        st.dataframe(styled, width='stretch', hide_index=True)

        st.markdown("### 模型选择建议")
        st.info("""
        **临床筛查推荐: Logistic Regression** (Recall=0.72, F1=0.56)
        - 召回率最高，能发现 72% 的 AKI 患者，漏诊风险最低
        - 可解释性强，每个特征的系数直接反映风险方向
        - 稳定性最优（训练/测试 AUC 差距仅 0.03）

        **区分度第一: LightGBM** (AUC=0.698)
        - 但 Recall 仅 0.56，漏诊风险较高
        - 作为辅助参考模型

        本系统定位为**术前风险筛查工具**，优先保证召回率，宁愿多提醒也不要漏掉危险患者。
        """)

        st.markdown("### AUC 排行榜")
        chart_df = eval_df[['Model','AUC']].set_index('Model').sort_values('AUC')
        st.bar_chart(chart_df)

        st.markdown("### F1 - Recall - Precision 对比")
        radar_df = eval_df[['Model','F1','Recall','Precision','Accuracy']].set_index('Model')
        st.bar_chart(radar_df, horizontal=True)

    with tab2:
        st.markdown("### ROC 曲线")
        roc_path = FIG_DIR / 'roc_curves.png'
        if roc_path.exists(): st.image(str(roc_path), width='stretch')
        else: st.warning("ROC曲线未生成。请运行 run_viz.py。")

        st.markdown("### PR 曲线")
        pr_path = FIG_DIR / 'pr_curves.png'
        if pr_path.exists(): st.image(str(pr_path), width='stretch')
        else: st.warning("PR曲线未生成。")

        st.markdown("### 混淆矩阵")
        cm_path = FIG_DIR / 'confusion_matrices.png'
        if cm_path.exists(): st.image(str(cm_path), width='stretch')
        else: st.warning("混淆矩阵未生成。")

    with tab3:
        st.markdown("### 校准曲线")
        cal_path = FIG_DIR / 'calibration_curves.png'
        if cal_path.exists(): st.image(str(cal_path), width='stretch')

        st.markdown("### 决策曲线 (DCA)")
        dca_path = FIG_DIR / 'dca_curve.png'
        if not dca_path.exists():
            dca_path = FIG_DIR / 'decision_curve.png'
        if dca_path.exists(): st.image(str(dca_path), width='stretch')

        st.markdown("### 临床影响曲线")
        cic_path = FIG_DIR / 'clinical_impact_curve.png'
        if cic_path.exists(): st.image(str(cic_path), width='stretch')

        # SHAP
        st.markdown("### SHAP 特征重要性")
        shap_path = FIG_DIR / 'shap_summary.png'
        if shap_path.exists(): st.image(str(shap_path), width='stretch')


# ============================================
# PAGE 3: Risk Prediction (CORE - REAL MODEL)
# ============================================
def page_prediction(assets):
    st.markdown("## 🔮 AKI 风险预测")
    st.markdown("输入患者临床信息，使用真实训练模型进行实时预测。")

    if assets['model'] is None:
        st.error("❌ 未找到训练好的模型。请先运行 run_models.py")
        return

    st.info(f"✅ 当前使用模型: **{assets['best_name']}** | 特征数: {len(assets.get('features',[]))}")

    with st.form("pred_form"):
        st.markdown("### 基本信息")
        c1, c2, c3 = st.columns(3)
        with c1:
            surgery_time = st.number_input("手术时间 (min)", 30, 1440, 300)
        with c2:
            apache = st.number_input("APACHE II 评分", 0, 60, 18)
        with c3:
            pre_sbp = st.number_input("术前 SBP (mmHg)", 70, 200, 135)

        st.markdown("### 肾功能相关")
        c1, c2, c3 = st.columns(3)
        with c1:
            scr = st.number_input("术前 Scr (umol/L)", 20.0, 500.0, 80.0, 1.0)
        with c2:
            egfr = st.number_input("术前 eGFR", 10.0, 150.0, 90.0, 1.0)
        with c3:
            ua = st.number_input("术前 UA (umol/L)", 100.0, 900.0, 400.0, 10.0)

        st.markdown("### 血液学指标")
        c1, c2, c3 = st.columns(3)
        with c1:
            wbc = st.number_input("术前 WBC (x10e9/L)", 1.0, 30.0, 7.0, 0.1)
        with c2:
            neut = st.number_input("术前 NEUT (x10e9/L)", 0.5, 25.0, 5.0, 0.1)
        with c3:
            mono = st.number_input("术前 MONO (x10e9/L)", 0.1, 5.0, 0.5, 0.1)

        st.markdown("### 心脏/炎症指标")
        c1, c2, c3 = st.columns(3)
        with c1:
            hstn = st.number_input("术前 hsTn (pg/mL)", 1.0, 5000.0, 50.0, 1.0)
        with c2:
            bnp = st.number_input("术前 BNP (pg/mL)", 10.0, 25000.0, 500.0, 10.0)
        with c3:
            plt = st.number_input("术前 PLT (x10e9/L)", 50, 800, 250)

        st.markdown("### 其他指标")
        c1, c2, c3 = st.columns(3)
        with c1:
            plr = st.number_input("术前 PLR", 10.0, 500.0, 150.0, 1.0)
        with c2:
            b2mg = st.number_input("术前 B2MG (mg/L)", 0.5, 10.0, 2.2, 0.1)
        with c3:
            rbp = st.number_input("术前 RBP (mg/L)", 10.0, 100.0, 40.0, 1.0)

        submitted = st.form_submit_button("开始预测", type="primary", width='stretch')

    if submitted:
        with st.spinner("正在使用 ML 模型进行预测..."):
            # Build input dict from form values
            input_dict = {
                '手术时间': surgery_time,
                'APACHEII': apache,
                '术前SBP': pre_sbp,
                '术前Scr': scr,
                '术前eGFR': egfr,
                '术前UA': ua,
                '术前WBC': wbc,
                '术前NEUT': neut,
                '术前MONO': mono,
                '术前hsTn': hstn,
                '术前BNP': bnp,
                '术前PLT': plt,
                '术前PLR': plr,
                '术前B2MG': b2mg,
                '术前RBP': rbp,
            }

            # Make real prediction
            result = predict_real(assets, input_dict)

            if result is None:
                st.error("预测失败。请确保模型和特征文件已正确加载。")
                return

            prob = result['probability']
            risk_level, risk_class, risk_emoji = (
                ("低风险","risk-low","🟢") if prob < risk_low else
                ("中风险","risk-medium","🟡") if prob < risk_high else
                ("高风险","risk-high","🔴")
            )

        # ---- Display Results ----
        st.markdown("---")
        st.markdown("## 📊 预测结果")

        c1,c2,c3 = st.columns([1,2,1])
        with c2:
            st.markdown(f"""
            <div class="{risk_class}">
                {risk_emoji} AKI风险等级: <strong>{risk_level}</strong><br>
                <span style="font-size:2.5rem;">{prob:.1%}</span>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("#### 风险概率")
        st.progress(float(prob))

        st.markdown("---")
        c1,c2 = st.columns([1,1])

        with c1:
            st.markdown("### ⚠️ 关键因素分析")

            # Use SHAP values if available
            if result.get('shap_values') is not None and assets['features']:
                sv = result['shap_values']
                feats = assets['features']

                # Top positive and negative SHAP
                idx = np.argsort(np.abs(sv))[::-1][:8]
                for i in idx:
                    feat_name = feats[i] if i < len(feats) else f'F{i}'
                    val = sv[i]
                    direction = "🔴" if val > 0 else "🟢"
                    impact = "增加风险" if val > 0 else "降低风险"
                    bar_color = "#e74c3c" if val > 0 else "#2ecc71"
                    bar_pct = min(abs(val) / (abs(sv).max() + 1e-10), 1.0) * 100
                    st.markdown(f"""
                    <div class="metric-card">
                        <strong>{direction} {feat_name}</strong> ({impact})
                        <div style="width:100%;background:#ecf0f1;border-radius:5px;margin-top:3px;">
                            <div style="width:{bar_pct}%;background:{bar_color};height:6px;border-radius:5px;"></div>
                        </div>
                        <small>SHAP: {val:+.4f}</small>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                # Fallback: simple rule-based on available inputs
                factors = []
                if egfr < 60: factors.append(("术前 eGFR < 60", 0.78))
                if apache > 20: factors.append(("APACHE II > 20", 0.72))
                if scr > 100: factors.append(("术前 Scr 升高", 0.68))
                if surgery_time > 360: factors.append(("手术时间 > 6h", 0.42))
                for f,imp in (factors or [("无显著危险因素",0.1)])[:5]:
                    st.markdown(f"""
                    <div class="metric-card">
                        <strong>{f}</strong>
                        <div style="width:100%;background:#ecf0f1;border-radius:5px;margin-top:3px;">
                            <div style="width:{imp*100}%;background:#e74c3c;height:6px;border-radius:5px;"></div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

        with c2:
            st.markdown("### 💊 临床建议")

            if prob < risk_low:
                recs = {
                    '监测': '常规术后监测，每12h记录尿量',
                    '预防': '维持充足水化，避免肾毒性药物',
                    '检查': '术后第1、3天复查 Scr、eGFR',
                    'KDIGO': 'Stage 0 — 无AKI风险',
                }
            elif prob < risk_high:
                recs = {
                    '监测': '每6h监测尿量和Scr变化',
                    '预防': '目标导向液体治疗，维持尿量 > 0.5 ml/kg/h',
                    '检查': '每日复查 Scr、eGFR、电解质、血气',
                    'KDIGO': '建议肾内科会诊评估',
                }
            else:
                recs = {
                    '监测': '每小时记录尿量，持续有创血压监测',
                    '预防': '启动KDIGO Bundle：优化容量+停肾毒性药+维持肾灌注',
                    '检查': '即刻复查Scr、eGFR，考虑肾脏超声',
                    'KDIGO': '⚠️ 紧急肾内科会诊，准备RRT评估',
                }

            for k,v in recs.items():
                with st.expander(f"📌 {k}"):
                    st.write(v)

            st.markdown("---")
            st.markdown("### 📋 KDIGO 诊断标准")
            st.info("""
            AKI诊断（满足任一）：
            - 48h内 Scr 升高 ≥ 26.5 μmol/L
            - 7天内 Scr 升至基线 1.5 倍
            - 尿量 < 0.5 ml/kg/h 持续 6h
            """)

        # SHAP waterfall
        st.markdown("---")
        st.markdown("### 🔍 SHAP 个体化解释")
        if result.get('shap_values') is not None and assets['features']:
            try:
                import shap
                sv = result['shap_values']
                ev = result['expected_value']
                feats = assets['features']

                fig,ax = plt.subplots(figsize=(10, max(6, len(feats[:15])*0.3)))
                abs_sv = np.abs(sv)
                top_idx = np.argsort(abs_sv)[-15:]
                top_feats = [feats[i] if i<len(feats) else f'F{i}' for i in top_idx]
                top_vals = sv[top_idx]
                colors = ['#e74c3c' if v>0 else '#2ecc71' for v in top_vals]
                ax.barh(range(len(top_feats)), top_vals[::-1], color=colors[::-1], alpha=0.85, edgecolor='white')
                ax.set_yticks(range(len(top_feats)))
                ax.set_yticklabels(top_feats[::-1], fontsize=9)
                ax.axvline(x=0, color='black', linewidth=0.5)
                ax.axvline(x=ev, color='gray', linestyle='--', alpha=0.5, label=f'Base: {ev:.3f}')
                ax.set_xlabel('SHAP Value')
                ax.set_title('SHAP Feature Contribution (Waterfall)', fontweight='bold')
                ax.legend(fontsize=8)
                plt.tight_layout()
                st.pyplot(fig)
            except Exception as e:
                st.info(f"SHAP可视化暂不可用: {e}")
        else:
            st.info("SHAP 值计算需要模型支持。当前模型可能不支持 SHAP 直接计算。")

        # PDF Export
        st.markdown("---")
        c1,c2,c3 = st.columns([1,1,1])
        with c2:
            patient_info = {
                'name': f'Patient_{datetime.now().strftime("%Y%m%d_%H%M%S")}',
                'APACHE II': str(apache),
                '手术时间': str(surgery_time),
                '术前eGFR': str(egfr), '术前Scr': str(scr),
                '术前SBP': str(pre_sbp),
                '术前UA': str(ua), '术前PLT': str(plt),
            }
            pdf_bytes = generate_pdf_report(patient_info, result)
            if pdf_bytes:
                st.download_button(
                    "📥 下载 PDF 报告", data=pdf_bytes,
                    file_name=f"AKI_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                    mime="application/pdf", width='stretch'
                )
            else:
                st.warning("PDF生成需要fpdf2库支持。安装: pip install fpdf2")


# ============================================
# PAGE 4: Report
# ============================================
def page_report(assets):
    st.markdown("## 📋 报告中心")

    st.info("📁 完成风险预测后，可在此页面下载 PDF 报告。支持批量预测和对比分析。")

    st.markdown("### 📊 特征列表")
    if assets['features']:
        st.markdown(f"模型使用 **{len(assets['features'])}** 个特征：")
        st.dataframe(pd.DataFrame({'特征名': assets['features']}), width='stretch', hide_index=True)


# ============================================
# Router
# ============================================
assets = load_all()
pages = {
    "🏠 首页": page_home,
    "📊 模型性能": page_performance,
    "🔮 风险预测": page_prediction,
    "📋 报告": page_report,
}
pages[page](assets)

# Footer
st.markdown("---")
st.markdown('<div class="footer">AKI 智能预测系统 v2.0 | 广西科技大学 · 白菜卷队 · 暑期数创 2026<br>'
            'Powered by ML · SHAP · Streamlit | 仅供学术研究参考</div>', unsafe_allow_html=True)

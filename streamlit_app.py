"""
AKI Prediction System - Streamlit Main Application (Root Entry Point)
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

# Paths — this file lives at repo root, so parent IS the project root
BASE_DIR = Path(__file__).parent
MODEL_DIR = BASE_DIR / 'models'
OUTPUT_DIR = BASE_DIR / 'outputs'
FIG_DIR = OUTPUT_DIR / 'figures'
TAB_DIR = OUTPUT_DIR / 'tables'
PHASE1_FIG_DIR = OUTPUT_DIR / 'phase1' / 'figures'
PHASE1_TAB_DIR = OUTPUT_DIR / 'phase1' / 'tables'
PHASE2_FIG_DIR = OUTPUT_DIR / 'phase2' / 'figures'
PHASE2_TAB_DIR = OUTPUT_DIR / 'phase2' / 'tables'

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
    page = st.radio("导航", ["🏠 首页", "📊 模型性能", "🔮 风险预测", "🏥 医生工作台", "📊 管理仪表盘", "📋 报告", "🔍 数据治理"],
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
        eval_path = TAB_DIR / 'model_comparison.csv'  # fallback
    if eval_path.exists():
        result['eval_df'] = pd.read_csv(eval_path)

    # Load final Voting model (AUC 0.821) — from app_data/ (non-LFS for Streamlit Cloud)
    voting_path = BASE_DIR / 'app_data' / 'final_model.joblib'
    if not voting_path.exists():
        voting_path = MODEL_DIR / 'final_voting_model.pkl'  # fallback
    if voting_path.exists():
        try:
            result['model'] = joblib.load(voting_path)
            result['best_name'] = 'Voting Ensemble (LR+RF+XGB+ET, AUC 0.821)'
        except:
            pass

    # Also load individual models for comparison display
    if MODEL_DIR.exists():
        for f in MODEL_DIR.glob('*.pkl'):
            if f.stem == 'final_voting_model':
                continue  # already loaded
            try:
                result['models'][f.stem] = joblib.load(f)
            except:
                pass

    # Load scaler — from app_data/ (non-LFS) first
    scaler_path = BASE_DIR / 'app_data' / 'scaler.joblib'
    if not scaler_path.exists():
        scaler_path = MODEL_DIR / 'scaler.pkl'  # fallback
    if scaler_path.exists():
        result['scaler'] = joblib.load(scaler_path)

    # Load selected features — from app_data/ (non-LFS) first
    feat_path = BASE_DIR / 'app_data' / 'features.txt'
    if not feat_path.exists():
        feat_path = MODEL_DIR / 'selected_features.txt'  # fallback
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
            # Support both old (Model) and new (模型) column names
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

        # Risk level (use sidebar slider values for consistency)
        prob = result['probability']
        _rl = risk_low if 'risk_low' in dir() else 0.3
        _rh = risk_high if 'risk_high' in dir() else 0.7
        risk = 'High' if prob > _rh else ('Medium' if prob > _rl else 'Low')
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

    col1,col2,col3,col4,col5 = st.columns(5)
    with col1: st.metric("📊 样本量", "420", "真实临床数据")
    with col2: st.metric("🧬 特征数", "94", "处理后")
    with col3: st.metric("🤖 模型数", "8", "全部训练完成")

    best_auc = "N/A"
    if assets['eval_df'] is not None:
        best_auc = f"{assets['eval_df'].iloc[0]['AUC']:.4f}"
    with col4: st.metric("🎯 最佳AUC", best_auc, assets.get('best_name',''))

    # Show data quality validation status
    n_staging = assets.get('n_staging_issues', 0)
    n_group = assets.get('n_group_stage_issues', 0)
    if n_staging == 0 and n_group == 0:
        with col5: st.metric("✅ 逻辑校验", "通过", "KDIGO一致")
    else:
        with col5: st.metric("⚠️ 逻辑校验", f"{n_staging + n_group}条异常", f"分期{n_staging}+分组{n_group}")

    st.markdown("---")
    col1,col2 = st.columns([2,1])
    with col1:
        st.markdown("""
        ### 📖 研究概述
        - **临床问题**: 心脏手术后 AKI 发生率 5-30%，显著增加死亡率和医疗费用
        - **数据来源**: 420 例心脏手术患者，95+ 临床特征
        - **技术方案**: 5 种 ML 模型系统比较 + 94 特征 + SMOTE 类别平衡
        - **核心创新**: SHAP 可解释 AI — 不仅预测风险，更解释"为什么"
        - **系统功能**: 在线预测 → 风险分层 → 危险因素 → 干预建议 → PDF 报告
        """)
    with col2:
        st.image("https://img.icons8.com/color/144/hospital.png", width=120)

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
    col1.success("### 📊 模型性能\n查看 5 个模型的\nROC/PR/校准曲线")
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

    tab1,tab2,tab3,tab4,tab5,tab6 = st.tabs(["📊 性能对比", "📈 ROC/PR曲线", "🎯 校准与DCA", "📉 CV可信度", "🔬 消融实验", "🤝 集成对比"])

    with tab1:
        st.markdown("### 模型性能总览（50次重复CV）")
        # Support both new (模型/50次CV AUC均值) and old (Model/AUC) formats
        model_col = '模型' if '模型' in eval_df.columns else 'Model'
        auc_col = '50次CV AUC均值' if '50次CV AUC均值' in eval_df.columns else 'AUC'
        std_col = '标准差' if '标准差' in eval_df.columns else None

        # Build display dataframe
        if std_col and std_col in eval_df.columns:
            display_df = eval_df[[model_col, auc_col, std_col]].copy()
            display_df.columns = ['模型', 'AUC (CV)', '标准差']
        else:
            numeric_cols = [c for c in eval_df.columns if c != model_col]
            display_df = eval_df[[model_col] + numeric_cols]

        st.dataframe(display_df, width='stretch', hide_index=True)

        if auc_col in eval_df.columns:
            st.markdown("#### AUC 排行榜")
            chart_df = eval_df[[model_col, auc_col]].set_index(model_col).sort_values(auc_col)
            st.bar_chart(chart_df)

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
        dca_path = FIG_DIR / 'decision_curve.png'
        if dca_path.exists(): st.image(str(dca_path), width='stretch')

        st.markdown("### 临床影响曲线")
        cic_path = FIG_DIR / 'clinical_impact_curve.png'
        if cic_path.exists(): st.image(str(cic_path), width='stretch')

        # SHAP
        st.markdown("### SHAP 特征重要性")
        shap_path = FIG_DIR / 'shap_summary.png'
        if shap_path.exists(): st.image(str(shap_path), width='stretch')

    with tab4:
        st.markdown("### 📉 交叉验证可信度")
        st.caption("五折分层交叉验证 — 均值ROC曲线 ± 1标准差置信带")
        # Try Phase 1 output first, then figures/
        cv_roc_path = PHASE1_FIG_DIR / 'cv_roc_with_ci.png'
        if not cv_roc_path.exists():
            cv_roc_path = FIG_DIR / 'cv_roc_with_ci.png'
        if cv_roc_path.exists():
            st.image(str(cv_roc_path), width='stretch')
        else:
            st.info("📌 五折CV ROC曲线未生成。请运行: python run_models.py --skip-ablation --skip-dca --skip-shap --skip-datagov")

        st.markdown("---")
        st.markdown("### 🎲 Bootstrap AUC分布")
        cv_auc_path = PHASE1_FIG_DIR / 'bootstrap_auc_dist.png'
        if not cv_auc_path.exists():
            cv_auc_path = PHASE1_FIG_DIR / 'cv_auc_distribution.png'
        if not cv_auc_path.exists():
            cv_auc_path = FIG_DIR / 'cv_auc_distribution.png'
        if cv_auc_path.exists():
            st.image(str(cv_auc_path), width='stretch')
        else:
            st.info("📌 Bootstrap AUC分布图未生成。")

        # CV summary table
        cv_table_path = PHASE1_TAB_DIR / 'cv_fold_results.csv'
        if not cv_table_path.exists():
            cv_table_path = TAB_DIR / 'cv_fold_results.csv'
        if cv_table_path.exists():
            st.markdown("---")
            st.markdown("### 📊 五折交叉验证结果")
            cv_df = pd.read_csv(cv_table_path)
            st.dataframe(cv_df, width='stretch', hide_index=True)

    with tab5:
        st.markdown("### 🔬 特征消融实验")
        st.caption('逐步移除特征组，观察模型AUC变化 — 回答"哪个特征组贡献最大？"')

        # Ablation heatmap
        abl_heat_path = PHASE1_FIG_DIR / 'ablation_heatmap.png'
        if not abl_heat_path.exists():
            abl_heat_path = FIG_DIR / 'ablation_heatmap.png'
        if abl_heat_path.exists():
            st.image(str(abl_heat_path), width='stretch')
        else:
            st.info("📌 消融热力图未生成。请运行: python run_models.py --skip-cv --skip-dca --skip-shap --skip-datagov")

        # Individual model ablation charts
        st.markdown("---")
        st.markdown("#### 📊 各模型消融详情")
        abl_model = st.selectbox("选择模型", ["xgboost", "randomforest", "catboost", "lightgbm", "logisticregression"],
                                  format_func=lambda x: x.upper() if x == 'xgboost' else x.title())
        abl_bar_path = PHASE1_FIG_DIR / f'ablation_{abl_model}.png'
        if abl_bar_path.exists():
            st.image(str(abl_bar_path), width='stretch')
        else:
            st.info(f"📌 {abl_model} 消融图未生成。")

        # Ablation comparison table
        abl_table_path = PHASE1_TAB_DIR / 'ablation_results.csv'
        if not abl_table_path.exists():
            abl_table_path = TAB_DIR / 'ablation_results.csv'
        if abl_table_path.exists():
            st.markdown("---")
            st.markdown("### 📊 消融对比表")
            abl_df = pd.read_csv(abl_table_path)
            st.dataframe(abl_df, width='stretch', hide_index=True)
            # Highlight key insight
            st.success("💡 **消融实验核心发现**: 移除特定特征组后AUC下降越大，说明该组特征贡献越高。可用于答辩中解释特征工程的价值。")

    with tab6:
        st.markdown("### 🤝 集成方法对比 (Phase 2)")
        st.caption("Voting vs Stacking vs Weighted Average — 三种集成策略完整对比")

        # Ensemble comparison chart
        ens_path = PHASE2_FIG_DIR / 'ensemble_comparison.png'
        if not ens_path.exists():
            ens_path = FIG_DIR / 'ensemble_comparison.png'
        if ens_path.exists():
            st.image(str(ens_path), width='stretch')
        else:
            st.info("📌 集成对比图未生成。请运行 Phase 2 Ensemble Pipeline。")

        # Ensemble summary
        st.markdown("---")
        st.markdown("### 💡 集成方法说明")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("""
            **Voting (投票法)**
            - 多个模型"投票"决定最终预测
            - Soft Voting: 概率平均
            - 简单稳定，不易过拟合
            """)
        with c2:
            st.markdown("""
            **Stacking (堆叠法)**
            - 元学习器学习如何组合基模型
            - 自动发现最优组合权重
            - 通常比Voting更强
            """)
        with c3:
            st.markdown("""
            **Weighted Avg (加权平均)**
            - 手动/自动分配模型权重
            - 灵活可调，可解释性强
            - 网格搜索最优权重
            """)


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
        st.markdown("### 📝 患者基本信息")
        c1,c2,c3 = st.columns(3)
        with c1:
            age = st.number_input("年龄", 18, 100, 55)
            gender = st.selectbox("性别", ["男","女"], index=0)
            ht = st.selectbox("高血压", ["否","是"], index=0)
            dm = st.selectbox("糖尿病", ["否","是"], index=0)
            chd = st.selectbox("冠心病", ["否","是"], index=0)
        with c2:
            surgery = st.selectbox("手术类型", ["心脏瓣膜手术","联合手术","结构性心脏病手术","冠状动脉旁路移植术","其他手术","大血管疾病手术"])
            surgery_time = st.number_input("手术时间 (min)", 30, 1440, 300)
            apache = st.number_input("APACHE II 评分", 0, 60, 18)
            blood_loss = st.number_input("术中失血量 (ml)", 0, 5000, 400)
            vent_time = st.number_input("术后通气时间 (min)", 0, 50000, 360)
        with c3:
            total_days = st.number_input("总住院天数", 1, 200, 22)
            icu_days = st.number_input("ICU 住院天数", 0.0, 50.0, 2.0, 0.5)
            cost = st.number_input("总住院费用 (元)", 10000.0, 500000.0, 90000.0, 1000.0)

        st.markdown("### 🔬 术前实验室指标")
        c1,c2,c3 = st.columns(3)
        with c1:
            scr = st.number_input("术前 Scr (μmol/L)", 20.0, 500.0, 80.0, 1.0)
            egfr = st.number_input("术前 eGFR", 10.0, 150.0, 90.0, 1.0)
            alb = st.number_input("术前 Alb (g/L)", 15.0, 60.0, 40.0, 0.1)
            hb = st.number_input("术前 Hb (g/L)", 50.0, 200.0, 130.0, 1.0)
            wbc = st.number_input("术前 WBC (x10e9/L)", 1.0, 30.0, 7.0, 0.1)
        with c2:
            crp = st.number_input("术前 CRP (mg/L)", 0.0, 200.0, 5.0, 0.1)
            lactate = st.number_input("术前 Lactate (mmol/L)", 0.1, 15.0, 1.0, 0.1)
            nlr = st.number_input("术前 NLR", 0.1, 30.0, 3.0, 0.1)
            bnp = st.number_input("术前 BNP (pg/mL)", 10.0, 25000.0, 500.0, 10.0)
            ph = st.number_input("术前 pH", 7.0, 7.6, 7.4, 0.01)
        with c3:
            k_val = st.number_input("术前 K+ (mmol/L)", 2.5, 7.0, 4.0, 0.01)
            urea = st.number_input("术前 Urea (mmol/L)", 1.0, 25.0, 5.5, 0.1)
            ua = st.number_input("术前 UA (μmol/L)", 100.0, 900.0, 400.0, 10.0)
            plt = st.number_input("术前 PLT (x10e9/L)", 50, 800, 250)

        st.markdown("### 🏥 术中/术后指标")
        c1,c2,c3 = st.columns(3)
        with c1:
            intra_urine = st.number_input("术中尿量 (ml)", 0, 10000, 1000)
            intra_cryst = st.number_input("术中晶体液量 (ml)", 0, 5000, 700, 10)
            intra_colloid = st.number_input("术中胶体液量 (ml)", 0, 3000, 700, 10)
        with c2:
            pre_sbp = st.number_input("术前 SBP (mmHg)", 70, 200, 135)
            pre_dbp = st.number_input("术前 DBP (mmHg)", 30, 120, 75)
        with c3:
            icu_scr = st.number_input("ICU入院 Scr (μmol/L)", 20.0, 500.0, 80.0, 1.0)
            icu_egfr = st.number_input("ICU入院 eGFR", 10.0, 150.0, 90.0, 1.0)

        submitted = st.form_submit_button("🔍 开始预测", type="primary", width='stretch')

    if submitted:
        with st.spinner("正在使用 ML 模型进行预测..."):
            # Build input dict from form values
            input_dict = {
                '年龄': age, '性别': 1 if gender=='男' else 2,
                '高血压': 1 if ht=='是' else 0,
                '糖尿病': 1 if dm=='是' else 0,
                '冠心病': 1 if chd=='是' else 0,
                'APACHEII': apache, '手术时间': surgery_time,
                '术中失血量': blood_loss, '术中尿量': intra_urine,
                '术中晶体液量': intra_cryst, '术中胶体液量': intra_colloid,
                '术前Scr': scr, '术前eGFR': egfr, '术前Alb': alb,
                '术前Hb': hb, '术前WBC': wbc, '术前CRP': crp,
                '术前Lactate': lactate, '术前NLR': nlr, '术前BNP': bnp,
                '术前pH': ph, '术前K': k_val, '术前Urea': urea,
                '术前UA': ua, '术前PLT': plt,
                '术前SBP': pre_sbp, '术前DBP': pre_dbp,
                'ICUAdmSCr': icu_scr, 'ICUAdmeGFR': icu_egfr,
                '总住院天数': total_days, '总住院费用': cost,
                '术后通气时间': vent_time, 'ICU住院天数': icu_days,
                '手术类型': surgery,  # will be label-encoded
            }

            # Make real prediction
            result = predict_real(assets, input_dict)

            if result is None:
                st.error("预测失败。请确保模型和特征文件已正确加载。")
                return

            prob = result['probability']
            # Star rating: 0-20%=1★, 20-40%=2★, 40-60%=3★, 60-80%=4★, 80-100%=5★
            n_stars = min(5, max(1, int(prob * 5) + 1))
            stars_filled = "★" * n_stars
            stars_empty = "☆" * (5 - n_stars)
            risk_level, risk_class, risk_color = (
                ("低风险","risk-low","#27ae60") if prob < risk_low else
                ("中风险","risk-medium","#f39c12") if prob < risk_high else
                ("高风险","risk-high","#e74c3c")
            )
            risk_emoji = {"低风险":"🟢","中风险":"🟡","高风险":"🔴"}[risk_level]

        # ---- Display Results ----
        st.markdown("---")
        st.markdown("## 📊 预测结果")

        c1,c2,c3 = st.columns([1,2,1])
        with c2:
            # Star rating display
            st.markdown(f"""
            <div class="{risk_class}">
                <div style="font-size:2.8rem;letter-spacing:6px;margin-bottom:8px;
                     text-shadow:0 2px 8px rgba(0,0,0,0.3);">
                    {stars_filled}<span style="opacity:0.5;">{stars_empty}</span>
                </div>
                {risk_emoji} AKI风险等级: <strong>{risk_level}</strong><br>
                <span style="font-size:2.5rem;">{prob:.1%}</span>
            </div>
            """, unsafe_allow_html=True)

        # Risk gauge visual
        st.markdown("#### 风险概率")
        st.progress(float(prob))
        c1,c2,c3 = st.columns(3)
        with c1:
            st.metric("风险等级", f"{risk_level} ({n_stars}/5★)")
        with c2:
            st.metric("预测概率", f"{prob:.1%}")
        with c3:
            # KDIGO stage estimate (Phase 2: using map_kdigo_stage)
            try:
                from src.models.calibration import map_kdigo_stage
                kdigo = map_kdigo_stage(prob)
                st.metric("预估KDIGO", kdigo['label'])
            except:
                kdigo_stage = "Stage 0" if prob < 0.3 else ("Stage 1" if prob < 0.5 else ("Stage 2" if prob < 0.7 else "Stage 3"))
                st.metric("预估KDIGO", kdigo_stage)

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
                # Fallback: simple rule-based
                factors = []
                if age > 60: factors.append(("年龄 > 60岁", 0.85))
                if egfr < 60: factors.append(("术前 eGFR < 60", 0.78))
                if apache > 20: factors.append(("APACHE II > 20", 0.72))
                if scr > 100: factors.append(("术前 Scr 升高", 0.68))
                if dm == "是": factors.append(("糖尿病史", 0.55))
                if lactate > 2: factors.append(("术前乳酸升高", 0.48))
                if surgery_time > 360: factors.append(("手术时间 > 6h", 0.42))
                if crp > 10: factors.append(("术前 CRP 升高", 0.38))
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

        # ============================================
        # COUNTERFACTUAL "WHAT-IF" ANALYSIS
        # ============================================
        st.markdown("---")
        st.markdown("### 🔄 反事实分析 (What-If)")
        st.caption("调整关键特征值，探索\"如果指标改变，风险会如何变化？\"")

        if result.get('shap_values') is not None and assets['features'] and assets['model']:
            cf_features = assets['features']
            cf_shap = result['shap_values']

            # Get top 5 influential features
            cf_top_idx = np.argsort(np.abs(cf_shap))[::-1][:5]
            cf_top_names = [cf_features[i] if i < len(cf_features) else f'F{i}' for i in cf_top_idx]

            cf_selected = st.selectbox(
                "选择要分析的特征", cf_top_names,
                help="选择一个特征，调整其数值，观察预测风险的变化"
            )

            cf_idx = cf_top_names.index(cf_selected)
            cf_real_idx = cf_top_idx[cf_idx]

            # Determine feature range for the slider
            cf_shap_val = cf_shap[cf_real_idx]
            cf_direction = "增加风险" if cf_shap_val > 0 else "降低风险"

            # Default ranges based on common clinical features
            cf_range_map = {
                'Scr': (20, 300, 80), 'eGFR': (15, 120, 90),
                '年龄': (18, 90, 55), 'APACHE': (0, 40, 15),
                'Hb': (50, 180, 130), 'Alb': (15, 55, 40),
                '手术时间': (60, 720, 240), '乳酸': (0.3, 10, 1.5),
                'CRP': (0, 50, 5), 'WBC': (1, 30, 8),
            }
            cf_default_range = (0.0, 100.0, 50.0)

            # Try to guess range from feature name
            cf_match = None
            for key, (lo, hi, default) in cf_range_map.items():
                if key.lower() in cf_selected.lower():
                    cf_match = (lo, hi, default)
                    break

            if cf_match:
                cf_lo, cf_hi, cf_default = cf_match
            else:
                cf_lo, cf_hi, cf_default = cf_default_range

            # Build a simple feature vector for counterfactual
            try:
                model = assets['model']
                # Generate counterfactual curve
                cf_values = np.linspace(cf_lo, cf_hi, 20)
                cf_probs = []
                cf_base_input = np.zeros(len(cf_features))

                # We need reference values for other features - use the prediction context
                # Create a reference input from the form values
                for i, feat in enumerate(cf_features):
                    if feat == cf_selected:
                        continue  # will vary this one
                    # Use form values as reference
                    val_str = None
                    if 'Scr' in feat or 'scr' in feat.lower() or '肌酐' in feat:
                        val_str = str(scr)
                    elif 'eGFR' in feat or 'egfr' in feat.lower():
                        val_str = str(egfr)
                    elif 'APACHE' in feat or 'apache' in feat.lower():
                        val_str = str(apache)
                    elif 'Alb' in feat or 'alb' in feat.lower() or '白蛋白' in feat:
                        val_str = str(alb)
                    elif 'Hb' in feat or 'hb' in feat.lower() or '血红蛋白' in feat:
                        val_str = str(hb)
                    elif 'lactate' in feat.lower() or '乳酸' in feat:
                        val_str = str(lactate)
                    elif '手术时间' in feat:
                        val_str = str(surgery_time)
                    elif '通气时间' in feat:
                        val_str = str(vent_time)
                    elif '失血' in feat or 'blood_loss' in feat.lower():
                        val_str = str(blood_loss)
                    elif '住院天数' in feat:
                        val_str = str(total_days)
                    elif 'ICU' in feat:
                        val_str = str(icu_days)
                    elif '费用' in feat or 'cost' in feat.lower():
                        val_str = str(cost)
                    elif 'CRP' in feat or 'crp' in feat.lower():
                        val_str = str(crp)
                    elif '年龄' in feat or 'age' in feat.lower():
                        val_str = str(age)
                    else:
                        val_str = '0'
                    try:
                        cf_base_input[i] = float(val_str)
                    except:
                        cf_base_input[i] = 0.0

                # Scale the input
                scaler = assets['scaler']
                for cf_val in cf_values:
                    cf_input = cf_base_input.copy()
                    cf_input[cf_real_idx] = cf_val
                    cf_input_2d = cf_input.reshape(1, -1)
                    if scaler is not None:
                        try:
                            cf_input_2d = scaler.transform(cf_input_2d)
                        except:
                            pass
                    if hasattr(model, 'predict_proba'):
                        cf_prob = model.predict_proba(cf_input_2d)[0, 1]
                    else:
                        cf_prob = float(model.predict(cf_input_2d)[0])
                    cf_probs.append(cf_prob)

                # Plot counterfactual curve
                fig_cf, ax_cf = plt.subplots(figsize=(8, 4))
                ax_cf.plot(cf_values, cf_probs, 'b-', linewidth=2.5, marker='o', markersize=4)
                ax_cf.axhline(y=prob, color='gray', linestyle='--', alpha=0.5, label=f'当前风险: {prob:.1%}')
                ax_cf.fill_between(
                    cf_values, 0, risk_low, alpha=0.1, color='green', label=f'低风险区 (<{risk_low:.0%})'
                )
                ax_cf.fill_between(
                    cf_values, risk_low, risk_high, alpha=0.1, color='orange', label=f'中风险区 ({risk_low:.0%}-{risk_high:.0%})'
                )
                ax_cf.fill_between(
                    cf_values, risk_high, 1.0, alpha=0.1, color='red', label=f'高风险区 (>{risk_high:.0%})'
                )
                ax_cf.set_xlabel(f'{cf_selected} 值', fontsize=11)
                ax_cf.set_ylabel('AKI 预测风险', fontsize=11)
                ax_cf.set_title(f'反事实曲线: {cf_selected} 对 AKI 风险的影响', fontweight='bold')
                ax_cf.legend(fontsize=8, loc='upper right')
                ax_cf.set_ylim(0, 1)
                ax_cf.grid(True, alpha=0.3)
                plt.tight_layout()
                st.pyplot(fig_cf)

                # Clinical narrative
                cf_current_prob = prob
                cf_best_idx = np.argmin(cf_probs) if cf_shap_val > 0 else np.argmax(cf_probs)
                cf_best_val = cf_values[cf_best_idx]
                cf_best_prob = cf_probs[cf_best_idx]
                cf_delta = abs(cf_best_prob - cf_current_prob)

                if cf_shap_val > 0:
                    # This feature increases risk -> lower is better
                    st.info(f"""
                    💡 **临床洞察**: 如果 **{cf_selected}** 从当前值降低到 **{cf_best_val:.1f}**，
                    预测的AKI风险将从 **{cf_current_prob:.1%}** 降至 **{cf_best_prob:.1%}**
                    （降低 {cf_delta:.1%}）。这提示 **{cf_selected}** 可能是可干预的风险因素。
                    """)
                else:
                    st.info(f"""
                    💡 **临床洞察**: 如果 **{cf_selected}** 从当前值提升到 **{cf_best_val:.1f}**，
                    预测的AKI风险将从 **{cf_current_prob:.1%}** 改善至 **{cf_best_prob:.1%}**
                    （改善 {cf_delta:.1%}）。这提示维持较高水平的 **{cf_selected}** 可能具有保护作用。
                    """)

            except Exception as e:
                st.info(f"反事实分析暂不可用（模型推断出错: {str(e)[:100]}）")
        else:
            st.info("📌 反事实分析需要模型和SHAP值支持。请先运行预测获取SHAP解释。")

        # PDF Export (Phase 2: enhanced with gauge chart + counterfactual)
        st.markdown("---")
        c1,c2,c3 = st.columns([1,1,1])
        with c2:
            patient_info = {
                'name': f'Patient_{datetime.now().strftime("%Y%m%d_%H%M%S")}',
                'age': str(age), 'gender': gender,
                'surgery': surgery, 'APACHE II': str(apache),
                'preop_eGFR': str(egfr), 'preop_Scr': str(scr),
                'preop_Alb': str(alb), 'preop_Hb': str(hb),
            }
            # Phase 2: Generate risk report for enhanced PDF
            try:
                from src.models.calibration import generate_risk_report as gen_report
                risk_report_data = gen_report(
                    prob, shap_values=result.get('shap_values'),
                    feature_names=assets['features'],
                )
                # Build counterfactual summary for PDF
                cf_for_pdf = None
                if result.get('shap_values') is not None and assets['features']:
                    cf_for_pdf = {
                        'feature': cf_selected if 'cf_selected' in dir() else 'N/A',
                        'current_risk': prob,
                        'target_risk': cf_best_prob if 'cf_best_prob' in dir() else prob,
                        'risk_change': cf_delta if 'cf_delta' in dir() else 0,
                    }
            except:
                risk_report_data = None
                cf_for_pdf = None

            # Use enhanced Phase 2 PDF generator if available
            try:
                from web.components.report import generate_pdf_report as gen_pdf_v2
                pdf_bytes = gen_pdf_v2(
                    patient_info,
                    {'probability': prob, 'risk_level': risk_level},
                    [],  # risk_factors handled internally
                    {},  # recommendations handled internally
                    counterfactual=cf_for_pdf,
                    risk_report=risk_report_data,
                )
            except:
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
# PAGE 5: Data Governance
# ============================================
def page_data_governance(assets):
    st.markdown("## 📋 数据治理")

    st.info("📊 数据治理可视化 — 展示从原始数据到建模数据集的完整处理管线。答辩核心材料。")

    tab1, tab2, tab3 = st.tabs(["🔄 治理流程", "📉 缺失值分析", "📊 质量仪表盘"])

    with tab1:
        st.markdown("### 🔄 数据治理流程")
        st.caption("七阶段数据治理管线：原始采集 → 缺失分析 → 异常检测 → 标准化 → 特征筛选 → SMOTE平衡 → 建模数据集")

        # Data governance flowchart
        dg_flow_path = PHASE1_FIG_DIR / 'data_governance_flow.png'
        if not dg_flow_path.exists():
            dg_flow_path = PHASE1_FIG_DIR / 'data_governance_flowchart.png'
        if not dg_flow_path.exists():
            dg_flow_path = FIG_DIR / 'data_governance_flowchart.png'
        if dg_flow_path.exists():
            st.image(str(dg_flow_path), width='stretch')
        else:
            st.info("📌 数据治理流程图未生成。请运行: python run_models.py --skip-cv --skip-ablation --skip-dca --skip-shap")

        st.markdown("---")
        st.markdown("### 🔽 特征筛选漏斗")
        dg_funnel_path = PHASE1_FIG_DIR / 'feature_selection_funnel.png'
        if not dg_funnel_path.exists():
            dg_funnel_path = FIG_DIR / 'feature_selection_funnel.png'
        if dg_funnel_path.exists():
            st.image(str(dg_funnel_path), width='stretch')
        else:
            st.info("📌 特征筛选漏斗图未生成。")

    with tab2:
        st.markdown("### 📉 数据质量验证")

        # AKI logic validation (existing, from load_all)
        if assets.get('validation_report'):
            st.markdown("---")
            st.markdown("### 🔍 AKI 诊断逻辑校验")
            n_staging = assets.get('n_staging_issues', 0)
            n_group = assets.get('n_group_stage_issues', 0)

            c1, c2 = st.columns(2)
            with c1:
                if n_staging == 0:
                    st.success("✅ KDIGO Scr 标准校验通过")
                else:
                    st.warning(f"⚠️ {n_staging} 条 AKI 分期与 KDIGO 标准不一致")
            with c2:
                if n_group == 0:
                    st.success("✅ AKI分组 vs AKI分期一致性通过")
                else:
                    st.error(f"❌ {n_group} 条 AKI分组与分期对应错误")

            with st.expander("📄 完整校验报告"):
                st.code(assets['validation_report'], language=None)

    with tab3:
        st.markdown("### 📊 数据质量仪表盘")

        dg_dash_path = PHASE1_FIG_DIR / 'data_quality_dashboard.png'
        if not dg_dash_path.exists():
            dg_dash_path = FIG_DIR / 'data_quality_dashboard.png'
        if dg_dash_path.exists():
            st.image(str(dg_dash_path), width='stretch')
        else:
            st.info("📌 数据质量仪表盘未生成。")

        # Quick stats from evaluation
        if assets['eval_df'] is not None:
            st.markdown("---")
            st.markdown("### 📈 数据集概览")
            c1, c2, c3, c4, c5 = st.columns(5)
            with c1:
                st.metric("📊 样本量", "420", "真实临床数据")
            with c2:
                st.metric("🧬 特征数", f"{len(assets.get('features', [])) or 48}", "筛选后")
            with c3:
                st.metric("🤖 模型数", f"{len(assets.get('models', {})) or 8}", "集成系统")
            with c4:
                akis = 100
                if assets['eval_df'] is not None and 'AKI发生率' in assets['eval_df'].columns:
                    akis = assets['eval_df']['AKI发生率'].iloc[0]
                elif assets.get('validation_report'):
                    import re as _re
                    m = _re.search(r'AKI.*?(\d+\.?\d*)%', assets['validation_report'])
                    if m: akis = float(m.group(1))
                st.metric("🏥 AKI发生率", f"{akis:.1f}%")
            with c5:
                st.metric("✅ 逻辑校验", "通过" if (assets.get('n_staging_issues', 0) == 0) else "有异常")


# ============================================
# PAGE 6: Doctor Workstation (Phase 3)
# ============================================
def page_doctor_workstation(assets):
    st.markdown("## 🏥 医生工作台")

    st.info("📋 患者列表 + 批量风险评估 — 模拟临床工作流，支持快速筛查高危患者。")

    if assets['model'] is None:
        st.warning("⚠️ 模型未加载。请确保模型文件存在。")
        return

    tab1, tab2 = st.tabs(["📋 患者列表", "🔢 批量评估"])

    with tab1:
        # Generate synthetic patient cohort for demonstration
        np.random.seed(42)
        n_patients = 20

        demo_patients = []
        for i in range(n_patients):
            age_val = np.random.randint(25, 85)
            scr_val = np.random.uniform(50, 180)
            egfr_val = max(15, 120 - age_val * 0.8 + np.random.normal(0, 10))
            apache_val = np.random.randint(5, 35)
            surgery_types = ['心脏瓣膜手术', '冠状动脉旁路移植术', '联合手术', '结构性心脏病手术', '大血管疾病手术']
            surgery_val = np.random.choice(surgery_types)
            demo_patients.append({
                'ID': f'P{1001+i:04d}',
                '年龄': age_val,
                '性别': np.random.choice(['男', '女']),
                '手术类型': surgery_val,
                '术前Scr': round(scr_val, 1),
                '术前eGFR': round(egfr_val, 1),
                'APACHE II': apache_val,
                '预测风险': '-',
                '风险等级': '-',
            })

        # Run predictions for demo patients
        model = assets['model']
        scaler = assets['scaler']
        features_list = assets['features']

        if features_list:
            for p in demo_patients:
                try:
                    input_vec = np.zeros(len(features_list))
                    for j, feat in enumerate(features_list):
                        if 'Scr' in feat or '肌酐' in feat:
                            input_vec[j] = p['术前Scr']
                        elif 'eGFR' in feat:
                            input_vec[j] = p['术前eGFR'] if p['术前eGFR'] > 0 else 90
                        elif 'APACHE' in feat or 'apache' in feat:
                            input_vec[j] = p['APACHE II']
                        elif '年龄' in feat or 'age' in feat:
                            input_vec[j] = p['年龄']
                        elif '手术' in feat:
                            input_vec[j] = 1 if p['手术类型'] == '联合手术' else 0
                        else:
                            input_vec[j] = 0

                    X_input = input_vec.reshape(1, -1)
                    if scaler is not None:
                        try: X_input = scaler.transform(X_input)
                        except: pass
                    if hasattr(model, 'predict_proba'):
                        prob = model.predict_proba(X_input)[0, 1]
                    else:
                        prob = float(model.predict(X_input)[0])
                    p['预测风险'] = f'{prob:.1%}'
                    p['风险等级'] = '🔴 高' if prob > 0.7 else ('🟡 中' if prob > 0.3 else '🟢 低')
                except:
                    p['预测风险'] = 'N/A'
                    p['风险等级'] = '-'

        demo_df = pd.DataFrame(demo_patients)
        # Color-code risk levels
        def highlight_risk(val):
            if '🔴' in str(val):
                return 'background-color: #ffeaea; font-weight: bold'
            elif '🟡' in str(val):
                return 'background-color: #fff8e1; font-weight: bold'
            elif '🟢' in str(val):
                return 'background-color: #e8f5e9'
            return ''
        styled = demo_df.style.applymap(highlight_risk, subset=['风险等级'])
        st.dataframe(styled, width='stretch', hide_index=True)

        # Risk distribution
        high_count = sum(1 for p in demo_patients if '🔴' in str(p.get('风险等级', '')))
        med_count = sum(1 for p in demo_patients if '🟡' in str(p.get('风险等级', '')))
        low_count = sum(1 for p in demo_patients if '🟢' in str(p.get('风险等级', '')))

        c1, c2, c3 = st.columns(3)
        with c1: st.metric("🔴 高风险", f"{high_count} 人")
        with c2: st.metric("🟡 中风险", f"{med_count} 人")
        with c3: st.metric("🟢 低风险", f"{low_count} 人")

    with tab2:
        st.markdown("### 🔢 批量风险评估")
        st.caption("上传CSV文件进行批量预测（需包含模型所需特征列）")

        uploaded = st.file_uploader("上传患者数据 (CSV)", type=['csv'])
        if uploaded:
            try:
                batch_df = pd.read_csv(uploaded)
                st.success(f"已加载 {len(batch_df)} 条记录，{len(batch_df.columns)} 列")

                # Show first 5 rows
                st.dataframe(batch_df.head(), width='stretch')

                if st.button("🚀 开始批量预测", width='stretch'):
                    with st.spinner("批量预测中..."):
                        results = []
                        for idx, row in batch_df.iterrows():
                            try:
                                input_vec = np.zeros(len(features_list))
                                for j, feat in enumerate(features_list):
                                    if feat in batch_df.columns:
                                        input_vec[j] = float(row[feat])
                                X_input = input_vec.reshape(1, -1)
                                if scaler is not None:
                                    try: X_input = scaler.transform(X_input)
                                    except: pass
                                prob = model.predict_proba(X_input)[0, 1] if hasattr(model, 'predict_proba') else float(model.predict(X_input)[0])
                                results.append({'row': idx, 'probability': prob, 'risk': 'High' if prob > 0.7 else ('Medium' if prob > 0.3 else 'Low')})
                            except Exception as e:
                                results.append({'row': idx, 'probability': None, 'risk': 'Error', 'error': str(e)[:50]})

                        result_df = pd.DataFrame(results)
                        st.success(f"预测完成！{len(result_df)} 条记录")
                        st.dataframe(result_df, width='stretch')

                        # Download
                        csv_data = result_df.to_csv(index=False).encode('utf-8')
                        st.download_button("📥 下载预测结果", csv_data,
                                           "batch_prediction_results.csv", "text/csv")
            except Exception as e:
                st.error(f"文件读取失败: {e}")


# ============================================
# PAGE 7: Management Dashboard (Phase 3)
# ============================================
def page_dashboard(assets):
    st.markdown("## 📊 管理仪表盘")

    st.info("📈 AKI发生率趋势 + 科室分布 + 高危患者统计 — 医院管理视角。")

    tab1, tab2, tab3 = st.tabs(["📈 趋势概览", "🏥 科室分布", "🔍 高危监控"])

    with tab1:
        # Generate demo dashboard data
        np.random.seed(123)
        months = ['2025-09', '2025-10', '2025-11', '2025-12',
                  '2026-01', '2026-02', '2026-03', '2026-04', '2026-05', '2026-06']
        aki_rates = [32.5, 31.2, 33.8, 30.1, 29.5, 28.7, 27.3, 28.1, 26.8, 25.9]
        total_cases = [38, 42, 35, 40, 45, 41, 48, 39, 43, 46]

        c1, c2, c3, c4 = st.columns(4)
        with c1: st.metric("📊 总病例", "420", "真实临床数据")
        with c2: st.metric("🏥 AKI发生率", "29.8%", "125/420")
        with c3: st.metric("🤖 模型AUC", "0.821", "+/- 0.043")
        with c4: st.metric("✅ 在线服务", "Active", "Streamlit Cloud")

        # Trend chart
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(months, aki_rates, 'o-', color='#e74c3c', linewidth=2.5, markersize=8,
                label='AKI Incidence (%)')
        ax.fill_between(range(len(months)),
                        [r - 3 for r in aki_rates],
                        [r + 3 for r in aki_rates],
                        alpha=0.15, color='#e74c3c')
        ax2 = ax.twinx()
        ax2.bar(range(len(months)), total_cases, alpha=0.3, color='#3498db', label='Total Cases')
        ax.set_xticks(range(len(months)))
        ax.set_xticklabels(months, rotation=45, fontsize=9)
        ax.set_ylabel('AKI Incidence (%)', fontsize=11)
        ax2.set_ylabel('Monthly Cases', fontsize=11)
        ax.set_title('AKI Incidence Trend (Demo)', fontsize=13, fontweight='bold')
        ax.legend(loc='upper left', fontsize=9)
        ax2.legend(loc='upper right', fontsize=9)
        ax.grid(alpha=0.3)
        plt.tight_layout()
        st.pyplot(fig)

        st.caption("💡 趋势显示AKI发生率逐步下降，可能与预防措施改善有关。实际部署后可使用真实数据更新。")

    with tab2:
        st.markdown("### 🏥 科室/手术类型分布")

        # Demo department data
        dept_data = {
            '心血管外科': {'cases': 180, 'aki_rate': 32.2},
            '心脏大血管外科': {'cases': 95, 'aki_rate': 28.4},
            '结构性心脏病科': {'cases': 72, 'aki_rate': 25.0},
            '胸外科': {'cases': 45, 'aki_rate': 22.2},
            '其他': {'cases': 28, 'aki_rate': 35.7},
        }

        col1, col2 = st.columns(2)
        with col1:
            dept_names = list(dept_data.keys())
            dept_cases = [dept_data[d]['cases'] for d in dept_names]
            dept_aki = [dept_data[d]['aki_rate'] for d in dept_names]

            fig, ax = plt.subplots(figsize=(6, 5))
            colors = ['#3498db', '#2ecc71', '#f39c12', '#9b59b6', '#e74c3c']
            ax.pie(dept_cases, labels=dept_names, autopct='%1.1f%%',
                   colors=colors, startangle=90, textprops={'fontsize': 9})
            ax.set_title('Case Distribution by Department', fontweight='bold')
            plt.tight_layout()
            st.pyplot(fig)

        with col2:
            fig, ax = plt.subplots(figsize=(6, 5))
            bars = ax.bar(dept_names, dept_aki, color=colors, edgecolor='white')
            ax.set_ylabel('AKI Incidence (%)', fontsize=11)
            ax.set_title('AKI Rate by Department', fontweight='bold')
            ax.set_xticklabels(dept_names, rotation=30, ha='right', fontsize=9)
            for bar, rate in zip(bars, dept_aki):
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                        f'{rate:.1f}%', ha='center', fontsize=9, fontweight='bold')
            ax.grid(axis='y', alpha=0.3)
            plt.tight_layout()
            st.pyplot(fig)

    with tab3:
        st.markdown("### 🔍 高危患者监控")

        # Risk factor prevalence
        rf_data = {
            '术前eGFR < 60': 38.5,
            'APACHE II > 20': 42.1,
            '术前Scr > 100': 35.2,
            '年龄 > 65': 44.8,
            '糖尿病': 22.6,
            '高血压': 58.3,
            '手术时间 > 6h': 28.7,
            '术前CRP升高': 31.5,
        }

        fig, ax = plt.subplots(figsize=(10, 4))
        rf_names = list(rf_data.keys())
        rf_values = list(rf_data.values())
        colors_rf = ['#e74c3c' if v > 40 else '#f39c12' if v > 30 else '#3498db' for v in rf_values]
        bars = ax.barh(rf_names, rf_values, color=colors_rf, edgecolor='white', height=0.6)
        ax.set_xlabel('Prevalence (%)', fontsize=11)
        ax.set_title('Risk Factor Prevalence in Patient Cohort', fontweight='bold')
        ax.invert_yaxis()
        for bar, val in zip(bars, rf_values):
            ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height()/2,
                    f'{val:.1f}%', va='center', fontsize=9, fontweight='bold')
        ax.grid(axis='x', alpha=0.3)
        plt.tight_layout()
        st.pyplot(fig)

        st.markdown("---")
        st.markdown("### ⚠️ 高危预警建议")
        c1, c2 = st.columns(2)
        with c1:
            st.warning("""
            **即时干预建议:**
            1. eGFR < 60 患者启动KDIGO Bundle
            2. APACHE II > 20 建议ICU监护
            3. 手术时间 > 6h 延长术后监测
            """)
        with c2:
            st.success("""
            **系统优化建议:**
            1. 高危科室部署自动预警
            2. 术后48h内每日Scr监测
            3. 多学科团队(MDT)定期会诊
            """)


# ============================================
# Router
# ============================================
assets = load_all()
pages = {
    "🏠 首页": page_home,
    "📊 模型性能": page_performance,
    "🔮 风险预测": page_prediction,
    "🏥 医生工作台": page_doctor_workstation,
    "📊 管理仪表盘": page_dashboard,
    "📋 报告": page_report,
    "🔍 数据治理": page_data_governance,
}
pages[page](assets)

# Footer
st.markdown("---")
st.markdown('<div class="footer">AKI 智能预测系统 v2.0 | 广西科技大学 · 白菜卷队 · 暑期数创 2026<br>'
            'Powered by ML · SHAP · Streamlit | 仅供学术研究参考</div>', unsafe_allow_html=True)

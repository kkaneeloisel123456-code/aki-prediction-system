#!/usr/bin/env python
"""Generate evaluation visualizations and SHAP analysis."""
import sys,os,warnings
warnings.filterwarnings('ignore')
sys.path.insert(0,os.path.dirname(__file__))
os.environ['LOKY_MAX_CPU_COUNT']='4'

import pandas as pd,numpy as np,joblib,logging
logging.getLogger('matplotlib').setLevel(logging.ERROR)
import matplotlib;matplotlib.use('Agg')

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score
from src.data.features import select_features_combined,encode_categorical_features
from src.models.evaluate import plot_roc_curves,plot_pr_curves,plot_confusion_matrices
from src.models.calibration import plot_calibration_curves_all,plot_decision_curve,plot_clinical_impact_curve,create_calibration_summary,analyze_risk_groups

fig_dir='outputs/figures';tab_dir='outputs/tables'
os.makedirs(fig_dir,exist_ok=True);os.makedirs(tab_dir,exist_ok=True)

# Load data
df=pd.read_csv('data/processed/aki_cleaned_20260708_162526.csv')
target='AKI分组'
if 'AKI分期' in df.columns:df=df.drop(columns=['AKI分期'])
y=df[target].copy()
X_all=df.drop(columns=[target])
X_all,enc=encode_categorical_features(X_all,['手术类型'] if '手术类型' in X_all.columns else [],'label')
X_all=X_all.select_dtypes(include=[np.number])
features,sel=select_features_combined(X_all,y,clinical_features=['年龄','术前Scr','术前eGFR','APACHEII','手术时间','术中尿量','术中失血量','高血压','糖尿病'],random_state=42)
X_sel=X_all[features].fillna(X_all[features].median())
scaler=StandardScaler()
X_scaled=pd.DataFrame(scaler.fit_transform(X_sel),columns=features)
_,X_test,_,y_test=train_test_split(X_scaled,y,test_size=0.2,random_state=42,stratify=y)

# Load models
models={}
for f in os.listdir('models/'):
    if f.endswith('.pkl') and f!='scaler.pkl':
        name=f.replace('.pkl','')
        models[name]=joblib.load(f'models/{name}.pkl')
print(f'Loaded {len(models)} models: {list(models.keys())}')

# Prepare data
model_results={}
for name,model in models.items():
    try:
        if hasattr(model,'predict_proba'):y_prob=model.predict_proba(X_test)[:,1]
        else:continue
        y_pred=(y_prob>=0.5).astype(int)
        model_results[name]={'y_true':y_test.values,'y_prob':y_prob,'y_pred':y_pred}
        print(f'{name}: AUC={roc_auc_score(y_test,y_prob):.4f}')
    except Exception as e:
        print(f'{name}: ERR {e}')

# Generate plots
print('\nGenerating plots...')
print('  ROC...')
try:plot_roc_curves(model_results,save_path=f'{fig_dir}/roc_curves.png');print('    OK')
except Exception as e:print(f'    FAIL: {e}')

print('  PR...')
try:plot_pr_curves(model_results,save_path=f'{fig_dir}/pr_curves.png');print('    OK')
except Exception as e:print(f'    FAIL: {e}')

print('  CM...')
try:plot_confusion_matrices(model_results,save_path=f'{fig_dir}/confusion_matrices.png');print('    OK')
except Exception as e:print(f'    FAIL: {e}')

# Note: calibration functions internally prepend FIGURES_DIR/TABLES_DIR, pass filename only
print('  Calibration...')
try:plot_calibration_curves_all(model_results,save_name='calibration_curves.png');print('    OK')
except Exception as e:print(f'    FAIL: {e}')

print('  DCA...')
try:
    probs_dict={n:r['y_prob'] for n,r in model_results.items()}
    plot_decision_curve(y_test.values,probs_dict,save_name='decision_curve.png');print('    OK')
except Exception as e:print(f'    FAIL: {e}')

best_name=sorted(model_results.keys(),key=lambda n:roc_auc_score(model_results[n]['y_true'],model_results[n]['y_prob']),reverse=True)[0]
print(f'Best model: {best_name}')

print('  Clinical Impact...')
try:plot_clinical_impact_curve(y_test.values,model_results[best_name]['y_prob'],save_name='clinical_impact_curve.png');print('    OK')
except Exception as e:print(f'    FAIL: {e}')

create_calibration_summary(model_results,save_name='calibration_summary.csv')
analyze_risk_groups(y_test.values,model_results[best_name]['y_prob'],save_name='risk_stratification.csv')

# SHAP
print('\n=== SHAP ===')
try:
    import shap
    from src.visualization.shap_viz import plot_shap_summary,plot_shap_bar,plot_shap_dependence,create_shap_importance_table,generate_clinical_interpretation,save_clinical_interpretation

    best_model=models[best_name]
    X_explain=X_test.iloc[:min(50,len(X_test))]

    if best_name in ['XGBoost','LightGBM','CatBoost','RandomForest','ExtraTrees']:
        explainer=shap.TreeExplainer(best_model)
        shap_values=explainer.shap_values(X_explain)
        if isinstance(shap_values,list):shap_values=shap_values[1]
    else:
        explainer=shap.KernelExplainer(best_model.predict_proba,shap.kmeans(X_explain,min(20,len(X_explain))))
        shap_values=explainer.shap_values(X_explain)
        if isinstance(shap_values,list):shap_values=shap_values[1]

    plot_shap_summary(shap_values,X_explain,max_display=15,save_name='shap_summary.png')
    plot_shap_bar(shap_values,X_explain,max_display=15,save_name='shap_bar.png')
    plot_shap_dependence(shap_values,X_explain,list(X_explain.columns)[:5],top_n=5,save_name='shap_dependence.png')
    create_shap_importance_table(shap_values,X_explain,save_name='shap_importance.csv')
    clinical_notes=generate_clinical_interpretation(shap_values,X_explain,list(X_explain.columns),top_n=10)
    save_clinical_interpretation(clinical_notes,save_name='clinical_interpretation.md')
    print('SHAP complete!')
except Exception as e:
    print(f'SHAP FAIL: {e}')
    import traceback;traceback.print_exc()

print('\n=== DONE ===')
print(f'Figures: {fig_dir}/')
print(f'Tables: {tab_dir}/')

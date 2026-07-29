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
from src.models.calibration import plot_calibration_curves_all,create_calibration_summary,analyze_risk_groups

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
	# ROC & PR — 已迁移至 run_clean.py
print('  ROC & PR: SKIP (已由 run_clean.py 统一生成5模型+Voting版本)')

print('  CM...')
# Confusion matrices — 已迁移至 run_clean.py
print('  Confusion Matrices: SKIP (已由 run_clean.py 统一生成)')

# Note: calibration functions internally prepend FIGURES_DIR/TABLES_DIR, pass filename only
print('  Calibration...')
# Calibration — 已迁移至 run_clean.py
print('  Calibration: SKIP (已由 run_clean.py 统一生成)')

# DCA — 已迁移至 run_clean.py
print('  DCA: SKIP (已由 run_clean.py 统一生成)')

best_name=sorted(model_results.keys(),key=lambda n:roc_auc_score(model_results[n]['y_true'],model_results[n]['y_prob']),reverse=True)[0]
print(f'Best model: {best_name}')

print('  Clinical Impact...')
try:plot_clinical_impact_curve(y_test.values,model_results[best_name]['y_prob'],save_name='clinical_impact_curve.png');print('    OK')
except Exception as e:print(f'    FAIL: {e}')

create_calibration_summary(model_results,save_name='calibration_summary.csv')
analyze_risk_groups(y_test.values,model_results[best_name]['y_prob'],save_name='risk_stratification.csv')

# SHAP — 已迁移至 run_clean.py (基于 XGBoost TreeExplainer, 全量420例)
print('\n=== SHAP: SKIP (已由 run_clean.py 统一生成) ===')

print('\n=== DONE ===')
print(f'Figures: {fig_dir}/')
print(f'Tables: {tab_dir}/')

#!/usr/bin/env python
"""Model training script — run this directly."""
import sys,os,warnings
warnings.filterwarnings('ignore')
os.environ['LOKY_MAX_CPU_COUNT']='4'
sys.path.insert(0,os.path.dirname(__file__))

import pandas as pd,numpy as np,joblib
from sklearn.model_selection import train_test_split,RandomizedSearchCV
from sklearn.preprocessing import StandardScaler
from src.data.features import select_features_combined,encode_categorical_features,handle_imbalance
from sklearn.metrics import accuracy_score,precision_score,recall_score,f1_score,roc_auc_score,brier_score_loss,confusion_matrix
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier,ExtraTreesClassifier
from sklearn.neural_network import MLPClassifier

print("Loading data...")
df=pd.read_csv('data/processed/aki_cleaned_20260708_162526.csv')
target='AKI分组'
if 'AKI分期' in df.columns:df=df.drop(columns=['AKI分期'])
y=df[target].copy()
X_all=df.drop(columns=[target])

print("Encoding...")
X_all,enc=encode_categorical_features(X_all,['手术类型'] if '手术类型' in X_all.columns else [],'label')
X_all=X_all.select_dtypes(include=[np.number])

print("Feature selection...")
clinical=['年龄','术前Scr','术前eGFR','APACHEII','手术时间','术中尿量','术中失血量','高血压','糖尿病']
features,sel=select_features_combined(X_all,y,clinical_features=clinical,random_state=42)
print(f'  {len(features)} features selected')

X_sel=X_all[features].fillna(X_all[features].median())
scaler=StandardScaler()
X_scaled=pd.DataFrame(scaler.fit_transform(X_sel),columns=features)

X_train,X_test,y_train,y_test=train_test_split(X_scaled,y,test_size=0.2,random_state=42,stratify=y)
X_tr,y_tr=handle_imbalance(X_train,y_train,method='smote',random_state=42)
print(f'Train: {X_tr.shape}, Test: {X_test.shape}')

models={}
for name in ['LogisticRegression','RandomForest','XGBoost','LightGBM','CatBoost','ExtraTrees','MLP']:
    print(f'--- {name} ---')
    try:
        if name=='LogisticRegression':
            m=LogisticRegression(penalty='l2',class_weight='balanced',max_iter=5000,random_state=42)
            s=RandomizedSearchCV(m,{'C':[0.01,0.1,1,10,100]},cv=5,scoring='roc_auc',n_iter=15,random_state=42,n_jobs=-1)
        elif name=='RandomForest':
            m=RandomForestClassifier(class_weight='balanced',random_state=42,n_jobs=-1)
            s=RandomizedSearchCV(m,{'n_estimators':[100,200,300],'max_depth':[5,7,10,None],'min_samples_split':[2,5]},cv=5,scoring='roc_auc',n_iter=15,random_state=42,n_jobs=-1)
        elif name=='XGBoost':
            from xgboost import XGBClassifier
            pos,neg=y_tr.sum(),len(y_tr)-y_tr.sum()
            m=XGBClassifier(scale_pos_weight=neg/max(pos,1),random_state=42,verbosity=0)
            s=RandomizedSearchCV(m,{'n_estimators':[100,200,300],'max_depth':[3,5,7],'learning_rate':[0.01,0.05,0.1]},cv=5,scoring='roc_auc',n_iter=15,random_state=42,n_jobs=-1)
        elif name=='LightGBM':
            from lightgbm import LGBMClassifier
            m=LGBMClassifier(class_weight='balanced',random_state=42,verbose=-1)
            s=RandomizedSearchCV(m,{'n_estimators':[100,200,300],'max_depth':[3,5,7,-1],'learning_rate':[0.01,0.05,0.1],'num_leaves':[15,31]},cv=5,scoring='roc_auc',n_iter=15,random_state=42,n_jobs=-1)
        elif name=='CatBoost':
            from catboost import CatBoostClassifier
            m=CatBoostClassifier(auto_class_weights='Balanced',random_seed=42,verbose=0)
            s=RandomizedSearchCV(m,{'iterations':[100,200,300],'depth':[4,6,8],'learning_rate':[0.01,0.05,0.1]},cv=5,scoring='roc_auc',n_iter=15,random_state=42,n_jobs=-1)
        elif name=='ExtraTrees':
            m=ExtraTreesClassifier(class_weight='balanced',random_state=42,n_jobs=-1)
            s=RandomizedSearchCV(m,{'n_estimators':[100,200,300],'max_depth':[5,7,10,None],'min_samples_split':[2,5]},cv=5,scoring='roc_auc',n_iter=15,random_state=42,n_jobs=-1)
        elif name=='MLP':
            m=MLPClassifier(hidden_layer_sizes=(128,64),early_stopping=True,max_iter=2000,random_state=42)
            s=RandomizedSearchCV(m,{'hidden_layer_sizes':[(64,32),(128,64)],'alpha':[0.001,0.01],'learning_rate_init':[0.001,0.01]},cv=3,scoring='roc_auc',n_iter=8,random_state=42,n_jobs=-1)
        s.fit(X_tr,y_tr)
        best=s.best_estimator_
        best.fit(X_tr,y_tr)
        models[name]=best
        joblib.dump(best,f'models/{name}.pkl')
        print(f'  CV={s.best_score_:.4f}')
    except Exception as e:
        print(f'  SKIP: {e}')

print('\n=== EVALUATION ===')
results=[]
for name,model in models.items():
    try:
        if hasattr(model,'predict_proba'):y_prob=model.predict_proba(X_test)[:,1]
        else:y_prob=model.predict(X_test);y_prob=y_prob[:,1] if y_prob.ndim>1 else y_prob
        y_pred=(y_prob>=0.5).astype(int)
        auc=roc_auc_score(y_test,y_prob)
        acc=accuracy_score(y_test,y_pred)
        prec=precision_score(y_test,y_pred,zero_division=0)
        rec=recall_score(y_test,y_pred,zero_division=0)
        f1=f1_score(y_test,y_pred,zero_division=0)
        brier=brier_score_loss(y_test,y_prob)
        tn,fp,fn,tp=confusion_matrix(y_test,y_pred).ravel()
        spec=tn/(tn+fp) if (tn+fp)>0 else 0
        npv_val=tn/(tn+fn) if (tn+fn)>0 else 0
        ppv_val=tp/(tp+fp) if (tp+fp)>0 else 0
        results.append({'Model':name,'AUC':round(auc,4),'Accuracy':round(acc,4),'Precision':round(prec,4),'Recall':round(rec,4),'F1':round(f1,4),'Brier':round(brier,4),'Specificity':round(spec,4),'NPV':round(npv_val,4),'PPV':round(ppv_val,4)})
        print(f'{name:<20} AUC={auc:.4f} F1={f1:.4f} Acc={acc:.4f} Rec={rec:.4f} Brier={brier:.4f}')
    except Exception as e:
        print(f'{name:<20} ERR: {e}')

eval_df=pd.DataFrame(results).sort_values('AUC',ascending=False)
eval_df.to_csv('outputs/tables/model_comparison.csv',index=False,encoding='utf-8-sig')
joblib.dump(scaler,'models/scaler.pkl')
with open('models/feature_names.txt','w',encoding='utf-8') as f:f.write('\n'.join(features))

best_name=eval_df.iloc[0]['Model']
print(f'\n=== BEST: {best_name} AUC={eval_df.iloc[0]["AUC"]} ===')
print('Models saved to models/')
print('Results saved to outputs/tables/model_comparison.csv')

# -*- coding: utf-8 -*-
"""P1 实验 1-4（仓库根目录内执行：python run_p1.py）
1) 临床基线对比：Thakar简化 / STS简化 / 临床LR(仅术前+术中) vs Voting，DeLong 检验（标准算法）
2) Top8/Top12 精简模型（LR/Ridge）同一5折x10嵌套CV口径
3) DCA 阈值网格 + 成本效益（每千例）
4) TabNet 诚实实验（5折x5次=25次，与Voting同折对比）
"""
import os, sys, warnings
warnings.filterwarnings('ignore')
import numpy as np
import pandas as pd
BASE = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE)
sys.path.insert(0, '.')

from sklearn.ensemble import RandomForestClassifier, ExtraTreesClassifier, VotingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.feature_selection import SelectFromModel
from sklearn.model_selection import RepeatedStratifiedKFold, StratifiedKFold, cross_val_predict, cross_val_score
from sklearn.metrics import roc_auc_score
from scipy import stats
from src.config import TARGET, classify_feature_timing
from src.data.prepare import prepare_training_data

OUT = os.path.join(BASE, 'outputs', 'p1')
os.makedirs(OUT, exist_ok=True)

# ---------- 数据 ----------
df = pd.read_excel('data/raw/AKI数据.xlsx')
prep = prepare_training_data(df)
X = prep['X']; y = np.asarray(prep['y'])
print('X:', X.shape, 'AKI:', int(y.sum()), '/', len(y))

_cv_selector = RandomForestClassifier(n_estimators=200, class_weight='balanced', random_state=42, n_jobs=-1)
def build_honest_pipeline(model):
    return Pipeline([
        ('imputer', SimpleImputer(strategy='median')),
        ('scaler', StandardScaler()),
        ('selector', SelectFromModel(_cv_selector, max_features=35, threshold=-np.inf)),
        ('model', model),
    ])

def make_voting():
    lr = LogisticRegression(C=0.02, penalty='l2', class_weight='balanced', max_iter=5000, random_state=42, solver='saga')
    rf = RandomForestClassifier(n_estimators=300, max_depth=5, min_samples_leaf=15, class_weight='balanced', random_state=42, n_jobs=-1)
    from xgboost import XGBClassifier
    xgb = XGBClassifier(n_estimators=200, max_depth=3, learning_rate=0.02, reg_alpha=1.0, reg_lambda=1.0, min_child_weight=5, random_state=42, use_label_encoder=False, eval_metric='logloss', verbosity=0)
    et = ExtraTreesClassifier(n_estimators=200, max_depth=5, min_samples_leaf=15, class_weight='balanced', random_state=42, n_jobs=-1)
    return VotingClassifier([('lr', lr), ('rf', rf), ('xgb', xgb), ('et', et)], voting='soft', weights=[2, 2, 1, 1])

def oof_proba(model, Xd, yv, cv):
    return np.asarray(cross_val_predict(build_honest_pipeline(model), Xd, yv, cv=cv, method='predict_proba', n_jobs=-1))[:, 1]

cv5 = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
rskf = RepeatedStratifiedKFold(n_splits=5, n_repeats=10, random_state=42)

# ---------- 1) 临床评分 ----------
raw = df.reset_index(drop=True)
age = np.asarray(raw['年龄'].astype(float))
sex_male = np.asarray((raw['性别'].astype(str).str.strip() == '男').astype(float))
dm = np.asarray(raw['糖尿病'].astype(float))
htn = np.asarray(raw['高血压'].astype(float))
pre_scr = np.asarray(raw['术前Scr'].astype(float)) / 88.4  # mg/dL
pre_egfr = np.asarray(raw['术前eGFR'].astype(float))
surg = np.asarray(raw['手术类型'].astype(str))
is_valve = np.array(['瓣' in s for s in surg], dtype=float)
is_cabg = np.array([('搭桥' in s) or ('CABG' in s.upper()) for s in surg], dtype=float)
is_combo = is_valve * is_cabg
is_other = 1.0 - np.maximum(is_valve, is_cabg)

def thakar_score():
    s = np.zeros(len(df))
    s += np.where(age >= 80, 5, np.where(age >= 70, 2, 0))
    s += (1 - sex_male)  # 女性+1
    s += np.nan_to_num(dm, nan=0.0) * 3
    s += np.where(pre_scr > 2.0, 3, 0)
    s += np.where(is_combo > 0.5, 4, np.where(is_other > 0.5, 4, np.where(is_valve > 0.5, 2, 0)))
    return s

def sts_score():
    s = np.zeros(len(df))
    s += np.where(age >= 80, 2, np.where(age >= 70, 1, 0))
    s += (1 - sex_male)
    s += np.where(pre_egfr < 30, 3, np.where(pre_egfr < 60, 2, 0))
    s += np.nan_to_num(dm, nan=0.0)
    s += np.nan_to_num(htn, nan=0.0)
    s += np.where(is_combo > 0.5, 2, np.where(is_other > 0.5, 2, 0))
    return s

thakar_oof = thakar_score()
sts_oof = sts_score()

clin_feats = [c for c in X.columns if classify_feature_timing(c) in ('preop', 'intraop') and 'APACHEII' not in c]
print('临床基线特征数(术前+术中, 不含APACHEII):', len(clin_feats))
clin_pipe = Pipeline([('imp', SimpleImputer(strategy='median')), ('sc', StandardScaler()),
                      ('lr', LogisticRegression(C=0.02, penalty='l2', class_weight='balanced', max_iter=5000, random_state=42, solver='saga'))])
clin_lr_oof = np.asarray(cross_val_predict(clin_pipe, X[clin_feats], y, cv=cv5, method='predict_proba', n_jobs=-1))[:, 1]
voting_oof = oof_proba(make_voting(), X, y, cv5)

# ---------- 标准 DeLong 检验 ----------
def delong_auc_var_components(y_true, p):
    """返回 AUC、V10(每个阳性样本的10分量)、V01(每个阴性样本的01分量)。"""
    m = int(y_true.sum()); n = len(y_true) - m
    p = np.asarray(p, dtype=float)
    y = np.asarray(y_true, dtype=int)
    pos_idx = np.where(y == 1)[0]; neg_idx = np.where(y == 0)[0]
    # V10_i = P(阴性得分 < 阳性i) + 0.5*P(等于)  (对每个阳性)
    V10 = np.zeros(m); V01 = np.zeros(n)
    p_pos = p[pos_idx]; p_neg = p[neg_idx]
    for i in range(m):
        V10[i] = (np.sum(p_neg < p_pos[i]) + 0.5 * np.sum(p_neg == p_pos[i])) / n
    for j in range(n):
        V01[j] = (np.sum(p_pos > p_neg[j]) + 0.5 * np.sum(p_pos == p_neg[j])) / m
    auc = V10.mean()
    return auc, V10, V01, m, n

def delong_test(y_true, p1, p2):
    a1, v10_1, v01_1, m, n = delong_auc_var_components(y_true, p1)
    a2, v10_2, v01_2, _, _ = delong_auc_var_components(y_true, p2)
    # 方差
    var1 = (np.var(v10_1, ddof=1) / m) + (np.var(v01_1, ddof=1) / n)
    var2 = (np.var(v10_2, ddof=1) / m) + (np.var(v01_2, ddof=1) / n)
    cov = (np.cov(v10_1, v10_2, ddof=1)[0, 1] / m) + (np.cov(v01_1, v01_2, ddof=1)[0, 1] / n)
    se = np.sqrt(max(var1 + var2 - 2 * cov, 1e-12))
    z = (a1 - a2) / se
    p = 2 * (1 - stats.norm.cdf(abs(z)))
    return a1, a2, z, p, se

def boot_ci(p, seed=42, n=500):
    rng = np.random.RandomState(seed)
    idx = np.arange(len(y))
    aucs = []
    for _ in range(n):
        b = rng.choice(idx, len(idx), replace=True)
        aucs.append(roc_auc_score(y[b], p[b]))
    return np.percentile(aucs, 2.5), np.percentile(aucs, 97.5)

res1 = []
for name, p in [('Thakar简化', thakar_oof), ('STS简化', sts_oof), ('临床LR(术前+术中)', clin_lr_oof), ('Voting全模型', voting_oof)]:
    a = roc_auc_score(y, p); lo, hi = boot_ci(p)
    res1.append({'模型': name, 'OOF AUC': round(a, 4), '95%CI_low': round(lo, 4), '95%CI_high': round(hi, 4)})
    print(f'{name}: AUC={a:.4f} [{lo:.4f},{hi:.4f}]')
pd.DataFrame(res1).to_csv(os.path.join(OUT, 'clinical_baseline_auc.csv'), index=False, encoding='utf-8-sig')

res2 = []
for name, p in [('Thakar简化', thakar_oof), ('STS简化', sts_oof), ('临床LR(术前+术中)', clin_lr_oof)]:
    a1, a2, z, pv, se = delong_test(y, p, voting_oof)
    # delong_test return types are inferred as a wide numpy union; cast to float.
    a1, a2, z, pv, se = float(a1), float(a2), float(z), float(pv), float(se)
    res2.append({'对比': f'{name} vs Voting全模型', 'AUC_1': round(a1, 4), 'AUC_2': round(a2, 4), 'DeLong_Z': round(z, 3), 'SE': round(se, 4), 'P': round(pv, 4)})
    print(f'DeLong {name} vs Voting: Z={z:.3f} P={pv:.4f}')
pd.DataFrame(res2).to_csv(os.path.join(OUT, 'delong_comparison.csv'), index=False, encoding='utf-8-sig')

# ---------- 2) Top8/Top12 精简模型 ----------
rf_imp = RandomForestClassifier(n_estimators=200, class_weight='balanced', random_state=42, n_jobs=-1)
X_imp_all = SimpleImputer(strategy='median').fit_transform(X)
rf_imp.fit(StandardScaler().fit_transform(X_imp_all), y)
top_names = [X.columns[i] for i in np.argsort(rf_imp.feature_importances_)[::-1]]

def make_lr():
    return LogisticRegression(C=0.02, penalty='l2', class_weight='balanced', max_iter=5000, random_state=42, solver='saga')
def make_ridge():
    from sklearn.linear_model import RidgeClassifier
    return RidgeClassifier(alpha=1.0, class_weight='balanced', random_state=42)
def pipe_for(clf):
    return Pipeline([('imp', SimpleImputer(strategy='median')), ('sc', StandardScaler()), ('clf', clf)])

res3 = []
for n_feat in [8, 12, 35]:
    cols = top_names[:n_feat]
    for name, clf in [('LR', make_lr()), ('Ridge', make_ridge())]:
        aucs = cross_val_score(pipe_for(clf), X[cols], y, cv=rskf, scoring='roc_auc', n_jobs=-1)
        res3.append({'特征数': n_feat, '模型': name, '50次CV AUC均值': round(aucs.mean(), 4), '标准差': round(aucs.std(), 4)})
        print(f'Top{n_feat} {name}: {aucs.mean():.4f} ± {aucs.std():.4f}')
pd.DataFrame(res3).to_csv(os.path.join(OUT, 'topN_reduced_models.csv'), index=False, encoding='utf-8-sig')

# ---------- 3) DCA 阈值 + 成本效益 ----------
from sklearn.isotonic import IsotonicRegression
iso = IsotonicRegression(out_of_bounds='clip')
cal_oof = iso.fit(voting_oof, y).predict(voting_oof)
prev = y.mean()
res4 = []
for t in np.arange(0.05, 0.55, 0.05):
    pred = (cal_oof >= t).astype(int)
    tp = ((pred == 1) & (y == 1)).sum(); fp = ((pred == 1) & (y == 0)).sum()
    tn = ((pred == 0) & (y == 0)).sum(); fn = ((pred == 0) & (y == 1)).sum()
    sens = tp / (tp + fn); spec = tn / (tn + fp)
    nb = tp / len(y) - fp / len(y) * (t / (1 - t))
    nb_all = prev - (1 - prev) * t / (1 - t)
    res4.append({'阈值': round(float(t), 2), '灵敏度': round(float(sens), 4), '特异度': round(float(spec), 4),
                 '净获益': round(float(nb), 4), '净获益_全干预': round(float(nb_all), 4),
                 '每千例预测高危数': round(float(pred.sum()) / len(y) * 1000, 1),
                 '每千例正确识别AKI': round(float(tp) / len(y) * 1000, 1)})
res4df = pd.DataFrame(res4)
res4df.to_csv(os.path.join(OUT, 'dca_threshold_cost.csv'), index=False, encoding='utf-8-sig')
print(res4df.to_string(index=False))
best = res4df.loc[res4df['净获益'].idxmax()]
print('DCA最优阈值:', best['阈值'], '净获益', best['净获益'])

# ---------- 4) TabNet 诚实实验（5折x5次） ----------
try:
    import torch  # type: ignore[import-not-found]
    from pytorch_tabnet.tab_model import TabNetClassifier  # type: ignore[import-not-found]
    print('torch', torch.__version__, '| pytorch_tabnet OK')
    imp = SimpleImputer(strategy='median'); sc = StandardScaler()
    Xn = sc.fit_transform(imp.fit_transform(X)).astype(np.float32)
    rskf25 = RepeatedStratifiedKFold(n_splits=5, n_repeats=5, random_state=42)
    tab_aucs = []; vot_aucs25 = []
    for k, (tr, te) in enumerate(rskf25.split(Xn, y), 1):
        clf = TabNetClassifier(n_d=8, n_a=8, n_steps=3, gamma=1.5, lambda_sparse=0,
                               verbose=0, seed=42, device_name='cpu')
        clf.fit(Xn[tr], y[tr], eval_set=[(Xn[te], y[te])], max_epochs=100, patience=15, batch_size=32, drop_last=False)
        tab_aucs.append(roc_auc_score(y[te], clf.predict_proba(Xn[te])[:, 1]))
        pipe = build_honest_pipeline(make_voting())
        pipe.fit(X.iloc[tr], y[tr])
        vot_aucs25.append(roc_auc_score(y[te], pipe.predict_proba(X.iloc[te])[:, 1]))
        print(f'fold {k}/25 TabNet={tab_aucs[-1]:.4f} Voting={vot_aucs25[-1]:.4f}')
    res5 = pd.DataFrame([
        {'模型': 'TabNet (5折x5次=25次)', 'AUC均值': round(float(np.mean(tab_aucs)), 4), '标准差': round(float(np.std(tab_aucs)), 4)},
        {'模型': 'Voting (5折x5次=25次, 同折)', 'AUC均值': round(float(np.mean(vot_aucs25)), 4), '标准差': round(float(np.std(vot_aucs25)), 4)},
    ])
    res5.to_csv(os.path.join(OUT, 'tabnet_comparison.csv'), index=False, encoding='utf-8-sig')
    print(res5.to_string(index=False))
except Exception as e:
    import traceback; traceback.print_exc()
    open(os.path.join(OUT, 'tabnet_status.txt'), 'w', encoding='utf-8').write(f'TabNet 实验失败: {e}')

print('DONE -> outputs/p1/')

-- ============================================================================
-- MIMIC-IV v2.x 外部验证：心脏手术队列 + 35 特征 + KDIGO 肌酐结局 提取脚本
-- ----------------------------------------------------------------------------
-- 前置条件：
--   1) 已通过 PhysioNet 获得 MIMIC-IV 授权并在本地 PostgreSQL 加载数据
--      （hosp / icu 模块；mimic_derived 派生视图可选，缺失时用下方备用逻辑）；
--   2) 本脚本只做“提取”，不加载/训练模型；评分由 scripts/mimic_validation.py 完成。
--
-- 运行方式：
--   psql -d mimic -f scripts/mimic_extract.sql -o outputs/tables/mimic_external_cohort.csv
--   或取消末尾 \copy 行的注释，直接导出 CSV（注意服务器端文件权限）。
--
-- 口径与近似（务必在报告中如实说明）：
--   * 队列：首次 ICU 住院 + 本次住院含心脏手术编码（ICD-9: 35/36 系；ICD-10: 021/022/023 系）；
--   * 基线肌酐：mimic_derived.kdigo_creatinine.baseline_creat（若无该视图，
--     可用 mimic_derived.creatinine_baseline 按 subject_id 取，或改用术前最低肌酐）；
--   * 结局：KDIGO 肌酐标准——48h 内较基线升高 >=0.3 mg/dL 或 7d 内 >=1.5 倍；
--     未纳入尿量标准（MIMIC 尿量覆盖有限），基线缺失时结局置 NULL（不纳入 AUC）；
--   * APACHE II：MIMIC-IV 官方派生库无 apache_ii 视图，用 apsiii 代理并明确标注；
--   * 手术时间/术中失血量：MIMIC 无 OR 内记录，置 NULL（由项目学习中位数填补），
--     另提供 adm_to_icu_hours（入院→入ICU 小时数）作为可选代理；
--   * 术中晶体液量：以入 ICU 后 6h 内晶体输入量代理（inputevents 仅覆盖 Metavision）；
--   * 各检验窗口：术前 = intime-72h~intime；入ICU即刻 = intime~intime+6h；
--     术后早期 = intime~intime+24h；取窗口内首个（时间序）数值。
-- ============================================================================
SET search_path TO hosp, icu, mimic_derived, public;

WITH
-- 0) 队列：成人 + 首次 ICU + 心脏手术
cohort AS (
    SELECT ie.subject_id, ie.hadm_id, ie.icustay_id, ie.intime,
           p.gender,
           EXTRACT(EPOCH FROM (ie.intime - adm.admittime)) / 3600.0 AS adm_to_icu_hours,
           LEAST(a.age, 89.0) AS age
    FROM icustays ie
    JOIN admissions adm USING (hadm_id)
    JOIN patients p USING (subject_id)
    JOIN mimic_derived.age a USING (subject_id, hadm_id)
    WHERE a.age >= 18
      AND ie.icustay_id = (
          SELECT MIN(ie2.icustay_id) FROM icustays ie2 WHERE ie2.hadm_id = ie.hadm_id
      )
),
cardiac AS (
    SELECT DISTINCT pi.hadm_id
    FROM procedures_icd pi
    JOIN d_icd_procedures d USING (icd_code, icd_version)
    WHERE (pi.icd_version = 9  AND (pi.icd_code LIKE '36%' OR pi.icd_code LIKE '35%'))
       OR (pi.icd_version = 10 AND (pi.icd_code LIKE '021%' OR pi.icd_code LIKE '022%'
                                 OR pi.icd_code LIKE '023%' OR pi.icd_code LIKE '02C%'))
),
base AS (
    SELECT c.*, kc.baseline_creat
    FROM cohort c
    JOIN cardiac cd USING (hadm_id)
    -- 基线肌酐（KDIGO 派生视图按 ICU 住院给出；版本不符时改 LEFT JOIN creatinine_baseline cb USING (subject_id)）
    LEFT JOIN kdigo_creatinine kc USING (icustay_id)
),
-- 1) 实验室事件（标准化：只保留数值与时间）
lab AS (
    SELECT l.subject_id, l.hadm_id, l.itemid, d.label, l.charttime, l.valuenum
    FROM labevents l
    LEFT JOIN d_labitems d USING (itemid)
    WHERE l.valuenum IS NOT NULL AND l.charttime IS NOT NULL
),
-- 2) 床旁事件（chartevents：SBP / PaO2 / 尿量等）
cg AS (
    SELECT ie.subject_id, ie.hadm_id, ie.icustay_id, c.charttime, c.itemid, c.valuenum
    FROM chartevents c
    JOIN icustays ie ON ie.icustay_id = c.icustay_id
    WHERE c.valuenum IS NOT NULL AND c.charttime IS NOT NULL
      AND c.itemid IN (220050, 220179, 50821)   -- ART BP 收缩压 / NIBP 收缩压 / PaO2
),
-- 3) 入 ICU 首次肌酐（用于 ICUAdmSCr 与 egfr_icu_first）
icu_cr AS (
    SELECT DISTINCT ON (l.subject_id, l.hadm_id)
           l.subject_id, l.hadm_id, l.valuenum AS cr_icu_first
    FROM lab l
    JOIN base b USING (subject_id, hadm_id)
    WHERE l.label ILIKE '%CREATININE%'
      AND l.charttime BETWEEN b.intime AND b.intime + INTERVAL '6 hours'
    ORDER BY l.subject_id, l.hadm_id, l.charttime
),
-- 4) 结局（KDIGO 肌酐标准，48h/7d 窗口）
outcome AS (
    SELECT b.subject_id, b.hadm_id, b.icustay_id, b.baseline_creat,
           MAX(CASE WHEN l.charttime BETWEEN b.intime AND b.intime + INTERVAL '48 hours'
                    THEN l.valuenum END) AS cr_max_48h,
           MAX(CASE WHEN l.charttime BETWEEN b.intime AND b.intime + INTERVAL '7 days'
                    THEN l.valuenum END) AS cr_max_7d
    FROM base b
    LEFT JOIN lab l ON l.subject_id = b.subject_id
                   AND l.label ILIKE '%CREATININE%'
                   AND l.charttime > b.intime
    GROUP BY 1, 2, 3, 4
)
SELECT
    b.subject_id, b.hadm_id, b.icustay_id, b.intime,
    -- ---------- 结局 ----------
    b.baseline_creat,
    o.cr_max_48h, o.cr_max_7d,
    CASE WHEN b.baseline_creat IS NOT NULL
              AND o.cr_max_48h IS NOT NULL AND (o.cr_max_48h - b.baseline_creat) >= 0.3
         THEN 1 ELSE 0 END AS aki_cr_48h,
    CASE WHEN b.baseline_creat IS NOT NULL
              AND o.cr_max_7d IS NOT NULL AND o.cr_max_7d >= 1.5 * b.baseline_creat
         THEN 1 ELSE 0 END AS aki_cr_7d,
    -- 主结局：基线缺失→NULL（外部验证时该样本不参与 AUC，需如实说明）
    CASE WHEN b.baseline_creat IS NULL THEN NULL
         WHEN (o.cr_max_48h - b.baseline_creat) >= 0.3 OR o.cr_max_7d >= 1.5 * b.baseline_creat
         THEN 1 ELSE 0 END AS outcome_aki,

    -- ---------- 35 个特征（列名 = scripts/mimic_feature_map.csv 的 mimic_concept） ----------
    (SELECT l.valuenum FROM lab l JOIN base b2 USING (subject_id, hadm_id)
     WHERE l.label ILIKE '%CREATININE%'
       AND l.charttime BETWEEN b2.intime AND b2.intime + INTERVAL '6 hours'
     ORDER BY l.charttime LIMIT 1) AS creatinine_icu_first,
    -- egfr_icu_first（CKD-EPI 2021 无种族系数，由入ICU肌酐计算）
    ROUND(142.0 * POWER(LEAST(ic.cr_icu_first / CASE WHEN b.gender = 'F' THEN 0.7 ELSE 0.9 END, 1),
                        CASE WHEN b.gender = 'F' THEN -0.241 ELSE -0.302 END)
              * POWER(GREATEST(ic.cr_icu_first / CASE WHEN b.gender = 'F' THEN 0.7 ELSE 0.9 END, 1), -1.200)
              * POWER(0.9938, b.age)
              * CASE WHEN b.gender = 'F' THEN 1.012 ELSE 1.0 END, 1) AS egfr_icu_first,
    (SELECT l.valuenum FROM lab l JOIN base b2 USING (subject_id, hadm_id)
     WHERE l.label ILIKE '%TROPONIN%'
       AND l.charttime BETWEEN b2.intime - INTERVAL '72 hours' AND b2.intime
     ORDER BY l.charttime DESC LIMIT 1) AS troponin_preop,
    (SELECT l.valuenum FROM lab l JOIN base b2 USING (subject_id, hadm_id)
     WHERE l.label ILIKE '%TROPONIN%'
       AND l.charttime BETWEEN b2.intime AND b2.intime + INTERVAL '24 hours'
     ORDER BY l.charttime LIMIT 1) AS troponin_postop,
    (SELECT l.valuenum FROM lab l JOIN base b2 USING (subject_id, hadm_id)
     WHERE l.label ILIKE '%MICROGLOBULIN%'
       AND l.charttime BETWEEN b2.intime AND b2.intime + INTERVAL '24 hours'
     ORDER BY l.charttime LIMIT 1) AS beta2_microglobulin_postop,
    (SELECT l.valuenum FROM lab l JOIN base b2 USING (subject_id, hadm_id)
     WHERE l.label ILIKE '%MICROGLOBULIN%'
       AND l.charttime BETWEEN b2.intime - INTERVAL '72 hours' AND b2.intime
     ORDER BY l.charttime DESC LIMIT 1) AS beta2_microglobulin_preop,
    (SELECT l.valuenum FROM lab l JOIN base b2 USING (subject_id, hadm_id)
     WHERE l.label ILIKE '%MYOGLOBIN%'
       AND l.charttime BETWEEN b2.intime AND b2.intime + INTERVAL '24 hours'
     ORDER BY l.charttime LIMIT 1) AS myoglobin_postop,
    (SELECT l.valuenum FROM lab l JOIN base b2 USING (subject_id, hadm_id)
     WHERE l.label ILIKE 'LACTATE'
       AND l.charttime BETWEEN b2.intime AND b2.intime + INTERVAL '24 hours'
     ORDER BY l.charttime LIMIT 1) AS lactate_postop,
    (SELECT l.valuenum FROM lab l JOIN base b2 USING (subject_id, hadm_id)
     WHERE l.label ILIKE '%UREA NITROGEN%'
       AND l.charttime BETWEEN b2.intime AND b2.intime + INTERVAL '24 hours'
     ORDER BY l.charttime LIMIT 1) AS bun_postop,
    (SELECT l.valuenum FROM lab l JOIN base b2 USING (subject_id, hadm_id)
     WHERE l.label ILIKE '%URIC ACID%'
       AND l.charttime BETWEEN b2.intime AND b2.intime + INTERVAL '24 hours'
     ORDER BY l.charttime LIMIT 1) AS uric_acid_postop,
    (SELECT l.valuenum FROM lab l JOIN base b2 USING (subject_id, hadm_id)
     WHERE l.label ILIKE '%MONOCYTE%' AND l.label NOT ILIKE '%RATIO%'
       AND l.charttime BETWEEN b2.intime AND b2.intime + INTERVAL '24 hours'
     ORDER BY l.charttime LIMIT 1) AS monocyte_postop,
    (SELECT l.valuenum FROM lab l JOIN base b2 USING (subject_id, hadm_id)
     WHERE l.label ILIKE '%PLATELET%'
       AND l.charttime BETWEEN b2.intime AND b2.intime + INTERVAL '24 hours'
     ORDER BY l.charttime LIMIT 1) AS platelet_postop,
    (SELECT l.valuenum FROM lab l JOIN base b2 USING (subject_id, hadm_id)
     WHERE l.label ILIKE '%PLATELET%'
       AND l.charttime BETWEEN b2.intime - INTERVAL '72 hours' AND b2.intime
     ORDER BY l.charttime DESC LIMIT 1) AS platelet_preop,
    (SELECT l.valuenum FROM lab l JOIN base b2 USING (subject_id, hadm_id)
     WHERE l.label ILIKE 'WBC' OR l.label ILIKE '%WHITE BLOOD%'
       AND l.charttime BETWEEN b2.intime - INTERVAL '72 hours' AND b2.intime
     ORDER BY l.charttime DESC LIMIT 1) AS wbc_preop,
    (SELECT l.valuenum FROM lab l JOIN base b2 USING (subject_id, hadm_id)
     WHERE l.label ILIKE '%RETINOL BINDING%'
       AND l.charttime BETWEEN b2.intime - INTERVAL '72 hours' AND b2.intime
     ORDER BY l.charttime DESC LIMIT 1) AS retinol_binding_protein_preop,
    (SELECT l.valuenum FROM lab l JOIN base b2 USING (subject_id, hadm_id)
     WHERE l.label ILIKE '%C-REACTIVE PROTEIN%'
       AND l.charttime BETWEEN b2.intime AND b2.intime + INTERVAL '24 hours'
     ORDER BY l.charttime LIMIT 1) AS crp_postop,
    (SELECT l.valuenum FROM lab l JOIN base b2 USING (subject_id, hadm_id)
     WHERE l.label ILIKE '%ALBUMIN%'
       AND l.charttime BETWEEN b2.intime AND b2.intime + INTERVAL '24 hours'
     ORDER BY l.charttime LIMIT 1) AS albumin_postop,
    (SELECT l.valuenum FROM lab l JOIN base b2 USING (subject_id, hadm_id)
     WHERE l.label ILIKE '%BASE EXCESS%'
       AND l.charttime BETWEEN b2.intime AND b2.intime + INTERVAL '24 hours'
     ORDER BY l.charttime LIMIT 1) AS base_excess_postop,
    (SELECT l.valuenum FROM lab l JOIN base b2 USING (subject_id, hadm_id)
     WHERE l.label ILIKE '%NEUTROPHIL%' AND l.label NOT ILIKE '%RATIO%'
       AND l.charttime BETWEEN b2.intime - INTERVAL '72 hours' AND b2.intime
     ORDER BY l.charttime DESC LIMIT 1) AS neutrophil_preop,
    (SELECT l.valuenum FROM lab l JOIN base b2 USING (subject_id, hadm_id)
     WHERE l.label ILIKE '%PROBNP%' OR l.label ILIKE '%BNP%'
       AND l.charttime BETWEEN b2.intime - INTERVAL '72 hours' AND b2.intime
     ORDER BY l.charttime DESC LIMIT 1) AS bnp_preop,
    (SELECT l.valuenum FROM lab l JOIN base b2 USING (subject_id, hadm_id)
     WHERE l.label ILIKE '%PROBNP%' OR l.label ILIKE '%BNP%'
       AND l.charttime BETWEEN b2.intime AND b2.intime + INTERVAL '24 hours'
     ORDER BY l.charttime LIMIT 1) AS bnp_postop,
    (SELECT l.valuenum FROM lab l JOIN base b2 USING (subject_id, hadm_id)
     WHERE l.label ILIKE '%CREATINE KINASE MB%'
       AND l.charttime BETWEEN b2.intime - INTERVAL '72 hours' AND b2.intime
     ORDER BY l.charttime DESC LIMIT 1) AS creatine_kinase_mb_preop,
    (SELECT l.valuenum FROM lab l JOIN base b2 USING (subject_id, hadm_id)
     WHERE l.label ILIKE 'CREATINE KINASE' AND l.label NOT ILIKE '%MB%'
       AND l.charttime BETWEEN b2.intime - INTERVAL '72 hours' AND b2.intime
     ORDER BY l.charttime DESC LIMIT 1) AS creatine_kinase_preop,
    (SELECT l.valuenum FROM lab l JOIN base b2 USING (subject_id, hadm_id)
     WHERE l.label ILIKE '%CREATININE%'
       AND l.charttime BETWEEN b2.intime - INTERVAL '72 hours' AND b2.intime
     ORDER BY l.charttime DESC LIMIT 1) AS creatinine_preop,
    (SELECT l.valuenum FROM lab l JOIN base b2 USING (subject_id, hadm_id)
     WHERE l.label ILIKE '%LYMPHOCYTE%' AND l.label NOT ILIKE '%RATIO%'
       AND l.charttime BETWEEN b2.intime - INTERVAL '72 hours' AND b2.intime
     ORDER BY l.charttime DESC LIMIT 1) AS lymphocyte_preop,
    (SELECT l.valuenum FROM lab l JOIN base b2 USING (subject_id, hadm_id)
     WHERE l.label ILIKE '%LYMPHOCYTE%' AND l.label NOT ILIKE '%RATIO%'
       AND l.charttime BETWEEN b2.intime AND b2.intime + INTERVAL '24 hours'
     ORDER BY l.charttime LIMIT 1) AS lymphocyte_postop,
    (SELECT c.valuenum FROM cg c JOIN base b2 USING (subject_id, hadm_id)
     WHERE c.itemid = 50821
       AND c.charttime BETWEEN b2.intime - INTERVAL '72 hours' AND b2.intime
     ORDER BY c.charttime DESC LIMIT 1) AS pao2_preop,
    (SELECT c.valuenum FROM cg c JOIN base b2 USING (subject_id, hadm_id)
     WHERE c.itemid = 50821
       AND c.charttime BETWEEN b2.intime AND b2.intime + INTERVAL '24 hours'
     ORDER BY c.charttime LIMIT 1) AS pao2_postop,
    (SELECT c.valuenum FROM cg c JOIN base b2 USING (subject_id, hadm_id)
     WHERE c.itemid IN (220050, 220179)
       AND c.charttime BETWEEN b2.intime - INTERVAL '72 hours' AND b2.intime
     ORDER BY c.charttime DESC LIMIT 1) AS sbp_preop,
    -- APACHE II：MIMIC-IV 无官方 apache_ii 视图，用 apsiii 代理（报告须注明）
    (SELECT aps.apsiii FROM apsiii aps WHERE aps.icustay_id = b.icustay_id) AS apache_ii,
    -- 术中晶体液量（代理：入ICU后6h内晶体输入量；inputevents 仅 Metavision）
    (SELECT SUM(ie.amount) FROM inputevents ie JOIN d_items di ON di.itemid = ie.itemid
     WHERE ie.icustay_id = b.icustay_id
       AND ie.amount > 0
       AND ie.starttime BETWEEN b.intime AND b.intime + INTERVAL '6 hours'
       AND (di.label ILIKE '%RINGER%' OR di.label ILIKE '%SALINE%'
         OR di.label ILIKE '%NACL%' OR di.label ILIKE '%SODIUM CHLORIDE%'
         OR di.label ILIKE '%PLASMA-LYTE%')) AS crystalloid_volume,
    -- 手术时间 / 术中失血量：MIMIC 无 OR 记录 → NULL（学习中位数填补），代理列 adm_to_icu_hours 另附
    NULL::double precision AS case_duration,
    NULL::double precision AS estimated_blood_loss,
    -- 派生比值（PLR / CAR / LMR / CKMB/CK 比值 / 术前eGFR）
    ROUND((SELECT l.valuenum FROM lab l JOIN base b2 USING (subject_id, hadm_id)
           WHERE l.label ILIKE '%PLATELET%'
             AND l.charttime BETWEEN b2.intime - INTERVAL '72 hours' AND b2.intime
           ORDER BY l.charttime DESC LIMIT 1)
        / NULLIF((SELECT l.valuenum FROM lab l JOIN base b2 USING (subject_id, hadm_id)
           WHERE l.label ILIKE '%LYMPHOCYTE%' AND l.label NOT ILIKE '%RATIO%'
             AND l.charttime BETWEEN b2.intime - INTERVAL '72 hours' AND b2.intime
           ORDER BY l.charttime DESC LIMIT 1), 0), 2) AS plr_preop,
    ROUND((SELECT l.valuenum FROM lab l JOIN base b2 USING (subject_id, hadm_id)
           WHERE l.label ILIKE '%PLATELET%'
             AND l.charttime BETWEEN b2.intime AND b2.intime + INTERVAL '24 hours'
           ORDER BY l.charttime LIMIT 1)
        / NULLIF((SELECT l.valuenum FROM lab l JOIN base b2 USING (subject_id, hadm_id)
           WHERE l.label ILIKE '%LYMPHOCYTE%' AND l.label NOT ILIKE '%RATIO%'
             AND l.charttime BETWEEN b2.intime AND b2.intime + INTERVAL '24 hours'
           ORDER BY l.charttime LIMIT 1), 0), 2) AS plr_postop,
    ROUND((SELECT l.valuenum FROM lab l JOIN base b2 USING (subject_id, hadm_id)
           WHERE l.label ILIKE '%C-REACTIVE PROTEIN%'
             AND l.charttime BETWEEN b2.intime AND b2.intime + INTERVAL '24 hours'
           ORDER BY l.charttime LIMIT 1)
        / NULLIF((SELECT l.valuenum FROM lab l JOIN base b2 USING (subject_id, hadm_id)
           WHERE l.label ILIKE '%ALBUMIN%'
             AND l.charttime BETWEEN b2.intime AND b2.intime + INTERVAL '24 hours'
           ORDER BY l.charttime LIMIT 1), 0), 2) AS crp_albumin_ratio_postop,
    ROUND((SELECT l.valuenum FROM lab l JOIN base b2 USING (subject_id, hadm_id)
           WHERE l.label ILIKE '%LYMPHOCYTE%' AND l.label NOT ILIKE '%RATIO%'
             AND l.charttime BETWEEN b2.intime - INTERVAL '72 hours' AND b2.intime
           ORDER BY l.charttime DESC LIMIT 1)
        / NULLIF((SELECT l.valuenum FROM lab l JOIN base b2 USING (subject_id, hadm_id)
           WHERE l.label ILIKE '%MONOCYTE%' AND l.label NOT ILIKE '%RATIO%'
             AND l.charttime BETWEEN b2.intime - INTERVAL '72 hours' AND b2.intime
           ORDER BY l.charttime DESC LIMIT 1), 0), 2) AS lmr_preop,
    ROUND((SELECT l.valuenum FROM lab l JOIN base b2 USING (subject_id, hadm_id)
           WHERE l.label ILIKE '%CREATINE KINASE MB%'
             AND l.charttime BETWEEN b2.intime - INTERVAL '72 hours' AND b2.intime
           ORDER BY l.charttime DESC LIMIT 1)
        / NULLIF((SELECT l.valuenum FROM lab l JOIN base b2 USING (subject_id, hadm_id)
           WHERE l.label ILIKE 'CREATINE KINASE' AND l.label NOT ILIKE '%MB%'
             AND l.charttime BETWEEN b2.intime - INTERVAL '72 hours' AND b2.intime
           ORDER BY l.charttime DESC LIMIT 1), 0), 2) AS ckmb_ck_ratio_preop,
    ROUND(142.0 * POWER(LEAST((SELECT l.valuenum FROM lab l JOIN base b2 USING (subject_id, hadm_id)
           WHERE l.label ILIKE '%CREATININE%'
             AND l.charttime BETWEEN b2.intime - INTERVAL '72 hours' AND b2.intime
           ORDER BY l.charttime DESC LIMIT 1) / CASE WHEN b.gender = 'F' THEN 0.7 ELSE 0.9 END, 1),
                        CASE WHEN b.gender = 'F' THEN -0.241 ELSE -0.302 END)
              * POWER(GREATEST((SELECT l.valuenum FROM lab l JOIN base b2 USING (subject_id, hadm_id)
           WHERE l.label ILIKE '%CREATININE%'
             AND l.charttime BETWEEN b2.intime - INTERVAL '72 hours' AND b2.intime
           ORDER BY l.charttime DESC LIMIT 1) / CASE WHEN b.gender = 'F' THEN 0.7 ELSE 0.9 END, 1), -1.200)
              * POWER(0.9938, b.age)
              * CASE WHEN b.gender = 'F' THEN 1.012 ELSE 1.0 END, 1) AS egfr_preop,
    b.adm_to_icu_hours
FROM base b
LEFT JOIN icu_cr ic USING (subject_id, hadm_id)
LEFT JOIN outcome o USING (subject_id, hadm_id, icustay_id)
ORDER BY b.subject_id, b.hadm_id;

-- 取消注释可导出 CSV（路径为 PostgreSQL 服务器端路径，需相应权限）：
-- \copy (WITH ... 同上查询 ... ) TO '/tmp/mimic_external_cohort.csv' WITH CSV HEADER

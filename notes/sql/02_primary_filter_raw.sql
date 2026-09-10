-- УСТАРЕЛ: построен на uspto_oce_pair, который выброшен (vintage 2015).
-- Сохранён как источник чисел, процитированных в brief-r4.
-- Замена: 09_parent_vs_pair.sql
-- типы преемственности, покрытие PAIR, earliest_pgpub_date
-- цена 0,407 ГиБ   ВНИМАНИЕ: без тай-брейкера
WITH flagged AS (
  SELECT app_id, mail_dt, art_unit,
         ROW_NUMBER() OVER (PARTITION BY app_id ORDER BY mail_dt) AS rn
  FROM `patents-public-data.uspto_oce_office_actions.office_actions`
  WHERE rejection_101='1' OR rejection_102='1' OR rejection_103='1' OR rejection_112='1'
),
cohort AS (
  SELECT app_id, mail_dt AS first_oa_dt, SUBSTR(mail_dt,1,4) AS oa_year
  FROM flagged
  WHERE rn = 1 AND REGEXP_CONTAINS(art_unit, r'^21\d\d$')
    AND SUBSTR(mail_dt,1,4) IN ('2015','2016')
),
par AS (
  SELECT application_number AS app_id,
         STRING_AGG(DISTINCT continuation_type ORDER BY continuation_type) AS ctypes
  FROM `patents-public-data.uspto_oce_pair.continuity_parents` GROUP BY 1
),
ad AS (
  SELECT application_number AS app_id,
         MIN(earliest_pgpub_date) AS pgpub_dt, MIN(filing_date) AS filing_dt,
         ANY_VALUE(application_type) AS app_type, COUNT(*) AS n_dup
  FROM `patents-public-data.uspto_oce_pair.application_data` GROUP BY 1
)
SELECT c.oa_year,
       COUNT(*)                                          AS n_cohort,
       COUNTIF(a.app_id IS NOT NULL)                     AS n_in_pair,
       MAX(IFNULL(a.n_dup,0))                            AS max_dup,
       COUNTIF(p.app_id IS NOT NULL)                     AS n_has_parent,
       COUNTIF(p.app_id IS NULL)                         AS n_primary,
       COUNTIF(a.pgpub_dt IS NOT NULL AND a.pgpub_dt!='') AS n_has_pgpub_dt,
       COUNTIF(a.pgpub_dt IS NOT NULL AND a.pgpub_dt!='' AND a.pgpub_dt < c.first_oa_dt) AS n_pub_before_oa,
       COUNTIF(p.app_id IS NULL AND a.pgpub_dt IS NOT NULL AND a.pgpub_dt!='' AND a.pgpub_dt < c.first_oa_dt) AS n_primary_and_pub_before,
       APPROX_TOP_COUNT(p.ctypes, 8)                     AS top_ctypes
FROM cohort c
LEFT JOIN par p ON c.app_id = p.app_id
LEFT JOIN ad  a ON c.app_id = a.app_id
GROUP BY 1 ORDER BY 1

-- УСТАРЕЛ: построен на uspto_oce_pair, который выброшен (vintage 2015).
-- Сохранён как источник чисел, процитированных в brief-r4.
-- Замена: 09_parent_vs_pair.sql
-- диаграмма потока, размеры сплитов, число страт K
-- цена 0,542 ГиБ   ВНИМАНИЕ: без тай-брейкера
-- ВАЖНО: pub_before_oa берётся из PAIR (vintage 2015) → дыра 28,9% на 2016.
--        При перезапуске брать publication_date из publications_201710.
WITH flagged AS (
  SELECT app_id, mail_dt, art_unit,
         ROW_NUMBER() OVER (PARTITION BY app_id ORDER BY mail_dt) AS rn
  FROM `patents-public-data.uspto_oce_office_actions.office_actions`
  WHERE rejection_101='1' OR rejection_102='1' OR rejection_103='1' OR rejection_112='1'
),
cohort AS (
  SELECT app_id, art_unit, mail_dt AS first_oa_dt,
         CASE WHEN SUBSTR(mail_dt,1,4)='2016' THEN '2016 (test)'
              WHEN SUBSTR(mail_dt,6,2) <= '06' THEN '2015 H1 (train)'
              ELSE '2015 H2 (valid)' END AS part
  FROM flagged
  WHERE rn = 1 AND REGEXP_CONTAINS(art_unit, r'^21\d\d$')
    AND SUBSTR(mail_dt,1,4) IN ('2015','2016')
),
par AS (SELECT application_number AS app_id,
               STRING_AGG(DISTINCT continuation_type ORDER BY continuation_type) AS ctypes
        FROM `patents-public-data.uspto_oce_pair.continuity_parents` GROUP BY 1),
ad  AS (SELECT application_number AS app_id, MIN(earliest_pgpub_date) AS pgpub_dt
        FROM `patents-public-data.uspto_oce_pair.application_data` GROUP BY 1),
xw  AS (SELECT CAST(patentApplicationNumber AS STRING) AS app_id,
               COUNTIF(REGEXP_CONTAINS(publication_number, r'^US-\d+-A')) AS n_pgpub
        FROM `patents-public-data.uspto_office_actions_text.app_pub_crosswalk` GROUP BY 1),
j AS (
  SELECT c.part, c.art_unit,
         (p.ctypes IS NOT NULL AND REGEXP_CONTAINS(p.ctypes, r'CON|DIV|CIP')) AS is_cont,
         (a.app_id IS NULL)                                                   AS pair_missing,
         IFNULL(x.n_pgpub,0) > 0                                              AS has_a_pub,
         (a.pgpub_dt IS NOT NULL AND a.pgpub_dt != '' AND a.pgpub_dt < c.first_oa_dt) AS pub_before_oa
  FROM cohort c
  LEFT JOIN par p ON c.app_id = p.app_id
  LEFT JOIN ad  a ON c.app_id = a.app_id
  LEFT JOIN xw  x ON c.app_id = x.app_id
)
SELECT part,
       COUNT(*)                                             AS n0_cohort,
       COUNTIF(pair_missing)                                AS n_pair_missing,
       COUNTIF(is_cont)                                     AS n_continuation,
       COUNTIF(NOT is_cont)                                 AS n1_primary,
       COUNTIF(NOT is_cont AND has_a_pub)                   AS n2_with_apub,
       COUNTIF(NOT is_cont AND has_a_pub AND pub_before_oa) AS n3_final,
       COUNT(DISTINCT IF(NOT is_cont AND has_a_pub AND pub_before_oa, art_unit, NULL)) AS k_art_units
FROM j GROUP BY part ORDER BY part

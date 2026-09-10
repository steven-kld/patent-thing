-- publications.parent против uspto_oce_pair: покрытие преемственности по годам
-- цена 3,169 ГиБ
WITH flagged AS (
  SELECT app_id, mail_dt, art_unit,
         ROW_NUMBER() OVER (PARTITION BY app_id ORDER BY mail_dt, ifw_number) AS rn
  FROM `patents-public-data.uspto_oce_office_actions.office_actions`
  WHERE rejection_101='1' OR rejection_102='1' OR rejection_103='1' OR rejection_112='1'
),
cohort AS (
  SELECT app_id, SUBSTR(mail_dt,1,4) AS oa_year
  FROM flagged
  WHERE rn = 1 AND REGEXP_CONTAINS(art_unit, r'^21\d\d$')
    AND SUBSTR(mail_dt,1,4) IN ('2015','2016')
),
xw AS (
  SELECT CAST(patentApplicationNumber AS STRING) AS app_id,
         ARRAY_AGG(publication_number ORDER BY publication_number LIMIT 1)[OFFSET(0)] AS pub_no
  FROM `patents-public-data.uspto_office_actions_text.app_pub_crosswalk`
  WHERE REGEXP_CONTAINS(publication_number, r'^US-\d+-A')
  GROUP BY 1
),
pub AS (
  SELECT publication_number AS pub_no,
         EXISTS(SELECT 1 FROM UNNEST(parent) p
                WHERE p.type IN ('continuation','division','continuation-in-part')) AS cont_strict,
         EXISTS(SELECT 1 FROM UNNEST(parent) p WHERE p.type = 'division-into')       AS div_into,
         EXISTS(SELECT 1 FROM UNNEST(parent) p WHERE p.type = 'a-371-of-international') AS pct371,
         ARRAY_LENGTH(parent) AS n_parent
  FROM `patents-public-data.patents.publications`
),
pair AS (
  SELECT application_number AS app_id,
         STRING_AGG(DISTINCT continuation_type ORDER BY continuation_type) AS ctypes
  FROM `patents-public-data.uspto_oce_pair.continuity_parents` GROUP BY 1
),
ad AS (SELECT DISTINCT application_number AS app_id
       FROM `patents-public-data.uspto_oce_pair.application_data`)
SELECT c.oa_year,
       COUNT(*)                                                    AS n_cohort,
       COUNTIF(x.pub_no IS NOT NULL)                               AS n_has_apub,
       COUNTIF(p.pub_no IS NOT NULL)                               AS n_in_publications,
       COUNTIF(a.app_id IS NULL)                                   AS n_pair_missing,
       COUNTIF(IFNULL(p.cont_strict,FALSE))                        AS n_cont_pub,
       COUNTIF(pr.ctypes IS NOT NULL AND REGEXP_CONTAINS(pr.ctypes, r'CON|DIV|CIP')) AS n_cont_pair,
       COUNTIF(IFNULL(p.div_into,FALSE))                           AS n_div_into,
       COUNTIF(IFNULL(p.pct371,FALSE))                             AS n_pct371,
       COUNTIF(    IFNULL(p.cont_strict,FALSE)  AND     (pr.ctypes IS NOT NULL AND REGEXP_CONTAINS(pr.ctypes, r'CON|DIV|CIP'))) AS both_yes,
       COUNTIF(    IFNULL(p.cont_strict,FALSE)  AND NOT (pr.ctypes IS NOT NULL AND REGEXP_CONTAINS(pr.ctypes, r'CON|DIV|CIP'))) AS pub_only,
       COUNTIF(NOT IFNULL(p.cont_strict,FALSE)  AND     (pr.ctypes IS NOT NULL AND REGEXP_CONTAINS(pr.ctypes, r'CON|DIV|CIP'))) AS pair_only
FROM cohort c
LEFT JOIN xw   x  ON c.app_id = x.app_id
LEFT JOIN pub  p  ON x.pub_no = p.pub_no
LEFT JOIN pair pr ON c.app_id = pr.app_id
LEFT JOIN ad   a  ON c.app_id = a.app_id
GROUP BY 1 ORDER BY 1

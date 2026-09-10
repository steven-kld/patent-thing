-- yield: когорта → publication_number; оценка ловушки №5 (непубликация)
-- цена 0,298 ГиБ   ВНИМАНИЕ: без тай-брейкера, запускалось до его принятия
WITH flagged AS (
  SELECT app_id, mail_dt, art_unit,
         ROW_NUMBER() OVER (PARTITION BY app_id ORDER BY mail_dt) AS rn
  FROM `patents-public-data.uspto_oce_office_actions.office_actions`
  WHERE rejection_101='1' OR rejection_102='1' OR rejection_103='1' OR rejection_112='1'
),
cohort AS (
  SELECT app_id, SAFE_CAST(app_id AS INT64) AS app_key, SUBSTR(mail_dt,1,4) AS oa_year
  FROM flagged
  WHERE rn = 1 AND REGEXP_CONTAINS(art_unit, r'^21\d\d$')
    AND SUBSTR(mail_dt,1,4) IN ('2015','2016')
),
xw AS (
  SELECT patentApplicationNumber AS app_key,
         COUNTIF(REGEXP_CONTAINS(publication_number, r'^US-\d+-A')) AS n_pgpub,
         COUNTIF(REGEXP_CONTAINS(publication_number, r'^US-\d+-B')) AS n_grant
  FROM `patents-public-data.uspto_office_actions_text.app_pub_crosswalk`
  GROUP BY 1
)
SELECT c.oa_year,
       COUNT(*)                                                     AS n_cohort,
       COUNTIF(c.app_key IS NULL)                                   AS n_cast_fail,
       COUNTIF(STARTS_WITH(c.app_id,'0'))                           AS n_leading_zero,
       COUNTIF(x.app_key IS NOT NULL)                               AS n_in_xwalk,
       COUNTIF(IFNULL(x.n_pgpub,0) > 0)                             AS n_with_pgpub,
       COUNTIF(IFNULL(x.n_pgpub,0) > 1)                             AS n_multi_pgpub,
       COUNTIF(IFNULL(x.n_pgpub,0) = 0 AND IFNULL(x.n_grant,0) > 0) AS n_grant_only
FROM cohort c LEFT JOIN xw x ON c.app_key = x.app_key
GROUP BY 1 ORDER BY 1

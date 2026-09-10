WITH flagged AS (
  SELECT app_id, ifw_number, mail_dt, art_unit, rejection_103
  FROM `patents-public-data.uspto_oce_office_actions.office_actions`
  WHERE rejection_101='1' OR rejection_102='1' OR rejection_103='1' OR rejection_112='1'
),
first_dt AS (SELECT app_id, MIN(mail_dt) AS min_dt FROM flagged GROUP BY 1),
grp AS (
  SELECT f.app_id,
         SUBSTR(d.min_dt,1,4)                       AS yr,
         COUNT(*)                                   AS n_docs,
         COUNT(DISTINCT f.ifw_number)               AS n_ifw,
         COUNT(DISTINCT f.art_unit)                 AS n_au,
         COUNT(DISTINCT f.rejection_103)            AS n_y,
         MAX(IF(REGEXP_CONTAINS(f.art_unit, r'^21\d\d$'),1,0)) AS any21,
         MIN(IF(REGEXP_CONTAINS(f.art_unit, r'^21\d\d$'),1,0)) AS all21
  FROM flagged f JOIN first_dt d ON f.app_id=d.app_id AND f.mail_dt=d.min_dt
  GROUP BY 1,2
)
SELECT yr,
       COUNT(*)                                        AS n_apps,
       COUNTIF(n_docs > 1)                             AS n_tied,
       COUNTIF(n_docs > 1 AND n_ifw < n_docs)          AS n_ifw_not_unique,
       COUNTIF(n_docs > 1 AND n_au > 1)                AS n_tied_diff_au,
       COUNTIF(n_docs > 1 AND any21=1 AND all21=0)     AS n_tied_2100_boundary,
       COUNTIF(n_docs > 1 AND n_y  > 1)                AS n_tied_diff_y
FROM grp
WHERE yr IN ('2015','2016')
GROUP BY yr ORDER BY yr

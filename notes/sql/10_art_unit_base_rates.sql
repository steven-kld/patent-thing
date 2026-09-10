-- базовые ставки §103 по art unit; сколько строк valid в области ставок
-- цена 0,611 ГиБ
WITH flagged AS (
  SELECT app_id, mail_dt, art_unit, rejection_103,
         ROW_NUMBER() OVER (PARTITION BY app_id ORDER BY mail_dt, ifw_number) AS rn
  FROM `patents-public-data.uspto_oce_office_actions.office_actions`
  WHERE rejection_101='1' OR rejection_102='1' OR rejection_103='1' OR rejection_112='1'
),
cohort AS (
  SELECT app_id, art_unit, mail_dt AS first_oa_dt, rejection_103,
         IF(SUBSTR(mail_dt,6,2) <= '06', 'train', 'valid') AS part
  FROM flagged
  WHERE rn = 1 AND REGEXP_CONTAINS(art_unit, r'^21\d\d$') AND SUBSTR(mail_dt,1,4)='2015'
),
par AS (SELECT application_number AS app_id,
               STRING_AGG(DISTINCT continuation_type ORDER BY continuation_type) AS ctypes
        FROM `patents-public-data.uspto_oce_pair.continuity_parents` GROUP BY 1),
ad  AS (SELECT application_number AS app_id, MIN(earliest_pgpub_date) AS pgpub_dt
        FROM `patents-public-data.uspto_oce_pair.application_data` GROUP BY 1),
xw  AS (SELECT CAST(patentApplicationNumber AS STRING) AS app_id,
               COUNTIF(REGEXP_CONTAINS(publication_number, r'^US-\d+-A')) AS n_pgpub
        FROM `patents-public-data.uspto_office_actions_text.app_pub_crosswalk` GROUP BY 1),
final AS (
  SELECT c.art_unit, c.part, c.rejection_103
  FROM cohort c
  LEFT JOIN par p ON c.app_id=p.app_id
  LEFT JOIN ad  a ON c.app_id=a.app_id
  LEFT JOIN xw  x ON c.app_id=x.app_id
  WHERE NOT (p.ctypes IS NOT NULL AND REGEXP_CONTAINS(p.ctypes, r'CON|DIV|CIP'))
    AND IFNULL(x.n_pgpub,0) > 0
    AND a.pgpub_dt IS NOT NULL AND a.pgpub_dt != '' AND a.pgpub_dt < c.first_oa_dt
),
au AS (
  SELECT art_unit,
         COUNTIF(part='train')                                   AS n_train,
         COUNTIF(part='valid')                                   AS n_valid,
         COUNTIF(part='train' AND rejection_103='1')             AS n103_train,
         SAFE_DIVIDE(COUNTIF(part='train' AND rejection_103='1'),
                     COUNTIF(part='train'))                      AS share_train
  FROM final GROUP BY 1
)
SELECT
  COUNT(*)                                                AS n_art_units,
  COUNTIF(n_train >= 50)                                  AS au_ge50_train,
  SUM(n_train)                                            AS rows_train,
  SUM(n_valid)                                            AS rows_valid,
  COUNTIF(share_train > 0.8889)                           AS au_above_p_star,
  COUNTIF(share_train > 0.8889 AND n_train >= 50)         AS au_above_p_star_ge50,
  SUM(IF(share_train > 0.8889, n_valid, 0))               AS valid_rows_above,
  SUM(IF(share_train > 0.8889 AND n_train >= 50, n_valid, 0)) AS valid_rows_above_ge50,
  SUM(IF(n_train < 50, n_train, 0))                       AS train_rows_in_small_au,
  SUM(IF(n_train < 50, n_valid, 0))                       AS valid_rows_in_small_au,
  APPROX_QUANTILES(share_train, 10)                       AS share_deciles,
  MAX(share_train)                                        AS max_share
FROM au

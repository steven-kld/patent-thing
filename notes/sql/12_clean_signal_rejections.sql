-- сигнал чистки rejections.type='103' против регулярок
-- цена 9,557 ГиБ — ОТВЕРГНУТ как исправитель, точность ~50%
WITH oce AS (
  SELECT app_id, mail_dt, art_unit, rejection_103,
         ROW_NUMBER() OVER (PARTITION BY app_id ORDER BY mail_dt, ifw_number) AS rn
  FROM `patents-public-data.uspto_oce_office_actions.office_actions`
  WHERE rejection_101='1' OR rejection_102='1' OR rejection_103='1' OR rejection_112='1'
),
coh AS (SELECT * FROM oce
        WHERE rn=1 AND REGEXP_CONTAINS(art_unit, r'^21\d\d$') AND SUBSTR(mail_dt,1,4)='2015'),
txt AS (
  SELECT CAST(patentApplicationNumber AS STRING) AS app_id,
         SUBSTR(submissionDate,1,10) AS sub_dt,
         bodyText,
         EXISTS(SELECT 1 FROM UNNEST(rejections) r WHERE r.type = '103') AS rej103,
         ARRAY_LENGTH(rejections) AS n_rej
  FROM `patents-public-data.uspto_office_actions_text.office_actions` TABLESAMPLE SYSTEM (5 PERCENT)
  WHERE techCenter = 2100 AND SUBSTR(submissionDate,1,4)='2015'
)
SELECT c.rejection_103                                                            AS flag,
       REGEXP_CONTAINS(t.bodyText, r'(?is)rejected\s+under\b.{0,60}?103')         AS b2,
       REGEXP_CONTAINS(t.bodyText, r'(?i)Claim\s+Rejections\s*[-–]\s*35\s*USC\s*§?\s*103') AS e,
       t.rej103                                                                   AS rj,
       (t.n_rej = 0)                                                              AS rej_empty,
       COUNT(*) AS n
FROM coh c JOIN txt t ON c.app_id=t.app_id AND c.mail_dt=t.sub_dt
GROUP BY 1,2,3,4,5 ORDER BY 1,2,3,4,5

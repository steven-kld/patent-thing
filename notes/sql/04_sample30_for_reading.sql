WITH oce AS (
  SELECT app_id, mail_dt, art_unit, document_cd,
         rejection_101, rejection_102, rejection_103, rejection_112,
         header_missing, fp_missing, rejection_fp_mismatch, closing_missing,
         ROW_NUMBER() OVER (PARTITION BY app_id ORDER BY mail_dt, ifw_number) AS rn
  FROM `patents-public-data.uspto_oce_office_actions.office_actions`
  WHERE rejection_101='1' OR rejection_102='1' OR rejection_103='1' OR rejection_112='1'
),
coh AS (
  SELECT * FROM oce
  WHERE rn = 1 AND REGEXP_CONTAINS(art_unit, r'^21\d\d$') AND SUBSTR(mail_dt,1,4)='2015'
),
txt AS (
  SELECT CAST(patentApplicationNumber AS STRING) AS app_id,
         SUBSTR(submissionDate,1,10)             AS sub_dt,
         legacyDocumentCodeIdentifier            AS doc_cd_txt,
         ARRAY_LENGTH(rejections)                AS n_rej,
         ARRAY_TO_STRING(ARRAY(SELECT DISTINCT r.type FROM UNNEST(rejections) r), ',') AS rej_types,
         sections.section103RejectionFormParagraphText AS fp103,
         bodyText
  FROM `patents-public-data.uspto_office_actions_text.office_actions` TABLESAMPLE SYSTEM (1 PERCENT)
  WHERE techCenter = 2100 AND SUBSTR(submissionDate,1,4) = '2015'
)
SELECT c.app_id, c.mail_dt, c.art_unit, c.document_cd, t.doc_cd_txt,
       c.rejection_101, c.rejection_102, c.rejection_103, c.rejection_112,
       c.rejection_fp_mismatch, c.header_missing, c.fp_missing, c.closing_missing,
       t.n_rej, t.rej_types, t.fp103, t.bodyText
FROM coh c
JOIN txt t ON c.app_id = t.app_id AND c.mail_dt = t.sub_dt
QUALIFY ROW_NUMBER() OVER (PARTITION BY c.rejection_103 ORDER BY FARM_FINGERPRINT(c.app_id)) <= 15

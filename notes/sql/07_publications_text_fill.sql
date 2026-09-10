-- заполненность и длины claims_localized у US pre-grant публикаций окна
-- цена 1,188 ГиБ   TABLESAMPLE — по частотам воспроизводимо, построчно нет
WITH s AS (
  SELECT publication_number, kind_code, publication_date,
         claims_localized AS cl,
         claims_localized[SAFE_OFFSET(0)].text AS txt
  FROM `patents-public-data.patents.publications` TABLESAMPLE SYSTEM (1 PERCENT)
  WHERE country_code = 'US' AND kind_code LIKE 'A%'
    AND publication_date BETWEEN 20130101 AND 20161231
)
SELECT COUNT(*)                              AS n_sample,
       COUNTIF(ARRAY_LENGTH(cl) = 0)         AS n_array_empty,
       COUNTIF(txt IS NULL OR txt = '')      AS n_text_blank,
       COUNTIF(cl[SAFE_OFFSET(0)].truncated) AS n_truncated,
       APPROX_QUANTILES(LENGTH(txt), 10)     AS len_deciles,
       ARRAY_AGG(STRUCT(publication_number, kind_code, publication_date,
                        LENGTH(txt) AS len, SUBSTR(txt,1,450) AS head)
                 ORDER BY publication_number LIMIT 4) AS samples
FROM s

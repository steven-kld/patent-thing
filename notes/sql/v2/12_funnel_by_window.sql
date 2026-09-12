-- Воронка по окнам. Дало (Manifest §"Воронка"):
--   2015H1 14 617 / 13 965 / 12 664 / 9 524   выжило 65,2%
--   2015H2 10 475 / 10 155 /  8 846 / 6 523   выжило 62,3%
--   2016H1 12 880 / 12 456 / 10 718 / 7 513   выжило 58,3%
--   2016H2 11 789 / 11 719 / 10 168 / 7 417   выжило 62,9%
-- Контрольные суммы совпали по всем четырём столбцам с 11_funnel_202511.
-- Тестовый блок (2016H2) = 7 417 заявок — потолок ставок, не число ставок.
-- Цена: 5,06 ГиБ.
-- --maximum_bytes_billed=6100000000

-- популяция Manifest §9: критерии 1-3 (окно, art unit 21xx, одиночная строка)
WITH m AS (SELECT app_id, MIN(mail_dt) d FROM `patents-public-data.uspto_oce_office_actions.office_actions` GROUP BY 1),
     f AS (SELECT o.app_id, o.mail_dt, o.art_unit FROM `patents-public-data.uspto_oce_office_actions.office_actions` o
           JOIN m ON o.app_id=m.app_id AND o.mail_dt=m.d
           WHERE m.d BETWEEN '2015-01-01' AND '2016-12-31'),
     g AS (SELECT app_id, COUNT(*) n, MIN(mail_dt) dt, ANY_VALUE(art_unit) au FROM f GROUP BY 1),
     pop AS (SELECT app_id, dt, CAST(REPLACE(dt,'-','') AS INT64) oa_dt FROM g
             WHERE n=1 AND SUBSTR(au,1,2)='21'),
     p AS (SELECT SUBSTR(application_number_formatted,3) an, kind_code, publication_date,
                  ARRAY_LENGTH(parent) np
           FROM `patents-public-data.patents.publications_202511` WHERE country_code='US' AND application_number_formatted!='')
SELECT CASE WHEN pop.dt<'2015-07-01' THEN '2015H1'
            WHEN pop.dt<'2016-01-01' THEN '2015H2'
            WHEN pop.dt<'2016-07-01' THEN '2016H1'
            ELSE '2016H2' END half,
       COUNT(DISTINCT pop.app_id) after_c123,
       COUNT(DISTINCT IF(p.kind_code='A1', pop.app_id, NULL)) has_a1,
       COUNT(DISTINCT IF(p.kind_code='A1' AND p.publication_date>0
             AND p.publication_date<pop.oa_dt, pop.app_id, NULL)) a1_before,
       COUNT(DISTINCT IF(p.kind_code='A1' AND p.publication_date>0
             AND p.publication_date<pop.oa_dt AND p.np=0, pop.app_id, NULL)) final
FROM pop LEFT JOIN p ON p.an = pop.app_id GROUP BY 1 ORDER BY 1;

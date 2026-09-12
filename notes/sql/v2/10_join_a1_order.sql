-- Склейка + наличие A1 + порядок «A1 против первого действия».
-- Дало (на живой таблице; на publications_202511 воспроизвелось до единицы):
--   pop_apps 49 761 | key_matched 49 743 (99,96%, не склеилось 18)
--   has_a1 48 295 | a1_before_oa 42 396 | a1_after_oa 5 899
--   сходимость 42 396 + 5 899 = 48 295 ровно.
-- Опровергло посылку «A1 не может быть раньше первого действия»: в 85,2%
-- случаев именно раньше, в 11,9% — нет. Основание критерия 5 (Manifest §9).
-- Защита: publication_date>0, иначе неопубликованные с нулём считались бы
-- «раньше любой даты».
-- Цена: 4,79 ГиБ.
-- --maximum_bytes_billed=5800000000

-- популяция Manifest §9: критерии 1-3 (окно, art unit 21xx, одиночная строка)
WITH m AS (SELECT app_id, MIN(mail_dt) d FROM `patents-public-data.uspto_oce_office_actions.office_actions` GROUP BY 1),
     f AS (SELECT o.app_id, o.mail_dt, o.art_unit FROM `patents-public-data.uspto_oce_office_actions.office_actions` o
           JOIN m ON o.app_id=m.app_id AND o.mail_dt=m.d
           WHERE m.d BETWEEN '2015-01-01' AND '2016-12-31'),
     g AS (SELECT app_id, COUNT(*) n, MIN(mail_dt) dt, ANY_VALUE(art_unit) au FROM f GROUP BY 1),
     pop AS (SELECT app_id, dt, CAST(REPLACE(dt,'-','') AS INT64) oa_dt FROM g
             WHERE n=1 AND SUBSTR(au,1,2)='21'),
     p AS (SELECT SUBSTR(application_number_formatted,3) an, kind_code, publication_date
           FROM `patents-public-data.patents.publications_202511`
           WHERE country_code='US' AND application_number_formatted IS NOT NULL
             AND application_number_formatted!='')
SELECT COUNT(DISTINCT pop.app_id) pop_apps,
       COUNT(DISTINCT IF(p.an IS NOT NULL, pop.app_id, NULL)) key_matched,
       COUNT(DISTINCT IF(p.kind_code='A1', pop.app_id, NULL)) has_a1,
       COUNT(DISTINCT IF(p.kind_code='A1' AND p.publication_date>0
             AND p.publication_date<pop.oa_dt, pop.app_id, NULL)) a1_before_oa,
       COUNT(DISTINCT IF(p.kind_code='A1' AND p.publication_date>0
             AND p.publication_date>=pop.oa_dt, pop.app_id, NULL)) a1_after_oa
FROM pop LEFT JOIN p ON p.an = pop.app_id;

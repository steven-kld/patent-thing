-- ВОРОНКА ЦЕЛИКОМ на замороженном снимке, включая критерий 4 (продолжения).
-- Дало: 49 761 -> 48 295 -> 42 396 -> 30 977 (orig_only), продолжений 11 419.
-- Сходимость: 30 977 + 11 419 = 42 396 ровно.
-- Первые четыре числа совпали с замером на ЖИВОЙ таблице до единицы —
-- это и есть доказательство воспроизводимости (шаг 13). Manifest §"Воронка".
-- Цена: 5,06 ГиБ (объединённый проход дешевле раздельных: ~$0,031 против ~$0,07).
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
SELECT COUNT(DISTINCT pop.app_id) pop_apps,
       COUNT(DISTINCT IF(p.an IS NOT NULL, pop.app_id, NULL)) key_matched,
       COUNT(DISTINCT IF(p.kind_code='A1', pop.app_id, NULL)) has_a1,
       COUNT(DISTINCT IF(p.kind_code='A1' AND p.publication_date>0
             AND p.publication_date<pop.oa_dt, pop.app_id, NULL)) a1_before,
       COUNT(DISTINCT IF(p.kind_code='A1' AND p.publication_date>0
             AND p.publication_date<pop.oa_dt AND p.np=0, pop.app_id, NULL)) orig_only,
       COUNT(DISTINCT IF(p.kind_code='A1' AND p.publication_date>0
             AND p.publication_date<pop.oa_dt AND p.np>0, pop.app_id, NULL)) continuations
FROM pop LEFT JOIN p ON p.an = pop.app_id;

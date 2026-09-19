-- ШАГ 13, проверка детерминизма. Прошлый прогон здесь и споткнулся:
-- три прогона давали 27 312 / 313 / 314.
-- Материализация была прогоном 1; этот запрос — прогон 2.
-- Сравнивается не только ЧИСЛО строк, но и САМ СОСТАВ: MD5 отсортированного
-- списка app_id. Совпадение счётчиков при разном наборе так не проскочит.
--
-- Дало: оба прогона 30 977 строк, 30 977 уникальных,
--       отпечаток 09934048a3fcb4a0a812c0bb0876b042 — ОДИНАКОВ.
--
-- ЛОВУШКА: SUM(FARM_FINGERPRINT(app_id)) переполняет INT64 на 30 тысячах
-- значений. Запрос при этом ОТРАБАТЫВАЕТ И ТАРИФИЦИРУЕТСЯ, возвращая ошибку.
-- Цена: 5,06 ГиБ ≈ $0,031 за свежий прогон; по своей таблице ~$0,001.
-- --maximum_bytes_billed=6100000000

-- прогон 2: свежий отбор популяции
WITH m AS (SELECT app_id, MIN(mail_dt) d FROM `patents-public-data.uspto_oce_office_actions.office_actions` GROUP BY 1),
     f AS (SELECT o.app_id, o.mail_dt, o.art_unit, o.rejection_103 FROM `patents-public-data.uspto_oce_office_actions.office_actions` o
           JOIN m ON o.app_id=m.app_id AND o.mail_dt=m.d
           WHERE m.d BETWEEN '2015-01-01' AND '2016-12-31'),
     g AS (SELECT app_id, COUNT(*) n, MIN(mail_dt) dt, MIN(art_unit) au,
                  MAX(CAST(rejection_103 AS INT64)) flag FROM f GROUP BY 1),
     pop AS (SELECT app_id, dt, CAST(REPLACE(dt,'-','') AS INT64) oa_dt
             FROM g WHERE n=1 AND SUBSTR(au,1,2)='21'),
     sel AS (SELECT pop.app_id FROM pop
             JOIN `patents-public-data.patents.publications_202511` p ON SUBSTR(p.application_number_formatted,3)=pop.app_id
             WHERE p.country_code='US' AND p.kind_code='A1' AND p.publication_date>0
               AND p.publication_date<pop.oa_dt AND ARRAY_LENGTH(p.parent)=0)
SELECT COUNT(*) n_rows, COUNT(DISTINCT app_id) n_uniq,
       TO_HEX(MD5(STRING_AGG(app_id, ',' ORDER BY app_id))) set_hash FROM sel;

-- прогон 1: то, что лежит в материализованной таблице
SELECT COUNT(*) n_rows, COUNT(DISTINCT app_id) n_uniq,
       TO_HEX(MD5(STRING_AGG(app_id, ',' ORDER BY app_id))) set_hash
FROM `<свой проект>.patent_v2.cohort`;

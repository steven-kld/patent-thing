-- Доли §103 по ПОДРАЗДЕЛЕНИЯМ внутри 2100. Анализ, не требование стадии 3.
-- Область: только train+valid. Популяция — итоговая, после всех пяти критериев.
-- Дало: 69 подразделений, 23 560 заявок, общая доля 76,45%.
--   >= 95%          0 подразделений
--   90–95%          4 подразделения, 1 232 заявки, 92,5%
--   88,89–90%       1, 175
--   85–88,89%       9, 3 162, 87,0%
--   80–85%         16, 6 012, 82,6%
--   < 80%          39, 12 979, 69,3%
-- Надёжно выше безубыточности (нижняя 95% граница > 8/9) — ДВА:
--   2174  n=403  92,80%  нижняя 90,69%
--   2195  n=314  94,90%  нижняя 92,86%
-- Цена: 5,06 ГиБ ≈ $0,031.
-- --maximum_bytes_billed=6100000000

WITH m AS (SELECT app_id, MIN(mail_dt) d FROM `patents-public-data.uspto_oce_office_actions.office_actions` GROUP BY 1),
     f AS (SELECT o.app_id, o.mail_dt, o.art_unit, o.rejection_103 FROM `patents-public-data.uspto_oce_office_actions.office_actions` o
           JOIN m ON o.app_id=m.app_id AND o.mail_dt=m.d
           WHERE m.d BETWEEN '2015-01-01' AND '2016-06-30'),
     g AS (SELECT app_id, COUNT(*) n, MIN(mail_dt) dt, MIN(art_unit) au,
                  MAX(CAST(rejection_103 AS INT64)) flag FROM f GROUP BY 1),
     pop AS (SELECT app_id, au, flag, CAST(REPLACE(dt,'-','') AS INT64) oa_dt
             FROM g WHERE n=1 AND SUBSTR(au,1,2)='21'),
     p AS (SELECT SUBSTR(application_number_formatted,3) an,
                  MAX(IF(kind_code='A1' AND publication_date>0,publication_date,NULL)) a1,
                  MAX(IF(kind_code='A1',ARRAY_LENGTH(parent),NULL)) np
           FROM `patents-public-data.patents.publications_202511` WHERE country_code='US' AND application_number_formatted!='' GROUP BY 1)
SELECT pop.au AS art_unit, COUNT(*) n, SUM(pop.flag) n103
FROM pop JOIN p ON p.an=pop.app_id
WHERE p.a1 IS NOT NULL AND p.a1 < pop.oa_dt AND p.np = 0
GROUP BY 1 ORDER BY 1;

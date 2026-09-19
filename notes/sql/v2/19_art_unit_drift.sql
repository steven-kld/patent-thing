-- Устойчивость подразделений во времени: те же доли по ПОЛУГОДИЯМ train+valid.
-- Отвечает на вопрос «а вдруг поведение подразделения изменится».
-- Дало: из 59 подразделений с n>=60 в каждом периоде дрейф значим у ВОСЬМИ
-- (симуляция при постоянной доле, p<0,05). У остальных 51 разброс объясняется
-- размером выборки: медианный размах 6,7 п.п. — столько же даёт чистый шум.
--
-- ГЛАВНОЕ: из двух «надёжных» подразделений
--   2174  92,1% -> 92,9% -> 93,8%   размах 1,7 п   p=0,867   устойчиво
--   2195  97,9% -> 95,6% -> 88,5%   размах 9,5 п   p=0,013   РЕАЛЬНОЕ ПАДЕНИЕ
-- 2195 выглядел лучшим только потому, что его усреднили по падающей траектории.
-- В последнем полугодии перед тестовым окном он уже не выше безубыточности.
--
-- И проверка правила «нигде не ниже 85%» вне выборки (отбор по двум первым
-- полугодиям, оценка на третьем): доля на отборе 89,13%, в следующем периоде
-- 87,22%, EV переворачивается с +0,22 на −1,50. Регрессия к среднему −1,9 п.п.
-- Отбор по подразделениям цели не берёт НИ ПРИ КАКОМ пороге.
-- Цена: 5,06 ГиБ ≈ $0,031.
-- --maximum_bytes_billed=6100000000

WITH m AS (SELECT app_id, MIN(mail_dt) d FROM `patents-public-data.uspto_oce_office_actions.office_actions` GROUP BY 1),
     f AS (SELECT o.app_id, o.mail_dt, o.art_unit, o.rejection_103 FROM `patents-public-data.uspto_oce_office_actions.office_actions` o
           JOIN m ON o.app_id=m.app_id AND o.mail_dt=m.d
           WHERE m.d BETWEEN '2015-01-01' AND '2016-06-30'),
     g AS (SELECT app_id, COUNT(*) n, MIN(mail_dt) dt, MIN(art_unit) au,
                  MAX(CAST(rejection_103 AS INT64)) flag FROM f GROUP BY 1),
     pop AS (SELECT app_id, au, flag, dt, CAST(REPLACE(dt,'-','') AS INT64) oa_dt
             FROM g WHERE n=1 AND SUBSTR(au,1,2)='21'),
     p AS (SELECT SUBSTR(application_number_formatted,3) an,
                  MAX(IF(kind_code='A1' AND publication_date>0,publication_date,NULL)) a1,
                  MAX(IF(kind_code='A1',ARRAY_LENGTH(parent),NULL)) np
           FROM `patents-public-data.patents.publications_202511` WHERE country_code='US' AND application_number_formatted!='' GROUP BY 1)
SELECT pop.au AS art_unit,
       CASE WHEN pop.dt<'2015-07-01' THEN 'H1_2015'
            WHEN pop.dt<'2016-01-01' THEN 'H2_2015' ELSE 'H1_2016' END AS half,
       COUNT(*) n, SUM(pop.flag) n103
FROM pop JOIN p ON p.an=pop.app_id
WHERE p.a1 IS NOT NULL AND p.a1 < pop.oa_dt AND p.np = 0
GROUP BY 1,2;

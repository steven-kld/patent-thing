-- ШАГ 14. Смещение фильтров ПО ЦЕЛИ, не по числу строк.
-- Область: ТОЛЬКО train+valid (2015-01 … 2016-06). Тестовое окно не трогается:
-- отсутствие поокошных долей исходов и есть то, что делает выбор ящика слепым.
-- Дало (популяция 21xx в окне: 41 285 заявок, доля §103 73,02%):
--   критерий 3 задвоенность   осталось 37 972 · 72,97%  снято  3 313 · 73,62%  −0,65 п
--   критерий 5 A1 раньше      осталось 35 306 · 73,76%  снято  5 979 · 68,66%  +5,10 п
--   критерий 4 продолжения    осталось 28 546 · 76,71%  снято 11 340 · 64,11%  +12,60 п
-- Вывод: критерий 3 нейтрален; критерий 4 МЕНЯЕТ ЗАДАЧУ, а не чистит данные.
-- Базовая ставка сдвигается 73,02% -> 76,71%; тривиальный бейслайн
-- «ставить на всё» остаётся убыточным: EV = 90*0,7671 − 80 = −10,96.
-- Фильтр по art_unit в замер НЕ включён: это определение популяции из вопроса
-- стадии 1, а не чистка внутри неё.
-- Цена: 5,07 ГиБ ≈ $0,031.
-- --maximum_bytes_billed=6100000000

WITH m AS (SELECT app_id, MIN(mail_dt) d FROM `patents-public-data.uspto_oce_office_actions.office_actions` GROUP BY 1),
     f AS (SELECT o.app_id, o.mail_dt, o.art_unit, o.rejection_103 FROM `patents-public-data.uspto_oce_office_actions.office_actions` o
           JOIN m ON o.app_id=m.app_id AND o.mail_dt=m.d
           WHERE m.d BETWEEN '2015-01-01' AND '2016-06-30'),
     g AS (SELECT app_id, COUNT(*) n, MIN(mail_dt) dt, ANY_VALUE(art_unit) au,
                  MAX(CAST(rejection_103 AS INT64)) flag FROM f GROUP BY 1),
     pop AS (SELECT app_id, n, flag, CAST(REPLACE(dt,'-','') AS INT64) oa_dt
             FROM g WHERE SUBSTR(au,1,2)='21'),
     p AS (SELECT SUBSTR(application_number_formatted,3) an,
                  MAX(IF(kind_code='A1' AND publication_date>0,publication_date,NULL)) a1_date,
                  MAX(IF(kind_code='A1',ARRAY_LENGTH(parent),NULL)) np
           FROM `patents-public-data.patents.publications_202511` WHERE country_code='US' AND application_number_formatted!=''
           GROUP BY 1)
SELECT COUNT(*) all_apps, ROUND(AVG(pop.flag)*100,2) all_rate,
  COUNTIF(pop.n=1) keep_single, ROUND(AVG(IF(pop.n=1,pop.flag,NULL))*100,2) rate_single,
  COUNTIF(pop.n>1) lost_double, ROUND(AVG(IF(pop.n>1,pop.flag,NULL))*100,2) rate_double,
  COUNTIF(p.a1_date IS NOT NULL AND p.a1_date<pop.oa_dt) keep_a1,
  ROUND(AVG(IF(p.a1_date IS NOT NULL AND p.a1_date<pop.oa_dt,pop.flag,NULL))*100,2) rate_a1,
  COUNTIF(p.np=0) keep_orig, ROUND(AVG(IF(p.np=0,pop.flag,NULL))*100,2) rate_orig,
  COUNTIF(p.np>0) lost_cont, ROUND(AVG(IF(p.np>0,pop.flag,NULL))*100,2) rate_cont
FROM pop LEFT JOIN p ON p.an=pop.app_id;

-- ЗАМЕЧАНИЕ О ДЕФЕКТЕ: здесь стоит ANY_VALUE(art_unit) — недетерминированно.
-- Даёт расхождение в 6 заявок из 41 285 против точного счёта. На итоговую
-- популяцию не влияет (все заявки с разными art_unit имеют n>1 и отсеиваются
-- критерием 3), но повторять этот приём в материализации нельзя.

-- Ряд ПЕРВЫХ действий помесячно и однозначность понятия «первое».
-- Дало: среднее 2015 по 21xx = 2 354, медиана 2 360 (выброса нет);
--       порог 0,75*среднего = 1765 — служил диагностикой, но механически
--       границу 2016-12 не производит ни в одном чтении (Manifest §9);
--       строк на дате первого действия: 1 -> 2 150 352, 2 -> 37 687 (1,7%),
--       трёх не бывает. Дата первого действия ОДНОЗНАЧНА без тай-брейкера.
-- Цена: 200 МБ.
-- --maximum_bytes_billed=200000000

WITH m AS (SELECT app_id, MIN(mail_dt) d FROM `patents-public-data.uspto_oce_office_actions.office_actions` GROUP BY 1),
     f AS (SELECT o.app_id, o.mail_dt, o.art_unit FROM `patents-public-data.uspto_oce_office_actions.office_actions` o
           JOIN m ON o.app_id=m.app_id AND o.mail_dt=m.d)
SELECT SUBSTR(mail_dt,1,7) ym,
       COUNT(DISTINCT IF(SUBSTR(art_unit,1,2)='21', app_id, NULL)) first21,
       COUNT(DISTINCT app_id) firstall
FROM f WHERE mail_dt>='2012-01' GROUP BY 1 ORDER BY 1;

-- кратность строк на дате первого действия
WITH m AS (SELECT app_id, MIN(mail_dt) d FROM `patents-public-data.uspto_oce_office_actions.office_actions` GROUP BY 1),
     f AS (SELECT o.app_id FROM `patents-public-data.uspto_oce_office_actions.office_actions` o JOIN m ON o.app_id=m.app_id AND o.mail_dt=m.d)
SELECT rows_on_first_date, COUNT(*) apps FROM (
  SELECT app_id, COUNT(*) rows_on_first_date FROM f GROUP BY 1)
GROUP BY 1 ORDER BY 1;

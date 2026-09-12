-- Форма таблицы метки: значения document_cd, значения rejection_103,
-- кратность действий на заявку, границы mail_dt.
-- Дало: document_cd только CTNF 2 961 350 / CTFR 1 423 182 — «первого действия»
--       как поля НЕ существует, его надо выводить через MIN(mail_dt);
--       rejection_103 = 1: 3 471 340, = 0: 913 192, NULL нет (Manifest §10);
--       действий на заявку: 1 -> 1 059 193, 2 -> 602 447, … 22 -> 1;
--       mail_dt 2001-01-01 … 2017-07-11 — ГРАНИЦА ИСТОЧНИКА МЕТКИ (Manifest §7).
-- Все три суммы сходятся с числом строк таблицы 4 384 532.
-- Цена: 25 МиБ + 12,5 МиБ + 42 МиБ + 60 МиБ.
-- --maximum_bytes_billed=60000000

SELECT document_cd, COUNT(*) c FROM `patents-public-data.uspto_oce_office_actions.office_actions` GROUP BY 1 ORDER BY c DESC;

SELECT rejection_103, COUNT(*) c FROM `patents-public-data.uspto_oce_office_actions.office_actions` GROUP BY 1 ORDER BY c DESC;

SELECT n, COUNT(*) apps FROM (
  SELECT app_id, COUNT(*) n FROM `patents-public-data.uspto_oce_office_actions.office_actions` GROUP BY 1) GROUP BY 1 ORDER BY 1;

SELECT MIN(mail_dt) min_dt, MAX(mail_dt) max_dt, COUNT(*) c FROM `patents-public-data.uspto_oce_office_actions.office_actions`;

SELECT LENGTH(app_id) len, COUNT(*) n_rows, COUNT(DISTINCT app_id) n_apps
FROM `patents-public-data.uspto_oce_office_actions.office_actions` GROUP BY 1 ORDER BY 1;   -- все 4 384 532 строки длиной ровно 8

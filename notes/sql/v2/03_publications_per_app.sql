-- Кратность: сколько публикаций приходится на одну заявку (шаг 8 требует
-- проверить, а не предположить 1:1).
-- Дало: 1 -> 10 940 937 | 2 -> 5 511 974 | 3 -> 12 346 | 4 -> 119 | 5 -> 5
-- Всего заявок 16 465 381 на 22 002 424 строки; без application_number — 2 строки.
-- Набор kind_code на заявку дал 881 466 заявок B1-only, то есть выданных
-- без предгрантовой публикации: у них нет текста как подан. Manifest §8.
-- Цена: 3,29 ГиБ / 4,11 ГиБ.
-- --maximum_bytes_billed=4000000000

SELECT rows_per_app, COUNT(*) n_apps FROM (
  SELECT application_number, COUNT(*) rows_per_app
  FROM `patents-public-data.patents.publications`
  WHERE country_code='US' AND application_number IS NOT NULL AND application_number!=''
  GROUP BY 1) GROUP BY 1 ORDER BY 1;

SELECT kinds, COUNT(*) n FROM (
  SELECT application_number, STRING_AGG(DISTINCT kind_code ORDER BY kind_code) kinds
  FROM `patents-public-data.patents.publications` WHERE country_code='US' AND application_number IS NOT NULL
  GROUP BY 1) GROUP BY 1 ORDER BY n DESC LIMIT 25;

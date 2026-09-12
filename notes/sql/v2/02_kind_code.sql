-- Какие kind_code существуют у US-публикаций и что означает application_kind.
-- Дало: A1 8 480 938 | A 6 148 989 | B2 5 437 558 | B1 950 585 | S1 686 655 …
-- Установило ловушку: kind_code 'A' (6,1 млн) в годах подачи 2013-2018 не
-- встречается ни разу, поэтому фильтр LIKE 'A%' затянул бы легаси-выдачи.
-- Manifest §9, критерий 5 и §"Воронка".
-- Цена: 1,17 ГиБ; вариант с application_kind — 1,65 ГиБ.
-- --maximum_bytes_billed=1400000000

SELECT kind_code, COUNT(*) c
FROM `patents-public-data.patents.publications`
WHERE country_code='US'
GROUP BY 1 ORDER BY c DESC;

SELECT kind_code, application_kind, COUNT(*) c
FROM `patents-public-data.patents.publications`
WHERE country_code='US'
GROUP BY 1,2 ORDER BY c DESC LIMIT 25;

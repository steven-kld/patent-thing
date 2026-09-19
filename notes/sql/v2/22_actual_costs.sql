-- ШАГ 15, издержки: ФАКТИЧЕСКИ оттарифицированные байты, а не оценка.
-- Дало по дням:
--   2026-09-05   4 задания   0,0000 ТиБ   $0,00
--   2026-09-08   3           0,0003       $0,00
--   2026-09-09   6           0,0034       $0,02
--   2026-09-10  13           0,0352       $0,22
--   2026-09-12  72           0,0444       $0,28
--   2026-09-19  12           1,3353       $8,35
--   итого                    1,4186 ТиБ   $8,87 брутто
-- Весь объём укладывается в один календарный месяц: 1 ТиБ бесплатен,
-- к оплате около 0,42 ТиБ ≈ $2,62.
-- M1: издержки в статистический аппарат не входят. Шаг 15 требует их
-- пересчитать на фактических строках — это он и есть.
-- Цена: минимум INFORMATION_SCHEMA, 10 МиБ.
-- --maximum_bytes_billed=200000000

SELECT DATE(creation_time) d, COUNT(*) jobs,
       ROUND(SUM(total_bytes_billed)/POW(1024,4),4) tib,
       ROUND(SUM(total_bytes_billed)/POW(1024,4)*6.25,2) usd
FROM `region-us`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
WHERE creation_time > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
  AND job_type='QUERY'
GROUP BY 1 ORDER BY 1;

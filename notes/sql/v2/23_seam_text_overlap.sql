-- ШАГ 18. Утечка по конструкции через шов 2016-06-30: совпадение текста.
-- Канал, который НЕ закрыт критериями популяции: разные app_id с одинаковым
-- текстом по разные стороны шва. Критерий 4 (parent пуст) снимает продолжения,
-- но братские заявки одного заявителя parent не объявляют и остаются.
--
-- Дало (A: точное совпадение title+abstract, B: совпадение только title):
--   ключ             различных хешей   дублей   через шов   строк через шов
--   title+abstract            30 900       64          12                26
--   title only                29 746      596         188               902
--
-- Уточнение по 188 группам title-only:
--   12  реферат идентичен        = те же 12 групп, что в A (сходимость)
--   10  реферат иной, длины в пределах 5%
--  166  реферат иной, длины расходятся; 42 группы больше 5 строк, макс 37
--       — типовые заголовки («microcomputer», «control method and control device»)
--
-- Метка 2016H2 в таблице NULL по построению (см. 16_materialize_cohort.sql),
-- поэтому утечке метки через шов протекать нечем. Проверяются только признаки:
-- O6 относит проверки утечки без y ящика к не-вскрытиям.
-- Цена: 2 запуска по ~24 МиБ. --maximum_bytes_billed=100000000

-- A. сводка по двум ключам
WITH n AS (
  SELECT period,
         LOWER(REGEXP_REPLACE(IFNULL(title,''),    r'\s+', ' ')) AS t,
         LOWER(REGEXP_REPLACE(IFNULL(abstract,''), r'\s+', ' ')) AS a
  FROM `<свой проект>.patent_v2.cohort`
),
ta AS (
  SELECT TO_HEX(MD5(CONCAT(t,' ||| ',a))) h,
         COUNTIF(period='2016H2') post, COUNTIF(period!='2016H2') pre, COUNT(*) c
  FROM n GROUP BY 1
),
ti AS (
  SELECT TO_HEX(MD5(t)) h,
         COUNTIF(period='2016H2') post, COUNTIF(period!='2016H2') pre, COUNT(*) c
  FROM n WHERE t != '' GROUP BY 1
)
SELECT 'title+abstract' AS key, COUNT(*) distinct_h, COUNTIF(c>1) dup_h,
       COUNTIF(pre>0 AND post>0) seam_h,
       IFNULL(SUM(IF(pre>0 AND post>0, c, 0)),0) seam_rows
FROM ta
UNION ALL
SELECT 'title only', COUNT(*), COUNTIF(c>1), COUNTIF(pre>0 AND post>0),
       IFNULL(SUM(IF(pre>0 AND post>0, c, 0)),0)
FROM ti;

-- B. разбор групп title-only, пересекающих шов
-- (запускался отдельно; псевдонимы не groups/rows — зарезервированы)
-- WITH n AS (...то же...),
-- g AS (SELECT TO_HEX(MD5(t)) h, COUNT(*) c,
--              COUNTIF(period='2016H2') post, COUNTIF(period!='2016H2') pre,
--              COUNT(DISTINCT TO_HEX(MD5(a))) distinct_abs,
--              MIN(LENGTH(a)) mn, MAX(LENGTH(a)) mx
--       FROM n WHERE t != '' GROUP BY 1 HAVING post>0 AND pre>0)
-- SELECT COUNT(*) n_groups, SUM(c) n_rows,
--        COUNTIF(distinct_abs=1) g_abs_identical,
--        COUNTIF(distinct_abs>1 AND mn>0 AND mx<=mn*1.05) g_abs_len_5pct,
--        COUNTIF(distinct_abs>1 AND (mn=0 OR mx>mn*1.05)) g_abs_differs,
--        COUNTIF(c>5) g_large, MAX(c) max_group
-- FROM g;

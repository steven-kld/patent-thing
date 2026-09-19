-- Проверка полноты текстов в материализованной таблице.
-- Возникла из вопроса «почему тексты такие короткие» — оказалось, короткими
-- они выглядят в превью консоли BigQuery, которая режет длинные строки.
-- Дало (символов):
--   поле          NULL   мин      среднее   медиана   макс
--   title            0     3          63        58        500
--   abstract         0    27         708       722      8 710
--   claims           0    26       7 862     7 061    222 492
--   description      0  2 650      58 235    46 546  8 307 085
-- Медианное описание ~46,5 тыс. символов, около девяти тысяч слов.
-- Максимум 8,31 МБ — ниже потолка Google в 9 МБ, что сходится с нулём
-- обрезанных (description_truncated).
-- Выборочная проверка одной строки: текст начинается разделом BACKGROUND
-- и заканчивается стандартной заключительной фразой — обрыва нет.
-- «nulls» — зарезервированное слово, в псевдонимах не использовать.
-- Цена: ~1,8 ГБ ≈ $0,011.
-- --maximum_bytes_billed=3000000000

SELECT 'description' AS fld, COUNTIF(description IS NULL) n_null,
       MIN(LENGTH(description)) len_min,
       CAST(AVG(LENGTH(description)) AS INT64) len_avg,
       APPROX_QUANTILES(LENGTH(description),2)[OFFSET(1)] len_med,
       MAX(LENGTH(description)) len_max
FROM `<свой проект>.patent_v2.cohort`;
-- (аналогично для title, abstract, claims через UNION ALL)

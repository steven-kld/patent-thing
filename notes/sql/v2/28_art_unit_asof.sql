-- ПЕРЕПРОВЕРКА as-of для art_unit (сессия 2026-09-20). Стадия 4, до заморозки.
-- Вопрос: было ли подразделение известно до даты первого действия.
--
-- ИСТОЧНИКА С ДАТОЙ ПРИСВОЕНИЯ НЕТ. Проверены все, где есть подразделение:
--   uspto_oce_pair.event_codes       справочник кодов, не история транзакций
--   uspto_oce_pair.application_data  examiner_art_unit — снимок без даты
--   uspto_peds.applications          groupArtUnitNumber — снимок без даты
-- Значит вопрос из этих данных не отвечается и может быть только объявлен.
--
-- Измерено вместо него — УСТОЙЧИВОСТЬ поля. Дало:
--   сошлось по app_id                28 467 из 30 977   91,90% покрытия
--   подразделение совпало полностью  23 509 / 28 467    82,58%
--                      разошлось                        17,42%
--   совпало по первым трём цифрам    26 701             93,80%
--   PAIR говорит «не 2100»              322              1,13%
--
-- Вывод автора: поле office_actions.art_unit — «art unit performing the
-- examination», то есть исход маршрутизации, а не то, что было известно
-- до действия. art_unit отвергнут и как признак, и как фильтр.
-- Universe §12 подтверждён, расхождение не потребовалось.
--
-- Цена: 149 МиБ ≈ $0,001.  --maximum_bytes_billed=200000000

WITH c AS (
  SELECT app_id, art_unit, period FROM `<свой проект>.patent_v2.cohort`
),
p AS (
  SELECT application_number AS an, examiner_art_unit AS au_pair
  FROM `patents-public-data.uspto_oce_pair.application_data`
  WHERE examiner_art_unit IS NOT NULL AND examiner_art_unit != ''
)
SELECT
  COUNT(*)                                                  n_joined,
  COUNTIF(c.art_unit = p.au_pair)                           same_full,
  COUNTIF(SUBSTR(c.art_unit,1,3) = SUBSTR(p.au_pair,1,3))   same_prefix3,
  COUNTIF(SUBSTR(p.au_pair,1,2) != '21')                    pair_outside_2100
FROM c JOIN p ON p.an = c.app_id;

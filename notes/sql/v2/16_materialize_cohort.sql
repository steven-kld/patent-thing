-- ШАГ 13. Материализация когорты. ЭТО ЗАПРОС, СОЗДАВШИЙ ТАБЛИЦУ.
-- Результат: <свой проект>.patent_v2.cohort — 30 977 строк, 1,94 ГиБ.
-- Числа по окнам совпали с замороженным Manifest до строки:
--   2015H1 9 524 · 2015H2 6 523 · 2016H1 7 513 · 2016H2 7 417
-- Метка проставлена ТОЛЬКО для train+valid (dt < 2016-07-01); у теста NULL:
-- решение автора, чтобы метку подтверждающего окна нельзя было посмотреть
-- раньше вскрытия.
-- Цена: 1,445 ТиБ = $8,21 (при нетронутом месячном лимите к оплате ~$1,96).
-- --maximum_bytes_billed=1600000000000
--
-- ДВЕ ЛОВУШКИ, обе поймались до запуска:
--   MIN(art_unit) вместо ANY_VALUE — ANY_VALUE недетерминирован (шаг 13);
--   ORDER BY x.text перед LIMIT 1 — без него выбор элемента массива произволен.
-- Постфактум обе оказались безвредны: n_en_* по нулям, выбирать было не из чего.
-- Но проверяется это только после материализации, а чинится до.
--
-- «window» и «rows» — зарезервированные слова BigQuery, псевдонимы не из них.

CREATE OR REPLACE TABLE `<свой проект>.patent_v2.cohort` AS
WITH m AS (SELECT app_id, MIN(mail_dt) d FROM `patents-public-data.uspto_oce_office_actions.office_actions` GROUP BY 1),
     f AS (SELECT o.app_id, o.mail_dt, o.art_unit, o.rejection_103 FROM `patents-public-data.uspto_oce_office_actions.office_actions` o
           JOIN m ON o.app_id=m.app_id AND o.mail_dt=m.d
           WHERE m.d BETWEEN '2015-01-01' AND '2016-12-31'),
     g AS (SELECT app_id, COUNT(*) n, MIN(mail_dt) dt, MIN(art_unit) au,
                  MAX(CAST(rejection_103 AS INT64)) flag FROM f GROUP BY 1),
     pop AS (SELECT app_id, dt, au, flag, CAST(REPLACE(dt,'-','') AS INT64) oa_dt
             FROM g WHERE n=1 AND SUBSTR(au,1,2)='21')
SELECT
  pop.app_id, p.publication_number, pop.dt AS first_action_date, pop.au AS art_unit,
  CASE WHEN pop.dt<'2015-07-01' THEN '2015H1' WHEN pop.dt<'2016-01-01' THEN '2015H2'
       WHEN pop.dt<'2016-07-01' THEN '2016H1' ELSE '2016H2' END AS period,
  IF(pop.dt < '2016-07-01', pop.flag, NULL) AS rejection_103,
  (SELECT x.text FROM UNNEST(p.title_localized)       x WHERE x.language='en' ORDER BY x.text LIMIT 1) AS title,
  (SELECT x.text FROM UNNEST(p.abstract_localized)    x WHERE x.language='en' ORDER BY x.text LIMIT 1) AS abstract,
  (SELECT x.text FROM UNNEST(p.claims_localized)      x WHERE x.language='en' ORDER BY x.text LIMIT 1) AS claims,
  (SELECT x.text FROM UNNEST(p.description_localized) x WHERE x.language='en' ORDER BY x.text LIMIT 1) AS description,
  (SELECT LOGICAL_OR(x.truncated) FROM UNNEST(p.claims_localized)      x WHERE x.language='en') AS claims_truncated,
  (SELECT LOGICAL_OR(x.truncated) FROM UNNEST(p.description_localized) x WHERE x.language='en') AS description_truncated,
  (SELECT COUNT(*) FROM UNNEST(p.title_localized)       x WHERE x.language='en') AS n_en_title,
  (SELECT COUNT(*) FROM UNNEST(p.description_localized) x WHERE x.language='en') AS n_en_description
FROM pop
JOIN `patents-public-data.patents.publications_202511` p ON SUBSTR(p.application_number_formatted,3)=pop.app_id
WHERE p.country_code='US' AND p.kind_code='A1' AND p.publication_date>0
  AND p.publication_date<pop.oa_dt AND ARRAY_LENGTH(p.parent)=0;

-- Формат ключа с обеих сторон и пригодность склейки.
-- Дало: app_id — ровно 8 символов у всех 4 384 532 строк, вариантов нет;
--       application_number в DOCDB-формате переменной длины ('US-69886910-A',
--       'US-202117153249-A') — для склейки НЕПРИГОДЕН;
--       application_number_formatted = 'US' + 8 цифр ('US12698869') — пригоден;
--       у ~3,9 млн US-публикаций это поле пустое.
-- Отсюда ключ Manifest §8: SUBSTR(application_number_formatted,3) = app_id.
-- Цена: 6,6 ГиБ (оба столбца сразу — дешевле, чем угадывать по одному).
-- --maximum_bytes_billed=7500000000

SELECT LENGTH(application_number) len_docdb,
       LENGTH(application_number_formatted) len_fmt,
       COUNT(*) c,
       ANY_VALUE(application_number) example_docdb,
       ANY_VALUE(application_number_formatted) example_fmt
FROM `patents-public-data.patents.publications` WHERE country_code='US'
GROUP BY 1,2 ORDER BY c DESC LIMIT 20;

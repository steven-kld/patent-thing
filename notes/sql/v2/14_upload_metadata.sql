-- Границы покрытия ТЕКСТОВ РЕШЕНИЙ (не текстов заявок).
-- Дало: 2020-11-02 … 2026-01-04, 262 файла, 4 736 400 действий.
-- С окном метки (до 2017-07-11) НЕ ПЕРЕСЕКАЕТСЯ НИ ОДНИМ ДНЁМ.
-- Отсюда Manifest §11: прочитать, что написал эксперт, и сверить с флагом —
-- средствами BigQuery нельзя. Это основание принятия варианта 3.
-- ЛОВУШКА: даты в этой таблице в формате MM-DD-YYYY. MIN/MAX по строке дают
-- лексикографический мусор ('01-01-2024' как минимум, '12-31-2023' как максимум).
-- Обязателен PARSE_DATE.
-- Цена: 10 МиБ (минимум INFORMATION_SCHEMA не при чём — таблица 57 КиБ,
-- но минимум тарификации запроса всё равно применяется).
-- --maximum_bytes_billed=11000000

SELECT MIN(SAFE.PARSE_DATE('%m-%d-%Y', from_date)) min_from,
       MAX(SAFE.PARSE_DATE('%m-%d-%Y', to_date)) max_to,
       MIN(SAFE_CAST(SUBSTR(first_office_action_submission_date,1,10) AS DATE)) first_oa,
       MAX(SAFE_CAST(SUBSTR(last_office_action_submission_date,1,10) AS DATE)) last_oa,
       SUM(office_action_count) total_oa, COUNT(*) files,
       COUNTIF(SAFE.PARSE_DATE('%m-%d-%Y', from_date) IS NULL) unparsed
FROM `patents-public-data.uspto_office_actions_text.office_actions_upload_metadata`;

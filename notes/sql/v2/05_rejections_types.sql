-- Вторая таблица OCE: поклеймовые основания отказа.
-- Дало: action_type '103' с subtype 'a' — 3 001 862, с NULL — 479 613;
--       в таблице есть и не-отказы: objected 1 177 245, cancelled 611 066,
--       allowed 278 348. Отсюда вывод Manifest §10: отрицательный класс
--       rejection_103=0 НЕ означает «заявка принята», и второй источник
--       для «принята» не подключается.
-- Цена: 98 МиБ.
-- --maximum_bytes_billed=125000000

SELECT action_type, action_subtype, COUNT(*) c
FROM `patents-public-data.uspto_oce_office_actions.rejections` GROUP BY 1,2 ORDER BY c DESC LIMIT 20;

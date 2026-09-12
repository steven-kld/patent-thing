-- ШАГ 11. Сверка rejection_103 против поклеймовой таблицы rejections.
-- КРИТЕРИЙ ПРИЕМЛЕМОСТИ БЫЛ ОБЪЯВЛЕН ДО ЗАПУСКА: дельта A+B выше 1% ->
-- искать способ устранить, иначе принять флаг определением исхода.
-- Дало: согласие 13 495 + 36 230; расхождение A (флаг=1, строки нет) = 36
--       (0,0723%); расхождение B (флаг=0, строка есть) = 0 ровно.
--       Итого 49 761 — сходится с популяцией.
-- ОГОВОРКА: B=0 ровно есть свидетельство того, что таблицы НЕ независимы —
-- одна выведена из другой тем же парсером. Проверка подтвердила внутреннюю
-- согласованность и НЕ измерила точность метки. Потолок НЕ получен.
-- Цена: 530 МиБ.
-- --maximum_bytes_billed=700000000

WITH m AS (SELECT app_id, MIN(mail_dt) d FROM `patents-public-data.uspto_oce_office_actions.office_actions` GROUP BY 1),
     f AS (SELECT o.app_id, o.ifw_number, o.rejection_103, o.mail_dt, o.art_unit
           FROM `patents-public-data.uspto_oce_office_actions.office_actions` o JOIN m ON o.app_id=m.app_id AND o.mail_dt=m.d
           WHERE m.d BETWEEN '2015-01-01' AND '2016-12-31'),
     g AS (SELECT app_id, COUNT(*) n FROM f GROUP BY 1),
     pop AS (SELECT f.* FROM f JOIN g USING(app_id)
             WHERE g.n=1 AND SUBSTR(f.art_unit,1,2)='21'),
     rj AS (SELECT DISTINCT app_id, ifw_number FROM `patents-public-data.uspto_oce_office_actions.rejections` WHERE action_type='103')
SELECT pop.rejection_103 AS flag,
       IF(rj.app_id IS NULL, 0, 1) AS in_rejections,
       COUNT(*) c
FROM pop LEFT JOIN rj ON rj.app_id=pop.app_id AND rj.ifw_number=pop.ifw_number
GROUP BY 1,2 ORDER BY 1,2;

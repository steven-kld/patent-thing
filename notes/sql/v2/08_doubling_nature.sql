-- Природа задвоения: артефакт загрузки или поведение экспертизы?
-- Дало:
--   A) по ВСЕМУ источнику: 2015-10 38,2% | 2015-11 78,5% | 2015-12 16,2%
--      | 2016-01..03 ~2,0-2,6% | все прочие месяцы окна 0,0%
--   B) art units поражены без разбора: 2872, 2837, 2842, 3731, 3745, 2665 …
--      все на уровне 20-30%. 2100 не выделен: 26,5% против 22,9% по источнику
--   C) пара = два ifw_number при ПОЛНОМ совпадении административных полей.
--      Различий signature_type / header_missing / fp_missing / closing_missing
--      / allowed_claims — НОЛЬ. uspc_subclass — 395, uspc_class — 104 из 37 499
-- Вывод: дубликат выгрузки, не два решения эксперта. Manifest §9, критерий 3.
-- Гипотеза «текст больше лимита» этим же и опровергнута: таблица текста не
-- содержит (110 байт на строку), а размер текста не зависит от месяца.
-- Цена: ~400 МБ на запрос.
-- --maximum_bytes_billed=400000000

-- A. задвоение помесячно, ВСЕ art units. Фильтра n=1 здесь быть не должно:
--    именно доля n>1 и есть измеряемая величина.
WITH m AS (SELECT app_id, MIN(mail_dt) d FROM `patents-public-data.uspto_oce_office_actions.office_actions` GROUP BY 1),
     f AS (SELECT o.app_id, o.mail_dt FROM `patents-public-data.uspto_oce_office_actions.office_actions` o
           JOIN m ON o.app_id=m.app_id AND o.mail_dt=m.d
           WHERE m.d BETWEEN '2015-01-01' AND '2016-12-31'),
     g AS (SELECT app_id, COUNT(*) n, MIN(mail_dt) dt FROM f GROUP BY 1)
SELECT SUBSTR(dt,1,7) ym, COUNT(*) apps, COUNTIF(n>1) dbl,
       ROUND(100*COUNTIF(n>1)/COUNT(*),1) pct
FROM g GROUP BY 1 ORDER BY 1;

-- A2. то же, но только 21xx: 2015-10 1 047 | 2015-11 1 699 | 2015-12 404
--     | 2016-01 49 | 2016-02 65 | 2016-03 55; сумма 3 319
WITH m AS (SELECT app_id, MIN(mail_dt) d FROM `patents-public-data.uspto_oce_office_actions.office_actions` GROUP BY 1),
     f AS (SELECT o.app_id, o.mail_dt, o.art_unit FROM `patents-public-data.uspto_oce_office_actions.office_actions` o
           JOIN m ON o.app_id=m.app_id AND o.mail_dt=m.d
           WHERE m.d BETWEEN '2015-01-01' AND '2016-12-31'),
     g AS (SELECT app_id, COUNT(*) n, MIN(mail_dt) dt,
                  COUNTIF(SUBSTR(art_unit,1,2)='21') n21 FROM f GROUP BY 1)
SELECT SUBSTR(dt,1,7) ym, COUNTIF(n21>0) total21, COUNTIF(n21>0 AND n=2) dbl21,
       ROUND(100*COUNTIF(n21>0 AND n=2)/COUNTIF(n21>0),1) pct
FROM g GROUP BY 1 ORDER BY 1;

-- B. в поражённые месяцы: какие art units задеты
WITH m AS (SELECT app_id, MIN(mail_dt) d FROM `patents-public-data.uspto_oce_office_actions.office_actions` GROUP BY 1),
     f AS (SELECT o.app_id, o.art_unit FROM `patents-public-data.uspto_oce_office_actions.office_actions` o
           JOIN m ON o.app_id=m.app_id AND o.mail_dt=m.d
           WHERE m.d BETWEEN '2015-10-01' AND '2016-03-31'),
     g AS (SELECT app_id, COUNT(*) n, ANY_VALUE(art_unit) au FROM f GROUP BY 1)
SELECT au, COUNT(*) apps, COUNTIF(n>1) dbl, ROUND(100*COUNTIF(n>1)/COUNT(*),1) pct
FROM g GROUP BY 1 HAVING dbl>0 ORDER BY dbl DESC LIMIT 15;

-- C. чем вообще различаются строки пары при одинаковом art_unit
WITH m AS (SELECT app_id, MIN(mail_dt) d FROM `patents-public-data.uspto_oce_office_actions.office_actions` GROUP BY 1),
     f AS (SELECT o.* FROM `patents-public-data.uspto_oce_office_actions.office_actions` o JOIN m ON o.app_id=m.app_id AND o.mail_dt=m.d
           WHERE m.d BETWEEN '2015-01-01' AND '2016-12-31'),
     g AS (SELECT app_id, COUNT(*) n,
             COUNT(DISTINCT art_unit) au, COUNT(DISTINCT document_cd) dc,
             COUNT(DISTINCT ifw_number) ifw, COUNT(DISTINCT uspc_class) ucl,
             COUNT(DISTINCT uspc_subclass) usub, COUNT(DISTINCT signature_type) sig,
             COUNT(DISTINCT header_missing) hm, COUNT(DISTINCT fp_missing) fpm,
             COUNT(DISTINCT closing_missing) cm, COUNT(DISTINCT allowed_claims) ac
           FROM f GROUP BY 1)
SELECT COUNT(*) pairs, COUNTIF(ifw>1) diff_ifw_number,
       COUNTIF(ucl>1) diff_uspc_class, COUNTIF(usub>1) diff_uspc_subclass,
       COUNTIF(sig>1) diff_signature_type, COUNTIF(hm>1) diff_header_missing,
       COUNTIF(fpm>1) diff_fp_missing, COUNTIF(cm>1) diff_closing_missing,
       COUNTIF(ac>1) diff_allowed_claims
FROM g WHERE n=2 AND au=1 AND dc=1;

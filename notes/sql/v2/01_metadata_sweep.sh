#!/bin/bash
# Перебор метаданных всех датасетов patents-public-data.
# Дал: 22 датасета, 1 041 таблица, 10 604 поля (Manifest §7 «Происхождение»).
# Установил, что поля про §103 существуют ровно в трёх таблицах.
# Цена: 32 запроса по минимуму INFORMATION_SCHEMA = 10 МиБ каждый, ~320 МиБ.
# bq ls и bq show — метаданные, 0 байт, бесплатно.
MP=<свой проект>   # задания создаются в СВОЁМ проекте, читают из публичного
P=patents-public-data

for d in $(bq --project_id=$P ls | tail -n +3 | awk '{print $1}'); do
  bq --project_id=$MP --quiet --format=csv query --use_legacy_sql=false \
     --max_rows=1000000 --maximum_bytes_billed=10485760 \
     "SELECT '$d' AS ds, table_name, field_path, data_type, IFNULL(description,'') AS descr
      FROM \`$P.$d.INFORMATION_SCHEMA.COLUMN_FIELD_PATHS\`" | tail -n +2 >> columns.csv
done
# ВНИМАНИЕ: --max_rows ставится ПОСЛЕ подкоманды query. До неё bq падает
# с 'Unknown command line flag'. По умолчанию отдаётся 100 строк — усечение молчаливое.

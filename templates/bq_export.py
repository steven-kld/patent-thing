"""Экспорт результата SQL-запроса BigQuery в parquet — с обязательным предохранителем.

Предохранитель `--max-bytes` обязателен: запрос, которому нужно прочитать больше,
BigQuery отклоняет до чтения, и платить не за что. Без `--run` делается только
dry run: печатается, сколько байт запрос прочитает, ничего не выгружается.

Сверка (необязательно): `--key` — столбец-ключ; печатаются число строк, число
уникальных ключей и MD5 отсортированного списка ключей через запятую (тот же
отпечаток, что `TO_HEX(MD5(STRING_AGG(key, ',' ORDER BY key)))` в BigQuery).
`--expect-rows` / `--expect-md5` — сверить с ранее объявленным; не сошлось — exit 1.

Подтверждающий ящик: метки ящика сюда не выгружать — отдельный запрос без
столбца метки или с WHERE по окну (см. CLAUDE.md, «Подтверждающий ящик»).

Примеры:
    python3 templates/bq_export.py --sql q.sql --max-bytes 5000000000
    python3 templates/bq_export.py --sql q.sql --max-bytes 5000000000 --run \
        --out ~/exp-work/data/texts.parquet --key app_id --expect-rows 30977

Требует google-cloud-bigquery, google-cloud-bigquery-storage, pyarrow.
Тариф on-demand сверять с cloud.google.com/bigquery/pricing ($6,25/ТиБ на
2026-10-04, первый ТиБ в месяц бесплатно). WHERE объём не уменьшает:
оплачиваются прочитанные столбцы, если таблица не секционирована.
"""
import argparse
import hashlib
import os
import sys

import pyarrow.parquet as pq
from google.cloud import bigquery


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sql", required=True, help="файл с запросом (хранится в репозитории)")
    ap.add_argument("--max-bytes", type=int, required=True, help="предохранитель, байт")
    ap.add_argument("--run", action="store_true", help="выполнить; без флага — только dry run")
    ap.add_argument("--out", help="parquet для результата")
    ap.add_argument("--key")
    ap.add_argument("--expect-rows", type=int)
    ap.add_argument("--expect-md5")
    a = ap.parse_args()

    sql = open(a.sql).read()
    client = bigquery.Client()
    dry = client.query(sql, job_config=bigquery.QueryJobConfig(
        dry_run=True, use_query_cache=False, maximum_bytes_billed=a.max_bytes))
    need = dry.total_bytes_processed
    print(f"dry run: прочитает {need} байт ({need / 2**30:.3f} ГиБ); предохранитель {a.max_bytes}")
    if need > a.max_bytes:
        sys.exit("ОТКАЗ: запрос дороже предохранителя")
    if not a.run:
        return
    if not a.out:
        sys.exit("ОТКАЗ: --run без --out")

    job = client.query(sql, job_config=bigquery.QueryJobConfig(
        maximum_bytes_billed=a.max_bytes, use_query_cache=False))
    tbl = job.result().to_arrow()
    print(f"job {job.job_id}: processed {job.total_bytes_processed}, billed {job.total_bytes_billed}")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    pq.write_table(tbl, a.out)
    digest = hashlib.sha256(open(a.out, "rb").read()).hexdigest()
    print(f"{a.out}: строк {tbl.num_rows}, sha256 {digest}")

    if a.key:
        keys = [str(k) for k in tbl.column(a.key).to_pylist()]
        md5 = hashlib.md5(",".join(sorted(keys)).encode()).hexdigest()
        print(f"ключ {a.key}: строк {len(keys)}, уникальных {len(set(keys))}, MD5 {md5}")
        bad = (a.expect_rows is not None and len(keys) != a.expect_rows) or \
              (a.expect_md5 is not None and md5 != a.expect_md5)
        if bad:
            sys.exit("СВЕРКА: НЕ СОВПАЛО")
        if a.expect_rows is not None or a.expect_md5:
            print("СВЕРКА: совпало")


if __name__ == "__main__":
    main()

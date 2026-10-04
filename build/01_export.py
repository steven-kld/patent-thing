"""Стадия 6, шаг 1 плана: экспорт когорты из BigQuery в локальный кэш.

Два файла, метки отдельно от текстов (решение автора):
  texts.parquet    app_id, period, title, abstract, claims, description — вся
                   когорта, включая confirm_2016H2 (признаки ящика: не вскрытие,
                   но объявление по O2; решение автора «вся когорта разом»)
  labels.parquet   app_id, period, rejection_103 — только period != '2016H2'.
                   Метки ящика не выгружаются даже как NULL

Предохранитель: maximum_bytes_billed = 87 960 930 222 байт = $0,50 по тарифу
$6,25/ТиБ (решение автора). Самый дорогой запрос по dry run — 2 079 545 536.

Сверка с artifacts/universe.md §13: 30 977 строк, 30 977 уникальных app_id,
MD5 отсортированного списка app_id через запятую = 09934048a3fcb4a0a812c0bb0876b042
(та же формула, что notes/sql/v2/20_determinism_check.sql).
"""
import hashlib
import os
import sys

import pyarrow.parquet as pq
from google.cloud import bigquery

MAX_BYTES = 87_960_930_222
TABLE = "patent_v2.cohort"
OUT = os.path.expanduser("~/patent-work/data")

EXPECT_ROWS = 30_977
EXPECT_MD5 = "09934048a3fcb4a0a812c0bb0876b042"

Q_TEXTS = f"SELECT app_id, period, title, abstract, claims, description FROM `{TABLE}`"
Q_LABELS = f"SELECT app_id, period, rejection_103 FROM `{TABLE}` WHERE period != '2016H2'"


def run(client, sql):
    cfg = bigquery.QueryJobConfig(maximum_bytes_billed=MAX_BYTES, use_query_cache=False)
    job = client.query(sql, job_config=cfg)
    tbl = job.result().to_arrow()
    print(f"  job {job.job_id}: processed {job.total_bytes_processed}, billed {job.total_bytes_billed}")
    return tbl


def main():
    os.makedirs(OUT, exist_ok=True)
    client = bigquery.Client()

    texts = run(client, Q_TEXTS)
    pq.write_table(texts, f"{OUT}/texts.parquet")
    ids = texts.column("app_id").to_pylist()
    md5 = hashlib.md5(",".join(sorted(ids)).encode()).hexdigest()
    print(f"texts: строк {len(ids)}, уникальных {len(set(ids))}, MD5 {md5}")

    labels = run(client, Q_LABELS)
    pq.write_table(labels, f"{OUT}/labels.parquet")
    print(f"labels: строк {labels.num_rows}, периоды {sorted(set(labels.column('period').to_pylist()))}")

    ok = len(ids) == EXPECT_ROWS == len(set(ids)) and md5 == EXPECT_MD5
    print("СВЕРКА:", "совпало" if ok else "НЕ СОВПАЛО")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

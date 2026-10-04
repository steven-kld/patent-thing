#!/usr/bin/env python3
"""Оценщик величин подтверждающего вскрытия, эксперимент №1, редакция 2.

Заменяет tools/est_ev.py (заморозка Protocol №8), который остаётся на месте.
Причина — ревизия шага 26, дефект 1: прежний оценщик засчитывал выигрыш при
pred == y, то есть платил и за «§103 не будет — и не было». Решение автора
(2026-10-04): «угаданное это только 103 будет, потому что нам платят только за
это. ошибка при 103 будет (когда его нет) - это штраф. угадывание, что 103 не
будет - не имеет никакого смысла».

Вход: CSV с двумя колонками (заголовок обязателен, порядок любой)
    bet   1 — на строку поставлено («§103 будет»), 0 — пас
    y     настоящий исход, 0/1
Колонки pred нет: ставка сама и есть предсказание «§103 будет».
Строка с bet=0 в экономику не входит: пас стоит 0 (Proposal).

Экономика — замороженные константы Proposal:
    ставка, y = 1   +10 USD
    ставка, y = 0   -80 USD
    пас               0 USD

    EV = 10 * (ставки с y=1) - 80 * (ставки с y=0)     USD на ящик целиком

Интервал: бутстрап по отдельным ставкам (блок 1). Братские заявки (cos векторов
ta ≥ 0,95) в ставки не попадают по построению конвейера Build — пасуются;
зависимость ненайденных братьев остаётся допущением. Уровень 0,95 с одной
стороны: ci_low — 5-й процентиль, ci_high — 95-й; в Protocol та же граница
записана как двустороннее 0,90 (множитель 1,645).

Запуск:
    python3 tools/est_ev_v2.py <путь к csv>
Печатает JSON: EV.point, EV.ci_low, EV.ci_high, bets.point, accuracy.point.
"""
import csv
import json
import random
import sys

C_WIN, C_LOSS = 10.0, 80.0
ITERATIONS, SEED, LEVEL = 10000, 14, 0.95


def read_rows(path):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    need = {"bet", "y"}
    if not rows or not need <= set(rows[0]):
        sys.exit(f"ОТКАЗ: в {path} нужны колонки bet, y")
    return rows


def outcomes(rows):
    """Исходы сделанных ставок, в долларах: +10 при y=1, -80 при y=0. Пасы отброшены."""
    out = []
    for r in rows:
        if int(r["bet"]) != 1:
            continue
        out.append(C_WIN if int(r["y"]) == 1 else -C_LOSS)
    return out


def percentile(sorted_vals, q):
    """Линейная интерполяция между соседними порядковыми статистиками."""
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (pos - lo) * (sorted_vals[hi] - sorted_vals[lo])


def estimate(rows):
    out = outcomes(rows)
    n = len(out)
    point = sum(out)
    wins = sum(1 for x in out if x > 0)

    rnd = random.Random(SEED)
    boot = sorted(sum(rnd.choices(out, k=n)) for _ in range(ITERATIONS)) if n else []

    return {
        "EV.point": point,
        "EV.ci_low": percentile(boot, 1 - LEVEL) if n else 0.0,
        "EV.ci_high": percentile(boot, LEVEL) if n else 0.0,
        "bets.point": n,
        "accuracy.point": wins / n if n else 0.0,
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    print(json.dumps(estimate(read_rows(sys.argv[1])), ensure_ascii=False, indent=1))

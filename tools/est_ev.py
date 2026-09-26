#!/usr/bin/env python3
"""Оценщик величин подтверждающего вскрытия, эксперимент №1.

Замораживается хешем в Protocol ДО обучения (P4). Модели не знает: на вход
идут уже принятые решения и настоящие исходы, на выход — числа правила.

Вход: CSV с тремя колонками (заголовок обязателен, порядок любой)
    bet   1 — на строку поставлено, 0 — пас
    pred  предсказание модели, 0/1
    y     настоящий исход, 0/1
Строка с bet=0 в экономику не входит вовсе: пас стоит 0 (Proposal).

Экономика — замороженные константы Proposal:
    верная ставка   +10 USD      pred == y
    ошибочная       -80 USD      pred != y
    пас               0 USD

    EV = 10 * верные - 80 * ошибочные          USD на ящик целиком

Интервал: бутстрап по ОТДЕЛЬНЫМ ставкам (единица — ставка, блок 1, решение
автора). Перетасовывается с возвратом n исходов ставок, n фиксировано;
это та же модель, по которой посчитан interval_frontier в Lockbox, поэтому
числа справки о мощности и числа вскрытия сопоставимы. Уровень 0,95 с одной
стороны: ci_low — 5-й процентиль, ci_high — 95-й.

Зависимость исходов между братскими заявками в этой модели отсутствует по
построению: при положительной корреляции разброс занижен, а интервал уже
настоящего (допущение названо в Lockbox, step_19_power.assumption).

Запуск:
    python3 tools/est_ev.py <путь к csv>
Печатает JSON с ключами, которых ждёт Protocol после развёртки величин (P5):
EV.point, EV.ci_low, EV.ci_high, bets.point, accuracy.point.
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
    need = {"bet", "pred", "y"}
    if not rows or not need <= set(rows[0]):
        sys.exit(f"ОТКАЗ: в {path} нужны колонки bet, pred, y")
    return rows


def outcomes(rows):
    """Исходы сделанных ставок, в долларах: +10 либо -80. Пасы отброшены."""
    out = []
    for r in rows:
        if int(r["bet"]) != 1:
            continue
        out.append(C_WIN if int(r["pred"]) == int(r["y"]) else -C_LOSS)
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

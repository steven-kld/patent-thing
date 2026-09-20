#!/usr/bin/env python3
"""Проверка фильтра по art_unit ВНЕ ВЫБОРКИ, на реальных окнах.

Данные: 27_art_unit_by_window.csv (69 подразделений × 3 окна, после purge).
Схема — walk-forward автора:
    фолд A:  подбор на 2015H1        → проверка на 2015H2
    фолд B:  подбор на 2015H1+2015H2 → проверка на 2016H1
Подбор = выбрать порог c и оставить подразделения с долей >= c на окне подбора.
Проверка = поставить на ВСЕ оставшиеся строки проверочного окна.

Считается только фильтр БЕЗ модели. Версия с моделью здесь недоказуема:
её критерий стоит на точности ставок модели внутри подразделения, а не на
базовой доле, и до обучения такой величины не существует.

Запуск: python3 notes/sql/v2/27_art_unit_walkforward.py
"""
import csv, collections
from statistics import NormalDist

Z = NormalDist().inv_cdf(0.95)
W, L, TARGET = 10.0, 80.0, 1650.0
MIN_SUPPORT = 0                      # пол числа наблюдений в окне подбора

d = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))
for r in csv.DictReader(open("notes/sql/v2/27_art_unit_by_window.csv")):
    cell = d[r["art_unit"]][r["period"]]
    cell[0] += int(r["n"]); cell[1] += int(r["n103"])

def agg(units, periods):
    n = n103 = 0
    for u in units:
        for p in periods:
            n += d[u][p][0]; n103 += d[u][p][1]
    return n, n103

def ev(n, n103):  return (W + L) * n103 - L * n
def ci(n, n103):
    if n == 0: return 0.0
    p = n103 / n
    return ev(n, n103) - Z * (W + L) * (n * p * (1 - p)) ** 0.5

ALL = sorted(d)
FOLDS = [("A", ["2015H1"], "2015H2"), ("B", ["2015H1", "2015H2"], "2016H1")]
CUTS = [0.00, 0.70, 0.75, 0.80, 0.85, 0.8889, 0.90, 0.92, 0.95]

for name, fit_w, test_w in FOLDS:
    n_all, n103_all = agg(ALL, [test_w])
    print(f"\n=== фолд {name}: подбор {'+'.join(fit_w)} → проверка {test_w} ===")
    print(f"без фильтра на {test_w}: n={n_all}, доля={n103_all/n_all:.4f}, "
          f"EV={ev(n_all,n103_all):.0f}")
    print(f"{'порог':>7} {'страт':>6} {'доля подб.':>11} {'n тест':>7} "
          f"{'доля тест':>10} {'просадка':>9} {'EV тест':>9} {'ci_low':>9}")
    for c in CUTS:
        S = []
        for u in ALL:
            n_f, n103_f = agg([u], fit_w)
            if n_f >= MIN_SUPPORT and n_f > 0 and n103_f / n_f >= c:
                S.append(u)
        if not S: continue
        nf, n103f = agg(S, fit_w)
        nt, n103t = agg(S, [test_w])
        if nt == 0: continue
        p_fit, p_test = n103f / nf, n103t / nt
        print(f"{c:7.4f} {len(S):6d} {p_fit:11.4f} {nt:7d} {p_test:10.4f} "
              f"{100*(p_fit-p_test):8.2f}п {ev(nt,n103t):9.0f} {ci(nt,n103t):9.0f}")

print(f"\nцель: ci_low >= {TARGET:g}")
print("окно проверки фолда B — 7 501 строка против 7 405 в ящике (разница 1,3%),")
print("поэтому его числа сравниваются с целью НАПРЯМУЮ. Фолд A на 6 523 —")
print("окно на 12% меньше ящика, там сравнение приблизительное.")

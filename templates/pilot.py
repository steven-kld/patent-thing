"""Пилот (stages-v2 X1–X4): есть ли сигнал, по out-of-fold оценкам train.

Берёт результаты templates/train_cv.py (oof — откалиброванные out-of-fold оценки
каждой конфигурации) и метки train. Для каждой конфигурации: объекты по убыванию
оценки, для каждого k = 1 … cap — точность верхушки, EV по экономике и ci_low
(бутстрап по отдельным действиям, как в оценщике эксперимента №1: 5-й процентиль).

Критерий пилота — формула, объявленная до запуска (карточка гипотезы §8):
`--criterion` — порог ci_low; пилот пройден, если хоть у одной конфигурации
ci_low(k) ≥ criterion при каком-нибудь k ≤ cap. Умолчания нет. Рекомендация —
плотность цели: target × N_train / N_ящика (как гейт разведки). «ci_low ≥ 0»
слишком мягок: эксперимент №1 (max EV +390 при цели 1650) его проходил.

Это train: оценки честные (объект не был в обучении своей модели), но окно то
же. На разведке обычно не лучше. Число пилота результатом не является (X2, E3).

Пример (экономика эксперимента №1):
    python3 templates/pilot.py --run ~/exp-work/train/run1 \
      --labels ~/exp-work/data/labels.parquet --label-col rejection_103 \
      --win 10 --loss 80 --target 1650 --cap 1629 --criterion 2122   # 1650·9522/7405
"""
import argparse
import glob
import os

import joblib
import numpy as np
import pyarrow.parquet as pq
from sklearn.metrics import roc_auc_score

SEED, B = 14, 10000


def ci_low_curve(yk, win, loss, ks, rs):
    """ci_low(k): бутстрап суммы первых k исходов, 5-й процентиль.

    Исходы двузначные (+win / −loss), поэтому бутстрап по отдельным действиям
    точно равен биномиальному: число удач в выборке с возвращением W ~ Bin(k, p_k),
    p_k — доля удач среди первых k. Сумма = win·W − loss·(k − W). Тот же
    результат, что перебор, но мгновенно.
    """
    cum = np.cumsum(yk)
    res = {}
    for k in ks:
        w = rs.binomial(k, cum[k - 1] / k, size=B)
        res[k] = float(np.percentile(win * w - loss * (k - w), 5))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--label-col", required=True)
    ap.add_argument("--id-col", default="id")
    ap.add_argument("--win", type=float, required=True)
    ap.add_argument("--loss", type=float, required=True)
    ap.add_argument("--target", type=float, required=True)
    ap.add_argument("--cap", type=int, required=True)
    ap.add_argument("--criterion", type=float, required=True)
    ap.add_argument("--step", type=int, default=10, help="шаг k для ci_low (точка — каждая)")
    a = ap.parse_args()

    run = os.path.expanduser(a.run)
    ids = open(f"{run}/ids.txt").read().split()
    lab = pq.read_table(os.path.expanduser(a.labels)).to_pandas()
    lab = lab.set_index(lab[a.id_col].astype(str))[a.label_col]
    y = np.array([int(lab[i]) for i in ids])
    be = a.loss / (a.win + a.loss)
    print(f"train N = {len(y)}, доля положительных {y.mean():.4f}, безубыточность {be:.4f}, "
          f"цель {a.target:g}, потолок {a.cap}, критерий ci_low ≥ {a.criterion:g}\n")

    rows = []
    for p in sorted(glob.glob(f"{run}/*.joblib")):
        name = os.path.basename(p)[:-7]
        o = joblib.load(p)["oof"]
        order = np.argsort(-o, kind="stable")
        out = np.where(y[order] == 1, a.win, -a.loss)
        cap = min(a.cap, len(y))
        ev = np.cumsum(out[:cap])
        ks = list(range(a.step, cap + 1, a.step))
        ci = ci_low_curve(y[order], a.win, a.loss, ks, np.random.RandomState(SEED))
        best_k = max(ci, key=ci.get)
        rows.append((ci[best_k], name, roc_auc_score(y, o), int(ev.argmax()) + 1, float(ev.max()),
                     best_k, {k: float(y[order][:k].mean()) for k in (100, 300, 1000) if k <= cap}))

    rows.sort(reverse=True)
    print(f"{'макс ci_low':>11} {'при k':>6} {'макс EV':>8} {'при k':>6} {'AUC':>6}  точность топ-100/300/1000  конфигурация")
    for ci, name, auc, k_ev, ev, k_ci, acc in rows:
        accs = " / ".join(f"{v:.1%}" for v in acc.values())
        print(f"{ci:11.0f} {k_ci:6} {ev:8.0f} {k_ev:6} {auc:6.3f}  {accs:26}  {name}")
    passed = rows[0][0] >= a.criterion
    print(f"\nПИЛОТ: {'пройден' if passed else 'НЕ пройден'} "
          f"(лучший ci_low {rows[0][0]:.0f} против критерия {a.criterion:g}; цель правила {a.target:g})")


if __name__ == "__main__":
    main()

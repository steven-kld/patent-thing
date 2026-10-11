"""Почти-дубликаты («братья») и их вклад в разброс.

Только train (метки train свободны, O6). Братья — связные компоненты по
cos(векторов поля `--field`) ≥ порога. Для каждого порога: число групп, доля
train в группах, ρ — внутригрупповая корреляция метки по парам, Deff =
1 + (Σm²/N − 1)·ρ — во сколько раз дисперсия суммы исходов больше, чем при
независимости. Плюс худший случай: все братья внутри k действий.

Зачем: бутстрап по отдельным действиям (block 1) верен, только если исходы
независимы; братья с одинаковым исходом занижают интервал и α. Если Deff
заметен — правило «брат → пас» на ставках или бутстрап по группам.

Пример:
    python3 templates/near_dups.py --vec ~/exp-work/vec/emb_small --field ta \
      --ids ~/exp-work/data/train_ids.txt --labels ~/exp-work/data/labels.parquet \
      --label-col label --k 300,800,1600
"""
import argparse
import os

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from train_cv import load_chunks


def components(V, th):
    n = len(V)
    parent = np.arange(n)

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for s in range(0, n, 1000):
        r, c = np.nonzero(V[s:s + 1000] @ V.T >= th)
        for i, j in zip(r + s, c):
            if i < j and find(i) != find(j):
                parent[find(i)] = find(j)
    return np.array([find(i) for i in range(n)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vec", required=True)
    ap.add_argument("--field", required=True)
    ap.add_argument("--ids", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--label-col", required=True)
    ap.add_argument("--id-col", default="id")
    ap.add_argument("--thresholds", default="0.99,0.97,0.95")
    ap.add_argument("--k", default="300,800,1600")
    a = ap.parse_args()

    ids = open(os.path.expanduser(a.ids)).read().split()
    lab = pq.read_table(os.path.expanduser(a.labels)).to_pandas()
    y = lab.set_index(lab[a.id_col].astype(str))[a.label_col].loc[ids].astype(int).values
    app, field, vec = load_chunks(a.vec, ids, a.id_col)
    k = field == a.field
    pos = {x: i for i, x in enumerate(app[k])}
    V = vec[k][[pos[x] for x in ids]]
    V = V / np.linalg.norm(V, axis=1, keepdims=True)
    p = y.mean()
    same_rand = p * p + (1 - p) * (1 - p)
    print(f"N = {len(y)}, доля положительных {p:.4f}\n")
    for th in (float(x) for x in a.thresholds.split(",")):
        g = components(V, th)
        sizes = np.bincount(pd.factorize(g)[0])
        multi = sizes[sizes >= 2]
        same = tot = 0
        for _, idx in pd.Series(np.arange(len(y))).groupby(g):
            if len(idx) < 2:
                continue
            kk, n = y[idx.values].sum(), len(idx)
            same += kk * (kk - 1) / 2 + (n - kk) * (n - kk - 1) / 2
            tot += n * (n - 1) / 2
        rho = ((same / tot) - same_rand) / (1 - same_rand) if tot else float("nan")
        deff = 1 + ((sizes ** 2).sum() / len(y) - 1) * rho
        worst = []
        for n in (int(x) for x in a.k.split(",")):
            if multi.sum() <= n:
                sq = (multi ** 2).sum() + (n - multi.sum())
                worst.append(f"k={n}: ×{1 + (sq / n - 1) * rho:.3f}")
        print(f"cos ≥ {th}: групп {len(multi)}, в группах {multi.sum()} ({multi.sum() / len(y):.2%}), "
              f"макс m {sizes.max()}, ρ {rho:.3f}, Deff {deff:.3f}; худший случай {', '.join(worst)}")


if __name__ == "__main__":
    main()

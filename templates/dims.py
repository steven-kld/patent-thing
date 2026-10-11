"""Сколько главных направлений несут 90/95/99% разброса векторов.

Только train, только признаки. Векторы кусков после L2 и векторы объектов
(среднее по кускам полей `--fields`, затем L2). Это PCA, а не усечение
Matryoshka: показывает, сколько независимых направлений есть, а не что
теряет усечение до первых k координат.

Пример:
    python3 templates/dims.py --vec ~/exp-work/vec/emb_small --ids ~/exp-work/data/train_ids.txt --fields ta,c,d
"""
import argparse
import os

import numpy as np

from train_cv import load_chunks


def ks(X):
    X = X - X.mean(0)
    ev = np.linalg.eigvalsh(X.T @ X / len(X))[::-1]
    c = np.cumsum(ev) / ev.sum()
    return [int(np.searchsorted(c, t) + 1) for t in (0.90, 0.95, 0.99)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vec", required=True)
    ap.add_argument("--ids", required=True)
    ap.add_argument("--fields", required=True)
    ap.add_argument("--id-col", default="id")
    a = ap.parse_args()
    ids = open(os.path.expanduser(a.ids)).read().split()
    app, field, vec = load_chunks(a.vec, ids, a.id_col)
    keep = np.isin(field, a.fields.split(","))
    app, V = app[keep], vec[keep]
    V = V / np.linalg.norm(V, axis=1, keepdims=True)
    u, inv = np.unique(app, return_inverse=True)
    A = np.zeros((len(u), V.shape[1]))
    np.add.at(A, inv, V)
    A /= np.linalg.norm(A, axis=1, keepdims=True)
    for name, X in (("куски", V), ("объекты", A)):
        k = ks(X)
        print(f"{name:8} N={len(X):7}  90% {k[0]:4}  95% {k[1]:4}  99% {k[2]:4}  из {V.shape[1]}")


if __name__ == "__main__":
    main()

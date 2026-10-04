"""Стадия 6, шаг 5 плана: сколько главных направлений несут 90/95/99% разброса векторов.

План разведки (protocol-v2.json): «перед обучением измерить на train, сколько главных
направлений несут 90/95/99% разброса векторов». Только train_2015H1 после purge,
только признаки — меток не читает.

Векторы — как их увидит голова при полной размерности: вектор куска после layer
norm (так сохранён), затем L2-нормировка. Два уровня:
  куски       все куски ta, c, d заявок train
  заявка      среднее по кускам tacd, затем L2 — один вектор на заявку
"""
import glob
import sys

import numpy as np
import pyarrow.parquet as pq

VEC = "/home/px/patent-work/vec"
train = set(open("/home/px/patent-work/data/train_ids.txt").read().split())


def load(d):
    ids, vs = [], []
    for f in sorted(glob.glob(f"{VEC}/{d}/part-*.parquet")):
        m = pq.read_table(f, columns=["app_id"]).to_pandas()
        k = m.app_id.isin(train).values
        if k.any():
            ids.append(m.app_id.values[k])
            vs.append(np.load(f[:-8] + ".npy")[k])
    return np.concatenate(ids), np.concatenate(vs)


def ks(X):
    X = X - X.mean(0)
    ev = np.linalg.eigvalsh(X.T @ X / len(X))[::-1]
    c = np.cumsum(ev) / ev.sum()
    return [int(np.searchsorted(c, t) + 1) for t in (0.90, 0.95, 0.99)]


for d in ("emb_small", "emb_large"):
    ids, V = load(d)
    V = V / np.linalg.norm(V, axis=1, keepdims=True)
    apps, inv = np.unique(ids, return_inverse=True)
    A = np.zeros((len(apps), V.shape[1]))
    np.add.at(A, inv, V)
    A /= np.bincount(inv)[:, None]
    A /= np.linalg.norm(A, axis=1, keepdims=True)
    assert len(apps) == len(train), (len(apps), len(train))
    kc, ka = ks(V), ks(A)
    print(f"{d}: заявок {len(apps)}, кусков {len(V)}")
    print(f"  куски        90% {kc[0]:4}  95% {kc[1]:4}  99% {kc[2]:4}   из 768")
    print(f"  заявка tacd  90% {ka[0]:4}  95% {ka[1]:4}  99% {ka[2]:4}   из 768")
    sys.stdout.flush()

"""Дефект 3 ревизии 26: вклад братских заявок в разброс. Только train_2015H1 после purge.

Метки train свободны (O6), разведка и ящик не читаются. При новом оценщике (ставка
всегда «§103 будет») исход ставки = y, поэтому корреляция y внутри групп и есть
корреляция исходов ставок.

Группы (только признаки):
  exact_ta   нормализованные title + abstract совпадают
  title      нормализованный title совпадает
  cos≥t      косинус векторов ta (мелкая нарезка) ≥ t, связные компоненты

Для каждой: число групп, доля train в группах, ρ — внутригрупповая корреляция y по
парам, Deff = 1 + (Σm²/N − 1)·ρ — во сколько раз дисперсия суммы исходов больше, чем
при независимости, если ставить на весь train. Плюс прямая проверка: SD суммы y
бутстрапом по группам против бутстрапа по заявкам.
"""
import re

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

D = "/home/px/patent-work/data"
PURGE = {"13859613", "13918690"}

t = pq.read_table(f"{D}/texts.parquet", columns=["app_id", "period", "title", "abstract"]).to_pandas()
t = t[(t.period == "2015H1") & ~t.app_id.isin(PURGE)]
lab = pq.read_table(f"{D}/labels.parquet").to_pandas()
t = t.merge(lab[["app_id", "rejection_103"]], on="app_id").sort_values("app_id").reset_index(drop=True)
y = t.rejection_103.astype(int).values
N = len(t)

ids = open(f"{D}/ta_train_ids.txt").read().split()
assert ids == list(t.app_id), "порядок векторов ta не совпал с train"
V = np.load(f"{D}/ta_train.npy")
V = V / np.linalg.norm(V, axis=1, keepdims=True)

norm = lambda s: re.sub(r"\W+", " ", s.lower()).strip()


def labels_from_keys(keys):
    return pd.factorize(pd.Series(keys))[0]


def labels_from_cos(th):
    parent = np.arange(N)

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for s in range(0, N, 1000):
        S = V[s:s + 1000] @ V.T
        r, c = np.nonzero(S >= th)
        for i, j in zip(r + s, c):
            if i < j:
                a, b = find(i), find(j)
                if a != b:
                    parent[a] = b
    return np.array([find(i) for i in range(N)])


def stats(g, rs):
    sizes = np.bincount(g)
    sizes = sizes[sizes > 0]
    multi = sizes[sizes >= 2]
    p = y.mean()
    same_rand = p * p + (1 - p) * (1 - p)
    same = tot = 0
    for grp in pd.Series(np.arange(N)).groupby(g):
        idx = grp[1].values
        if len(idx) < 2:
            continue
        k = y[idx].sum()
        n = len(idx)
        same += k * (k - 1) / 2 + (n - k) * (n - k - 1) / 2
        tot += n * (n - 1) / 2
    rho = ((same / tot) - same_rand) / (1 - same_rand) if tot else float("nan")
    deff = 1 + ((sizes ** 2).sum() / N - 1) * rho
    # бутстрап: SD суммы y по группам против по заявкам
    gid = pd.factorize(g)[0]
    G = gid.max() + 1
    gsum = np.bincount(gid, weights=y, minlength=G)
    gn = np.bincount(gid, minlength=G)
    sd_iid = np.std([y[rs.randint(0, N, N)].sum() for _ in range(2000)])
    sums = []
    for _ in range(2000):
        pick = rs.randint(0, G, G)
        sums.append(gsum[pick].sum() * N / gn[pick].sum())
    sd_clu = np.std(sums)
    return dict(groups=len(multi), in_groups=int(multi.sum()), share=multi.sum() / N,
                max_m=int(sizes.max()), pairs=int(tot), rho=rho, deff=deff,
                boot_ratio=(sd_clu / sd_iid) ** 2)


rs = np.random.RandomState(14)
rows = [("exact_ta", labels_from_keys([norm(a) + "|" + norm(b) for a, b in zip(t.title, t.abstract)])),
        ("title", labels_from_keys([norm(a) for a in t.title]))]
for th in (0.99, 0.98, 0.97, 0.95):
    rows.append((f"cos≥{th}", labels_from_cos(th)))

print(f"train_2015H1 после purge: N = {N}, доля §103 = {y.mean():.4f}\n")
print(f"{'группы':10} {'групп':>6} {'в группах':>9} {'доля':>6} {'макс m':>6} {'пар':>7} {'ρ':>7} {'Deff':>6} {'бутстрап':>8}")
for name, g in rows:
    s = stats(g, rs)
    print(f"{name:10} {s['groups']:6} {s['in_groups']:9} {s['share']:6.2%} {s['max_m']:6} {s['pairs']:7} "
          f"{s['rho']:7.3f} {s['deff']:6.3f} {s['boot_ratio']:8.3f}")

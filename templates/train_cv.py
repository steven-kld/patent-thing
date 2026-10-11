"""Обучение голов на train с кросс-валидацией.

Читает ТОЛЬКО объекты из `--ids` (train) и их метки. Разведку и ящик не трогает:
векторы фильтруются по списку при чтении, лишние в память не попадают.

Конфигурации: нарезка (`--vec ИМЯ=ПАПКА`, можно несколько) × вариант
(`--variant ИМЯ=ПОЛЕ+ПОЛЕ…`) × голова (logreg, mlp) × размерность × сведение.

Для каждой конфигурации:
  1  5 фолдов; near-дубликаты по полю `--group-field` (cos ≥ `--dup-cos`) — в одном
     фолде, иначе модель «подсмотрит» ответ у почти одинакового соседа
  2  сетка настроек; выбор по среднему log-loss out-of-fold (честность вероятностей)
  3  mlp — ранняя остановка по log-loss на отложенных 10% обучающей части
  4  калибровка Platt на out-of-fold оценках (монотонна: порядок не меняет)
  5  финальная модель на всём train
Векторы: поля варианта → первые dim координат → L2 → сведение (mean|max) → L2.

Выход: <out>/<конфигурация>.joblib (модель, калибратор, настройки, oof — откалиброванные
out-of-fold оценки для пилота), <out>/ids.txt (порядок строк oof), summary.json.
Лог — процент и ETA. `--only` и `--compare` — проверка детерминизма на подмножестве:
веса и калибратор сверяются побитово с прошлым прогоном.

Ориентир: 9,5 тыс. объектов × 768, 96 конфигураций — ~2 ч на 8 ядрах CPU.
Требует scikit-learn, joblib.

Пример:
    python3 templates/train_cv.py --out ~/exp-work/train/run1 \
      --vec small=~/exp-work/vec/emb_small --vec large=~/exp-work/vec/emb_large \
      --ids ~/exp-work/data/train_ids.txt --labels ~/exp-work/data/labels.parquet \
      --label-col label --variant all=ta+c+d --variant c=c --group-field ta
"""
import argparse
import copy
import glob
import hashlib
import itertools
import json
import os
import time

import joblib
import numpy as np
import pyarrow.parquet as pq
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
from sklearn.model_selection import GroupKFold
from sklearn.neural_network import MLPClassifier

SEED = 14
LOGREG_C = np.logspace(-3, 2, 11)
MLP_WIDTH = (32, 64, 128)
MLP_ALPHA = (1e-4, 1e-3, 1e-2)
MLP_MAX_EPOCHS, MLP_PATIENCE, MLP_VAL_FRAC = 200, 10, 0.1


def load_chunks(d, ids, id_col):
    keep = set(ids)
    app, field, vec = [], [], []
    for f in sorted(glob.glob(f"{os.path.expanduser(d)}/part-*.parquet")):
        m = pq.read_table(f, columns=[id_col, "field"]).to_pandas()
        k = m[id_col].astype(str).isin(keep).values
        if k.any():
            app.append(m[id_col].astype(str).values[k])
            field.append(m.field.values[k])
            vec.append(np.load(f[:-8] + ".npy")[k])
    return np.concatenate(app), np.concatenate(field), np.concatenate(vec)


def app_matrix(ids, app, field, vec, fields, dim, pooling):
    keep = np.isin(field, list(fields))
    a, v = app[keep], vec[keep][:, :dim]
    v = v / np.linalg.norm(v, axis=1, keepdims=True)
    pos = {x: i for i, x in enumerate(ids)}
    row = np.array([pos[x] for x in a])
    if pooling == "mean":
        X = np.zeros((len(ids), dim))
        np.add.at(X, row, v)
        X /= np.bincount(row, minlength=len(ids))[:, None]
    else:
        X = np.full((len(ids), dim), -np.inf)
        np.maximum.at(X, row, v)
    assert np.isfinite(X).all(), "у объекта нет кусков варианта"
    return X / np.linalg.norm(X, axis=1, keepdims=True)


def dup_groups(ids, app, field, vec, group_field, cos):
    """Связные компоненты «почти дубликатов»: cos векторов поля group_field ≥ cos."""
    k = field == group_field
    pos = {x: i for i, x in enumerate(app[k])}
    V = vec[k][[pos[x] for x in ids]]
    V = V / np.linalg.norm(V, axis=1, keepdims=True)
    parent = np.arange(len(ids))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for s in range(0, len(ids), 1000):
        r, c = np.nonzero(V[s:s + 1000] @ V.T >= cos)
        for i, j in zip(r + s, c):
            if i < j and find(i) != find(j):
                parent[find(i)] = find(j)
    return np.array([find(i) for i in range(len(ids))])


def fit_mlp(X, y, width, alpha):
    idx = np.random.RandomState(SEED).permutation(len(y))
    n_val = int(len(y) * MLP_VAL_FRAC)
    va, tr = idx[:n_val], idx[n_val:]
    m = MLPClassifier(hidden_layer_sizes=(width,), alpha=alpha, random_state=SEED,
                      learning_rate_init=1e-3, batch_size=256)
    best, best_loss, bad = None, np.inf, 0
    for _ in range(MLP_MAX_EPOCHS):
        m.partial_fit(X[tr], y[tr], classes=[0, 1])
        loss = log_loss(y[va], m.predict_proba(X[va])[:, 1], labels=[0, 1])
        if loss < best_loss - 1e-6:
            best, best_loss, bad = copy.deepcopy(m), loss, 0
        else:
            bad += 1
            if bad >= MLP_PATIENCE:
                break
    return best


def fit(head, X, y, hp):
    if head == "logreg":
        return LogisticRegression(C=hp["C"], max_iter=5000, random_state=SEED).fit(X, y)
    return fit_mlp(X, y, hp["width"], hp["alpha"])


def grid(head):
    if head == "logreg":
        return [{"C": float(c)} for c in LOGREG_C]
    return [{"width": w, "alpha": a} for w, a in itertools.product(MLP_WIDTH, MLP_ALPHA)]


def logit(p):
    p = np.clip(p, 1e-7, 1 - 1e-7)
    return np.log(p / (1 - p))


def train_config(head, X, y, folds):
    results = []
    for hp in grid(head):
        oof = np.zeros(len(y))
        for tr, te in folds:
            oof[te] = fit(head, X[tr], y[tr], hp).predict_proba(X[te])[:, 1]
        results.append((log_loss(y, oof, labels=[0, 1]), hp, oof))
    cv_loss, hp, oof = min(results, key=lambda r: r[0])
    platt = LogisticRegression(C=1e6, max_iter=1000).fit(logit(oof)[:, None], y)
    cal = platt.predict_proba(logit(oof)[:, None])[:, 1]
    return fit(head, X, y, hp), platt, cal, {
        "hp": hp, "cv_logloss": cv_loss, "cv_logloss_calibrated": log_loss(y, cal, labels=[0, 1]),
        "grid": [{"hp": h, "cv_logloss": l} for l, h, _ in results]}


def weights_bytes(path):
    d = joblib.load(path)
    m, pl = d["model"], d["platt"]
    ws = (m.coef_, m.intercept_) if hasattr(m, "coef_") else (*m.coefs_, *m.intercepts_)
    return b"".join(np.ascontiguousarray(w).tobytes() for w in (*ws, pl.coef_, pl.intercept_))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--vec", action="append", required=True, help="ИМЯ=ПАПКА векторов")
    ap.add_argument("--ids", required=True, help="файл со списком объектов train")
    ap.add_argument("--labels", required=True)
    ap.add_argument("--label-col", required=True)
    ap.add_argument("--id-col", default="id", help="ключ в labels и в векторах")
    ap.add_argument("--variant", action="append", required=True, help="ИМЯ=ПОЛЕ+ПОЛЕ…")
    ap.add_argument("--heads", default="logreg,mlp")
    ap.add_argument("--dims", default="256,512,768")
    ap.add_argument("--poolings", default="mean,max")
    ap.add_argument("--group-field", required=True)
    ap.add_argument("--dup-cos", type=float, default=0.95)
    ap.add_argument("--only")
    ap.add_argument("--compare")
    a = ap.parse_args()

    vecs = dict(s.split("=", 1) for s in a.vec)
    variants = {k: set(v.split("+")) for k, v in (s.split("=", 1) for s in a.variant)}
    heads, poolings = a.heads.split(","), a.poolings.split(",")
    dims = [int(x) for x in a.dims.split(",")]
    only = set(a.only.split(",")) if a.only else None
    out = os.path.expanduser(a.out)
    os.makedirs(out, exist_ok=True)

    ids = open(os.path.expanduser(a.ids)).read().split()
    lab = pq.read_table(os.path.expanduser(a.labels)).to_pandas()
    lab = lab.set_index(lab[a.id_col].astype(str))[a.label_col]
    y = np.array([int(lab[i]) for i in ids])
    open(f"{out}/ids.txt", "w").write("\n".join(ids) + "\n")

    summary = {"n_train": len(ids), "share_pos": float(y.mean()), "configs": {}}
    total = len(only) if only else len(vecs) * len(variants) * len(heads) * len(dims) * len(poolings)
    done, t0, folds = 0, time.time(), None
    for vname, vdir in vecs.items():
        app, field, vec = load_chunks(vdir, ids, a.id_col)
        assert set(app) == set(ids), "в векторах не все объекты train или лишние"
        if folds is None:
            groups = dup_groups(ids, app, field, vec, a.group_field, a.dup_cos)
            folds = list(GroupKFold(n_splits=5).split(np.zeros(len(y)), y, groups))
        for variant, dim, pooling in itertools.product(variants, dims, poolings):
            names = [f"{vname}_{variant}_{h}_{dim}_{pooling}" for h in heads]
            if only and not only & set(names):
                continue
            X = app_matrix(ids, app, field, vec, variants[variant], dim, pooling)
            for head, name in zip(heads, names):
                if only and name not in only:
                    continue
                model, platt, cal, info = train_config(head, X, y, folds)
                joblib.dump({"model": model, "platt": platt, "oof": cal, **info}, f"{out}/{name}.joblib")
                summary["configs"][name] = info
                done += 1
                el = time.time() - t0
                print(f"[{done}/{total} {done / total:4.0%}  прошло {el / 60:5.1f} мин, осталось "
                      f"~{el / done * (total - done) / 60:5.1f} мин]  {name}: {info['hp']}  "
                      f"cv log-loss {info['cv_logloss']:.5f}", flush=True)

    with open(f"{out}/summary.json", "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1, sort_keys=True)
    h = hashlib.sha256(open(f"{out}/summary.json", "rb").read())
    for p in sorted(glob.glob(f"{out}/*.joblib")):
        h.update(weights_bytes(p))
    print("sha256 обучения:", h.hexdigest())

    if a.compare:
        ok = True
        for name in sorted(summary["configs"]):
            same = weights_bytes(f"{out}/{name}.joblib") == \
                weights_bytes(f"{os.path.expanduser(a.compare)}/{name}.joblib")
            ok &= same
            print(f"  {name}: {'совпало' if same else 'НЕ СОВПАЛО'}")
        print("СВЕРКА:", "совпало" if ok else "НЕ СОВПАЛО")


if __name__ == "__main__":
    main()

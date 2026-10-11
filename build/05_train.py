"""Стадия 6, шаг 28: обучение голов на train_2015H1. Разведку и ящик не читает.

Спецификация — artifacts/build.md («Задача 3», «Порядок операций над векторами»).

НА ПАЛЬЦАХ, ЧТО ДЕЛАЕТ ЭТОТ ФАЙЛ
--------------------------------
У нас уже есть векторы: каждый кусок текста каждой заявки превращён энкодером в
768 чисел. Этот файл учит «головы» — маленькие модели, которые по вектору
заявки говорят: «вероятность, что будет §103, — столько-то».

Голов надо обучить много, по одной на каждую конфигурацию:
    нарезка      small (куски по 1000 токенов) или large (по 2048)
    вариант      какие поля заявки смотрим: tacd, tac, c, d
    голова       logreg (простая) или mlp (с одним скрытым слоем)
    размерность  берём первые 256, 512 или все 768 чисел вектора
    сведение     как из многих кусков сделать один вектор: среднее или максимум
2 × 4 × 2 × 3 × 2 = 96 конфигураций.

Для каждой конфигурации, ТОЛЬКО на train:
  1  делим train на 5 частей (фолдов). Учим на четырёх, проверяем на пятой,
     и так пять раз по кругу — каждая заявка один раз была «проверочной».
     Братские заявки (почти одинаковый текст) всегда в одной части, иначе
     модель «подсмотрит» ответ у брата
  2  у головы есть настройки (сила регуляризации у logreg; ширина слоя и
     регуляризация у mlp). Пробуем каждую настройку из сетки по схеме п. 1
     и берём ту, у которой вероятности честнее всего (меньше log-loss)
  3  mlp учится проходами по данным (эпохами); останавливаем, когда на
     отложенном кусочке обучающих данных вероятности перестали улучшаться
  4  калибровка: по оценкам из п. 1 учим поправку, которая делает «95%»
     честными 95%. Порядок заявок поправка не меняет
  5  финальная модель — та же настройка, обученная на всём train

Выход: <out>/<конфигурация>.joblib (модель + поправка + настройки) и
<out>/summary.json. В конце печатается хеш: два прогона обязаны дать один
и тот же хеш (шаг 30 требует воспроизводимости).

Требует scikit-learn и joblib в ~/patent-work/venv.
"""
import argparse
import copy
import glob
import hashlib
import itertools
import json
import os

import joblib
import numpy as np
import pyarrow.parquet as pq
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
from sklearn.model_selection import GroupKFold
from sklearn.neural_network import MLPClassifier

DATA = os.path.expanduser("~/patent-work/data")
VEC = os.path.expanduser("~/patent-work/vec")

# Одно и то же «случайное» зерно везде: тогда любая случайность (начальные веса
# mlp, перемешивание) повторяется от прогона к прогону, и хеш совпадает.
SEED = 14

# Оси перебора — те же, что в selection.space и _план_разведки.
CHUNKINGS = {"small": "emb_small", "large": "emb_large"}
VARIANTS = {"tacd": {"ta", "c", "d"}, "tac": {"ta", "c"}, "c": {"c"}, "d": {"d"}}
HEADS = ("logreg", "mlp")
DIMS = (256, 512, 768)
POOLINGS = ("mean", "max")

# Сетки настроек голов (инженерный выбор; что из них лучше, решают данные train).
# C у logreg — обратная сила регуляризации: маленький C = сильно «сжимаем» веса,
# модель осторожная; большой C = почти не сжимаем, модель смелая.
LOGREG_C = np.logspace(-3, 2, 11)          # 0,001 … 100, 11 значений
# mlp: сколько нейронов в скрытом слое и сколько штрафовать большие веса.
MLP_WIDTH = (32, 64, 128)
MLP_ALPHA = (1e-4, 1e-3, 1e-2)
# Ранняя остановка: максимум 200 проходов; стоп, если 10 подряд без улучшения;
# 10% обучающей части откладывается, чтобы на ней следить за улучшением.
MLP_MAX_EPOCHS, MLP_PATIENCE, MLP_VAL_FRAC = 200, 10, 0.1
# Порог «братства» — решение автора (build.md).
SIBLING_COS = 0.95


# ------------------------------------------------------------------ данные

def train_ids_and_labels():
    """Список заявок train и их ответы y (1 — был §103, 0 — не был).

    train_ids.txt — 9 522 заявки train_2015H1 после purge. Метки берём только
    за период 2015H1: разведочные метки в этом файле тоже лежат, но сюда не
    попадают, а меток ящика в labels.parquet нет вовсе.
    """
    ids = open(f"{DATA}/train_ids.txt").read().split()
    lab = pq.read_table(f"{DATA}/labels.parquet").to_pandas()
    lab = lab[lab.period == "2015H1"].set_index("app_id").rejection_103
    y = np.array([int(lab[a]) for a in ids])
    return ids, y


def load_chunks(chunking, train):
    """Векторы кусков только заявок train.

    Векторы лежат частями (part-00000 … part-00061) по всей когорте. Из каждой
    части оставляем только строки заявок train — векторы разведки и ящика в
    память даже не попадают.
    Возвращает три параллельных массива: чья заявка, какое поле (ta/c/d), вектор.
    """
    app, field, vec = [], [], []
    for f in sorted(glob.glob(f"{VEC}/{CHUNKINGS[chunking]}/part-*.parquet")):
        m = pq.read_table(f, columns=["app_id", "field"]).to_pandas()
        k = m.app_id.isin(train).values
        if k.any():
            app.append(m.app_id.values[k])
            field.append(m.field.values[k])
            vec.append(np.load(f[:-8] + ".npy")[k])
    return np.concatenate(app), np.concatenate(field), np.concatenate(vec)


def app_matrix(ids, app, field, vec, variant, dim, pooling):
    """Из многих кусков каждой заявки делаем ОДИН вектор заявки.

    Порядок из build.md:
      1  оставляем куски нужных полей (для варианта c — только куски claims)
      2  у каждого куска берём первые dim чисел и приводим к длине 1 (L2)
      3  сводим куски заявки: среднее по каждой координате или максимум
      4  результат снова приводим к длине 1 — чтобы у заявки из 3 кусков и у
         заявки из 30 вектор был одного масштаба
    Возвращает таблицу: строка — заявка (в порядке ids), столбцы — dim чисел.
    """
    keep = np.isin(field, list(VARIANTS[variant]))
    a, v = app[keep], vec[keep][:, :dim]
    v = v / np.linalg.norm(v, axis=1, keepdims=True)
    pos = {x: i for i, x in enumerate(ids)}
    row = np.array([pos[x] for x in a])              # номер строки заявки для каждого куска
    X = np.zeros((len(ids), dim)) if pooling == "mean" else np.full((len(ids), dim), -np.inf)
    if pooling == "mean":
        np.add.at(X, row, v)                          # складываем куски в строку своей заявки…
        X /= np.bincount(row, minlength=len(ids))[:, None]   # …и делим на их число
    else:
        np.maximum.at(X, row, v)                      # по каждой координате — наибольшее
    assert np.isfinite(X).all(), "у заявки нет кусков варианта"
    return X / np.linalg.norm(X, axis=1, keepdims=True)


def sibling_groups(ids, app, field, vec):
    """Кто кому брат — чтобы братья при кросс-валидации были в одной части.

    Берём вектор ta (заголовок + реферат) каждой заявки. Если косинус двух
    векторов ≥ 0,95 — заявки братья. Братство транзитивно: если A брат B, а B
    брат C, все трое в одной группе (union-find, как в build/03_siblings.py).
    Возвращает номер группы для каждой заявки.
    """
    k = field == "ta"
    pos = {x: i for i, x in enumerate(app[k])}
    V = vec[k][[pos[x] for x in ids]]
    V = V / np.linalg.norm(V, axis=1, keepdims=True)
    parent = np.arange(len(ids))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for s in range(0, len(ids), 1000):               # блоками по 1000, чтобы влезло в память
        r, c = np.nonzero(V[s:s + 1000] @ V.T >= SIBLING_COS)
        for i, j in zip(r + s, c):
            if i < j:
                a, b = find(i), find(j)
                if a != b:
                    parent[a] = b
    return np.array([find(i) for i in range(len(ids))])


# ------------------------------------------------------------------ головы

def fit_logreg(X, y, C):
    """logreg: каждой из dim координат — свой вес; взвешенная сумма → вероятность."""
    return LogisticRegression(C=C, max_iter=5000, random_state=SEED).fit(X, y)


def fit_mlp(X, y, width, alpha):
    """mlp: вектор → скрытый слой из width нейронов → вероятность.

    Учится проходами (эпохами). После каждого прохода смотрим log-loss на
    отложенных 10% — насколько честны вероятности на данных, которых модель
    не видела. Запоминаем лучшую версию; если 10 проходов подряд лучше не
    стало — останавливаемся и возвращаем лучшую.
    Встроенная остановка sklearn смотрит на долю угаданных, а автор выбрал
    log-loss, поэтому цикл написан вручную.
    """
    rs = np.random.RandomState(SEED)
    idx = rs.permutation(len(y))
    n_val = int(len(y) * MLP_VAL_FRAC)
    va, tr = idx[:n_val], idx[n_val:]
    m = MLPClassifier(hidden_layer_sizes=(width,), alpha=alpha, random_state=SEED,
                      learning_rate_init=1e-3, batch_size=256)
    best, best_loss, bad = None, np.inf, 0
    for _ in range(MLP_MAX_EPOCHS):
        m.partial_fit(X[tr], y[tr], classes=[0, 1])  # один проход по обучающей части
        loss = log_loss(y[va], m.predict_proba(X[va])[:, 1], labels=[0, 1])
        if loss < best_loss - 1e-6:
            best, best_loss, bad = copy.deepcopy(m), loss, 0
        else:
            bad += 1
            if bad >= MLP_PATIENCE:
                break
    return best


def grid(head):
    """Все варианты настроек, которые пробуем для этой головы."""
    if head == "logreg":
        return [{"C": float(c)} for c in LOGREG_C]
    return [{"width": w, "alpha": a} for w, a in itertools.product(MLP_WIDTH, MLP_ALPHA)]


def fit(head, X, y, hp):
    return fit_logreg(X, y, **hp) if head == "logreg" else fit_mlp(X, y, **hp)


def logit(p):
    """Вероятность → «шкала уверенности» от −∞ до +∞; на ней удобно учить поправку."""
    p = np.clip(p, 1e-7, 1 - 1e-7)
    return np.log(p / (1 - p))


def train_config(head, X, y, folds):
    """Одна конфигурация целиком.

    1  для каждой настройки из сетки: 5 раз учим на 4 частях, оцениваем пятую.
       Получаем для каждой заявки train оценку модели, которая эту заявку НЕ
       видела (out-of-fold, OOF). log-loss по этим оценкам — честная мера
    2  выбираем настройку с наименьшим log-loss
    3  калибровка Platt: учим простую поправку «сырая оценка → честная
       вероятность» на тех же OOF-оценках. Поправка монотонная: порядок заявок
       не меняется, меняются только сами проценты
    4  финальная модель — выбранная настройка на всём train
    """
    results = []
    for hp in grid(head):
        oof = np.zeros(len(y))
        for tr, te in folds:
            oof[te] = fit(head, X[tr], y[tr], hp).predict_proba(X[te])[:, 1]
        results.append((log_loss(y, oof, labels=[0, 1]), hp, oof))
    cv_loss, hp, oof = min(results, key=lambda r: r[0])
    platt = LogisticRegression(C=1e6, max_iter=1000).fit(logit(oof)[:, None], y)
    cal_oof = platt.predict_proba(logit(oof)[:, None])[:, 1]
    model = fit(head, X, y, hp)
    return model, platt, {"hp": hp, "cv_logloss": cv_loss,
                          "cv_logloss_calibrated": log_loss(y, cal_oof, labels=[0, 1]),
                          "grid": [{"hp": h, "cv_logloss": l} for l, h, _ in results]}


# ------------------------------------------------------------------ прогон

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    ids, y = train_ids_and_labels()
    train = set(ids)
    summary = {"n_train": len(ids), "share_103": float(y.mean()), "configs": {}}
    folds = None

    for chunking in CHUNKINGS:
        app, field, vec = load_chunks(chunking, train)
        # Защита: в памяти ровно заявки train — ни одной лишней, ни одной пропавшей.
        assert set(app) == train, "в векторах не все заявки train или лишние"
        if folds is None:
            # Деление на 5 частей — одно на все конфигурации, чтобы их сравнение
            # было честным: все проверяются на одних и тех же частях.
            groups = sibling_groups(ids, app, field, vec)
            folds = list(GroupKFold(n_splits=5).split(np.zeros(len(y)), y, groups))
        for variant, dim, pooling in itertools.product(VARIANTS, DIMS, POOLINGS):
            X = app_matrix(ids, app, field, vec, variant, dim, pooling)
            for head in HEADS:
                name = f"{chunking}_{variant}_{head}_{dim}_{pooling}"
                model, platt, info = train_config(head, X, y, folds)
                joblib.dump({"model": model, "platt": platt, **info}, f"{a.out}/{name}.joblib")
                summary["configs"][name] = info
                print(f"{name}: {info['hp']}  cv log-loss {info['cv_logloss']:.5f}", flush=True)

    # Отпечаток всего обучения: сводка + веса всех моделей. Файлы .joblib сами по
    # себе хешировать нельзя — упаковка может отличаться при тех же весах.
    with open(f"{a.out}/summary.json", "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1, sort_keys=True)
    h = hashlib.sha256(open(f"{a.out}/summary.json", "rb").read())
    for p in sorted(glob.glob(f"{a.out}/*.joblib")):
        m = joblib.load(p)["model"]
        for w in (m.coef_, m.intercept_) if hasattr(m, "coef_") else (*m.coefs_, *m.intercepts_):
            h.update(np.ascontiguousarray(w).tobytes())
    print("sha256 обучения:", h.hexdigest())


if __name__ == "__main__":
    main()

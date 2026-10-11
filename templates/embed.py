"""Нарезка текстов и векторизация энкодером Hugging Face. Ориентир: 31 тыс. длинных
документов (~20 тыс. токенов), модель 137M, RTX 4090 — ~1,5 ч на одну нарезку.

Поля задаются спецификацией `--field ИМЯ=СТОЛБЕЦ[+СТОЛБЕЦ…]:whole|chunk`:
    whole   столбцы склеиваются через "\\n" и кодируются одним куском (обрезается
            до тела куска)
    chunk   текст режется окном по токенам: тело = max_len − служебные, шаг =
            тело − нахлёст. Куски не пересекают границу полей
Пример:
    --field ta=title+abstract:whole --field c=claims:chunk --field d=description:chunk

В каждый кусок добавляется префикс `--prefix` (у ряда моделей — задача:
classification:, clustering:, search_document: … — выбор меняет векторы). Вектор куска — среднее
по токенам и layer norm (до усечения Matryoshka); сохраняется полный.
Сведение кусков, усечение размерности, L2 — потом, при обучении.

Ревизии закреплять обе: `--revision` (веса) и `--code-revision` (remote_code,
бывает отдельным репозиторием). remote_code старых моделей может не работать с
transformers 5.x — проверить загрузку и при надобности закрепить 4.x. Длину
куска сверять с max_trained_positions модели.

Вход — parquet с `--id` и текстовыми столбцами; меток в нём быть не должно.
Выход — <out>/part-XXXXX.parquet (id, field, idx, n_tok) + .npy (float32, порядок
строк совпадает). Готовые части пропускаются — прерванный прогон продолжается.
В конце — sha256 всех векторов: два прогона на одной машине обязаны совпасть
(на CPU и GPU побитово не совпадут).
"""
import argparse
import glob
import hashlib
import os

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import torch
import torch.nn.functional as F
from transformers import AutoModel, AutoTokenizer


def parse_field(s):
    name, rest = s.split("=", 1)
    cols, mode = rest.rsplit(":", 1)
    assert mode in ("whole", "chunk"), s
    return name, cols.split("+"), mode


def chunk_ids(ids, body, overlap):
    if len(ids) <= body:
        return [ids]
    step = body - overlap
    out = []
    for s in range(0, len(ids), step):
        out.append(ids[s:s + body])
        if s + body >= len(ids):
            break
    return out


@torch.no_grad()
def embed(model, tok, prefix_ids, seqs, device, batch_tokens):
    full = [[tok.cls_token_id] + prefix_ids + s + [tok.sep_token_id] for s in seqs]
    order = np.argsort([-len(s) for s in full])
    vecs = np.zeros((len(full), model.config.hidden_size), dtype=np.float32)
    i = 0
    while i < len(order):
        L = len(full[order[i]])
        idx = order[i:i + max(1, batch_tokens // L)]
        ids = torch.zeros((len(idx), L), dtype=torch.long)
        mask = torch.zeros((len(idx), L), dtype=torch.long)
        for r, j in enumerate(idx):
            ids[r, :len(full[j])] = torch.tensor(full[j])
            mask[r, :len(full[j])] = 1
        ids, mask = ids.to(device), mask.to(device)
        h = model(input_ids=ids, attention_mask=mask).last_hidden_state.float()
        m = mask.unsqueeze(-1).float()
        v = F.layer_norm((h * m).sum(1) / m.sum(1), (h.shape[-1],))
        vecs[idx] = v.cpu().numpy()
        i += len(idx)
    return vecs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--texts", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--id", required=True, help="столбец-ключ")
    ap.add_argument("--field", action="append", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--revision", required=True)
    ap.add_argument("--code-revision")
    ap.add_argument("--prefix", default="")
    ap.add_argument("--max-len", type=int, required=True, help="длина куска со служебными")
    ap.add_argument("--overlap", type=int, required=True, help="нахлёст в токенах")
    ap.add_argument("--ids-file", help="подвыборка: файл с ключами по одному в строке")
    ap.add_argument("--part-size", type=int, default=500)
    ap.add_argument("--batch-tokens", type=int, default=16384)
    a = ap.parse_args()

    fields = [parse_field(f) for f in a.field]
    torch.manual_seed(0)
    torch.use_deterministic_algorithms(True, warn_only=True)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32
    tok = AutoTokenizer.from_pretrained(a.model, revision=a.revision)
    kw = {"code_revision": a.code_revision} if a.code_revision else {}
    model = AutoModel.from_pretrained(a.model, revision=a.revision, trust_remote_code=True,
                                      torch_dtype=dtype, **kw).to(device).eval()
    enc = lambda s: tok(s, add_special_tokens=False)["input_ids"]
    prefix_ids = enc(a.prefix) if a.prefix else []
    body = a.max_len - 2 - len(prefix_ids)

    cols = [a.id] + sorted({c for _, cs, _ in fields for c in cs})
    t = pq.read_table(a.texts, columns=cols).to_pandas()
    if a.ids_file:
        t = t[t[a.id].astype(str).isin(set(open(a.ids_file).read().split()))]
    t = t.sort_values(a.id).reset_index(drop=True)
    os.makedirs(a.out, exist_ok=True)

    for p0 in range(0, len(t), a.part_size):
        name = f"{a.out}/part-{p0 // a.part_size:05d}"
        if os.path.exists(name + ".done"):
            continue
        meta, seqs = [], []
        for _, row in t.iloc[p0:p0 + a.part_size].iterrows():
            for fname, fcols, mode in fields:
                ids = enc("\n".join(str(row[c]) for c in fcols))
                pieces = [ids[:body]] if mode == "whole" else chunk_ids(ids, body, a.overlap)
                for i, s in enumerate(pieces):
                    meta.append((str(row[a.id]), fname, i, len(s)))
                    seqs.append(s)
        v = embed(model, tok, prefix_ids, seqs, device, a.batch_tokens)
        pq.write_table(pa.table({"id": [m[0] for m in meta], "field": [m[1] for m in meta],
                                 "idx": [m[2] for m in meta], "n_tok": [m[3] for m in meta]}),
                       name + ".parquet")
        np.save(name + ".npy", v)
        open(name + ".done", "w").close()
        print(f"{name}: объектов {min(a.part_size, len(t) - p0)}, кусков {len(seqs)}, "
              f"токенов {sum(len(s) for s in seqs)}", flush=True)

    h = hashlib.sha256()
    for f in sorted(glob.glob(f"{a.out}/part-*.npy")):
        h.update(np.load(f).tobytes())
    print("sha256 векторов:", h.hexdigest())


if __name__ == "__main__":
    main()

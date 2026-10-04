"""Стадия 6, шаги 2–3 плана: нарезка и векторизация. Спецификация — artifacts/build.md, «Нарезка».

Элементы заявки: ta (title + "\\n" + abstract, целиком), c (claims), d (description).
c и d режутся окном по токенам: тело куска = max_len − 4 служебных, шаг = тело − нахлёст.
В каждом куске префикс "classification: ". Куски не пересекают границу полей.
Сохраняется вектор каждого куска (768, mean pooling по токенам + layer norm, как
у Nomic до усечения). Сведение кусков и усечение размерности — после, на разведке.

Вход: texts.parquet (только тексты, меток здесь нет и быть не должно).
Выход: <out>/chunks.parquet — app_id, field, idx, n_tok; <out>/vectors.npy (float32);
порядок строк совпадает. Хеш векторов печатается в конце.

Продолжение после прерывания: заявки пишутся частями part-XXXXX; готовые части
пропускаются. Порядок заявок — по app_id.
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

MODEL = "nomic-ai/nomic-embed-text-v1.5"
REV = "e9b6763023c676ca8431644204f50c2b100d9aab"
CODE_REV = "7710840340a098cfb869c4f65e87cf2b1b70caca"
PREFIX = "classification: "


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


def pieces(row, tok, body, overlap):
    """[(field, idx, token_ids)] для одной заявки, без префикса и служебных."""
    enc = lambda s: tok(s, add_special_tokens=False)["input_ids"]
    out = [("ta", 0, enc(row["title"] + "\n" + row["abstract"])[:body])]
    for field in ("c", "d"):
        text = row["claims"] if field == "c" else row["description"]
        for i, ids in enumerate(chunk_ids(enc(text), body, overlap)):
            out.append((field, i, ids))
    return out


@torch.no_grad()
def embed(model, tok, seqs, device, batch_tokens):
    pre = tok(PREFIX, add_special_tokens=False)["input_ids"]
    cls, sep = tok.cls_token_id, tok.sep_token_id
    full = [[cls] + pre + s + [sep] for s in seqs]
    order = np.argsort([-len(s) for s in full])
    vecs = np.zeros((len(full), 768), dtype=np.float32)
    i = 0
    while i < len(order):
        L = len(full[order[i]])
        n = max(1, batch_tokens // L)
        idx = order[i:i + n]
        ids = torch.zeros((len(idx), L), dtype=torch.long)
        mask = torch.zeros((len(idx), L), dtype=torch.long)
        for r, j in enumerate(idx):
            ids[r, :len(full[j])] = torch.tensor(full[j])
            mask[r, :len(full[j])] = 1
        ids, mask = ids.to(device), mask.to(device)
        h = model(input_ids=ids, attention_mask=mask).last_hidden_state.float()
        m = mask.unsqueeze(-1).float()
        v = (h * m).sum(1) / m.sum(1)
        v = F.layer_norm(v, (v.shape[1],))
        vecs[idx] = v.cpu().numpy()
        i += n
    return vecs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--texts", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-len", type=int, required=True, help="1000 или 2048, со служебными")
    ap.add_argument("--overlap", type=int, required=True)
    ap.add_argument("--app-ids", help="файл со списком app_id (по одному в строке) — подвыборка")
    ap.add_argument("--part-size", type=int, default=500)
    ap.add_argument("--batch-tokens", type=int, default=16384)
    a = ap.parse_args()

    torch.manual_seed(0)
    torch.use_deterministic_algorithms(True, warn_only=True)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32
    tok = AutoTokenizer.from_pretrained(MODEL, revision=REV)
    if a.max_len > 2048:
        raise SystemExit("max_len > 2048: модель обучена до 2048 (artifacts/build.md)")
    model = AutoModel.from_pretrained(MODEL, revision=REV, code_revision=CODE_REV,
                                      trust_remote_code=True, torch_dtype=dtype).to(device).eval()

    body = a.max_len - 4
    t = pq.read_table(a.texts, columns=["app_id", "title", "abstract", "claims", "description"]).to_pandas()
    if a.app_ids:
        keep = set(open(a.app_ids).read().split())
        t = t[t.app_id.isin(keep)]
    t = t.sort_values("app_id").reset_index(drop=True)
    os.makedirs(a.out, exist_ok=True)

    for p0 in range(0, len(t), a.part_size):
        name = f"{a.out}/part-{p0 // a.part_size:05d}"
        if os.path.exists(name + ".done"):
            continue
        meta, seqs = [], []
        for _, row in t.iloc[p0:p0 + a.part_size].iterrows():
            for field, i, ids in pieces(row, tok, body, a.overlap):
                meta.append((row["app_id"], field, i, len(ids)))
                seqs.append(ids)
        v = embed(model, tok, seqs, device, a.batch_tokens)
        pq.write_table(pa.table({"app_id": [m[0] for m in meta], "field": [m[1] for m in meta],
                                 "idx": [m[2] for m in meta], "n_tok": [m[3] for m in meta]}),
                       name + ".parquet")
        np.save(name + ".npy", v)
        open(name + ".done", "w").close()
        print(f"{name}: заявок {min(a.part_size, len(t) - p0)}, кусков {len(seqs)}, токенов {sum(len(s) for s in seqs)}", flush=True)

    h = hashlib.sha256()
    for f in sorted(glob.glob(f"{a.out}/part-*.npy")):
        h.update(np.load(f).tobytes())
    print("sha256 векторов:", h.hexdigest())


if __name__ == "__main__":
    main()

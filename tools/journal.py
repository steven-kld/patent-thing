#!/usr/bin/env python3
"""Единственный допустимый способ записи в journal.jsonl.

Рода записей — четыре (stages-v2 §10): заморозка, вскрытие, закрытие,
расхождение. Команд edit и delete нет и не должно появиться.

Что проверяется механически:

  общее
    * файл только дописывается: закоммиченное обязано быть префиксом рабочего
      файла (J5); незакоммиченный хвост — признак оборванного запуска;
    * id, ts, type, sha256, prev, role, trials, verdict ставит скрипт и из
      входа не принимает (J4): переданные снаружи — запись задним числом
      либо роль/вердикт, назначенные после того, как число стало известно;
    * один коммит на запись, артефакт входит в тот же коммит (J5);
    * experiment ссылается на существующую заморозку Proposal; у самой
      заморозки Proposal пуст (§10.1);
    * refs — целые id существующих записей.

  заморозка (§10.2, U2, S3, S4, A1)
    * артефакт существует, лежит внутри репозитория, sha256 считает скрипт;
    * prev = sha256 артефакта предыдущей стадии, берётся из действующей
      заморозки; пусто только у Proposal;
    * действующая заморозка стадии одна: вторая допустима только после
      расхождения, убившего первую;
    * восстановление обнулённой стадии — тем же sha256 и со ссылкой на
      расхождение, которое её убило (S4);
    * у стадии Protocol артефакт разбирается как JSON и проверяется по схеме
      (notes/protocol-schema.md): F1–F14.

  вскрытие (§10.3, E1, E3, E7, E8, E9, E19, C2, O8)
    * роль читается из артефакта Lockbox, из входа не принимается;
    * у разведочного: claim генерируется машиной (J3), verdict и trials пусты;
    * у подтверждающего: ящик вскрывается один раз; набор ключей values обязан
      совпадать с объявленным в Protocol точно; хеши оценщиков сверяются;
      trials вычисляется и обязан быть 1; вердикт вычисляется правилом;
      бюджет подтверждений выведен из потолка семейного риска.

  расхождение (§10.5, S3)
    * invalidates перечисляет стадии; каскад на старшие считает скрипт.

Отказ — результат работы, а не сбой.

Использование:
    journal.py freeze   < payload.json
    journal.py open     < payload.json
    journal.py close    < payload.json
    journal.py diverge  < payload.json
    journal.py verify
    journal.py next-id
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from statistics import NormalDist

JOURNAL = "journal.jsonl"
TZ = timezone(timedelta(hours=4))  # Тбилиси

STAGES = ["Proposal", "Manifest", "Universe", "Lockbox", "Protocol",
          "Build", "Tearsheet", "Incubation", "Registry"]
STEPS = {"Proposal": "1–6", "Manifest": "7–11", "Universe": "12–15",
         "Lockbox": "16–20", "Protocol": "21–26", "Build": "27–30",
         "Tearsheet": "31–36", "Incubation": "37–39", "Registry": "40–41"}

KINDS = {"заморозка", "вскрытие", "закрытие", "расхождение"}
ROLES = {"разведка", "подтверждение"}
VERDICTS = {"принято", "отвергнуто", "н/п"}
TAKES = {"point", "ci_low", "ci_high"}
OPS = {">", ">=", "<", "<="}

SET_BY_SCRIPT = {"id", "ts", "type", "sha256", "prev", "role", "trials", "verdict"}

N = NormalDist()


class Refused(Exception):
    pass


# --------------------------------------------------------------------------- git


def git(*args: str, check: bool = True) -> str:
    p = subprocess.run(["git", *args], capture_output=True, text=True)
    if check and p.returncode != 0:
        raise Refused(f"git {' '.join(args)}: {p.stderr.strip()}")
    return p.stdout


def repo_root() -> Path:
    return Path(git("rev-parse", "--show-toplevel").strip())


def head_journal(root: Path) -> str:
    """Содержимое journal.jsonl в HEAD. Пустая строка, если файла там ещё нет."""
    p = subprocess.run(["git", "show", f"HEAD:{JOURNAL}"],
                       capture_output=True, text=True, cwd=root)
    return p.stdout if p.returncode == 0 else ""


def working_tree_dirty_elsewhere(root: Path) -> list[str]:
    out = git("-C", str(root), "status", "--porcelain")
    return [l[3:] for l in out.splitlines() if l[3:].strip() and l[3:].strip() != JOURNAL]


# ------------------------------------------------------------------- целостность


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_journal(root: Path) -> list[dict]:
    path = root / JOURNAL
    if not path.exists():
        return []
    out = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise Refused(f"строка {i} журнала не разбирается как JSON: {e}")
    return out


def check_append_only(root: Path) -> None:
    committed = head_journal(root)
    if not committed:
        return
    path = root / JOURNAL
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    if not current.startswith(committed):
        raise Refused(
            "рабочий journal.jsonl не является продолжением закоммиченного: "
            "существующие строки изменены или удалены. Записи не будет. "
            "Разберись через `git diff -- journal.jsonl`."
        )


def check_uncommitted_entries(root: Path) -> None:
    committed = head_journal(root)
    path = root / JOURNAL
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    if len(current) > len(committed):
        raise Refused(
            "в journal.jsonl есть незакоммиченные строки. Скрипт коммитит каждую "
            "запись сам, значит прошлый запуск оборвался или файл правили в обход. "
            "Разберись вручную."
        )


def is_legacy(e: dict) -> bool:
    """Запись прошлой схемы: event=register/result, рода из KINDS у неё нет."""
    return "event" in e or e.get("type") not in KINDS


def current(entries: list[dict]) -> list[dict]:
    return [e for e in entries if not is_legacy(e)]


def in_repo(root: Path, raw: str) -> Path:
    p = Path(raw)
    if not p.is_absolute():
        p = root / p
    if not p.exists():
        raise Refused(f"файла нет по пути {p}")
    try:
        p.resolve().relative_to(root.resolve())
    except ValueError:
        raise Refused(
            f"{raw} лежит вне репозитория. Артефакт, до которого не дотянуться, "
            "артефактом не является (§10.2)."
        )
    return p


# ------------------------------------------------------------------ состояние


def experiment_of(e: dict) -> int | None:
    if e.get("type") == "заморозка" and e.get("stage") == "Proposal":
        return e["id"]
    exp = e.get("experiment")
    return exp if isinstance(exp, int) else None


def entries_of(entries: list[dict], exp: int) -> list[dict]:
    return [e for e in current(entries) if experiment_of(e) == exp]


def stage_state(entries: list[dict], exp: int) -> tuple[dict, dict]:
    """Действующие заморозки по стадиям и обнулённые (S1, S3, U2)."""
    active: dict[str, dict] = {}
    killed: dict[str, dict] = {}
    for e in entries_of(entries, exp):
        if e["type"] == "заморозка":
            active[e["stage"]] = e
            killed.pop(e["stage"], None)
        elif e["type"] == "расхождение":
            inv = e.get("invalidates") or []
            if not inv:
                continue
            first = min(STAGES.index(s) for s in inv)
            for s in STAGES[first:]:
                if s in active:
                    killed[s] = {"sha256": active[s]["sha256"], "by": e["id"]}
                    del active[s]
    return active, killed


def promoted(entries: list[dict], exp: int) -> int:
    return sum(1 for e in entries_of(entries, exp)
               if e["type"] == "вскрытие" and e.get("role") == "подтверждение")


def confirming_boxes_opened(entries: list[dict], exp: int) -> set[tuple[str, str]]:
    return {(e["lockbox"]["freeze"], e["lockbox"]["box"])
            for e in entries_of(entries, exp)
            if e["type"] == "вскрытие" and e.get("role") == "подтверждение"}


# ----------------------------------------------------------------- выражения


def _unit_mul(a: dict, b: dict, sign: int = 1) -> dict:
    out = dict(a)
    for k, v in b.items():
        out[k] = out.get(k, 0) + sign * v
    return {k: v for k, v in out.items() if v != 0}


def unit_str(u: dict) -> str:
    return " ".join(f"{k}^{v:g}" for k, v in sorted(u.items())) or "1"


def _eval(node, resolve):
    """Значение и размерность выражения. Ни вызовов, ни условий, ни сравнений (P2)."""
    if isinstance(node, ast.Expression):
        return _eval(node.body, resolve)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
            and not isinstance(node.value, bool):
        return float(node.value), {}
    if isinstance(node, ast.Name):
        return resolve(node.id)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        v, u = _eval(node.operand, resolve)
        return (-v if isinstance(node.op, ast.USub) else v), u
    if isinstance(node, ast.BinOp):
        lv, lu = _eval(node.left, resolve)
        rv, ru = _eval(node.right, resolve)
        op = node.op
        if isinstance(op, ast.Mult):
            return lv * rv, _unit_mul(lu, ru)
        if isinstance(op, ast.Div):
            if rv == 0:
                raise Refused("деление на ноль в выражении")
            return lv / rv, _unit_mul(lu, ru, -1)
        if isinstance(op, (ast.Add, ast.Sub)):
            if lu != ru:
                raise Refused(
                    f"складываются разные размерности: {unit_str(lu)} и {unit_str(ru)}")
            return (lv + rv if isinstance(op, ast.Add) else lv - rv), lu
        if isinstance(op, ast.Pow):
            if ru:
                raise Refused(f"показатель степени с размерностью {unit_str(ru)}")
            return lv ** rv, {k: v * rv for k, v in lu.items()}
    raise Refused(
        "в выражении допустимы только имена, числа и + − * / ** — "
        "ни вызовов, ни условий, ни дизъюнкции (P2)"
    )


def parse_expr(src: str):
    try:
        return ast.parse(str(src), mode="eval")
    except SyntaxError as e:
        raise Refused(f"выражение не разбирается: {src!r} ({e})")


def unit_of(src: str) -> dict:
    v, u = _eval(parse_expr(src), lambda n: (1.0, {n: 1}))
    if abs(v - 1.0) > 1e-12:
        raise Refused(f"единица измерения не может содержать множитель: {src!r}")
    return u


# ------------------------------------------------------------------- Protocol


def _need(d: dict, key: str, where: str):
    if key not in d or d[key] in ("", None):
        raise Refused(f"в {where} не заполнено обязательное поле {key!r} (A5)")
    return d[key]


def load_protocol(root: Path, freeze: dict) -> dict:
    path = in_repo(root, freeze["artifact"]["path"])
    digest = sha256_file(path)
    if digest != freeze["sha256"]:
        raise Refused(
            f"артефакт Protocol изменён после заморозки: в записи №{freeze['id']} "
            f"{freeze['sha256']}, у файла {digest}. Артефакт неизменяем (A1)."
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise Refused(f"артефакт Protocol не разбирается как JSON: {e}")


def resolve_constants(prot: dict) -> dict[str, tuple[float, dict]]:
    """Пересчёт выведенных констант и их размерностей (V2, P6)."""
    decl = prot.get("constants")
    if not isinstance(decl, list):
        raise Refused("constants обязан быть списком (может быть пустым)")
    env: dict[str, tuple[float, dict]] = {}
    for c in decl:
        name = _need(c, "name", "constants")
        unit = unit_of(_need(c, "unit", f"константе {name}"))
        prov = _need(c, "provenance", f"константе {name}")
        if prov not in {"назначено", "выведено", "измерено"}:
            raise Refused(
                f"{name}: provenance — назначено | выведено | измерено, получено {prov!r}")
        if "value" not in c:
            raise Refused(f"{name}: нет value")
        value = float(c["value"])
        if prov == "выведено":
            expr = _need(c, "derivation", f"константе {name}")
            got, gu = _eval(parse_expr(expr), lambda n: _lookup(env, n, name))
            if abs(got - value) > 1e-9 * max(1.0, abs(value)):
                raise Refused(
                    f"{name}: выведенное значение не сходится. "
                    f"{expr} = {got:g}, в документе {value:g} (V2)")
            if gu != unit:
                raise Refused(
                    f"{name}: размерность вывода {unit_str(gu)} не равна "
                    f"объявленной {unit_str(unit)} (P6)")
        elif prov == "назначено":
            if not str(c.get("basis", "")).strip():
                raise Refused(
                    f"{name}: назначенное число обязано иметь basis с автором. "
                    "Абсолютное число без автора — угадывание (P7)")
        else:
            src = c.get("source") or {}
            if not isinstance(src, dict) or "entry" not in src or "artifact_sha256" not in src:
                raise Refused(
                    f"{name}: измеренная константа обязана нести source "
                    "{entry, artifact_sha256} (P8)")
        env[name] = (value, unit)
    return env


def _lookup(env: dict, name: str, who: str):
    if name not in env:
        raise Refused(f"{who}: имя {name!r} не объявлено в constants")
    return env[name]


def validate_protocol(root: Path, prot: dict, lockbox: dict, entries: list[dict],
                      exp: int) -> dict:
    """F1–F14. Возвращает вычисленные trials, α, бюджет и сопутствующие числа."""
    consts = resolve_constants(prot)

    quantities = prot.get("quantities")
    if not isinstance(quantities, dict) or not quantities:
        raise Refused("quantities обязан быть непустым объектом")

    slices = prot.get("slices")
    if not isinstance(slices, list):
        raise Refused("slices обязан быть списком (может быть пустым, O7)")
    slice_ids = []
    bearing = []
    for s in slices:
        sid = _need(s, "id", "срезе")
        _need(s, "definition", f"срезе {sid}")
        if "bears_verdict" not in s or not isinstance(s["bears_verdict"], bool):
            raise Refused(f"срез {sid}: bears_verdict обязан быть true или false (O7)")
        slice_ids.append(sid)
        if s["bears_verdict"]:
            bearing.append(sid)
    if len(bearing) > 1:
        raise Refused(
            f"срезов, способных вынести вердикт, {len(bearing)}: {bearing}. "
            "Испытаний столько же (O7), а у подтверждающего вскрытия их обязан быть 1")
    verdict_population = bearing[0] if bearing else "verdict_box"

    # величины
    for name, q in quantities.items():
        unit_of(_need(q, "unit", f"величине {name}"))
        pop = _need(q, "population", f"величине {name}")
        if pop != "verdict_box" and pop not in slice_ids:
            raise Refused(
                f"{name}: population {pop!r} — ни verdict_box, ни объявленный срез (A3)")
        if q.get("better") not in {"higher", "lower"}:
            raise Refused(f"{name}: better — higher | lower (P10, P11)")
        rng = q.get("range")
        if not (isinstance(rng, list) and len(rng) == 2):
            raise Refused(f"{name}: range обязан быть [низ, верх], null — неограниченно")
        est = q.get("estimator") or {}
        for k in ("spec", "path", "sha256"):
            _need(est, k, f"estimator величины {name}")
        ep = in_repo(root, est["path"])
        got = sha256_file(ep)
        if got != est["sha256"]:
            raise Refused(
                f"{name}: оценщик {est['path']} не сходится с объявленным хешем. "
                f"в документе {est['sha256']}, у файла {got} (A4, P4)")
        unc = q.get("uncertainty")
        if unc is not None:
            for k in ("method", "dependence", "level"):
                _need(unc, k, f"uncertainty величины {name}")
            if not isinstance(unc["dependence"], dict):
                raise Refused(
                    f"{name}: uncertainty.dependence обязан быть объектом. "
                    "Умолчания нет: молчание читалось бы как «наблюдения независимы» "
                    "(P5, E13)")
            if not 0 < float(unc["level"]) < 1:
                raise Refused(f"{name}: uncertainty.level вне (0, 1)")

    # кандидаты и ящики
    cands = prot.get("verdict_candidates")
    if not isinstance(cands, list) or not cands:
        raise Refused("verdict_candidates обязан быть непустым списком (E8)")
    boxes = prot.get("verdict_box")
    if not isinstance(boxes, list) or not boxes:
        raise Refused("verdict_box обязан быть непустым списком")
    lb_sha = lockbox["sha256"]
    for b in boxes:
        if b.get("lockbox_sha256") != lb_sha:
            raise Refused(
                f"verdict_box ссылается на заморозку Lockbox {b.get('lockbox_sha256')}, "
                f"а действующая — {lb_sha} (A2)")
        role = box_role(root, lockbox, b.get("box", ""))
        if role != "подтверждение":
            raise Refused(
                f"ящик {b.get('box')!r} имеет роль {role!r}. Вердикт выносится "
                "только на подтверждающем (E9)")
    agg = prot.get("aggregate")
    if len(boxes) > 1:
        if not isinstance(agg, dict) or not str(agg.get("expr", "")).strip():
            raise Refused(
                "ящиков больше одного: aggregate обязателен, иначе вердикт может "
                "вынести любое окно и испытаний столько же (шаг 23, O7)")
        independence_ref(root, lockbox, agg.get("independence"),
                         "aggregate по нескольким ящикам (E13)")
    elif agg:
        raise Refused("aggregate при одном ящике не имеет смысла")

    # отбор кандидата
    sel = prot.get("selection") or {}
    sbox = sel.get("box") or {}
    if sbox.get("lockbox_sha256") != lb_sha:
        raise Refused("selection.box ссылается не на действующую заморозку Lockbox")
    srole = box_role(root, lockbox, sbox.get("box", ""))
    if srole != "разведка":
        raise Refused(
            f"selection.box {sbox.get('box')!r} имеет роль {srole!r}: отбор ведётся "
            "на разведке (E14, E15)")
    if (sbox.get("lockbox_sha256"), sbox.get("box")) in \
            {(b["lockbox_sha256"], b["box"]) for b in boxes}:
        raise Refused("selection.box и verdict_box — один ящик (E15)")
    obj = str(_need(sel, "objective", "selection"))
    parts = obj.split()
    if len(parts) != 2 or parts[0] not in {"argmax", "argmin"} or parts[1] not in quantities:
        raise Refused(
            "selection.objective — формула вида «argmax <величина>» над объявленной "
            f"величиной, а не суждение (E6). Получено: {obj!r}")
    space = sel.get("space")
    if not isinstance(space, dict) or not space:
        raise Refused("selection.space обязан быть непустым объектом: перечислимое "
                      "пространство перебора (E6)")
    space_ids = space_members(space)
    outside = [c for c in cands if c not in space_ids]
    if outside:
        raise Refused(
            f"кандидаты {outside} не принадлежат объявленному пространству перебора. "
            "Подкрутить победителя после перебора — вынести с разведки больше, "
            "чем там было (E6)")

    # правило
    rule = prot.get("decision_rule") or {}
    clauses = rule.get("all")
    if not isinstance(clauses, list) or not clauses:
        raise Refused("decision_rule.all обязан быть непустым списком клауз (E9)")
    if set(rule) - {"all"}:
        raise Refused(
            f"в decision_rule допустим только all: {sorted(set(rule) - {'all'})} — "
            "дизъюнкция выражается числом кандидатов или срезов, где она считается (P2)")

    alphas, reports = [], []
    for i, cl in enumerate(clauses, 1):
        where = f"клаузе {i}"
        left = cl.get("left") or {}
        qname = _need(left, "quantity", where)
        if qname not in quantities:
            raise Refused(f"{where}: величина {qname!r} не объявлена (F1)")
        q = quantities[qname]
        take = _need(left, "take", where)
        if take not in TAKES:
            raise Refused(f"{where}: take — point | ci_low | ci_high, умолчания нет")
        op = _need(cl, "op", where)
        if op not in OPS:
            raise Refused(f"{where}: op — один из {sorted(OPS)}")
        right = cl.get("right") or {}
        if set(right) != {"const"}:
            raise Refused(
                f"{where}: right обязан быть {{const: имя}}. Сравнение двух величин "
                "требует их ковариации, которой Protocol не объявляет: парную разность "
                "объявляют отдельной величиной со своим нулём")
        cname = right["const"]
        cval, cunit = _lookup(consts, cname, where)
        cprov = next(c["provenance"] for c in prot["constants"] if c["name"] == cname)
        if cprov == "измерено":
            raise Refused(
                f"{where}: константа {cname} измерена. Правило, сравнивающее результат "
                "с числом, измеренным на разведке, — это E3 наизнанку (F3, P8)")
        qunit = unit_of(q["unit"])
        if qunit != cunit:
            raise Refused(
                f"{where}: размерности не сходятся — {qname} в {unit_str(qunit)}, "
                f"{cname} в {unit_str(cunit)} (P9)")
        if q["population"] != verdict_population:
            raise Refused(
                f"{where}: {qname} живёт на популяции {q['population']!r}, а вердикт "
                f"выносится на {verdict_population!r} (O7)")
        up = op in {">", ">="}
        if (q["better"] == "higher") != up:
            raise Refused(
                f"{where}: {qname} лучше когда {q['better']}, а клауза требует "
                f"{op}. Направление перевёрнуто (P11)")
        bad = "ci_high" if q["better"] == "higher" else "ci_low"
        if take == bad:
            raise Refused(
                f"{where}: при better={q['better']} консервативный конец — "
                f"{'ci_low' if q['better'] == 'higher' else 'ci_high'}, а взят {take}. "
                "С неконсервативного конца размер правила уходит к 0,975 (P10)")
        if take != "point" and not q.get("uncertainty"):
            raise Refused(f"{where}: take={take} при необъявленной uncertainty у {qname}")

        nul = q.get("null")
        if not isinstance(nul, dict):
            raise Refused(
                f"{qname}: величина входит в правило, значит обязана объявить null "
                "со значением и дисперсией — иначе размер правила не вычисляется (F9)")
        if nul.get("kind") not in {"mathematical", "measured"}:
            raise Refused(f"{qname}: null.kind — mathematical | measured")
        if "value" not in nul:
            raise Refused(f"{qname}: в null нет value")
        mu0 = float(nul["value"])
        sd_ref = (nul.get("dispersion") or {}).get("sd")
        if not isinstance(sd_ref, dict) or set(sd_ref) != {"const"}:
            raise Refused(
                f"{qname}: null.dispersion.sd обязан быть {{const: имя}} — "
                "из него вычисляется α (F10, P18)")
        sd, sdunit = _lookup(consts, sd_ref["const"], f"null величины {qname}")
        if sdunit != qunit:
            raise Refused(
                f"{qname}: размерность дисперсии нуля {unit_str(sdunit)} не равна "
                f"размерности величины {unit_str(qunit)} (P9)")
        if sd <= 0:
            raise Refused(f"{qname}: дисперсия нуля обязана быть положительной")

        z = 0.0 if take == "point" else N.inv_cdf(1 - (1 - float(q["uncertainty"]["level"])) / 2)
        k = -z if take == "ci_low" else (z if take == "ci_high" else 0.0)
        t = (cval - k * sd - mu0) / sd
        a = 1 - N.cdf(t) if up else N.cdf(t)
        alphas.append(a)

        det = cval - k * sd + (N.inv_cdf(0.8) * sd if up else -N.inv_cdf(0.8) * sd)
        reports.append(f"  клауза {i}: {qname}.{take} {op} {cname}={cval:g} "
                       f"→ α = {a:.4g}; мощность 0,8 против {det:g} {unit_str(qunit)}")

        lo, hi = rng = quantities[qname]["range"]
        if lo is not None and hi is not None and hi > lo:
            share = (hi - cval) / (hi - lo) if up else (cval - lo) / (hi - lo)
            share = min(max(share, 0.0), 1.0)
            reports.append(f"           принимает {share:.1%} объявленного диапазона")
            if share >= 1.0:
                raise Refused(
                    f"{where}: правило принимает весь объявленный диапазон {rng} — "
                    "формально валидно и не значит ничего (§7)")

    alpha = min(alphas)

    # множественность и бюджет
    mult = prot.get("multiplicity") or {}
    dep = mult.get("dependence")
    if dep not in {"unknown", "independent"}:
        raise Refused("multiplicity.dependence — unknown | independent (P12)")
    comb = mult.get("combine")
    if comb not in {"union_bound", "independent"}:
        raise Refused("multiplicity.combine — union_bound | independent")
    if comb == "independent":
        if dep != "independent":
            raise Refused(
                "combine=independent при dependence=unknown: произведение "
                "предполагает независимость испытаний, а необъявленная независимость "
                "считается отсутствующей (E13, P12)")
        independence_ref(root, lockbox, mult.get("independence"),
                         "combine=independent (E13)")
    ceil_ref = mult.get("ceiling")
    if not isinstance(ceil_ref, dict) or set(ceil_ref) != {"const"}:
        raise Refused("multiplicity.ceiling обязан быть {const: имя}")
    ceiling, cu = _lookup(consts, ceil_ref["const"], "multiplicity.ceiling")
    if cu:
        raise Refused(f"потолок семейного риска безразмерен, объявлен в {unit_str(cu)}")
    cprov = next(c["provenance"] for c in prot["constants"] if c["name"] == ceil_ref["const"])
    if cprov != "назначено":
        raise Refused(
            "потолок семейного риска обязан быть назначен автором: из него выводится "
            "число попыток. Выведенный потолок оставляет бюджет без предка (F11, 4.3)")
    if not 0 < ceiling < 1:
        raise Refused("потолок семейного риска вне (0, 1)")

    if alpha <= 0.0:
        raise Refused(
            "размер правила ушёл в машинный нуль: порог отстоит от нуля больше чем "
            "на ~8 дисперсий. Обычно это не строгость, а ошибка в единицах или в "
            "дисперсии нуля — проверь их раньше, чем бюджет (P9, P18)")
    if family_risk(alpha, 1, comb) > ceiling:
        raise Refused(
            f"α = {alpha:.4g} превосходит потолок {ceiling:g} уже при одном "
            "подтверждении: правило слишком слабое, чтобы его стоило проверять (F10)")
    budget = budget_from_ceiling(alpha, ceiling, comb)

    trials = len(cands) * max(1, len(bearing)) * (1 if agg else len(boxes))
    if trials != 1:
        raise Refused(
            f"trials = {trials} (кандидатов {len(cands)}, срезов с вердиктом "
            f"{len(bearing)}, ящиков {len(boxes)}). У подтверждающего вскрытия "
            "обязан быть 1: вердикт может вынести ровно одно сравнение (§10.3, E8)")

    return {"alpha": alpha, "ceiling": ceiling, "combine": comb, "budget": budget,
            "trials": trials, "promoted": promoted(entries, exp), "reports": reports,
            "verdict_population": verdict_population,
            "expected_keys": expected_keys(quantities)}


def space_members(space: dict) -> set[str]:
    """Имена кандидатов, которые объявленное пространство перебора содержит."""
    out: set[str] = set()
    for v in space.values():
        if isinstance(v, list):
            out |= {str(x) for x in v}
        else:
            out.add(str(v))
    return out


def expected_keys(quantities: dict) -> set[str]:
    keys = set()
    for name, q in quantities.items():
        keys.add(f"{name}.point")
        if q.get("uncertainty"):
            keys |= {f"{name}.ci_low", f"{name}.ci_high"}
    return keys


def family_risk(alpha: float, n: int, combine: str) -> float:
    return min(1.0, n * alpha) if combine == "union_bound" else 1 - (1 - alpha) ** n


def budget_from_ceiling(alpha: float, ceiling: float, combine: str) -> int:
    """Наибольшее n, при котором семейный риск ещё не превышает потолок (4.3).

    Считается формулой, а не перебором: у строгого правила α бывает 1e-10, и
    перебор ушёл бы на сотни миллионов шагов.
    """
    if combine == "union_bound":
        n = int(ceiling // alpha)
    else:
        n = int(math.log1p(-ceiling) / math.log1p(-alpha))
    while n > 1 and family_risk(alpha, n, combine) > ceiling:
        n -= 1
    while family_risk(alpha, n + 1, combine) <= ceiling:
        n += 1
    return max(1, n)


def lockbox_artifact(root: Path, freeze: dict) -> dict:
    path = in_repo(root, freeze["artifact"]["path"])
    if sha256_file(path) != freeze["sha256"]:
        raise Refused(
            f"артефакт Lockbox изменён после заморозки №{freeze['id']}. Неизменяем (A1)")
    try:
        art = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise Refused(
            "артефакт Lockbox обязан быть JSON с объектом boxes: роль ящика читается "
            f"из него, а не принимается из входа (J4, E1). {e}")
    if not isinstance(art.get("boxes"), dict) or not art["boxes"]:
        raise Refused("в артефакте Lockbox нет непустого объекта boxes")
    return art


def box_role(root: Path, freeze: dict, box: str) -> str:
    art = lockbox_artifact(root, freeze)
    if box not in art["boxes"]:
        raise Refused(
            f"ящика {box!r} нет в заморозке Lockbox №{freeze['id']}: "
            f"объявлены {sorted(art['boxes'])}")
    role = (art["boxes"][box] or {}).get("role")
    if role not in ROLES:
        raise Refused(f"ящик {box!r}: роль {role!r} — ожидается одна из {sorted(ROLES)}")
    return role


def independence_ref(root: Path, freeze: dict, ref, who: str) -> float:
    if not isinstance(ref, dict) or set(ref) != {"lockbox_key"}:
        raise Refused(
            f"{who} обязан сослаться на меру независимости из Lockbox: "
            "{lockbox_key: имя}. Необъявленная независимость считается "
            "отсутствующей (E13)")
    art = lockbox_artifact(root, freeze)
    key = ref["lockbox_key"]
    if key not in (art.get("independence") or {}):
        raise Refused(
            f"{who}: в артефакте Lockbox нет independence[{key!r}]. Мера независимости "
            "измеряется и записывается, а не предполагается (E13)")
    return float(art["independence"][key])


# ------------------------------------------------------------------ проверки входа


def reject_script_fields(payload: dict) -> None:
    stray = SET_BY_SCRIPT & payload.keys()
    if stray:
        raise Refused(
            f"поля {sorted(stray)} ставит скрипт, а не вызывающий (J4). Переданные "
            "снаружи — это запись задним числом либо роль и вердикт, назначенные "
            "после того, как число стало известно"
        )


def check_claim(payload: dict) -> str:
    claim = str(_need(payload, "claim", "записи")).strip()
    if len(claim.split()) < 4:
        raise Refused("claim слишком короткий: нужно утверждение, а не тема (J3)")
    return claim


def check_refs(payload: dict, entries: list[dict], required: bool) -> list[int]:
    refs = payload.get("refs") or []
    if required and not refs:
        raise Refused("refs обязателен: запись связывает себя с тем, что уже записано")
    if not isinstance(refs, list) or any(not isinstance(r, int) for r in refs):
        raise Refused("refs — список целых id")
    known = {e["id"] for e in entries}
    missing = [r for r in refs if r not in known]
    if missing:
        raise Refused(f"refs ссылается на несуществующие записи: {missing}")
    return refs


def check_stage(payload: dict) -> str:
    stage = _need(payload, "stage", "записи")
    if stage not in STAGES:
        raise Refused(f"stage — одна из {STAGES}")
    return stage


def check_experiment(payload: dict, entries: list[dict], is_proposal: bool) -> int | None:
    props = [e["id"] for e in current(entries)
             if e["type"] == "заморозка" and e["stage"] == "Proposal"]
    if is_proposal:
        if payload.get("experiment"):
            raise Refused(
                "у заморозки Proposal experiment пуст: она себя и определяет (§10.1)")
        return None
    exp = payload.get("experiment")
    if not isinstance(exp, int):
        raise Refused(
            "experiment — id заморозки Proposal, к которой относится событие. "
            f"В журнале есть: {props or 'ни одной — начни с заморозки Proposal'}")
    if exp not in props:
        raise Refused(f"запись №{exp} не является заморозкой Proposal. Есть: {props}")
    return exp


# --------------------------------------------------------------------- запись


def append_and_commit(root: Path, entry: dict, message: str,
                      extra: list[Path] | None = None) -> None:
    # extra добавляется до записи строки: если git откажет, журнал останется
    # нетронутым, а не с незакоммиченным хвостом
    for p in extra or []:
        git("-C", str(root), "add", "--", str(p.resolve().relative_to(root.resolve())))
    line = json.dumps(entry, ensure_ascii=False, sort_keys=True)
    with (root / JOURNAL).open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    git("-C", str(root), "add", "--", JOURNAL)
    git("-C", str(root), "commit", "-m", message)


def preamble(root: Path) -> list[dict]:
    entries = load_journal(root)
    check_append_only(root)
    check_uncommitted_entries(root)
    return entries


def new_id(entries: list[dict]) -> int:
    return max([e.get("id", 0) for e in entries], default=0) + 1


def now() -> str:
    return datetime.now(TZ).isoformat(timespec="milliseconds")


def warn_dirty(root: Path) -> None:
    dirty = working_tree_dirty_elsewhere(root)
    if dirty:
        print("! рабочее дерево грязное помимо журнала: " + ", ".join(dirty),
              file=sys.stderr)


# --------------------------------------------------------------------- команды


def cmd_freeze(root: Path) -> None:
    payload = json.load(sys.stdin)
    entries = preamble(root)
    reject_script_fields(payload)
    stage = check_stage(payload)
    claim = check_claim(payload)
    exp = check_experiment(payload, entries, stage == "Proposal")
    refs = check_refs(payload, entries, required=False)

    art = payload.get("artifact")
    if not isinstance(art, dict) or "path" not in art or set(art) != {"path"}:
        raise Refused("artifact — объект с единственным полем path; sha256 считает скрипт")
    path = in_repo(root, art["path"])
    digest = sha256_file(path)

    if stage == "Proposal":
        prev, active, killed = "", {}, {}
        # тот же вопрос под новым id обнулил бы promoted, а счётчик обнуляет
        # только отказ от вопроса (C5)
        for other in (e["id"] for e in current(entries)
                      if e["type"] == "заморозка" and e["stage"] == "Proposal"):
            _, other_killed = stage_state(entries, other)
            if other_killed.get("Proposal", {}).get("sha256") == digest:
                raise Refused(
                    f"та же посылка уже была заморожена как эксперимент №{other} и "
                    f"обнулена записью №{other_killed['Proposal']['by']}. Новая "
                    "заморозка того же sha256 дала бы новый experiment и обнулила "
                    "promoted, а его обнуляет только отказ от вопроса (C5). "
                    "Либо вопрос изменился — тогда изменится и артефакт, — либо "
                    "счётчик обязан остаться прежним"
                )
    else:
        active, killed = stage_state(entries, exp)
        idx = STAGES.index(stage)
        prev_stage = None
        for s in reversed(STAGES[:idx]):
            if s in active:
                prev_stage = s
                break
            if not any(e["type"] == "закрытие" and e["stage"] == s
                       for e in entries_of(entries, exp)):
                raise Refused(
                    f"стадия {s} не заморожена и не объявлена недоступной записью "
                    f"закрытия. {stage} не может стоять на непройденной стадии (S2)")
        if prev_stage is None:
            raise Refused(f"ни одна стадия раньше {stage} не заморожена")
        prev = active[prev_stage]["sha256"]

        if stage in active:
            raise Refused(
                f"у стадии {stage} уже есть действующая заморозка №{active[stage]['id']}. "
                "Вторая допустима только после расхождения, убившего первую (U2, A1)")
        if stage in killed:
            if digest == killed[stage]["sha256"]:
                if killed[stage]["by"] not in refs:
                    raise Refused(
                        f"восстановление {stage} тем же sha256 требует refs на "
                        f"расхождение №{killed[stage]['by']}, которое её убило (S4)")
            elif killed[stage]["by"] not in refs:
                print(f"! {stage} была обнулена записью №{killed[stage]['by']}, новый "
                      "sha256 не совпадает: это обычная новая заморозка, старшие "
                      "стадии остаются непройденными (S4)", file=sys.stderr)

    report = None
    if stage == "Protocol":
        if "Lockbox" not in (active or {}):
            raise Refused("Protocol замораживается на действующей заморозке Lockbox")
        if path.suffix != ".json":
            raise Refused(
                "артефакт Protocol обязан быть .json: из него вычисляются вердикт, "
                "trials и α (notes/protocol-schema.md)")
        try:
            prot = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise Refused(f"артефакт Protocol не разбирается как JSON: {e}")
        report = validate_protocol(root, prot, active["Lockbox"], entries, exp)
        if report["promoted"] >= report["budget"]:
            raise Refused(
                f"подтверждений уже {report['promoted']}, выведенный бюджет "
                f"{report['budget']}. Правило остановки исчерпано до заморозки: "
                "следующее подтверждение — новая гипотеза со своей ценой (F12)")

    entry = {"id": new_id(entries), "type": "заморозка", "ts": now(), "stage": stage,
             "claim": claim, "experiment": exp, "refs": refs,
             "artifact": {"path": art["path"]}, "sha256": digest, "prev": prev}
    append_and_commit(root, entry, f"journal: заморозка {stage} #{entry['id']}", [path])
    warn_dirty(root)
    print(json.dumps(entry, ensure_ascii=False, indent=2))
    if report:
        print(f"\nвыведено из Protocol (не поля, а следствия):", file=sys.stderr)
        for line in report["reports"]:
            print(line, file=sys.stderr)
        print(f"  α = {report['alpha']:.4g}; потолок {report['ceiling']:g}; "
              f"combine={report['combine']}\n"
              f"  бюджет подтверждений: {report['budget']} "
              f"(израсходовано {report['promoted']})\n"
              f"  trials = {report['trials']}; вердикт выносится на "
              f"{report['verdict_population']}\n"
              f"  ключи values подтверждающего вскрытия: "
              f"{sorted(report['expected_keys'])}", file=sys.stderr)


def cmd_open(root: Path) -> None:
    payload = json.load(sys.stdin)
    entries = preamble(root)
    reject_script_fields(payload)
    stage = check_stage(payload)
    exp = check_experiment(payload, entries, False)
    refs = check_refs(payload, entries, required=False)
    active, _ = stage_state(entries, exp)

    if "Lockbox" not in active:
        raise Refused("нет действующей заморозки Lockbox: вскрывать нечего")
    lb = payload.get("lockbox")
    if not isinstance(lb, dict) or set(lb) != {"freeze", "box"}:
        raise Refused("lockbox — объект {freeze: sha256 заморозки Lockbox, box: имя}")
    if lb["freeze"] != active["Lockbox"]["sha256"]:
        raise Refused(
            f"lockbox.freeze {lb['freeze']} не равен действующей заморозке Lockbox "
            f"{active['Lockbox']['sha256']}")
    role = box_role(root, active["Lockbox"], lb["box"])

    values = payload.get("values")
    if not isinstance(values, dict) or not values:
        raise Refused("values — непустой объект величина → число")
    bad = [k for k, v in values.items() if not isinstance(v, (int, float))
           or isinstance(v, bool)]
    if bad:
        raise Refused(f"в values не числа: {bad}")
    nonfinite = [k for k, v in values.items() if not math.isfinite(v)]
    if nonfinite:
        raise Refused(
            f"в values не конечные числа: {nonfinite}. Сравнение с ними молча даёт "
            "«отвергнуто», хотя это сломанный прогон: ему место в записи "
            "расхождения с вердиктом н/п, а не в отказе правила (E19)")

    art_paths: list[Path] = []
    art = payload.get("artifact")
    if art is not None and (not isinstance(art, dict) or set(art) != {"path"}):
        raise Refused(
            "artifact — объект с единственным полем path; sha256 считает скрипт")
    entry = {"id": new_id(entries), "type": "вскрытие", "ts": now(), "stage": stage,
             "experiment": exp, "refs": refs,
             "lockbox": {"freeze": lb["freeze"], "box": lb["box"]}, "role": role}

    if role == "разведка":
        if "claim" in payload:
            raise Refused(
                "claim разведочного вскрытия генерируется машиной: оно ничего не "
                "связывает, а требование писать триста фраз руками сделало бы "
                "неограниченную разведку ограниченной бумагой (J3)")
        entry["claim"] = (f"разведочное вскрытие {lb['box']}: "
                          f"{len(values)} величин, {', '.join(sorted(values))}")
        entry["trials"] = None
        entry["verdict"] = None
        entry["values"] = values
        if art is not None:
            p = in_repo(root, art["path"])
            entry["artifact"] = {"path": art["path"]}
            entry["sha256"] = sha256_file(p)
            art_paths.append(p)
    else:
        if (lb["freeze"], lb["box"]) in confirming_boxes_opened(entries, exp):
            raise Refused(
                f"ящик {lb['box']} уже вскрыт. Второе вскрытие — не «ещё одно "
                "испытание», а уничтожение ящика: это расхождение с invalidates "
                "на заморозку Lockbox, а не вскрытие (E7, E17, C2)")
        if "Protocol" not in active:
            raise Refused(
                "нет действующей заморозки Protocol: вердикт выводится правилом из "
                "неё, а не назначается (E9)")
        prot = load_protocol(root, active["Protocol"])
        rep = validate_protocol(root, prot, active["Lockbox"], entries, exp)
        if rep["trials"] != 1:
            raise Refused(f"trials = {rep['trials']}, а обязан быть 1 (§10.3)")
        if rep["promoted"] + 1 > rep["budget"]:
            raise Refused(
                f"подтверждений {rep['promoted']}, бюджет {rep['budget']}: правило "
                "остановки объявлено заранее и исчерпано. Следующее подтверждение — "
                "новая гипотеза со своей ценой (F12, 4.3)")
        if set(values) != rep["expected_keys"]:
            lack = sorted(rep["expected_keys"] - set(values))
            extra = sorted(set(values) - rep["expected_keys"])
            raise Refused(
                "набор ключей values не совпадает с объявленным в Protocol. "
                f"недостаёт: {lack}; лишние: {extra}. Недостающий ключ означает, что "
                "правило неприменимо, лишний — что посчитано не объявленное (§10.3, P5)"
            )
        if art is None:
            raise Refused("у подтверждающего вскрытия artifact обязателен (§10.3)")
        p = in_repo(root, art["path"])
        art_paths.append(p)
        claim = check_claim(payload)

        verdict = evaluate_rule(prot, values)
        entry["claim"] = claim
        entry["trials"] = rep["trials"]
        entry["values"] = values
        entry["verdict"] = verdict
        entry["artifact"] = {"path": art["path"]}
        entry["sha256"] = sha256_file(p)
        entry["alpha"] = rep["alpha"]
        entry["family_risk"] = family_risk(rep["alpha"], rep["promoted"] + 1,
                                           rep["combine"])
        entry["protocol_sha256"] = active["Protocol"]["sha256"]

    append_and_commit(root, entry, f"journal: вскрытие {lb['box']} #{entry['id']}",
                      art_paths)
    warn_dirty(root)
    print(json.dumps(entry, ensure_ascii=False, indent=2))
    if role == "подтверждение":
        print(f"\nящик израсходован. подтверждений: {promoted(load_journal(root), exp)}"
              f"; семейный риск {entry['family_risk']:.4g}", file=sys.stderr)


def evaluate_rule(prot: dict, values: dict) -> str:
    """Вердикт из values по правилу. Ничего, кроме конъюнкции клауз (E9, шаг 35)."""
    consts = resolve_constants(prot)
    for cl in prot["decision_rule"]["all"]:
        key = f"{cl['left']['quantity']}.{cl['left']['take']}"
        if key not in values:
            return "н/п"
        lhs = float(values[key])
        rhs = consts[cl["right"]["const"]][0]
        op = cl["op"]
        ok = (lhs > rhs if op == ">" else lhs >= rhs if op == ">="
              else lhs < rhs if op == "<" else lhs <= rhs)
        if not ok:
            return "отвергнуто"
    return "принято"


def cmd_close(root: Path) -> None:
    payload = json.load(sys.stdin)
    entries = preamble(root)
    reject_script_fields(payload)
    stage = check_stage(payload)
    claim = check_claim(payload)
    exp = check_experiment(payload, entries, False)
    refs = check_refs(payload, entries, required=False)
    entry = {"id": new_id(entries), "type": "закрытие", "ts": now(), "stage": stage,
             "claim": claim, "experiment": exp, "refs": refs}
    append_and_commit(root, entry, f"journal: закрытие #{entry['id']}")
    warn_dirty(root)
    print(json.dumps(entry, ensure_ascii=False, indent=2))


def cmd_diverge(root: Path) -> None:
    payload = json.load(sys.stdin)
    entries = preamble(root)
    reject_script_fields(payload)
    stage = check_stage(payload)
    claim = check_claim(payload)
    exp = check_experiment(payload, entries, False)
    refs = check_refs(payload, entries, required=True)

    inv = payload.get("invalidates")
    if inv is None or not isinstance(inv, list):
        raise Refused(
            "invalidates — список стадий, чьи артефакты перестали действовать; "
            "пустой список, если расхождение правит только текст (§10.5)")
    unknown = [s for s in inv if s not in STAGES]
    if unknown:
        raise Refused(f"в invalidates не стадии: {unknown}")
    active, _ = stage_state(entries, exp)
    absent = [s for s in inv if s not in active]
    if absent:
        raise Refused(f"стадии {absent} и так не имеют действующей заморозки")

    entry = {"id": new_id(entries), "type": "расхождение", "ts": now(), "stage": stage,
             "claim": claim, "experiment": exp, "refs": refs, "invalidates": inv}
    append_and_commit(root, entry, f"journal: расхождение #{entry['id']}")
    warn_dirty(root)
    print(json.dumps(entry, ensure_ascii=False, indent=2))
    if inv:
        first = min(STAGES.index(s) for s in inv)
        print("! обнулены и все старшие стадии (S3): "
              + ", ".join(s for s in STAGES[first:] if s in active), file=sys.stderr)


def cmd_next_id(root: Path) -> None:
    print(new_id(load_journal(root)))


def cmd_verify(root: Path) -> None:
    check_append_only(root)
    entries = load_journal(root)
    problems: list[str] = []

    ids = [e.get("id") for e in entries]
    if ids != list(range(1, len(ids) + 1)):
        problems.append("id не монотонны или есть пропуски")
    legacy = [e["id"] for e in entries if is_legacy(e)]
    if legacy:
        print(f"записей прошлой схемы: {len(legacy)} (id {legacy[0]}–{legacy[-1]}), "
              "не валидируются и в счётчики не входят")

    known = {e["id"] for e in entries}
    for e in current(entries):
        for r in e.get("refs") or []:
            if r not in known:
                problems.append(f"№{e['id']}: refs на несуществующую запись {r}")
        if e["type"] == "вскрытие" and e.get("role") == "разведка" and e.get("verdict"):
            problems.append(f"№{e['id']}: у разведочного вскрытия стоит вердикт (E3)")
        if e["type"] == "вскрытие" and e.get("role") == "подтверждение" \
                and e.get("verdict") not in VERDICTS:
            problems.append(
                f"№{e['id']}: вердикт {e.get('verdict')!r} вне "
                f"{sorted(VERDICTS)} — строку правили в обход скрипта")

    props = [e for e in current(entries)
             if e["type"] == "заморозка" and e["stage"] == "Proposal"]
    if not props:
        print("\nэксперимента нет. Следующий шаг: заморозка Proposal "
              f"(шаги {STEPS['Proposal']})")
    for p in props:
        exp = p["id"]
        active, killed = stage_state(entries, exp)
        print(f"\nэксперимент №{exp}: {p['claim'][:70]}")
        for s in STAGES:
            if s in active:
                print(f"  {s:<11} заморожен №{active[s]['id']}  {active[s]['sha256'][:12]}")
            elif s in killed:
                print(f"  {s:<11} ОБНУЛЕН записью №{killed[s]['by']} (S3/S4)")
        nxt = next((s for s in STAGES if s not in active), None)
        if nxt:
            print(f"  следующий шаг: {nxt} (шаги {STEPS[nxt]})")

        done = promoted(entries, exp)
        scouts = sum(1 for e in entries_of(entries, exp)
                     if e["type"] == "вскрытие" and e["role"] == "разведка")
        print(f"  promoted: {done}; вскрытий разведки: {scouts}")
        if "Protocol" in active:
            try:
                prot = load_protocol(root, active["Protocol"])
                rep = validate_protocol(root, prot, active["Lockbox"], entries, exp)
                print(f"  α = {rep['alpha']:.4g}; бюджет {rep['budget']}; "
                      f"семейный риск при {done} "
                      f"{family_risk(rep['alpha'], max(done, 1), rep['combine']):.4g}")
                for e in entries_of(entries, exp):
                    if e["type"] == "вскрытие" and e["role"] == "подтверждение":
                        again = evaluate_rule(prot, e["values"])
                        if again != e["verdict"]:
                            problems.append(
                                f"№{e['id']}: вердикт в журнале {e['verdict']!r}, "
                                f"правило действующего Protocol даёт {again!r}")
            except Refused as err:
                problems.append(f"действующий Protocol эксперимента №{exp}: {err}")

    if problems:
        print("\nПРОБЛЕМЫ:")
        for p in problems:
            print("  - " + p)
        sys.exit(1)
    print("\nнарушений не найдено")


def main() -> None:
    cmds = {"freeze": cmd_freeze, "open": cmd_open, "close": cmd_close,
            "diverge": cmd_diverge, "verify": cmd_verify, "next-id": cmd_next_id}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        print(__doc__)
        sys.exit(2)
    try:
        cmds[sys.argv[1]](repo_root())
    except Refused as e:
        print(f"ОТКАЗ: {e}", file=sys.stderr)
        sys.exit(1)
    except BrokenPipeError:
        sys.exit(0)


if __name__ == "__main__":
    main()

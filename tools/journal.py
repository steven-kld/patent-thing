#!/usr/bin/env python3
"""Единственный допустимый способ записи в journal.jsonl.

Инварианты, которые здесь проверяются механически:
  * файл только дописывается; закоммиченное содержимое обязано быть
    префиксом рабочего файла (иначе строки правили руками);
  * ts ставит скрипт, из аргументов не принимается;
  * id ставит скрипт, из аргументов не принимается;
  * result допускается только если register этого id уже в HEAD,
    то есть попал в отдельный, более ранний коммит;
  * на один id не более одного result;
  * decision_rule обязан содержать оператор сравнения и число;
  * artifact проверяется по sha256 в момент записи result;
  * после каждой записи — git add + git commit, один коммит на запись.

Команд edit и delete нет и не должно появиться. Исправление ошибочной
записи — новое событие type="решение" с полем refs.

Использование:
    journal.py next-id
    journal.py register  < payload.json
    journal.py result    < payload.json
    journal.py verify
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

JOURNAL = "journal.jsonl"
TZ = timezone(timedelta(hours=4))  # Тбилиси

TYPES = {"предрегистрация", "гейт", "данные", "конфигурация", "аудит", "решение"}
SPLITS = {"train", "valid", "test", "n/a"}

REGISTER_FIELDS = ["type", "claim", "metric", "split", "decision_rule", "config", "data_ref"]
RESULT_FIELDS = ["values", "artifact", "verdict", "reason"]

FORBIDDEN_IN_PAYLOAD = {"id", "ts", "event", "code_commit", "register_commit", "values"}
FORBIDDEN_IN_RESULT = {"id", "ts", "event", "claim", "decision_rule", "metric", "config"}


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
    p = subprocess.run(["git", "show", f"HEAD:{JOURNAL}"], capture_output=True, text=True, cwd=root)
    return p.stdout if p.returncode == 0 else ""


def head_commit(root: Path) -> str:
    return git("-C", str(root), "rev-parse", "HEAD").strip()


def working_tree_dirty_elsewhere(root: Path) -> list[str]:
    """Изменённые/неотслеживаемые файлы, кроме самого журнала."""
    out = git("-C", str(root), "status", "--porcelain")
    return [l[3:] for l in out.splitlines() if l[3:].strip() and l[3:].strip() != JOURNAL]


# ------------------------------------------------------------------- целостность


def load_journal(root: Path) -> list[dict]:
    path = root / JOURNAL
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    out = []
    for i, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise Refused(f"строка {i} журнала не разбирается как JSON: {e}")
    return out


def check_append_only(root: Path) -> None:
    """Закоммиченное содержимое обязано быть префиксом рабочего файла."""
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
    """Незакоммиченный хвост означает, что предыдущая запись оборвалась."""
    committed = head_journal(root)
    path = root / JOURNAL
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    if len(current) > len(committed):
        raise Refused(
            "в journal.jsonl есть незакоммиченные строки. Скрипт коммитит каждую "
            "запись сам, значит прошлый запуск оборвался или файл правили в обход. "
            "Разберись вручную."
        )


# ---------------------------------------------------------------------- проверки


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


DECISION_RULE_RE = re.compile(r"(>=|<=|>|<|=|не менее|не более|выше|ниже)")
NUMBER_RE = re.compile(r"\d")


def validate_register(payload: dict, entries: list[dict]) -> None:
    stray = FORBIDDEN_IN_PAYLOAD & payload.keys()
    if stray:
        raise Refused(
            f"поля {sorted(stray)} задаются скриптом, а не вызывающим. "
            "ts и id, переданные снаружи, — это запись задним числом."
        )
    missing = [f for f in REGISTER_FIELDS if f not in payload or payload[f] in ("", None, {})]
    if missing:
        raise Refused(f"не заполнены обязательные поля register: {missing}")
    if payload["type"] not in TYPES:
        raise Refused(f"type должен быть одним из {sorted(TYPES)}")
    if payload["split"] not in SPLITS:
        raise Refused(f"split должен быть одним из {sorted(SPLITS)}")
    if not isinstance(payload["config"], dict):
        raise Refused("config должен быть объектом, а не строкой")

    rule = str(payload["decision_rule"])
    if not (DECISION_RULE_RE.search(rule) and NUMBER_RE.search(rule)):
        raise Refused(
            "decision_rule обязан содержать сравнение и число: что именно "
            "считается «принято», решается до прогона. "
            "Пример: «ΔAUC на valid > 0.005». Получено: " + repr(rule)
        )

    claim = str(payload["claim"]).strip()
    if len(claim.split()) < 4:
        raise Refused("claim слишком короткий: нужно утверждение с исходом, а не тема")

    if not entries and payload["type"] != "предрегистрация":
        raise Refused("первая запись журнала обязана быть type=предрегистрация")
    if payload["type"] == "предрегистрация":
        if entries:
            raise Refused("предрегистрация допустима только как запись №1")
        if "brief_sha256" not in payload["config"]:
            raise Refused("в config предрегистрации обязан быть brief_sha256")


def find_register(entries: list[dict], eid: int) -> dict | None:
    for e in entries:
        if e.get("id") == eid and e.get("event") == "register":
            return e
    return None


def register_commit_of(root: Path, eid: int) -> str | None:
    """Самый ранний коммит, в чьей версии журнала уже есть register этого id."""
    revs = git("-C", str(root), "rev-list", "--reverse", "HEAD", "--", JOURNAL).split()
    for rev in revs:
        p = subprocess.run(["git", "show", f"{rev}:{JOURNAL}"], capture_output=True, text=True, cwd=root)
        if p.returncode != 0:
            continue
        for line in p.stdout.splitlines():
            if not line.strip():
                continue
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            if e.get("id") == eid and e.get("event") == "register":
                return rev
    return None


def validate_result(root: Path, payload: dict, entries: list[dict]) -> tuple[int, str]:
    stray = FORBIDDEN_IN_RESULT & payload.keys()
    if stray:
        raise Refused(f"поля {sorted(stray)} в result не задаются: {sorted(stray)}")
    if "refs" not in payload:
        raise Refused("в result обязан быть refs — id испытания, к которому он относится")
    eid = payload["refs"]
    if not isinstance(eid, int):
        raise Refused("refs должен быть целым id")

    missing = [f for f in RESULT_FIELDS if f not in payload or payload[f] in ("", None)]
    if missing:
        raise Refused(f"не заполнены обязательные поля result: {missing}")
    if payload["verdict"] not in {"принято", "отвергнуто", "н/п"}:
        raise Refused("verdict: принято | отвергнуто | н/п")
    if not isinstance(payload["values"], dict):
        raise Refused("values должен быть объектом метрика → число")

    reg = find_register(entries, eid)
    if reg is None:
        raise Refused(f"register №{eid} в журнале не найден")
    if any(e.get("event") == "result" and e.get("refs") == eid for e in entries):
        raise Refused(f"для испытания №{eid} результат уже записан; перезапись запрещена")

    if reg["metric"] not in payload["values"]:
        raise Refused(
            f"в register №{eid} объявлена метрика {reg['metric']!r}, в values её нет. "
            "Метрика выбирается до прогона."
        )

    rc = register_commit_of(root, eid)
    if rc is None:
        raise Refused(
            f"register №{eid} не найден ни в одном коммите — он ещё не закоммичен. "
            "Результат нельзя записать в том же коммите, что и гипотезу."
        )

    art = payload["artifact"]
    if not isinstance(art, dict) or "path" not in art:
        raise Refused("artifact должен быть объектом с полем path")
    ap = Path(art["path"])
    if not ap.is_absolute():
        ap = root / ap
    if not ap.exists():
        raise Refused(f"файла результата нет по пути {ap}")
    digest = sha256_file(ap)
    if "sha256" in art and art["sha256"] != digest:
        raise Refused(f"sha256 не сходится: в payload {art['sha256']}, у файла {digest}")
    art["sha256"] = digest

    return eid, rc


# ----------------------------------------------------------------------- запись


def append_and_commit(root: Path, entry: dict, message: str) -> None:
    line = json.dumps(entry, ensure_ascii=False, sort_keys=True)
    with (root / JOURNAL).open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    git("-C", str(root), "add", "--", JOURNAL)
    git("-C", str(root), "commit", "-m", message)


def cmd_register(root: Path) -> None:
    payload = json.load(sys.stdin)
    entries = load_journal(root)
    check_append_only(root)
    check_uncommitted_entries(root)
    validate_register(payload, entries)

    dirty = working_tree_dirty_elsewhere(root)
    entry = {
        "id": max([e.get("id", 0) for e in entries], default=0) + 1,
        "event": "register",
        "ts": datetime.now(TZ).isoformat(timespec="milliseconds"),
        "code_commit": head_commit(root),
        "code_dirty": dirty,
        **payload,
    }
    append_and_commit(root, entry, f"journal: register #{entry['id']}")
    if dirty:
        print(
            "! рабочее дерево грязное, code_commit не описывает код полностью: "
            + ", ".join(dirty),
            file=sys.stderr,
        )
    print(json.dumps(entry, ensure_ascii=False, indent=2))


def cmd_result(root: Path) -> None:
    payload = json.load(sys.stdin)
    entries = load_journal(root)
    check_append_only(root)
    check_uncommitted_entries(root)
    eid, rc = validate_result(root, payload, entries)

    same = rc == head_commit(root)
    entry = {
        "id": max([e.get("id", 0) for e in entries], default=0) + 1,
        "event": "result",
        "ts": datetime.now(TZ).isoformat(timespec="milliseconds"),
        "register_commit": rc,
        "no_intervening_commit": same,
        **payload,
    }
    append_and_commit(root, entry, f"journal: result for #{eid}")
    if same:
        print(
            f"! между гипотезой #{eid} и результатом не было ни одного коммита. "
            "Запись сделана, но в журнале стоит no_intervening_commit=true.",
            file=sys.stderr,
        )
    print(json.dumps(entry, ensure_ascii=False, indent=2))


def cmd_next_id(root: Path) -> None:
    entries = load_journal(root)
    print(max([e.get("id", 0) for e in entries], default=0) + 1)


def cmd_verify(root: Path) -> None:
    check_append_only(root)
    entries = load_journal(root)
    problems: list[str] = []

    ids = [e.get("id") for e in entries]
    if ids != list(range(1, len(ids) + 1)):
        problems.append("id не монотонны или есть пропуски")

    open_regs = []
    for e in entries:
        if e.get("event") == "register" and e.get("type") not in {"предрегистрация", "решение"}:
            got = any(r.get("event") == "result" and r.get("refs") == e["id"] for r in entries)
            if not got:
                open_regs.append(e["id"])
        if e.get("event") == "result":
            reg = find_register(entries, e.get("refs"))
            if reg is None:
                problems.append(f"result #{e['id']} ссылается на несуществующий register")
                continue
            t_reg = datetime.fromisoformat(reg["ts"])
            t_res = datetime.fromisoformat(e["ts"])
            if t_res < t_reg:
                problems.append(f"#{reg['id']}: результат не позже гипотезы")

    trials = sum(1 for e in entries if e.get("event") == "register" and e.get("type") == "конфигурация")
    print(f"записей: {len(entries)}")
    print(f"испытаний type=конфигурация: {trials}")
    print(f"открытых register без result: {open_regs}")
    same = sum(1 for e in entries if e.get("no_intervening_commit"))
    print(f"результатов без коммита между гипотезой и результатом: {same}")
    if problems:
        print("ПРОБЛЕМЫ:")
        for p in problems:
            print("  - " + p)
        sys.exit(1)
    print("нарушений не найдено")


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in {"register", "result", "next-id", "verify"}:
        print(__doc__)
        sys.exit(2)
    try:
        root = repo_root()
        {"register": cmd_register, "result": cmd_result,
         "next-id": cmd_next_id, "verify": cmd_verify}[sys.argv[1]](root)
    except Refused as e:
        print(f"ОТКАЗ: {e}", file=sys.stderr)
        sys.exit(1)
    except BrokenPipeError:
        sys.exit(0)


if __name__ == "__main__":
    main()
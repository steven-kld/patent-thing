#!/usr/bin/env python3
"""Проверки чистых функций journal.py. Запуск: python3 tools/test_journal.py

Самодостаточен: фикстуры строит во временном каталоге, журнала и git не
касается. Пути с записью (freeze, open, close, diverge) здесь не проверяются —
они коммитят, и их первый прогон ручной (notes/state.md §4).
"""

import copy
import hashlib
import importlib.util
import json
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("j", HERE / "journal.py")
j = importlib.util.module_from_spec(spec)
spec.loader.exec_module(j)

ok = fail = 0


def case(name, fn, expect=None):
    global ok, fail
    try:
        r = fn()
        if expect is None:
            print(f"  ok   {name}" + (f" → {r}" if r is not None else ""))
            ok += 1
        else:
            print(f"  ПРОПУЩЕН отказ: {name} (ждали {expect!r}, вернулось {r!r})")
            fail += 1
    except j.Refused as e:
        if expect is not None and expect in str(e):
            print(f"  ok   отказ: {name}")
            ok += 1
        else:
            print(f"  СБОЙ {name}: {e}")
            fail += 1
    except Exception as e:
        print(f"  ИСКЛЮЧЕНИЕ {name}: {type(e).__name__}: {e}")
        fail += 1


def eq(name, got, want):
    global ok, fail
    if got == want or (isinstance(want, float) and abs(got - want) < 1e-9):
        print(f"  ok   {name} = {got}")
        ok += 1
    else:
        print(f"  СБОЙ {name}: {got!r} вместо {want!r}")
        fail += 1


# --------------------------------------------------------------------- фикстуры

root = pathlib.Path(tempfile.mkdtemp(prefix="journal-test-"))
(root / "est.py").write_text("def q(pred, truth):\n    return 0.0\n", encoding="utf-8")
(root / "lockbox.json").write_text(json.dumps({
    "boxes": {"scout": {"role": "разведка"},
              "confirm_a": {"role": "подтверждение"},
              "confirm_b": {"role": "подтверждение"}},
    "independence": {"scout_vs_confirm": 0.81, "between_windows": 0.62},
}, ensure_ascii=False), encoding="utf-8")


def sha(name):
    return hashlib.sha256((root / name).read_bytes()).hexdigest()


LB = {"id": 4, "sha256": sha("lockbox.json"), "artifact": {"path": "lockbox.json"}}
PROPOSAL = {"id": 1, "type": "заморозка", "stage": "Proposal",
            "claim": "утверждение с названным исходом", "sha256": "a" * 64}

BASE = {
    "quantities": {
        "excess": {
            "unit": "USD", "population": "verdict_box", "better": "higher",
            "range": [-120000, 150000],
            "estimator": {"spec": "парная разность", "path": "est.py",
                          "sha256": sha("est.py")},
            "uncertainty": {"method": "paired_bootstrap",
                            "dependence": {"block": 1, "unit": "row"},
                            "level": 0.95, "iterations": 1000, "seed": 42},
            "null": {"value": 0, "kind": "mathematical",
                     "dispersion": {"sd": {"const": "c_sd_null"}}},
        },
        "hit_rate": {
            "unit": "1", "population": "verdict_box", "better": "higher",
            "range": [0, 1],
            "estimator": {"spec": "доля верных", "path": "est.py",
                          "sha256": sha("est.py")},
        },
    },
    "constants": [
        {"name": "c_hour", "value": 50, "unit": "USD/hour",
         "provenance": "назначено", "basis": "ставка часа автора"},
        {"name": "c_hpd", "value": 3, "unit": "hour/day",
         "provenance": "назначено", "basis": "режим автора"},
        {"name": "c_days", "value": 10, "unit": "day",
         "provenance": "назначено", "basis": "длительность гипотезы"},
        {"name": "c_payback", "value": 3000, "unit": "USD",
         "provenance": "выведено", "derivation": "2 * c_hour * c_hpd * c_days"},
        {"name": "c_sd_null", "value": 700, "unit": "USD",
         "provenance": "измерено",
         "source": {"entry": 11, "artifact_sha256": "0" * 64}},
        {"name": "c_risk", "value": 0.05, "unit": "1",
         "provenance": "назначено", "basis": "потолок семейного риска"},
    ],
    "verdict_candidates": ["b2"],
    "slices": [{"id": "q1", "definition": "первый квартал", "bears_verdict": False}],
    "verdict_box": [{"lockbox_sha256": sha("lockbox.json"), "box": "confirm_a"}],
    "decision_rule": {"all": [
        {"left": {"quantity": "excess", "take": "ci_low"}, "op": ">=",
         "right": {"const": "c_payback"}}]},
    "selection": {"box": {"lockbox_sha256": sha("lockbox.json"), "box": "scout"},
                  "objective": "argmax excess",
                  "space": {"model": ["b1", "b2", "b3"], "C": [0.1, 1, 10]}},
    "multiplicity": {"dependence": "unknown", "combine": "union_bound",
                     "ceiling": {"const": "c_risk"}},
}


def V(prot, entries=(PROPOSAL,)):
    return j.validate_protocol(root, prot, LB, list(entries), 1)


def mod(**patch):
    p = copy.deepcopy(BASE)
    p.update(patch)
    return p


def clause(**over):
    c = copy.deepcopy(BASE["decision_rule"]["all"][0])
    c.update(over)
    return mod(decision_rule={"all": [c]})


def left(**over):
    c = copy.deepcopy(BASE["decision_rule"]["all"][0])
    c["left"].update(over)
    return mod(decision_rule={"all": [c]})


def const(name, **over):
    p = copy.deepcopy(BASE)
    for c in p["constants"]:
        if c["name"] == name:
            c.update(over)
    return p


def box(name):
    return {"lockbox_sha256": sha("lockbox.json"), "box": name}


# ------------------------------------------------------------------- проверки

print("\n— единицы и выражения")
eq("USD/hour × hour/day × day", j.unit_str(j._eval(
    j.parse_expr("a*b*c"),
    lambda n: (1.0, {"a": j.unit_of("USD/hour"), "b": j.unit_of("hour/day"),
                     "c": j.unit_of("day")}[n]))[1]), "USD^1")
eq("year**-0.5", j.unit_str(j.unit_of("year**-0.5")), "year^-0.5")
case("единица с множителем", lambda: j.unit_of("2*USD"), "не может содержать множитель")
case("вызов в выражении",
     lambda: j._eval(j.parse_expr("max(a,b)"), lambda n: (1.0, {})),
     "только имена, числа")
case("условие в выражении",
     lambda: j._eval(j.parse_expr("a if b else c"), lambda n: (1.0, {})),
     "только имена, числа")
case("сложение разных размерностей",
     lambda: j._eval(j.parse_expr("a+b"),
                     lambda n: (1.0, {"a": {"USD": 1}, "b": {"day": 1}}[n])),
     "разные размерности")

print("\n— константы")
eq("базовый набор", len(j.resolve_constants(BASE)), 6)
case("выведенное не сходится",
     lambda: j.resolve_constants(const("c_payback", value=3500)), "не сходится")
case("размерность вывода не та",
     lambda: j.resolve_constants(const("c_payback", unit="USD/day")),
     "размерность вывода")
case("назначенное без basis",
     lambda: j.resolve_constants(const("c_hour", basis="  ")), "basis с автором")
case("измеренное без source",
     lambda: j.resolve_constants(const("c_sd_null", source=None)), "source")

print("\n— α, бюджет, мощность")
r = V(BASE)
z = j.N.inv_cdf(0.975)
eq("α = 1−Φ(z+(c−μ₀)/σ)", r["alpha"], 1 - j.N.cdf(z + 3000 / 700))
eq("trials", r["trials"], 1)
permissive = const("c_risk", value=0.9)
at_null = const("c_payback", value=0, provenance="назначено", basis="нуль",
                derivation=None)
for c in at_null["constants"]:
    if c["name"] == "c_risk":
        c["value"] = 0.9
eq("порог на нуле, ci_low → α", V(at_null)["alpha"], 0.025)
point_at_null = copy.deepcopy(at_null)
point_at_null["decision_rule"]["all"][0]["left"]["take"] = "point"
eq("порог на нуле, point → α", V(point_at_null)["alpha"], 0.5)
case("ci_high при better=higher", lambda: V(left(take="ci_high")),
     "консервативный конец")
case("перевёрнутое направление", lambda: V(clause(op="<=")),
     "Направление перевёрнуто")
case("α выше потолка", lambda: V(const("c_risk", value=1e-11)),
     "превосходит потолок")
case("потолок выведен, а не назначен",
     lambda: V(const("c_risk", value=0.01, provenance="выведено",
                     derivation="c_days / c_days / 100")),
     "обязан быть назначен автором")
eq("бюджет при α=0.025, потолок 0.05, union_bound",
   j.budget_from_ceiling(0.025, 0.05, "union_bound"), 2)
eq("бюджет при α=0.025, потолок 0.05, independent",
   j.budget_from_ceiling(0.025, 0.05, "independent"), 2)
eq("семейный риск union_bound n=2", j.family_risk(0.025, 2, "union_bound"), 0.05)

print("\n— клаузы и правило")
case("измеренная константа в правиле",
     lambda: V(clause(right={"const": "c_sd_null"})), "измерена")
case("сравнение двух величин",
     lambda: V(clause(right={"quantity": "hit_rate", "take": "point"})),
     "требует их ковариации")
case("размерности клаузы не сходятся", lambda: V(left(quantity="hit_rate")),
     "размерности не сходятся")
case("дизъюнкция в правиле",
     lambda: V(mod(decision_rule={"all": BASE["decision_rule"]["all"], "any": []})),
     "дизъюнкция выражается")
case("take не объявлен", lambda: V(left(take=None)), "take")
case("правило принимает весь диапазон",
     lambda: V(const("c_payback", value=-120000, provenance="назначено",
                     basis="пол", derivation=None)),
     "принимает весь объявленный диапазон")

print("\n— trials")
case("двое кандидатов", lambda: V(mod(verdict_candidates=["b1", "b2"])),
     "trials = 2")
case("два среза с вердиктом",
     lambda: V(mod(slices=[{"id": "q1", "definition": "q1", "bears_verdict": True},
                           {"id": "q2", "definition": "q2", "bears_verdict": True}])),
     "способных вынести вердикт, 2")
case("два ящика без aggregate",
     lambda: V(mod(verdict_box=[box("confirm_a"), box("confirm_b")])),
     "aggregate обязателен")
two = mod(verdict_box=[box("confirm_a"), box("confirm_b")],
          aggregate={"expr": "mean(excess)"})
case("aggregate без ссылки на независимость", lambda: V(two),
     "меру независимости")
bad_ref = copy.deepcopy(two)
bad_ref["aggregate"]["independence"] = {"lockbox_key": "нет_такого"}
case("ссылка на отсутствующую независимость", lambda: V(bad_ref),
     "нет independence")
good_ref = copy.deepcopy(two)
good_ref["aggregate"]["independence"] = {"lockbox_key": "between_windows"}
eq("два ящика с aggregate и ссылкой → trials", V(good_ref)["trials"], 1)
case("вердикт на срезе, величина на ящике",
     lambda: V(mod(slices=[{"id": "q1", "definition": "q1",
                            "bears_verdict": True}])),
     "живёт на популяции")

print("\n— ящики и отбор")
case("verdict_box с ролью разведка",
     lambda: V(mod(verdict_box=[box("scout")])), "Вердикт выносится")
case("selection.box подтверждающий",
     lambda: V(mod(selection={**BASE["selection"], "box": box("confirm_b")})),
     "отбор ведётся")
case("objective — суждение",
     lambda: V(mod(selection={**BASE["selection"],
                              "objective": "тот, который выглядит осмысленно"})),
     "формула вида")
case("кандидат вне пространства перебора",
     lambda: V(mod(verdict_candidates=["b2_подкрученный"])),
     "не принадлежат объявленному")
case("несуществующий ящик", lambda: V(mod(verdict_box=[box("нет")])),
     "нет в заморозке Lockbox")
case("combine=independent при dependence=unknown",
     lambda: V(mod(multiplicity={**BASE["multiplicity"], "combine": "independent"})),
     "считается отсутствующей")
case("combine=independent со ссылкой",
     lambda: V(mod(multiplicity={"dependence": "independent",
                                 "combine": "independent",
                                 "ceiling": {"const": "c_risk"},
                                 "independence": {"lockbox_key": "scout_vs_confirm"}}
                   ))["budget"] > 0)

print("\n— оценщик и uncertainty")
bad_est = copy.deepcopy(BASE)
bad_est["quantities"]["excess"]["estimator"]["sha256"] = "b" * 64
case("хеш оценщика не сходится", lambda: V(bad_est),
     "не сходится с объявленным хешем")
no_est = copy.deepcopy(BASE)
del no_est["quantities"]["hit_rate"]["estimator"]
case("величина без оценщика", lambda: V(no_est), "estimator")
no_dep = copy.deepcopy(BASE)
del no_dep["quantities"]["excess"]["uncertainty"]["dependence"]
case("uncertainty без dependence", lambda: V(no_dep), "dependence")
no_null = copy.deepcopy(BASE)
del no_null["quantities"]["excess"]["null"]
case("величина правила без нуля", lambda: V(no_null), "обязана объявить null")

print("\n— вердикт из values")
eq("ожидаемые ключи", sorted(V(BASE)["expected_keys"]),
   ["excess.ci_high", "excess.ci_low", "excess.point", "hit_rate.point"])
for vals, want in [({"excess.ci_low": 3000.0}, "принято"),
                   ({"excess.ci_low": 3000.0001}, "принято"),
                   ({"excess.ci_low": 2999.99}, "отвергнуто"),
                   ({"excess.ci_low": -50000}, "отвергнуто"),
                   ({"excess.point": 9999}, "н/п")]:
    eq(f"{vals}", j.evaluate_rule(BASE, vals), want)

print("\n— состояние журнала")


def F(i, stage, s, exp=None):
    return {"id": i, "type": "заморозка", "stage": stage, "sha256": s,
            "experiment": exp, "claim": "утверждение с названным исходом"}


def D(i, stage, inv, exp):
    return {"id": i, "type": "расхождение", "stage": stage, "invalidates": inv,
            "experiment": exp, "claim": "факт разошёлся с обещанным", "refs": [1]}


def O(i, role, b, exp, verdict=None):
    return {"id": i, "type": "вскрытие", "stage": "Tearsheet", "role": role,
            "lockbox": {"freeze": "LB", "box": b}, "experiment": exp,
            "values": {}, "verdict": verdict, "claim": "вскрытие ящика по плану"}


LEGACY = [{"id": 1, "event": "register", "type": "предрегистрация"},
          {"id": 2, "event": "result", "refs": 1}]
E = LEGACY + [F(3, "Proposal", "s3"), F(4, "Manifest", "s4", 3),
              F(5, "Universe", "s5", 3), F(6, "Lockbox", "s6", 3),
              F(7, "Protocol", "s7", 3)]

eq("записи прошлой схемы отфильтрованы", [e["id"] for e in j.current(E)],
   [3, 4, 5, 6, 7])
eq("эксперимент заморозки Proposal", j.experiment_of(F(3, "Proposal", "s3")), 3)
a, k = j.stage_state(E, 3)
eq("действующие стадии", sorted(a),
   ["Lockbox", "Manifest", "Proposal", "Protocol", "Universe"])
a, k = j.stage_state(E + [D(8, "Universe", ["Universe"], 3)], 3)
eq("после расхождения на Universe — действующие", sorted(a),
   ["Manifest", "Proposal"])
eq("каскад S3 обнулил старшие", sorted(k), ["Lockbox", "Protocol", "Universe"])
a, k = j.stage_state(E + [D(8, "Universe", ["Universe"], 3),
                          F(9, "Universe", "s5", 3)], 3)
eq("восстановление S4 вернуло стадию", sorted(a),
   ["Manifest", "Proposal", "Universe"])
E4 = E + [O(8, "разведка", "scout", 3), O(9, "разведка", "scout", 3),
          O(10, "подтверждение", "confirm_a", 3, "отвергнуто")]
eq("promoted считает только подтверждения", j.promoted(E4, 3), 1)
eq("вскрытые подтверждающие", j.confirming_boxes_opened(E4, 3),
   {("LB", "confirm_a")})
E5 = E4 + [F(11, "Proposal", "s11"), O(12, "подтверждение", "other", 11, "принято")]
eq("счётчик по эксперименту, а не по журналу",
   (j.promoted(E5, 3), j.promoted(E5, 11)), (1, 1))

print(f"\nитого: ok {ok}, сбоев {fail}")
sys.exit(1 if fail else 0)

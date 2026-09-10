# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

## Проект: стенд

**Два слоя, и они путаются.** Эксперимент — то, что проверяется на данных.
Стенд — то, что не даёт незаметно подогнать проверку под результат. Правки в
стенд и правки в эксперимент не смешивать в одном изменении.

**Нормативные документы стенда.** Читать перед работой:

```
notes/state.md             где стенд сейчас: что построено, чего нет, что guard
                           останавливает и что нет. Читать первым
notes/stages-v2.md         стадии, гейты, рода записей, разведка и подтверждение
notes/protocol-schema.md   схема артефакта Protocol: поля, вердикт, trials, α
notes/journal-tool.md      контракт tools/journal.py и формат артефактов
README.md                  относительные и абсолютные ограничения
```

`journal.py verify` говорит, где эксперимент; `notes/state.md` — где стенд.

При расхождении между `notes/stages-v2.md` и постановкой конкретного
эксперимента верен `stages-v2.md`, а расхождение — событие, подлежащее записи.

**Журнал испытаний.** `journal.jsonl` изменяется исключительно через
`tools/journal.py`. Прямая запись, редактирование существующих строк,
удаление строк и ручной `git commit` журнала запрещены.

**`tools/journal.py` — это guard, а не прикладной код.** Разделы 2 и 4 выше
к нему не применяются:

- Отказ скрипта (`ОТКАЗ: ...`, exit 1) — это результат работы, а не сбой.
  Показать текст пользователю и остановиться. Не обходить, не подгонять
  вход под проверку, не править скрипт, чтобы команда прошла.
- Проверки «на невозможное» здесь намеренные. Не упрощать, не сокращать,
  не удалять как избыточные. Менять скрипт — только по явной просьбе
  пользователя и только тем, что он попросил.

**Артефакты.** Файл артефакта неизменяем после заморозки (A1). Исправление —
новый артефакт и новая запись, старый остаётся. Не редактировать файл, на
который уже ссылается заморозка: хеш разойдётся, и скрипт откажет.

**Постановка эксперимента.** Любой документ постановки только читается: правка
существующей редакции запрещена, новая редакция — новый файл плюс запись в
журнале. Правило решения живёт в артефакте Protocol, а не в прозе постановки:
при расхождении верен артефакт.

**Подтверждающий ящик.** Открывается один раз, автором, в самом конце.
Не читать, не считать на нём метрики, не подглядывать по собственной
инициативе — ни на целевой переменной, ни на величинах, зависящих от неё.

**Платные источники данных.** Бюджет — ноль. Любой запрос к тарифицируемому
источнику выполняется только с жёстким предохранителем на объём или стоимость,
заданным явно в самом запросе. Запрос без предохранителя не выполнять.

## Git: запрет

Агенту запрещено выполнять любые команды `git` и `gh` — включая
`status`, `log`, `diff`, `add`, `commit`, `checkout`, `restore`, `stash`,
`reset`, `push`, `pull`, `branch`, `clean`, `rebase`. Читающие команды
запрещены наравне с пишущими: исключений нет, чтобы не было предмета
для трактовки.

Запрещено также: изменять что-либо в `.git/`, править `.gitignore`,
вызывать git через обёртки (`bash -c`, `sh -c`, пайпы, скрипты,
созданные для этой цели), устанавливать хуки.

Единственный git в проекте — внутри `tools/journal.py`, который коммитит
журнал сам. Это не исключение из запрета: агент вызывает `journal.py`,
а не git.

Если для задачи нужна операция с git — сформулируй команду, объясни зачем
и попроси пользователя выполнить её. Не выполняй сам и не ищи обход.
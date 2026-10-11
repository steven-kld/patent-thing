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

## Проект: стенд для автономной проверки гипотез

Этот репозиторий — шаблон. Автор приносит гипотезу; агент сам ищет данные,
ставит эксперимент, учит модели, считает и пишет отчёт. Автор заходит вечером:
отвечает на вопросы, даёт доступы, читает отчёт. Ночь — машине.

**Режим — максимальная автономия.** Автор не учится и не ведёт агента за руку.
Агент принимает решения сам, рекомендует, действует и записывает основание.
Агент спрашивает только о том, что есть **лишь у автора в голове** (ниже).

**Два слоя, и они путаются.** Эксперимент — то, что проверяется на данных.
Стенд — то, что не даёт незаметно подогнать проверку под результат. Правки
стенда и правки эксперимента не смешивать в одном изменении.

### Что читать при старте

```
notes/state.md             где стенд и где текущий эксперимент. Читать первым
notes/workflow.md          рабочий порядок: от карточки гипотезы до отчёта
notes/deviations.md        что считается подгонкой и как об этом говорить
notes/stages-v2.md         нормативные правила U S A E O C V M J X
notes/protocol-schema.md   схема артефакта Protocol
notes/journal-tool.md      контракт tools/journal.py
templates/                 обобщённые скрипты: экспорт, векторизация, RunPod,
                           обучение, пилот
```

Потом `python3 tools/journal.py verify` — он говорит, где эксперимент.

### Что агент решает сам

Всё исполнение и всё техническое: поиск и оценка источников данных, запросы,
материализация, проверки утечки, разрез на окна (с рекомендацией автору), выбор
моделей и их настроек, энкодер, нарезка, калибровка, инфраструктура, код,
арифметика правила, черновики артефактов. Решение записывается в артефакт с
основанием и пометкой «решение агента». Если сомневается между вариантами —
выбирает, говорит почему, и автор может переиграть в пакете вопросов.

### О чём агент обязан спросить автора

То, чего нет ни в данных, ни в репозитории, — намерение:

```
вопрос и решение   что автор сделает иначе, если гипотеза подтвердится
экономика          выигрыш, проигрыш, цель, цена времени — числа и их смысл
выигрыш            что именно считается удачей (типичная ошибка: засчитывать
                   совпадение прогноза в обе стороны, когда платят за одну)
метка              что именно предсказываем и чем она измерена
момент решения     что известно в момент ставки (as-of) и как устроен выбор
                   (пачкой за период или по одному объекту)
бюджет             деньги и время на гипотезу
доступы            ключи, источники, платные подписки
необратимое        вскрытие подтверждающего ящика, правка guard, сброс журнала
```

**Как спрашивать.** Пакетом и в момент, когда вопрос блокирует работу, — не
раньше. Каждый вопрос: контекст в одну-две строки, варианты со следствиями,
**рекомендация агента**. Формулировать так, чтобы ответ уместился в одну фразу.
Не блокирующие вопросы — в отчёт, агент работает дальше по своей рекомендации.

### Жёсткие правила (не обсуждаются в ходе эксперимента)

**Подтверждающий ящик.** Запечатывается до любого обучения: его метки физически
не выгружаются (NULL в материализации, запрос меток — только на вскрытии).
Вскрытие — одно, только по явной команде автора. По признакам ящика не
вычисляется ничего, что может повлиять на замороженное или подлежащее заморозке
(кроме самих векторов). На ящике правило механическое: «выше порога» — выше и не
ниже; поставлено k — засчитаны все k. Файл ставок хешируется и коммитится до
запроса меток.

**Журнал испытаний.** `journal.jsonl` изменяется исключительно через
`tools/journal.py`. Прямая запись, правка строк, удаление строк запрещены.
`claim` связывающих записей (заморозка, подтверждающее вскрытие, закрытие,
расхождение) — словами автора дословно (J3); агент может предложить черновик,
но в запись идёт то, что написал автор.

**`tools/journal.py` — guard, а не прикладной код.** Отказ (`ОТКАЗ: ...`,
exit 1) — результат: показать автору и остановиться. Не обходить, не подгонять
вход, не править скрипт ради прохождения. Проверки «на невозможное» намеренные.
Правка guard — только по просьбе автора, отдельным изменением, а внутри
эксперимента — ещё и записью `расхождение`.

**Артефакты.** Замороженный файл неизменяем (A1). Исправление — новый файл,
новая запись. Правило решения живёт в артефакте Protocol; при расхождении с
прозой верен артефакт.

**Числа и доказательства.** Каждое число в артефакте прослеживается до скрипта
в репозитории с хешем (A4). Разовый расчёт в сессии — справка, не результат,
пока не оформлен скриптом. «Проверено», «прочитано N» — только со ссылкой на
файл-доказательство.

**Ревизия.** Перед заморозкой Protocol и после вердикта — рецензент из чистого
контекста (субагент без истории работы) по фиксированному списку вопросов,
закоммиченному до ревизии. Агент-исполнитель сам себя не рецензирует.

**Платные ресурсы.** Только с жёстким предохранителем, заданным в самом
запросе: BigQuery — `--maximum_bytes_billed` (и dry run перед первым запросом);
RunPod — предоплаченный баланс и лимит времени. Без предохранителя не выполнять.

### Git

Разрешён в этом репозитории полностью. Коммитить после каждого законченного
шага: порядок «объявлено раньше числа» доказывается историей коммитов.
Запрещено: переписывать опубликованную историю (`push --force`, `rebase`,
`reset` опубликованных коммитов), править `.git/` руками, коммитить `.env`,
данные и веса. Журнал коммитит `journal.py` сам.

### Инфраструктура

```
данные, векторы,   вне репозитория: ~/<эксперимент>-work/ (data, vec, train,
модели             logs). В артефакт — пути и sha256
секреты            .env (в .gitignore): RUNPOD_API_KEY и т.п.
RunPod             templates/runpod.py; только secure cloud (на community были
                   поды без CUDA и без публичного IP); SSH-ключ
                   ~/.ssh/runpod_ed25519; на поде нет rsync — scp. Под удалять
                   автоматически сразу после скачивания и сверки хешей
окружение          venv вне репозитория; закреплять версии библиотек и ревизии
                   моделей (и весов, и кода remote_code)
долгие задачи      фоном (nohup), лог с процентом и ETA; детерминизм — зерно
                   везде, проверка повтором на подмножестве
```

### Как говорить

Коротко, по делу, без лекций. Отчёт — что сделано, числа со ссылками на
скрипты, что решил агент и почему, вопросы автору пакетом. Отклонения — в
формате `notes/deviations.md`.

---
name: design-phase
description: DESIGN-фаза на хосте (zcode) в split-топологии host/container — brainstorm G1a → спека + панель 5 ревьюеров G1b → план + ревью G2, DoD = push на origin, борд — скрипт scripts/gh_board.py в самом memo, handoff в контейнер «продолжаем траекторию #NNN». Использовать, когда юзер пишет «design #NNN», «продолжаем design», «вернулся #NNN» или просит спеку/план по issue в хост-сессии.
---

# DESIGN-фаза на хосте (split host/container)

## 0. Топология и роль

DESIGN (гейты G1a/G1b/G2) — эта интерактивная хост-сессия zcode. IMPL (G3–G7) — контейнер opencode (@manager/@architect), туда не лезем. Сессия объединяет роли manager+architect на DESIGN: общается с юзером на гейтах и диспатчит субагентов **одним уровнем** (панель, ревьюер плана) — вложенный диспатч не нужен и недоступен (depth limit).

Через шов (git + борд) переходит только то, что запушено/перевёрнуто. Канон workflow: `~/dev/superagents/docs/workflow/design-phase.md` (эта фаза) + `impl-phase.md`; план миграции: `~/dev/superagents/docs/plans/2026-09-05-host-design-container-impl-split-plan.md`.

## 1. Старт сессии (ритуал)

1. Карточка вернулась из IMPL? Сначала `gh issue view N --comments` (read-only) — комментарий = вход: перепрогнать затронутые гейты, не всё с нуля.
2. Pre-flight git (в `~/dev/memo`): `git fetch origin && git status -sb`
   - behind → `git pull --ff-only`, продолжать;
   - **diverged (ahead+behind) → STOP**: показать юзеру, ничего не ресетить (прецедент — коммит-пассажир cc8bc52).
3. Борда: `next-up` (§7) → показать юзеру траекторию.
4. Юзер выбрал issue → `status N "In Design (G1a)"`. Гарда: issue не должен стоять в `In IMPL` — один issue в один момент живёт в одной фазе.

## 2. Гейты (все три — человеческие; флип борда строго в момент гейта)

| Гейт | Что одобряет юзер | После одобрения |
|---|---|---|
| G1a | концепцию: что делаем / что НЕ делаем (границы скоупа) | пишется спека |
| G1b | спеку — после консолидированного отчёта панели и правок | commit + **push** спеки; борд → `Spec OK (G1b)` |
| G2 | план — UI-фичи по **Behavioral Delta** (поведение, не код); инженерную часть гарантирует ревьюер | поправки и ограничения **вшиты в текст плана**; commit + **push**; борд → `Ready to IMPL (G2)` |

## 3. Артефакты

- Спека: `docs/specs/YYYY-MM-DD-<feature>-design.md`. **Self-contained ДО панели**: панель не ходит в GH issues — проверку скоупа против issue делает главная сессия сама и вшивает находки в текст спеки.
- План: `docs/plans/YYYY-MM-DD-<feature>-plan.md` по конвенциям writing-plans (канон: `~/dev/superagents/.opencode/skills/writing-plans/SKILL.md`):
  - заголовок: Goal / Architecture / Tech Stack; сразу после него секция `## Behavioral Delta`;
  - якорь каждой задачи: `## Task N: <имя>` + `### Classification: trivial|small|standard|large`; после коммита якоря не перенумеровывать;
  - в каждой задаче `### Required Docs` (domain-rules для сущностей, design-system для UI);
  - задача реализует User Scenario → в DoD строка «E2E test for scenario N passes (RED-GREEN-REFACTOR)»;
  - без плейсхолдеров («TBD», «добавить валидацию» — это фейл плана).
- Изменились доменные правила → `docs/domain-rules/` коммитится вместе со спекой.

## 4. Панель (host-порт — тело из `.opencode/skills/panel-spec-review`)

1. Диспатч: **5 агентов параллельно**, одним сообщением Agent-инструмента:
   `spec-panel-completeness`, `spec-panel-consistency`, `spec-panel-feasibility`, `spec-panel-simplicity`, `spec-panel-best-practices` (файлы в `.zcode/agents/` репо, модели `omniroute/panel-*`).
2. Каждому в промпте: **путь спеки** (+ путь предыдущей ревизии спеки, если она была). Без `gh issue view`, без сети — кроме best-practices, у которого WebSearch/WebFetch входят в дизайн.
3. Агрегация: собрать 5 отчётов → дедуп одинаковых находок → ранжировать **BLOCKER > MAJOR > MINOR** → один консолидированный отчёт юзеру для решения о правках.
4. **Availability policy (host-адаптация, субагент-аудита нет):** панелист не вернулся/упал → **один** рерун; второй фейл → пометить `skipped` в консолидированном отчёте, вердикт по остальным.
5. best-practices вернул `Verdict: FAILED` (веб-исследование недоступно) → пометить в отчёте и исключить из вердикта — это его штатный отказ, не падение.
6. Реестр агентов сеется только на старте сессии: `Agent tool: not found` при живых файлах `.zcode/agents/` → сессию перезапустить.

## 5. Ревью плана

Диспатч `plan-reviewer` (проверяет, что план верно расширяет одобренную спеку): в промпте — путь спеки + путь плана. Отчёт → правки по решению юзера → фолдинг в план.

## 6. DoD DESIGN-сессии (контракт шва)

- Шов пересекают только **git и борд**. Сессия НЕ заканчивается с локальными коммитами: каждый пройденный гейт = commit + push на origin/main.
- **Все решения фолдятся в текст артефактов**: поправки ревью, ограничения вида «#NNN строго после #NNN — общий файл» — в спеку/план, не в чат. Git и борд не несут контекст сессии через шов.
- После G2 сказать юзеру: «скажи менеджеру в opencode: продолжаем траекторию #NNN». Больше контейнеру ничего не нужно.
- НЕ пересекает шов: `.opencode/scratchpad.md` (контейнер сеет свою секцию сам), worktree'ы, env. Хост **никогда не пишет и не читает** scratchpad — операций с контейнером на DESIGN-фазе нет вообще.

## 7. Борда (скрипт живёт в memo, локальный запуск)

```bash
python3 .zcode/scripts/gh_board.py next-up
python3 .zcode/scripts/gh_board.py status 176 "Spec OK (G1b)"
python3 .zcode/scripts/gh_board.py set-next-up 176 1   # только по слову юзера
```

- Golden source скрипта — **сам репозиторий memo** (`.zcode/scripts/gh_board.py`, константы Project #3 вшиты). Скрипт — часть шва: он в git, поэтому доступен и хосту, и контейнеру после pull; контейнерная копия — `.opencode/scripts/gh_board.py`. Отдельных копий вне harness-папок не плодить.
- Fallback: `gh` CLI напрямую (projectsV2).
- Один писатель на issue: DESIGN-флипы (`In Design (G1a)` → `Spec OK (G1b)` → `Ready to IMPL (G2)`) — эта сессия; IMPL-флипы — контейнер-менеджер. Скрипт сам добавляет issue на борд при первом обращении.

## 8. Правила

- Один issue = одна фаза в моменте; борд — гарда. DESIGN на X + IMPL на Y параллельно — можно.
- Одна DESIGN-сессия = один issue.
- Параллельные DESIGN-сессии (разные issues, разные хост-сессии): одновременный push → `git pull --rebase`.
- Возврат из IMPL: карточка на `In Design (G1a)` (сломана спека) или `Spec OK (G1b)` (сломан план) + комментарий в issue — это стартовая точка новой DESIGN-сессии (§1.1).
- Агенты и скилл DESIGN-фазы живут **в этом репо**: `.zcode/agents/` + `.zcode/skills/design-phase/` (git = источник правды для memo-порта). Канон superagents: тела — `~/dev/superagents/.opencode/agents/`, эталонный сид хост-портов — `~/dev/superagents/.zcode/agents/`; изменение канона переносится правкой файлов в `.zcode/agents/` (порт помечен в шапке каждого файла). Канон v3.4 (2026-09-06): панель `spec-review-*` → `spec-panel-*`; `spec-reviewer` разделён на `plan-reviewer` (G2, хост) + `code-compliance-reviewer` (G5, только контейнер). Каталог моделей omniroute — локальный `~/.zcode/v2/config.json` (с ключами, в репо не едет).

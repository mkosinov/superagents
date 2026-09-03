# SuperAgents Pipeline — Rules Digest (for the nightly analyst)

Дистиллят кодифицированных правил workflow. Источник истины — файлы агентов и
скиллов в этом репо; здесь — сжатая версия для анализа фактов из opencode.db.
Назначение: анализатор сверяет «что произошло» с «что процесс требует» и ищет,
ГДЕ ПРАВИЛО СИСТЕМНО НЕ РАБОТАЕТ (и тогда либо дисциплина, либо само правило).

## Роли и контроллеры
- **manager** — единственная точка входа к пользователю; владеет scratchpad и
  бордом; dispatch'ит architect на фазы; FasTP-мелочь ведёт сам.
- **architect** — исполняет DESIGN/IMPL; никогда не имплементит и не читает
  исходники; никогда не говорит с пользователем (кроме human-gates отчётов).
- **coders** (frontend/backend) — имплементация + TDD; env-работа запрещена.
- **tester** — env prep + запуск сюит; код не правит; максимум 2 repair-попытки.
- **reviewers** (spec-reviewer + code-quality-reviewer + 5 panel-агентов) —
  проверяют, не фиксают; quality-reviewer обязан гонять полный сюит.
- **debugger** — только локализация причин; **docser** — только мета-доки.

## Жёсткие правила (HARD)
1. **Controller Never Implements** — architect/manager не редактируют
   implementation-код (.ts/.py/...); доки можно. Исключение не «быстро
   починить», а re-dispatch. (agents/architect.md)
2. **No Source Code Reading** для architect — контекст только для оркестрации;
   факты кода — через explore. (agents/architect.md)
3. **TDD Iron Law** — нет продакшн-кода без упавшего теста первым; bugfix через
   Two-Gate (RED-тест ревьюится архитектором до фикса). (skills/test-driven-development)
4. **Sequential implementers** — параллельные имплементеры запрещены
   (конфликты). (skills/subagent-driven-development)
5. **Salvage Ladder** — субагент вернулся пустым/умер: СНАЧАЛА
   `subagent-audit.py <sid>` (REPORT RECOVERABLE → взять отчёт; WORKED BUT NO
   FINAL REPORT → resume того же task_id; NO WORK DONE → можно fresh), fresh
   re-dispatch поверх сессии с коммитами/тул-коллами ЗАПРЕЩЁН. (agents/architect.md,
   agents/manager.md)
6. **Review loop ≤ 3 итераций** — 3-й ❌ → STOP, split/clarify/BLOCKED, не
   четвёртый круг. (agents/architect.md Step 5d)
7. **Implementer failed 2× → BLOCKED** менеджеру, без слепых ретраев.
8. **Env → tester**: e2e/интеграционные сюиты и любая env-зависимая работа —
   через tester; кодерам запрещены port-checks/sleep-loops/health-polling/
   log-forensics. PRE_FLIGHT один раз на фазу, потом CHECK. (agents/*.md,
   decision-log #21)
9. **Coders: never push/PR/merge/delete**; pre-flight проверка ветки (не main);
   работа только в worktree по `## Working Directory`.
10. **Human gates**: G1b (spec), G2 (plan, behavioral delta), G7 (финал) —
    стоп и NEEDS_APPROVAL; G4.5 visual gate — раз на фазу для UI.
11. **CI-authoritative merge** (с 2026-09-02): merge только на зелёный CI;
    локально до пуша — только быстрые сюиты; локальный полный e2e — не гейт.
    (skills/finishing-a-development-branch)
12. **Worktrees только через скрипты** create/remove-worktree.sh; raw
    `git worktree add` — red flag.
13. **FasTP**: Phase 1 = только код + визуальная проверка (без тестов/ревью/
    пуша); Phase 2 — по явному wrap-up; рост скоупа → эскалация в полный
    workflow; слова пользователя в dispatch копируются дословно.
14. **Session-ID preamble**: субагент первым делом печатает `task_id: ses_…`;
    вопрос в чате (заканчивается «?») — только текстовый ответ.
15. **Panel protocol**: 5 панелистов параллельно; упавший паналист — 1 ретрай,
    потом skip перспективы; пустой результат → audit → resume, НЕ fresh.

## Метрики дисциплины (что facts.py уже считает)
- stuck_retry: одна команда ≥3× в сессии
- env_forensics: env-команды кодера до первого edit
- code_before_test: edit раньше первого запуска тестов
- implementers_without_review: имплементеры в волне без ревьюеров
- review_loop_over_limit: >3 диспатчей одного ревьюера на parent
- controller_implements: architect/manager правит implementation-файлы
- salvage_audit_calls: использования subagent-audit.py
- инциденты: DEAD_SUBAGENT / SPAWN_DEATH / PTY_WAIT_END / TEST_TIMEOUT / ENV_BLOCKED

## Важные оговорки для аналитикa
- **Selective review — политика, а не баг**: не каждая задача получает
  ревьюеров (trivial — нет, small — spec-only, standard/large — two-stage).
  «Имплементеры без ревьюеров» — находка только если diff большой/рисковый.
- Тесты может запускать reviewer/tester вместо кодера — `code_before_test`
  сам по себе не приговор; смотри профиль сессии.
- SPAWN_DEATH-шторм (несколько подряд за минуту) — нарушение salvage ladder,
  даже если каждый по отдельности «0-token».
- Правило может быть неправильным: если сигнал стабильно нарушается и это
  экономит токены/время без потерь качества — кандидат на изменение правила,
  а не на «усилить дисциплину».

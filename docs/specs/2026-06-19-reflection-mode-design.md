# Reflection Mode — Design Document

> **Date:** 2026-06-19
> **Project:** SuperAgents (framework-level feature, golden source)
> **Spec version:** 1.0
> **Status:** Draft — awaiting G1b (User Approval)

---

## 1. Overview

**Reflection Mode** — это self-analysis инструмент для workflow SuperAgents, который:

- Изучает историю сессий в `opencode.db` (read-only, без новой БД)
- Сравнивает фактическое выполнение с эталонным workflow (Key Principles, gates, skill triggers)
- Формирует **proposals** на улучшение (обновление agent.md, skills, конфига, чеклистов ревьюверов)
- Закрывает loop: трекает эффект от ранее применённых proposals

**Trigger modes:**

| Mode | Когда | Кто запускает |
|------|-------|---------------|
| **Bug-driven** | Перед фиксом бага | Архитектор (вручную или по протоколу) |
| **Wave-driven** | В конце wave | Архитектор или `/finish-wave` команда |
| **Time-driven** | Ночью | Cron `0 3 * * *` |

**Релевантность workflow:** 6 из 8 Key Principles SuperAgents напрямую проверяются reflection-mode'ом (см. §6). Это self-enforcement слой для принципов.

---

## 2. Goals & Non-Goals

### 2.1 Goals (MVP)

1. **Workflow compliance audit** — автоматическая проверка 6 Key Principles на каждой wave/баге/неделе
2. **Concrete proposals** — не "что-то пошло не так", а конкретный diff в конкретный файл
3. **Human-in-the-loop** — по умолчанию все proposals требуют одобрения пользователя
4. **Auto-apply для safe cases** — архитектурно поддержать, в MVP выключено
5. **Closing-the-loop** — трекинг "применили proposal X → баг Y больше не появляется"
6. **Quality scoring** — эвристики + LLM для оценки полезности skills/agents
7. **No new big DB** — работаем только с существующим `~/.local/share/opencode/opencode.db` (965 MB)
8. **Reusable across projects** — один skill + один agent, per-project конфиг

### 2.2 Non-Goals (явно не делаем)

- ❌ In-session memory updates (другая архитектура, нужны opencode hooks)
- ❌ Persistent agent memory (USER.md, multi-tier memory) — отдельный проект
- ❌ Auto-apply в default (явно off, опционально через флаг)
- ❌ Compaction / summarization (runtime фича LLM)
- ❌ Cross-agent shared memory (не нужно для workflow analysis)
- ❌ Skill consolidation / dedup (мало скиллов, не критично)
- ❌ Semantic search / vector DB (не внедряем)
- ❌ Knowledge graph между сущностями (overkill)
- ❌ GEPA-style multi-candidate evolution (требует parallel infra)
- ❌ Real-time intervention (другая архитектура)

---

## 3. Architecture

### 3.1 Компоненты

```
~/.config/opencode/
├── agents/
│   └── reflector.md                    # NEW: subagent для анализа
├── skills/
│   └── reflect/                        # NEW
│       ├── SKILL.md                    # entry point
│       ├── README.md
│       ├── scripts/
│       │   ├── reflect.sh              # CLI wrapper
│       │   ├── reconstruct_tree.py     # session-tree из opencode.db
│       │   ├── attribute_to_sessions.py # file → sessions (git log)
│       │   ├── workflow_checks.py      # 6 compliance checks
│       │   ├── quality_scoring.py      # heuristics + LLM
│       │   ├── closing_the_loop.py     # proposal → outcome tracking
│       │   ├── analyze.py              # LLM proposal generator
│       │   ├── notify.sh               # telegram notification
│       │   └── queries.sql             # все SQL запросы
│       ├── templates/
│       │   ├── post-mortem.md          # bug-driven output
│       │   ├── wave-report.md          # wave-driven output
│       │   ├── nightly-digest.md       # time-driven output
│       │   └── proposal.md             # generic proposal format
│       ├── config/
│       │   └── reflect.config.example.json  # per-project config example
│       └── examples/
│           ├── example-postmortem-session-title.md
│           ├── example-wave-report-wave-4-5.md
│           └── example-nightly-digest.md
└── reflection/                         # runtime storage
    ├── reports/                        # все сгенерированные отчёты
    ├── proposals/                      # активные proposals (pending approval)
    ├── decisions/                      # audit log: applied/rejected proposals
    └── state.json                      # last-run state (idempotency)
```

### 3.2 Golden source

Все компоненты разрабатываются в `superagents/` (golden source):

```
superagents/
├── agents/
│   └── reflector.md                    # source
├── skills/
│   └── reflect/                        # source
│       ├── SKILL.md
│       ├── scripts/
│       ├── templates/
│       ├── config/
│       └── examples/
└── docs/
    ├── specs/2026-06-19-reflection-mode-design.md  # this file
    ├── plans/2026-06-19-reflection-mode-plan.md     # Step 2 output
    └── architecture/reflection-mode.md             # концепция для архитекторов
```

**Sync:** через @infra (как остальные skills/agents). Sync-протокол без изменений.

### 3.3 Workflow position

**Параллельный sidecar, не sequential gate.** У каждого триггера свой момент:

```
                    Main workflow
G1a → G1b → G2 → G3 → G4-G6 → G7
              │
              └── ~ Reflection (parallel: bug/wave/time triggers)
                       │
                       ├── Bug-driven: перед bug-fix (вне workflow)
                       ├── Wave-driven: в конце wave (после G4-G6)
                       └── Time-driven: cron (вне workflow)
```

---

## 4. Data model

### 4.1 Read-only источник: opencode.db

Используем существующие таблицы:

| Таблица | Что извлекаем |
|---------|--------------|
| `session` | id, title, parent_id, agent, model, cost, tokens_*, time_created, time_updated, time_archived, path, time_compacting |
| `message` | JSON: role, mode, agent, path, cost, tokens, modelID, providerID, time |
| `part` | JSON: type=tool, tool=name, state (status, metadata.output, error), time_created, time_updated |
| `session_message` | type=event, time_created, data |
| `event` | aggregate_id, type, data, seq |
| `todo` | задачи и приоритеты |
| `permission` | решения по правам |

**Никаких новых таблиц в opencode.db** — мы только читаем.

### 4.2 Storage для proposals: filesystem

Всё что мы пишем — markdown файлы + JSON state:

```
~/.config/opencode/reflection/
├── reports/YYYY-MM-DD-<mode>.md         # human-readable отчёты
├── proposals/<proposal-id>.md           # pending proposals
├── decisions/YYYY-MM-DD-<proposal-id>.md # applied/rejected (audit)
└── state.json                           # last-run timestamps, cursors
```

**Не отдельная БД** — `state.json` для курсоров (последний обработанный session) + директории для отчётов. Легко бэкапить, легко читать, легко коммитить в git.

### 4.3 Per-project конфиг

```jsonc
// ~/.config/opencode/reflect.config.json (опционально)
{
  "workflow_checks": {
    "controller_never_implements": {
      "enabled": true,
      "severity": "critical"
    },
    "mandatory_reviewer_for_code": {
      "enabled": true,
      "file_patterns": ["*.ts", "*.tsx", "*.py"],
      "severity": "critical"
    },
    "tdd_red_first": {
      "enabled": true,
      "severity": "warning"
    },
    "max_review_loops": {
      "enabled": true,
      "max_loops": 3,
      "severity": "warning"
    },
    "gate_compliance": {
      "enabled": true,
      "gates": ["G1a", "G1b", "G2", "G7"],
      "severity": "critical"
    },
    "regression_test_on_bugfix": {
      "enabled": true,
      "severity": "warning"
    }
  },
  "auto_apply": {
    "enabled": false,                      // off в MVP
    "max_confidence": 0.95,
    "max_severity": "info",
    "allowed_types": ["archive-skill"]
  },
  "notify": {
    "telegram_chat_id": "...",
    "min_severity_to_notify": "warning"
  }
}
```

---

## 5. Trigger modes

### 5.1 Bug-driven (post-mortem)

**Назначение:** перед фиксом бага — найти workflow gaps которые привели к багу.

**Триггер:** архитектор (ручной) или протокол bug-fix:
```
Юзер: "В session title баг"
Architect: "Принял. Сначала reflection post-mortem для target file"
```

**Flow:**

```
1. attribute_to_sessions.py
   → git log -- <target-file> + session.path + time window
   → список релевантных sessions

2. reconstruct_tree.py
   → построить session-tree для каждой релевантной session
   → main + subagents + reviews

3. workflow_checks.py
   → запустить все 6 checks на этих деревьях
   → собрать violations

4. closing_the_loop.py
   → проверить существующие proposals на ту же code area
   → если есть matched — пометить как "verified working/didn't help"

5. analyze.py
   → LLM-анализ violations + контекста
   → генерация post-mortem.md
   → список конкретных proposals с confidence

6. notify + wait for approval
```

**Output:** `~/.config/opencode/reflection/reports/<date>-postmortem-<target>.md`

### 5.2 Wave-driven

**Назначение:** в конце wave — compliance check всего что было сделано.

**Триггер:** архитектор или `/finish-wave <name>` команда.

**Flow:**

```
1. identify_wave_sessions.py
   → match by title pattern (e.g., "Wave 4.5 старт" + suffix 1/2/3)
   → list of sessions in this wave

2. reconstruct_tree.py
   → дерево для всей wave

3. workflow_checks.py
   → 6 checks на всех sessions wave'ы
   → group by subagent

4. quality_scoring.py
   → skill effectiveness score для wave
   → token efficiency per session
   → cost analysis

5. analyze.py
   → LLM-генерация wave-report.md
   → highlights: что прошло хорошо, что нет, proposals

6. notify
```

**Output:** `~/.config/opencode/reflection/reports/<date>-wave-<name>.md`

### 5.3 Time-driven (nightly)

**Назначение:** каждую ночь — общий обзор workflow + regression detection.

**Триггер:** cron `0 3 * * *` или `reflect.sh nightly --days=7`.

**Flow:**

```
1. collect_sessions.py
   → last 7 days sessions из opencode.db

2. workflow_checks.py
   → checks на всех sessions (агрегированная статистика)

3. regression_detection.py
   → duration trends: tool/session/wave/test (current vs previous 7d)
   → если delta > 30% → alert

4. cost_trends.py
   → cost per agent, per day, per session
   → spike detection

5. quality_scoring.py
   → aggregate skill effectiveness за период

6. analyze.py
   → nightly-digest.md
   → top 3 critical issues + top 5 proposals

7. notify (telegram если severity >= warning)
```

**Output:** `~/.config/opencode/reflection/reports/<date>-nightly.md`

---

## 6. Workflow compliance checks

**16 checks в MVP**, организованных по severity:

| Severity | Кол-во | Назначение |
|----------|--------|-----------|
| **critical** | 5 | Контроль hard rules (architect не имплементит, ревью обязательны, gates пройдены) |
| **warning** | 8 | Качество workflow (TDD, loops, recovery, completeness) |
| **info** | 3 | Гигиена (orphans, dead-ends, context overflow) |

Базовые 6 checks (§6.1-6.6) мапятся на Key Principles SuperAgents README. Дополнительные 10 (§15) — на emergent anti-patterns. Все checks настраиваются per-project через `reflect.config.json` (`enabled: bool`).

Каждый check — функция в `workflow_checks.py` с интерфейсом:

```python
def check_X(session_tree: SessionTree, config: dict) -> List[Violation]:
    """Возвращает список violations для данного check."""
```

Добавление нового check = новая функция + регистрация в `WORKFLOW_CHECKS` dict. Существующие checks можно отключить per-project без удаления кода.

### 6.1 `controller_never_implements` (Principle 1)

**Что ловит:** architect-agent вызывал edit/write/apply_patch tools.

```sql
SELECT s.id, s.title, COUNT(*) AS code_edits
FROM session s
JOIN part p ON p.session_id = s.id
WHERE s.agent = 'architect'
  AND json_extract(p.data, '$.tool') IN ('edit', 'write', 'apply_patch')
  AND json_extract(p.data, '$.state.error') IS NULL
  AND s.time_created > ?
GROUP BY s.id
HAVING code_edits > 0;
```

**Severity:** critical
**Proposal:** "Architect в {N} сессий редактировал {files} файлов напрямую. Возможные причины: implementer fail → architect починил сам. Решение: разбить задачу или улучшить implementer."

### 6.2 `mandatory_reviewer_for_code` (Principle 2)

**Что ловит:** spec-reviewer и code-quality-reviewer не вызваны для файлов matching `*.ts|*.tsx|*.py`.

**Сложнее:** нужен git diff на каждой session, чтобы знать какие файлы трогали. Reconstruct tree → для каждой subagent session найти file list → проверить что review session был вызван.

**Severity:** critical
**Proposal:** "В {wave} пропущен code-quality-review для {N} файлов. Восстановить или добавить hook в opencode.jsonc."

### 6.3 `tdd_red_first` (Principle 7)

**Что ловит:** subagent начал с edit, не с test run.

```sql
SELECT s.id, s.title, s.agent,
  (SELECT json_extract(p.data, '$.tool') 
   FROM part p WHERE p.session_id = s.id 
   ORDER BY p.time_created LIMIT 1) AS first_tool
FROM session s
WHERE s.agent IN ('frontend-coder', 'backend-coder')
  AND s.parent_id IS NOT NULL
  AND s.time_created > ?;
```

**Severity:** warning
**Proposal:** "Frontend-coder в {N}/{M} сессий начал с edit (без test). TDD не соблюдается. Усилить skill 'test-driven-development' triggers в agent.md."

### 6.4 `max_review_loops` (Principle 5)

**Что ловит:** больше 3 review iterations на одну wave.

**Severity:** warning
**Proposal:** "В {wave} — {N} итераций по code-quality-reviewer (>3 лимит). Задача слишком крупная, разбить."

### 6.5 `gate_compliance` (Principle 4)

**Что ловит:** пропущены Human Gates (G1a, G1b, G2, G7).

**Сложно:** нужно знать какие gates были для конкретной feature. Используем metadata сессии + title pattern. Если в workflow были gate markers, а в session — нет, считаем пропущенным.

**Severity:** critical
**Proposal:** "В {N}/{M} feature waves пропущен G2 approval. Возможно архитектор не вызвал /present-plan."

### 6.6 `regression_test_on_bugfix` (Principle 7)

**Что ловит:** session помечена как bug-fix, но regression test не добавлен.

**Эвристика:** session.title содержит "fix", "bug", "patch" → bug-fix. В этой session — есть ли `bash` calls с pattern `vitest|pytest|test.*new|describe.*new`?

**Severity:** warning
**Proposal:** "В fix-сессии {title} не добавлен regression test. Зафиксировать или обновить architect control flow."

### 6.7 Расширяемость

Каждый check — это функция в `workflow_checks.py` с интерфейсом:

```python
def check_X(session_tree: SessionTree, config: dict) -> List[Violation]:
    """Возвращает список violations для данного check."""
```

Добавление нового check = новая функция + регистрация в `WORKFLOW_CHECKS` dict.

---

## 7. Decision log & Closing-the-loop

### 7.1 Decision log (audit trail)

Каждый proposal при создании получает ID и сохраняется как файл:

```markdown
<!-- ~/.config/opencode/reflection/proposals/2026-06-19-spec-reviewer-checklist.md -->
# Proposal: Update spec-reviewer checklist

**ID:** prop-2026-06-19-001
**Generated:** 2026-06-19 03:00:00
**Mode:** wave-driven
**Severity:** warning
**Confidence:** 0.85
**Auto-apply eligible:** ❌ (severity=warning, requires approval)

## Target
`~/.config/opencode/agents/spec-reviewer.md`

## Rationale
Wave 4.5: 3/5 spec-review сессий одобрили код без проверки edge cases...

## Proposed diff
[вставка diff блока]

## Action
- [ ] Approve (apply diff)
- [ ] Reject (reason: ___)
- [ ] Modify (specify changes)
```

**Когда юзер одобряет/отклоняет**, файл перемещается в `decisions/`:

```markdown
<!-- decisions/2026-06-19-spec-reviewer-checklist.md -->
# Decision: prop-2026-06-19-001

**Original proposal:** proposals/2026-06-19-spec-reviewer-checklist.md
**Decided:** 2026-06-19 14:23 by user
**Outcome:** applied | rejected | modified
**Applied diff commit:** abc123
**Reason for reject:** "..."
```

### 7.2 Closing-the-loop

Когда reflector генерирует новый proposal или запускает bug-driven post-mortem:

```
1. closing_the_loop.py
   → Берёт новые violations / bug context
   → Ищет в decisions/ прошлые proposals с overlap (по file pattern, по keywords)
   → Если найдено:
     - matched proposal applied < 30 days ago → mark "should have prevented"
     - matched proposal applied > 30 days ago → "didn't prevent" 
     - matched proposal rejected → "user decision not to fix"
   → Добавляет секцию "Related past decisions" в новый proposal/report
```

**Метрика:** `applied_proposals_prevented_bugs / total_applied_proposals` — ROI reflector'а.

### 7.3 Quality / effectiveness scoring

Для каждого skill/agent — набор метрик:

```python
# quality_scoring.py
@dataclass
class EffectivenessScore:
    name: str                              # skill or agent name
    type: str                              # "skill" | "agent" | "workflow_step"
    usage_count: int                       # как часто вызывался
    success_rate: float                    # heuristic: % вызовов без error/correction
    token_efficiency: float                # median tokens на usage
    user_correction_rate: float            # % вызовов после которых user поправил
    duration_impact_ms: float              # median duration
    composite_score: float                 # weighted aggregate
    confidence: float                      # 0-1 на основе sample size
```

**Heuristics для success:**
- Tool call завершился `status="completed"` без error
- В следующих 3 messages не было user correction (heuristic via LLM classify)
- Session завершилась без BLOCKED

**LLM classify (опционально):** для подозрительных случаев — LLM анализирует 3-5 последних сообщений после skill call → "was this useful?"

**Output:** агрегируется в отчёт `top_5_most_effective_skills` + `top_5_least_effective_skills`.

---

## 8. Auto-apply architecture

**MVP:** auto-apply ВЫКЛЮЧЕН. Но архитектура поддерживает.

### 8.1 Eligibility rules

```python
def is_auto_apply_eligible(proposal: Proposal) -> bool:
    if not config.auto_apply.enabled:
        return False
    
    if proposal.severity not in config.auto_apply.allowed_severities:
        return False
    
    if proposal.confidence < config.auto_apply.min_confidence:
        return False
    
    if proposal.type not in config.auto_apply.allowed_types:
        return False
    
    return True
```

**Default safe cases (если юзер включит):**
- `archive-skill` (удаление неиспользуемого скилла)
- `comment-cleanup` (удаление TODO комментариев)
- `docs-update` (исправление опечаток в docs)

**Всегда требуют approval:** изменения в agent.md, opencode.jsonc, SKILL.md workflow-changing.

### 8.2 CLI flag

```bash
reflect.sh nightly --days=7 --auto-apply   # включает auto-apply для eligible
reflect.sh nightly --days=7                 # dry-run (default в MVP)
```

### 8.3 Audit для auto-apply

Даже auto-applied proposals логируются в `decisions/`:

```markdown
# Decision: prop-2026-06-19-002 (auto-applied)

**Outcome:** applied
**Mode:** auto-apply (config.enabled=true)
**Eligibility:** confidence=0.97, severity=info, type=archive-skill
**Applied at:** 2026-06-19 03:00:12
**Undo command:** `git revert <commit>` (if proposal was committed)
```

---

## 9. Configuration & sync

### 9.1 Per-project конфиг

Файл `~/.config/opencode/reflect.config.json` — **не** в golden source, создаётся per-project.

```jsonc
{
  "workflow_checks": {
    "controller_never_implements": { "enabled": true, "severity": "critical" },
    "mandatory_reviewer_for_code": { 
      "enabled": true, 
      "file_patterns": ["*.ts", "*.tsx", "*.py"],
      "severity": "critical" 
    },
    // ... остальные 4 checks
  },
  "auto_apply": { "enabled": false },
  "notify": { 
    "telegram_chat_id": "384096803",
    "min_severity_to_notify": "warning"
  },
  "thresholds": {
    "regression_delta_pct": 30,
    "min_confidence_for_proposal": 0.6
  }
}
```

### 9.2 Sync protocol

| Что | Где живёт | Как синхронизируется |
|-----|-----------|---------------------|
| `reflect` skill | `superagents/skills/reflect/` (source) → `~/.config/opencode/skills/reflect/` (installed) | @infra (как остальные skills) |
| `reflector` agent | `superagents/agents/reflector.md` → `~/.config/opencode/agents/reflector.md` | @infra |
| `reflect.config.json` | Только `~/.config/opencode/` (per-project, не синхронизируется) | ручная правка |
| Runtime storage | Только `~/.config/opencode/reflection/` (per-install, не синхронизируется) | — |

**Container restart** не требуется — skill и agent подхватываются при следующем запуске subagent'а.

### 9.3 Cron setup

```bash
# /etc/cron.d/opencode-reflect
0 3 * * * root /root/.config/opencode/skills/reflect/scripts/reflect.sh nightly --days=7 2>&1 | logger -t opencode-reflect
```

---

## 10. Visual Compliance Checks

**N/A — feature без UI.**

Reflection Mode — это CLI skill + subagent. Не имеет UI компонентов, не влияет на отображение страниц Memo или других проектов. Visual Compliance Gate (Step 4.5) не применяется.

Если в будущем появится web UI для просмотра отчётов (например, dashboard), для него будет отдельный spec с Visual Compliance Checks.

---

## 11. Implementation outline (для plan)

| Слой | Файлы | Время |
|------|-------|-------|
| **Foundation** | | |
| Session-tree reconstructor | `reconstruct_tree.py` + `queries.sql` | 1 день |
| File→session attribution | `attribute_to_sessions.py` | 0.5 дня |
| 16 workflow checks | `workflow_checks.py` (6 base + 10 из §15) | 1 день |
| LLM proposal generator | `analyze.py` | 0.5 дня |
| CLI wrapper | `reflect.sh` | 0.3 дня |
| **Additions** | | |
| Decision log | `decisions/` + audit logic | 0.5 дня |
| Auto-apply architecture | CLI flag + eligibility | 0.3 дня |
| Confidence scoring | в `analyze.py` | 0.5 дня |
| Regression detection | duration/cost queries + thresholds | 0.5 дня |
| Cost trends | aggregate queries | 0.5 дня |
| Duration tracking | part timestamps | 0.5 дня |
| Quality scoring | `quality_scoring.py` | 1 день |
| Closing-the-loop | `closing_the_loop.py` | 1 день |
| **Auto skill generation** | `detect_skill_candidates.py` | 1 день |
| **Reflection scoring** | metrics + trends в `analyze.py` | 0.5 дня |
| **Modes** | | |
| Bug-driven | post-mortem template + flow | 1 день |
| Wave-driven | wave identifier + template | 0.5 дня |
| Time-driven | nightly cron + telegram notify | 0.5 дня |
| **Infra** | | |
| Agent `reflector.md` | subagent definition | 0.2 дня |
| SKILL.md + README | docs | 0.5 дня |
| 4 example отчёта | examples/ | 0.5 дня |
| Per-project config example | `reflect.config.example.json` | 0.2 дня |
| **Validation** | | |
| Dry-run на 1110 сессиях | retro-testing | 1 день |
| Отладка false positives | tune thresholds | 0.5 дня |
| **ИТОГО** | | **~11-12 дней** |

---

## 12. Open questions

| # | Вопрос | Решение |
|---|--------|---------|
| 1 | Где хранить runtime state (`state.json`)? | `~/.config/opencode/reflection/state.json` (per-install) |
| 2 | Telegram notification: chat_id откуда? | Из `reflect.config.json` или env `OPENCODE_NOTIFICATION_TELEGRAM_CHAT_ID` |
| 3 | Что делать с очень старыми sessions (>90 дней)? | Архивировать в `reflection/reports/archive/`, queries с cutoff |
| 4 | Как отслеживать "deleted proposals"? | Каждое решение в `decisions/` хранится вечно, не удаляется |
| 5 | Multi-machine setup? (если несколько opencode контейнеров) | Каждый контейнер свой `~/.config/opencode/`, reflection не синхронизируется. Возможна v2 фича — shared storage |
| 6 | Privacy: если в сессии были секреты? | `part.state.metadata.output` может содержать echo команд. **Действие перед v1.0:** добавить redactor pass (regex для API keys, токенов, паролей) перед отправкой в LLM. **До MVP** достаточно фильтра `sk-*`, `AIza*`, `Bearer *`, password env vars |

---

## 13. Sources / inspiration

- **Letta** (бывший MemGPT) — sleep-time subagents, memory blocks, BlockHistory
- **Hermes Agent** (Nous Research) — Closed Learning Loop, OERC, Curator Daemon, GEPA
- **Reflexion** (NeurIPS 2023) — verbal self-reflection
- **Voyager** (MineDojo) — skill library + self-verification
- **OpenClaw reflect skill** — `/reflect weekly` простой CLI подход

(Использовано как inspiration, не копируется 1:1 — у нас свой scope и constraints.)

---

## 14. Additional workflow checks (10 новых)

К базовым 6 checks из §6 добавляем 10. Все реализуются как функции в `workflow_checks.py`. Каждый настраивается per-project (`enabled: bool`, `severity`, `threshold`).

### 15.1 `stuck-in-retry` (critical) ⭐ твой приоритет

**Что ловит:** Тот же `bash` command повторяется 3+ раза в одной сессии с **одинаковым** command'ом (без вариации).

```sql
SELECT session_id,
       json_extract(data, '$.state.metadata.input.command') AS cmd,
       COUNT(*) AS repeats
FROM part
WHERE json_extract(data, '$.tool') = 'bash'
  AND time_created > ?
GROUP BY session_id, cmd
HAVING repeats >= 3;
```

**Severity:** critical
**Proposal:** "В session {id} bash команда `{cmd}` повторена {N} раз без вариации. Возможные причины: tool error не прочитан, retry без диагностики. Добавить в agent rules: 'если команда вернула error — diagnose before retry'."

### 15.2 `same-error-repeated` (critical) ⭐ твой приоритет

**Что ловит:** Один и тот же tool падает с тем же `state.error` в 3+ разных sessions.

```sql
WITH recent_errors AS (
  SELECT
    json_extract(data, '$.tool') AS tool,
    json_extract(data, '$.state.error') AS error_pattern,
    COUNT(DISTINCT session_id) AS session_count
  FROM part
  WHERE json_extract(data, '$.state.error') IS NOT NULL
    AND time_created > ?
  GROUP BY tool, error_pattern
  HAVING session_count >= 3
)
SELECT * FROM recent_errors ORDER BY session_count DESC;
```

**Severity:** critical
**Proposal:** "Tool `{tool}` падает с ошибкой `{error}` в {N} разных сессиях. Это системная проблема. Возможные действия: убрать tool, добавить fallback, обновить opencode, заблокировать egress."

### 15.3 `arch-session-too-long` (warning) ⭐ твой приоритет

**Что ловит:** Main session (architect) длится > 30 минут без subagent dispatch.

```sql
SELECT s.id, s.title,
       (s.time_updated - s.time_created) / 1000.0 AS duration_sec,
       (SELECT COUNT(*) FROM session WHERE parent_id = s.id) AS subagent_count
FROM session s
WHERE s.agent = 'architect'
  AND s.parent_id IS NULL
  AND (s.time_updated - s.time_created) > 30 * 60 * 1000
  AND subagent_count = 0;
```

**Severity:** warning
**Proposal:** "Main session {id} работала {N} минут без subagent. Архитектор сам делал работу — нарушение Principle 1 или over-thinking. Декомпозировать или dispatch'нуть subagent."

### 15.4 `skill-triggered-when-should` (warning) ⭐ твой приоритет

**Что ловит:** Subagent менял файлы, требующие обязательного skill, но skill не вызван.

**Implementation:** Whitelist обязательных skills per file pattern:

```jsonc
// reflect.config.json
{
  "skill_triggers": {
    "frontend-coder": [
      { "files": ["*.tsx", "*.ts"], "required_skill": "vitest-playwright-patterns" },
      { "files": ["components/**"], "required_skill": "vercel-composition-patterns" }
    ],
    "backend-coder": [
      { "files": ["api/**", "models/**"], "required_skill": "fastapi-clean-architecture" },
      { "files": ["tests/**"], "required_skill": "pytest-patterns" }
    ],
    "architect": [
      { "files": [".opencode/**"], "required_skill": "subagent-driven-development" }
    ]
  }
}
```

**Severity:** warning
**Proposal:** "В session {id} implementer менял `{file}` (matching `*.tsx`), но skill `vitest-playwright-patterns` не вызван. Добавить в agent.md trigger или рассмотреть skill устарел."

### 15.5 `subagent-completion-rate` (warning)

**Что ловит:** % subagent сессий с `status=error` vs `completed` ниже threshold (default 80%).

```sql
SELECT agent,
  SUM(CASE WHEN time_archived IS NOT NULL THEN 1 ELSE 0 END) AS archived,
  COUNT(*) AS total
FROM session
WHERE parent_id IS NOT NULL
  AND time_created > ?
GROUP BY agent;
```

**Severity:** warning
**Proposal:** "Agent `{agent}` completion rate {N}% за 7 дней (target 80%). Паттерн: {N} сессий завершились ошибкой. Изучить логи."

### 15.6 `first-time-right` (warning)

**Что ловит:** Задача завершена с 0 review iterations (идеал) vs > 3 (плохо).

```sql
WITH wave_reviews AS (
  SELECT parent_id, COUNT(*) AS review_count
  FROM session
  WHERE agent IN ('spec-reviewer', 'code-quality-reviewer')
    AND time_created > ?
  GROUP BY parent_id
)
SELECT
  SUM(CASE WHEN review_count = 0 THEN 1 ELSE 0 END) AS zero,
  SUM(CASE WHEN review_count = 1 THEN 1 ELSE 0 END) AS one,
  SUM(CASE WHEN review_count = 2 THEN 1 ELSE 0 END) AS two,
  SUM(CASE WHEN review_count >= 3 THEN 1 ELSE 0 END) AS three_plus,
  COUNT(*) AS total
FROM wave_reviews;
```

**Severity:** warning
**Proposal:** "First-time-right rate: {N}% (target 50%). {M}% wave'ов требуют 3+ итераций — задачи слишком крупные или implementer не понимает спеку."

### 15.7 `over-orchestration` (warning)

**Что ловит:** Main session с > 6 subagent вызовами.

```sql
SELECT s.id, s.title, COUNT(child.id) AS subagent_count
FROM session s
JOIN session child ON child.parent_id = s.id
WHERE s.agent = 'architect' AND s.parent_id IS NULL
  AND s.time_created > ?
GROUP BY s.id
HAVING subagent_count > 6;
```

**Severity:** warning
**Proposal:** "Main session {id} запустила {N} subagent'ов. Возможно wave слишком крупная — разбить на 2-3 wave'ы."

### 15.8 `dead-end-sessions` (info)

**Что ловит:** Session завершилась < 1 минуты без subagent (failed fast).

```sql
SELECT id, title, agent,
  (time_updated - time_created) / 1000.0 AS duration_sec
FROM session
WHERE (time_updated - time_created) < 60 * 1000
  AND parent_id IS NULL
  AND time_created > ?;
```

**Severity:** info
**Proposal:** "Session {id} завершилась за {N} сек без результата. Возможно context issue или wrong agent."

### 15.9 `skill-orphan` (info)

**Что ловит:** Skill существует, не вызывался > 30 дней.

**Implementation:** List `~/.config/opencode/skills/*/SKILL.md` → cross-reference с `part.tool = "skill"` в opencode.db → skill-orphan = last call > 30d ago.

**Severity:** info
**Proposal:** "Skill `{name}` не вызывался {N} дней. Архивировать или обновить triggers."

### 15.10 `context-overflow` (info)

**Что ловит:** Sessions с `time_compacting IS NOT NULL` (opencode triggered compaction).

```sql
SELECT id, title, agent, time_compacting
FROM session
WHERE time_compacting IS NOT NULL
  AND time_created > ?;
```

**Severity:** info
**Proposal:** "Session {id} триггернула compaction — контекст переполнился. Возможно: long session без /reset, или задача слишком комплексная."

### 15.11 `missed-parallelism` (info) ⭐ поощряем параллелизм

**Что ловит:** Subagent вызовы в одной wave, которые **могли быть параллельны** (нет data dependency между ними).

**Note:** Это **положительный** check — поощряем параллелизм, а не enforce sequential. Противоречит текущему Principle 3 в superagents README — нужна отдельная дискуссия по Principle 3.

**Heuristic:** Если 2+ subagent'а запущены в одной main session и не было `user message` между их `parent_id` references — candidates for parallel.

**Severity:** info
**Proposal:** "В wave {name} 3 subagent'а запущены последовательно. Анализ показал отсутствие data dependency между ними. Можно было параллелить через async task(). Рассмотрите добавление в agents/architect.md: 'если subagent не зависит от результата другого — параллель'."

---

## 15. Automatic skill generation

Reflection-mode может предлагать **создание новых skills** на основе паттернов.

### 16.1 Детекция кандидатов

```python
# scripts/detect_skill_candidates.py

PATTERNS = {
    "recurring_recovery": {
        "description": "Tool A error → Tool B success повторяется N+ раз",
        "min_count": 3,
        "action": "Propose skill '<b>-recovery'"
    },
    "recurring_command_sequence": {
        "description": "Одинаковая последовательность bash/read/write N+ раз",
        "min_count": 5,
        "action": "Propose skill wrapping this sequence"
    },
    "user_repeated_warning": {
        "description": "Юзер 3+ раза сказал то же предупреждение (LLM classify)",
        "min_count": 3,
        "action": "Propose skill enforcing the rule"
    },
    "subagent_repeated_clarification": {
        "description": "Subagent 5+ раз задал один и тот же clarifying question",
        "min_count": 5,
        "action": "Propose skill with standard answer"
    }
}
```

### 16.2 Proposal format

```markdown
# Proposal: create-skill websearch-fallback

**ID:** prop-2026-06-19-015
**Type:** create-skill
**Mode:** time-driven (detected in nightly scan)
**Severity:** info
**Confidence:** 0.78
**Auto-apply eligible:** ❌ (create-skill ВСЕГДА требует approval)

## Detected pattern
23/47 сессий researcher-agent встретил `websearch` Decode error →
через 1 шаг успешный вызов `websearch_cited`.

## Proposed skill

File: `~/.config/opencode/skills/websearch-fallback/SKILL.md`

```yaml
name: websearch-fallback
description: |
  TRIGGER: When websearch (Exa) returns "Decode error" or "Connection timeout".
  ACTION: Do not retry. Immediately call websearch_cited with same query.
```

## Action
- [ ] Approve (skill будет создан в указанном пути)
- [ ] Modify (specify changes to skill content)
- [ ] Reject (reason: ___)
```

### 16.3 Whitelist allowed paths

Skills создаются **только** в `~/.config/opencode/skills/`. Никогда не пишем в `superagents/skills/` автоматически — это ручная синхронизация через @infra.

---

## 16. Reflection process scoring

**Meta:** сам reflection-mode тоже нужно мерить. Без этого непонятно — помогает он или мешает.

### 17.1 Метрики

```python
@dataclass
class ReflectionMetrics:
    # Proposal quality
    proposal_adoption_rate: float      # applied / (applied + rejected)
    avg_confidence_accepted: float     # средний confidence одобренных
    avg_confidence_rejected: float     # средний confidence отклонённых
    
    # Эффект
    compliance_trend: List[float]      # % passing checks по дням
    closing_loop_hit_rate: float       # applied proposals, которые предотвратили same-class bug
    
    # Стоимость
    avg_tokens_per_reflection: float
    cost_per_wave_analyzed: float
    
    # Coverage
    waves_analyzed_7d: int
    waves_skipped_7d: int              # cron упал / не было событий
    
    # Здоровье
    false_positive_rate: float         # % rejected (высокий = шумно)
    avg_time_to_decision_hours: float
```

### 17.2 Где показываем

Секция в **nightly-digest**:

```markdown
## 🪞 Reflection Health

| Metric | This run | 7d avg | Trend |
|--------|----------|--------|-------|
| Proposals generated | 12 | 9 | ↑ |
| Adoption rate | 67% | 65% | → |
| False positive rate | 25% | 22% | ↑ (warning) |
| Compliance score | 78% | 75% | ↑ |
| Tokens used | 24K | 22K | normal |
| Time to decision (avg) | 2.3h | 3.1h | ↓ (better) |
```

### 17.3 Meta-alerts

```
⚠️ "False positive rate 35% (>30%) — tune thresholds, слишком много noise"
⚠️ "Adoption rate 25% (<50%) — proposals не находят отклика, проверь качество"
⚠️ "Compliance trend ↓5% over 14 days — workflow ухудшается, нужны действия"
```

### 17.4 Implementation

- `~/.config/opencode/reflection/metrics.json` — агрегаты за 30/90 дней
- Rolling windows считаются в `analyze.py`
- Не в state.json (там только cursors для idempotency)

---

## 17. Updated implementation outline

| Слой | Файлы | Время |
|------|-------|-------|
| **Foundation** | | |
| Session-tree reconstructor | `reconstruct_tree.py` + `queries.sql` | 1 день |
| File→session attribution | `attribute_to_sessions.py` | 0.5 дня |
| 16 workflow checks | `workflow_checks.py` (6 base + 10 из §15) | 1 день |
| LLM proposal generator | `analyze.py` | 0.5 дня |
| CLI wrapper | `reflect.sh` | 0.3 дня |
| **Additions** | | |
| Decision log | `decisions/` + audit logic | 0.5 дня |
| Auto-apply architecture | CLI flag + eligibility | 0.3 дня |
| Confidence scoring | в `analyze.py` | 0.5 дня |
| Regression detection | duration/cost queries + thresholds | 0.5 дня |
| Cost trends | aggregate queries | 0.5 дня |
| Duration tracking | part timestamps | 0.5 дня |
| Quality scoring | `quality_scoring.py` | 1 день |
| Closing-the-loop | `closing_the_loop.py` | 1 день |
| **Auto skill generation** | `detect_skill_candidates.py` | 1 день |
| **Reflection scoring** | metrics + trends в `analyze.py` | 0.5 дня |
| **Modes** | | |
| Bug-driven | post-mortem template + flow | 1 день |
| Wave-driven | wave identifier + template | 0.5 дня |
| Time-driven | nightly cron + telegram notify | 0.5 дня |
| **Infra** | | |
| Agent `reflector.md` | subagent definition | 0.2 дня |
| SKILL.md + README | docs | 0.5 дня |
| 4 example отчёта | examples/ | 0.5 дня |
| Per-project config example | `reflect.config.example.json` | 0.2 дня |
| **Validation** | | |
| Dry-run на 1110 сессиях | retro-testing | 1 день |
| Отладка false positives | tune thresholds | 0.5 дня |
| **ИТОГО** | | **~11-12 дней** |

---

## 18. Self-review checklist (final)

- [x] 16 workflow checks описаны (6 base §6 + 10 новых §15)
- [x] Три trigger mode описаны с flow (§5)
- [x] Non-goals явные и обоснованы (§2.2)
- [x] Storage на filesystem (не новая БД) — соответствует требованию "не создавая новую большую БД" (§4.2)
- [x] Per-project config отдельно от skill/agent (§4.3, §9.1)
- [x] Sync protocol использует существующий (@infra) (§9.2)
- [x] Auto-apply архитектурно поддержан, но off в MVP (§8)
- [x] Closing-the-loop и quality scoring включены в MVP (§7.2, §7.3)
- [x] Automatic skill generation описан (§16)
- [x] Reflection process scoring описан (§17)
- [x] Visual Compliance Checks N/A (нет UI) (§10)
- [x] Связь с Key Principles superagents явная (§6 + §3.3)
- [x] Domain rules явно вне scope (§12.1 — закрыт в чате, вынесу в open question если нужно)
- [x] Sequential vs parallel: поощряем parallelism через `missed-parallelism` check (§15.11)
- [x] Open questions явно перечислены с действиями (§12)

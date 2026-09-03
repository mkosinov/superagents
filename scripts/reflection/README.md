# Reflection v4 (host-side) — README & integration contract

Status: **VALIDATED / PILOT DONE / CRON NOT YET CREATED** (2026-09-03).
Owner/maintainer: zcode host session `sess_93bd2e05-49fc-4d50-b097-735c3e6834ef`
(the nightly analyst lives there once cron is created).

## What this is

Ночной аналитик процесса разработки (issue #13): детерминированный экстрактор
фактов из opencode.db + анализ-сессия zcode на хосте (drill-down по сырым
транскриптам) → лента находок (`~/dev/opencode/reflection-host/index.json`) →
готовые патчи в superagents по accept пользователя. Замена контейнерного
reflection-скилла (тот заморожен, backlog 2098 proposals не трогаем).

## Files

- `facts.py` — экстрактор (read-only sqlite внутри контейнера `opencode`).
  CLI: `--days N | --since/--until`, `--out pack.json --md pack.md`.
- `rules-digest.md` — дистиллят правил pipeline для аналитика.
- Runtime (вне репо): `~/dev/opencode/reflection-host/{index.json,reports/,proposals/}`.
- Протокол ночной сессии — в prompt cron-задачи zcode (создаётся после миграции).

## ⚠️ Dependencies on memo/container — migration MUST read this

1. **Data source**: `docker exec opencode sqlite3 "file:/root/.local/share/opencode/opencode.db?mode=ro"`
   (read-only, busy_timeout 30s), фильтр сессий `session.directory = '/root/workspace/memo'`.
   Схема: `session` (parent_id, agent, tokens_*, time_* в epoch-ms),
   `message.data$.role`, `part.data` JSON (type=tool/task/text; state.input.command,
   state.input.filePath, state.output, state.error).
2. **Если memo переезжает с `/root/workspace/memo`** — нужно обновить `MEMO_DIR`
   в facts.py И путь доступа к базе (если opencode-сервер остаётся в контейнере,
   но проект уехал — фильтр меняется на новый directory).
3. **Если сессии разработки переезжают на хост (zcode)** — opencode.db перестанет
   пополняться; reflection остаётся без новых данных. Тогда: либо (a) держать
   разработку memo в opencode (где бы он ни жил), либо (b) у reflection появляется
   второй адаптер источника под новое хранилище сессий. Схема-маппинг уже в facts.py.
4. **Open items пересекаются с миграцией**: патчи 001/002 (см.
   `~/dev/opencode/reflection-host/proposals/2026-09-02/`) меняют
   `agents/spec-reviewer.md` и `agents/architect.md` — НЕ трогать эти файлы
   параллельно с миграционным синком; статус патчей: ждут accept пользователя.
5. **Container touch policy**: никаких правок контейнера/compose; факты читаются
   через `docker exec`, синк принятых правок — `docker cp` (golden source rule).

## Interface for the migration agent

- Прочитать этот файл + `rules-digest.md` — этого достаточно.
- Вопросы/согласование — через пользователя с session id выше
  (ReadSessionContext по `sess_93bd2e05-…`), либо пользователь ретранслирует.
- После переезда memo прислать: новый путь проекта, где теперь живут сессии,
  дату среза — reflection обновит MEMO_DIR/адаптер и продолжит с того же
  findings index.

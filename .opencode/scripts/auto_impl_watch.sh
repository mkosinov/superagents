#!/usr/bin/env bash
# auto_impl_watch.sh — контейнерный наблюдатель IMPL-конвейера superagents.
#
# Инвариант (раз в INTERVAL): если есть карточка Ready to IMPL, доступная
# этому наблюдателю, — захватить её (статус In IMPL + поле host на борде)
# и запустить фоном `opencode run` (дефолтный агент superagents = manager).
# ГЛОБАЛЬНОГО мьютекса и глобального бюджета нет: слоты ПО МАШИНАМ
# (host_budgets в docs/board/board_config.json, imac 2 / macbook 1); гонку
# за одну карточку ломает тайбрейк по полю host (запись, пауза, перечитывание
# — владеет последний писавший, ранний отходит).
#
# Старт:  docker exec -d opencode bash /root/workspace/superagents/.opencode/scripts/auto_impl_watch.sh
# Стоп:   docker exec opencode pkill -f '^bash /root/workspace/superagents/.opencode/scripts/auto_impl_watch\.sh$'
#         ВАЖНО: якоря ^…$ обязательны — без них pkill -f убивает и entrypoint-обёртку
#         контейнера (в её cmdline тоже есть имя скрипта) → контейнер перезапускается
#         по restart-политике и ГИБНУТ все живые сессии менеджеров (инцидент 2026-09-20).
# Вкл.:   docker exec opencode touch /root/.local/state/opencode/auto-impl.enabled
# Выкл.:  docker exec opencode rm -f /root/.local/state/opencode/auto-impl.enabled
#
# Метка хоста: /root/.local/state/opencode/auto-impl-host — должна совпадать
# с вариантом поля host на борде ("imac"/"macbook";hk/gcp зарезервированы).
# Повторные попытки по issue ПРОДОЛЖАЮТ существующую сессию менеджера
# (opencode run --session <id>): id берётся из БД — последняя сессия с
# названием «<N> IMPL. …». Отдельного реестра сессий нет, БД = источник истины.
# Ёмкость машины = бюджет хоста на БОРДЕ (host_budgets в
# docs/board/board_config.json: imac 2 / macbook 1) — карточки «In IMPL» с
# меткой этого хоста, считается внутри pick-next. Финишный менеджер, чья
# карточка ушла в PR (G7) на CI, НЕ считается (2026-09-21, решение юзера:
# карточка на CI не занимает IMPL слот) — карточка больше не в In IMPL.
# Реестр auto-impl.pids УДАЛЁН (2026-09-21): был дублем борд-бюджета,
# состояние живёт на борде. Открытые UI/TUI-окна и ручные сессии юзера без
# карточки In IMPL ёмкость не занимают (грабли 14.09: открытые окна
# блокировали конвейер). Заморозка машины без снятия флага: файл
# /root/.local/state/opencode/auto-impl-max = 0 (читается каждый цикл;
# env AUTO_IMPL_MAX_SESSIONS больше не используется).
# Выбор карточки: gh_board.py pick-next "$HOST_LABEL" (первая Ready to IMPL
# по приоритету; бюджет слотов своей машины по полю host; пропуск карточек
# со свежими записями и с незакрытыми depends-on из тела issue).
# Сверка стейл-карточек (2026-09-22): раз в цикл, ДО pick-next,
# gh_board.py reconcile "$HOST_LABEL" чинит два класса: (1) закрытый issue в
# In IMPL/PR (G7) — потерянный финальный флип → In-main/Not planned + строка
# merged; (2) In IMPL своего хоста с ЗАВИСШИМ прогоном — сессии в opencode.db
# молчат больше часа (CLI opencode run — лишь клиент-наблюдатель, он
# отваливается, пока сессия работает в сервере) → запись BLOCKED в
# auto-impl log (отдых CLAIM_TTL_HOURS, анти-crash-loop) + назад в
# Ready to IMPL. Проверка живости — по базе сессий, поэтому пункт 2 работает
# только из контейнера; с хоста (macOS) он пропускается.
# Владение карточкой = поле host на борде (единственный источник, 2026-09-20;
# CLAIM-комментарии больше не пишутся). Комментарий «auto-impl log:» на issue
# остаётся каналом BLOCKED-событий менеджера; свежая BLOCKED-запись —
# карточка отдыхает (CLAIM_TTL_HOURS = 1ч в gh_board.py). Блокер, ждущий
# юзера, дополнительно отмечается полем gate (значение blocked); снимается
# менеджером при продолжении либо автоматически при уходе из In IMPL.
# Параметризация под superagents (порт из memo, pin 20b710f7): рабочий
# каталог /root/workspace/superagents; pid-lock /tmp/auto-impl-watch-superagents.lock
# (наблюдатель memo живёт в ТОМ ЖЕ контейнере — общий путь лока исключал бы
# их друг друга); identity проекта gh_board.py берёт из
# docs/board/board_config.json (mkosinov/superagents). HANDOFF менеджера
# адаптирован: блокеры пишутся через gh_board.py auto-log (прямые правки
# комментариев запрещены — монополия скрипта на борд и комментарии), хвост
# про сдвиг очереди удалён (этой команды в superagents нет).

set -uo pipefail

REPO=/root/workspace/superagents
STATE=/root/.local/state/opencode
LOG="$STATE/auto-impl-watch.log"
LOCK=/tmp/auto-impl-watch-superagents.lock
INTERVAL="${AUTO_IMPL_INTERVAL:-180}"
TIEBREAK_WAIT=6   # сек: окно, в котором второй наблюдатель успевает перезаписать поле host

cd "$REPO" || exit 1
mkdir -p "$STATE"
exec >>"$LOG" 2>&1

if [ -e "$LOCK" ] && kill -0 "$(cat "$LOCK" 2>/dev/null)" 2>/dev/null; then
    echo "$(date -Is) watcher already running"
    exit 1
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

HOST_LABEL=$(cat "$STATE/auto-impl-host" 2>/dev/null || hostname)
export GH_BOARD_HOST="$HOST_LABEL"   # gh_board.py подставляет метку в pick-next и status
echo "=== auto-impl watcher start $(date -Is) host=$HOST_LABEL interval=${INTERVAL}s ==="

while true; do
    sleep "$INTERVAL"

    [ -f "$STATE/auto-impl.enabled" ] || continue

    # ёмкость решает борд (host_budgets по In IMPL+host внутри pick-next;
    # карточка на CI, статус PR (G7), не считается). Здесь — только ручная
    # заморозка машины без снятия флага: auto-impl-max = 0.
    if [ "$(cat "$STATE/auto-impl-max" 2>/dev/null || true)" = "0" ]; then
        continue
    fi

    # сверка стейл-карточек ДО выбора: чинить надо до захвата новых
    python3 .opencode/scripts/gh_board.py reconcile "$HOST_LABEL" \
        || echo "$(date -Is) reconcile failed"

    PICK=$(python3 .opencode/scripts/gh_board.py pick-next "$HOST_LABEL") || { echo "$(date -Is) board query failed: $PICK"; continue; }
    case "$PICK" in
        NONE|"") continue ;;
        *[!0-9]*) echo "$(date -Is) unexpected pick output: $PICK"; continue ;;
    esac
    N="$PICK"

    # захват одним действием: статус In IMPL + поле host (GH_BOARD_HOST экспортирован)
    echo "$(date -Is) claiming #$N on $HOST_LABEL"
    if ! python3 .opencode/scripts/gh_board.py status "$N" "In IMPL"; then
        echo "$(date -Is) status claim failed — skip"
        continue
    fi

    # тайбрейк гонки: после TIEBREAK_WAIT поле host на карточке должно быть
    # нашим (два наблюдателя могли захватить одновременно; владеет последний
    # писавший, ранний молча отходит)
    sleep "$TIEBREAK_WAIT"
    OWNER=$(python3 .opencode/scripts/gh_board.py host "$N" 2>/dev/null) || OWNER=""
    case "$OWNER" in
        "$HOST_LABEL") : ;;
        *) echo "$(date -Is) #$N lost claim race (owner=${OWNER:-none}) — back off"; continue ;;
    esac

    # свежий харнесс перед стартом
    git pull --ff-only >/dev/null 2>&1 || echo "$(date -Is) WARN: git pull failed, starting on current tree"

    # сессия менеджера по issue: повторный запуск ПРОДОЛЖАЕТ существующую.
    # Источник истины — БД: последняя сессия с названием «<N> IMPL. …»
    SID=$(sqlite3 /root/.local/share/opencode/opencode.db \
        "select id from session where title like '%#${N} IMPL.%' order by rowid desc limit 1" 2>/dev/null)

    # шаблон названия сессии: "#issue IMPL. 1-5 ключевых слова" (из заголовка issue)
    ITITLE=$(gh issue view "$N" --json title --jq .title 2>/dev/null || echo "")
    KEYWORDS=$(printf '%s' "$ITITLE" | awk '{out=""; for(i=1;i<=5&&i<=NF;i++) out=out (i>1?" ":"") $i; print out; exit}')
    TITLE="#${N} IMPL. ${KEYWORDS:-интерактив}"

    if [ -n "$SID" ]; then
        echo "$(date -Is) #$N → continue session $SID"
        MSG="Auto-IMPL retry: время отдыха по прежнему блокеру прошло — переоцени гейты и продолжай работу (если на карточке стоял gate=blocked — сними: gh_board.py gate $N none). Если блокер ещё в силе — снова запись «BLOCKED <причина>» в auto-impl log (python3 .opencode/scripts/gh_board.py auto-log $N \"BLOCKED <причина>\"), и gate blocked (gh_board.py gate $N blocked), если блокер ждёт пользователя — и стоп, ничего не начиная."
        # --attach: сессия живёт на работающем сервере (:4096) — сразу видна в вебе
        nohup opencode run --attach "http://localhost:${OPENCODE_PORT:-4096}" --dir "$REPO" \
            --session "$SID" "$MSG" > "$STATE/auto-impl-$N.log" 2>&1 &
    else
        HANDOFF="Авто-IMPL: карточка #$N взята из Ready to IMPL (статус уже In IMPL). Организуй IMPL по её спеке и плану из репо (mkosinov/superagents). ПЕРЕД СТАРТОМ проверь гейты плана (T0): если зависимость не смержена или в плане открытое юзер-решение — верни карточку на борде в статус Ready to IMPL (python3 .opencode/scripts/gh_board.py status $N \"Ready to IMPL\") и допиши в auto-impl log запись «BLOCKED <причина>»: python3 .opencode/scripts/gh_board.py auto-log $N \"BLOCKED <причина>\" (борд-операции и комментарии к issue — только через gh_board.py), и остановись, ничего не начиная. Блокеры по ходу работы — так же запись «BLOCKED …» в auto-impl log через gh_board.py auto-log; карточку в Ready to IMPL не возвращать. Блокер, который ждёт решения пользователя, ДОПОЛНИТЕЛЬНО отметь полем gate на борде: python3 .opencode/scripts/gh_board.py gate $N blocked (снял блокер и продолжил — gh_board.py gate $N none; уход карточки из In IMPL снимает автоматически). Зависимостные блокеры (мерж не случился) gate НЕ ставят — они снимаются сами. По завершении — штатный finishing: PR, борд In-main."
        # --attach: сессия создаётся на работающем сервере (:4096) — сразу видна в вебе
        nohup opencode run --attach "http://localhost:${OPENCODE_PORT:-4096}" --dir "$REPO" \
            --title "$TITLE" "$HANDOFF" > "$STATE/auto-impl-$N.log" 2>&1 &
    fi
    echo "$(date -Is) #$N launched (pid $!, session: ${SID:-new}, title: $TITLE, log: $STATE/auto-impl-$N.log)"
done

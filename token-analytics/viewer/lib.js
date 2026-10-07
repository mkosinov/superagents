// lib.js — чистые помощники просмотрщика: форматирование, сортировка,
// вкладки, дерево сверл-дауна, полосы агрегатов, диалог привязки.
// Никакого DOM и fetch — только данные → данные (тестируется под node);
// вся работа со страницей живёт в app.js. Метки — дословно из спеки §Viewer.
//
// Данные: /data/index.json, /data/issues/<project>-<N>.json,
// /data/unmatched.json — формы задаёт collector.write_snapshots.

"use strict";

// --- Контрактные строки (спека §Viewer) -------------------------------------

var UNMATCHED_TAB = "__unmatched__";          // id глобальной вкладки
var UNMATCHED_LABEL = "Несопоставленные";     // её подпись
var APPROX_LABEL = "≈ сумма по параллельным дочерним сессиям";
// «календарно: …» собирается в calendarLine()

// --- Числа и даты ------------------------------------------------------------

// Токены «по-человечески»: 12.4M / 830K / 999 (один знак после запятой,
// хвостовой «.0» убирается: 830K, а не 830.0K).
function trim1(value) {
  var s = value.toFixed(1);
  return s.endsWith(".0") ? s.slice(0, -2) : s;
}

function fmtTokens(n) {
  n = Math.max(0, Math.round(n || 0));
  if (n < 1000) { return String(n); }
  if (n < 1000000) { return trim1(n / 1000) + "K"; }
  return trim1(n / 1000000) + "M";
}

// Целые с группировкой пробелом: 48 240 000 (для 5 компонент токенов).
function fmtInt(n) {
  return String(Math.max(0, Math.round(n || 0)))
    .replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}

// Активное время модели: «1ч 24м», «45м», «30с»; при часах минуты
// дополняются нулём («1ч 02м»); ровные часы — без минут («2ч»).
function fmtDuration(ms) {
  ms = Math.max(0, Math.round(ms || 0));
  var sec = Math.floor(ms / 1000);
  if (sec < 60) { return sec + "с"; }
  var min = Math.floor(sec / 60);
  if (min < 60) { return min + "м"; }
  var h = Math.floor(min / 60);
  var m = min % 60;
  return m === 0 ? h + "ч" : h + "ч " + String(m).padStart(2, "0") + "м";
}

// Последняя активность: снапшот хранит UTC-дату «YYYY-MM-DD» — показываем
// локально в принятом порядке «DD.MM.YYYY»; пустое/битое → «—».
function fmtDate(iso) {
  if (typeof iso !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) {
    return "—";
  }
  var parts = iso.split("-");
  return parts[2] + "." + parts[1] + "." + parts[0];
}

// Русская плюрализация: 1 день / 2 дня / 5 дней / 21 день.
function pluralRu(n, one, few, many) {
  n = Math.abs(Math.round(n));
  var m10 = n % 10, m100 = n % 100;
  if (m10 === 1 && m100 !== 11) { return one; }
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) { return few; }
  return many;
}

// Вторичная строка фазы: «календарно: 3 дня», меньше суток — «календарно: 9 ч».
function calendarLine(cal) {
  if (!cal) { return ""; }
  if (cal.days !== null && cal.days !== undefined) {
    return "календарно: " + cal.days + " " +
      pluralRu(cal.days, "день", "дня", "дней");
  }
  var h = cal.hours || 0;
  var hs = (h % 1 !== 0) ? String(h) : String(Math.round(h));
  return "календарно: " + hs + " ч";
}

// --- Индекс: сортировка, вкладки ----------------------------------------------

// Таблица задач — по сумме токенов (убыв.), затем проект, затем номер —
// тот же порядок, что пишет collector; сортируем и на клиенте (защита).
function sortIssues(rows) {
  return (rows || []).slice().sort(function (a, b) {
    var at = (a.tokens || {}).total || 0;
    var bt = (b.tokens || {}).total || 0;
    if (at !== bt) { return bt - at; }
    if (a.project !== b.project) { return a.project < b.project ? -1 : 1; }
    return (a.issue || 0) - (b.issue || 0);
  });
}

// Вкладки: проекты с задачами в порядке «сильнейшей» задачи, затем
// сконфигурированные проекты без сопоставленных задач (index.projects —
// у такого таба явное пустое состояние), глобальная «Несопоставленные»
// последней.
function projectTabs(rows, projects) {
  var seen = [];
  sortIssues(rows).forEach(function (row) {
    if (seen.indexOf(row.project) === -1) { seen.push(row.project); }
  });
  var extra = (projects || []).filter(function (p) {
    return seen.indexOf(p) === -1;
  });
  return seen.concat(extra).map(function (p) {
    return { id: p, label: p, unmatched: false };
  }).concat([{ id: UNMATCHED_TAB, label: UNMATCHED_LABEL, unmatched: true }]);
}

function issueDataUrl(project, issue) {
  return "/data/issues/" + project + "-" + issue + ".json";
}

// --- Страница задачи: фазы, полосы ---------------------------------------------

// Фазы в каноническом порядке; ОТСУТСТВУЮЩАЯ фаза скрыта, а не занулена.
var PHASE_ORDER = [["design", "DESIGN"], ["impl", "IMPL"]];

function phaseRows(phases) {
  return PHASE_ORDER.filter(function (pair) {
    return phases && phases[pair[0]];
  }).map(function (pair) {
    return { key: pair[0], label: pair[1], phase: phases[pair[0]] };
  });
}

// by_model/by_agent → строки полос: ширина — доля от максимума (0…100).
function barsWidths(rows, keyField) {
  rows = rows || [];
  var max = 0;
  rows.forEach(function (r) { max = Math.max(max, r.tokens || 0); });
  return rows.map(function (r) {
    var pct = max > 0 ? ((r.tokens || 0) * 100) / max : 0;
    var label = r[keyField];
    return {
      label: (label !== null && label !== undefined) ? label : "—",
      tokens: r.tokens || 0,
      pct: Math.round(pct * 10) / 10,
    };
  });
}

// --- Дерево сверл-дауна --------------------------------------------------------

// Плоский список видимых узлов: дети рисуются только при раскрытом
// предке на ВСЕХ уровнях выше; ключ — путь индексов («0/1/2»), устойчив
// в пределах одного снапшота. Узел без детей — нераскрываемый лист.
function visibleNodes(roots, expanded) {
  var open = new Set(expanded || []);
  var out = [];
  function walk(nodes, prefix, depth) {
    (nodes || []).forEach(function (node, i) {
      var key = prefix + i;
      var children = node.children || [];
      var expandable = children.length > 0;
      out.push({ node: node, key: key, depth: depth, expandable: expandable });
      if (expandable && open.has(key)) {
        walk(children, key + "/", depth + 1);
      }
    });
  }
  walk(roots, "", 0);
  return out;
}

// Переключить раскрытость ключа; новый массив (иммутабельно — удобно и
// для тестов, и для перерисовки).
function toggleKey(keys, key) {
  var list = (keys || []).slice();
  var i = list.indexOf(key);
  if (i >= 0) { list.splice(i, 1); } else { list.push(key); }
  return list;
}

// Заголовок узла: пустой титул сессии → явная заглушка.
function nodeTitle(node) {
  return (node && node.title) ? node.title : "(без названия)";
}

// --- Диалог «Привязать» ---------------------------------------------------------

// Номер задачи из поля ввода: только положительное целое, иначе null
// (400 от сервера — не наш путь; валидируем до отправки).
function parseIssueNumber(value) {
  if (typeof value !== "string") { return null; }
  var s = value.trim();
  if (!/^\d+$/.test(s)) { return null; }
  var n = parseInt(s, 10);
  return n > 0 ? n : null;
}

// Проект в диалоге: атрибутируемый по каталогу — он; иначе первый известный.
function prefillProject(rowProject, knownProjects) {
  var known = knownProjects || [];
  if (known.indexOf(rowProject) !== -1) { return rowProject; }
  return known[0] || "";
}

// Экспорт для node-тестов; в браузере module не определён — no-op.
if (typeof module !== "undefined" && module.exports !== undefined) {
  module.exports = {
    UNMATCHED_TAB: UNMATCHED_TAB,
    UNMATCHED_LABEL: UNMATCHED_LABEL,
    APPROX_LABEL: APPROX_LABEL,
    fmtTokens: fmtTokens,
    fmtInt: fmtInt,
    fmtDuration: fmtDuration,
    fmtDate: fmtDate,
    pluralRu: pluralRu,
    calendarLine: calendarLine,
    sortIssues: sortIssues,
    projectTabs: projectTabs,
    issueDataUrl: issueDataUrl,
    phaseRows: phaseRows,
    barsWidths: barsWidths,
    visibleNodes: visibleNodes,
    toggleKey: toggleKey,
    nodeTitle: nodeTitle,
    parseIssueNumber: parseIssueNumber,
    prefillProject: prefillProject,
  };
}

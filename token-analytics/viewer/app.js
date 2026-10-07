// app.js — DOM-слой просмотрщика: вкладки, таблицы, страница задачи,
// дерево сверл-дауна, диалог «Привязать». Вся чистая логика — в lib.js
// (там же контрактные строки спеки); здесь только рендер и события.
// Данные — тот же источник: /data/index.json, /data/unmatched.json,
// /data/issues/<project>-<N>.json; привязка — POST /api/bind.

"use strict";

(function () {

  // --- ссылки на контрактные функции lib.js (классические скрипты) ------
  var L = {
    fmtTokens: fmtTokens,
    fmtInt: fmtInt,
    fmtDuration: fmtDuration,
    fmtDate: fmtDate,
    calendarLine: calendarLine,
    sortIssues: sortIssues,
    projectTabs: projectTabs,
    issueDataUrl: issueDataUrl,
    phaseRows: phaseRows,
    barsWidths: barsWidths,
    needsScrollHint: needsScrollHint,
    visibleNodes: visibleNodes,
    toggleKey: toggleKey,
    nodeTitle: nodeTitle,
    parseIssueNumber: parseIssueNumber,
    prefillProject: prefillProject,
    UNMATCHED_TAB: UNMATCHED_TAB,
    UNMATCHED_LABEL: UNMATCHED_LABEL,
    APPROX_LABEL: APPROX_LABEL,
  };

  var TOKEN_KINDS = ["input", "output", "reasoning", "cache_read", "cache_write"];

  var state = {
    index: null,        // index.json {issues, sources, projects?}
    unmatched: [],      // unmatched.json
    tab: null,          // проект | UNMATCHED_TAB
    issue: null,        // {project, issue, snapshot}
    expanded: [],       // раскрытые ключи дерева (пути индексов)
  };

  // --- мини-помощники DOM ------------------------------------------------

  function byId(id) { return document.getElementById(id); }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) { node.className = cls; }
    if (text !== undefined && text !== null) { node.textContent = text; }
    return node;
  }

  function clear(node) {
    while (node.firstChild) { node.removeChild(node.firstChild); }
  }

  function hide(id) { byId(id).hidden = true; }
  function show(id) { byId(id).hidden = false; }

  // Фейд-подсказка у правого края широкой таблицы — только когда контейнер
  // действительно прокручивается (ширина известна лишь у видимого узла,
  // поэтому вызывается после снятия hidden).
  function updateScrollHint(wrap) {
    wrap.classList.toggle("scrolls",
      L.needsScrollHint(wrap.scrollWidth, wrap.clientWidth));
  }

  // --- данные --------------------------------------------------------------

  function fetchJson(url) {
    return fetch(url).then(function (res) {
      if (!res.ok) { throw new Error(url + " → HTTP " + res.status); }
      return res.json();
    });
  }

  function loadData() {
    return Promise.all([
      fetchJson("/data/index.json"),
      fetchJson("/data/unmatched.json"),
    ]).then(function (results) {
      state.index = results[0] || {};
      state.index.issues = state.index.issues || [];
      state.unmatched = results[1] || [];
    });
  }

  function knownProjects() {
    var known = (state.index.projects || []).slice();
    state.index.issues.forEach(function (row) {
      if (known.indexOf(row.project) === -1) { known.push(row.project); }
    });
    return known;
  }

  // --- каркас: вкладки, виды, источники -------------------------------------

  function showView(name) {
    hide("load-error");
    ["view-project", "view-issue", "view-unmatched"].forEach(function (id) {
      byId(id).hidden = id !== "view-" + name;
    });
  }

  function renderSources() {
    var node = byId("sources");
    var sources = state.index.sources;
    if (!sources) { node.textContent = ""; return; }
    node.textContent = "host " + (sources.host ? "✓" : "✗")
      + " · контейнер " + (sources.container ? "✓" : "✗");
    node.classList.toggle("sources-bad",
      sources.host === false || sources.container === false);
  }

  function renderTabs() {
    var tabs = byId("tabs");
    clear(tabs);
    L.projectTabs(state.index.issues, state.index.projects).forEach(function (tab) {
      var btn = el("button", "tab" + (tab.unmatched ? " tab-unmatched" : ""),
                   tab.label);
      btn.type = "button";
      btn.setAttribute("role", "tab");
      btn.classList.toggle("active", state.tab === tab.id);
      btn.addEventListener("click", function () {
        state.tab = tab.id;
        state.issue = null;
        state.expanded = [];
        render();
      });
      tabs.appendChild(btn);
    });
  }

  // --- вид «проект»: таблица задач -------------------------------------------

  function phaseChip(phase, cls) {
    if (!phase) { return el("span", "chip chip-off", "—"); }
    return el("span", "chip " + cls, L.fmtTokens(phase.tokens.total));
  }

  function renderProject() {
    showView("project");
    byId("project-title").textContent = state.tab;
    var rows = L.sortIssues(state.index.issues).filter(function (row) {
      return row.project === state.tab;
    });

    var empty = byId("project-empty");
    var wrap = byId("project-table");
    clear(empty); clear(wrap);

    if (rows.length === 0) {
      // явное пустое состояние: проект сконфигурирован, задач нет
      empty.appendChild(el("p", null,
        "В проекте «" + state.tab + "» пока нет сопоставленных задач."));
      empty.appendChild(el("p", "empty-hint",
        "Обнови данные (collect) или привяжи сессии во вкладке «"
        + L.UNMATCHED_LABEL + "»."));
      wrap.hidden = true;
      empty.hidden = false;
      return;
    }

    var table = el("table", "table");
    var head = el("tr");
    ["Задача", "Токены", "Активное время", "Последняя активность",
     "design / IMPL"].forEach(function (title) {
      head.appendChild(el("th", null, title));
    });
    table.appendChild(el("thead")).appendChild(head);

    var tbody = el("tbody");
    rows.forEach(function (row) {
      var tr = el("tr", "row-link");
      tr.tabIndex = 0;

      var title = el("td", "cell-title");
      title.appendChild(el("span", "issue-no mono", "#" + row.issue));
      title.appendChild(el("span", "issue-name", row.title));

      var tokens = el("td", "cell-num mono", L.fmtTokens(row.tokens.total));
      tokens.title = L.fmtInt(row.tokens.total) + " токенов (сумма 5 компонент)";

      var active = el("td", "cell-num mono", L.fmtDuration(row.active_ms));
      var last = el("td", "cell-num mono", L.fmtDate(row.last_activity));

      var split = el("td", "cell-split");
      var splitWrap = el("span", "split");
      var designChip = phaseChip(row.phases && row.phases.design, "chip-design");
      designChip.title = "design";
      var implChip = phaseChip(row.phases && row.phases.impl, "chip-impl");
      implChip.title = "IMPL";
      splitWrap.appendChild(designChip);
      splitWrap.appendChild(implChip);
      split.appendChild(splitWrap);

      [title, tokens, active, last, split].forEach(function (td) {
        tr.appendChild(td);
      });

      function open() { openIssue(row.project, row.issue); }
      tr.addEventListener("click", open);
      tr.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          open();
        }
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);
    empty.hidden = true;
    wrap.hidden = false;
    updateScrollHint(wrap);
  }

  // --- вид «несопоставленные» --------------------------------------------------

  function renderUnmatched() {
    showView("unmatched");
    byId("unmatched-title").textContent = L.UNMATCHED_LABEL;
    var empty = byId("unmatched-empty");
    var wrap = byId("unmatched-table");
    clear(empty); clear(wrap);

    if (state.unmatched.length === 0) {
      empty.appendChild(el("p", null, "Несопоставленных сессий нет — всё привязано."));
      wrap.hidden = true;
      empty.hidden = false;
      return;
    }

    var table = el("table", "table");
    var head = el("tr");
    ["Дата", "Проект", "Сессия", "Токены", ""].forEach(function (title) {
      head.appendChild(el("th", null, title));
    });
    table.appendChild(el("thead")).appendChild(head);

    var tbody = el("tbody");
    state.unmatched.forEach(function (row) {
      var tr = el("tr");

      var date = el("td", "cell-num mono", L.fmtDate(row.date));
      var project = el("td", "cell-num mono", row.project);
      var session = el("td", "cell-title");
      session.appendChild(el("span", "issue-name", row.title || "(без названия)"));
      if (row.directory) {
        var dir = el("span", "dir mono", row.directory);
        session.appendChild(dir);
      }

      var tokens = el("td", "cell-num mono", L.fmtTokens(row.tokens));
      tokens.title = L.fmtInt(row.tokens) + " токенов по поддереву сессии";

      var action = el("td", "cell-action");
      var btn = el("button", "btn btn-small btn-primary", "Привязать");
      btn.type = "button";
      btn.addEventListener("click", function () {
        openBind(row.session_id, {
          project: L.prefillProject(row.project, knownProjects()),
          issue: null,
          phase: "design",
        }, (row.title || "(без названия)") + " · " + row.session_id);
      });
      action.appendChild(btn);

      [date, project, session, tokens, action].forEach(function (td) {
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);
    empty.hidden = true;
    wrap.hidden = false;
    updateScrollHint(wrap);
  }

  // --- вид «задача» ----------------------------------------------------------

  function openIssue(project, issue) {
    fetchJson(L.issueDataUrl(project, issue)).then(function (snapshot) {
      state.issue = { project: project, issue: issue, snapshot: snapshot };
      state.expanded = [];   // новое дерево — начинаем свёрнуто
      render();
    }).catch(function (err) {
      state.issue = null;
      render();
      var node = byId("load-error");
      clear(node);
      node.appendChild(el("p", null, "Не удалось открыть задачу "
        + project + " #" + issue + "."));
      node.appendChild(el("p", "empty-hint mono", String(err.message || err)));
      node.hidden = false;
    });
  }

  function componentsLine(tokens) {
    var parts = TOKEN_KINDS.map(function (kind) {
      return kind + " " + L.fmtInt(tokens[kind]);
    });
    parts.push("всего " + L.fmtInt(tokens.total));
    return parts.join(" · ");
  }

  function renderBars(container, rows, keyField, accent) {
    L.barsWidths(rows, keyField).forEach(function (bar) {
      var line = el("div", "bar-row");
      var label = el("span", "bar-label mono", bar.label);
      label.title = L.fmtInt(bar.tokens) + " токенов";
      var track = el("div", "bar-track");
      var fill = el("div", "bar-fill " + accent);
      fill.style.width = bar.pct + "%";
      track.appendChild(fill);
      var value = el("span", "bar-value mono", L.fmtTokens(bar.tokens));
      value.title = L.fmtInt(bar.tokens) + " токенов";
      line.appendChild(label);
      line.appendChild(track);
      line.appendChild(value);
      container.appendChild(line);
    });
  }

  function barsBlock(title, rows, keyField, accent) {
    var block = el("div", "bars");
    block.appendChild(el("h4", "bars-title", title));
    renderBars(block, rows, keyField, accent);
    return block;
  }

  function anyApprox(nodes) {
    return nodes.some(function isApprox(node) {
      return node.approx || (node.children || []).some(isApprox);
    });
  }

  function renderTree(container, phase, phaseKey) {
    var heading = el("h4", "tree-title", "Дерево сессий");
    container.appendChild(heading);
    if (anyApprox(phase.tree)) {
      // контейнерное время — приближение; подпись из спеки §Viewer
      container.appendChild(el("p", "approx-note", "≈ " + L.APPROX_LABEL));
    }

    var rows = L.visibleNodes(phase.tree, state.expanded);
    if (rows.length === 0) { return; }

    var list = el("div", "tree");
    rows.forEach(function (row) {
      var node = row.node;
      var line = el("div", "tree-row");
      line.style.paddingLeft = row.depth * 20 + "px";

      var expander = el("span", "tree-expander mono",
                        row.expandable ? (state.expanded.indexOf(row.key) >= 0 ? "▾" : "▸") : "·");
      if (row.expandable) {
        var btn = el("button", "tree-toggle");
        btn.type = "button";
        btn.title = state.expanded.indexOf(row.key) >= 0 ? "Свернуть" : "Раскрыть";
        btn.appendChild(expander);
        btn.addEventListener("click", function () {
          state.expanded = L.toggleKey(state.expanded, row.key);
          renderIssueBody();
        });
        line.appendChild(btn);
      } else {
        line.appendChild(expander);
      }

      var name = el("span", "tree-name", L.nodeTitle(node));
      line.appendChild(name);
      if (node.agent) {
        line.appendChild(el("span", "tree-agent mono", node.agent));
      }

      var tokens = el("span", "cell-num mono tree-tokens",
                      L.fmtTokens(node.tokens.total));
      tokens.title = componentsLine(node.tokens);
      line.appendChild(tokens);

      // контейнерное время помечается «≈» (полная подпись — над деревом)
      var timeText = (node.approx ? "≈ " : "") + L.fmtDuration(node.active_ms);
      var time = el("span", "cell-num mono tree-time", timeText);
      if (node.approx) { time.title = L.APPROX_LABEL; }
      line.appendChild(time);

      // перепривязка ошибочно сопоставленной сессии — с узла дерева
      if (node.session_id) {
        var bind = el("button", "btn btn-small tree-bind", "Привязать");
        bind.type = "button";
        bind.title = "Перепривязать сессию " + node.session_id;
        bind.addEventListener("click", function () {
          openBind(node.session_id, {
            project: state.issue.project,
            issue: state.issue.issue,
            phase: phaseKey,
          }, L.nodeTitle(node) + " · " + node.session_id);
        });
        line.appendChild(bind);
      }

      list.appendChild(line);
    });
    container.appendChild(list);
  }

  function renderPhaseCard(phaseKey, label, phase) {
    var card = el("section", "phase-card phase-" + phaseKey);

    var head = el("div", "phase-head");
    head.appendChild(el("span", "phase-label mono", label));
    var metrics = el("span", "phase-metrics mono");
    var total = el("span", "phase-total", L.fmtTokens(phase.tokens.total));
    total.title = L.fmtInt(phase.tokens.total) + " токенов";
    metrics.appendChild(total);
    metrics.appendChild(el("span", "phase-sep", "·"));
    metrics.appendChild(el("span", null, L.fmtDuration(phase.active_ms)));
    head.appendChild(metrics);
    card.appendChild(head);

    // вторичная строка: календарный размах фазы
    card.appendChild(el("p", "phase-calendar", L.calendarLine(phase.calendar)));

    card.appendChild(el("p", "phase-components mono", componentsLine(phase.tokens)));

    var barsGrid = el("div", "bars-grid");
    barsGrid.appendChild(barsBlock("по моделям", phase.by_model, "model", "bar-model"));
    barsGrid.appendChild(barsBlock("по агентам", phase.by_agent, "agent", "bar-agent"));
    card.appendChild(barsGrid);

    renderTree(card, phase, phaseKey);
    return card;
  }

  function renderIssueBody() {
    var snap = state.issue.snapshot;
    var body = byId("issue-body");
    clear(body);

    var title = el("h2", "view-title");
    title.appendChild(el("span", "issue-no mono", "#" + snap.issue + " "));
    title.appendChild(el("span", null, snap.title));
    body.appendChild(title);

    var summary = el("p", "issue-summary mono");
    var sumTokens = el("span", "phase-total", L.fmtTokens(snap.tokens.total));
    sumTokens.title = componentsLine(snap.tokens);
    summary.appendChild(sumTokens);
    summary.appendChild(el("span", "phase-sep", "·"));
    summary.appendChild(el("span", null, L.fmtDuration(snap.active_ms)));
    summary.appendChild(el("span", "phase-sep", "·"));
    summary.appendChild(el("span", null,
      "активность до " + L.fmtDate(snap.last_activity)));
    summary.appendChild(el("span", "phase-sep", "·"));
    summary.appendChild(el("span", null, componentsLine(snap.tokens)));
    body.appendChild(summary);

    // агрегаты по всей задаче (фазовые — внутри каждой карточки)
    var issueBars = el("div", "bars-grid bars-grid-issue");
    issueBars.appendChild(barsBlock("по моделям — вся задача",
                                    snap.by_model, "model", "bar-model"));
    issueBars.appendChild(barsBlock("по агентам — вся задача",
                                    snap.by_agent, "agent", "bar-agent"));
    body.appendChild(issueBars);

    // отсутствующая фаза скрыта, а не занулена (lib.phaseRows)
    L.phaseRows(snap.phases).forEach(function (row) {
      body.appendChild(renderPhaseCard(row.key, row.label, row.phase));
    });
  }

  function renderIssue() {
    showView("issue");
    renderIssueBody();
  }

  // --- диалог «Привязать» ------------------------------------------------------

  var bindDialog = byId("bind-dialog");
  var bindState = { sessionId: null };

  function showBindMessage(text) {
    var node = byId("bind-message");
    node.textContent = text;
    node.hidden = false;
  }

  function openBind(sessionId, prefill, hintText) {
    bindState.sessionId = sessionId;

    var known = knownProjects();
    var projectSelect = byId("bind-project");
    clear(projectSelect);
    if (known.length === 0) {
      // нет ни одного известного проекта — нечем предзаполнить выбор
      projectSelect.appendChild(el("option", null, "(нет проектов)"));
    } else {
      known.forEach(function (project) {
        var option = el("option", null, project);
        option.value = project;
        projectSelect.appendChild(option);
      });
    }
    var wanted = prefill.project || (known[0] || "");
    projectSelect.value = wanted;

    byId("bind-issue").value = prefill.issue !== null && prefill.issue !== undefined
      ? String(prefill.issue) : "";
    byId("bind-phase").value = prefill.phase || "design";
    byId("bind-hint").textContent = hintText || "";
    byId("bind-message").hidden = true;
    byId("bind-submit").disabled = false;
    bindDialog.showModal();
  }

  function submitBind(event) {
    event.preventDefault();
    var issue = L.parseIssueNumber(byId("bind-issue").value);
    if (issue === null) {
      showBindMessage("Номер задачи — целое число больше нуля.");
      return;
    }
    var project = byId("bind-project").value;
    if (!project) {
      showBindMessage("Выбери проект.");
      return;
    }
    var payload = {
      session_id: bindState.sessionId,
      project: project,
      issue: issue,
      phase: byId("bind-phase").value,
    };
    byId("bind-submit").disabled = true;
    byId("bind-message").hidden = true;

    fetch("/api/bind", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then(function (res) {
      if (res.ok) { return null; }
      // сервер отклонил: 400 валидация, 503 идёт сбор — покажем причину
      return res.json().catch(function () { return null; }).then(function (data) {
        var detail = data && data.error ? ": " + data.error : "";
        throw new Error("Сервер отклонил привязку (HTTP " + res.status + ")" + detail);
      });
    }).then(function () {
      bindDialog.close();
      // привязано: обновляем данные и открываем задачу-приёмник
      return loadData().then(function () {
        state.tab = project;
        state.expanded = [];
        openIssue(project, issue);
        renderTabs();
      });
    }).catch(function (err) {
      // сервер не запущен / сеть / отклонение — plainly, без падения
      showBindMessage("Не привязано — " + String(err.message || err)
        + ". Сервер (collect serve) должен быть запущен.");
      byId("bind-submit").disabled = false;
    });
  }

  // --- каркас и запуск -----------------------------------------------------------

  function render() {
    renderTabs();
    renderSources();
    if (state.issue) {
      renderIssue();
    } else if (state.tab === L.UNMATCHED_TAB) {
      renderUnmatched();
    } else if (state.tab) {
      renderProject();
    } else {
      showView("project");
      byId("project-title").textContent = "";
      byId("project-empty").hidden = true;
      byId("project-table").hidden = true;
    }
  }

  byId("issue-back").addEventListener("click", function () {
    state.issue = null;
    render();
  });
  byId("bind-cancel").addEventListener("click", function () {
    bindDialog.close();
  });
  byId("bind-form").addEventListener("submit", submitBind);

  loadData().then(function () {
    var tabs = L.projectTabs(state.index.issues, state.index.projects);
    state.tab = tabs.length > 0 ? tabs[0].id : L.UNMATCHED_TAB;
    render();
  }).catch(function (err) {
    var node = byId("load-error");
    clear(node);
    node.appendChild(el("p", null,
      "Данные не загрузились — нужен собранный снимок и сервер (collect serve)."));
    node.appendChild(el("p", "empty-hint mono", String(err.message || err)));
    node.hidden = false;
  });

})();

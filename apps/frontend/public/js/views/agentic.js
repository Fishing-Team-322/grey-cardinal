import { api } from "../api.js";
import { bindForm, currentTeam, errorMessage, escapeHtml, formatDate, setTopbar, toast } from "../view-utils.js";

const BOARD_VIEWS = [
  ["agent", "Agent View"],
  ["status", "Status View"],
  ["people", "People View"],
  ["risk", "Risk View"],
  ["timeline", "Timeline View"],
  ["source", "Source View"],
];

function managedTeam(params = {}) {
  const teams = window.gcCurrentUser.teams || [];
  return teams.find((team) => team.id === (params.id || params.teamId)) || currentTeam({ teams });
}

function setHeader(root, title, desc, actions = "") {
  root.querySelector("#agentic-title").textContent = title;
  root.querySelector("#agentic-desc").textContent = desc;
  setTopbar(title, actions);
}

export async function greyBoardView(root, params, query) {
  const team = managedTeam(params);
  if (!team) return empty(root, "Команда не найдена");
  const view = query.view || "agent";
  setHeader(root, "Grey Board", "Живая доска задач, источников, рисков и действий агента.", `<a class="btn btn-ghost" href="/app/teams/${team.id}/ai-inbox">AI Inbox</a><a class="btn btn-primary" href="/app/teams/${team.id}/yougile">YouGile</a>`);
  await renderBoard(root, team.id, view);
}

async function renderBoard(root, teamId, view) {
  const content = root.querySelector("#agentic-content");
  content.innerHTML = '<div class="view-loading">Загрузка Grey Board...</div>';
  const data = await api.greyBoard.get(teamId, view);
  content.innerHTML = `
    <div class="grey-cockpit">
      <aside class="board-switcher">${BOARD_VIEWS.map(([key, label]) => `<a class="${key === view ? "active" : ""}" href="/app/teams/${teamId}/board?view=${key}">${label}</a>`).join("")}</aside>
      <section class="board-main">
        ${healthBar(data.health)}
        <div class="agent-board">${data.groups.map(groupHtml).join("")}</div>
      </section>
      <aside class="agent-rail">
        <div class="rail-title">Agent Recommendations</div>
        ${(data.recommendations || []).map(recommendationHtml).join("") || '<div class="dim">Критичных рекомендаций нет.</div>'}
      </aside>
    </div>`;
  content.querySelectorAll("[data-task-action]").forEach((button) => {
    button.onclick = async () => {
      await api.greyBoard.action(button.dataset.taskId, { action: button.dataset.taskAction });
      toast("Задача обновлена");
      await renderBoard(root, teamId, view);
    };
  });
}

function healthBar(health) {
  return `<div class="healthbar">
    ${healthPill("LLM", health.llm === "configured")}
    ${healthPill("Telegram", health.telegram === "linked")}
    ${healthPill("YouGile", health.yougile === "synced")}
    <span class="pill ${health.open_risks ? "warn" : "ok"}"><span class="dot"></span>${health.open_risks || 0} risks</span>
    <span class="pill idle">last sync: ${escapeHtml(health.last_sync || "never")}</span>
  </div>`;
}

function healthPill(label, ok) {
  return `<span class="pill ${ok ? "ok" : "warn"}"><span class="dot"></span>${label} ${ok ? "OK" : "setup"}</span>`;
}

function groupHtml(group) {
  return `<div class="agent-col">
    <div class="agent-col-head"><b>${escapeHtml(group.title)}</b><span class="mono">${group.count ?? group.cards.length}</span></div>
    <div class="col gap-10">${group.cards.map(cardHtml).join("") || '<span class="faint">Пусто</span>'}</div>
  </div>`;
}

function cardHtml(card) {
  return `<article class="task-evidence-card">
    <div class="flex between gap-8"><b>${escapeHtml(card.public_id)} ${escapeHtml(card.title)}</b><span class="pill ${card.yougile.sync_status === "conflict" ? "err" : "info"}">${escapeHtml(card.yougile.sync_status)}</span></div>
    <div class="task-meta">${escapeHtml(card.assignee_name || card.assignee_text || "Без исполнителя")} · ${escapeHtml(card.priority)} · ${card.deadline ? formatDate(card.deadline) : "без дедлайна"}</div>
    <div class="evidence-line"><span>Источник</span><b>${escapeHtml(card.source.type)}</b><span>Confidence</span><b>${Math.round((card.confidence || 0) * 100)}%</b></div>
    ${card.signals.length ? `<div class="signal-list">${card.signals.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>` : ""}
    <details class="mt-8"><summary>Доказательства агента</summary>
      <div class="source-text">${escapeHtml(card.source.text || card.description || "Источник не сохранен")}</div>
      <div class="agent-log">${card.agent_history.map((item) => `<div><span>${escapeHtml(item.at || "")}</span>${escapeHtml(item.text)}</div>`).join("")}</div>
      <div class="code-msg mt-8">YouGile: ${escapeHtml(card.yougile.external_task_id || "not linked")} · ${escapeHtml(card.yougile.last_sync || "no sync")}</div>
    </details>
    <div class="card-actions">
      ${actionBtn(card, "start", "В работу")}
      ${actionBtn(card, "done", "Готово")}
      ${actionBtn(card, "blocked", "Блок")}
      ${actionBtn(card, "review", "Review")}
      ${card.yougile.external_url ? `<a class="btn btn-sm btn-ghost" target="_blank" href="${escapeHtml(card.yougile.external_url)}">YouGile</a>` : ""}
    </div>
  </article>`;
}

function actionBtn(card, action, label) {
  return `<button class="btn btn-sm btn-ghost" data-task-id="${card.id}" data-task-action="${action}">${label}</button>`;
}

function recommendationHtml(item) {
  return `<div class="recommendation ${item.severity}">
    <div class="flex between gap-8"><b>${escapeHtml(item.title)}</b><span>${escapeHtml(item.severity)}</span></div>
    <p>${escapeHtml(item.message)}</p>
    <button class="btn btn-sm btn-ghost" type="button">Открыть</button>
  </div>`;
}

export async function aiInboxView(root, params) {
  const team = managedTeam(params);
  if (!team) return empty(root, "Команда не найдена");
  setHeader(root, "AI Inbox", "Human-in-the-loop входящие: предложения задач, конфликты, дубли и низкая уверенность.");
  const content = root.querySelector("#agentic-content");
  const data = await api.aiInbox.list(team.id);
  content.innerHTML = `<div class="inbox-list">${data.items.map(inboxItem).join("") || '<div class="note warn">AI Inbox пуст.</div>'}</div>`;
  content.querySelectorAll("[data-inbox]").forEach((button) => {
    button.onclick = async () => {
      const fn = button.dataset.inboxAction === "approve" ? api.aiInbox.approve : api.aiInbox.reject;
      await fn(button.dataset.inbox);
      toast("AI Inbox обновлен");
      await aiInboxView(root, params);
    };
  });
}

function inboxItem(item) {
  return `<article class="card card-pad">
    <div class="card-head"><div><div class="eyebrow">${escapeHtml(item.type)}</div><div class="card-title mt-6">${escapeHtml(item.proposed_action || "Нужно решение")}</div></div><span class="pill info">${Math.round(item.confidence * 100)}%</span></div>
    <div class="source-text">${escapeHtml(item.source_text)}</div>
    <pre class="json-box">${escapeHtml(JSON.stringify(item.parsed_payload || {}, null, 2))}</pre>
    <div class="flex gap-8 mt-12"><button class="btn btn-primary" data-inbox="${item.id}" data-inbox-action="approve">Принять</button><button class="btn btn-ghost" data-inbox="${item.id}" data-inbox-action="reject">Отклонить</button></div>
  </article>`;
}

export async function setupView(root, params) {
  const team = managedTeam(params);
  if (!team) return empty(root, "Команда не найдена");
  setHeader(root, "Setup Wizard", "Мастер внедрения: компания, команда, Telegram, YouGile, LLM и тестовый сценарий.", `<button class="btn btn-primary" id="run-demo">Запустить demo</button>`);
  const data = await api.setup.status(team.id);
  root.querySelector("#agentic-content").innerHTML = `<div class="setup-steps">${data.steps.map(step => `<div class="check-item ${step.status === "done" ? "done" : step.status === "warning" ? "active" : ""}"><div class="check-box">✓</div><div><div class="check-title">${escapeHtml(step.title)}</div><div class="check-desc">${escapeHtml(step.status)}</div></div></div>`).join("")}</div>`;
  document.getElementById("run-demo").onclick = async () => {
    await api.setup.runDemo(team.id);
    toast("Demo создано");
    await setupView(root, params);
  };
}

export async function yougileFullView(root, params) {
  const team = managedTeam(params);
  if (!team) return empty(root, "Команда не найдена");
  setHeader(root, "YouGile Full Sync", "Подключение, выбор реальной доски, mapping колонок, импорт и manual sync.");
  const content = root.querySelector("#agentic-content");
  const status = await api.yougile.statusFull(team.id).catch(() => ({ connected: false }));
  if (!status.connected) {
    content.innerHTML = `<div class="card card-pad-lg"><h2>Подключить YouGile</h2><form id="yg-full" class="grid g2 mt-20"><label>Login<input class="input mt-6" name="login"></label><label>Password<input class="input mt-6" name="password" type="password"></label><label>Company ID<input class="input mt-6" name="company_id"></label><label>API key<input class="input mt-6" name="api_key"></label><button class="btn btn-primary" type="submit">Проверить и подключить</button></form></div>`;
    bindForm(content, "#yg-full", async (data) => {
      await api.yougile.connectFull(team.id, Object.fromEntries(data.entries()));
      toast("YouGile подключен");
      await yougileFullView(root, params);
    });
    return;
  }
  const [boards, events] = await Promise.all([api.yougile.boardsFull(team.id), api.yougile.syncEvents(team.id).catch(() => ({ items: [] }))]);
  content.innerHTML = `<div class="grid g4">
    ${stat("Досок", status.stats.boards || 0)}${stat("Колонок", status.stats.columns || 0)}${stat("Связанных задач", status.stats.tasks || 0)}${stat("Статус", status.status || "active")}
  </div>
  <div class="grid g2 mt-20">
    <div class="card card-pad"><div class="card-head"><div class="card-title">Реальные YouGile boards</div><button class="btn btn-sm btn-primary" id="import-board">Импортировать</button></div>
      <div class="col gap-8">${boards.items.map(board => `<button class="board-row ${board.is_selected ? "selected" : ""}" data-board="${board.id}"><b>${escapeHtml(board.name)}</b><span>${escapeHtml(board.external_id)}</span></button>`).join("") || '<div class="dim">Доски еще не загружены.</div>'}</div>
    </div>
    <div class="card card-pad"><div class="card-head"><div class="card-title">Sync events</div><button class="btn btn-sm btn-ghost" id="sync-now">Sync</button></div>
      <div class="event-list">${events.items.slice(0, 12).map(event => `<div><b>${escapeHtml(event.status)}</b> ${escapeHtml(event.entity_type)} <span>${escapeHtml(event.message || "")}</span></div>`).join("") || '<div class="dim">Событий нет.</div>'}</div>
    </div>
  </div>`;
  content.querySelectorAll("[data-board]").forEach((button) => {
    button.onclick = async () => {
      await api.yougile.selectBoard(team.id, button.dataset.board, null);
      toast("Доска выбрана");
      await yougileFullView(root, params);
    };
  });
  content.querySelector("#import-board").onclick = async () => {
    const result = await api.yougile.importBoard(team.id);
    toast(`Импорт: ${result.imported_tasks} новых, ${result.updated_tasks} обновлено`);
    await yougileFullView(root, params);
  };
  content.querySelector("#sync-now").onclick = async () => {
    await api.yougile.syncFull(team.id);
    toast("Manual sync выполнен");
    await yougileFullView(root, params);
  };
}

export async function teamMapView(root, params) {
  const companyId = params.companyId || params.id;
  setHeader(root, "Team Map", "Операционная карта команд, рисков и sync health.");
  const data = await api.companies.map(companyId);
  root.querySelector("#agentic-content").innerHTML = `<div class="org-map"><div class="org-root">${escapeHtml(data.company.name)}</div>${data.teams.map(team => `<a href="/app/teams/${team.id}/board" class="org-team ${team.status}"><b>${escapeHtml(team.name)}</b><span>Open ${team.open_tasks}</span><span>Risks ${team.risks}</span><span>${escapeHtml(team.sync_health)}</span></a>`).join("")}</div>`;
}

export async function recommendationsView(root, params) {
  const team = managedTeam(params);
  if (!team) return empty(root, "Команда не найдена");
  setHeader(root, "Agent Recommendations", "Следующие действия руководителя.");
  const data = await api.recommendations.team(team.id);
  root.querySelector("#agentic-content").innerHTML = `<div class="grid g2">${data.items.map(recommendationHtml).join("") || '<div class="note warn">Рекомендаций нет.</div>'}</div>`;
}

export async function peopleView(root, params) {
  const team = managedTeam(params);
  if (!team) return empty(root, "Команда не найдена");
  setHeader(root, "People", "Сотрудники, нагрузка, отсутствие, достижения.");
  const data = await api.people.team(team.id);
  root.querySelector("#agentic-content").innerHTML = `<div class="grid g3">${data.items.map(personCard).join("")}</div>`;
}

export async function profileView(root, params) {
  const mine = location.pathname === "/app/me";
  setHeader(root, mine ? "Мой профиль" : "Employee Profile", "Задачи, digest, активность, достижения и Telegram linking.");
  const data = mine ? await api.people.me() : await api.people.profile(params.userId);
  root.querySelector("#agentic-content").innerHTML = profileHtml(data);
}

export async function telegramTopicsView(root, params) {
  const team = managedTeam(params);
  if (!team) return empty(root, "Команда не найдена");
  setHeader(root, "Telegram Topics", "Привязка Telegram topics к team/board/source stream.");
  const data = await api.topics.list(team.id);
  root.querySelector("#agentic-content").innerHTML = `<div class="card card-pad"><table class="tbl"><thead><tr><th>Chat</th><th>Thread</th><th>Source</th><th>Status</th></tr></thead><tbody>${data.items.map(item => `<tr><td>${escapeHtml(item.chat_title || item.telegram_chat_id)}</td><td class="mono">${item.message_thread_id}</td><td>${escapeHtml(item.source_name || "Telegram topic")}</td><td><span class="pill ${item.bound ? "ok" : "warn"}">${item.bound ? "bound" : "new"}</span></td></tr>`).join("") || '<tr><td colspan="4">Темы появятся после сообщений из Telegram topics.</td></tr>'}</tbody></table></div>`;
}

function personCard(item) {
  const p = item.profile;
  return `<a class="card card-pad" href="/app/people/${item.id}"><div class="card-title">${escapeHtml(item.display_name)}</div><div class="dim">${escapeHtml(item.role)}</div><div class="grid g2 mt-16">${stat("Open", p.stats.open_tasks)}${stat("Overdue", p.stats.overdue)}${stat("XP", p.stats.xp)}${stat("Absence", p.absence.active ? "yes" : "no")}</div></a>`;
}

function profileHtml(data) {
  return `<div class="grid g2">
    <div class="card card-pad"><h2>${escapeHtml(data.user.display_name)}</h2><p class="dim">${escapeHtml(data.user.email || "")}</p><div class="grid g4 mt-20">${stat("Open", data.stats.open_tasks)}${stat("Overdue", data.stats.overdue)}${stat("Closed/week", data.stats.closed_week)}${stat("XP", data.stats.xp)}</div><div class="note mt-20">${escapeHtml(data.digest)}</div></div>
    <div class="card card-pad"><div class="card-title">Achievements</div><div class="grid g2 mt-16">${data.achievements.map(a => `<div class="ach ${a.earned ? "" : "locked"}"><div class="ico">${a.earned ? "✓" : "·"}</div><div class="ach-name">${escapeHtml(a.name)}</div></div>`).join("")}</div></div>
  </div><div class="card card-pad mt-20"><div class="card-title">Tasks</div><table class="tbl mt-12"><tbody>${data.tasks.map(task => `<tr><td>${escapeHtml(task.public_id)}</td><td>${escapeHtml(task.title)}</td><td>${escapeHtml(task.status)}</td><td>${task.deadline ? formatDate(task.deadline) : ""}</td></tr>`).join("")}</tbody></table></div>`;
}

function stat(label, value) {
  return `<div class="stat"><div class="stat-label">${escapeHtml(label)}</div><div class="stat-value mono">${escapeHtml(String(value))}</div></div>`;
}

function empty(root, text) {
  root.querySelector("#agentic-content").innerHTML = `<div class="note warn">${escapeHtml(text)}</div>`;
}

export default greyBoardView;

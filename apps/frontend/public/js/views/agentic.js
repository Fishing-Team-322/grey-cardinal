import { api } from "../api.js";
import { bindForm, currentTeam, errorMessage, escapeHtml, formatDate, setTopbar, toast } from "../view-utils.js";

const BOARD_VIEWS = [
  ["agent", "Ассистент"],
  ["status", "Статусы"],
  ["people", "Люди"],
  ["risk", "Риски"],
  ["timeline", "Сроки"],
  ["source", "Источник"],
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
  setHeader(root, "Grey Board", "Живая доска задач, источников, рисков и действий ассистента.", `<a class="btn btn-ghost" href="/app/teams/${team.id}/ai-inbox">Входящие AI</a><a class="btn btn-primary" href="/app/teams/${team.id}/yougile">YouGile</a>`);
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
        <div class="agent-board">${(data.groups || data.columns || []).map(groupHtml).join("")}</div>
      </section>
      <aside class="agent-rail">
        <div class="rail-title">Рекомендации ассистента</div>
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
    <span class="pill ${health.open_risks ? "warn" : "ok"}"><span class="dot"></span>${health.open_risks || 0} рисков</span>
    <span class="pill idle">последняя синхронизация: ${escapeHtml(health.last_sync || "не было")}</span>
  </div>`;
}

function healthPill(label, ok) {
  return `<span class="pill ${ok ? "ok" : "warn"}"><span class="dot"></span>${label} ${ok ? "готово" : "настроить"}</span>`;
}

function groupHtml(group) {
  const cards = group.cards || group.tasks || [];
  return `<div class="agent-col">
    <div class="agent-col-head"><b>${escapeHtml(group.title)}</b><span class="mono">${group.count ?? cards.length}</span></div>
    <div class="col gap-10">${cards.map(cardHtml).join("") || '<span class="faint">Пусто</span>'}</div>
  </div>`;
}

function cardHtml(card) {
  return `<article class="task-evidence-card">
    <div class="flex between gap-8"><b>${escapeHtml(card.public_id)} ${escapeHtml(card.title)}</b><span class="pill ${card.yougile.sync_status === "conflict" ? "err" : "info"}">${escapeHtml(card.yougile.sync_status)}</span></div>
    <div class="task-meta">${escapeHtml(card.assignee_name || card.assignee_text || "Без исполнителя")} · ${escapeHtml(card.priority)} · ${card.deadline ? formatDate(card.deadline) : "без дедлайна"}</div>
    <div class="evidence-line"><span>Источник</span><b>${escapeHtml(sourceLabel(card.source.type))}</b><span>Уверенность</span><b>${Math.round((card.confidence || 0) * 100)}%</b></div>
    ${card.signals.length ? `<div class="signal-list">${card.signals.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>` : ""}
    <details class="mt-8"><summary>Доказательства агента</summary>
      <div class="source-text">${escapeHtml(card.source.text || card.description || "Источник не сохранен")}</div>
      <div class="agent-log">${card.agent_history.map((item) => `<div><span>${escapeHtml(item.at || "")}</span>${escapeHtml(item.text)}</div>`).join("")}</div>
      <div class="code-msg mt-8">YouGile: ${escapeHtml(card.yougile.external_task_id || "не связано")} · ${escapeHtml(card.yougile.last_sync || "синхронизации не было")}</div>
    </details>
    <div class="card-actions">
      ${actionBtn(card, "start", "В работу")}
      ${actionBtn(card, "done", "Готово")}
      ${actionBtn(card, "blocked", "Блок")}
      ${actionBtn(card, "review", "На проверку")}
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
  setHeader(root, "Входящие AI", "Входящие решения: предложения задач, конфликты, дубли и низкая уверенность.");
  const content = root.querySelector("#agentic-content");
  const data = await api.aiInbox.list(team.id);
  content.innerHTML = `<div class="inbox-list">${data.items.map(inboxItem).join("") || '<div class="note warn">Входящие AI пусты.</div>'}</div>`;
  content.querySelectorAll("[data-inbox]").forEach((button) => {
    button.onclick = async () => {
      const fn = button.dataset.inboxAction === "approve" ? api.aiInbox.approve : api.aiInbox.reject;
      await fn(button.dataset.inbox);
      toast("Входящие AI обновлены");
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
  setHeader(root, "Мастер настройки", "Мастер внедрения: компания, команда, Telegram, YouGile, LLM и тестовый сценарий.", `<button class="btn btn-primary" id="run-demo">Запустить демо</button>`);
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
  setHeader(root, "Синхронизация YouGile", "Подключение, выбор реальной доски, сопоставление колонок, импорт и ручная синхронизация.");
  const content = root.querySelector("#agentic-content");
  const status = await api.yougile.statusFull(team.id).catch(() => ({ connected: false }));
  if (!status.connected) {
    content.innerHTML = `<div class="card card-pad-lg"><h2>Подключить YouGile</h2><form id="yg-full" class="grid g2 mt-20"><label>Логин<input class="input mt-6" name="login"></label><label>Пароль<input class="input mt-6" name="password" type="password"></label><label>ID компании<input class="input mt-6" name="company_id"></label><label>API-ключ<input class="input mt-6" name="api_key"></label><button class="btn btn-primary" type="submit">Проверить и подключить</button></form></div>`;
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
    toast("Ручная синхронизация выполнена");
    await yougileFullView(root, params);
  };
}

export async function teamMapView(root, params) {
  const companyId = params.companyId || params.id;
  setHeader(root, "Карта взаимодействий", "Проекты показывают, где команды реально работают вместе и где возникают блокировки.");
  const data = await api.companies.map(companyId);
  const teamNames = new Map((data.teams || []).map((team) => [team.id, team.name]));
  root.querySelector("#agentic-content").innerHTML = `
    <div class="collab-kpis">
      <div><b>${data.stats?.active_projects || 0}</b><span>активных проектов</span></div>
      <div><b>${data.stats?.participating_teams || 0}</b><span>команд в проектах</span></div>
      <div><b>${data.stats?.collaboration_links || 0}</b><span>рабочих связей</span></div>
    </div>
    <section class="collab-map">
      <div class="collab-company">${escapeHtml(data.company.name)}</div>
      <div class="collab-projects">
        ${(data.projects || []).map((project) => `
          <a class="collab-project" href="/app/projects/${project.id}">
            <div class="project-code">${escapeHtml(project.code)}</div>
            <h3>${escapeHtml(project.name)}</h3>
            <div class="collab-progress"><i style="width:${project.progress || 0}%"></i></div>
            <small>${project.progress || 0}% · ${project.done || 0}/${project.tasks || 0} задач</small>
            <div class="collab-team-chips">${project.teams.map((team) => `<span class="${team.role === "lead" ? "lead" : ""}">${escapeHtml(team.name)}</span>`).join("")}</div>
          </a>`).join("") || '<div class="project-empty">Активных межкомандных проектов пока нет.</div>'}
      </div>
    </section>
    <div class="grid g2 mt-20">
      <section class="card card-pad">
        <div class="card-head"><div class="card-title">Команды</div><span class="card-sub">нагрузка и риски</span></div>
        <div class="collab-team-list">${(data.teams || []).map((team) => `<a href="/app/teams/${team.id}/board" class="collab-team-row ${team.status}"><span class="status-dot"></span><b>${escapeHtml(team.name)}</b><small>${team.open_tasks} открыто · ${team.risks} рисков</small></a>`).join("")}</div>
      </section>
      <section class="card card-pad">
        <div class="card-head"><div class="card-title">Связи между командами</div><span class="card-sub">по совместной работе</span></div>
        <div class="collab-edge-list">${(data.edges || []).sort((a, b) => b.collaboration_points - a.collaboration_points).map((edge) => `<div class="collab-edge"><div><b>${escapeHtml(teamNames.get(edge.source_team_id) || "Команда")}</b><span>↔</span><b>${escapeHtml(teamNames.get(edge.target_team_id) || "Команда")}</b></div><small>${edge.projects} проектов · ${edge.completed_tasks} событий · ${edge.collaboration_points} баллов</small></div>`).join("") || '<div class="empty-inline">Совместных связей пока нет.</div>'}</div>
      </section>
    </div>`;
}

export async function recommendationsView(root, params) {
  const team = managedTeam(params);
  if (!team) return empty(root, "Команда не найдена");
  setHeader(root, "Рекомендации ассистента", "Следующие действия руководителя.");
  const data = await api.recommendations.team(team.id);
  root.querySelector("#agentic-content").innerHTML = `<div class="grid g2">${data.items.map(recommendationHtml).join("") || '<div class="note warn">Рекомендаций нет.</div>'}</div>`;
}

export async function peopleView(root, params) {
  const team = managedTeam(params);
  if (!team) return empty(root, "Команда не найдена");
  setHeader(root, "Сотрудники", "Сотрудники, нагрузка, отсутствие, достижения.");
  const data = await api.people.team(team.id);
  root.querySelector("#agentic-content").innerHTML = `<div class="grid g3">${data.items.map(personCard).join("")}</div>`;
}

export async function profileView(root, params, query = {}) {
  const mine = location.pathname === "/app/me";
  const teamId = query.team || null;
  const team = window.gcCurrentUser.teams?.find((item) => String(item.id) === String(teamId));
  const actions = team
    ? `<a class="btn btn-ghost" href="/app/teams/${team.id}">Назад к команде</a>`
    : "";
  setHeader(
    root,
    mine ? "Мой профиль" : "Профиль сотрудника",
    mine ? "Личный прогресс, активность и текущая работа." : `История работы${team ? ` в команде «${team.name}»` : ""}.`,
    actions,
  );
  const container = root.querySelector("#agentic-content");
  async function render() {
    let data;
    try {
      data = mine ? await api.people.me() : await api.people.profile(params.userId, teamId);
    } catch (e) {
      container.innerHTML = `<div class="note warn">${escapeHtml(e.message || "Не удалось загрузить профиль")}</div>`;
      return;
    }
    container.innerHTML = profileHtml(data, mine);
    bindProfileFilters(container);
    if (mine) bindProfileEdit(container, data, render);
  }
  await render();
}

const ROLE_RU = { director: "Директор", manager: "Руководитель", employee: "Сотрудник", member: "Участник" };

function profileInitials(name) {
  return (name || "").trim().split(/\s+/).slice(0, 2).map((w) => (w[0] || "").toUpperCase()).join("") || "?";
}

function avatarBlock(user, big) {
  const size = big ? "avatar-xl" : "avatar-sm";
  if (user.photo_data_url) {
    return `<div class="gc-avatar ${size}" style="background-image:url('${escapeHtml(user.photo_data_url)}')"></div>`;
  }
  return `<div class="gc-avatar ${size} ph">${escapeHtml(profileInitials(user.display_name))}</div>`;
}

function profileHtml(data, mine) {
  const u = data.user || {};
  const s = data.stats || {};
  const levelProgress = Math.min(100, Math.round((s.level_xp / (s.next_level_xp || 100)) * 100));
  const role = ROLE_RU[u.role] || u.role || "—";
  const achievements = data.achievements || [];
  const earned = achievements.filter((achievement) => achievement.earned).length;
  const tasks = data.tasks || [];
  const openTasks = tasks.filter((task) => !["done", "cancelled", "rejected"].includes(task.status));
  const completedTasks = tasks
    .filter((task) => task.completed_at)
    .sort((a, b) => new Date(b.completed_at) - new Date(a.completed_at));
  return `
  <div class="gc-profile">
    <section class="card prof-hero">
      <div class="prof-hero-row">
        <div class="prof-ava-wrap">
          ${avatarBlock(u, true)}
          ${mine ? `<label class="ava-edit" title="Загрузить фото">Фото<input type="file" id="ava-input" accept="image/*" hidden></label>` : ""}
        </div>
        <div class="prof-id">
          <div class="prof-name-row">
            <h2 id="prof-name">${escapeHtml(u.display_name || "—")}</h2>
            <span class="lvl-badge" title="Уровень">Уровень ${s.level || 1}</span>
            <span class="role-badge">${escapeHtml(role)}</span>
            ${u.telegram_linked ? `<span class="tg-badge">${escapeHtml(u.telegram_username ? "@" + u.telegram_username : "Telegram")}</span>` : ""}
          </div>
          <p class="prof-bio" id="prof-bio">${escapeHtml(u.bio || (mine ? "Добавьте пару слов о себе…" : ""))}</p>
          <p class="profile-digest">${escapeHtml(data.digest || "Данных для персональной сводки пока нет.")}</p>
          <div class="lvl-bar"><div class="lvl-fill" style="width:${levelProgress}%"></div><span class="lvl-txt">${s.level_xp || 0} / ${s.next_level_xp || 100} XP до ${(s.level || 1) + 1} уровня</span></div>
        </div>
      </div>
      ${mine ? `<div class="prof-edit-actions"><button class="btn btn-sm btn-ghost" id="edit-profile">Редактировать</button></div>` : ""}
    </section>

    <div class="prof-stats">
      ${profileStat("Серия", `${s.streak || 0} дн.`, "Дни с закрытиями подряд")}
      ${profileStat("Закрыто", s.closed_total || 0, "За всё время")}
      ${profileStat("За неделю", s.closed_week || 0, "Последние 7 дней")}
      ${profileStat("Открыто", s.open_tasks || 0, s.overdue ? `${s.overdue} просрочено` : "Без просрочек")}
    </div>

    <div class="profile-layout">
      <main class="profile-main">
        <article class="card card-pad">
          <div class="card-head">
            <div><div class="eyebrow muted">Последние 12 недель</div><div class="card-title mt-6">Активность закрытий</div></div>
            <span class="card-sub">${completedTasks.length} завершено</span>
          </div>
          ${contributionHeatmap(completedTasks)}
        </article>

        <article class="card card-pad">
          <div class="card-head">
            <div><div class="eyebrow muted">История</div><div class="card-title mt-6">Лента активности</div></div>
            <span class="card-sub">по датам закрытия</span>
          </div>
          ${activityTimeline(completedTasks)}
        </article>

        <article class="card card-pad">
          <div class="card-head">
            <div class="card-title">Все задачи</div>
            <div class="profile-task-filters" aria-label="Фильтр задач">
              <button class="active" data-profile-filter="all">Все</button>
              <button data-profile-filter="open">Открытые</button>
              <button data-profile-filter="done">Закрытые</button>
            </div>
          </div>
          <div class="profile-task-table">
            ${tasks.slice(0, 30).map(profileTaskRow).join("") || '<div class="empty-inline">Задач пока нет.</div>'}
          </div>
        </article>
      </main>

      <aside class="profile-side">
        <article class="card card-pad">
          <div class="card-head"><div class="card-title">Текущая работа</div><span class="pill ${s.overdue ? "warn" : "idle"}">${openTasks.length}</span></div>
          <div class="profile-open-list">
            ${openTasks.slice(0, 6).map((task) => `<div>
              <span class="task-key">${escapeHtml(task.public_id)}</span>
              <b>${escapeHtml(task.title)}</b>
              <small>${task.deadline ? `Срок: ${formatDate(task.deadline)}` : "Без дедлайна"}</small>
            </div>`).join("") || '<div class="empty-inline">Активных задач нет.</div>'}
          </div>
        </article>

        <article class="card card-pad">
          <div class="card-head"><div class="card-title">Достижения</div><span class="card-sub">${earned}/${achievements.length}</span></div>
          <div class="profile-achievements">
            ${achievements.map((achievement) => `<div class="${achievement.earned ? "earned" : "locked"}">
              <span>${achievement.earned ? "✓" : "·"}</span>
              <div><b>${escapeHtml(achievement.name)}</b><small>${escapeHtml(achievement.desc || "")}</small></div>
            </div>`).join("")}
          </div>
        </article>
      </aside>
    </div>
  </div>`;
}

function profileStat(label, value, hint) {
  return `<div class="card prof-stat"><div class="ps-lbl">${escapeHtml(label)}</div><div class="ps-val">${escapeHtml(String(value))}</div><div class="ps-hint">${escapeHtml(hint)}</div></div>`;
}

function contributionHeatmap(completedTasks) {
  const byDay = new Map();
  completedTasks.forEach((task) => {
    const key = dateKey(task.completed_at);
    byDay.set(key, (byDay.get(key) || 0) + 1);
  });
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const start = new Date(today);
  start.setDate(today.getDate() - 83);
  const cells = Array.from({ length: 84 }, (_, index) => {
    const date = new Date(start);
    date.setDate(start.getDate() + index);
    const count = byDay.get(dateKey(date)) || 0;
    const level = count === 0 ? 0 : count === 1 ? 1 : count <= 3 ? 2 : 3;
    const title = `${date.toLocaleDateString("ru-RU")}: ${count} закрыто`;
    return `<i class="level-${level}" title="${escapeHtml(title)}"></i>`;
  }).join("");
  return `<div class="contribution-shell">
    <div class="contribution-days"><span>Пн</span><span>Ср</span><span>Пт</span></div>
    <div class="contribution-grid">${cells}</div>
    <div class="contribution-legend"><span>Меньше</span><i></i><i class="level-1"></i><i class="level-2"></i><i class="level-3"></i><span>Больше</span></div>
  </div>`;
}

function activityTimeline(tasks) {
  if (!tasks.length) return '<div class="empty-inline">Закрытых задач пока нет.</div>';
  const groups = new Map();
  tasks.slice(0, 12).forEach((task) => {
    const key = new Date(task.completed_at).toLocaleDateString("ru-RU", {
      day: "numeric",
      month: "long",
      year: "numeric",
    });
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(task);
  });
  return `<div class="activity-timeline">${[...groups.entries()].map(([date, items]) => `
    <section>
      <time>${escapeHtml(date)}</time>
      <div>${items.map((task) => `
        <article>
          <span class="activity-marker"></span>
          <div><p>Закрыл задачу <b>${escapeHtml(task.public_id)}</b>${task.project ? ` в <a href="/app/projects/${task.project.id}">${escapeHtml(task.project.code)}</a>` : ""}</p><h4>${escapeHtml(task.title)}</h4></div>
          <small>${new Date(task.completed_at).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}</small>
        </article>`).join("")}</div>
    </section>`).join("")}</div>`;
}

function profileTaskRow(task) {
  const done = ["done", "cancelled", "rejected"].includes(task.status);
  return `<div class="profile-task-row" data-task-state="${done ? "done" : "open"}">
    <span class="task-key">${escapeHtml(task.public_id)}</span>
    <div><b>${escapeHtml(task.title)}</b><small>${task.project ? `${escapeHtml(task.project.code)} · ` : ""}${task.completed_at ? `Закрыто ${formatDate(task.completed_at)}` : task.deadline ? `Срок ${formatDate(task.deadline)}` : "Без дедлайна"}</small></div>
    <span class="pill ${task.status === "done" ? "ok" : task.status === "blocked" ? "warn" : "idle"}">${escapeHtml(profileStatusLabel(task.status))}</span>
  </div>`;
}

function bindProfileFilters(container) {
  const buttons = container.querySelectorAll("[data-profile-filter]");
  const rows = container.querySelectorAll("[data-task-state]");
  buttons.forEach((button) => {
    button.onclick = () => {
      buttons.forEach((item) => item.classList.toggle("active", item === button));
      rows.forEach((row) => {
        row.hidden = button.dataset.profileFilter !== "all"
          && row.dataset.taskState !== button.dataset.profileFilter;
      });
    };
  });
}

function profileStatusLabel(status) {
  return {
    proposed: "предложено",
    confirmed: "подтверждено",
    todo: "к работе",
    in_progress: "в работе",
    blocked: "заблокировано",
    review: "на проверке",
    done: "готово",
    cancelled: "отменено",
    rejected: "отклонено",
  }[status] || status;
}

function dateKey(value) {
  const date = value instanceof Date ? value : new Date(value);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function bindProfileEdit(container, data, rerender) {
  const u = data.user || {};
  const input = container.querySelector("#ava-input");
  if (input) {
    input.addEventListener("change", async () => {
      const file = input.files?.[0];
      if (!file) return;
      try {
        const dataUrl = await resizeImage(file, 256);
        await api.people.update({ photo_data_url: dataUrl });
        toast("Фото обновлено");
        await rerender();
      } catch (e) { toast("Не удалось загрузить фото: " + (e.message || "")); }
    });
  }
  const editBtn = container.querySelector("#edit-profile");
  if (editBtn) {
    editBtn.addEventListener("click", () => openProfileEditor(container, u, rerender));
  }
}

function openProfileEditor(container, u, rerender) {
  let dialog = document.getElementById("profile-edit-dialog");
  if (!dialog) {
    dialog = document.createElement("dialog");
    dialog.id = "profile-edit-dialog";
    dialog.className = "task-dialog";
    document.body.appendChild(dialog);
  }
  dialog.innerHTML = `<div class="task-panel">
    <header><h3>Редактировать профиль</h3><button class="icon-close" type="button">×</button></header>
    <label class="fld">Имя<input id="pe-name" value="${escapeHtml(u.display_name || "")}"></label>
    <label class="fld">О себе<textarea id="pe-bio" rows="3">${escapeHtml(u.bio || "")}</textarea></label>
    <div style="display:flex;gap:8px;margin-top:14px">
      <button class="btn btn-sm btn-primary" id="pe-save">Сохранить</button>
      <button class="btn btn-sm btn-ghost" id="pe-cancel" type="button">Отмена</button>
    </div>
  </div>`;
  dialog.querySelector(".icon-close").onclick = () => dialog.close();
  dialog.querySelector("#pe-cancel").onclick = () => dialog.close();
  dialog.querySelector("#pe-save").onclick = async () => {
    try {
      await api.people.update({
        display_name: dialog.querySelector("#pe-name").value.trim(),
        bio: dialog.querySelector("#pe-bio").value,
      });
      toast("Профиль сохранён");
      dialog.close();
      await rerender();
    } catch (e) { toast("Ошибка: " + (e.message || "")); }
  };
  dialog.showModal();
}

function resizeImage(file, max) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("read error"));
    reader.onload = () => {
      const img = new Image();
      img.onerror = () => reject(new Error("bad image"));
      img.onload = () => {
        const scale = Math.min(1, max / Math.max(img.width, img.height));
        const w = Math.round(img.width * scale), h = Math.round(img.height * scale);
        const canvas = document.createElement("canvas");
        canvas.width = w; canvas.height = h;
        canvas.getContext("2d").drawImage(img, 0, 0, w, h);
        resolve(canvas.toDataURL("image/jpeg", 0.85));
      };
      img.src = reader.result;
    };
    reader.readAsDataURL(file);
  });
}

export async function telegramTopicsView(root, params) {
  const team = managedTeam(params);
  if (!team) return empty(root, "Команда не найдена");
  setHeader(root, "Темы Telegram", "Привязка тем Telegram к команде, доске и источнику.");
  const data = await api.topics.list(team.id);
  root.querySelector("#agentic-content").innerHTML = `<div class="card card-pad"><table class="tbl"><thead><tr><th>Чат</th><th>Тема</th><th>Источник</th><th>Статус</th></tr></thead><tbody>${data.items.map(item => `<tr><td>${escapeHtml(item.chat_title || item.telegram_chat_id)}</td><td class="mono">${item.message_thread_id}</td><td>${escapeHtml(item.source_name || "Тема Telegram")}</td><td><span class="pill ${item.bound ? "ok" : "warn"}">${item.bound ? "привязано" : "новая"}</span></td></tr>`).join("") || '<tr><td colspan="4">Темы появятся после сообщений из Telegram.</td></tr>'}</tbody></table></div>`;
}

function personCard(item) {
  const p = item.profile;
  return `<a class="card card-pad" href="/app/people/${item.id}"><div class="card-title">${escapeHtml(item.display_name)}</div><div class="dim">${escapeHtml(item.role)}</div><div class="grid g2 mt-16">${stat("Open", p.stats.open_tasks)}${stat("Overdue", p.stats.overdue)}${stat("XP", p.stats.xp)}${stat("Absence", p.absence.active ? "yes" : "no")}</div></a>`;
}

function stat(label, value) {
  return `<div class="stat"><div class="stat-label">${escapeHtml(label)}</div><div class="stat-value mono">${escapeHtml(String(value))}</div></div>`;
}

function sourceLabel(value) {
  return {
    manual: "вручную",
    telegram: "Telegram",
    meeting: "созвон",
    meeting_transcript: "транскрипт",
    yougile: "YouGile",
  }[value] || value || "источник";
}

function empty(root, text) {
  root.querySelector("#agentic-content").innerHTML = `<div class="note warn">${escapeHtml(text)}</div>`;
}

export default greyBoardView;

import { api } from "../api.js";
import { wsOn } from "../ws.js";
import { emptyState, errorMessage, escapeHtml, formatDate, setTopbar, toast } from "../view-utils.js";

const ACTIVE_STATUSES = new Set(["proposed", "confirmed", "todo", "new", "in_progress", "blocked", "review"]);
const DONE_STATUSES = new Set(["done", "cancelled"]);

export default async function managerView(root, params) {
  const teamId = params.id || window.gcCurrentUser.teams?.find((team) => team.role === "manager")?.id;
  const content = root.querySelector("#manager-content");
  if (!teamId) {
    content.innerHTML = emptyState("Нет доступной команды", "Примите приглашение или создайте команду.");
    return;
  }

  let team;
  try {
    team = await api.teams.get(teamId);
  } catch (error) {
    content.innerHTML = `<div class="note warn">${escapeHtml(errorMessage(error))}</div>`;
    return;
  }

  window.gcCurrentUser.teams = window.gcCurrentUser.teams.map((item) =>
    item.id === team.id ? { ...item, ...team } : item);
  root.querySelector("#team-title").textContent = team.name;
  setTopbar(team.name, `
    <a class="btn btn-ghost" href="/app/teams/${team.id}/insights">AI-аналитика</a>
    <button class="btn btn-primary" id="invite-employee">Пригласить</button>`);

  await render(root, team);
  document.getElementById("invite-employee").onclick = () => createInvite(root, team);

  const refresh = (payload) => {
    if (String(payload?.team_id) === String(teamId)) render(root, team);
  };
  const unsubs = ["card_created", "card_moved", "card_closed", "meeting_confirmed", "task_status_responded"]
    .map((event) => wsOn(event, refresh));
  return () => unsubs.forEach((unsubscribe) => unsubscribe());
}

async function render(root, team) {
  const [
    meetings,
    telegram,
    yougile,
    agents,
    members,
    localTasks,
    llm,
    pulse,
    standup,
    copilot,
  ] = await Promise.all([
    api.meetings.list(team.id).catch(() => ({ items: [] })),
    api.teams.telegramStatus(team.id).catch(() => ({ linked: false })),
    api.yougile.status(team.id).catch(() => ({ connected: false })),
    api.daemon.status().catch(() => ({ agents: [] })),
    api.teams.members(team.id).catch(() => ({ items: [] })),
    api.tasks.list(team.id).catch(() => ({ items: [] })),
    api.llm.health(team.id).catch(() => ({ status: "error" })),
    api.insights.pulse(team.id).catch(() => ({ metrics: {} })),
    api.insights.standup(team.id).catch(() => ({ total_blocked: 0, members: [] })),
    api.insights.copilot(team.id).catch(() => ({ actions: [] })),
  ]);

  const tasks = localTasks.items || [];
  const people = members.items || [];
  const metrics = pulse.metrics || {};
  const now = Date.now();
  const active = tasks.filter((task) => ACTIVE_STATUSES.has(task.status));
  const overdue = active.filter((task) => task.deadline && new Date(task.deadline).getTime() < now);
  const blocked = active.filter((task) => task.status === "blocked");
  const closedWeek = tasks.filter((task) =>
    task.completed_at && new Date(task.completed_at).getTime() >= now - 7 * 86400000);
  const health = [
    telegram.linked,
    yougile.connected,
    llm.status === "ok",
    agents.agents?.some((agent) => agent.online),
  ].filter(Boolean).length;

  root.querySelector("#manager-content").innerHTML = `
    <div class="team-dashboard">
      <section class="team-workspace">
        <section class="team-command-hero">
          <div>
            <div class="eyebrow muted">Командный обзор</div>
            <h2>${teamHealthTitle(overdue.length, blocked.length)}</h2>
            <p>${teamHealthText(overdue.length, blocked.length, closedWeek.length)}</p>
          </div>
          <div class="team-hero-actions">
            <a class="btn btn-ghost" href="/app/teams/${team.id}/board">Grey Board</a>
            <a class="btn btn-primary" href="/app/teams/${team.id}/insights">Открыть AI-центр</a>
          </div>
        </section>

        <div class="team-kpis">
          ${teamMetric("Активные", active.length, `${blocked.length} заблокировано`, blocked.length ? "warn" : "")}
          ${teamMetric("Закрыто за 7 дней", closedWeek.length, weekDelta(metrics), closedWeek.length ? "ok" : "")}
          ${teamMetric("Просрочено", overdue.length, overdue.length ? "Нужна сортировка" : "Сроки в норме", overdue.length ? "err" : "ok")}
          ${teamMetric("Контур готов", `${health}/4`, health === 4 ? "Все системы доступны" : "Есть что настроить", health === 4 ? "ok" : "warn")}
        </div>

        <div class="team-overview-grid">
          <article class="card card-pad team-velocity-card">
            <div class="card-head">
              <div><div class="eyebrow muted">Динамика</div><div class="card-title mt-6">Закрытия за 7 дней</div></div>
              <span class="pill ${closedWeek.length ? "ok" : "idle"}"><span class="dot"></span>${closedWeek.length} завершено</span>
            </div>
            ${velocityChart(tasks)}
          </article>
          <article class="card card-pad team-focus-card">
            <div class="card-head">
              <div><div class="eyebrow muted">Фокус</div><div class="card-title mt-6">Решения на сегодня</div></div>
              <a class="card-sub accent-text" href="/app/teams/${team.id}/insights?view=copilot">Все</a>
            </div>
            ${focusActions(copilot.actions, overdue, blocked)}
          </article>
        </div>

        <div class="team-overview-grid secondary">
          <article class="card card-pad">
            <div class="card-head">
              <div><div class="eyebrow muted">Распределение</div><div class="card-title mt-6">Нагрузка по людям</div></div>
              <span class="card-sub">${people.length} участников</span>
            </div>
            ${workloadChart(people, tasks, team.id)}
          </article>
          <article class="card card-pad">
            <div class="card-head">
              <div><div class="eyebrow muted">Сейчас</div><div class="card-title mt-6">Командный стендап</div></div>
              <a class="card-sub accent-text" href="/app/teams/${team.id}/insights?view=standup">Подробнее</a>
            </div>
            ${standupSummary(standup)}
          </article>
        </div>

        <article class="card card-pad mt-16">
          <div class="card-head">
            <div><div class="eyebrow muted">Текущая работа</div><div class="card-title mt-6">Поток задач</div></div>
            <a class="card-sub accent-text" href="/app/teams/${team.id}/board">Открыть полную доску</a>
          </div>
          ${taskKanban(tasks)}
        </article>

        <div class="team-bottom-grid mt-16">
          <article class="card card-pad">
            <div class="card-head"><div class="card-title">Ближайшие созвоны</div><a href="/app/meetings" class="card-sub accent-text">Все</a></div>
            ${meetings.items.slice(0, 4).map((meeting) => `
              <a class="integration-row compact" href="/app/meetings/${meeting.id}">
                <span><b>${escapeHtml(meeting.title)}</b><span class="meta">${formatDate(meeting.scheduled_at)}</span></span>
                <span class="pill info">${escapeHtml(meeting.state)}</span>
              </a>`).join("") || '<div class="empty-inline">Запланированных созвонов нет.</div>'}
          </article>
          <article class="card card-pad">
            <div class="card-head"><div class="card-title">Состояние систем</div><a href="/app/integrations" class="card-sub accent-text">Настроить</a></div>
            <div class="system-health-grid">
              ${systemHealth("Telegram", telegram.linked, "/app/integrations/telegram")}
              ${systemHealth("YouGile", yougile.connected, "/app/integrations/yougile")}
              ${systemHealth("AI-модель", llm.status === "ok", "/app/integrations/llm")}
              ${systemHealth("Windows-агент", agents.agents?.some((agent) => agent.online), "/app/integrations/daemon")}
            </div>
          </article>
        </div>
      </section>
      ${membersRail(team, people, tasks)}
    </div>`;
  bindMemberActions(root, team);
}

function teamMetric(label, value, hint, tone = "") {
  return `<div class="team-metric ${tone}">
    <span>${escapeHtml(label)}</span><strong>${escapeHtml(String(value))}</strong><small>${escapeHtml(hint)}</small>
  </div>`;
}

function teamHealthTitle(overdue, blocked) {
  if (overdue >= 3) return "Накопились задачи, которые требуют решения";
  if (blocked) return "Темп есть, но часть работы упёрлась в блокеры";
  return "Команда движется в устойчивом ритме";
}

function countPhrase(count, forms) {
  const value = Math.abs(Number(count) || 0);
  const mod100 = value % 100;
  const mod10 = value % 10;
  const form = mod100 >= 11 && mod100 <= 14
    ? forms[2]
    : mod10 === 1
      ? forms[0]
      : mod10 >= 2 && mod10 <= 4
        ? forms[1]
        : forms[2];
  return `${value} ${form}`;
}

function teamHealthText(overdue, blocked, closedWeek) {
  if (overdue || blocked) {
    const risks = [
      overdue ? countPhrase(overdue, ["просроченная задача", "просроченные задачи", "просроченных задач"]) : "",
      blocked ? countPhrase(blocked, ["заблокированная задача", "заблокированные задачи", "заблокированных задач"]) : "",
    ].filter(Boolean).join(" и ");
    return `${risks}. Ниже собраны люди и действия, с которых лучше начать.`;
  }
  return `${countPhrase(closedWeek, ["задача закрыта", "задачи закрыты", "задач закрыто"])} за неделю. Критичных сигналов в рабочем потоке сейчас нет.`;
}

function weekDelta(metrics) {
  const current = Number(metrics.completed_this_week || 0);
  const previous = Number(metrics.completed_prev_week || 0);
  const delta = current - previous;
  if (!current && !previous) return "Пока без динамики";
  if (!delta) return "На уровне прошлой недели";
  return `${delta > 0 ? "+" : ""}${delta} к прошлой неделе`;
}

function velocityChart(tasks) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const days = Array.from({ length: 7 }, (_, index) => {
    const date = new Date(today);
    date.setDate(today.getDate() - (6 - index));
    const next = new Date(date);
    next.setDate(date.getDate() + 1);
    const count = tasks.filter((task) => {
      if (!task.completed_at) return false;
      const completed = new Date(task.completed_at);
      return completed >= date && completed < next;
    }).length;
    return {
      count,
      label: new Intl.DateTimeFormat("ru-RU", { weekday: "short" }).format(date).replace(".", ""),
      date: new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "2-digit" }).format(date),
    };
  });
  const max = Math.max(1, ...days.map((day) => day.count));
  return `<div class="velocity-chart">
    ${days.map((day) => `<div class="velocity-day">
      <div class="velocity-bar-wrap"><i style="height:${Math.max(5, Math.round(day.count / max * 100))}%"></i><b>${day.count || ""}</b></div>
      <span>${escapeHtml(day.label)}</span><small>${day.date}</small>
    </div>`).join("")}
  </div>`;
}

function focusActions(actions, overdue, blocked) {
  const items = (actions || []).map((action) => action.text);
  if (!items.length && overdue.length) items.push(`Разобрать просроченную задачу ${overdue[0].public_id}: ${overdue[0].title}`);
  if (items.length < 3 && blocked.length) items.push(`Снять блокировку с ${blocked[0].public_id}: ${blocked[0].title}`);
  if (!items.length) {
    return '<div class="empty-inline">Срочных решений нет. Можно двигать стратегические задачи.</div>';
  }
  return `<div class="team-focus-list">${items.slice(0, 3).map((item, index) => `
    <div><span>${index + 1}</span><p>${escapeHtml(item)}</p></div>`).join("")}</div>`;
}

function workloadChart(members, tasks, teamId) {
  const rows = members.map((member) => {
    const mine = tasks.filter((task) => String(task.assignee_id) === String(member.id));
    const active = mine.filter((task) => ACTIVE_STATUSES.has(task.status)).length;
    const blocked = mine.filter((task) => task.status === "blocked").length;
    return { member, active, blocked };
  }).sort((a, b) => b.active - a.active);
  const max = Math.max(1, ...rows.map((row) => row.active));
  return rows.length ? `<div class="workload-list">${rows.slice(0, 7).map(({ member, active, blocked }) => `
    <a class="workload-row" href="/app/people/${member.id}?team=${teamId}">
      <span class="compact-avatar">${memberInitials(member)}</span>
      <span class="workload-person"><b>${escapeHtml(member.display_name || member.email)}</b><small>${blocked
        ? countPhrase(blocked, ["задача заблокирована", "задачи заблокированы", "задач заблокировано"])
        : countPhrase(active, ["активная задача", "активные задачи", "активных задач"])}</small></span>
      <span class="workload-track"><i class="${blocked ? "warn" : ""}" style="width:${Math.max(active ? 8 : 0, Math.round(active / max * 100))}%"></i></span>
      <strong class="mono">${active}</strong>
    </a>`).join("")}</div>` : '<div class="empty-inline">Участники ещё не добавлены.</div>';
}

function standupSummary(standup) {
  const members = standup.members || [];
  return members.length ? `<div class="standup-compact-list">${members.slice(0, 5).map((member) => `
    <div>
      <span class="status-line ${member.blocked?.length ? "blocked" : "active"}"></span>
      <span class="grow"><b>${escapeHtml(member.display_name)}</b><small>${escapeHtml(member.blocked?.[0] || member.doing?.[0] || member.done_recently?.[0] || "Без активных задач")}</small></span>
      <span class="pill ${member.needs_help ? "warn" : "idle"}">${member.needs_help ? "помочь" : "в работе"}</span>
    </div>`).join("")}</div>` : '<div class="empty-inline">Активной работы для стендапа пока нет.</div>';
}

function taskKanban(tasks) {
  const columns = [
    ["К выполнению", ["proposed", "confirmed", "todo", "new"]],
    ["В работе", ["in_progress", "blocked", "review"]],
    ["Готово", ["done", "cancelled"]],
  ];
  return `<div class="team-flow-board">${columns.map(([title, statuses]) => {
    const items = tasks.filter((task) => statuses.includes(task.status));
    return `<section class="team-flow-column">
      <header><b>${title}</b><span>${items.length}</span></header>
      <div>${items.slice(0, 4).map(taskMiniCard).join("") || '<div class="board-empty">Пусто</div>'}</div>
    </section>`;
  }).join("")}</div>`;
}

function taskMiniCard(task) {
  return `<article class="team-task-mini ${task.status === "blocked" ? "blocked" : ""}">
    <div><span class="task-key">${escapeHtml(task.public_id)}</span><span class="pill idle">${statusLabel(task.status)}</span></div>
    <b>${escapeHtml(task.title)}</b>
    <small>${escapeHtml(task.assignee_name || "Без исполнителя")}${task.deadline ? ` · ${formatDate(task.deadline)}` : ""}</small>
  </article>`;
}

function systemHealth(name, connected, href) {
  return `<a class="system-health-item ${connected ? "ok" : ""}" href="${href}">
    <span class="dot"></span><b>${escapeHtml(name)}</b><small>${connected ? "работает" : "настроить"}</small>
  </a>`;
}

function membersRail(team, members, tasks) {
  const currentUser = window.gcCurrentUser || {};
  const teamRole = currentUser.teams?.find((item) => item.id === team.id)?.role;
  const canManage = teamRole === "manager"
    || currentUser.companies?.some((company) => company.id === team.company_id && company.role === "director");
  const sorted = [...members].sort((a, b) =>
    Number(b.online) - Number(a.online)
    || roleRank(a.role) - roleRank(b.role)
    || (a.display_name || "").localeCompare(b.display_name || "", "ru"));
  return `<aside class="team-members-rail">
    <div class="rail-head">
      <div><div class="eyebrow muted">Команда</div><div class="rail-title">${sorted.length} человек</div></div>
      <button class="btn btn-sm btn-primary" id="rail-invite" type="button">Добавить</button>
    </div>
    <p class="rail-hint">Нажмите на сотрудника, чтобы открыть историю работы и закрытых задач.</p>
    <div class="member-list">
      ${sorted.map((member) => memberRow(member, canManage, String(currentUser.id || ""), team.id, tasks)).join("")
        || '<div class="dim">В команде пока никого нет.</div>'}
    </div>
  </aside>`;
}

function memberRow(member, canManage, currentUserId, teamId, tasks) {
  const avatarStyle = member.photo_data_url
    ? `background-image:url('${escapeHtml(member.photo_data_url)}');background-size:cover;background-position:center`
    : "background:#2a2a33";
  const mine = tasks.filter((task) => String(task.assignee_id) === String(member.id));
  const active = mine.filter((task) => ACTIVE_STATUSES.has(task.status)).length;
  const closed = mine.filter((task) => DONE_STATUSES.has(task.status)).length;
  const isSelf = String(member.id) === currentUserId;
  const nextRole = member.role === "manager" ? "employee" : "manager";
  const roleAction = member.role === "manager" ? "Снять роль" : "Сделать руководителем";
  return `<div class="member-row" data-user="${escapeHtml(member.id)}">
    <a class="member-profile-link" href="/app/people/${member.id}?team=${teamId}">
      <div class="member-avatar av sm" style="${avatarStyle}">${member.photo_data_url ? "" : memberInitials(member)}</div>
      <div class="member-meta">
        <div class="member-name">${escapeHtml(member.display_name || member.email)}</div>
        <div class="member-status ${member.online ? "online" : ""}"><span></span>${member.online ? "онлайн" : `был ${formatLastSeen(member.last_seen_at)}`}</div>
      </div>
      <span class="member-workload">${active} / ${closed}</span>
    </a>
    <div class="member-row-foot">
      <span class="tag">${member.role === "manager" ? "Руководитель" : "Сотрудник"}</span>
      ${canManage ? `<button class="member-menu-button" type="button" aria-label="Действия">•••</button>` : ""}
    </div>
    ${canManage ? `<div class="member-actions" hidden>
      <button class="btn btn-sm btn-ghost member-role" data-role="${nextRole}" type="button">${roleAction}</button>
      <button class="btn btn-sm btn-ghost member-remove" type="button" ${isSelf ? "disabled" : ""}>Удалить</button>
    </div>` : ""}
  </div>`;
}

function bindMemberActions(root, team) {
  root.querySelector("#rail-invite")?.addEventListener("click", () => createInvite(root, team));
  root.querySelectorAll(".member-menu-button").forEach((button) => {
    button.addEventListener("click", () => {
      const actions = button.closest(".member-row")?.querySelector(".member-actions");
      if (actions) actions.hidden = !actions.hidden;
    });
  });
  root.querySelectorAll(".member-role").forEach((button) => {
    button.addEventListener("click", async () => {
      const userId = button.closest(".member-row")?.dataset.user;
      try {
        await api.teams.updateMemberRole(team.id, userId, button.dataset.role);
        toast(button.dataset.role === "manager" ? "Руководитель назначен" : "Роль обновлена");
        await render(root, team);
      } catch (error) {
        toast(errorMessage(error), "err");
      }
    });
  });
  root.querySelectorAll(".member-remove").forEach((button) => {
    button.addEventListener("click", async () => {
      const row = button.closest(".member-row");
      const name = row?.querySelector(".member-name")?.textContent || "сотрудника";
      if (!confirm(`Удалить ${name} из команды?`)) return;
      try {
        await api.teams.removeMember(team.id, row.dataset.user);
        toast("Сотрудник удалён");
        await render(root, team);
      } catch (error) {
        toast(errorMessage(error), "err");
      }
    });
  });
}

function statusLabel(status) {
  return {
    proposed: "предложено",
    confirmed: "подтверждено",
    todo: "к работе",
    new: "новая",
    in_progress: "в работе",
    blocked: "блок",
    review: "проверка",
    done: "готово",
    cancelled: "отменено",
  }[status] || status;
}

function memberInitials(member) {
  return escapeHtml((member.display_name || member.email || "?")
    .split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase());
}

function roleRank(role) {
  return role === "manager" ? 0 : 1;
}

function formatLastSeen(value) {
  if (!value) return "не появлялся";
  const date = new Date(value);
  const minutes = Math.round((Date.now() - date.getTime()) / 60000);
  if (minutes < 1) return "только что";
  if (minutes < 60) return `${minutes} мин назад`;
  if (minutes < 1440) return `${Math.round(minutes / 60)} ч назад`;
  return date.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" });
}

async function createInvite(root, team) {
  try {
    const invite = await api.teams.invite(team, "employee");
    const url = `${location.origin}/invite.html?token=${encodeURIComponent(invite.token)}`;
    root.insertAdjacentHTML("beforeend", `
      <div class="modal-backdrop" id="employee-invite">
        <div class="modal">
          <h2>Приглашение сотрудника</h2>
          <p class="dim mt-8">Ссылка добавит человека именно в команду «${escapeHtml(team.name)}».</p>
          <div class="code-msg mt-16">${escapeHtml(url)}</div>
          <div class="flex gap-8 mt-16">
            <button class="btn btn-primary" id="copy-employee">Копировать</button>
            <button class="btn btn-ghost" id="close-employee">Закрыть</button>
          </div>
        </div>
      </div>`);
    root.querySelector("#copy-employee").onclick = async () => {
      await navigator.clipboard.writeText(url);
      toast("Ссылка скопирована");
    };
    root.querySelector("#close-employee").onclick = () => root.querySelector("#employee-invite").remove();
  } catch (error) {
    toast(errorMessage(error), "err");
  }
}

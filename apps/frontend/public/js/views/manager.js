import { api } from "../api.js";
import { wsOn } from "../ws.js";
import { emptyState, errorMessage, escapeHtml, formatDate, setTopbar, toast } from "../view-utils.js";

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
  window.gcCurrentUser.teams = window.gcCurrentUser.teams.map((item) => item.id === team.id ? { ...item, ...team } : item);
  root.querySelector("#team-title").textContent = team.name;
  setTopbar(team.name, '<button class="btn btn-primary" id="invite-employee">Пригласить</button>');
  await render(root, team);
  document.getElementById("invite-employee").onclick = () => createInvite(root, team);

  const refresh = (payload) => {
    if (payload?.team_id === teamId) render(root, team);
  };
  const unsubs = ["card_created", "card_moved", "card_closed", "meeting_confirmed"].map((event) => wsOn(event, refresh));
  return () => unsubs.forEach((unsubscribe) => unsubscribe());
}

async function render(root, team) {
  const [meetings, telegram, yougile, agents, board, members, localTasks, llm] = await Promise.all([
    api.meetings.list(team.id).catch(() => ({ items: [] })),
    api.teams.telegramStatus(team.id).catch(() => ({ linked: false })),
    api.yougile.status(team.id).catch(() => ({ connected: false })),
    api.daemon.status().catch(() => ({ agents: [] })),
    loadBoard(team.id),
    api.teams.members(team.id).catch(() => ({ items: [] })),
    api.tasks.list(team.id).catch(() => ({ items: [] })),
    api.llm.health(team.id).catch(() => ({ status: "error" })),
  ]);
  root.querySelector("#manager-content").innerHTML = `
    <div class="team-dashboard">
    <section class="team-workspace">
    <div class="grid g4">
      <div class="stat"><div class="stat-label">Активных задач</div><div class="stat-value mono">${localTasks.items.filter((task) => !["done", "cancelled"].includes(task.status)).length}</div></div>
      <div class="stat"><div class="stat-label">Созвонов</div><div class="stat-value mono">${meetings.items.length}</div></div>
      <div class="stat"><div class="stat-label">Telegram</div><div class="stat-value" style="font-size:20px">${telegram.linked ? "Подключён" : "Не подключён"}</div></div>
      <div class="stat"><div class="stat-label">Участников</div><div class="stat-value mono">${members.items.length}</div></div>
    </div>
    <div class="card card-pad mt-20"><div class="card-head"><div class="card-title">Рабочий поток</div><span class="card-sub">${localTasks.items.length} задач</span></div>${taskKanban(localTasks.items)}</div>
    <div class="card card-pad mt-20">
      <div class="card-head"><div class="card-title">YouGile зеркало</div><a class="card-sub accent-text" href="/app/integrations/yougile">Настроить</a></div>
      ${yougile.connected ? board.html : '<div class="note warn">YouGile ещё не подключён.</div>'}
    </div>
    <div class="grid g2 mt-20">
      <div class="card card-pad"><div class="card-head"><div class="card-title">Ближайшие созвоны</div><a href="/app/meetings" class="card-sub accent-text">Все</a></div>
        ${meetings.items.slice(0, 4).map((meeting) => `<a class="integration-row" href="/app/meetings/${meeting.id}"><span><b>${escapeHtml(meeting.title)}</b><span class="meta">${formatDate(meeting.scheduled_at)}</span></span><span class="pill info">${escapeHtml(meeting.state)}</span></a>`).join("") || '<div class="dim">Созвонов пока нет.</div>'}
      </div>
      <div class="card card-pad"><div class="card-head"><div class="card-title">Интеграции</div></div>
        ${integration("Telegram-чат", telegram.linked, "/app/integrations/telegram")}
        ${integration("YouGile", yougile.connected, "/app/integrations/yougile")}
        ${integration("LLM (семантика)", llm.status === "ok", "/app/integrations/llm")}
        ${integration("Windows-агент", agents.agents.length > 0, "/app/integrations/daemon")}
      </div>
    </div>
    </section>
    ${membersRail(team, members.items || [])}
    </div>`;
  bindMemberActions(root, team);
}

function taskKanban(tasks) {
  const columns = [
    ["К выполнению", ["proposed", "todo", "new"]],
    ["В работе", ["in_progress", "blocked"]],
    ["Готово", ["done", "cancelled"]],
  ];
  return `<div class="kanban">${columns.map(([title, statuses]) => `<div class="kanban-col"><b>${title}</b><div class="col gap-8 mt-12">${tasks.filter((task) => statuses.includes(task.status)).map((task) => `<div class="card card-pad" style="padding:12px"><div class="flex between gap-8"><b>${escapeHtml(task.title)}</b><span class="pill info">${escapeHtml(task.public_id)}</span></div><div class="meta mt-8">${escapeHtml(task.assignee_name || "Не назначено")}</div></div>`).join("") || '<span class="faint">Пусто</span>'}</div></div>`).join("")}</div>`;
}

async function loadBoard(teamId) {
  try {
    const projects = await api.yougile.projects(teamId);
    const project = projects.find((item) => item.is_primary) || projects[0];
    if (!project) return { count: 0, html: '<div class="dim">В YouGile пока нет проектов.</div>' };
    const boards = await api.yougile.boards(teamId, project.id);
    const columns = boards.flatMap((board) => board.columns || []).slice(0, 3);
    const tasks = await Promise.all(columns.map((column) => api.yougile.tasks(teamId, column.id)));
    return {
      count: tasks.flat().length,
      html: `<div class="kanban">${columns.map((column, index) => `<div class="kanban-col"><b>${escapeHtml(column.name)}</b><div class="col gap-8 mt-12">${tasks[index].map((task) => `<div class="card card-pad" style="padding:12px"><b>${escapeHtml(task.title)}</b>${task.deadline ? `<div class="faint mt-8">${formatDate(task.deadline)}</div>` : ""}</div>`).join("") || '<span class="faint">Пусто</span>'}</div></div>`).join("")}</div>`,
    };
  } catch {
    return { count: 0, html: '<div class="note warn">Не удалось загрузить зеркало доски.</div>' };
  }
}

function integration(name, connected, href) {
  return `<a class="integration-row" href="${href}"><span>${name}</span><span class="pill ${connected ? "ok" : "warn"}"><span class="dot"></span>${connected ? "подключено" : "настроить"}</span></a>`;
}

function membersRail(team, members) {
  const currentUser = window.gcCurrentUser || {};
  const teamRole = currentUser.teams?.find((item) => item.id === team.id)?.role;
  const canManage = teamRole === "manager" || currentUser.companies?.some((company) => company.id === team.company_id && company.role === "director");
  const sorted = [...members].sort((a, b) => Number(b.online) - Number(a.online) || roleRank(a.role) - roleRank(b.role) || (a.display_name || "").localeCompare(b.display_name || "", "ru"));
  return `<aside class="team-members-rail">
    <div class="rail-head">
      <div><div class="eyebrow muted">Участники отдела</div><div class="rail-title">${sorted.length} человек</div></div>
      <button class="btn btn-sm btn-primary" id="rail-invite" type="button">Пригласить</button>
    </div>
    <div class="member-list">
      ${sorted.map((member) => memberRow(member, canManage, String(currentUser.id || ""))).join("") || '<div class="dim">В команде пока никого нет.</div>'}
    </div>
  </aside>`;
}

function memberRow(member, canManage, currentUserId) {
  const initials = (member.display_name || member.email || "?").split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase();
  const avatarStyle = member.photo_data_url
    ? `background-image:url('${escapeHtml(member.photo_data_url)}');background-size:cover;background-position:center`
    : "background:#2a2a33";
  const isSelf = String(member.id) === currentUserId;
  const nextRole = member.role === "manager" ? "employee" : "manager";
  const roleAction = member.role === "manager" ? "Снять" : "Назначить";
  return `<div class="member-row" data-user="${escapeHtml(member.id)}">
    <div class="member-avatar av sm" style="${avatarStyle}">${member.photo_data_url ? "" : escapeHtml(initials)}</div>
    <div class="member-meta">
      <div class="member-name">${escapeHtml(member.display_name || member.email)}</div>
      <div class="member-status ${member.online ? "online" : ""}"><span></span>${member.online ? "онлайн" : `был ${formatLastSeen(member.last_seen_at)}`}</div>
    </div>
    <span class="tag">${member.role === "manager" ? "Руководитель" : "Сотрудник"}</span>
    ${canManage ? `<div class="member-actions">
      <button class="btn btn-sm btn-ghost member-role" data-role="${nextRole}" type="button">${roleAction}</button>
      <button class="btn btn-sm btn-ghost member-remove" type="button" ${isSelf ? "disabled" : ""}>Удалить</button>
    </div>` : ""}
  </div>`;
}

function bindMemberActions(root, team) {
  root.querySelector("#rail-invite")?.addEventListener("click", () => createInvite(root, team));
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
      if (!confirm(`Удалить ${name} из отдела?`)) return;
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
    root.insertAdjacentHTML("beforeend", `<div class="modal-backdrop" id="employee-invite"><div class="modal"><h2>Приглашение сотрудника</h2><div class="code-msg mt-16">${escapeHtml(url)}</div><div class="flex gap-8 mt-16"><button class="btn btn-primary" id="copy-employee">Копировать</button><button class="btn btn-ghost" id="close-employee">Закрыть</button></div></div></div>`);
    root.querySelector("#copy-employee").onclick = async () => { await navigator.clipboard.writeText(url); toast("Ссылка скопирована"); };
    root.querySelector("#close-employee").onclick = () => root.querySelector("#employee-invite").remove();
  } catch (error) {
    toast(errorMessage(error), "err");
  }
}

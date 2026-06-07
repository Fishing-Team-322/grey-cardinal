import { api } from "../api.js";
import { wsOn } from "../ws.js";
import { emptyState, escapeHtml, formatDate, setTopbar } from "../view-utils.js";

export default async function employeeView(root) {
  setTopbar("Моя панель");
  const content = root.querySelector("#employee-content");
  const teams = window.gcCurrentUser.teams || [];
  if (!teams.length) {
    content.innerHTML = emptyState("Нет команды", "Примите приглашение, чтобы увидеть задачи и созвоны.");
    return;
  }
  const [gamification, agents, meetingLists, taskLists] = await Promise.all([
    api.leaderboards.me().catch(() => null),
    api.daemon.status().catch(() => ({ agents: [] })),
    Promise.all(teams.map((team) => api.meetings.list(team.id).catch(() => ({ items: [] })))),
    Promise.all(teams.map((team) => api.tasks.list(team.id, { assignee: "me" }).catch(() => null))),
  ]);
  const meetings = meetingLists.flatMap((list) => list.items || []);
  const tasksAvailable = taskLists.some(Boolean);
  const tasks = taskLists.flatMap((list) => list?.items || []);
  content.innerHTML = `
    <div class="grid g4">
      <div class="stat"><div class="stat-label">Мой XP</div><div class="stat-value mono">${gamification?.xp ?? 0}</div></div>
      <div class="stat"><div class="stat-label">Позиция</div><div class="stat-value mono">${gamification?.rank ?? "—"}</div></div>
      <div class="stat"><div class="stat-label">Созвонов</div><div class="stat-value mono">${meetings.length}</div></div>
      <div class="stat"><div class="stat-label">Windows Agent</div><div class="stat-value" style="font-size:20px">${agents.agents.some((agent) => agent.online) ? "Online" : "Offline"}</div></div>
    </div>
    <div class="grid g2 mt-20">
      <div class="card card-pad"><div class="card-head"><div class="card-title">Мои задачи</div></div>
        ${tasksAvailable ? tasks.map((task) => `<div class="card card-pad mt-8" style="padding:14px"><div class="flex between gap-8"><span><b>${escapeHtml(task.title)}</b><span class="meta">${escapeHtml(task.public_id)} · ${escapeHtml(task.status)}</span></span>${task.deadline ? `<span class="faint">${formatDate(task.deadline)}</span>` : ""}</div><div class="flex gap-8 wrap mt-12"><button class="btn btn-sm btn-ghost task-response" data-id="${task.id}" data-response="in_progress">В процессе</button><button class="btn btn-sm btn-primary task-response" data-id="${task.id}" data-response="done">Сделал</button><button class="btn btn-sm btn-ghost task-response" data-id="${task.id}" data-response="wont_do">Не буду делать</button></div></div>`).join("") || '<div class="dim">Назначенных задач пока нет.</div>' : '<div class="note warn">Не удалось загрузить задачи.</div>'}
      </div>
      <div class="card card-pad"><div class="card-head"><div class="card-title">Ближайшие созвоны</div></div>
        ${meetings.slice(0, 6).map((meeting) => `<a class="integration-row" href="/app/meetings/${meeting.id}"><span><b>${escapeHtml(meeting.title)}</b><span class="meta">${formatDate(meeting.scheduled_at)}</span></span><span class="pill info">${escapeHtml(meeting.state)}</span></a>`).join("") || '<div class="dim">Созвонов пока нет.</div>'}
      </div>
    </div>`;
  content.querySelectorAll(".task-response").forEach((button) => {
    button.onclick = async () => {
      let reason;
      if (button.dataset.response === "wont_do") {
        reason = prompt("Укажите причину: нет времени, не актуально, передал другому или заблокировано");
        if (!reason) return;
      }
      await api.tasks.statusResponse(button.dataset.id, button.dataset.response, reason);
      const card = button.closest(".card");
      card.querySelector(".meta").textContent = `${card.querySelector(".meta").textContent.split(" · ")[0]} · ${button.dataset.response}`;
    };
  });
  const refresh = (payload) => {
    if (teams.some((team) => team.id === payload?.team_id)) location.reload();
  };
  const unsubs = ["xp_granted", "card_moved", "meeting_armed"].map((event) => wsOn(event, refresh));
  return () => unsubs.forEach((unsubscribe) => unsubscribe());
}

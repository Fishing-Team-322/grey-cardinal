import { api } from "../api.js";
import { currentTeam, errorMessage, escapeHtml, formatDate, setTopbar } from "../view-utils.js";

export default async function leaderboardView(root) {
  setTopbar("Лидерборд");
  const content = root.querySelector("#leaderboard-content");
  const team = currentTeam(window.gcCurrentUser);
  const company = window.gcCurrentUser.companies?.[0];

  async function show(tab) {
    root.querySelectorAll("#leaderboard-tabs button").forEach((button) => button.classList.toggle("active", button.dataset.tab === tab));
    content.innerHTML = '<div class="view-loading">Загрузка...</div>';
    try {
      if (tab === "me") {
        const data = await api.leaderboards.me();
        content.innerHTML = `<div class="grid g4"><div class="stat"><div class="stat-label">Всего XP</div><div class="stat-value mono">${data.points_total}</div></div><div class="stat"><div class="stat-label">Уровень</div><div class="stat-value mono">${data.level}</div></div><div class="stat"><div class="stat-label">До следующего</div><div class="stat-value mono">${data.next_level_xp - data.level_xp}</div></div><div class="stat"><div class="stat-label">Достижения</div><div class="stat-value mono">${data.achievements.filter((item) => item.unlocked).length}</div></div></div>
          <div class="card card-pad mt-20"><div class="card-head"><div class="card-title">История начислений</div></div>${data.recent_events.map((event) => `<div class="integration-row"><span><b>${escapeHtml(event.reason)}</b><span class="meta">${formatDate(event.created_at)}</span></span><span class="mono accent-text">+${event.points} XP</span></div>`).join("") || '<div class="dim">Начислений пока нет.</div>'}</div>`;
      } else if (tab === "team" && team) {
        const data = await api.leaderboards.team(team.id);
        content.innerHTML = `<div class="card card-pad"><div class="card-head"><div class="card-title">${escapeHtml(data.team_name)}</div></div>${data.items.map((item) => `<div class="integration-row"><span class="flex center gap-12"><span class="mono accent-text">${item.rank}</span><span><b>${escapeHtml(item.display_name)}</b><span class="meta">${escapeHtml(item.role)} · уровень ${item.level}</span></span></span><span class="mono">${item.points} XP</span></div>`).join("") || '<div class="dim">Участников пока нет.</div>'}</div>`;
      } else if (tab === "company" && company) {
        const data = await api.leaderboards.company(company.id);
        content.innerHTML = `<div class="card card-pad"><div class="card-head"><div class="card-title">${escapeHtml(data.company_name)}</div></div>${data.items.map((item) => `<div class="integration-row"><span class="flex center gap-12"><span class="mono accent-text">${item.rank}</span><span><b>${escapeHtml(item.team_name)}</b><span class="meta">${item.members} участников · ${item.completed_tasks} задач</span></span></span><span class="mono">${item.points} XP</span></div>`).join("") || '<div class="dim">Команд пока нет.</div>'}</div>`;
      } else {
        content.innerHTML = '<div class="note warn">Для этой вкладки нет доступного контекста.</div>';
      }
    } catch (error) {
      content.innerHTML = `<div class="note warn">${escapeHtml(errorMessage(error))}. Ограничение отмечено в MISSING_ENDPOINTS.md.</div>`;
    }
  }
  root.querySelectorAll("#leaderboard-tabs button").forEach((button) => button.onclick = () => show(button.dataset.tab));
  await show("me");
}

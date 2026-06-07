import { escapeHtml, setTopbar, emptyState } from "../view-utils.js";

export default async function teamsView(root) {
  setTopbar("Команды");
  const teams = window.gcCurrentUser.teams || [];
  root.querySelector("#teams-content").innerHTML = teams.length
    ? `<div class="data-grid">${teams.map((team) => `<a class="card team-card" href="/app/teams/${team.id}">
        <div class="eyebrow">${escapeHtml(team.role)}</div><h3 class="mt-8">${escapeHtml(team.name)}</h3>
        <div class="dim mt-8">${escapeHtml(team.timezone)}</div></a>`).join("")}</div>`
    : emptyState("Команд пока нет", "Команда появится здесь после создания или принятия приглашения.");
}

import { api } from "../api.js";
import { Router } from "../router.js";
import { wsOn } from "../ws.js";
import { bindForm, emptyState, errorMessage, escapeHtml, setTopbar, toast } from "../view-utils.js";

export default async function directorView(root, params) {
  const companyId = params.id || window.gcCurrentUser.companies?.[0]?.id;
  if (!companyId) return Router.navigate("/app/companies", true);
  const content = root.querySelector("#company-overview");
  let overview;
  try {
    overview = await api.companies.overview(companyId);
  } catch (error) {
    content.innerHTML = `<div class="note warn">${escapeHtml(errorMessage(error))}</div>`;
    return;
  }
  setTopbar(overview.company.name, '<button class="btn btn-primary" id="top-create-team">Создать команду</button>');
  root.querySelector("#company-title").textContent = overview.company.name;
  render(root, overview, companyId);
  document.getElementById("top-create-team").onclick = () => openTeamModal(root, companyId, overview.company.timezone);

  const reload = (payload) => {
    if (!payload?.company_id || payload.company_id === companyId) api.companies.overview(companyId).then((data) => render(root, data, companyId));
  };
  const unsubscribers = ["card_created", "card_closed", "risk_flagged"].map((event) => wsOn(event, reload));
  return () => unsubscribers.forEach((unsubscribe) => unsubscribe());
}

function render(root, overview, companyId) {
  const { totals, teams, hotspots } = overview;
  root.querySelector("#company-overview").innerHTML = `
    <div class="grid g4">
      ${stat("Команд", totals.teams)}
      ${stat("Открытых задач", totals.open_tasks)}
      ${stat("Просрочено", totals.overdue_tasks, totals.overdue_tasks ? "var(--warn)" : "")}
      ${stat("Закрыто за 7 дней", totals.completed_last_7_days)}
    </div>
    <div class="flex between center mt-24"><h2>Команды</h2><button class="btn btn-primary" id="create-team">Создать команду</button></div>
    <div class="data-grid mt-16">
      ${teams.map((team) => `<div class="card team-card">
        <a href="/app/teams/${team.id}"><h3>${escapeHtml(team.name)}</h3></a>
        <div class="grid g2 mt-16">
          <div><span class="faint">Участники</span><div class="mono mt-6">${team.members_count}</div></div>
          <div><span class="faint">Открыто</span><div class="mono mt-6">${team.open_tasks}</div></div>
          <div><span class="faint">Просрочено</span><div class="mono mt-6">${team.overdue_tasks}</div></div>
          <div><span class="faint">Закрыто за 7 дней</span><div class="mono mt-6">${team.completed_last_7_days}</div></div>
        </div>
        <div class="flex gap-8 mt-16">
          <a class="btn btn-sm btn-ghost" href="/app/teams/${team.id}">Открыть</a>
          <button class="btn btn-sm btn-ghost invite-manager" data-team="${team.id}">Пригласить менеджера</button>
        </div>
      </div>`).join("") || emptyState("Команд пока нет", "Создайте первую команду компании.")}
    </div>
    <div class="card card-pad mt-24">
      <div class="card-head"><div class="card-title">Риски</div><span class="pill ${hotspots.length ? "warn" : "ok"}"><span class="dot"></span>${hotspots.length}</span></div>
      ${hotspots.length ? hotspots.map((hotspot) => `<div class="note warn mt-8">${escapeHtml(hotspot.message)}</div>`).join("") : '<div class="dim">Активных рисков не обнаружено.</div>'}
    </div>`;
  root.querySelector("#create-team").onclick = () => openTeamModal(root, companyId, overview.company.timezone);
  root.querySelectorAll(".invite-manager").forEach((button) => {
    button.onclick = async () => {
      const team = teams.find((item) => item.id === button.dataset.team);
      const invite = await api.teams.invite({ ...team, company_id: companyId }, "manager");
      showInvite(root, invite.token);
    };
  });
}

function stat(label, value, color = "") {
  return `<div class="stat"><div class="stat-label">${label}</div><div class="stat-value mono" ${color ? `style="color:${color}"` : ""}>${value ?? 0}</div></div>`;
}

function openTeamModal(root, companyId, timezone) {
  root.insertAdjacentHTML("beforeend", `<div class="modal-backdrop" id="team-modal"><form class="modal col gap-16" id="team-form">
    <div class="flex between center"><h2>Новая команда</h2><button type="button" class="btn btn-sm btn-ghost" id="close-team">Закрыть</button></div>
    <label>Название<input class="input mt-6" name="name" minlength="2" required></label>
    <button class="btn btn-primary" type="submit">Создать</button><div id="team-error" class="alert alert-error" hidden></div>
  </form></div>`);
  root.querySelector("#close-team").onclick = () => root.querySelector("#team-modal").remove();
  bindForm(root, "#team-form", async (data) => {
    try {
      const team = await api.teams.create(companyId, data.get("name"), timezone);
      const context = await api.context();
      window.gcCurrentUser.teams = context.teams;
      toast("Команда создана");
      Router.navigate(`/app/teams/${team.id}`);
    } catch (error) {
      const element = root.querySelector("#team-error");
      element.textContent = errorMessage(error);
      element.hidden = false;
    }
  });
}

function showInvite(root, token) {
  const url = `${location.origin}/invite.html?token=${encodeURIComponent(token)}`;
  root.insertAdjacentHTML("beforeend", `<div class="modal-backdrop" id="invite-modal"><div class="modal">
    <h2>Ссылка для менеджера</h2><div class="code-msg mt-16">${escapeHtml(url)}</div>
    <div class="flex gap-8 mt-16"><button class="btn btn-primary" id="copy-invite">Копировать</button><button class="btn btn-ghost" id="close-invite">Закрыть</button></div>
  </div></div>`);
  root.querySelector("#copy-invite").onclick = async () => {
    await navigator.clipboard.writeText(url);
    toast("Ссылка скопирована");
  };
  root.querySelector("#close-invite").onclick = () => root.querySelector("#invite-modal").remove();
}

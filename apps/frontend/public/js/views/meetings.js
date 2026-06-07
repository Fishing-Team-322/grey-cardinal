import { api } from "../api.js";
import { bindForm, emptyState, errorMessage, escapeHtml, formatDate, setTopbar, toast } from "../view-utils.js";

export default async function meetingsView(root) {
  setTopbar("Созвоны");
  const teams = window.gcCurrentUser.teams || [];
  const teamSelect = root.querySelector("#meeting-team");
  teamSelect.innerHTML = teams.map((team) => `<option value="${team.id}">${escapeHtml(team.name)}</option>`).join("");
  const content = root.querySelector("#meetings-content");
  const createButton = root.querySelector("#create-meeting");
  createButton.hidden = !teams.some((team) => ["manager"].includes(team.role));

  let allMeetings = [];
  async function load() {
    content.innerHTML = '<div class="view-loading">Загрузка...</div>';
    const selected = teamSelect.value || teams[0]?.id;
    if (!selected) {
      content.innerHTML = emptyState("Созвонов пока нет", "Сначала присоединитесь к команде.");
      return;
    }
    try {
      const data = await api.meetings.list(selected);
      allMeetings = data.items || [];
      render();
    } catch (error) {
      content.innerHTML = `<div class="note warn">${escapeHtml(errorMessage(error))}</div>`;
    }
  }
  function render() {
    const status = root.querySelector("#meeting-status").value;
    const items = allMeetings.filter((meeting) => !status || meeting.state === status);
    content.innerHTML = items.length
      ? `<div class="data-grid">${items.map((meeting) => `<a class="card team-card" href="/app/meetings/${meeting.id}">
          <div class="flex between center"><span class="pill info">${escapeHtml(meeting.state)}</span><span class="mono faint">${escapeHtml(meeting.public_id)}</span></div>
          <h3 class="mt-12">${escapeHtml(meeting.title)}</h3><div class="dim mt-8">${formatDate(meeting.scheduled_at)}</div>
        </a>`).join("")}</div>`
      : emptyState("Встреч не найдено", "Измените фильтр или создайте новую встречу.");
  }
  teamSelect.onchange = load;
  root.querySelector("#meeting-status").onchange = render;
  createButton.onclick = () => openCreateModal(root, teamSelect.value, load);
  await load();
}

function openCreateModal(root, teamId, reload) {
  root.insertAdjacentHTML("beforeend", `<div class="modal-backdrop" id="meeting-modal"><form class="modal col gap-16" id="meeting-form">
    <div class="flex between center"><h2>Новая встреча</h2><button type="button" class="btn btn-sm btn-ghost" id="close-meeting">Закрыть</button></div>
    <label>Тема<input class="input mt-6" name="title" required value="Командный созвон"></label>
    <label>Дата и время<input class="input mt-6" type="datetime-local" name="scheduled_at" required></label>
    <label>Длительность, минут<input class="input mt-6" type="number" name="duration" min="10" max="240" value="60"></label>
    <button class="btn btn-primary" type="submit">Создать</button><div id="meeting-error" class="alert alert-error" hidden></div>
  </form></div>`);
  root.querySelector("#close-meeting").onclick = () => root.querySelector("#meeting-modal").remove();
  bindForm(root, "#meeting-form", async (data) => {
    try {
      await api.meetings.create(teamId, data.get("title"), new Date(data.get("scheduled_at")).toISOString(), Number(data.get("duration")));
      root.querySelector("#meeting-modal").remove();
      toast("Встреча создана");
      await reload();
    } catch (error) {
      const element = root.querySelector("#meeting-error");
      element.textContent = errorMessage(error);
      element.hidden = false;
    }
  });
}

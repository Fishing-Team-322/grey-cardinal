import { api } from "../api.js";
import { Router } from "../router.js";
import { bindForm, emptyState, errorMessage, escapeHtml, setTopbar, toast } from "../view-utils.js";

export default async function companiesView(root) {
  setTopbar("Компании");
  const content = root.querySelector("#companies-content");
  let companies;
  try {
    companies = await api.companies.list();
  } catch (error) {
    content.innerHTML = `<div class="note warn">${escapeHtml(errorMessage(error))}</div>`;
    return;
  }
  content.innerHTML = companies.length
    ? `<div class="data-grid">${companies.map((company) => `
        <a class="card team-card" href="/app/companies/${company.id}">
          <div class="eyebrow">${escapeHtml(company.role || "company")}</div>
          <h3 class="mt-8">${escapeHtml(company.name)}</h3>
          <div class="dim mt-8">${escapeHtml(company.timezone)}</div>
        </a>`).join("")}</div>`
    : emptyState(
        "Создайте первую компанию",
        "Компания объединит команды, приглашения и общие метрики.",
        '<button class="btn btn-primary mt-20" id="empty-create-company">Создать компанию</button>',
      );
  root.querySelector("#create-company").onclick = () => openModal(root);
  root.querySelector("#empty-create-company")?.addEventListener("click", () => openModal(root));
}

function openModal(root) {
  const zones = typeof Intl.supportedValuesOf === "function"
    ? Intl.supportedValuesOf("timeZone")
    : ["Europe/Moscow", "Europe/London", "Asia/Dubai"];
  const preferred = Intl.DateTimeFormat().resolvedOptions().timeZone || "Europe/Moscow";
  root.insertAdjacentHTML("beforeend", `<div class="modal-backdrop" id="company-modal">
    <form class="modal col gap-16" id="company-form">
      <div class="flex between center"><h2>Новая компания</h2><button type="button" class="btn btn-sm btn-ghost" id="close-company">Закрыть</button></div>
      <label>Название<input class="input mt-6" name="name" minlength="2" required></label>
      <label>Часовой пояс<select class="mt-6" name="timezone">${zones.map((zone) => `<option ${zone === preferred ? "selected" : ""}>${escapeHtml(zone)}</option>`).join("")}</select></label>
      <button class="btn btn-primary" type="submit">Создать</button>
      <div class="alert alert-error" id="company-error" hidden></div>
    </form>
  </div>`);
  root.querySelector("#close-company").onclick = () => root.querySelector("#company-modal").remove();
  bindForm(root, "#company-form", async (data) => {
    try {
      const company = await api.companies.create(data.get("name"), data.get("timezone"));
      toast("Компания создана");
      await refreshUserContext();
      Router.navigate(`/app/companies/${company.id}`);
    } catch (error) {
      const element = root.querySelector("#company-error");
      element.textContent = errorMessage(error);
      element.hidden = false;
    }
  });
}

async function refreshUserContext() {
  const context = await api.context();
  window.gcCurrentUser.companies = context.companies;
  window.gcCurrentUser.teams = context.teams;
}

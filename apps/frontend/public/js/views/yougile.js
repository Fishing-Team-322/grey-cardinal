import { api } from "../api.js";
import { bindForm, currentTeam, errorMessage, escapeHtml, setTopbar, toast } from "../view-utils.js";

export default async function yougileView(root) {
  setTopbar("YouGile");
  const content = root.querySelector("#yougile-content");
  const managed = window.gcCurrentUser.teams?.filter((team) => team.role === "manager") || [];
  let team = currentTeam({ teams: managed }, new URLSearchParams(location.search).get("team"));
  if (!team) {
    content.innerHTML = '<div class="note warn">Для настройки YouGile нужна роль руководителя команды.</div>';
    return;
  }
  content.insertAdjacentHTML("beforebegin", `<div class="flex gap-12 mb-16"><select id="yougile-team">${managed.map((item) => `<option value="${item.id}" ${item.id === team.id ? "selected" : ""}>${escapeHtml(item.name)}</option>`).join("")}</select></div>`);
  root.querySelector("#yougile-team").onchange = () => {
    team = managed.find((item) => item.id === root.querySelector("#yougile-team").value);
    loadStatus();
  };

  async function loadStatus() {
    content.innerHTML = '<div class="view-loading">Проверяем подключение...</div>';
    const status = await api.yougile.status(team.id).catch(() => ({ connected: false }));
    if (status.connected) renderConnected(content, team, status, loadStatus);
    else renderLogin(content, team, loadStatus);
  }
  await loadStatus();
}

function renderLogin(content, team, reload) {
  content.innerHTML = `<div class="card card-pad-lg" style="max-width:620px"><div class="eyebrow">Шаг 1 из 3</div><h2 class="mt-12">Вход в YouGile</h2>
    <form id="yougile-login" class="col gap-16 mt-20"><label>Логин<input class="input mt-6" name="login" required autocomplete="username"></label><label>Пароль<input class="input mt-6" type="password" name="password" required autocomplete="current-password"></label><button class="btn btn-primary" type="submit">Продолжить</button><div class="alert alert-error" id="yougile-error" hidden></div></form></div>`;
  bindForm(content, "#yougile-login", async (data) => {
    try {
      const result = await api.yougile.login(team.id, data.get("login"), data.get("password"));
      renderCompanies(content, team, result, reload);
    } catch (error) {
      const element = content.querySelector("#yougile-error");
      element.textContent = error.code?.error === "invalid_credentials" || error.code === "invalid_credentials" ? "Неверный логин или пароль" : errorMessage(error);
      element.hidden = false;
    }
  });
}

function renderCompanies(content, team, loginResult, reload) {
  content.innerHTML = `<div class="card card-pad-lg"><div class="eyebrow">Шаг 2 из 3</div><h2 class="mt-12">Выберите компанию</h2><div class="data-grid mt-20">${loginResult.companies.map((company) => `<button class="card team-card company-choice" data-id="${company.id}"><h3>${escapeHtml(company.name)}</h3></button>`).join("")}</div></div>`;
  content.querySelectorAll(".company-choice").forEach((button) => {
    button.onclick = () => connect(content, team, loginResult.onboarding_token, button.dataset.id, reload);
  });
  if (loginResult.companies.length === 1) connect(content, team, loginResult.onboarding_token, loginResult.companies[0].id, reload);
}

async function connect(content, team, token, companyId, reload) {
  content.innerHTML = '<div class="card card-pad-lg"><div class="eyebrow">Шаг 3 из 3</div><h2 class="mt-12">Подтягиваем рабочее пространство...</h2><div class="bar mt-20"><i style="width:65%"></i></div></div>';
  try {
    await api.yougile.connect(team.id, token, companyId);
    for (let attempt = 0; attempt < 30; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 2000));
      const status = await api.yougile.status(team.id);
      if (status.last_synced_at) {
        toast("YouGile подключён");
        await reload();
        return;
      }
    }
    await reload();
  } catch (error) {
    content.innerHTML = `<div class="note warn">${escapeHtml(errorMessage(error))}</div>`;
  }
}

function renderConnected(content, team, status, reload) {
  const stats = status.stats || {};
  content.innerHTML = `<div class="grid g4">
    <div class="stat"><div class="stat-label">Проектов</div><div class="stat-value mono">${stats.projects || 0}</div></div>
    <div class="stat"><div class="stat-label">Досок</div><div class="stat-value mono">${stats.boards || 0}</div></div>
    <div class="stat"><div class="stat-label">Колонок</div><div class="stat-value mono">${stats.columns || 0}</div></div>
    <div class="stat"><div class="stat-label">Задач</div><div class="stat-value mono">${stats.tasks || 0}</div></div>
  </div><div class="card card-pad mt-20"><div class="card-head"><div class="card-title">Подключено: ${escapeHtml(status.company?.name || team.name)}</div><span class="pill ok"><span class="dot"></span>connected</span></div><div class="dim">Последняя синхронизация: ${escapeHtml(status.last_synced_at || "выполняется")}</div><div class="flex gap-8 mt-16"><button class="btn btn-primary" id="yougile-sync">Синхронизировать</button><button class="btn btn-ghost" id="yougile-disconnect">Отключить</button></div></div>`;
  content.querySelector("#yougile-sync").onclick = async () => { await api.yougile.syncNow(team.id); toast("Синхронизация запущена"); };
  content.querySelector("#yougile-disconnect").onclick = async () => { await api.yougile.disconnect(team.id); await reload(); };
}

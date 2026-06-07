import { api } from "../api.js";
import { bindForm, currentTeam, errorMessage, escapeHtml, setTopbar, toast } from "../view-utils.js";

export default async function yougileView(root, params = {}) {
  setTopbar("YouGile");
  const content = root.querySelector("#yougile-content");
  const managed = window.gcCurrentUser.teams?.filter((team) => team.role === "manager") || [];
  let team = currentTeam(
    { teams: managed },
    params.teamId || new URLSearchParams(location.search).get("team"),
  );
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
    if (status.connected) await renderConnected(content, team, status, loadStatus);
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

async function renderConnected(content, team, status, reload) {
  const stats = status.stats || {};
  const [boards, events] = await Promise.all([
    api.yougile.mirrorBoards(team.id).catch(() => []),
    api.yougile.syncEvents(team.id).catch(() => []),
  ]);
  content.innerHTML = `<div class="grid g4">
    <div class="stat"><div class="stat-label">Проектов</div><div class="stat-value mono">${stats.projects || 0}</div></div>
    <div class="stat"><div class="stat-label">Досок</div><div class="stat-value mono">${stats.boards || 0}</div></div>
    <div class="stat"><div class="stat-label">Колонок</div><div class="stat-value mono">${stats.columns || 0}</div></div>
    <div class="stat"><div class="stat-label">Задач</div><div class="stat-value mono">${stats.tasks || 0}</div></div>
  </div>
  <section class="integration-band mt-20">
    <div class="card-head"><div><div class="card-title">Подключено: ${escapeHtml(status.company?.name || team.name)}</div><div class="dim">Последняя синхронизация: ${escapeHtml(status.last_synced_at || "выполняется")}</div></div><span class="pill ${status.sync_errors ? "err" : "ok"}"><span class="dot"></span>${status.sync_errors ? `${status.sync_errors} ошибок` : "connected"}</span></div>
    <div class="flex gap-8"><button class="btn btn-primary" id="yougile-sync">Синхронизировать</button><button class="btn btn-ghost" id="yougile-disconnect">Отключить</button></div>
  </section>
  <section class="integration-band mt-20">
    <div class="card-head"><div><div class="card-title">Рабочая доска</div><div class="dim">Выберите board и сопоставьте колонки со статусами Grey Cardinal.</div></div></div>
    <label>Board<select class="input mt-6" id="mirror-board">${boards.map((board) => `<option value="${board.id}" ${board.is_selected ? "selected" : ""}>${escapeHtml(board.name)}</option>`).join("")}</select></label>
    <div id="column-map" class="column-map mt-16"></div>
    <div class="flex gap-8 mt-16"><button class="btn btn-primary" id="save-board">Сохранить mapping</button><button class="btn btn-ghost" id="import-board">Импортировать задачи</button></div>
    <div id="import-result" class="dim mt-12"></div>
  </section>
  <section class="integration-band mt-20">
    <div class="card-title">Последние sync-события</div>
    <div class="sync-log mt-12">${events.slice(0, 20).map((event) => `<div><span class="mono">${new Date(event.created_at).toLocaleString("ru-RU")}</span><span>${escapeHtml(event.direction)} · ${escapeHtml(event.action)}</span><span class="${event.status === "error" ? "accent-text" : "dim"}">${escapeHtml(event.error || event.status)}</span></div>`).join("") || '<div class="dim">Событий пока нет.</div>'}</div>
  </section>`;
  const boardSelect = content.querySelector("#mirror-board");
  const columnMap = content.querySelector("#column-map");
  const statuses = ["", "backlog", "todo", "in_progress", "blocked", "review", "done"];
  const renderColumns = () => {
    const board = boards.find((item) => item.id === boardSelect.value);
    columnMap.innerHTML = (board?.columns || []).map((column) => `<div class="column-map-row"><span>${escapeHtml(column.name)}</span><select class="input" data-column="${column.id}">${statuses.map((value) => `<option value="${value}" ${value === (column.mapped_status || "") ? "selected" : ""}>${value || "Не сопоставлено"}</option>`).join("")}</select></div>`).join("");
  };
  boardSelect.onchange = renderColumns;
  renderColumns();
  content.querySelector("#save-board").onclick = async () => {
    const mappings = Object.fromEntries([...columnMap.querySelectorAll("[data-column]")].map((select) => [select.dataset.column, select.value || null]));
    await api.yougile.selectBoard(team.id, boardSelect.value, mappings);
    toast("Доска и колонки сохранены");
    await reload();
  };
  content.querySelector("#import-board").onclick = async () => {
    const result = await api.yougile.importBoard(team.id);
    content.querySelector("#import-result").textContent = `Импортировано: ${result.imported_tasks}, обновлено: ${result.updated_tasks}, пропущено: ${result.skipped_tasks}`;
    toast("Импорт завершён");
  };
  content.querySelector("#yougile-sync").onclick = async () => { await api.yougile.syncNow(team.id); toast("Синхронизация запущена"); };
  content.querySelector("#yougile-disconnect").onclick = async () => { await api.yougile.disconnect(team.id); await reload(); };
}

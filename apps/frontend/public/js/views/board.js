import { api } from "../api.js";
import { escapeHtml, setTopbar, toast } from "../view-utils.js";

const VIEWS = [
  ["agent", "Agent"],
  ["status", "Status"],
  ["people", "People"],
  ["risk", "Risk"],
  ["timeline", "Timeline"],
  ["source", "Source"],
];

export default async function boardView(root, params, query) {
  setTopbar("Grey Board");
  const teamId = params.teamId;
  let activeView = query.view || "agent";
  const content = root.querySelector("#board-content");
  const controls = root.querySelector("#board-views");
  const members = await api.teams.members(teamId).then((data) => data.items).catch(() => []);
  root.querySelector("#board-inbox-link").href = `/app/teams/${teamId}/ai-inbox`;
  controls.innerHTML = VIEWS.map(([key, label]) => `<button data-view="${key}" class="${key === activeView ? "active" : ""}">${label}</button>`).join("");

  async function load() {
    content.innerHTML = '<div class="view-loading">Собираем зеркало доски...</div>';
    try {
      const data = await api.greyBoard.get(teamId, activeView);
      root.querySelector("#board-summary").textContent = `${data.stats.tasks} задач · ${data.stats.overdue} просрочено · ${data.stats.sync_errors} ошибок sync`;
      const columns = data.columns || data.groups || [];
      content.innerHTML = columns.map(renderColumn).join("");
      content.querySelectorAll("[data-task]").forEach((button) => {
        button.onclick = () => openTask(root, JSON.parse(button.dataset.task), members, load);
      });
      content.querySelectorAll("[data-inbox]").forEach((button) => {
        button.onclick = () => {
          location.href = `/app/teams/${teamId}/ai-inbox`;
        };
      });
    } catch (error) {
      content.innerHTML = `<div class="note warn">${escapeHtml(error.message)}</div>`;
    }
  }

  controls.onclick = async (event) => {
    const button = event.target.closest("[data-view]");
    if (!button) return;
    activeView = button.dataset.view;
    controls.querySelectorAll("button").forEach((item) => item.classList.toggle("active", item === button));
    history.replaceState({}, "", `${location.pathname}?view=${activeView}`);
    await load();
  };
  root.querySelector("#board-refresh").onclick = load;
  await load();
}

function renderColumn(column) {
  const cards = column.cards || column.tasks || [];
  return `<section class="board-column">
    <header><span>${escapeHtml(column.title)}</span><b>${cards.length}</b></header>
    <div class="board-stack">${cards.length ? cards.map(renderCard).join("") : '<div class="board-empty">Нет задач</div>'}</div>
  </section>`;
}

function renderCard(task) {
  if (task.is_inbox) {
    return `<button class="board-task inbox-board-task" data-inbox="${task.id}">
      <div class="task-key">AI Inbox <span class="source-mark">${escapeHtml(task.kind)}</span></div>
      <div class="task-name">${escapeHtml(task.title)}</div>
      <div class="task-meta"><span>${escapeHtml(task.reason)}</span><span>${Math.round(task.confidence * 100)}%</span></div>
    </button>`;
  }
  return renderTask(task);
}

function renderTask(task) {
  const assignee = task.assignee?.telegram_username ? `@${task.assignee.telegram_username}` : task.assignee?.display_name || "Без исполнителя";
  const deadline = task.deadline ? new Date(task.deadline).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "Без дедлайна";
  const syncClass = task.sync.status === "synced" ? "ok" : task.sync.status === "error" || task.sync.status === "conflict" ? "err" : "warn";
  return `<button class="board-task" data-task='${escapeAttr(JSON.stringify(task))}'>
    <div class="task-key">${escapeHtml(task.public_id)} <span class="source-mark">${escapeHtml(task.source)}</span></div>
    <div class="task-name">${escapeHtml(task.title)}</div>
    <div class="task-meta"><span>${escapeHtml(assignee)}</span><span>${escapeHtml(deadline)}</span></div>
    <div class="task-foot"><span class="tag">${escapeHtml(task.status)}</span><span class="sync-dot ${syncClass}" title="YouGile: ${escapeHtml(task.sync.status)}"></span></div>
  </button>`;
}

function openTask(root, task, members, reload) {
  const dialog = root.querySelector("#task-dialog");
  const memberOptions = [
    '<option value="">Без исполнителя</option>',
    ...members.map((member) => `<option value="${member.id}" ${task.assignee?.id === member.id ? "selected" : ""}>${escapeHtml(member.display_name)}</option>`),
  ].join("");
  const deadlineValue = task.deadline ? new Date(task.deadline).toISOString().slice(0, 16) : "";
  dialog.innerHTML = `<form method="dialog" class="task-panel">
    <header><div><div class="task-key">${escapeHtml(task.public_id)}</div><h3>${escapeHtml(task.title)}</h3></div><button class="icon-close" aria-label="Закрыть">×</button></header>
    <dl class="task-details">
      <dt>Исполнитель</dt><dd>${escapeHtml(task.assignee?.display_name || "Без исполнителя")}</dd>
      <dt>Дедлайн</dt><dd>${task.deadline ? escapeHtml(new Date(task.deadline).toLocaleString("ru-RU")) : "Не указан"}</dd>
      <dt>Источник</dt><dd>${escapeHtml(task.source)}</dd>
      <dt>Confidence</dt><dd>${task.confidence == null ? "—" : `${Math.round(task.confidence * 100)}%`}</dd>
      <dt>Исходное сообщение</dt><dd>${escapeHtml(task.evidence?.raw_text || "—")}</dd>
      <dt>Почему назначен</dt><dd>${escapeHtml(task.agent?.identity_resolution?.source || "—")}</dd>
      <dt>YouGile</dt><dd class="${task.sync.status === "error" ? "accent-text" : ""}">${escapeHtml(task.sync.status)}${task.sync.error ? `<br>${escapeHtml(task.sync.error)}` : ""}</dd>
    </dl>
    <div class="task-edit-grid">
      <label>Исполнитель<select id="task-assignee">${memberOptions}</select></label>
      <label>Дедлайн<input id="task-deadline" type="datetime-local" value="${deadlineValue}"></label>
    </div>
    <div class="task-actions">
      <button type="button" class="btn btn-sm" data-move="in_progress">В работу</button>
      <button type="button" class="btn btn-sm" data-move="blocked">Заблокировано</button>
      <button type="button" class="btn btn-sm" data-move="review">Review</button>
      <button type="button" class="btn btn-sm btn-primary" data-move="done">Готово</button>
      <button type="button" class="btn btn-sm" id="save-task-fields">Сохранить поля</button>
      <button type="button" class="btn btn-sm btn-ghost" id="ask-status">Спросить статус</button>
      ${task.sync.external_url ? `<a class="btn btn-sm btn-ghost" href="${escapeAttr(task.sync.external_url)}" target="_blank" rel="noreferrer">Открыть в YouGile</a>` : ""}
    </div>
  </form>`;
  dialog.querySelectorAll("[data-move]").forEach((button) => {
    button.onclick = async () => {
      const result = await api.tasks.move(task.id, button.dataset.move);
      toast(result.sync_status === "error" ? "Статус сохранён, YouGile вернул ошибку" : "Статус обновлён");
      dialog.close();
      await reload();
    };
  });
  dialog.querySelector("#ask-status").onclick = async () => {
    await api.tasks.askStatus(task.id);
    toast("Запрос статуса поставлен в очередь");
  };
  dialog.querySelector("#save-task-fields").onclick = async () => {
    const assigneeId = dialog.querySelector("#task-assignee").value || null;
    const deadlineRaw = dialog.querySelector("#task-deadline").value;
    await api.tasks.assign(task.id, assigneeId);
    await api.tasks.deadline(
      task.id,
      deadlineRaw ? new Date(deadlineRaw).toISOString() : null,
    );
    toast("Поля задачи обновлены");
    dialog.close();
    await reload();
  };
  dialog.showModal();
}

function escapeAttr(value) {
  return value.replace(/&/g, "&amp;").replace(/'/g, "&#39;").replace(/</g, "&lt;");
}

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

// Views where dragging a card onto a column has a meaning.
const DROP_VIEWS = { status: "move", people: "assign" };

let currentUserId = null;

function injectStyles() {
  if (document.getElementById("gc-board-dnd-styles")) return;
  const style = document.createElement("style");
  style.id = "gc-board-dnd-styles";
  style.textContent = `
  .board-toolbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:8px 0}
  .board-toolbar input[type=search]{flex:1;min-width:160px;padding:7px 10px;border-radius:8px;
    border:1px solid var(--line,#232329);background:var(--card,#16161a);color:inherit}
  .board-toolbar .chip{padding:6px 10px;border-radius:8px;border:1px solid var(--line,#232329);
    background:var(--card,#16161a);cursor:pointer;font-size:13px;user-select:none}
  .board-toolbar .chip.on{border-color:#ff003c;color:#fff;background:#1c1216}
  .board-task{position:relative;cursor:grab}
  .board-task[draggable=true]:active{cursor:grabbing}
  .board-task.dragging{opacity:.45}
  .board-task.prio-overdue{border-left:3px solid #ff003c}
  .board-task.prio-soon{border-left:3px solid #f1c40f}
  .board-task.prio-high{border-left:3px solid #ff7a00}
  .board-column.drop-target{outline:2px dashed #ff003c;outline-offset:2px;border-radius:10px}
  .board-column.collapsed .board-stack{display:none}
  .board-column header{cursor:default;display:flex;align-items:center;gap:6px}
  .board-column header .col-collapse{margin-left:auto;cursor:pointer;opacity:.6}
  .card-copy{position:absolute;top:6px;right:6px;opacity:0;border:none;background:transparent;
    cursor:pointer;font-size:12px;color:var(--muted,#8a8a93)}
  .board-task:hover .card-copy{opacity:.8}
  .board-hidden{display:none!important}
  .task-comments{margin-top:14px;border-top:1px solid var(--line,#232329);padding-top:10px}
  .task-comments h4{margin:0 0 8px}
  .comments-list{display:flex;flex-direction:column;gap:8px;max-height:260px;overflow:auto;margin-bottom:8px}
  .comment-item{background:var(--card,#16161a);border:1px solid var(--line,#232329);border-radius:8px;padding:7px 10px}
  .comment-head{display:flex;justify-content:space-between;gap:8px;font-size:12px;color:var(--muted,#8a8a93);margin-bottom:3px}
  .comment-body{white-space:pre-wrap;word-break:break-word}
  .comment-form{display:flex;gap:8px}
  .comment-form input{flex:1;padding:8px 10px;border-radius:8px;border:1px solid var(--line,#232329);background:var(--card,#16161a);color:inherit}
  `;
  document.head.appendChild(style);
}

export default async function boardView(root, params, query) {
  injectStyles();
  setTopbar("Grey Board");
  const teamId = params.teamId;
  let activeView = query.view || "agent";
  let search = "";
  let onlyMine = false;
  const collapsed = new Set();
  const content = root.querySelector("#board-content");
  const controls = root.querySelector("#board-views");
  try { currentUserId = window.gcCurrentUser?.id || null; } catch { currentUserId = null; }
  const members = await api.teams.members(teamId).then((data) => data.items).catch(() => []);
  root.querySelector("#board-inbox-link").href = `/app/teams/${teamId}/ai-inbox`;
  controls.innerHTML = VIEWS.map(([key, label]) => `<button data-view="${key}" class="${key === activeView ? "active" : ""}">${label}</button>`).join("");

  // Toolbar: live search + "only mine" + drag hint.
  let toolbar = root.querySelector("#board-toolbar");
  if (!toolbar) {
    toolbar = document.createElement("div");
    toolbar.id = "board-toolbar";
    toolbar.className = "board-toolbar";
    toolbar.innerHTML = `
      <input type="search" id="board-search" placeholder="Поиск по задачам ( / )">
      <span class="chip" id="board-mine">👤 Только мои</span>
      <span class="chip" id="board-drag-hint" title="Перетаскивайте карточки между колонками">🖱️ drag-n-drop</span>`;
    content.parentNode.insertBefore(toolbar, content);
    toolbar.querySelector("#board-search").addEventListener("input", (e) => { search = e.target.value.trim().toLowerCase(); applyFilter(); });
    toolbar.querySelector("#board-mine").addEventListener("click", (e) => { onlyMine = !onlyMine; e.target.classList.toggle("on", onlyMine); applyFilter(); });
    document.addEventListener("keydown", (e) => {
      if (e.key === "/" && document.activeElement?.id !== "board-search") {
        const el = root.querySelector("#board-search"); if (el) { e.preventDefault(); el.focus(); }
      }
    });
  }

  function applyFilter() {
    content.querySelectorAll(".board-task").forEach((card) => {
      const text = (card.dataset.search || "").toLowerCase();
      const mine = card.dataset.mine === "1";
      const hit = (!search || text.includes(search)) && (!onlyMine || mine);
      card.classList.toggle("board-hidden", !hit);
    });
  }

  async function load() {
    content.innerHTML = '<div class="view-loading">Собираем зеркало доски...</div>';
    try {
      const data = await api.greyBoard.get(teamId, activeView);
      root.querySelector("#board-summary").textContent = `${data.stats.tasks} задач · ${data.stats.overdue} просрочено · ${data.stats.sync_errors} ошибок sync`;
      const columns = data.columns || data.groups || [];
      content.innerHTML = columns.map((c) => renderColumn(c, collapsed)).join("");
      bindCards();
      bindDnd();
      applyFilter();
    } catch (error) {
      content.innerHTML = `<div class="note warn">${escapeHtml(error.message)}</div>`;
    }
  }

  function bindCards() {
    content.querySelectorAll("[data-task]").forEach((card) => {
      card.addEventListener("click", (e) => {
        if (e.target.closest(".card-copy")) return;
        openTask(root, JSON.parse(card.dataset.task), members, load);
      });
    });
    content.querySelectorAll(".card-copy").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        navigator.clipboard?.writeText(btn.dataset.copy || "").then(() => toast("ID скопирован"));
      });
    });
    content.querySelectorAll("[data-inbox]").forEach((button) => {
      button.addEventListener("click", () => { location.href = `/app/teams/${teamId}/ai-inbox`; });
    });
    content.querySelectorAll(".col-collapse").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const col = btn.closest(".board-column");
        const key = col.dataset.colKey;
        col.classList.toggle("collapsed");
        if (col.classList.contains("collapsed")) collapsed.add(key); else collapsed.delete(key);
      });
    });
  }

  function bindDnd() {
    const mode = DROP_VIEWS[activeView];
    if (!mode) return;
    content.querySelectorAll(".board-task[data-task-id]").forEach((card) => {
      card.setAttribute("draggable", "true");
      card.addEventListener("dragstart", (e) => {
        card.classList.add("dragging");
        e.dataTransfer.setData("text/plain", card.dataset.taskId);
        e.dataTransfer.effectAllowed = "move";
      });
      card.addEventListener("dragend", () => card.classList.remove("dragging"));
    });
    content.querySelectorAll(".board-column[data-col-key]").forEach((col) => {
      col.addEventListener("dragover", (e) => { e.preventDefault(); col.classList.add("drop-target"); });
      col.addEventListener("dragleave", () => col.classList.remove("drop-target"));
      col.addEventListener("drop", async (e) => {
        e.preventDefault();
        col.classList.remove("drop-target");
        const taskId = e.dataTransfer.getData("text/plain");
        const target = col.dataset.colKey;
        const dragged = content.querySelector(`.board-task[data-task-id="${taskId}"]`);
        if (!dragged || dragged.dataset.colKey === target) return;
        // optimistic move
        col.querySelector(".board-stack")?.appendChild(dragged);
        dragged.dataset.colKey = target;
        try {
          if (mode === "move") {
            const res = await api.tasks.move(taskId, target);
            toast(res.sync_status === "error" ? "Статус сохранён, YouGile вернул ошибку" : "Статус обновлён");
          } else {
            const assignee = target === "unassigned" ? null : target;
            await api.tasks.assign(taskId, assignee);
            toast("Исполнитель обновлён");
          }
        } catch (err) {
          toast("Не удалось: " + (err.message || "ошибка"));
          await load();
        }
      });
    });
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

function cardPriorityClass(task) {
  if (task.risk?.overdue) return "prio-overdue";
  if (task.risk?.due_soon) return "prio-soon";
  if (task.priority === "high" || task.priority === "urgent") return "prio-high";
  return "";
}

function renderColumn(column, collapsed) {
  const cards = column.cards || column.tasks || [];
  const key = column.id || "";
  const overdue = cards.filter((c) => c.risk?.overdue).length;
  const isCollapsed = collapsed.has(key);
  return `<section class="board-column ${isCollapsed ? "collapsed" : ""}" data-col-key="${escapeAttr(key)}">
    <header><span>${escapeHtml(column.title)}</span><b>${cards.length}</b>${overdue ? `<span class="tag" title="просрочено">⏰${overdue}</span>` : ""}<span class="col-collapse" title="Свернуть">▾</span></header>
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
  const mine = currentUserId && task.assignee?.id === currentUserId ? "1" : "0";
  const searchText = `${task.public_id} ${task.title} ${assignee} ${task.status}`;
  return `<div class="board-task ${cardPriorityClass(task)}" data-task-id="${escapeAttr(task.id)}" data-col-key="${escapeAttr(task.status)}" data-mine="${mine}" data-search="${escapeAttr(searchText)}" data-task='${escapeAttr(JSON.stringify(task))}'>
    <button class="card-copy" data-copy="${escapeAttr(task.public_id)}" title="Скопировать ID">📋</button>
    <div class="task-key">${escapeHtml(task.public_id)} <span class="source-mark">${escapeHtml(task.source)}</span></div>
    <div class="task-name">${escapeHtml(task.title)}</div>
    <div class="task-meta"><span>${escapeHtml(assignee)}</span><span>${escapeHtml(deadline)}</span></div>
    <div class="task-foot"><span class="tag">${escapeHtml(task.status)}</span><span class="sync-dot ${syncClass}" title="YouGile: ${escapeHtml(task.sync.status)}"></span></div>
  </div>`;
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
    <section class="task-comments" id="task-comments">
      <h4>💬 Комментарии</h4>
      <div id="comments-list" class="comments-list"><div class="view-loading">Загрузка…</div></div>
      <form id="comment-form" class="comment-form">
        <input id="comment-input" type="text" placeholder="Написать комментарий…" autocomplete="off">
        <button type="submit" class="btn btn-sm btn-primary">Отправить</button>
      </form>
    </section>
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
    await api.tasks.deadline(task.id, deadlineRaw ? new Date(deadlineRaw).toISOString() : null);
    toast("Поля задачи обновлены");
    dialog.close();
    await reload();
  };
  const closeBtn = dialog.querySelector(".icon-close");
  if (closeBtn) closeBtn.onclick = () => dialog.close();
  loadComments(dialog, task);
  dialog.showModal();
}

async function loadComments(dialog, task) {
  const list = dialog.querySelector("#comments-list");
  const form = dialog.querySelector("#comment-form");
  const input = dialog.querySelector("#comment-input");
  async function refresh() {
    try {
      const data = await api.tasks.comments(task.id);
      const items = data.items || [];
      list.innerHTML = items.length
        ? items.map((c) => `<div class="comment-item"><div class="comment-head"><b>${escapeHtml(c.author_name || "—")}</b><span>${escapeHtml(new Date(c.created_at).toLocaleString("ru-RU"))}</span></div><div class="comment-body">${escapeHtml(c.body)}</div></div>`).join("")
        : '<div class="board-empty">Пока нет комментариев</div>';
    } catch (e) {
      list.innerHTML = `<div class="note warn">${escapeHtml(e.message)}</div>`;
    }
  }
  form.onsubmit = async (e) => {
    e.preventDefault();
    const body = input.value.trim();
    if (!body) return;
    input.value = "";
    try { await api.tasks.addComment(task.id, body); await refresh(); }
    catch (err) { toast("Не удалось добавить: " + (err.message || "ошибка")); input.value = body; }
  };
  await refresh();
}

function escapeAttr(value) {
  return String(value).replace(/&/g, "&amp;").replace(/'/g, "&#39;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
}

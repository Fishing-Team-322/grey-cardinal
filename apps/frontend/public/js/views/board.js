import { api } from "../api.js";
import { escapeHtml, setTopbar, toast } from "../view-utils.js";

const VIEWS = [
  ["status", "Статусы"],
  ["agent", "Agent"],
  ["people", "Люди"],
  ["risk", "Риски"],
  ["timeline", "Сроки"],
  ["source", "Источник"],
];

// Jira-like Russian status labels. Only DB-allowed statuses (ck_task_status):
// todo, in_progress, blocked, review, done, cancelled.
const STATUS_RU = {
  todo: "К выполнению",
  in_progress: "В работе",
  review: "На проверке",
  blocked: "Заблокировано",
  done: "Готово",
  cancelled: "Отменено",
};
const STATUS_ORDER = ["todo", "in_progress", "review", "blocked", "done"];
const ALLOWED_STATUSES = new Set(["todo", "in_progress", "review", "blocked", "done", "cancelled"]);

// Views where dragging a card onto a column means something.
const DROP_VIEWS = { status: "move", people: "assign" };

let currentUserId = null;

function injectStyles() {
  if (document.getElementById("gc-board-v2")) return;
  const style = document.createElement("style");
  style.id = "gc-board-v2";
  style.textContent = `
  .grey-board{display:flex;gap:14px;overflow-x:auto;padding-bottom:12px;align-items:flex-start}
  .board-column{background:#121216;border:1px solid #232329;border-radius:14px;min-width:280px;max-width:300px;
    flex:0 0 auto;display:flex;flex-direction:column;max-height:calc(100vh - 220px)}
  .board-column>header{display:flex;align-items:center;gap:8px;padding:12px 14px;border-bottom:1px solid #1e1e24;
    font-weight:600;position:sticky;top:0;background:#121216;border-radius:14px 14px 0 0;z-index:1}
  .board-column>header .count{margin-left:auto;background:#222;border-radius:20px;padding:1px 9px;font-size:12px;color:#aaa}
  .board-column>header .col-collapse{cursor:pointer;opacity:.5;font-size:12px}
  .board-column>header .col-dot{width:9px;height:9px;border-radius:50%}
  .board-stack{padding:10px;display:flex;flex-direction:column;gap:10px;overflow-y:auto}
  .board-column.collapsed .board-stack{display:none}
  .board-empty{color:#6a6a73;font-size:13px;text-align:center;padding:18px 0}
  .gc-card{position:relative;background:#1a1a1f;border:1px solid #26262e;border-left:3px solid #3a3a44;
    border-radius:12px;padding:11px 12px;cursor:grab;transition:transform .08s,border-color .15s,box-shadow .15s}
  .gc-card:hover{border-color:#3a3a46;box-shadow:0 4px 18px rgba(0,0,0,.35);transform:translateY(-1px)}
  .gc-card:active{cursor:grabbing}
  .gc-card.dragging{opacity:.4}
  .gc-card.p-overdue{border-left-color:#ff003c}
  .gc-card.p-soon{border-left-color:#f1c40f}
  .gc-card.p-high{border-left-color:#ff7a00}
  .gc-card .c-top{display:flex;align-items:center;gap:8px;font-size:11px;color:#7d7d87;margin-bottom:5px}
  .gc-card .c-pid{color:#ff003c;font-weight:700;letter-spacing:.3px}
  .gc-card .c-src{margin-left:auto;text-transform:uppercase;font-size:9.5px;opacity:.6}
  .gc-card .c-title{font-weight:600;line-height:1.3;margin-bottom:9px;word-break:break-word}
  .gc-card .c-foot{display:flex;align-items:center;gap:8px}
  .gc-card .c-ava{width:22px;height:22px;border-radius:50%;background:#2a2a33;color:#ddd;font-size:10px;
    display:flex;align-items:center;justify-content:center;font-weight:700;flex-shrink:0}
  .gc-card .c-ava.none{background:transparent;border:1px dashed #3a3a44;color:#6a6a73}
  .gc-card .c-dl{margin-left:auto;font-size:11.5px;color:#9a9aa3;display:flex;align-items:center;gap:4px}
  .gc-card .c-dl.overdue{color:#ff5470}
  .gc-card .sync-dot{width:7px;height:7px;border-radius:50%}
  .gc-card .sync-dot.ok{background:#2ecc71}.gc-card .sync-dot.warn{background:#f1c40f}.gc-card .sync-dot.err{background:#ff003c}
  .gc-card .c-copy{position:absolute;top:8px;right:8px;border:none;background:transparent;cursor:pointer;
    opacity:0;font-size:12px;color:#6a6a73}
  .gc-card:hover .c-copy{opacity:.8}
  .board-column.drop-target{outline:2px dashed #ff003c;outline-offset:-2px}
  .board-toolbar2{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:10px 0}
  .board-toolbar2 input[type=search]{flex:1;min-width:160px;padding:8px 11px;border-radius:9px;border:1px solid #232329;background:#16161a;color:inherit}
  .board-toolbar2 .chip{padding:7px 11px;border-radius:9px;border:1px solid #232329;background:#16161a;cursor:pointer;font-size:13px;user-select:none}
  .board-toolbar2 .chip.on{border-color:#ff003c;color:#fff;background:#1c1216}
  .board-hidden{display:none!important}
  /* Centered, scrollable detail panel */
  dialog.task-dialog{position:fixed;inset:0;margin:auto;width:min(720px,calc(100vw - 24px));
    max-height:90vh;overflow:auto;border:1px solid #26262e;border-radius:16px;background:#141418;color:#ececf0;padding:0}
  dialog.task-dialog::backdrop{background:rgba(0,0,0,.72)}
  .task-panel{padding:22px}
  .tp-status-row{display:flex;gap:10px;align-items:center;margin:14px 0}
  .tp-status-row select,.task-edit-grid select,.task-edit-grid input{padding:8px 10px;border-radius:9px;border:1px solid #2a2a33;background:#1a1a1f;color:inherit}
  .task-edit-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:8px 0 14px}
  .task-edit-grid label{display:flex;flex-direction:column;gap:5px;font-size:12.5px;color:#9a9aa3}
  .task-details{display:grid;grid-template-columns:150px minmax(0,1fr);gap:8px 12px;margin:16px 0 0;padding:14px 0;border-block:1px solid #232329;font-size:13px}
  .task-details dt{color:#9a9aa3}
  .task-details dd{min-width:0;overflow-wrap:anywhere;white-space:pre-wrap}
  .task-comments{margin-top:16px;border-top:1px solid #232329;padding-top:12px}
  .task-comments h4{margin:0 0 10px}
  .comments-list{display:flex;flex-direction:column;gap:8px;max-height:280px;overflow:auto;margin-bottom:10px}
  .comment-item{background:#1a1a1f;border:1px solid #26262e;border-radius:10px;padding:8px 11px}
  .comment-head{display:flex;justify-content:space-between;gap:8px;font-size:12px;color:#8a8a93;margin-bottom:3px}
  .comment-body{white-space:pre-wrap;word-break:break-word}
  .comment-form{display:flex;gap:8px}
  .comment-form input{flex:1;padding:9px 11px;border-radius:9px;border:1px solid #2a2a33;background:#1a1a1f;color:inherit}
  `;
  document.head.appendChild(style);
}

function initials(name) {
  if (!name) return "";
  return name.trim().split(/\s+/).slice(0, 2).map((w) => w[0]?.toUpperCase() || "").join("");
}
function fmtDeadline(iso) {
  if (!iso) return "";
  const d = new Date(iso), now = new Date();
  const days = Math.round((new Date(iso).setHours(0, 0, 0, 0) - new Date().setHours(0, 0, 0, 0)) / 864e5);
  const t = d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  if (days === 0) return "сегодня " + t;
  if (days === 1) return "завтра " + t;
  if (days === -1) return "вчера " + t;
  return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" }) + " " + t;
}

export default async function boardView(root, params, query) {
  injectStyles();
  setTopbar("Доска");
  const teamId = params.teamId;
  let activeView = query.view || "status";
  let search = "";
  let onlyMine = false;
  const collapsed = new Set();
  const content = root.querySelector("#board-content");
  const controls = root.querySelector("#board-views");
  try { currentUserId = window.gcCurrentUser?.id || null; } catch { currentUserId = null; }
  const members = await api.teams.members(teamId).then((d) => d.items).catch(() => []);
  root.querySelector("#board-inbox-link").href = `/app/teams/${teamId}/ai-inbox`;
  controls.innerHTML = VIEWS.map(([k, label]) => `<button data-view="${k}" class="${k === activeView ? "active" : ""}">${label}</button>`).join("");

  let toolbar = root.querySelector("#board-toolbar2");
  if (!toolbar) {
    toolbar = document.createElement("div");
    toolbar.id = "board-toolbar2";
    toolbar.className = "board-toolbar2";
    toolbar.innerHTML = `<input type="search" id="board-search" placeholder="Поиск ( / )">
      <span class="chip" id="board-mine">👤 Только мои</span>
      <span class="chip" title="Перетаскивайте карточки мышкой">🖱️ drag-n-drop</span>`;
    content.parentNode.insertBefore(toolbar, content);
    toolbar.querySelector("#board-search").addEventListener("input", (e) => { search = e.target.value.trim().toLowerCase(); applyFilter(); });
    toolbar.querySelector("#board-mine").addEventListener("click", (e) => { onlyMine = !onlyMine; e.currentTarget.classList.toggle("on", onlyMine); applyFilter(); });
    document.addEventListener("keydown", (e) => {
      if (e.key === "/" && document.activeElement?.id !== "board-search") {
        const el = root.querySelector("#board-search"); if (el) { e.preventDefault(); el.focus(); }
      }
    });
  }

  function applyFilter() {
    content.querySelectorAll(".gc-card").forEach((card) => {
      const hit = (!search || (card.dataset.search || "").includes(search)) && (!onlyMine || card.dataset.mine === "1");
      card.classList.toggle("board-hidden", !hit);
    });
  }

  async function load() {
    content.innerHTML = '<div class="view-loading">Собираем доску…</div>';
    try {
      const data = await api.greyBoard.get(teamId, activeView);
      root.querySelector("#board-summary").textContent = `${data.stats.tasks} задач · ${data.stats.overdue} просрочено · ${data.stats.sync_errors} ошибок sync`;
      const columns = data.columns || data.groups || [];
      content.innerHTML = columns.map((c) => renderColumn(c, collapsed, activeView)).join("");
      bindCards();
      bindDnd();
      applyFilter();
    } catch (error) {
      content.innerHTML = `<div class="note warn">${escapeHtml(error.message)}</div>`;
    }
  }

  function bindCards() {
    content.querySelectorAll(".gc-card[data-task]").forEach((card) => {
      card.addEventListener("click", (e) => {
        if (e.target.closest(".c-copy")) return;
        openTask(root, JSON.parse(card.dataset.task), members, load);
      });
    });
    content.querySelectorAll(".gc-card[data-inbox]").forEach((card) => {
      card.addEventListener("click", () => { location.href = `/app/teams/${teamId}/ai-inbox`; });
    });
    content.querySelectorAll(".c-copy").forEach((btn) => {
      btn.addEventListener("click", (e) => { e.stopPropagation(); navigator.clipboard?.writeText(btn.dataset.copy || "").then(() => toast("ID скопирован")); });
    });
    content.querySelectorAll(".col-collapse").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const col = btn.closest(".board-column");
        col.classList.toggle("collapsed");
        const key = col.dataset.colKey;
        if (col.classList.contains("collapsed")) collapsed.add(key); else collapsed.delete(key);
      });
    });
  }

  function bindDnd() {
    const mode = DROP_VIEWS[activeView];
    if (!mode) return;
    content.querySelectorAll(".gc-card[data-task-id]").forEach((card) => {
      card.setAttribute("draggable", "true");
      card.addEventListener("dragstart", (e) => {
        card.classList.add("dragging");
        e.dataTransfer.setData("text/plain", card.dataset.taskId);
        e.dataTransfer.effectAllowed = "move";
      });
      card.addEventListener("dragend", () => card.classList.remove("dragging"));
    });
    content.querySelectorAll(".board-column[data-col-key]").forEach((col) => {
      col.addEventListener("dragover", (e) => { e.preventDefault(); e.dataTransfer.dropEffect = "move"; col.classList.add("drop-target"); });
      col.addEventListener("dragleave", () => col.classList.remove("drop-target"));
      col.addEventListener("drop", async (e) => {
        e.preventDefault();
        col.classList.remove("drop-target");
        const taskId = e.dataTransfer.getData("text/plain");
        const target = col.dataset.colKey;
        const dragged = content.querySelector(`.gc-card[data-task-id="${taskId}"]`);
        if (!dragged || dragged.dataset.colKey === target) return;
        if (mode === "move" && !ALLOWED_STATUSES.has(target)) {
          toast("Нельзя перенести в этот статус");
          await load();
          return;
        }
        col.querySelector(".board-stack")?.appendChild(dragged);
        dragged.dataset.colKey = target;
        try {
          if (mode === "move") {
            const res = await api.tasks.move(taskId, target);
            toast(res.sync_status === "error" ? "Статус сохранён, YouGile вернул ошибку" : "Готово");
          } else {
            await api.tasks.assign(taskId, target === "unassigned" ? null : target);
            toast("Исполнитель обновлён");
          }
        } catch (err) { toast("Не удалось: " + (err.message || "ошибка")); await load(); }
      });
    });
  }

  controls.onclick = async (event) => {
    const button = event.target.closest("[data-view]");
    if (!button) return;
    activeView = button.dataset.view;
    controls.querySelectorAll("button").forEach((i) => i.classList.toggle("active", i === button));
    history.replaceState({}, "", `${location.pathname}?view=${activeView}`);
    await load();
  };
  root.querySelector("#board-refresh").onclick = load;
  await load();
}

const COL_DOT = { backlog: "#6a6a73", todo: "#3a7afe", in_progress: "#f1c40f", blocked: "#ff003c", review: "#a06bff", done: "#2ecc71" };

function renderColumn(column, collapsed, view) {
  const cards = column.cards || column.tasks || [];
  const key = column.id || "";
  const title = view === "status" && STATUS_RU[key] ? STATUS_RU[key] : column.title;
  const overdue = cards.filter((c) => c.risk?.overdue).length;
  const dot = view === "status" && COL_DOT[key] ? `<span class="col-dot" style="background:${COL_DOT[key]}"></span>` : "";
  const droppable = DROP_VIEWS[view] ? `data-col-key="${escapeAttr(key)}"` : "";
  return `<section class="board-column ${collapsed.has(key) ? "collapsed" : ""}" ${droppable}>
    <header>${dot}<span>${escapeHtml(title)}</span><span class="count">${cards.length}</span>${overdue ? `<span class="count" title="просрочено">⏰${overdue}</span>` : ""}<span class="col-collapse" title="Свернуть">▾</span></header>
    <div class="board-stack">${cards.length ? cards.map((card) => renderCard(card, key)).join("") : '<div class="board-empty">Пусто</div>'}</div>
  </section>`;
}

function renderCard(task, columnKey = null) {
  if (task.is_inbox) {
    return `<div class="gc-card" data-inbox="${escapeAttr(task.id)}">
      <div class="c-top"><span class="c-pid">AI Inbox</span><span class="c-src">${escapeHtml(task.kind)}</span></div>
      <div class="c-title">${escapeHtml(task.title)}</div>
      <div class="c-foot"><span style="font-size:11.5px;color:#9a9aa3">${escapeHtml(task.reason)}</span><span class="c-dl">${Math.round(task.confidence * 100)}%</span></div>
    </div>`;
  }
  const aName = task.assignee?.display_name || "";
  const ava = aName ? `<span class="c-ava" title="${escapeAttr(aName)}">${escapeHtml(initials(aName))}</span>` : `<span class="c-ava none" title="Без исполнителя">∅</span>`;
  const dl = task.deadline ? `<span class="c-dl ${task.risk?.overdue ? "overdue" : ""}">⏰ ${escapeHtml(fmtDeadline(task.deadline))}</span>` : "";
  const sc = task.sync.status === "synced" ? "ok" : (task.sync.status === "error" || task.sync.status === "conflict") ? "err" : "warn";
  const prio = task.risk?.overdue ? "p-overdue" : task.risk?.due_soon ? "p-soon" : (task.priority === "high" || task.priority === "urgent") ? "p-high" : "";
  const mine = currentUserId && task.assignee?.id === currentUserId ? "1" : "0";
  const searchText = `${task.public_id} ${task.title} ${aName} ${task.status}`.toLowerCase();
  return `<div class="gc-card ${prio}" data-task-id="${escapeAttr(task.id)}" data-col-key="${escapeAttr(columnKey || task.status)}" data-mine="${mine}" data-search="${escapeAttr(searchText)}" data-task='${escapeAttr(JSON.stringify(task))}'>
    <button class="c-copy" data-copy="${escapeAttr(task.public_id)}" title="Скопировать ID">📋</button>
    <div class="c-top"><span class="c-pid">${escapeHtml(task.public_id)}</span><span class="c-src">${escapeHtml(task.source)}</span></div>
    <div class="c-title">${escapeHtml(task.title)}</div>
    <div class="c-foot">${ava}${dl}<span class="sync-dot ${sc}" title="YouGile: ${escapeHtml(task.sync.status)}"></span></div>
  </div>`;
}

function openTask(root, task, members, reload) {
  const dialog = root.querySelector("#task-dialog");
  dialog.classList.add("task-dialog");
  const memberOptions = [
    '<option value="">Без исполнителя</option>',
    ...members.map((mm) => `<option value="${mm.id}" ${task.assignee?.id === mm.id ? "selected" : ""}>${escapeHtml(mm.display_name)}</option>`),
  ].join("");
  const statusOptions = STATUS_ORDER.map((s) => `<option value="${s}" ${task.status === s ? "selected" : ""}>${STATUS_RU[s]}</option>`).join("");
  const deadlineValue = task.deadline ? new Date(task.deadline).toISOString().slice(0, 16) : "";
  dialog.innerHTML = `<div class="task-panel">
    <header><div><div class="c-pid" style="font-size:12px">${escapeHtml(task.public_id)}</div><h3 style="margin:6px 0 0">${escapeHtml(task.title)}</h3></div><button class="icon-close" aria-label="Закрыть" type="button">×</button></header>
    <div class="tp-status-row">
      <label style="color:#9a9aa3;font-size:13px">Статус</label>
      <select id="task-status">${statusOptions}</select>
      <button type="button" class="btn btn-sm btn-primary" id="apply-status">Применить</button>
    </div>
    <div class="task-edit-grid">
      <label>Исполнитель<select id="task-assignee">${memberOptions}</select></label>
      <label>Дедлайн<input id="task-deadline" type="datetime-local" value="${deadlineValue}"></label>
    </div>
    <div class="task-actions" style="display:flex;gap:8px;flex-wrap:wrap">
      <button type="button" class="btn btn-sm" id="save-task-fields">Сохранить поля</button>
      <button type="button" class="btn btn-sm btn-ghost" id="ask-status">Спросить статус</button>
      ${task.sync.external_url ? `<a class="btn btn-sm btn-ghost" href="${escapeAttr(task.sync.external_url)}" target="_blank" rel="noreferrer">Открыть в YouGile</a>` : ""}
    </div>
    <dl class="task-details">
      <dt>Источник</dt><dd>${escapeHtml(task.source)}</dd>
      <dt>Confidence</dt><dd>${task.confidence == null ? "—" : `${Math.round(task.confidence * 100)}%`}</dd>
      <dt>Исходное сообщение</dt><dd>${escapeHtml(task.evidence?.raw_text || "—")}</dd>
      <dt>YouGile</dt><dd class="${task.sync.status === "error" ? "accent-text" : ""}">${escapeHtml(task.sync.status)}${task.sync.error ? `<br>${escapeHtml(task.sync.error)}` : ""}</dd>
    </dl>
    <section class="task-comments">
      <h4>💬 Комментарии</h4>
      <div id="comments-list" class="comments-list"><div class="view-loading">Загрузка…</div></div>
      <form id="comment-form" class="comment-form"><input id="comment-input" type="text" placeholder="Написать комментарий…" autocomplete="off"><button type="submit" class="btn btn-sm btn-primary">Отправить</button></form>
    </section>
  </div>`;

  dialog.querySelector(".icon-close").onclick = () => dialog.close();
  dialog.querySelector("#apply-status").onclick = async () => {
    const next = dialog.querySelector("#task-status").value;
    if (next === task.status) { toast("Статус не изменился"); return; }
    try {
      const res = await api.tasks.move(task.id, next);
      toast(res.sync_status === "error" ? "Статус сохранён, YouGile вернул ошибку" : "Статус обновлён");
      dialog.close(); await reload();
    } catch (e) { toast("Ошибка: " + (e.message || "")); }
  };
  dialog.querySelector("#ask-status").onclick = async () => { await api.tasks.askStatus(task.id); toast("Запрос статуса поставлен в очередь"); };
  dialog.querySelector("#save-task-fields").onclick = async () => {
    const assigneeId = dialog.querySelector("#task-assignee").value || null;
    const deadlineRaw = dialog.querySelector("#task-deadline").value;
    try {
      await api.tasks.assign(task.id, assigneeId);
      await api.tasks.deadline(task.id, deadlineRaw ? new Date(deadlineRaw).toISOString() : null);
      toast("Поля обновлены"); dialog.close(); await reload();
    } catch (e) { toast("Ошибка: " + (e.message || "")); }
  };
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
      list.innerHTML = `<div class="note warn">Не загрузить: ${escapeHtml(e.message || "ошибка")}</div>`;
    }
  }
  if (form) form.onsubmit = async (e) => {
    e.preventDefault();
    const body = input.value.trim();
    if (!body) return;
    input.value = "";
    try { await api.tasks.addComment(task.id, body); await refresh(); }
    catch (err) { toast("Не отправить: " + (err.message || "ошибка")); input.value = body; }
  };
  await refresh();
}

function escapeAttr(value) {
  return String(value).replace(/&/g, "&amp;").replace(/'/g, "&#39;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
}

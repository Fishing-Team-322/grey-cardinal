import { api } from "../api.js";
import { escapeHtml, formatDate, setTopbar, toast } from "../view-utils.js";

const STATUS_LABEL = {
  pending: "Ожидает",
  approved: "Принята",
  rejected: "Отклонена",
};

const STATUS_TABS = [
  ["pending", "Ожидают"],
  ["approved", "Принятые"],
  ["rejected", "Отклонённые"],
  ["all", "Все"],
];

const KIND_LABEL = {
  needs_assignee: "Нужен исполнитель",
  task_candidate_uncertain: "Черновик задачи",
  task_candidate: "Кандидат в задачи",
  low_confidence: "Низкая уверенность",
  duplicate: "Возможный дубль",
};

const REASON_LABEL = {
  low_confidence_parse: "Модель не уверена в разборе",
  windows_agent_proposal: "Из заметки Windows-агента",
  ambiguous_assignee: "Неоднозначный исполнитель",
};

const SOURCE_META = {
  telegram: { label: "Telegram", icon: "tg" },
  daemon_proposal: { label: "Windows-агент", icon: "daemon" },
  windows_agent: { label: "Windows-агент", icon: "daemon" },
  meeting_transcript: { label: "Из созвона", icon: "meet" },
};

const HIGH_CONFIDENCE = 0.85;

const STYLE_ID = "gc-inbox-v2";

function injectStyles() {
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
  .inbox-v2{display:flex;flex-direction:column;gap:18px}
  .inbox-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
  .inbox-stat{padding:14px 16px;border:1px solid var(--line);border-radius:var(--r);background:var(--surface);display:flex;flex-direction:column;gap:4px}
  .inbox-stat b{font-size:24px;line-height:1;font-weight:700}
  .inbox-stat span{font-size:12px;color:var(--text-faint);text-transform:uppercase;letter-spacing:.04em}
  .inbox-stat.accent b{color:var(--accent-2)}
  .inbox-toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
  .inbox-search{display:flex;align-items:center;gap:8px;flex:1;min-width:220px;padding:9px 12px;border:1px solid var(--line);border-radius:var(--r);background:var(--surface)}
  .inbox-search svg{width:16px;height:16px;color:var(--text-faint);flex:none}
  .inbox-search input{flex:1;border:0;background:transparent;color:var(--text);outline:none;font-size:14px}
  .inbox-chips{display:flex;gap:6px;flex-wrap:wrap}
  .inbox-chip{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);background:var(--surface);color:var(--text-dim);padding:7px 11px;border-radius:999px;cursor:pointer;font-size:13px}
  .inbox-chip svg{width:14px;height:14px}
  .inbox-chip.active{color:var(--text);border-color:var(--accent-line);background:var(--accent-soft)}
  .inbox-sort{padding:8px 10px;border:1px solid var(--line);border-radius:var(--r);background:var(--surface);color:var(--text-dim);font-size:13px}
  .inbox-grid{display:flex;flex-direction:column;gap:12px}
  .inbox-card{display:grid;grid-template-columns:44px minmax(0,1fr) auto;gap:16px;padding:18px;border:1px solid var(--line);border-radius:var(--r-lg);background:var(--surface);transition:border-color .15s,transform .15s}
  .inbox-card:hover{border-color:var(--line-2)}
  .inbox-card.selected{border-color:var(--accent-line);box-shadow:inset 0 0 0 1px var(--accent-line)}
  .inbox-card.is-dup{border-left:3px solid var(--warn)}
  .inbox-gutter{display:flex;flex-direction:column;align-items:center;gap:10px}
  .inbox-source{width:44px;height:44px;border-radius:12px;display:grid;place-items:center;background:var(--surface-3);color:var(--text-dim);flex:none}
  .inbox-source svg{width:20px;height:20px}
  .inbox-body{min-width:0;display:flex;flex-direction:column;gap:9px}
  .inbox-line{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
  .inbox-kind{font-size:11px;font-weight:600;letter-spacing:.03em;text-transform:uppercase;color:var(--text-dim);padding:3px 8px;border:1px solid var(--line);border-radius:6px}
  .inbox-time{font-size:12px;color:var(--text-faint);margin-left:auto}
  .inbox-card h3{font-size:17px;letter-spacing:0;overflow-wrap:anywhere}
  .inbox-desc{color:var(--text-dim);font-size:14px;overflow-wrap:anywhere}
  .inbox-quote{font-size:13px;color:var(--text-dim);padding:8px 12px;border-left:2px solid var(--line-2);background:var(--bg-2);border-radius:0 8px 8px 0;overflow-wrap:anywhere}
  .inbox-tags{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
  .inbox-reason{font-size:12px;color:var(--text-faint)}
  .inbox-dup{font-size:12px;color:var(--warn);display:inline-flex;align-items:center;gap:6px}
  .inbox-dup i{width:6px;height:6px;border-radius:50%;background:var(--warn);flex:none}
  .inbox-conf{display:flex;align-items:center;gap:10px;min-width:170px}
  .inbox-conf-bar{flex:1;height:6px;border-radius:999px;background:var(--surface-3);overflow:hidden}
  .inbox-conf-bar i{display:block;height:100%;border-radius:999px}
  .inbox-conf b{font-size:12px;font-variant-numeric:tabular-nums;min-width:34px;text-align:right}
  .conf-high i{background:var(--ok)}.conf-high b{color:var(--ok)}
  .conf-mid i{background:var(--warn)}.conf-mid b{color:var(--warn)}
  .conf-low i{background:var(--err)}.conf-low b{color:var(--err)}
  .inbox-candidates{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
  .inbox-candidates>span{font-size:12px;color:var(--text-faint)}
  .inbox-cand{font-size:12px;padding:4px 9px;border-radius:999px;border:1px solid var(--line);background:var(--bg-2);color:var(--text-dim);cursor:pointer}
  .inbox-cand:hover{border-color:var(--accent-line);color:var(--text)}
  .inbox-cand b{color:var(--text-faint);font-weight:500;margin-left:4px}
  .inbox-side{display:flex;flex-direction:column;gap:8px;align-items:stretch;min-width:200px}
  .inbox-side .input,.inbox-side select{width:100%;padding:9px 10px;border:1px solid var(--line);border-radius:9px;background:var(--bg-2);color:var(--text)}
  .inbox-side .btn{width:100%}
  .inbox-outcome{display:flex;align-items:center;gap:7px;font-size:13px;color:var(--text-dim);justify-content:flex-end}
  .inbox-check{width:18px;height:18px;accent-color:var(--accent);cursor:pointer}
  .inbox-empty{padding:48px 24px;text-align:center;border:1px dashed var(--line-2);border-radius:var(--r-lg);color:var(--text-dim)}
  .inbox-empty b{display:block;font-size:16px;color:var(--text);margin-bottom:6px}
  .inbox-bulkbar{position:sticky;bottom:16px;display:flex;align-items:center;gap:12px;padding:12px 16px;border:1px solid var(--accent-line);border-radius:var(--r-lg);background:var(--surface-2);box-shadow:var(--shadow-lg);margin-top:4px}
  .inbox-bulkbar b{font-size:14px}
  .inbox-bulkbar .grow{flex:1}
  @media(max-width:860px){.inbox-stats{grid-template-columns:repeat(2,1fr)}.inbox-card{grid-template-columns:1fr}.inbox-source{display:none}.inbox-side{min-width:0}}
  `;
  document.head.appendChild(style);
}

export default async function aiInboxView(root, params) {
  injectStyles();
  setTopbar("Входящие AI");
  const mount = root.querySelector("#inbox-root");
  const members = await api.teams.members(params.teamId).then((data) => data.items || []).catch(() => []);

  const state = {
    status: "pending",
    source: "all",
    search: "",
    sort: "new",
    selected: new Set(),
    items: [],
    assignees: new Map(),
  };

  function visibleItems() {
    const search = state.search.trim().toLowerCase();
    let list = state.items.filter((item) => {
      if (state.status !== "all" && item.status !== state.status) return false;
      if (state.source !== "all" && (item.source?.type || "telegram") !== state.source) return false;
      if (search) {
        const haystack = `${item.semantic?.task?.title || ""} ${item.raw_text || ""} ${item.identity?.display_name || ""}`.toLowerCase();
        if (!haystack.includes(search)) return false;
      }
      return true;
    });
    if (state.sort === "confidence") {
      list = list.slice().sort((a, b) => (b.confidence || 0) - (a.confidence || 0));
    }
    return list;
  }

  function sources() {
    const present = new Set(state.items.map((item) => item.source?.type || "telegram"));
    return [...present];
  }

  async function load() {
    mount.innerHTML = '<div class="view-loading">Загружаем очередь...</div>';
    try {
      state.items = await api.aiInbox.list(params.teamId);
    } catch (error) {
      mount.innerHTML = `<div class="note warn">${escapeHtml(error.message || "Не удалось загрузить очередь")}</div>`;
      return;
    }
    state.selected.clear();
    renderShell();
  }

  function renderShell() {
    const present = sources();
    const sourceChips = present.length > 1
      ? `<div class="inbox-chips" data-role="source">
          ${chip("all", "Все источники", null, state.source === "all")}
          ${present.map((key) => chip(key, sourceLabel(key), SOURCE_META[key]?.icon, state.source === key)).join("")}
        </div>`
      : "";
    mount.innerHTML = `
      <div class="inbox-v2">
        <div class="inbox-stats" id="inbox-stats"></div>
        <div class="inbox-toolbar">
          <label class="inbox-search">${window.gcIcon("inbox")}<input type="search" id="inbox-search" placeholder="Поиск по тексту или исполнителю" value="${escapeHtml(state.search)}"></label>
          <div class="segmented" data-role="status">
            ${STATUS_TABS.map(([key, label]) => `<button class="${state.status === key ? "active" : ""}" data-status="${key}">${label}</button>`).join("")}
          </div>
          ${sourceChips}
          <select class="inbox-sort" id="inbox-sort">
            <option value="new" ${state.sort === "new" ? "selected" : ""}>Сначала новые</option>
            <option value="confidence" ${state.sort === "confidence" ? "selected" : ""}>По уверенности</option>
          </select>
        </div>
        <div class="inbox-grid" id="inbox-grid"></div>
        <div id="inbox-bulk"></div>
      </div>`;

    mount.querySelector("#inbox-search").oninput = (event) => {
      state.search = event.target.value;
      renderGrid();
    };
    mount.querySelector("[data-role='status']").onclick = (event) => {
      const button = event.target.closest("[data-status]");
      if (!button) return;
      state.status = button.dataset.status;
      state.selected.clear();
      mount.querySelectorAll("[data-role='status'] button").forEach((item) => item.classList.toggle("active", item === button));
      renderGrid();
    };
    mount.querySelector("[data-role='source']")?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-chip]");
      if (!button) return;
      state.source = button.dataset.chip;
      mount.querySelectorAll("[data-role='source'] [data-chip]").forEach((item) => item.classList.toggle("active", item === button));
      renderGrid();
    });
    mount.querySelector("#inbox-sort").onchange = (event) => {
      state.sort = event.target.value;
      renderGrid();
    };
    renderGrid();
  }

  function renderStats() {
    const pending = state.items.filter((item) => item.status === "pending");
    const confident = pending.filter((item) => (item.confidence || 0) >= HIGH_CONFIDENCE).length;
    const needsAssignee = pending.filter((item) => item.kind === "needs_assignee" || item.identity?.status === "unresolved").length;
    const avg = pending.length
      ? Math.round(pending.reduce((sum, item) => sum + (item.confidence || 0), 0) / pending.length * 100)
      : 0;
    const stats = mount.querySelector("#inbox-stats");
    if (!stats) return;
    stats.innerHTML = [
      statTile(pending.length, "Ожидают", true),
      statTile(`${avg}%`, "Средняя уверенность"),
      statTile(confident, "Готовы к приёму"),
      statTile(needsAssignee, "Нужен исполнитель"),
    ].join("");
  }

  function renderGrid() {
    renderStats();
    const grid = mount.querySelector("#inbox-grid");
    const list = visibleItems();
    state.selected.forEach((id) => { if (!list.some((item) => item.id === id)) state.selected.delete(id); });
    if (!list.length) {
      grid.innerHTML = emptyState();
    } else {
      grid.innerHTML = list.map((item) => renderCard(item)).join("");
    }
    bindCards(grid);
    renderBulk();
  }

  function renderCard(item) {
    const task = item.semantic?.task || {};
    const title = task.title || item.raw_text || "Без названия";
    const isPending = item.status === "pending";
    const selectable = state.status === "pending" && isPending;
    const selected = state.selected.has(item.id);
    const conf = confidenceClass(item.confidence);
    const confPct = item.confidence == null ? null : Math.round(item.confidence * 100);
    const source = SOURCE_META[item.source?.type] || { label: sourceLabel(item.source?.type), icon: "inbox" };
    const kindLabel = KIND_LABEL[item.kind] || "Сигнал";
    const reason = REASON_LABEL[item.reason] || item.reason;
    const showQuote = task.title && item.raw_text && item.raw_text !== task.title;
    const candidates = (item.identity?.candidates || []).filter((cand) => cand.user_id);

    const side = isPending ? `
      <div class="inbox-side">
        <select class="input" data-assignee="${item.id}">
          ${assigneeOptions(item)}
        </select>
        <button class="btn btn-sm btn-primary" data-approve="${item.id}">Создать в Grey Board</button>
        <button class="btn btn-sm btn-ghost" data-reject="${item.id}">Отклонить</button>
      </div>`
      : `<div class="inbox-outcome">${outcomeIcon(item.status)}<span>${escapeHtml(STATUS_LABEL[item.status] || item.status)}</span></div>`;

    return `<article class="inbox-card ${selected ? "selected" : ""} ${item.duplicate_task_id ? "is-dup" : ""}" data-card="${item.id}">
      <div class="inbox-gutter">
        ${selectable ? `<input type="checkbox" class="inbox-check" data-select="${item.id}" ${selected ? "checked" : ""} aria-label="Выбрать">` : ""}
        <div class="inbox-source" title="${escapeHtml(source.label)}">${window.gcIcon(source.icon)}</div>
      </div>
      <div class="inbox-body">
        <div class="inbox-line">
          <span class="inbox-kind">${escapeHtml(kindLabel)}</span>
          <span class="inbox-time">${escapeHtml(source.label)} · ${escapeHtml(timeAgo(item.created_at))}</span>
        </div>
        <h3>${escapeHtml(title)}</h3>
        ${task.description ? `<p class="inbox-desc">${escapeHtml(task.description)}</p>` : ""}
        ${showQuote ? `<div class="inbox-quote">${escapeHtml(item.raw_text)}</div>` : ""}
        <div class="inbox-conf ${conf.cls}">
          <div class="inbox-conf-bar"><i style="width:${confPct == null ? 0 : confPct}%"></i></div>
          <b>${confPct == null ? "—" : `${confPct}%`}</b>
        </div>
        <div class="inbox-tags">
          ${reason ? `<span class="inbox-reason">${escapeHtml(reason)}</span>` : ""}
          ${item.duplicate_task_id ? `<span class="inbox-dup"><i></i>Похоже на существующую задачу</span>` : ""}
        </div>
        ${isPending && candidates.length ? `<div class="inbox-candidates"><span>Кандидаты:</span>${candidates.slice(0, 4).map((cand) => `<button class="inbox-cand" data-cand="${item.id}" data-user="${escapeHtml(cand.user_id)}">${escapeHtml(cand.display_name || "Участник")}${cand.score != null ? `<b>${Math.round(cand.score * 100)}%</b>` : ""}</button>`).join("")}</div>` : ""}
      </div>
      ${side}
    </article>`;
  }

  function assigneeOptions(item) {
    const selected = state.assignees.get(item.id) ?? item.identity?.user_id ?? "";
    return [
      `<option value="">Без исполнителя</option>`,
      ...members.map((member) => `<option value="${escapeHtml(member.id)}" ${String(selected) === String(member.id) ? "selected" : ""}>${escapeHtml(member.display_name)}</option>`),
    ].join("");
  }

  function bindCards(grid) {
    grid.querySelectorAll("[data-select]").forEach((box) => {
      box.onchange = () => {
        if (box.checked) state.selected.add(box.dataset.select);
        else state.selected.delete(box.dataset.select);
        box.closest(".inbox-card")?.classList.toggle("selected", box.checked);
        renderBulk();
      };
    });
    grid.querySelectorAll("[data-assignee]").forEach((select) => {
      select.onchange = () => state.assignees.set(select.dataset.assignee, select.value);
    });
    grid.querySelectorAll("[data-cand]").forEach((button) => {
      button.onclick = () => {
        const select = grid.querySelector(`[data-assignee="${button.dataset.cand}"]`);
        if (select) {
          select.value = button.dataset.user;
          state.assignees.set(button.dataset.cand, button.dataset.user);
        }
      };
    });
    grid.querySelectorAll("[data-approve]").forEach((button) => {
      button.onclick = () => approveItems([button.dataset.approve], button);
    });
    grid.querySelectorAll("[data-reject]").forEach((button) => {
      button.onclick = async () => {
        button.disabled = true;
        await api.aiInbox.reject(button.dataset.reject).catch(() => {});
        toast("Сигнал отклонён");
        await load();
      };
    });
  }

  function renderBulk() {
    const host = mount.querySelector("#inbox-bulk");
    if (!host) return;
    const pending = visibleItems().filter((item) => item.status === "pending");
    const confidentIds = pending.filter((item) => (item.confidence || 0) >= HIGH_CONFIDENCE).map((item) => item.id);
    const selectedCount = state.selected.size;
    if (selectedCount > 0) {
      host.innerHTML = `<div class="inbox-bulkbar">
        <b>Выбрано ${selectedCount}</b>
        <span class="grow"></span>
        <button class="btn btn-sm btn-ghost" id="bulk-clear">Снять</button>
        <button class="btn btn-sm btn-ghost" id="bulk-reject">Отклонить</button>
        <button class="btn btn-sm btn-primary" id="bulk-approve">Создать задачи</button>
      </div>`;
      host.querySelector("#bulk-clear").onclick = () => { state.selected.clear(); renderGrid(); };
      host.querySelector("#bulk-approve").onclick = (event) => approveItems([...state.selected], event.currentTarget);
      host.querySelector("#bulk-reject").onclick = async (event) => {
        event.currentTarget.disabled = true;
        for (const id of state.selected) await api.aiInbox.reject(id).catch(() => {});
        toast(`Отклонено: ${state.selected.size}`);
        await load();
      };
    } else if (state.status === "pending" && confidentIds.length > 1) {
      host.innerHTML = `<div class="inbox-bulkbar">
        <b>${confidentIds.length} сигналов с уверенностью ≥ ${Math.round(HIGH_CONFIDENCE * 100)}%</b>
        <span class="grow"></span>
        <button class="btn btn-sm btn-primary" id="bulk-confident">Принять все уверенные</button>
      </div>`;
      host.querySelector("#bulk-confident").onclick = (event) => approveItems(confidentIds, event.currentTarget);
    } else {
      host.innerHTML = "";
    }
  }

  async function approveItems(ids, trigger) {
    if (!ids.length) return;
    if (trigger) trigger.disabled = true;
    let done = 0;
    for (const id of ids) {
      const assigneeId = state.assignees.get(id) ?? state.items.find((item) => item.id === id)?.identity?.user_id ?? "";
      try {
        if (assigneeId) await api.aiInbox.assign(id, assigneeId);
        await api.aiInbox.approve(id);
        done += 1;
      } catch {
        /* keep going; failures surface in the summary toast */
      }
    }
    toast(done === 1 ? "Задача создана в Grey Board" : `Создано задач: ${done} из ${ids.length}`, done ? "ok" : "warn");
    await load();
  }

  function emptyState() {
    const messages = {
      pending: ["Очередь пуста", "Новые предложения из Telegram и Windows-агента появятся здесь."],
      approved: ["Пока нет принятых сигналов", "Принятые предложения станут задачами в Grey Board."],
      rejected: ["Отклонённых сигналов нет", "Здесь будут предложения, которые вы отклонили."],
      all: ["Сигналов нет", "Когда команда начнёт переписку, AI соберёт кандидатов в задачи."],
    };
    const [title, text] = state.search
      ? ["Ничего не найдено", "Попробуйте изменить запрос или сбросить фильтры."]
      : (messages[state.status] || messages.all);
    return `<div class="inbox-empty"><b>${escapeHtml(title)}</b>${escapeHtml(text)}</div>`;
  }

  await load();
}

function statTile(value, label, accent = false) {
  return `<div class="inbox-stat ${accent ? "accent" : ""}"><b>${escapeHtml(String(value))}</b><span>${escapeHtml(label)}</span></div>`;
}

function chip(key, label, icon, active) {
  return `<button class="inbox-chip ${active ? "active" : ""}" data-chip="${escapeHtml(key)}">${icon ? window.gcIcon(icon) : ""}${escapeHtml(label)}</button>`;
}

function sourceLabel(type) {
  return SOURCE_META[type]?.label || (type ? type.replace(/_/g, " ") : "Источник");
}

function confidenceClass(value) {
  if (value == null) return { cls: "conf-mid" };
  if (value >= HIGH_CONFIDENCE) return { cls: "conf-high" };
  if (value >= 0.6) return { cls: "conf-mid" };
  return { cls: "conf-low" };
}

function outcomeIcon(status) {
  const color = status === "approved" ? "var(--ok)" : status === "rejected" ? "var(--err)" : "var(--text-faint)";
  return `<span style="width:8px;height:8px;border-radius:50%;background:${color};display:inline-block"></span>`;
}

function timeAgo(value) {
  if (!value) return "только что";
  const diff = (Date.now() - new Date(value).getTime()) / 1000;
  if (Number.isNaN(diff)) return "";
  if (diff < 60) return "только что";
  if (diff < 3600) return `${Math.floor(diff / 60)} мин назад`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} ч назад`;
  if (diff < 604800) return `${Math.floor(diff / 86400)} дн назад`;
  return formatDate(value);
}

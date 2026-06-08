import { api } from "../api.js";
import { bindForm, currentTeam, errorMessage, escapeHtml, formatDate, setTopbar, toast } from "../view-utils.js";

const BOARD_VIEWS = [
  ["agent", "Agent View"],
  ["status", "Status View"],
  ["people", "People View"],
  ["risk", "Risk View"],
  ["timeline", "Timeline View"],
  ["source", "Source View"],
];

function managedTeam(params = {}) {
  const teams = window.gcCurrentUser.teams || [];
  return teams.find((team) => team.id === (params.id || params.teamId)) || currentTeam({ teams });
}

function setHeader(root, title, desc, actions = "") {
  root.querySelector("#agentic-title").textContent = title;
  root.querySelector("#agentic-desc").textContent = desc;
  setTopbar(title, actions);
}

export async function greyBoardView(root, params, query) {
  const team = managedTeam(params);
  if (!team) return empty(root, "Команда не найдена");
  const view = query.view || "agent";
  setHeader(root, "Grey Board", "Живая доска задач, источников, рисков и действий агента.", `<a class="btn btn-ghost" href="/app/teams/${team.id}/ai-inbox">AI Inbox</a><a class="btn btn-primary" href="/app/teams/${team.id}/yougile">YouGile</a>`);
  await renderBoard(root, team.id, view);
}

async function renderBoard(root, teamId, view) {
  const content = root.querySelector("#agentic-content");
  content.innerHTML = '<div class="view-loading">Загрузка Grey Board...</div>';
  const data = await api.greyBoard.get(teamId, view);
  content.innerHTML = `
    <div class="grey-cockpit">
      <aside class="board-switcher">${BOARD_VIEWS.map(([key, label]) => `<a class="${key === view ? "active" : ""}" href="/app/teams/${teamId}/board?view=${key}">${label}</a>`).join("")}</aside>
      <section class="board-main">
        ${healthBar(data.health)}
        <div class="agent-board">${(data.groups || data.columns || []).map(groupHtml).join("")}</div>
      </section>
      <aside class="agent-rail">
        <div class="rail-title">Agent Recommendations</div>
        ${(data.recommendations || []).map(recommendationHtml).join("") || '<div class="dim">Критичных рекомендаций нет.</div>'}
      </aside>
    </div>`;
  content.querySelectorAll("[data-task-action]").forEach((button) => {
    button.onclick = async () => {
      await api.greyBoard.action(button.dataset.taskId, { action: button.dataset.taskAction });
      toast("Задача обновлена");
      await renderBoard(root, teamId, view);
    };
  });
}

function healthBar(health) {
  return `<div class="healthbar">
    ${healthPill("LLM", health.llm === "configured")}
    ${healthPill("Telegram", health.telegram === "linked")}
    ${healthPill("YouGile", health.yougile === "synced")}
    <span class="pill ${health.open_risks ? "warn" : "ok"}"><span class="dot"></span>${health.open_risks || 0} risks</span>
    <span class="pill idle">last sync: ${escapeHtml(health.last_sync || "never")}</span>
  </div>`;
}

function healthPill(label, ok) {
  return `<span class="pill ${ok ? "ok" : "warn"}"><span class="dot"></span>${label} ${ok ? "OK" : "setup"}</span>`;
}

function groupHtml(group) {
  const cards = group.cards || group.tasks || [];
  return `<div class="agent-col">
    <div class="agent-col-head"><b>${escapeHtml(group.title)}</b><span class="mono">${group.count ?? cards.length}</span></div>
    <div class="col gap-10">${cards.map(cardHtml).join("") || '<span class="faint">Пусто</span>'}</div>
  </div>`;
}

function cardHtml(card) {
  return `<article class="task-evidence-card">
    <div class="flex between gap-8"><b>${escapeHtml(card.public_id)} ${escapeHtml(card.title)}</b><span class="pill ${card.yougile.sync_status === "conflict" ? "err" : "info"}">${escapeHtml(card.yougile.sync_status)}</span></div>
    <div class="task-meta">${escapeHtml(card.assignee_name || card.assignee_text || "Без исполнителя")} · ${escapeHtml(card.priority)} · ${card.deadline ? formatDate(card.deadline) : "без дедлайна"}</div>
    <div class="evidence-line"><span>Источник</span><b>${escapeHtml(card.source.type)}</b><span>Confidence</span><b>${Math.round((card.confidence || 0) * 100)}%</b></div>
    ${card.signals.length ? `<div class="signal-list">${card.signals.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>` : ""}
    <details class="mt-8"><summary>Доказательства агента</summary>
      <div class="source-text">${escapeHtml(card.source.text || card.description || "Источник не сохранен")}</div>
      <div class="agent-log">${card.agent_history.map((item) => `<div><span>${escapeHtml(item.at || "")}</span>${escapeHtml(item.text)}</div>`).join("")}</div>
      <div class="code-msg mt-8">YouGile: ${escapeHtml(card.yougile.external_task_id || "not linked")} · ${escapeHtml(card.yougile.last_sync || "no sync")}</div>
    </details>
    <div class="card-actions">
      ${actionBtn(card, "start", "В работу")}
      ${actionBtn(card, "done", "Готово")}
      ${actionBtn(card, "blocked", "Блок")}
      ${actionBtn(card, "review", "Review")}
      ${card.yougile.external_url ? `<a class="btn btn-sm btn-ghost" target="_blank" href="${escapeHtml(card.yougile.external_url)}">YouGile</a>` : ""}
    </div>
  </article>`;
}

function actionBtn(card, action, label) {
  return `<button class="btn btn-sm btn-ghost" data-task-id="${card.id}" data-task-action="${action}">${label}</button>`;
}

function recommendationHtml(item) {
  return `<div class="recommendation ${item.severity}">
    <div class="flex between gap-8"><b>${escapeHtml(item.title)}</b><span>${escapeHtml(item.severity)}</span></div>
    <p>${escapeHtml(item.message)}</p>
    <button class="btn btn-sm btn-ghost" type="button">Открыть</button>
  </div>`;
}

export async function aiInboxView(root, params) {
  const team = managedTeam(params);
  if (!team) return empty(root, "Команда не найдена");
  setHeader(root, "AI Inbox", "Human-in-the-loop входящие: предложения задач, конфликты, дубли и низкая уверенность.");
  const content = root.querySelector("#agentic-content");
  const data = await api.aiInbox.list(team.id);
  content.innerHTML = `<div class="inbox-list">${data.items.map(inboxItem).join("") || '<div class="note warn">AI Inbox пуст.</div>'}</div>`;
  content.querySelectorAll("[data-inbox]").forEach((button) => {
    button.onclick = async () => {
      const fn = button.dataset.inboxAction === "approve" ? api.aiInbox.approve : api.aiInbox.reject;
      await fn(button.dataset.inbox);
      toast("AI Inbox обновлен");
      await aiInboxView(root, params);
    };
  });
}

function inboxItem(item) {
  return `<article class="card card-pad">
    <div class="card-head"><div><div class="eyebrow">${escapeHtml(item.type)}</div><div class="card-title mt-6">${escapeHtml(item.proposed_action || "Нужно решение")}</div></div><span class="pill info">${Math.round(item.confidence * 100)}%</span></div>
    <div class="source-text">${escapeHtml(item.source_text)}</div>
    <pre class="json-box">${escapeHtml(JSON.stringify(item.parsed_payload || {}, null, 2))}</pre>
    <div class="flex gap-8 mt-12"><button class="btn btn-primary" data-inbox="${item.id}" data-inbox-action="approve">Принять</button><button class="btn btn-ghost" data-inbox="${item.id}" data-inbox-action="reject">Отклонить</button></div>
  </article>`;
}

export async function setupView(root, params) {
  const team = managedTeam(params);
  if (!team) return empty(root, "Команда не найдена");
  setHeader(root, "Setup Wizard", "Мастер внедрения: компания, команда, Telegram, YouGile, LLM и тестовый сценарий.", `<button class="btn btn-primary" id="run-demo">Запустить demo</button>`);
  const data = await api.setup.status(team.id);
  root.querySelector("#agentic-content").innerHTML = `<div class="setup-steps">${data.steps.map(step => `<div class="check-item ${step.status === "done" ? "done" : step.status === "warning" ? "active" : ""}"><div class="check-box">✓</div><div><div class="check-title">${escapeHtml(step.title)}</div><div class="check-desc">${escapeHtml(step.status)}</div></div></div>`).join("")}</div>`;
  document.getElementById("run-demo").onclick = async () => {
    await api.setup.runDemo(team.id);
    toast("Demo создано");
    await setupView(root, params);
  };
}

export async function yougileFullView(root, params) {
  const team = managedTeam(params);
  if (!team) return empty(root, "Команда не найдена");
  setHeader(root, "YouGile Full Sync", "Подключение, выбор реальной доски, mapping колонок, импорт и manual sync.");
  const content = root.querySelector("#agentic-content");
  const status = await api.yougile.statusFull(team.id).catch(() => ({ connected: false }));
  if (!status.connected) {
    content.innerHTML = `<div class="card card-pad-lg"><h2>Подключить YouGile</h2><form id="yg-full" class="grid g2 mt-20"><label>Login<input class="input mt-6" name="login"></label><label>Password<input class="input mt-6" name="password" type="password"></label><label>Company ID<input class="input mt-6" name="company_id"></label><label>API key<input class="input mt-6" name="api_key"></label><button class="btn btn-primary" type="submit">Проверить и подключить</button></form></div>`;
    bindForm(content, "#yg-full", async (data) => {
      await api.yougile.connectFull(team.id, Object.fromEntries(data.entries()));
      toast("YouGile подключен");
      await yougileFullView(root, params);
    });
    return;
  }
  const [boards, events] = await Promise.all([api.yougile.boardsFull(team.id), api.yougile.syncEvents(team.id).catch(() => ({ items: [] }))]);
  content.innerHTML = `<div class="grid g4">
    ${stat("Досок", status.stats.boards || 0)}${stat("Колонок", status.stats.columns || 0)}${stat("Связанных задач", status.stats.tasks || 0)}${stat("Статус", status.status || "active")}
  </div>
  <div class="grid g2 mt-20">
    <div class="card card-pad"><div class="card-head"><div class="card-title">Реальные YouGile boards</div><button class="btn btn-sm btn-primary" id="import-board">Импортировать</button></div>
      <div class="col gap-8">${boards.items.map(board => `<button class="board-row ${board.is_selected ? "selected" : ""}" data-board="${board.id}"><b>${escapeHtml(board.name)}</b><span>${escapeHtml(board.external_id)}</span></button>`).join("") || '<div class="dim">Доски еще не загружены.</div>'}</div>
    </div>
    <div class="card card-pad"><div class="card-head"><div class="card-title">Sync events</div><button class="btn btn-sm btn-ghost" id="sync-now">Sync</button></div>
      <div class="event-list">${events.items.slice(0, 12).map(event => `<div><b>${escapeHtml(event.status)}</b> ${escapeHtml(event.entity_type)} <span>${escapeHtml(event.message || "")}</span></div>`).join("") || '<div class="dim">Событий нет.</div>'}</div>
    </div>
  </div>`;
  content.querySelectorAll("[data-board]").forEach((button) => {
    button.onclick = async () => {
      await api.yougile.selectBoard(team.id, button.dataset.board, null);
      toast("Доска выбрана");
      await yougileFullView(root, params);
    };
  });
  content.querySelector("#import-board").onclick = async () => {
    const result = await api.yougile.importBoard(team.id);
    toast(`Импорт: ${result.imported_tasks} новых, ${result.updated_tasks} обновлено`);
    await yougileFullView(root, params);
  };
  content.querySelector("#sync-now").onclick = async () => {
    await api.yougile.syncFull(team.id);
    toast("Manual sync выполнен");
    await yougileFullView(root, params);
  };
}

export async function teamMapView(root, params) {
  const companyId = params.companyId || params.id;
  setHeader(root, "Team Map", "Операционная карта команд, рисков и sync health.");
  const data = await api.companies.map(companyId);
  root.querySelector("#agentic-content").innerHTML = `<div class="org-map"><div class="org-root">${escapeHtml(data.company.name)}</div>${data.teams.map(team => `<a href="/app/teams/${team.id}/board" class="org-team ${team.status}"><b>${escapeHtml(team.name)}</b><span>Open ${team.open_tasks}</span><span>Risks ${team.risks}</span><span>${escapeHtml(team.sync_health)}</span></a>`).join("")}</div>`;
}

export async function recommendationsView(root, params) {
  const team = managedTeam(params);
  if (!team) return empty(root, "Команда не найдена");
  setHeader(root, "Agent Recommendations", "Следующие действия руководителя.");
  const data = await api.recommendations.team(team.id);
  root.querySelector("#agentic-content").innerHTML = `<div class="grid g2">${data.items.map(recommendationHtml).join("") || '<div class="note warn">Рекомендаций нет.</div>'}</div>`;
}

export async function peopleView(root, params) {
  const team = managedTeam(params);
  if (!team) return empty(root, "Команда не найдена");
  setHeader(root, "People", "Сотрудники, нагрузка, отсутствие, достижения.");
  const data = await api.people.team(team.id);
  root.querySelector("#agentic-content").innerHTML = `<div class="grid g3">${data.items.map(personCard).join("")}</div>`;
}

export async function profileView(root, params) {
  injectProfileStyles();
  const mine = location.pathname === "/app/me";
  setHeader(root, mine ? "Мой профиль" : "Профиль сотрудника", "Прогресс, достижения, активность.");
  const container = root.querySelector("#agentic-content");
  async function render() {
    let data;
    try {
      data = mine ? await api.people.me() : await api.people.profile(params.userId);
    } catch (e) {
      container.innerHTML = `<div class="note warn">${escapeHtml(e.message || "Не удалось загрузить профиль")}</div>`;
      return;
    }
    container.innerHTML = profileHtml(data, mine);
    if (mine) bindProfileEdit(container, data, render);
  }
  await render();
}

const ROLE_RU = { director: "Директор", manager: "Руководитель", employee: "Сотрудник", member: "Участник" };

function profileInitials(name) {
  return (name || "").trim().split(/\s+/).slice(0, 2).map((w) => (w[0] || "").toUpperCase()).join("") || "?";
}

function avatarBlock(user, big) {
  const size = big ? "avatar-xl" : "avatar-sm";
  if (user.photo_data_url) {
    return `<div class="gc-avatar ${size}" style="background-image:url('${escapeHtml(user.photo_data_url)}')"></div>`;
  }
  return `<div class="gc-avatar ${size} ph">${escapeHtml(profileInitials(user.display_name))}</div>`;
}

function profileHtml(data, mine) {
  const u = data.user || {};
  const s = data.stats || {};
  const pct = Math.min(100, Math.round((s.level_xp / (s.next_level_xp || 100)) * 100));
  const role = ROLE_RU[u.role] || u.role || "—";
  const earned = data.achievements.filter((a) => a.earned).length;
  return `
  <div class="gc-profile">
    <div class="card prof-hero">
      <div class="prof-hero-row">
        <div class="prof-ava-wrap">
          ${avatarBlock(u, true)}
          ${mine ? `<label class="ava-edit" title="Загрузить фото">📷<input type="file" id="ava-input" accept="image/*" hidden></label>` : ""}
        </div>
        <div class="prof-id">
          <div class="prof-name-row">
            <h2 id="prof-name">${escapeHtml(u.display_name || "—")}</h2>
            <span class="lvl-badge" title="Уровень">LVL ${s.level || 1}</span>
            <span class="role-badge">${escapeHtml(role)}</span>
            ${u.telegram_linked ? `<span class="tg-badge">📱 ${escapeHtml(u.telegram_username ? "@" + u.telegram_username : "Telegram")}</span>` : ""}
          </div>
          <p class="prof-bio" id="prof-bio">${escapeHtml(u.bio || (mine ? "Добавьте пару слов о себе…" : ""))}</p>
          <div class="lvl-bar"><div class="lvl-fill" style="width:${pct}%"></div><span class="lvl-txt">${s.level_xp || 0} / ${s.next_level_xp || 100} XP до ${(s.level || 1) + 1} ур.</span></div>
        </div>
      </div>
      ${mine ? `<div class="prof-edit-actions"><button class="btn btn-sm btn-ghost" id="edit-profile">✏️ Редактировать</button></div>` : ""}
    </div>

    <div class="prof-stats">
      ${statCard("🔥", "Серия", (s.streak || 0) + " дн.")}
      ${statCard("⭐", "Всего XP", s.xp || 0)}
      ${statCard("📋", "Открытых", s.open_tasks || 0)}
      ${statCard("⏰", "Просрочено", s.overdue || 0)}
      ${statCard("✅", "За неделю", s.closed_week || 0)}
      ${statCard("🏆", "Закрыто всего", s.closed_total || 0)}
    </div>

    <div class="card card-pad">
      <div class="card-title">Достижения <span class="dim">${earned}/${data.achievements.length}</span></div>
      <div class="ach-grid">
        ${data.achievements.map((a) => `<div class="ach-card ${a.earned ? "earned" : "locked"}" title="${escapeHtml(a.desc || "")}">
          <div class="ach-ico">${a.earned ? (a.icon || "✓") : "🔒"}</div>
          <div class="ach-meta"><div class="ach-name">${escapeHtml(a.name)}</div><div class="ach-desc">${escapeHtml(a.desc || "")}</div></div>
        </div>`).join("")}
      </div>
    </div>

    <div class="card card-pad">
      <div class="card-title">Задачи</div>
      <table class="tbl mt-12"><tbody>
        ${(data.tasks || []).slice(0, 30).map((t) => `<tr><td class="mono">${escapeHtml(t.public_id)}</td><td>${escapeHtml(t.title)}</td><td><span class="pill">${escapeHtml(t.status)}</span></td><td>${t.deadline ? formatDate(t.deadline) : ""}</td></tr>`).join("") || '<tr><td colspan="4" class="dim">Задач нет</td></tr>'}
      </tbody></table>
    </div>
  </div>`;
}

function statCard(icon, label, value) {
  return `<div class="card prof-stat"><div class="ps-ico">${icon}</div><div class="ps-val">${escapeHtml(String(value))}</div><div class="ps-lbl">${escapeHtml(label)}</div></div>`;
}

function bindProfileEdit(container, data, rerender) {
  const u = data.user || {};
  const input = container.querySelector("#ava-input");
  if (input) {
    input.addEventListener("change", async () => {
      const file = input.files?.[0];
      if (!file) return;
      try {
        const dataUrl = await resizeImage(file, 256);
        await api.people.update({ photo_data_url: dataUrl });
        toast("Фото обновлено");
        await rerender();
      } catch (e) { toast("Не удалось загрузить фото: " + (e.message || "")); }
    });
  }
  const editBtn = container.querySelector("#edit-profile");
  if (editBtn) {
    editBtn.addEventListener("click", () => openProfileEditor(container, u, rerender));
  }
}

function openProfileEditor(container, u, rerender) {
  let dialog = document.getElementById("profile-edit-dialog");
  if (!dialog) {
    dialog = document.createElement("dialog");
    dialog.id = "profile-edit-dialog";
    dialog.className = "task-dialog";
    document.body.appendChild(dialog);
  }
  dialog.innerHTML = `<div class="task-panel">
    <header><h3>Редактировать профиль</h3><button class="icon-close" type="button">×</button></header>
    <label class="fld">Имя<input id="pe-name" value="${escapeHtml(u.display_name || "")}"></label>
    <label class="fld">О себе<textarea id="pe-bio" rows="3">${escapeHtml(u.bio || "")}</textarea></label>
    <div style="display:flex;gap:8px;margin-top:14px">
      <button class="btn btn-sm btn-primary" id="pe-save">Сохранить</button>
      <button class="btn btn-sm btn-ghost" id="pe-cancel" type="button">Отмена</button>
    </div>
  </div>`;
  dialog.querySelector(".icon-close").onclick = () => dialog.close();
  dialog.querySelector("#pe-cancel").onclick = () => dialog.close();
  dialog.querySelector("#pe-save").onclick = async () => {
    try {
      await api.people.update({
        display_name: dialog.querySelector("#pe-name").value.trim(),
        bio: dialog.querySelector("#pe-bio").value,
      });
      toast("Профиль сохранён");
      dialog.close();
      await rerender();
    } catch (e) { toast("Ошибка: " + (e.message || "")); }
  };
  dialog.showModal();
}

function resizeImage(file, max) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("read error"));
    reader.onload = () => {
      const img = new Image();
      img.onerror = () => reject(new Error("bad image"));
      img.onload = () => {
        const scale = Math.min(1, max / Math.max(img.width, img.height));
        const w = Math.round(img.width * scale), h = Math.round(img.height * scale);
        const canvas = document.createElement("canvas");
        canvas.width = w; canvas.height = h;
        canvas.getContext("2d").drawImage(img, 0, 0, w, h);
        resolve(canvas.toDataURL("image/jpeg", 0.85));
      };
      img.src = reader.result;
    };
    reader.readAsDataURL(file);
  });
}

function injectProfileStyles() {
  if (document.getElementById("gc-profile-styles")) return;
  const st = document.createElement("style");
  st.id = "gc-profile-styles";
  st.textContent = `
  .gc-profile{display:flex;flex-direction:column;gap:16px}
  .prof-hero{padding:20px;position:relative}
  .prof-hero-row{display:flex;gap:18px;align-items:center}
  .prof-ava-wrap{position:relative;flex-shrink:0}
  .gc-avatar{border-radius:50%;background-size:cover;background-position:center;background-color:#2a2a33;display:flex;align-items:center;justify-content:center;font-weight:800;color:#ddd}
  .gc-avatar.avatar-xl{width:96px;height:96px;font-size:34px}
  .gc-avatar.avatar-sm{width:34px;height:34px;font-size:13px}
  .ava-edit{position:absolute;right:-2px;bottom:-2px;width:30px;height:30px;border-radius:50%;background:#ff003c;color:#fff;display:flex;align-items:center;justify-content:center;cursor:pointer;font-size:14px;border:2px solid #141418}
  .prof-name-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
  .prof-name-row h2{margin:0;font-size:24px}
  .lvl-badge{background:linear-gradient(135deg,#ff003c,#ff7a00);color:#fff;font-weight:800;font-size:11px;padding:3px 9px;border-radius:20px}
  .role-badge{background:#22222a;border:1px solid #33333d;color:#cfcfd6;font-size:12px;padding:3px 9px;border-radius:20px}
  .tg-badge{background:#142a3a;border:1px solid #1d4a66;color:#7fc8ff;font-size:12px;padding:3px 9px;border-radius:20px}
  .prof-bio{color:#9a9aa3;margin:8px 0 12px}
  .lvl-bar{position:relative;height:20px;background:#1a1a1f;border:1px solid #2a2a33;border-radius:20px;overflow:hidden;max-width:420px}
  .lvl-fill{height:100%;background:linear-gradient(90deg,#ff003c,#ff7a00)}
  .lvl-txt{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:11px;color:#fff;text-shadow:0 1px 2px rgba(0,0,0,.6)}
  .prof-edit-actions{position:absolute;top:16px;right:16px}
  .prof-stats{display:grid;grid-template-columns:repeat(6,1fr);gap:12px}
  @media(max-width:760px){.prof-stats{grid-template-columns:repeat(3,1fr)}}
  .prof-stat{padding:14px;text-align:center}
  .ps-ico{font-size:20px}.ps-val{font-size:22px;font-weight:800;margin:4px 0}.ps-lbl{color:#8a8a93;font-size:12px}
  .ach-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px;margin-top:14px}
  .ach-card{display:flex;gap:10px;align-items:center;padding:12px;border:1px solid #26262e;border-radius:12px;background:#16161a}
  .ach-card.locked{opacity:.45;filter:grayscale(1)}
  .ach-card.earned{border-color:#3a2a18;background:linear-gradient(135deg,#1a1410,#16161a)}
  .ach-ico{font-size:26px;flex-shrink:0}
  .ach-name{font-weight:700}.ach-desc{font-size:12px;color:#8a8a93}
  .fld{display:flex;flex-direction:column;gap:5px;margin-top:10px;font-size:13px;color:#9a9aa3}
  .fld input,.fld textarea{padding:8px 10px;border-radius:9px;border:1px solid #2a2a33;background:#1a1a1f;color:#ececf0;font:inherit}
  `;
  document.head.appendChild(st);
}

export async function telegramTopicsView(root, params) {
  const team = managedTeam(params);
  if (!team) return empty(root, "Команда не найдена");
  setHeader(root, "Telegram Topics", "Привязка Telegram topics к team/board/source stream.");
  const data = await api.topics.list(team.id);
  root.querySelector("#agentic-content").innerHTML = `<div class="card card-pad"><table class="tbl"><thead><tr><th>Chat</th><th>Thread</th><th>Source</th><th>Status</th></tr></thead><tbody>${data.items.map(item => `<tr><td>${escapeHtml(item.chat_title || item.telegram_chat_id)}</td><td class="mono">${item.message_thread_id}</td><td>${escapeHtml(item.source_name || "Telegram topic")}</td><td><span class="pill ${item.bound ? "ok" : "warn"}">${item.bound ? "bound" : "new"}</span></td></tr>`).join("") || '<tr><td colspan="4">Темы появятся после сообщений из Telegram topics.</td></tr>'}</tbody></table></div>`;
}

function personCard(item) {
  const p = item.profile;
  return `<a class="card card-pad" href="/app/people/${item.id}"><div class="card-title">${escapeHtml(item.display_name)}</div><div class="dim">${escapeHtml(item.role)}</div><div class="grid g2 mt-16">${stat("Open", p.stats.open_tasks)}${stat("Overdue", p.stats.overdue)}${stat("XP", p.stats.xp)}${stat("Absence", p.absence.active ? "yes" : "no")}</div></a>`;
}

function stat(label, value) {
  return `<div class="stat"><div class="stat-label">${escapeHtml(label)}</div><div class="stat-value mono">${escapeHtml(String(value))}</div></div>`;
}

function empty(root, text) {
  root.querySelector("#agentic-content").innerHTML = `<div class="note warn">${escapeHtml(text)}</div>`;
}

export default greyBoardView;

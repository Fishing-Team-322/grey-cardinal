import { api } from "../api.js";
import { escapeHtml, formatDate, setTopbar, toast } from "../view-utils.js";

const STATUS = {
  active: "В работе",
  paused: "На паузе",
  completed: "Завершён",
  cancelled: "Отменён",
};

function injectStyles() {
  if (document.getElementById("gc-projects-v1")) return;
  const style = document.createElement("style");
  style.id = "gc-projects-v1";
  style.textContent = `
  .project-toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:18px}
  .project-toolbar input{flex:1;min-width:220px;padding:10px 12px;border:1px solid #282830;border-radius:10px;background:#151519;color:inherit}
  .project-tabs{display:flex;gap:6px}.project-tabs button{border:1px solid #282830;background:#151519;color:#aaa;padding:8px 11px;border-radius:9px;cursor:pointer}
  .project-tabs button.active{color:#fff;border-color:#c2152e;background:#211217}
  .project-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:14px}
  .project-card{display:flex;flex-direction:column;gap:14px;padding:18px;text-decoration:none;color:inherit;background:linear-gradient(145deg,#18181d,#121216);border:1px solid #292930;border-radius:16px;transition:.15s}
  .project-card:hover{transform:translateY(-2px);border-color:#4b3038}
  .project-card-top,.project-meta,.project-hero-top,.project-section-head{display:flex;align-items:center;justify-content:space-between;gap:12px}
  .project-code{font:700 11px/1.2 ui-monospace,monospace;letter-spacing:.08em;color:#e15b70}
  .project-card h3{margin:4px 0 0;font-size:18px}.project-card p{margin:0;color:#94949e;min-height:38px}
  .project-status{font-size:12px;padding:5px 9px;border:1px solid #34343c;border-radius:999px}.project-status.active{color:#86e0a2}.project-status.paused{color:#e8c66d}
  .project-progress{height:7px;border-radius:999px;background:#27272e;overflow:hidden}.project-progress i{display:block;height:100%;background:linear-gradient(90deg,#c2152e,#f16272)}
  .project-meta{font-size:12px;color:#90909a;justify-content:flex-start;flex-wrap:wrap}.project-meta span{padding:5px 8px;background:#202026;border-radius:8px}
  .project-hero{padding:22px;border:1px solid #2a2a32;border-radius:18px;background:radial-gradient(circle at 85% 0,rgba(194,21,46,.18),transparent 35%),#151519}
  .project-hero h1{font-size:28px;margin:6px 0}.project-hero p{max-width:820px;color:#a7a7b0}
  .project-kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:20px}.project-kpi{padding:13px;background:#1d1d22;border:1px solid #292930;border-radius:12px}.project-kpi b{display:block;font-size:22px}.project-kpi span{font-size:12px;color:#8f8f98}
  .project-layout{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:16px;margin-top:16px}
  .project-section{padding:18px;background:#151519;border:1px solid #292930;border-radius:16px}.project-section h2{margin:0;font-size:17px}
  .project-board{display:grid;grid-template-columns:repeat(2,minmax(230px,1fr));gap:10px;margin-top:14px}
  .project-column{background:#111115;border:1px solid #25252c;border-radius:12px;padding:10px;min-height:160px}.project-column>header{display:flex;justify-content:space-between;color:#a6a6af;font-size:12px;margin-bottom:10px}
  .project-task{padding:11px;margin-bottom:8px;background:#1b1b20;border:1px solid #292930;border-radius:10px}.project-task b{display:block;font-size:13px;margin:5px 0}.project-task small{color:#85858e}.project-task-teams{display:flex;gap:4px;flex-wrap:wrap;margin-top:8px}.project-task-teams span{font-size:10px;background:#282830;padding:3px 6px;border-radius:5px}
  .project-team-list,.project-people{display:flex;flex-direction:column;gap:8px;margin-top:12px}.project-team,.project-person{display:flex;align-items:center;gap:9px;padding:9px;background:#1d1d22;border-radius:10px;color:inherit;text-decoration:none}
  .project-team>div,.project-person>div{display:flex;min-width:0;flex-direction:column;gap:3px}.project-team small,.project-person small{display:block;color:#85858e}
  .project-avatar{width:30px;height:30px;border-radius:50%;background:#34343d;display:grid;place-items:center;font-size:11px;font-weight:700;background-size:cover;background-position:center}
  .project-empty{padding:36px;text-align:center;border:1px dashed #303038;border-radius:15px;color:#92929b}
  .project-task-dialog{width:min(560px,calc(100vw - 24px));border:1px solid #303038;border-radius:16px;background:#151519;color:inherit;padding:0}.project-task-dialog::backdrop{background:rgba(0,0,0,.72)}
  .project-task-form{display:flex;flex-direction:column;gap:12px;padding:20px}.project-task-form label{display:flex;flex-direction:column;gap:6px;color:#92929b;font-size:13px}.project-task-form input,.project-task-form select{padding:10px;border:1px solid #2b2b33;border-radius:9px;background:#1d1d22;color:inherit}
  .project-task[draggable]{cursor:grab}.project-task[draggable]:active{cursor:grabbing}.project-task.dragging{opacity:.45}
  .project-column.drop-target{outline:2px dashed #c2152e;outline-offset:-3px;background:#171019}
  @media(max-width:900px){.project-layout{grid-template-columns:1fr}.project-kpis{grid-template-columns:repeat(2,1fr)}}
  @media(max-width:620px){.project-board{grid-template-columns:1fr}}
  `;
  document.head.appendChild(style);
}

export async function projectsView(root) {
  injectStyles();
  setTopbar("Проекты");
  const content = root.querySelector("#project-content");
  const actions = root.querySelector("#project-actions");
  const manager = isManager();
  actions.innerHTML = manager && firstTeam()
    ? `<a class="btn btn-primary" href="/app/teams/${firstTeam().id}/insights?view=planner">Спланировать проект</a>`
    : "";
  let state = "active";
  let search = "";
  let data;
  try {
    data = await api.projects.list();
  } catch (error) {
    content.innerHTML = `<div class="note warn">${escapeHtml(error.message)}</div>`;
    return;
  }

  function render() {
    const items = (data.items || []).filter((project) => {
      const statusHit = state === "all" || project.status === state;
      const text = `${project.code} ${project.name} ${project.description || ""}`.toLowerCase();
      return statusHit && (!search || text.includes(search));
    });
    content.innerHTML = `
      <div class="project-toolbar">
        <input id="project-search" type="search" placeholder="Найти проект или код" value="${escapeHtml(search)}">
        <div class="project-tabs">
          ${[["active","В работе"],["paused","Пауза"],["completed","Завершены"],["all","Все"]].map(([key,label]) => `<button class="${state === key ? "active" : ""}" data-state="${key}">${label}</button>`).join("")}
        </div>
      </div>
      <div class="project-grid">${items.map(projectCard).join("") || '<div class="project-empty">В этом разделе пока нет проектов.</div>'}</div>`;
    content.querySelector("#project-search").oninput = (event) => {
      search = event.target.value.trim().toLowerCase();
      render();
      content.querySelector("#project-search")?.focus();
    };
    content.querySelectorAll("[data-state]").forEach((button) => {
      button.onclick = () => { state = button.dataset.state; render(); };
    });
  }
  render();
}

export async function projectDetailView(root, params, skipPull = false) {
  injectStyles();
  setTopbar("Проект");
  const content = root.querySelector("#project-content");
  const actions = root.querySelector("#project-actions");
  let project;
  try {
    project = await api.projects.get(params.projectId);
  } catch (error) {
    content.innerHTML = `<div class="note warn">${escapeHtml(error.message)}</div>`;
    return;
  }
  root.querySelector("#project-title").textContent = project.name;
  root.querySelector("#project-desc").textContent = `${project.code} · ${STATUS[project.status] || project.status}`;
  actions.innerHTML = `<a class="btn btn-ghost" href="/app/projects">Все проекты</a>${isManager() ? '<button class="btn btn-ghost" id="add-project-task">Добавить задачу</button><button class="btn btn-primary" id="sync-project">Синхронизировать YouGile</button>' : ""}`;
  const progress = project.stats.tasks ? Math.round(project.stats.done / project.stats.tasks * 100) : 0;
  content.innerHTML = `
    <section class="project-hero">
      <div class="project-hero-top"><span class="project-code">${escapeHtml(project.code)}</span><span class="project-status ${escapeHtml(project.status)}">${escapeHtml(STATUS[project.status] || project.status)}</span></div>
      <h1>${escapeHtml(project.name)}</h1>
      <p>${escapeHtml(project.description || project.expected_result || "Описание проекта пока не добавлено.")}</p>
      <div class="project-progress"><i style="width:${progress}%"></i></div>
      <div class="project-kpis">
        ${kpi(`${progress}%`, "готовность")}
        ${kpi(project.stats.tasks, "задач")}
        ${kpi(project.stats.teams, "команд")}
        ${kpi(project.stats.members, "участников")}
      </div>
    </section>
    <div class="project-layout">
      <main class="project-section">
        <div class="project-section-head"><h2>Рабочий поток</h2><span class="project-code">срок ${escapeHtml(formatDate(project.deadline))}</span></div>
        <div class="project-board">${["todo","in_progress","review","done"].map((status) => projectColumn(status, project.tasks || [])).join("")}</div>
      </main>
      <aside>
        <section class="project-section">
          <h2>Команды</h2>
          <div class="project-team-list">${(project.teams || []).map((team) => `<div class="project-team"><span class="project-avatar">${initials(team.name)}</span><div><b>${escapeHtml(team.name)}</b><small>${team.role === "lead" ? "ведущая команда" : "участник"} · ${team.allocation_percent}%</small></div></div>`).join("")}</div>
        </section>
        <section class="project-section" style="margin-top:12px">
          <h2>Участники</h2>
          <div class="project-people">${(project.members || []).slice(0, 12).map((person) => personCard(person)).join("")}</div>
        </section>
      </aside>
    </div>`;
  actions.querySelector("#sync-project")?.addEventListener("click", async (event) => {
    event.currentTarget.disabled = true;
    try {
      const result = await api.projects.syncYougile(project.id);
      toast(result.ok ? "Проект синхронизирован с YouGile" : (result.error || "Синхронизация не выполнена"), result.ok ? "ok" : "warn");
    } finally {
      event.currentTarget.disabled = false;
    }
  });
  actions.querySelector("#add-project-task")?.addEventListener("click", () => {
    openProjectTaskDialog(root, project, () => projectDetailView(root, params));
  });
  bindProjectBoardDnd(content, () => projectDetailView(root, params, true));

  if (!skipPull) {
    // Reflect YouGile-side changes (cards moved in YouGile) back onto the board.
    api.projects.pullYougile(project.id)
      .then((result) => {
        const statuses = Number(result?.updated_statuses || 0);
        const comments = Number(result?.imported_comments || 0);
        if (statuses > 0 || comments > 0) {
          const changes = [
            statuses > 0 ? `${statuses} статусов` : "",
            comments > 0 ? `${comments} комментариев` : "",
          ].filter(Boolean).join(", ");
          toast(`Обновлено из YouGile: ${changes}`);
          projectDetailView(root, params, true);
        }
      })
      .catch(() => {});
  }
}

function bindProjectBoardDnd(content, reload) {
  const board = content.querySelector(".project-board");
  if (!board) return;
  board.querySelectorAll(".project-task[data-task-id]").forEach((card) => {
    card.addEventListener("dragstart", (event) => {
      card.classList.add("dragging");
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", card.dataset.taskId);
    });
    card.addEventListener("dragend", () => card.classList.remove("dragging"));
  });
  board.querySelectorAll(".project-column[data-status]").forEach((column) => {
    column.addEventListener("dragover", (event) => {
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
      column.classList.add("drop-target");
    });
    column.addEventListener("dragleave", (event) => {
      if (!column.contains(event.relatedTarget)) column.classList.remove("drop-target");
    });
    column.addEventListener("drop", async (event) => {
      event.preventDefault();
      column.classList.remove("drop-target");
      const taskId = event.dataTransfer.getData("text/plain");
      const target = column.dataset.status;
      const card = board.querySelector(`.project-task[data-task-id="${taskId}"]`);
      if (!card || card.dataset.status === target) return;
      card.dataset.status = target;
      column.appendChild(card);
      try {
        const result = await api.tasks.move(taskId, target);
        const sync = result.sync_status;
        toast(
          sync === "error" || sync === "conflict"
            ? "Статус сохранён, YouGile вернул ошибку"
            : sync === "local_only"
              ? "Статус сохранён, YouGile не подключён"
              : "Готово, синхронизировано с YouGile",
          sync === "error" || sync === "conflict" ? "warn" : "ok",
        );
      } catch (error) {
        toast(error.message || "Не удалось перенести задачу", "warn");
      }
      await reload();
    });
  });
}

function projectCard(project) {
  const progress = project.stats.tasks ? Math.round(project.stats.done / project.stats.tasks * 100) : 0;
  return `<a class="project-card" href="/app/projects/${project.id}">
    <div class="project-card-top"><div><span class="project-code">${escapeHtml(project.code)}</span><h3>${escapeHtml(project.name)}</h3></div><span class="project-status ${escapeHtml(project.status)}">${escapeHtml(STATUS[project.status] || project.status)}</span></div>
    <p>${escapeHtml(project.expected_result || project.description || "Цель проекта не описана")}</p>
    <div class="project-progress"><i style="width:${progress}%"></i></div>
    <div class="project-meta"><span>${progress}%</span><span>${project.stats.tasks} задач</span><span>${project.stats.teams} команд</span>${project.stats.blocked ? `<span>${project.stats.blocked} блокеров</span>` : ""}</div>
  </a>`;
}

function projectColumn(status, tasks) {
  const titles = { todo: "К выполнению", in_progress: "В работе", review: "Проверка", done: "Готово" };
  const items = tasks.filter((task) => task.status === status);
  return `<section class="project-column" data-status="${escapeHtml(status)}"><header><b>${titles[status]}</b><span>${items.length}</span></header>${items.map(taskCard).join("") || '<div class="dim">Нет задач</div>'}</section>`;
}

function taskCard(task) {
  return `<article class="project-task" draggable="true" data-task-id="${escapeHtml(task.id)}" data-status="${escapeHtml(task.status)}"><span class="project-code">${escapeHtml(task.public_id)}</span><b>${escapeHtml(task.title)}</b><small>${task.deadline ? escapeHtml(formatDate(task.deadline)) : "Без срока"}</small><div class="project-task-teams">${(task.teams || []).map((team) => `<span>${escapeHtml(team.name)}</span>`).join("")}</div></article>`;
}

function personCard(person) {
  const style = person.photo_data_url ? `style="background-image:url('${escapeHtml(person.photo_data_url)}')"` : "";
  return `<a class="project-person" href="/app/people/${person.id}"><span class="project-avatar" ${style}>${person.photo_data_url ? "" : initials(person.display_name)}</span><div><b>${escapeHtml(person.display_name)}</b><small>${person.role === "manager" ? "руководитель" : "участник"}</small></div></a>`;
}

function kpi(value, label) {
  return `<div class="project-kpi"><b>${escapeHtml(value)}</b><span>${escapeHtml(label)}</span></div>`;
}

function initials(value) {
  return escapeHtml((value || "?").split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase());
}

function isManager() {
  const user = window.gcCurrentUser || {};
  return Boolean(user.companies?.length || user.teams?.some((team) => team.role === "manager"));
}

function firstTeam() {
  return window.gcCurrentUser?.teams?.[0] || null;
}

function openProjectTaskDialog(root, project, reload) {
  const dialog = document.createElement("dialog");
  dialog.className = "project-task-dialog";
  const teamOptions = (project.teams || []).map((team) => `<option value="${escapeHtml(team.id)}">${escapeHtml(team.name)}</option>`).join("");
  const memberOptions = (project.members || []).map((person) => `<option value="${escapeHtml(person.id)}">${escapeHtml(person.display_name)}</option>`).join("");
  dialog.innerHTML = `<form method="dialog" class="project-task-form">
    <div class="project-section-head"><h2>Новая задача проекта</h2><button class="btn btn-ghost" value="cancel">Закрыть</button></div>
    <label>Название<input id="new-project-task-title" required maxlength="240"></label>
    <label>Команда-владелец<select id="new-project-task-team">${teamOptions}</select></label>
    <label>Исполнители<select id="new-project-task-members" multiple size="6">${memberOptions}</select></label>
    <label>Срок<input id="new-project-task-deadline" type="datetime-local"></label>
    <button class="btn btn-primary" id="save-project-task" type="button">Создать задачу</button>
  </form>`;
  document.body.appendChild(dialog);
  dialog.addEventListener("close", () => dialog.remove());
  dialog.querySelector("#save-project-task").onclick = async (event) => {
    const title = dialog.querySelector("#new-project-task-title").value.trim();
    if (!title) return;
    const ownerTeamId = dialog.querySelector("#new-project-task-team").value;
    const assigneeIds = [...dialog.querySelector("#new-project-task-members").selectedOptions].map((option) => option.value);
    const deadline = dialog.querySelector("#new-project-task-deadline").value;
    event.currentTarget.disabled = true;
    try {
      await api.projects.createTask(project.id, {
        title,
        owner_team_id: ownerTeamId,
        team_ids: [ownerTeamId],
        assignee_ids: assigneeIds,
        deadline: deadline ? new Date(deadline).toISOString() : null,
      });
      dialog.close();
      toast("Задача добавлена в проект");
      await reload();
    } catch (error) {
      event.currentTarget.disabled = false;
      toast(error.message || "Не удалось создать задачу", "warn");
    }
  };
  dialog.showModal();
}

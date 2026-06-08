import { api } from "../api.js";
import { escapeHtml, setTopbar, toast } from "../view-utils.js";

export default async function aiInboxView(root, params) {
  setTopbar("Входящие AI");
  const content = root.querySelector("#inbox-content");
  let filter = "pending";
  const members = await api.teams.members(params.teamId).then((data) => data.items).catch(() => []);

  async function load() {
    content.innerHTML = '<div class="view-loading">Загружаем очередь...</div>';
    const items = await api.aiInbox.list(params.teamId);
    const visible = filter === "all" ? items : items.filter((item) => item.status === filter);
    content.innerHTML = visible.length ? visible.map((item) => renderItem(item, members)).join("") : '<div class="note">Очередь пуста.</div>';
    content.querySelectorAll("[data-approve]").forEach((button) => {
      button.onclick = async () => {
        const assigneeId = content.querySelector(`[data-assignee="${button.dataset.approve}"]`)?.value;
        if (assigneeId) await api.aiInbox.assign(button.dataset.approve, assigneeId);
        await api.aiInbox.approve(button.dataset.approve);
        toast("Задача создана во внутренней Grey Board");
        await load();
      };
    });
    content.querySelectorAll("[data-reject]").forEach((button) => {
      button.onclick = async () => {
        await api.aiInbox.reject(button.dataset.reject);
        toast("Сигнал отклонён");
        await load();
      };
    });
  }

  root.querySelector("#inbox-filter").onclick = async (event) => {
    const button = event.target.closest("[data-status]");
    if (!button) return;
    filter = button.dataset.status;
    root.querySelectorAll("#inbox-filter button").forEach((item) => item.classList.toggle("active", item === button));
    await load();
  };
  await load();
}

function renderItem(item, members) {
  const task = item.semantic?.task || {};
  const selectedAssignee = item.identity?.user_id || "";
  const memberOptions = [
    '<option value="">Без исполнителя</option>',
    ...members.map((member) => `<option value="${member.id}" ${selectedAssignee === member.id ? "selected" : ""}>${escapeHtml(member.display_name)}</option>`),
  ].join("");
  return `<article class="inbox-item">
    <div class="inbox-main">
      <div class="flex gap-8"><span class="tag">${escapeHtml(item.kind)}</span><span class="pill ${item.status === "pending" ? "warn" : "idle"}">${escapeHtml(item.status)}</span></div>
      <h3>${escapeHtml(task.title || item.raw_text)}</h3>
      <p>${escapeHtml(item.raw_text)}</p>
      <div class="task-meta"><span>Причина: ${escapeHtml(item.reason)}</span><span>Уверенность: ${Math.round(item.confidence * 100)}%</span></div>
    </div>
    ${item.status === "pending" ? `<div class="inbox-actions"><select class="input" data-assignee="${item.id}">${memberOptions}</select><button class="btn btn-sm btn-primary" data-approve="${item.id}">Создать в Grey Board</button><button class="btn btn-sm btn-ghost" data-reject="${item.id}">Отклонить</button></div>` : ""}
  </article>`;
}

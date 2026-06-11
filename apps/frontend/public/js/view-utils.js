import { ApiError } from "./api.js";

export function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
}

export function formatDate(value) {
  if (!value) return "не указано";
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function currentTeam(user, id = null) {
  const teams = user?.teams || [];
  if (id != null) {
    return teams.find((team) => String(team.id) === String(id)) || teams[0] || null;
  }
  const selected = typeof window !== "undefined" && window.gcSelectedTeamId ? window.gcSelectedTeamId() : null;
  return teams.find((team) => String(team.id) === String(selected)) || teams[0] || null;
}

export function setTopbar(title, actions = "") {
  const topbar = document.getElementById("app-topbar");
  if (topbar) topbar.innerHTML = `<button class="mobile-menu" type="button" aria-label="Открыть меню">${window.gcIcon("menu")}</button><div class="crumb"><b>${escapeHtml(title)}</b></div><div class="grow"></div>${actions}`;
}

export function toast(message, kind = "ok") {
  const stack = document.getElementById("toast-stack");
  if (!stack) return;
  const element = document.createElement("div");
  element.className = `toast ${kind}`;
  element.textContent = message;
  stack.append(element);
  setTimeout(() => element.remove(), 3500);
}

export function errorMessage(error) {
  if (!(error instanceof ApiError)) return "Не удалось загрузить данные";
  if (error.status === 404) return "Backend пока не предоставляет эти данные";
  if (error.status === 403) return "Недостаточно прав";
  if (error.status === 409) return typeof error.code === "string" ? error.code : "Конфликт данных";
  return typeof error.code === "string" ? error.code : "Ошибка API";
}

export function emptyState(title, text, action = "") {
  return `<div class="empty-state"><div class="page-title">${escapeHtml(title)}</div><p class="page-desc">${escapeHtml(text)}</p>${action}</div>`;
}

export function bindForm(root, selector, handler) {
  const form = root.querySelector(selector);
  if (!form) return;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = form.querySelector('[type="submit"]');
    submit?.setAttribute("disabled", "");
    try {
      await handler(new FormData(form), form);
    } finally {
      submit?.removeAttribute("disabled");
    }
  });
}

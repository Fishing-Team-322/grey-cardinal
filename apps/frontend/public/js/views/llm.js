import { api } from "../api.js";
import { currentTeam, errorMessage, escapeHtml, setTopbar, toast } from "../view-utils.js";

export default async function llmView(root) {
  setTopbar("LLM");
  const content = root.querySelector("#llm-content");
  const managed = window.gcCurrentUser.teams?.filter((team) => team.role === "manager") || [];
  let team = currentTeam({ teams: managed }, new URLSearchParams(location.search).get("team"));
  if (!team) {
    content.innerHTML = '<div class="note warn">Для настройки LLM нужна роль руководителя команды.</div>';
    return;
  }
  content.insertAdjacentHTML(
    "beforebegin",
    `<div class="flex gap-12 mb-16"><select id="llm-team">${managed
      .map((item) => `<option value="${item.id}" ${item.id === team.id ? "selected" : ""}>${escapeHtml(item.name)}</option>`)
      .join("")}</select></div>`,
  );
  root.querySelector("#llm-team").onchange = () => {
    team = managed.find((item) => item.id === root.querySelector("#llm-team").value);
    render(content, team);
  };
  await render(content, team);
}

function providerCard(title, data, latency) {
  if (!data) return "";
  const rows = [
    ["Провайдер", data.provider],
    ["Base URL", data.base_url],
    ["Модель", data.model],
  ]
    .filter(([, value]) => value)
    .map(([label, value]) => `<div class="flex between gap-8"><span class="dim">${label}</span><span class="mono">${escapeHtml(String(value))}</span></div>`)
    .join("");
  const lat = latency != null ? `<div class="flex between gap-8"><span class="dim">Latency</span><span class="mono">${latency} ms</span></div>` : "";
  return `<div class="card card-pad"><div class="card-head"><div class="card-title">${title}</div></div>${rows}${lat}</div>`;
}

async function render(content, team) {
  content.innerHTML = '<div class="view-loading">Проверяем LLM...</div>';
  let health;
  try {
    health = await api.llm.health(team.id);
  } catch (error) {
    content.innerHTML = `<div class="note warn">${escapeHtml(errorMessage(error))}</div>`;
    return;
  }

  const ok = health.status === "ok";
  const primary = health.primary || {};
  const fallback = health.fallback || {};
  const primaryLatency = primary.latency_ms;
  const fallbackEnabled = fallback.enabled === true;

  const statusPill = ok
    ? '<span class="pill ok"><span class="dot"></span>работает</span>'
    : '<span class="pill warn"><span class="dot"></span>ошибка</span>';

  const primaryError = primary.error
    ? `<div class="note warn mt-12">Primary недоступен: ${escapeHtml(String(primary.error))}${primary.message ? ` (${escapeHtml(String(primary.message))})` : ""}</div>`
    : "";

  const fallbackWarn = fallbackEnabled
    ? ""
    : '<div class="note warn mt-12">⚠️ Fallback-провайдер не настроен. Рекомендуем включить OpenRouter как резерв (LLM_FALLBACK_ENABLED=true), иначе при сбое Groq бот останется без классификации.</div>';

  const fallbackStatus = fallbackEnabled
    ? `<div class="flex between gap-8"><span class="dim">Статус</span><span class="pill ${fallback.status === "error" ? "warn" : "ok"}">${escapeHtml(String(fallback.status || "configured"))}</span></div>`
    : '<div class="dim">Не настроен</div>';

  content.innerHTML = `
    <div class="card card-pad"><div class="card-head"><div class="card-title">Статус LLM</div>${statusPill}</div>
      <div class="dim">Семантический парсер русских сообщений: Groq (primary) → OpenRouter (fallback).</div>
      ${primaryError}${fallbackWarn}
      <div class="flex gap-8 mt-16"><button class="btn btn-primary" id="llm-check">Проверить LLM</button></div>
    </div>
    <div class="grid g2 mt-20">
      ${providerCard("Primary", primary.provider ? primary : { provider: primary.provider, model: primary.model }, primaryLatency)}
      <div class="card card-pad"><div class="card-head"><div class="card-title">Fallback</div></div>
        ${fallbackEnabled ? `<div class="flex between gap-8"><span class="dim">Провайдер</span><span class="mono">${escapeHtml(String(fallback.provider || ""))}</span></div>
        ${fallback.base_url ? `<div class="flex between gap-8"><span class="dim">Base URL</span><span class="mono">${escapeHtml(String(fallback.base_url))}</span></div>` : ""}
        <div class="flex between gap-8"><span class="dim">Модель</span><span class="mono">${escapeHtml(String(fallback.model || ""))}</span></div>` : ""}
        ${fallbackStatus}
      </div>
    </div>`;

  content.querySelector("#llm-check").onclick = async () => {
    toast("Проверяем провайдер...");
    await render(content, team);
  };
}

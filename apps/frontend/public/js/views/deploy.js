import { api } from "../api.js";
import { escapeHtml, formatDate, setTopbar } from "../view-utils.js";

export default async function deployView(root) {
  setTopbar("Деплой");
  const data = await api.deploy.status();
  root.querySelector("#deploy-content").innerHTML = `<div class="grid g3">
    <div class="stat"><div class="stat-label">Frontend</div><div class="stat-value" style="font-size:20px;color:var(--ok)">Static Caddy</div></div>
    <div class="stat"><div class="stat-label">Auth</div><div class="stat-value" style="font-size:20px;color:var(--ok)">httpOnly cookie</div></div>
    <div class="stat"><div class="stat-label">WebSocket</div><div class="stat-value" style="font-size:20px;color:var(--ok)">Single connection</div></div>
  </div><div class="card card-pad mt-20"><div class="card-head"><div class="card-title">Production status</div><span class="pill ok"><span class="dot"></span>${escapeHtml(data.status)}</span></div><div class="integration-row"><span>Окружение</span><b>${escapeHtml(data.environment)}</b></div><div class="integration-row"><span>Версия API</span><b>${escapeHtml(data.version)}</b></div><div class="integration-row"><span>Проверено</span><b>${formatDate(data.checked_at)}</b></div></div>`;
}

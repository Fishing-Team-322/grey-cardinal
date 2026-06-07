import { api } from "../api.js";
import { currentTeam, escapeHtml, setTopbar } from "../view-utils.js";

export default async function integrationsView(root) {
  setTopbar("Интеграции");
  const content = root.querySelector("#integrations-content");
  const team = currentTeam(window.gcCurrentUser, new URLSearchParams(location.search).get("team"));
  const [personalTelegram, teamTelegram, yougile, agents, telemost, llm] = await Promise.all([
    api.telegram.status().catch(() => ({ linked: false })),
    team ? api.teams.telegramStatus(team.id).catch(() => ({ linked: false })) : { linked: false },
    team ? api.yougile.status(team.id).catch(() => ({ connected: false })) : { connected: false },
    api.daemon.status().catch(() => ({ agents: [] })),
    api.telemost.status().catch(() => ({ available: false })),
    team ? api.llm.health(team.id).catch(() => ({ status: "error" })) : { status: "error" },
  ]);
  content.innerHTML = `<div class="card card-pad">
    ${row("Личный Telegram", personalTelegram.linked, "/app/integrations/telegram", personalTelegram.telegram_username ? `@${escapeHtml(personalTelegram.telegram_username)}` : "")}
    ${row("Командный Telegram", teamTelegram.linked, "/app/integrations/telegram", team?.name || "")}
    ${row("YouGile", yougile.connected, "/app/integrations/yougile", team?.name || "")}
    ${row("LLM (семантика)", llm.status === "ok", "/app/integrations/llm", llm.primary?.provider || "")}
    ${row("Windows Agent", agents.agents.length > 0, "/app/integrations/daemon", `${agents.agents.length} устройств`)}
    ${row("Yandex Telemost", telemost.available, "/app/integrations/telemost", telemost.provider || "")}
  </div>`;
}

function row(name, connected, href, detail) {
  return `<a class="integration-row" href="${href}"><span><b>${name}</b>${detail ? `<span class="meta">${detail}</span>` : ""}</span><span class="pill ${connected ? "ok" : "warn"}"><span class="dot"></span>${connected ? "connected" : "настроить"}</span></a>`;
}

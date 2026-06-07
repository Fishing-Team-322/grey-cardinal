import { api } from "../api.js";
import { escapeHtml, formatDate, setTopbar, toast } from "../view-utils.js";

export default async function daemonView(root) {
  setTopbar("Desktop Agent");
  const content = root.querySelector("#daemon-content");
  let timer;

  async function render() {
    const data = await api.daemon.status().catch(() => ({ agents: [] }));
    content.innerHTML = `<div class="grid g2">
      <div class="card card-pad"><div class="card-head"><div class="card-title">Установка</div></div>
        <p class="dim">Windows-агент записывает системное аудио и отправляет его на обработку.</p>
        <a class="btn btn-primary mt-16" href="/downloads/GreyCardinalAgentSetup.exe">Скачать для Windows</a>
        <button class="btn btn-ghost mt-16" id="pair-agent">Получить код привязки</button><div id="pairing-code" class="mt-16"></div>
      </div>
      <div class="card card-pad"><div class="card-head"><div class="card-title">Устройства</div><span class="pill ${data.agents.some((agent) => agent.online) ? "ok" : "idle"}"><span class="dot"></span>${data.agents.filter((agent) => agent.online).length} online</span></div>
        ${data.agents.map((agent) => `<div class="integration-row"><span><b>${escapeHtml(agent.device_name)}</b><span class="meta">${escapeHtml(agent.platform)} · ${agent.last_seen_at ? formatDate(agent.last_seen_at) : "не выходил на связь"}</span></span><span class="pill ${agent.online ? "ok" : "idle"}"><span class="dot"></span>${agent.online ? "online" : "offline"}</span></div>`).join("") || '<div class="dim">Привязанных устройств пока нет.</div>'}
      </div>
    </div>`;
    content.querySelector("#pair-agent").onclick = async () => {
      const result = await api.daemon.pairingCode();
      content.querySelector("#pairing-code").innerHTML = `<div class="code-msg" style="font-size:24px;text-align:center">${escapeHtml(result.pairing_code)}</div><div class="faint mt-8">Действует до ${formatDate(result.expires_at)}</div>`;
      toast("Код создан");
    };
  }
  await render();
  timer = setInterval(render, 5000);
  return () => clearInterval(timer);
}

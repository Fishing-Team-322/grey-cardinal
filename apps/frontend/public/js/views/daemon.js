import { api } from "../api.js";
import { escapeHtml, formatDate, setTopbar, toast } from "../view-utils.js";

export default async function daemonView(root) {
  setTopbar("Windows Agent");
  const content = root.querySelector("#daemon-content");
  let timer;
  let pairing = null;

  async function render() {
    const data = await api.daemon.status().catch(() => ({ agents: [] }));
    content.innerHTML = `<div class="grid g2">
      <div class="card card-pad"><div class="card-head"><div class="card-title">Установка</div></div>
        <p class="dim">Windows-агент работает в трее. Запись запускается и останавливается только вручную из меню агента.</p>
        <a class="btn btn-primary mt-16" href="/downloads/GreyCardinalAgent-x64.msi?v=0.6.5" download>Скачать MSI для Windows</a>
        <p class="faint mt-12">Установите MSI, запустите Grey Cardinal Agent из меню «Пуск», затем откройте значок в трее и выберите «Привязать по коду».</p>
        <button class="btn btn-ghost mt-16" id="pair-agent">Получить код привязки</button>
        <div id="pairing-code" class="mt-16">${pairing ? pairingHtml(pairing) : ""}</div>
      </div>
      <div class="card card-pad"><div class="card-head"><div class="card-title">Устройства</div><span class="pill ${data.agents.some((agent) => agent.online) ? "ok" : "idle"}"><span class="dot"></span>${data.agents.filter((agent) => agent.online).length} online</span></div>
        ${data.agents.map((agent) => `<div class="integration-row"><span><b>${escapeHtml(agent.device_name)}</b><span class="meta">${escapeHtml(agent.platform)} · ${agent.last_seen_at ? formatDate(agent.last_seen_at) : "не выходил на связь"}</span></span><span class="flex gap-8 center"><span class="pill ${agent.online ? "ok" : "idle"}"><span class="dot"></span>${agent.online ? "online" : "offline"}</span><button class="btn btn-sm btn-ghost unpair-agent" type="button" data-agent-id="${agent.agent_id}" data-agent-name="${escapeHtml(agent.device_name)}">Отвязать</button></span></div>`).join("") || '<div class="dim">Привязанных устройств пока нет.</div>'}
      </div>
    </div>`;
    content.querySelector("#pair-agent").onclick = async () => {
      pairing = await api.daemon.pairingCode();
      content.querySelector("#pairing-code").innerHTML = pairingHtml(pairing);
      bindCopy();
      toast("Код создан");
    };
    content.querySelectorAll(".unpair-agent").forEach((button) => {
      button.onclick = async () => {
        const deviceName = button.dataset.agentName || "это устройство";
        if (!window.confirm(`Отвязать ${deviceName}? Агент на этом устройстве потеряет доступ.`)) return;
        button.disabled = true;
        try {
          await api.daemon.unpair(button.dataset.agentId);
          toast("Устройство отвязано");
          await render();
        } catch (error) {
          button.disabled = false;
          toast("Не удалось отвязать устройство");
        }
      };
    });
    bindCopy();
  }

  function pairingHtml(result) {
    return `<div class="code-msg" style="font-size:24px;text-align:center">${escapeHtml(result.pairing_code)}</div>
      <button class="btn btn-ghost mt-8" id="copy-pairing-code">Скопировать код</button>
      <div class="faint mt-8">Действует до ${formatDate(result.expires_at)} и не исчезнет при обновлении списка устройств.</div>`;
  }

  function bindCopy() {
    const button = content.querySelector("#copy-pairing-code");
    if (!button || !pairing) return;
    button.onclick = async () => {
      await navigator.clipboard.writeText(pairing.pairing_code);
      toast("Код скопирован");
    };
  }

  await render();
  timer = setInterval(render, 5000);
  return () => clearInterval(timer);
}

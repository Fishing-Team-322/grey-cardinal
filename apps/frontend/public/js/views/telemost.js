import { api } from "../api.js";
import { currentTeam, escapeHtml, setTopbar, toast } from "../view-utils.js";

const STATUS_PILL = {
  connected: { cls: "ok", label: "connected" },
  expired: { cls: "warn", label: "reconnect required" },
  error: { cls: "warn", label: "error" },
  disconnected: { cls: "warn", label: "not connected" },
};

export default async function telemostView(root) {
  setTopbar("Yandex Telemost");
  const content = root.querySelector("#telemost-content");
  const team = currentTeam(window.gcCurrentUser, new URLSearchParams(location.search).get("team"));

  // Surface the OAuth callback result (?connected=1 / ?error=...).
  const params = new URLSearchParams(location.search);
  if (params.get("connected")) toast("Яндекс Телемост подключён");
  if (params.get("error")) toast(`Не удалось подключить Телемост: ${params.get("error")}`);

  if (!team) {
    content.innerHTML = `<div class="card card-pad">Сначала выберите команду.</div>`;
    return;
  }

  async function render() {
    const status = await api.yandexTelemost
      .status(team.id)
      .catch(() => ({ status: "error", connected: false, server_configured: false }));
    const pill = STATUS_PILL[status.status] || STATUS_PILL.disconnected;
    const settings = status.settings || {};

    content.innerHTML = `<div class="card card-pad-lg" style="max-width:760px">
      <div class="card-head">
        <div class="card-title">Yandex Telemost</div>
        <span class="pill ${pill.cls}"><span class="dot"></span>${pill.label}</span>
      </div>
      <p class="page-desc mt-12">Создавайте ссылки Яндекс Телемоста прямо из Telegram-чата.
        Grey Cardinal сможет присылать summary и задачи после встречи.</p>
      ${status.server_configured ? "" : `<div class="alert alert-error mt-12">Сервер не настроен:
        не заданы YANDEX_TELEMOST_CLIENT_ID/SECRET. Обратитесь к администратору.</div>`}
      ${status.expires_at ? `<div class="faint mt-8">Токен действует до ${escapeHtml(status.expires_at)}</div>` : ""}

      <div class="flex gap-10 mt-16">
        ${
          status.connected
            ? `<button class="btn btn-ghost" id="tm-reconnect">Reconnect</button>
               <button class="btn btn-ghost" id="tm-disconnect">Disconnect</button>
               <button class="btn btn-primary" id="tm-test">Test create room</button>`
            : `<button class="btn btn-primary" id="tm-connect" ${status.server_configured ? "" : "disabled"}>Connect Yandex Telemost</button>`
        }
      </div>
      <div id="tm-test-result" class="mt-12"></div>

      <div class="card card-pad mt-20">
        <div class="card-title">Настройки</div>
        <label class="flex center gap-10 mt-12">
          <input type="checkbox" id="tm-autojoin" ${settings.enable_meeting_agent_auto_join ? "checked" : ""}>
          <span>Подключать meeting agent к встрече автоматически</span>
        </label>
        <label class="flex center gap-10 mt-8">
          <input type="checkbox" checked disabled>
          <span class="dim">Всегда писать в чат уведомление о записи ИИ (обязательно)</span>
        </label>
        <label class="col mt-12">Шаблон названия встречи
          <input class="input mt-6" id="tm-title" value="${escapeHtml(settings.default_title_template || "")}">
        </label>
        <button class="btn btn-ghost mt-12" id="tm-save">Сохранить настройки</button>
      </div>
    </div>`;

    const byId = (id) => content.querySelector(`#${id}`);

    byId("tm-connect")?.addEventListener("click", async () => {
      const { authorization_url } = await api.yandexTelemost.connectStart(team.id);
      window.location.href = authorization_url;
    });
    byId("tm-reconnect")?.addEventListener("click", async () => {
      const { authorization_url } = await api.yandexTelemost.connectStart(team.id);
      window.location.href = authorization_url;
    });
    byId("tm-disconnect")?.addEventListener("click", async () => {
      await api.yandexTelemost.disconnect(team.id);
      toast("Отключено");
      await render();
    });
    byId("tm-test")?.addEventListener("click", async () => {
      try {
        const res = await api.yandexTelemost.testCreateRoom(team.id);
        byId("tm-test-result").innerHTML = `<div class="alert">Комната создана:
          <a href="${escapeHtml(res.join_url)}" target="_blank" rel="noopener">${escapeHtml(res.join_url)}</a></div>`;
      } catch (e) {
        byId("tm-test-result").innerHTML = `<div class="alert alert-error">Не удалось создать комнату: ${escapeHtml(e.code || "error")}</div>`;
      }
    });
    byId("tm-save")?.addEventListener("click", async () => {
      await api.yandexTelemost.saveSettings(team.id, {
        enable_meeting_agent_auto_join: byId("tm-autojoin").checked,
        default_title_template: byId("tm-title").value,
      });
      toast("Настройки сохранены");
      await render();
    });
  }

  await render();
}

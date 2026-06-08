import { api } from "../api.js";
import { bindForm, errorMessage, escapeHtml, setTopbar, toast } from "../view-utils.js";

export default async function settingsView(root) {
  setTopbar("Настройки");
  const user = await api.auth.me();
  const content = root.querySelector("#settings-content");
  const telegram = await api.telegram.status().catch(() => ({ linked: false }));
  const agents = await api.daemon.status().catch(() => ({ agents: [] }));
  const zones = typeof Intl.supportedValuesOf === "function"
    ? Intl.supportedValuesOf("timeZone")
    : ["Europe/Moscow", "Europe/London", "Asia/Dubai"];
  const currentZone = user.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone;
  content.innerHTML = `<div class="grid g2">
    <form class="card card-pad col gap-16" id="profile-form">
      <div class="card-head"><div class="card-title">Профиль</div></div>
      <label>Email<input class="input mt-6" value="${escapeHtml(user.email)}" readonly></label>
      <label>Отображаемое имя<input class="input mt-6" name="display_name" value="${escapeHtml(user.display_name)}" required></label>
      <label>Имя<input class="input mt-6" name="first_name" value="${escapeHtml(user.first_name)}"></label>
      <label>Фамилия<input class="input mt-6" name="last_name" value="${escapeHtml(user.last_name)}"></label>
      <label>Часовой пояс<select class="mt-6" name="timezone">${zones.map((zone) => `<option ${zone === currentZone ? "selected" : ""}>${escapeHtml(zone)}</option>`).join("")}</select></label>
      <button class="btn btn-primary" type="submit">Сохранить</button><div class="alert alert-error" id="profile-error" hidden></div>
    </form>
    <div class="col gap-16">
      <div class="card card-pad"><div class="card-head"><div class="card-title">Подключения</div></div>
        <a class="integration-row" href="/app/integrations/telegram"><span>Telegram</span><span class="pill ${telegram.linked ? "ok" : "warn"}">${telegram.linked ? "привязан" : "настроить"}</span></a>
        <a class="integration-row" href="/app/integrations/daemon"><span>Windows-агент</span><span class="pill ${agents.agents.length ? "ok" : "warn"}">${agents.agents.length} устройств</span></a>
      </div>
      <form class="card card-pad col gap-16" id="password-form"><div class="card-head"><div class="card-title">Безопасность</div></div><label>Текущий пароль<input class="input mt-6" type="password" name="old_password" required></label><label>Новый пароль<input class="input mt-6" type="password" name="new_password" minlength="6" required></label><button class="btn btn-primary" type="submit">Сменить пароль</button><div class="alert alert-error" id="password-error" hidden></div><button class="btn btn-ghost" type="button" id="logout">Выйти</button></form>
    </div>
  </div>`;
  bindForm(root, "#profile-form", async (data) => {
    try {
      const updated = await api.auth.update({
        display_name: data.get("display_name"),
        first_name: data.get("first_name"),
        last_name: data.get("last_name"),
        timezone: data.get("timezone"),
      });
      window.gcCurrentUser = { ...window.gcCurrentUser, ...updated };
      window.gcSidebar(window.gcCurrentUser, window.gcCurrentUser.companies?.length ? "director" : window.gcCurrentUser.teams?.some((team) => team.role === "manager") ? "manager" : "employee");
      toast("Профиль сохранён");
    } catch (error) {
      const element = root.querySelector("#profile-error");
      element.textContent = errorMessage(error);
      element.hidden = false;
    }
  });
  bindForm(root, "#password-form", async (data, form) => {
    try {
      await api.auth.changePassword(data.get("old_password"), data.get("new_password"));
      form.reset();
      toast("Пароль изменён");
    } catch (error) {
      const element = root.querySelector("#password-error");
      element.textContent = errorMessage(error);
      element.hidden = false;
    }
  });
  root.querySelector("#logout").onclick = async () => {
    await api.auth.logout();
    location.href = "/";
  };
}

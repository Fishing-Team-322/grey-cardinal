import { api } from "../api.js";
import { bindForm, errorMessage, escapeHtml, setTopbar, toast } from "../view-utils.js";

export default async function settingsView(root) {
  setTopbar("Настройки");
  const user = { ...(window.gcCurrentUser || {}), ...(await api.auth.me()) };
  const content = root.querySelector("#settings-content");
  const telegram = await api.telegram.status().catch(() => ({ linked: false }));
  const agents = await api.daemon.status().catch(() => ({ agents: [] }));
  const managerTeam = (user.teams || []).find((team) => team.role === "manager");
  const botSettings = managerTeam
    ? await api.teams.botSettings(managerTeam.id).catch(() => null)
    : null;
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
      ${botSettings ? `<form class="card card-pad col gap-16" id="bot-behavior-form">
        <div class="card-head"><div><div class="card-title">Поведение Telegram-бота</div><div class="meta">${escapeHtml(botSettings.team_name)}</div></div></div>
        <label class="integration-row">
          <span class="col gap-8"><b>Отвечать только по имени</b><span class="meta">Обрабатывать сообщения, начинающиеся с «Кардинал»</span></span>
          <input type="checkbox" name="require_cardinal_mention" ${botSettings.require_cardinal_mention ? "checked" : ""}>
        </label>
        <button class="btn btn-primary" type="submit">Сохранить поведение бота</button>
        <div class="alert alert-error" id="bot-behavior-error" hidden></div>
      </form>
      <div class="card card-pad col gap-12" id="emotion-card">
        <div class="card-head"><div><div class="card-title">Эмоциональный анализ команды</div><div class="meta">${escapeHtml(botSettings.team_name)}</div></div>
          <span class="pill ${botSettings.emotion_analysis ? "ok" : "idle"}" id="emotion-pill"><span class="dot"></span>${botSettings.emotion_analysis ? "включён" : "выключен"}</span></div>
        <p class="meta" style="line-height:1.5">Оценивает <b>настроение и тонус команды</b> по сообщениям в чате — это питает командного питомца и радар выгорания. Анализируются только агрегаты (без чтения личного), строго по согласию команды.</p>
        <label class="integration-row" style="cursor:pointer">
          <span class="col gap-4"><b>Включить анализ настроения</b><span class="meta">Тон и активность чата → wellbeing-сигналы и питомец</span></span>
          <span class="gc-switch ${botSettings.emotion_analysis ? "on" : ""}" id="emotion-toggle" role="switch" tabindex="0" aria-checked="${botSettings.emotion_analysis ? "true" : "false"}"></span>
        </label>
        <div class="note" style="font-size:12px;display:flex;gap:8px;align-items:flex-start">
          <svg viewBox="0 0 24 24" width="15" fill="none" stroke="currentColor" stroke-width="1.8" style="flex:none;margin-top:1px;color:#a78bfa"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M9 12l2 2 4-4"/></svg>
          <span>Это инструмент заботы о команде, а не слежки. Можно выключить в любой момент — сбор данных прекратится.</span>
        </div>
        <div class="alert alert-error" id="emotion-error" hidden></div>
      </div>` : ""}
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
  if (botSettings) {
    bindForm(root, "#bot-behavior-form", async (data) => {
      try {
        await api.teams.saveBotSettings(managerTeam.id, {
          require_cardinal_mention: data.get("require_cardinal_mention") === "on",
        });
        toast("Поведение бота сохранено");
      } catch (error) {
        const element = root.querySelector("#bot-behavior-error");
        element.textContent = errorMessage(error);
        element.hidden = false;
      }
    });
  }
  if (botSettings) {
    const toggle = root.querySelector("#emotion-toggle");
    const pill = root.querySelector("#emotion-pill");
    const errEl = root.querySelector("#emotion-error");
    let saving = false;
    const apply = async () => {
      if (saving) return;
      saving = true;
      errEl.hidden = true;
      const next = !toggle.classList.contains("on");
      toggle.classList.toggle("on", next);
      toggle.setAttribute("aria-checked", String(next));
      try {
        const res = await api.teams.saveBotSettings(managerTeam.id, { emotion_analysis: next });
        const on = res.emotion_analysis !== false && next;
        toggle.classList.toggle("on", on);
        toggle.setAttribute("aria-checked", String(on));
        pill.className = `pill ${on ? "ok" : "idle"}`;
        pill.innerHTML = `<span class="dot"></span>${on ? "включён" : "выключен"}`;
        toast(on ? "Эмоциональный анализ включён" : "Эмоциональный анализ выключен");
      } catch (error) {
        toggle.classList.toggle("on", !next);
        toggle.setAttribute("aria-checked", String(!next));
        errEl.textContent = errorMessage(error);
        errEl.hidden = false;
      } finally {
        saving = false;
      }
    };
    toggle.addEventListener("click", apply);
    toggle.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); apply(); } });
  }
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

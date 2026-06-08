import { api } from "../api.js";
import { Router } from "../router.js";
import { homeForUser, roleForUser } from "../auth.js";
import { escapeHtml, setTopbar, toast } from "../view-utils.js";

const TZ = typeof Intl.supportedValuesOf === "function"
  ? Intl.supportedValuesOf("timeZone")
  : ["Europe/Moscow", "Europe/London", "Asia/Dubai"];
const PREF_TZ = Intl.DateTimeFormat().resolvedOptions().timeZone || "Europe/Moscow";

async function refreshContext() {
  const [me, ctx] = await Promise.all([api.auth.me(), api.context()]);
  const user = { ...me, companies: ctx.companies || [], teams: ctx.teams || [] };
  window.gcCurrentUser = user;
  appReady(user);
  return user;
}
function appReady(user) {
  try { window.gcSidebar(user, roleForUser(user)); } catch { /* ignore */ }
}

export default async function onboardingView(root) {
  injectStyles();
  setTopbar("Добро пожаловать");
  const el = root.querySelector("#onboarding-content");
  let user = window.gcCurrentUser;
  try { user = await api.auth.me().then((me) => api.context().then((c) => ({ ...me, companies: c.companies || [], teams: c.teams || [] }))); } catch { /* keep */ }
  if (user && ((user.companies || []).length || (user.teams || []).length)) {
    Router.navigate(homeForUser(user), true);
    return;
  }
  renderChoice(el, user || {});
}

function renderChoice(el, user) {
  el.innerHTML = `
  <div class="ob-wrap">
    <div class="ob-head">
      <h1>Привет, ${escapeHtml((user.first_name || user.display_name || "коллега"))}! 👋</h1>
      <p>Давайте настроим Grey Cardinal. С чего начнём?</p>
    </div>
    <div class="ob-choice">
      <button class="ob-card" id="ob-create">
        <div class="ob-ico">🏢</div>
        <h3>Создать организацию</h3>
        <p>Я руководитель или директор. Настрою компанию, команду и интеграции по шагам.</p>
      </button>
      <button class="ob-card" id="ob-join">
        <div class="ob-ico">🤝</div>
        <h3>Присоединиться к команде</h3>
        <p>Меня пригласит руководитель. Введу код приглашения или подожду инвайт.</p>
      </button>
    </div>
  </div>`;
  el.querySelector("#ob-create").onclick = () => renderCreate(el);
  el.querySelector("#ob-join").onclick = () => renderJoin(el, user);
}

// ── Join flow ────────────────────────────────────────────────────────────────
function renderJoin(el, user) {
  el.innerHTML = `
  <div class="ob-wrap">
    <button class="ob-back" id="ob-back">← Назад</button>
    <div class="ob-head"><h1>Присоединиться к команде</h1>
      <p>Попросите руководителя или директора пригласить вас. Если у вас есть код приглашения — введите его ниже.</p></div>
    <div class="ob-panel">
      <label class="ob-fld">Код или ссылка приглашения
        <input id="ob-token" placeholder="вставьте код или ссылку">
      </label>
      <button class="btn btn-primary" id="ob-accept">Присоединиться</button>
      <div class="ob-note" id="ob-join-msg"></div>
      <div class="ob-divider"></div>
      <div class="ob-hint">
        <b>Нет кода?</b> Передайте руководителю ваш email — он создаст приглашение в кабинете:
        <div class="ob-email">${escapeHtml(user.email || "—")}</div>
      </div>
    </div>
  </div>`;
  el.querySelector("#ob-back").onclick = () => renderChoice(el, user);
  el.querySelector("#ob-accept").onclick = async () => {
    const raw = el.querySelector("#ob-token").value.trim();
    const token = raw.split("/").pop().split("=").pop().trim();
    const msg = el.querySelector("#ob-join-msg");
    if (!token) { msg.textContent = "Введите код приглашения."; return; }
    try {
      await api.invites.accept(token);
      toast("Вы присоединились к команде!");
      const user2 = await refreshContext();
      Router.navigate(homeForUser(user2), true);
    } catch (e) {
      msg.textContent = "Не удалось принять приглашение: " + (e.message || "проверьте код");
    }
  };
}

// ── Create (director) flow ───────────────────────────────────────────────────
function renderCreate(el) {
  const state = { step: 1, companyId: null, teamId: null, team: null, companyName: "", teamName: "" };
  const steps = ["Компания", "Команда", "Telegram", "YouGile", "Приглашения"];

  function shell(inner) {
    el.innerHTML = `
    <div class="ob-wrap">
      <button class="ob-back" id="ob-back">← Назад</button>
      <div class="ob-steps">${steps.map((s, i) => `<div class="ob-step ${i + 1 === state.step ? "active" : ""} ${i + 1 < state.step ? "done" : ""}"><span>${i + 1 < state.step ? "✓" : i + 1}</span>${s}</div>`).join("")}</div>
      <div class="ob-panel">${inner}</div>
    </div>`;
    el.querySelector("#ob-back").onclick = () => {
      if (state.step > 1) { state.step--; route(); } else renderChoice(el, window.gcCurrentUser || {});
    };
  }

  function route() {
    if (state.step === 1) stepCompany();
    else if (state.step === 2) stepTeam();
    else if (state.step === 3) stepTelegram();
    else if (state.step === 4) stepYougile();
    else stepInvite();
  }

  function stepCompany() {
    shell(`<h2>Создайте компанию</h2><p class="ob-sub">Компания объединяет команды и метрики.</p>
      <label class="ob-fld">Название<input id="c-name" value="${escapeHtml(state.companyName)}" placeholder="Например, Fishing Team"></label>
      <label class="ob-fld">Часовой пояс<select id="c-tz">${TZ.map((z) => `<option ${z === PREF_TZ ? "selected" : ""}>${escapeHtml(z)}</option>`).join("")}</select></label>
      <button class="btn btn-primary" id="c-next">Далее →</button><div class="ob-note" id="c-msg"></div>`);
    el.querySelector("#c-next").onclick = async () => {
      const name = el.querySelector("#c-name").value.trim();
      if (name.length < 2) { el.querySelector("#c-msg").textContent = "Введите название."; return; }
      try {
        const company = await api.companies.create(name, el.querySelector("#c-tz").value);
        state.companyId = company.id; state.companyName = name;
        await refreshContext();
        state.step = 2; route();
      } catch (e) { el.querySelector("#c-msg").textContent = "Ошибка: " + (e.message || ""); }
    };
  }

  function stepTeam() {
    shell(`<h2>Создайте команду</h2><p class="ob-sub">Команда — это рабочее пространство с доской и Telegram-чатом.</p>
      <label class="ob-fld">Название команды<input id="t-name" value="${escapeHtml(state.teamName)}" placeholder="Например, Разработка"></label>
      <button class="btn btn-primary" id="t-next">Далее →</button><div class="ob-note" id="t-msg"></div>`);
    el.querySelector("#t-next").onclick = async () => {
      const name = el.querySelector("#t-name").value.trim();
      if (name.length < 2) { el.querySelector("#t-msg").textContent = "Введите название."; return; }
      try {
        const team = await api.teams.create(state.companyId, name, PREF_TZ);
        state.teamId = team.id; state.team = team; state.teamName = name;
        await refreshContext();
        state.step = 3; route();
      } catch (e) { el.querySelector("#t-msg").textContent = "Ошибка: " + (e.message || ""); }
    };
  }

  function stepTelegram() {
    shell(`<h2>Подключите Telegram</h2><p class="ob-sub">Бот будет ловить задачи из чата команды. Это можно сделать позже.</p>
      <div class="ob-note" id="tg-code">Получаю код привязки…</div>
      <ol class="ob-list">
        <li>Добавьте бота <b>@grey_cxrdinxl_bot</b> в ваш групповой чат.</li>
        <li>Отправьте в чат: <code id="tg-cmd">/bind_team КОД</code></li>
      </ol>
      <div class="ob-row"><button class="btn btn-primary" id="tg-next">Далее →</button><button class="btn btn-ghost" id="tg-skip">Пропустить</button></div>`);
    el.querySelector("#tg-skip").onclick = () => { state.step = 4; route(); };
    el.querySelector("#tg-next").onclick = () => { state.step = 4; route(); };
    api.teams.telegramBindCode(state.teamId).then((res) => {
      const code = res.code || res.bind_code || "—";
      el.querySelector("#tg-code").innerHTML = `Код привязки: <b class="ob-code">${escapeHtml(code)}</b> (действует ~20 мин)`;
      el.querySelector("#tg-cmd").textContent = `/bind_team ${code}`;
    }).catch(() => { el.querySelector("#tg-code").textContent = "Код можно получить позже в настройках команды."; });
  }

  function stepYougile() {
    shell(`<h2>Подключите YouGile</h2><p class="ob-sub">Двусторонняя синхронизация задач с доской YouGile. Необязательно — можно подключить позже.</p>
      <div class="ob-row">
        <a class="btn btn-primary" href="/app/teams/${state.teamId}/yougile">Открыть подключение YouGile</a>
        <button class="btn btn-ghost" id="y-skip">Пропустить</button>
      </div>
      <div class="ob-hint mt-12">Подключение откроется на отдельной странице. Вернитесь сюда, чтобы завершить настройку.</div>
      <button class="btn btn-primary mt-16" id="y-next">Далее →</button>`);
    el.querySelector("#y-skip").onclick = () => { state.step = 5; route(); };
    el.querySelector("#y-next").onclick = () => { state.step = 5; route(); };
  }

  function stepInvite() {
    shell(`<h2>Пригласите команду</h2><p class="ob-sub">Создайте ссылку-приглашение для сотрудников. Необязательно.</p>
      <div class="ob-row"><button class="btn btn-primary" id="i-gen">Создать приглашение</button><button class="btn btn-ghost" id="i-skip">Пропустить</button></div>
      <div class="ob-note" id="i-link"></div>
      <button class="btn btn-primary mt-16" id="i-finish">🎉 Завершить настройку</button>`);
    el.querySelector("#i-gen").onclick = async () => {
      try {
        const inv = await api.teams.invite({ company_id: state.companyId, id: state.teamId }, "employee");
        const token = inv.token || inv.id || "";
        const link = `${location.origin}/login.html?invite=${encodeURIComponent(token)}`;
        el.querySelector("#i-link").innerHTML = `Ссылка-приглашение (скопируйте и отправьте):<div class="ob-email" id="i-url">${escapeHtml(link)}</div>`;
        el.querySelector("#i-url").onclick = () => { navigator.clipboard?.writeText(link); toast("Скопировано"); };
      } catch (e) { el.querySelector("#i-link").textContent = "Не удалось создать приглашение: " + (e.message || ""); }
    };
    el.querySelector("#i-skip").onclick = () => finish();
    el.querySelector("#i-finish").onclick = () => finish();
  }

  async function finish() {
    const user = await refreshContext().catch(() => window.gcCurrentUser);
    toast("Готово! Добро пожаловать в Grey Cardinal 🖤");
    Router.navigate(state.teamId ? `/app/teams/${state.teamId}/board` : homeForUser(user || {}), true);
  }

  route();
}

function injectStyles() {
  if (document.getElementById("gc-onboarding-styles")) return;
  const st = document.createElement("style");
  st.id = "gc-onboarding-styles";
  st.textContent = `
  .onboarding-page{display:flex;justify-content:center;padding:24px 16px}
  .ob-wrap{width:100%;max-width:760px}
  .ob-head h1{margin:0 0 6px;font-size:28px}
  .ob-head p{color:#9a9aa3;margin:0 0 22px}
  .ob-choice{display:grid;grid-template-columns:1fr 1fr;gap:16px}
  @media(max-width:680px){.ob-choice{grid-template-columns:1fr}}
  .ob-card{text-align:left;background:#16161a;border:1px solid #26262e;border-radius:16px;padding:22px;cursor:pointer;color:inherit;transition:border-color .15s,transform .08s}
  .ob-card:hover{border-color:#ff003c;transform:translateY(-2px)}
  .ob-ico{font-size:34px;margin-bottom:10px}
  .ob-card h3{margin:0 0 6px;font-size:18px}
  .ob-card p{margin:0;color:#9a9aa3;font-size:14px}
  .ob-back{background:none;border:none;color:#9a9aa3;cursor:pointer;margin-bottom:12px;font-size:14px}
  .ob-steps{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px}
  .ob-step{display:flex;align-items:center;gap:7px;font-size:13px;color:#6a6a73;background:#16161a;border:1px solid #26262e;border-radius:20px;padding:6px 12px}
  .ob-step span{width:20px;height:20px;border-radius:50%;background:#2a2a33;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700}
  .ob-step.active{color:#fff;border-color:#ff003c}.ob-step.active span{background:#ff003c}
  .ob-step.done{color:#2ecc71}.ob-step.done span{background:#14401f;color:#2ecc71}
  .ob-panel{background:#16161a;border:1px solid #26262e;border-radius:16px;padding:24px}
  .ob-panel h2{margin:0 0 4px}
  .ob-sub{color:#9a9aa3;margin:0 0 16px}
  .ob-fld{display:flex;flex-direction:column;gap:6px;margin-bottom:14px;font-size:13px;color:#9a9aa3}
  .ob-fld input,.ob-fld select{padding:10px 12px;border-radius:10px;border:1px solid #2a2a33;background:#1a1a1f;color:#ececf0;font:inherit}
  .ob-note{margin-top:12px;color:#9a9aa3;font-size:13px}
  .ob-row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
  .ob-list{color:#cfcfd6;line-height:1.9;margin:10px 0}
  .ob-list code,.ob-code{background:#0e0e11;border:1px solid #2a2a33;border-radius:6px;padding:2px 8px;color:#ff7a7f}
  .ob-divider{height:1px;background:#26262e;margin:18px 0}
  .ob-hint{color:#9a9aa3;font-size:13px}
  .ob-email{margin-top:8px;background:#0e0e11;border:1px solid #2a2a33;border-radius:8px;padding:10px 12px;word-break:break-all;cursor:pointer}
  .mt-12{margin-top:12px}.mt-16{margin-top:16px}
  `;
  document.head.appendChild(st);
}

import { api } from "../api.js";
import { currentTeam, errorMessage, escapeHtml, setTopbar } from "../view-utils.js";

const pct = (v) => `${Math.round(Number(v || 0) * 100)}%`;
const money = (v) => Number(v || 0).toLocaleString("ru-RU");

const LEVEL_COLOR = { ok: "#2dd4bf", watch: "#f1c40f", high: "#f59e0b", critical: "#ef4444" };
const LEVEL_LABEL = { ok: "норма", watch: "наблюдать", high: "высокий", critical: "критич." };
const VERDICT = {
  fits: { label: "Команда справится", col: "#2dd4bf" },
  tight: { label: "На грани", col: "#f1c40f" },
  hire_needed: { label: "Нужно усиление", col: "#ef4444" },
};
const SCEN_LABEL = { current: "Текущий штаб", with_hire: "С наймом", with_more_time: "С запасом по сроку" };

function err(message) {
  return `<div class="note warn">${escapeHtml(message)}</div>`;
}

function bar(value, color) {
  const w = Math.max(2, Math.min(100, Math.round(Number(value || 0) * 100)));
  return `<div class="ins-track"><div class="ins-fill" style="width:${w}%;background:${color}"></div></div>`;
}

function injectStyles() {
  if (document.getElementById("insights-style")) return;
  const st = document.createElement("style");
  st.id = "insights-style";
  st.textContent = `
  .ins-track{height:8px;border-radius:6px;background:#23232b;overflow:hidden;margin-top:6px}
  .ins-fill{height:100%;border-radius:6px;transition:width .5s ease}
  .ins-row{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:12px 0;border-top:1px solid var(--line,#23232b)}
  .ins-row:first-child{border-top:0}
  .ins-pill{font-size:11px;font-weight:700;padding:2px 9px;border-radius:20px;color:#0c0c0e}
  .ins-narrative{white-space:pre-line;line-height:1.55}
  .ins-scn{display:flex;flex-direction:column;gap:6px}
  .ins-scn .verdict{font-weight:700}
  .ins-drivers{color:var(--muted,#8a8a93);font-size:12.5px}
  .ins-form textarea{width:100%;min-height:96px;resize:vertical;background:#16161a;color:inherit;border:1px solid var(--line,#23232b);border-radius:10px;padding:10px 12px;font:inherit}
  .ins-recommend{outline:2px solid #2dd4bf66;border-radius:12px}
  `;
  document.head.appendChild(st);
}

export default async function insightsView(root, params) {
  injectStyles();
  const user = window.gcCurrentUser;
  const teamId = params.teamId || currentTeam(user)?.id;
  setTopbar("AI-аналитика");
  const content = root.querySelector("#insights-content");
  if (!teamId) {
    content.innerHTML = err("Не удалось определить команду.");
    return;
  }

  const loaders = {
    pulse: () => renderPulse(content, teamId),
    burnout: () => renderBurnout(content, teamId),
    planner: () => renderPlanner(content, teamId),
    standup: () => renderStandup(content, teamId),
    copilot: () => renderCopilot(content, teamId),
  };

  async function show(tab) {
    root.querySelectorAll("#insights-tabs button").forEach((b) =>
      b.classList.toggle("active", b.dataset.tab === tab));
    content.innerHTML = '<div class="view-loading">Загрузка…</div>';
    try {
      await loaders[tab]();
    } catch (error) {
      content.innerHTML = err(errorMessage(error));
    }
  }

  root.querySelectorAll("#insights-tabs button").forEach((b) =>
    (b.onclick = () => show(b.dataset.tab)));
  await show("pulse");
}

// ── Pulse ──────────────────────────────────────────────────────────────────
async function renderPulse(content, teamId) {
  const data = await api.insights.pulse(teamId);
  const mt = data.metrics || {};
  const delta = mt.completed_this_week - mt.completed_prev_week;
  const deltaTxt = delta === 0 ? "без изменений" : `${delta > 0 ? "+" : ""}${delta} к пр. неделе`;
  const moodTxt = mt.valence_now != null
    ? pct((mt.valence_now + 1) / 2) : "—";
  content.innerHTML = `
    <div class="grid g4">
      <div class="stat"><div class="stat-label">Закрыто за неделю</div><div class="stat-value mono">${mt.completed_this_week ?? 0}</div><div class="stat-delta">${escapeHtml(deltaTxt)}</div></div>
      <div class="stat"><div class="stat-label">Создано</div><div class="stat-value mono">${mt.created_this_week ?? 0}</div></div>
      <div class="stat"><div class="stat-label">Просрочено</div><div class="stat-value mono">${mt.overdue_now ?? 0}</div></div>
      <div class="stat"><div class="stat-label">Настроение</div><div class="stat-value mono">${moodTxt}</div></div>
    </div>
    <div class="card card-pad mt-20"><div class="card-head"><div class="card-title">Сводка недели</div></div>
      <div class="ins-narrative">${data.narrative || ""}</div></div>`;
}

// ── Burnout ────────────────────────────────────────────────────────────────
async function renderBurnout(content, teamId) {
  const data = await api.insights.burnout(teamId);
  const s = data.summary || {};
  const members = data.members || [];
  const head = s.top
    ? `<div class="note warn">⚠️ Под риском: <b>${escapeHtml(s.top)}</b>. Всего на радаре: ${s.at_risk_count}.</div>`
    : `<div class="note">🟢 Растущих рисков выгорания не вижу.</div>`;
  const rows = members.map((mfc) => {
    const col = LEVEL_COLOR[mfc.level] || "#8a8a93";
    const eta = mfc.eta_days ? ` · порог ~${mfc.eta_days} дн` : "";
    const drivers = (mfc.drivers || []).length ? `<div class="ins-drivers">${escapeHtml(mfc.drivers.join(", "))}</div>` : "";
    return `<div class="ins-row"><div style="flex:1">
        <b>${escapeHtml(mfc.display_name)}</b>
        <span class="ins-pill" style="background:${col};margin-left:8px">${LEVEL_LABEL[mfc.level] || mfc.level}</span>
        ${bar(mfc.risk, col)}${drivers}
      </div>
      <div style="text-align:right;min-width:96px">
        <div class="mono" style="font-size:18px;color:${col}">${pct(mfc.risk)}</div>
        <div class="ins-drivers">стресс ${escapeHtml(mfc.trend)}${eta}</div>
      </div></div>`;
  }).join("");
  content.innerHTML = `${head}
    <div class="card card-pad mt-20"><div class="card-head"><div class="card-title">Радар выгорания</div></div>
      ${rows || '<div class="dim">Нет данных по участникам.</div>'}</div>`;
}

// ── Planner ────────────────────────────────────────────────────────────────
async function renderPlanner(content, teamId) {
  content.innerHTML = `
    <div class="card card-pad ins-form"><div class="card-head"><div class="card-title">Планировщик проекта</div></div>
      <p class="dim" style="margin:0 0 10px">Опиши проект — посчитаю бюджет, срок, хватит ли текущего штаба и что будет с настроением команды.</p>
      <textarea id="plan-desc" placeholder="Напр.: интеграция оплаты, личный кабинет, мобильное приложение"></textarea>
      <div class="flex center gap-12" style="margin-top:10px">
        <label class="dim">Горизонт, недель:</label>
        <input id="plan-weeks" type="number" min="1" max="26" value="4" style="width:72px;background:#16161a;color:inherit;border:1px solid var(--line,#23232b);border-radius:8px;padding:6px 8px"/>
        <button class="btn btn-primary" id="plan-go">Рассчитать</button>
      </div>
    </div>
    <div id="plan-result" class="mt-20"></div>`;
  const out = content.querySelector("#plan-result");
  content.querySelector("#plan-go").onclick = async () => {
    const description = content.querySelector("#plan-desc").value.trim();
    const horizon_weeks = Number(content.querySelector("#plan-weeks").value) || 4;
    if (!description) { out.innerHTML = err("Опиши проект."); return; }
    out.innerHTML = '<div class="view-loading">Считаю сценарии…</div>';
    try {
      const plan = await api.insights.plan(teamId, { description, horizon_weeks });
      out.innerHTML = renderPlan(plan);
    } catch (error) {
      out.innerHTML = err(errorMessage(error));
    }
  };
}

function renderPlan(plan) {
  const scenarios = plan.scenarios || {};
  const can = plan.can_use_current_team ? '<span style="color:#2dd4bf">✅ да</span>' : '<span style="color:#ef4444">🛑 нет</span>';
  const base = scenarios.current || {};
  const cards = ["current", "with_hire", "with_more_time"].filter((k) => scenarios[k]).map((k) => {
    const sc = scenarios[k];
    const v = VERDICT[sc.verdict] || { label: sc.verdict, col: "#8a8a93" };
    const rec = k === plan.recommended ? " ins-recommend" : "";
    const star = k === plan.recommended ? "⭐ " : "";
    return `<div class="card card-pad ins-scn${rec}">
      <div class="card-title">${star}${escapeHtml(SCEN_LABEL[k] || k)}</div>
      <div class="verdict" style="color:${v.col}">${v.label}</div>
      <div class="dim">${Math.round(sc.total_hours)} ч · ${money(sc.budget_min)}–${money(sc.budget_max)} ₽</div>
      <div class="dim">срок ~${sc.duration_weeks_p50} нед (P90 ${sc.duration_weeks_p90})</div>
      <div class="dim">настроение ${pct(sc.current_mood)} → ${pct(sc.projected_mood)}</div>
    </div>`;
  }).join("");
  const risks = (base.risks || []).length
    ? `<div class="card card-pad mt-20"><div class="card-title">Риски</div>${base.risks.slice(0, 5).map((r) => `<div class="ins-row">⚠️ ${escapeHtml(r)}</div>`).join("")}</div>` : "";
  const recObj = scenarios[plan.recommended] || base;
  const recs = (recObj.recommendations || []).length
    ? `<div class="card card-pad mt-20"><div class="card-title">Рекомендации</div>${recObj.recommendations.slice(0, 4).map((r) => `<div class="ins-row">💡 ${escapeHtml(r)}</div>`).join("")}</div>` : "";
  const skills = Object.entries(plan.skill_matrix || {})
    .map(([name, role]) => `<span class="tag">${escapeHtml(name)}: ${escapeHtml(role)}</span>`).join(" ");
  return `
    <div class="note">Хватит текущего штаба: ${can}${base.missing_roles?.length ? ` · не хватает ролей: ${escapeHtml(base.missing_roles.join(", "))}` : ""}</div>
    <div class="grid g3 mt-20">${cards}</div>
    ${skills ? `<div class="card card-pad mt-20"><div class="card-title">Квалификация (по истории)</div><div class="flex" style="flex-wrap:wrap;gap:6px;margin-top:8px">${skills}</div></div>` : ""}
    ${risks}${recs}`;
}

// ── Standup ────────────────────────────────────────────────────────────────
async function renderStandup(content, teamId) {
  const data = await api.insights.standup(teamId);
  const members = data.members || [];
  const rows = members.map((ms) => {
    const lines = [];
    if (ms.doing?.length) lines.push(`<div class="dim">🔄 ${escapeHtml(ms.doing.join("; "))}</div>`);
    if (ms.blocked?.length) lines.push(`<div style="color:#ef4444">⛔ ${escapeHtml(ms.blocked.join("; "))}</div>`);
    if (ms.done_recently?.length) lines.push(`<div style="color:#2dd4bf">✅ ${escapeHtml(ms.done_recently.join("; "))}</div>`);
    if (ms.needs_help && ms.help_reason) lines.push(`<div style="color:#f59e0b">💬 нужна помощь: ${escapeHtml(ms.help_reason)}</div>`);
    return `<div class="ins-row"><div style="flex:1"><b>${escapeHtml(ms.display_name)}</b>${ms.needs_help ? " 🆘" : ""}${lines.join("")}</div></div>`;
  }).join("");
  const help = (data.needs_help || []).length
    ? `<div class="note warn">🤝 Помощь нужна: ${escapeHtml(data.needs_help.join(", "))}</div>` : "";
  content.innerHTML = `${help}
    <div class="card card-pad mt-20"><div class="card-head"><div class="card-title">🌅 Утренний стендап</div></div>
      ${rows || '<div class="dim">Активных задач нет — чистый старт дня.</div>'}</div>`;
}

// ── Copilot ────────────────────────────────────────────────────────────────
async function renderCopilot(content, teamId) {
  const data = await api.insights.copilot(teamId);
  const actions = data.actions || [];
  const rows = actions.map((a, i) =>
    `<div class="ins-row"><div style="flex:1"><b>${i + 1}.</b> ${escapeHtml(a.icon)} ${escapeHtml(a.text)}</div></div>`).join("");
  content.innerHTML = `
    <div class="card card-pad"><div class="card-head"><div class="card-title">☕️ Копилот руководителя</div></div>
      <p class="dim" style="margin:0 0 6px">Три вещи на сегодня по данным команды.</p>
      ${rows || '<div class="dim">Сегодня горящего нет — рисков, просрочек и блоков не вижу.</div>'}</div>`;
}

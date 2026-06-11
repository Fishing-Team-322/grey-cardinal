import { api } from "../api.js";
import { currentTeam, errorMessage, escapeHtml, setTopbar } from "../view-utils.js";

const VIEWS = [
  ["overview", "Обзор", "Общая картина"],
  ["pulse", "Пульс", "Темп и настроение"],
  ["burnout", "Риски", "Нагрузка и выгорание"],
  ["standup", "Стендап", "Кто чем занят"],
  ["planner", "Планировщик", "Сценарии проекта"],
  ["copilot", "Копилот", "Фокус руководителя"],
];

const LEVEL_LABEL = {
  ok: "Норма",
  watch: "Наблюдать",
  high: "Высокий риск",
  critical: "Критический риск",
};

const VERDICT = {
  fits: { label: "Команда справится", tone: "ok" },
  tight: { label: "План на грани", tone: "warn" },
  hire_needed: { label: "Нужно усиление", tone: "err" },
};

const SCENARIO_LABEL = {
  current: "Текущая команда",
  with_hire: "С усилением",
  with_more_time: "Больше времени",
};

const pct = (value) => `${Math.round(Number(value || 0) * 100)}%`;
const money = (value) => Number(value || 0).toLocaleString("ru-RU");

export default async function insightsView(root, params, query = {}) {
  const user = window.gcCurrentUser;
  const team = currentTeam(user, params.teamId);
  const teamId = team?.id;
  const view = VIEWS.some(([key]) => key === query.view) ? query.view : "overview";
  setTopbar("AI-аналитика", teamId
    ? `<a class="btn btn-ghost" href="/app/teams/${teamId}">Команда</a><a class="btn btn-primary" href="/app/teams/${teamId}/board">Открыть доску</a>`
    : "");

  const shell = root.querySelector("#insights-shell");
  if (!teamId) {
    shell.innerHTML = errorState("Не удалось определить команду.");
    return;
  }

  root.querySelector("#insights-title").textContent = view === "overview"
    ? `AI-центр команды ${team.name || ""}`.trim()
    : VIEWS.find(([key]) => key === view)?.[1] || "AI-аналитика";
  root.querySelector("#insights-desc").textContent = view === "overview"
    ? "Решения, риски и рабочий ритм собраны в одном спокойном обзоре."
    : VIEWS.find(([key]) => key === view)?.[2] || "";

  shell.innerHTML = `
    <div class="insights-workspace">
      <aside class="insights-nav" aria-label="Разделы AI-аналитики">
        <div class="insights-nav-label">Инструменты</div>
        ${VIEWS.map(([key, label, description]) => `
          <a class="insights-nav-item ${key === view ? "active" : ""}" href="/app/teams/${teamId}/insights?view=${key}">
            <span>${escapeHtml(label)}</span>
            <small>${escapeHtml(description)}</small>
          </a>`).join("")}
      </aside>
      <section class="insights-content" id="insights-content">
        <div class="view-loading">Собираю аналитику...</div>
      </section>
    </div>`;

  const content = shell.querySelector("#insights-content");
  const loaders = {
    overview: () => renderOverview(content, team),
    pulse: () => renderPulse(content, teamId),
    burnout: () => renderBurnout(content, teamId),
    standup: () => renderStandup(content, teamId),
    planner: () => renderPlanner(content, teamId),
    copilot: () => renderCopilot(content, teamId),
  };

  try {
    await loaders[view]();
  } catch (error) {
    content.innerHTML = errorState(errorMessage(error));
  }
}

async function renderOverview(content, team) {
  const [pulseResult, burnoutResult, standupResult, copilotResult] = await Promise.allSettled([
    api.insights.pulse(team.id),
    api.insights.burnout(team.id),
    api.insights.standup(team.id),
    api.insights.copilot(team.id),
  ]);
  const pulse = settledValue(pulseResult, { metrics: {} });
  const burnout = settledValue(burnoutResult, { summary: {}, members: [] });
  const standup = settledValue(standupResult, { members: [], needs_help: [], total_blocked: 0 });
  const copilot = settledValue(copilotResult, { actions: [] });
  const metrics = pulse.metrics || {};
  const atRisk = burnout.summary?.at_risk_count || 0;
  const blocked = standup.total_blocked || 0;
  const status = atRisk > 0 || metrics.overdue_now > 2
    ? { tone: "warn", title: "Нужен фокус руководителя", text: "Есть сигналы, которые лучше разобрать сегодня." }
    : blocked > 0
      ? { tone: "info", title: "Команда движется, но есть блокеры", text: "Темп стабильный, нескольким задачам нужна помощь." }
      : { tone: "ok", title: "Рабочий ритм в норме", text: "Критичных сигналов сейчас не видно." };
  const mood = metrics.valence_now == null ? null : (metrics.valence_now + 1) / 2;

  content.innerHTML = `
    <section class="insights-hero ${status.tone}">
      <div>
        <div class="eyebrow muted">Состояние на сегодня</div>
        <h2>${escapeHtml(status.title)}</h2>
        <p>${escapeHtml(status.text)}</p>
      </div>
      <div class="insights-hero-score">
        <strong>${metrics.completed_this_week ?? 0}</strong>
        <span>задач закрыто за 7 дней</span>
      </div>
    </section>

    <div class="insights-kpis">
      ${metricCard("Закрыто", metrics.completed_this_week ?? 0, completionDelta(metrics))}
      ${metricCard("Просрочено", metrics.overdue_now ?? 0, metrics.overdue_now ? "Нужна сортировка" : "Чистый список")}
      ${metricCard("Блокеры", blocked, blocked ? "Разобрать сегодня" : "Нет блокеров")}
      ${metricCard("Настроение", mood == null ? "Нет данных" : pct(mood), mood == null ? "Анализ выключен" : mood >= 0.6 ? "Позитивный фон" : "Стоит проверить")}
    </div>

    <div class="insights-overview-grid">
      <article class="card card-pad insights-overview-primary">
        <div class="card-head">
          <div>
            <div class="eyebrow muted">Пульс недели</div>
            <div class="card-title mt-6">Темп команды</div>
          </div>
          <a class="card-sub accent-text" href="/app/teams/${team.id}/insights?view=pulse">Подробнее</a>
        </div>
        ${comparisonChart(metrics)}
        <div class="insights-summary">${plainNarrative(pulse.narrative || "Данных для недельной сводки пока недостаточно.")}</div>
      </article>

      <article class="card card-pad">
        <div class="card-head">
          <div>
            <div class="eyebrow muted">Фокус</div>
            <div class="card-title mt-6">Что сделать сегодня</div>
          </div>
          <a class="card-sub accent-text" href="/app/teams/${team.id}/insights?view=copilot">Копилот</a>
        </div>
        ${copilotActions(copilot.actions, 3)}
      </article>

      <article class="card card-pad">
        <div class="card-head">
          <div>
            <div class="eyebrow muted">Люди</div>
            <div class="card-title mt-6">Радар нагрузки</div>
          </div>
          <a class="card-sub accent-text" href="/app/teams/${team.id}/insights?view=burnout">Все риски</a>
        </div>
        ${burnoutPreview(burnout.members, team.id)}
      </article>

      <article class="card card-pad">
        <div class="card-head">
          <div>
            <div class="eyebrow muted">Рабочий день</div>
            <div class="card-title mt-6">Стендап без созвона</div>
          </div>
          <a class="card-sub accent-text" href="/app/teams/${team.id}/insights?view=standup">Открыть</a>
        </div>
        ${standupPreview(standup.members)}
      </article>
    </div>

    <div class="feature-launcher">
      <a class="feature-launch-card" href="/app/teams/${team.id}/insights?view=planner">
        <span class="feature-launch-index">01</span>
        <div><b>Проверить новый проект</b><p>Сравнить сроки, бюджет и сценарий с усилением.</p></div>
        <span class="feature-launch-arrow">→</span>
      </a>
      <a class="feature-launch-card" href="/app/teams/${team.id}/insights?view=standup">
        <span class="feature-launch-index">02</span>
        <div><b>Подготовиться к синку</b><p>Увидеть текущую работу, закрытия и блокеры по людям.</p></div>
        <span class="feature-launch-arrow">→</span>
      </a>
    </div>`;
}

async function renderPulse(content, teamId) {
  const data = await api.insights.pulse(teamId);
  const metrics = data.metrics || {};
  const mood = metrics.valence_now == null ? null : (metrics.valence_now + 1) / 2;
  const stress = metrics.stress_now == null ? null : metrics.stress_now;
  content.innerHTML = `
    <section class="section-intro">
      <div><div class="eyebrow muted">Последние 7 дней</div><h2>Темп, настроение и качество потока</h2></div>
      <span class="pill ${metrics.overdue_now ? "warn" : "ok"}"><span class="dot"></span>${metrics.overdue_now ? `${metrics.overdue_now} просрочено` : "Просрочек нет"}</span>
    </section>
    <div class="insights-kpis">
      ${metricCard("Закрыто", metrics.completed_this_week ?? 0, completionDelta(metrics))}
      ${metricCard("Создано", metrics.created_this_week ?? 0, "Новых задач")}
      ${metricCard("Настроение", mood == null ? "—" : pct(mood), metricTrend(metrics.valence_now, metrics.valence_prev))}
      ${metricCard("Стресс", stress == null ? "—" : pct(stress), metricTrend(metrics.stress_prev, metrics.stress_now, true))}
    </div>
    <div class="grid g2 mt-20">
      <article class="card card-pad">
        <div class="card-title">Сравнение недель</div>
        ${comparisonChart(metrics, true)}
      </article>
      <article class="card card-pad">
        <div class="card-title">Эмоциональный фон</div>
        <div class="gauge-grid mt-20">
          ${gauge("Настроение", mood, "ok")}
          ${gauge("Стресс", stress, stress != null && stress > 0.65 ? "err" : "info")}
        </div>
      </article>
    </div>
    <article class="card card-pad mt-20">
      <div class="card-head"><div class="card-title">Вывод для руководителя</div><span class="pill info">AI-сводка</span></div>
      <div class="insights-summary large">${plainNarrative(data.narrative || "Сводка пока не сформирована.")}</div>
    </article>`;
}

async function renderBurnout(content, teamId) {
  const data = await api.insights.burnout(teamId);
  const members = data.members || [];
  const atRisk = data.summary?.at_risk_count || 0;
  content.innerHTML = `
    <section class="section-intro">
      <div><div class="eyebrow muted">Прогноз по тренду</div><h2>Радар нагрузки и выгорания</h2><p>Не диагноз, а ранний сигнал по стрессу, просрочкам и числу активных задач.</p></div>
      <span class="pill ${atRisk ? "warn" : "ok"}"><span class="dot"></span>${atRisk ? `${atRisk} требуют внимания` : "Команда в норме"}</span>
    </section>
    <div class="risk-legend">
      <span><i class="risk-dot ok"></i>Норма</span>
      <span><i class="risk-dot watch"></i>Наблюдать</span>
      <span><i class="risk-dot high"></i>Высокий</span>
      <span><i class="risk-dot critical"></i>Критический</span>
    </div>
    <div class="risk-card-grid mt-20">
      ${members.map((member) => riskCard(member, teamId)).join("") || '<div class="empty-panel">Недостаточно данных для прогноза.</div>'}
    </div>`;
}

async function renderStandup(content, teamId) {
  const data = await api.insights.standup(teamId);
  const members = data.members || [];
  content.innerHTML = `
    <section class="section-intro">
      <div><div class="eyebrow muted">Живая сводка</div><h2>Стендап без отдельного созвона</h2><p>Текущая работа, недавние закрытия и места, где нужна помощь.</p></div>
      <span class="pill ${data.total_blocked ? "warn" : "ok"}"><span class="dot"></span>${data.total_blocked ? `${data.total_blocked} блокеров` : "Блокеров нет"}</span>
    </section>
    ${data.needs_help?.length ? `<div class="attention-strip">Помощь нужна: <b>${escapeHtml(data.needs_help.join(", "))}</b></div>` : ""}
    <div class="standup-grid mt-20">
      ${members.map(standupCard).join("") || '<div class="empty-panel">Активных задач нет. У команды чистый старт дня.</div>'}
    </div>`;
}

async function renderPlanner(content, teamId) {
  content.innerHTML = `
    <section class="section-intro">
      <div><div class="eyebrow muted">Сценарное планирование</div><h2>Проверить проект до старта</h2><p>Опишите результат, а система сравнит текущий состав, найм и более длинный горизонт.</p></div>
    </section>
    <div class="planner-layout">
      <form class="card card-pad planner-form" id="plan-form">
        <label>
          <span>Что нужно сделать</span>
          <textarea id="plan-desc" rows="7" placeholder="Например: запустить личный кабинет, интеграцию оплаты и мобильное приложение"></textarea>
        </label>
        <label>
          <span>Горизонт планирования</span>
          <div class="planner-horizon">
            <input id="plan-weeks" type="range" min="1" max="26" value="6">
            <output id="plan-weeks-value">6 недель</output>
          </div>
        </label>
        <button class="btn btn-primary btn-lg" type="submit">Рассчитать сценарии</button>
      </form>
      <aside class="planner-help">
        <div class="eyebrow muted">Что попадёт в расчёт</div>
        <ul>
          <li>история задач и фактический темп;</li>
          <li>навыки, найденные в прошлой работе;</li>
          <li>нагрузка и эмоциональный фон;</li>
          <li>диапазон бюджета и срок P90.</li>
        </ul>
      </aside>
    </div>
    <div id="plan-result" class="mt-20"></div>`;

  const form = content.querySelector("#plan-form");
  const weeks = form.querySelector("#plan-weeks");
  const weeksValue = form.querySelector("#plan-weeks-value");
  weeks.oninput = () => { weeksValue.textContent = weeksLabel(Number(weeks.value)); };
  form.onsubmit = async (event) => {
    event.preventDefault();
    const description = form.querySelector("#plan-desc").value.trim();
    const horizonWeeks = Number(weeks.value) || 6;
    const output = content.querySelector("#plan-result");
    if (!description) {
      output.innerHTML = errorState("Добавьте короткое описание проекта.");
      return;
    }
    form.querySelector("button").disabled = true;
    output.innerHTML = '<div class="view-loading compact">Сравниваю сценарии...</div>';
    try {
      const plan = await api.insights.plan(teamId, {
        description,
        horizon_weeks: horizonWeeks,
      });
      output.innerHTML = renderPlan(plan);
    } catch (error) {
      output.innerHTML = errorState(errorMessage(error));
    } finally {
      form.querySelector("button").disabled = false;
    }
  };
}

async function renderCopilot(content, teamId) {
  const data = await api.insights.copilot(teamId);
  content.innerHTML = `
    <section class="section-intro">
      <div><div class="eyebrow muted">Фокус на сегодня</div><h2>Копилот руководителя</h2><p>Короткий список решений, которые сильнее всего повлияют на работу команды.</p></div>
    </section>
    <div class="copilot-list">
      ${(data.actions || []).map((action, index) => `
        <article class="copilot-action ${escapeHtml(action.kind || "default")}">
          <span class="copilot-number">${String(index + 1).padStart(2, "0")}</span>
          <div><span class="pill info">${actionKind(action.kind)}</span><h3>${escapeHtml(action.text)}</h3></div>
        </article>`).join("") || `
        <div class="empty-panel large">
          <h3>Срочных действий нет</h3>
          <p>Риски, просрочки и блокеры не требуют вмешательства. Можно заняться долгосрочным планированием.</p>
        </div>`}
    </div>
    <article class="card card-pad mt-20">
      <div class="card-title">Полная утренняя сводка</div>
      <div class="insights-summary mt-16">${plainNarrative(data.narrative || "Копилот пока не сформировал сводку.")}</div>
    </article>`;
}

function renderPlan(plan) {
  const scenarios = plan.scenarios || {};
  const base = scenarios.current || {};
  const recommended = plan.recommended;
  const cards = ["current", "with_hire", "with_more_time"]
    .filter((key) => scenarios[key])
    .map((key) => {
      const scenario = scenarios[key];
      const verdict = VERDICT[scenario.verdict] || { label: scenario.verdict, tone: "info" };
      return `<article class="scenario-card ${key === recommended ? "recommended" : ""}">
        ${key === recommended ? '<span class="scenario-choice">Рекомендуемый</span>' : ""}
        <div class="eyebrow muted">${escapeHtml(SCENARIO_LABEL[key] || key)}</div>
        <h3>${escapeHtml(verdict.label)}</h3>
        <div class="scenario-metrics">
          <div><span>Срок</span><b>${scenario.duration_weeks_p50} нед.</b><small>P90: ${scenario.duration_weeks_p90}</small></div>
          <div><span>Бюджет</span><b>${money(scenario.budget_min)}–${money(scenario.budget_max)} ₽</b></div>
          <div><span>Объём</span><b>${Math.round(scenario.total_hours)} ч</b></div>
          <div><span>Настроение</span><b>${pct(scenario.current_mood)} → ${pct(scenario.projected_mood)}</b></div>
        </div>
      </article>`;
    }).join("");
  const recommendationSource = scenarios[recommended] || base;
  return `
    <div class="plan-verdict ${plan.can_use_current_team ? "ok" : "warn"}">
      <div><span>Текущий состав</span><b>${plan.can_use_current_team ? "Можно использовать" : "Нужно изменить план"}</b></div>
      ${base.missing_roles?.length ? `<p>Не хватает ролей: ${escapeHtml(base.missing_roles.join(", "))}</p>` : ""}
    </div>
    <div class="scenario-grid mt-20">${cards}</div>
    <div class="grid g2 mt-20">
      ${listPanel("Главные риски", base.risks)}
      ${listPanel("Что сделать", recommendationSource.recommendations)}
    </div>
    ${Object.keys(plan.skill_matrix || {}).length ? `
      <article class="card card-pad mt-20">
        <div class="card-title">Навыки, найденные в истории команды</div>
        <div class="skill-cloud mt-16">${Object.entries(plan.skill_matrix).map(([name, role]) => `<span><b>${escapeHtml(name)}</b>${escapeHtml(role)}</span>`).join("")}</div>
      </article>` : ""}`;
}

function comparisonChart(metrics, detailed = false) {
  const values = [
    ["Прошлая неделя", metrics.completed_prev_week || 0, "muted"],
    ["Эта неделя", metrics.completed_this_week || 0, "accent"],
    ["Создано", metrics.created_this_week || 0, "info"],
  ];
  const max = Math.max(1, ...values.map(([, value]) => value));
  return `<div class="comparison-chart ${detailed ? "detailed" : ""}">
    ${values.map(([label, value, tone]) => `
      <div class="comparison-row">
        <span>${label}</span>
        <div><i class="${tone}" style="width:${Math.max(4, Math.round(value / max * 100))}%"></i></div>
        <b class="mono">${value}</b>
      </div>`).join("")}
  </div>`;
}

function burnoutPreview(members, teamId) {
  const visible = (members || []).slice(0, 4);
  return visible.length ? `<div class="compact-list">${visible.map((member) => `
    <a href="/app/people/${member.user_id}?team=${teamId}" class="compact-person">
      <span class="compact-avatar">${initials(member.display_name)}</span>
      <span class="grow"><b>${escapeHtml(member.display_name)}</b><small>${escapeHtml((member.drivers || [LEVEL_LABEL[member.level]]).join(" · "))}</small></span>
      <strong class="risk-text ${escapeHtml(member.level)}">${pct(member.risk)}</strong>
    </a>`).join("")}</div>` : '<div class="empty-inline">Сигналов пока нет.</div>';
}

function standupPreview(members) {
  const visible = (members || []).slice(0, 4);
  return visible.length ? `<div class="compact-list">${visible.map((member) => `
    <div class="compact-person">
      <span class="status-line ${member.blocked?.length ? "blocked" : "active"}"></span>
      <span class="grow"><b>${escapeHtml(member.display_name)}</b><small>${member.blocked?.[0] ? escapeHtml(member.blocked[0]) : member.doing?.[0] ? escapeHtml(member.doing[0]) : "Недавно завершил задачу"}</small></span>
      <span class="pill ${member.blocked?.length ? "warn" : "idle"}">${member.blocked?.length ? "блок" : "в работе"}</span>
    </div>`).join("")}</div>` : '<div class="empty-inline">Активной работы сейчас нет.</div>';
}

function copilotActions(actions, limit) {
  const visible = (actions || []).slice(0, limit);
  return visible.length ? `<div class="decision-list">${visible.map((action, index) => `
    <div class="decision-row"><span>${index + 1}</span><p>${escapeHtml(action.text)}</p></div>`).join("")}</div>`
    : '<div class="empty-inline">Срочных решений нет.</div>';
}

function riskCard(member, teamId) {
  const drivers = member.drivers?.length
    ? member.drivers
    : ["Сильных факторов риска не обнаружено"];
  return `<a class="risk-card ${escapeHtml(member.level)}" href="/app/people/${member.user_id}?team=${teamId}">
    <div class="risk-card-head">
      <span class="compact-avatar large">${initials(member.display_name)}</span>
      <div class="grow"><h3>${escapeHtml(member.display_name)}</h3><span>${escapeHtml(LEVEL_LABEL[member.level] || member.level)}</span></div>
      <div class="risk-ring ${escapeHtml(member.level)}" style="--risk:${Math.round(member.risk * 100)}"><b>${pct(member.risk)}</b></div>
    </div>
    <div class="risk-card-metrics">
      <div><span>Активных</span><b>${member.active_count || 0}</b></div>
      <div><span>Просрочено</span><b>${member.overdue_count || 0}</b></div>
      <div><span>Стресс</span><b>${escapeHtml(member.trend || "стабилен")}</b></div>
      <div><span>Порог</span><b>${member.eta_days == null ? "—" : `~${member.eta_days} дн.`}</b></div>
    </div>
    <div class="risk-drivers">${drivers.map((driver) => `<span>${escapeHtml(driver)}</span>`).join("")}</div>
  </a>`;
}

function standupCard(member) {
  return `<article class="standup-card ${member.needs_help ? "needs-help" : ""}">
    <header>
      <span class="compact-avatar">${initials(member.display_name)}</span>
      <div><h3>${escapeHtml(member.display_name)}</h3><span>${member.needs_help ? escapeHtml(member.help_reason || "Нужна помощь") : "Рабочий ритм"}</span></div>
    </header>
    ${workList("В работе", member.doing, "active")}
    ${workList("Заблокировано", member.blocked, "blocked")}
    ${workList("Недавно закрыто", member.done_recently, "done")}
  </article>`;
}

function workList(title, items, tone) {
  if (!items?.length) return "";
  return `<div class="standup-section ${tone}"><span>${title}</span>${items.map((item) => `<p>${escapeHtml(item)}</p>`).join("")}</div>`;
}

function gauge(label, value, tone) {
  const normalized = value == null ? 0 : Math.max(0, Math.min(1, value));
  return `<div class="metric-gauge">
    <div class="gauge-ring ${tone}" style="--value:${Math.round(normalized * 100)}"><b>${value == null ? "—" : pct(value)}</b></div>
    <span>${label}</span>
  </div>`;
}

function metricCard(label, value, hint) {
  return `<div class="insight-metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(String(value))}</strong><small>${escapeHtml(hint || "")}</small></div>`;
}

function listPanel(title, items = []) {
  return `<article class="card card-pad"><div class="card-title">${escapeHtml(title)}</div>
    <div class="recommendation-list mt-16">${items?.length ? items.slice(0, 6).map((item) => `<div><span></span><p>${escapeHtml(item)}</p></div>`).join("") : '<p class="dim">Нет дополнительных пунктов.</p>'}</div>
  </article>`;
}

function completionDelta(metrics) {
  const delta = Number(metrics.completed_this_week || 0) - Number(metrics.completed_prev_week || 0);
  if (delta === 0) return "Как на прошлой неделе";
  return `${delta > 0 ? "+" : ""}${delta} к прошлой неделе`;
}

function metricTrend(current, previous, reverse = false) {
  if (current == null || previous == null) return "Нет сравнения";
  const delta = Math.round((current - previous) * 100);
  const positive = reverse ? delta <= 0 : delta >= 0;
  return `${delta > 0 ? "+" : ""}${delta} п.п. · ${positive ? "лучше" : "хуже"}`;
}

function weeksLabel(value) {
  if (value % 10 === 1 && value % 100 !== 11) return `${value} неделя`;
  if ([2, 3, 4].includes(value % 10) && ![12, 13, 14].includes(value % 100)) return `${value} недели`;
  return `${value} недель`;
}

function actionKind(kind) {
  return {
    unload: "Нагрузка",
    deadline: "Срок",
    unblock: "Блокер",
    recognize: "Признание",
  }[kind] || "Рекомендация";
}

function settledValue(result, fallback) {
  return result.status === "fulfilled" ? result.value : fallback;
}

function plainNarrative(value) {
  return escapeHtml(String(value || "").replace(/<[^>]+>/g, "")).replace(/\n/g, "<br>");
}

function initials(name) {
  return escapeHtml(String(name || "?").split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase());
}

function errorState(message) {
  return `<div class="empty-panel large"><h3>Не удалось загрузить раздел</h3><p>${escapeHtml(message)}</p></div>`;
}

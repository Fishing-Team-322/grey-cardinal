import { Router } from "./router.js?v=20260608-2";
import { getCurrentUser, guardFor, homeForUser, roleForUser } from "./auth.js";
import { appStore } from "./store.js";
import { wsConnect, wsOn } from "./ws.js";
import { toast } from "./view-utils.js";

import director from "./views/director.js";
import companies from "./views/companies.js";
import teams from "./views/teams.js";
import manager from "./views/manager.js";
import employee from "./views/employee.js";
import meetings from "./views/meetings.js";
import meeting from "./views/meeting.js";
import integrations from "./views/integrations.js";
import yougile from "./views/yougile.js";
import llm from "./views/llm.js";
import telegram from "./views/telegram.js";
import daemon from "./views/daemon.js";
import telemost from "./views/telemost.js";
import leaderboard from "./views/leaderboard.js";
import settings from "./views/settings.js";
import deploy from "./views/deploy.js";
import board from "./views/board.js";
import aiInbox from "./views/ai-inbox.js";
import onboarding from "./views/onboarding.js";
import { teamMapView, setupView, profileView } from "./views/agentic.js";

function ensureMobileMenu() {
  const topbar = document.getElementById("app-topbar");
  if (!topbar || topbar.querySelector(".mobile-menu")) return;
  const button = document.createElement("button");
  button.className = "mobile-menu";
  button.type = "button";
  button.setAttribute("aria-label", "Открыть меню");
  button.innerHTML = window.gcIcon("menu");
  topbar.prepend(button);
}

function bindCabinetNotifications(user) {
  const myId = String(user.id || "");
  const myName = (user.display_name || user.login || "").trim().toLowerCase();
  const myTeams = new Set((user.teams || []).map((team) => String(team.id)));
  wsOn("task_assigned", (payload) => {
    if (payload?.assignee_id && String(payload.assignee_id) !== myId) return;
    toast(`Вам назначили задачу: ${payload?.public_id || ""} ${payload?.title || ""}`.trim(), "info");
  });
  wsOn("task_created", (payload) => {
    const assignee = String(payload?.assignee || "").trim().toLowerCase();
    if (!assignee || !myName || assignee !== myName) return;
    toast(`Новая задача на вас: ${payload?.public_id || ""} ${payload?.title || ""}`.trim(), "info");
  });
  wsOn("meeting_reminder", (payload) => {
    if (payload?.team_id && !myTeams.has(String(payload.team_id))) return;
    toast(`Скоро созвон: ${payload?.title || payload?.public_id || "встреча"}`, "info");
  });
  wsOn("reminder_sent", (payload) => {
    if (payload?.kind === "deadline") toast(`Скоро дедлайн: ${payload?.public_id || "задача"}`, "warn");
  });
}

const topbar = document.getElementById("app-topbar");
if (topbar) new MutationObserver(ensureMobileMenu).observe(topbar, { childList: true });
ensureMobileMenu();

document.addEventListener("click", (event) => {
  if (event.target.closest(".mobile-menu")) {
    document.body.classList.add("sidebar-open");
    return;
  }
  if (event.target.closest(".sidebar-close, .sidebar-backdrop, .sidebar .nav-item")) {
    document.body.classList.remove("sidebar-open");
  }
});

async function boot() {
  let user;
  try {
    user = await getCurrentUser();
  } catch {
    location.href = `/login.html?next=${encodeURIComponent(location.pathname + location.search)}`;
    return;
  }
  window.gcCurrentUser = user;
  appStore.state.currentUser = user;
  appStore.state.context = { companies: user.companies, teams: user.teams };
  appStore.state.selectedTeamId = user.teams?.[0]?.id || null;
  window.gcSidebar(user, roleForUser(user));
  wsConnect();
  bindCabinetNotifications(user);

  Router.register("/app/companies", "/partials/companies.html", companies, guardFor("director"));
  Router.register("/app/companies/:id", "/partials/director.html", director, guardFor("director"));
  Router.register("/app/companies/:id/map", "/partials/agentic.html", teamMapView, guardFor("director"));
  Router.register("/app/director", "/partials/director.html", director, guardFor("director"));
  Router.register("/app/setup", "/partials/agentic.html", setupView, guardFor("director", "manager"));
  Router.register("/app/teams", "/partials/teams.html", teams, guardFor("director", "manager"));
  Router.register("/app/teams/:id", "/partials/manager.html", manager, guardFor("director", "manager"));
  Router.register("/app/teams/:teamId/board", "/partials/board.html", board);
  Router.register("/app/teams/:teamId/ai-inbox", "/partials/ai-inbox.html", aiInbox, guardFor("director", "manager"));
  Router.register("/app/teams/:teamId/yougile", "/partials/yougile.html", yougile, guardFor("director", "manager"));
  Router.register("/app/manager", "/partials/manager.html", manager, guardFor("manager"));
  Router.register("/app/employee", "/partials/employee.html", employee, guardFor("employee"));
  Router.register("/app/meetings", "/partials/meetings.html", meetings);
  Router.register("/app/meetings/:id", "/partials/meeting.html", meeting);
  Router.register("/app/leaderboard", "/partials/leaderboard.html", leaderboard);
  Router.register("/app/integrations", "/partials/integrations.html", integrations, guardFor("director", "manager"));
  Router.register("/app/integrations/yougile", "/partials/yougile.html", yougile, guardFor("director", "manager"));
  Router.register("/app/integrations/llm", "/partials/llm.html", llm, guardFor("director", "manager"));
  Router.register("/app/integrations/telegram", "/partials/telegram.html", telegram);
  Router.register("/app/integrations/daemon", "/partials/daemon.html", daemon);
  Router.register("/app/integrations/telemost", "/partials/telemost.html", telemost, guardFor("director", "manager"));
  Router.register("/app/settings", "/partials/settings.html", settings);
  Router.register("/app/deploy", "/partials/deploy.html", deploy, guardFor("director"));
  Router.register("/app/people/:userId", "/partials/agentic.html", profileView);
  Router.register("/app/me", "/partials/agentic.html", profileView);
  Router.register("/app/welcome", "/partials/onboarding.html", onboarding);

  // First-run: a user with no company and no team is sent to onboarding.
  const needsOnboarding = !(user.companies || []).length && !(user.teams || []).length;
  if (needsOnboarding && !location.pathname.startsWith("/app/welcome")) {
    await Router.navigate("/app/welcome", true);
  } else if (location.pathname === "/app" || location.pathname === "/app/") {
    await Router.navigate(homeForUser(user), true);
  } else {
    await Router.start();
  }
}

boot();

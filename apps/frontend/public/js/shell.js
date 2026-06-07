import { Router } from "./router.js";
import { getCurrentUser, guardFor, homeForUser, roleForUser } from "./auth.js";
import { appStore } from "./store.js";
import { wsConnect } from "./ws.js";

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

  Router.register("/app/companies", "/partials/companies.html", companies, guardFor("director"));
  Router.register("/app/companies/:id", "/partials/director.html", director, guardFor("director"));
  Router.register("/app/director", "/partials/director.html", director, guardFor("director"));
  Router.register("/app/teams", "/partials/teams.html", teams, guardFor("director", "manager"));
  Router.register("/app/teams/:id", "/partials/manager.html", manager, guardFor("director", "manager"));
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

  if (location.pathname === "/app" || location.pathname === "/app/") {
    await Router.navigate(homeForUser(user), true);
  } else {
    await Router.start();
  }
}

boot();

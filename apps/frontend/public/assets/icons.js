(function () {
  const icons = {
    company: '<path d="M3 21h18M5 21V7l7-4 7 4v14M9 9h.01M15 9h.01M9 13h.01M15 13h.01M9 17h6"/>',
    team: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM22 21v-2a4 4 0 0 0-3-3.87"/>',
    user: '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z"/>',
    meet: '<path d="M15 10l5-3v10l-5-3v-4zM2 6h13v12H2z"/>',
    trophy: '<path d="M6 9a6 6 0 0 0 12 0V3H6zM6 5H3v2a3 3 0 0 0 3 3M18 5h3v2a3 3 0 0 1-3 3M9 21h6M12 17v4"/>',
    plug: '<path d="M9 2v6M15 2v6M7 8h10v3a5 5 0 0 1-10 0zM12 16v6"/>',
    tg: '<path d="M22 3 2 11l6 2 2 7 3-4 5 4 4-17z"/>',
    daemon: '<path d="M12 2a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3zM19 10v1a7 7 0 0 1-14 0v-1M12 18v4M8 22h8"/>',
    deploy: '<path d="M4 17l6-6-6-6M12 19h8"/>',
    cog: '<path d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19 12a7 7 0 1 1-14 0 7 7 0 0 1 14 0z"/>',
    board: '<path d="M3 5h18M7 5v14M14 5v14M3 19h18M3 5v14h18V5"/>',
    inbox: '<path d="M4 4h16l2 10h-5a5 5 0 0 1-10 0H2zM8 4l-2 10M16 4l2 10"/>',
    map: '<path d="M12 3v6M6 13h12M6 13v6M18 13v6M4 19h4M10 9h4M16 19h4"/>',
    menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
    close: '<path d="M6 6l12 12M18 6 6 18"/>',
    board: '<path d="M3 3h7v18H3zM14 3h7v10h-7zM14 17h7v4h-7z"/>',
    inbox: '<path d="M4 4h16v13H4zM4 13h4l2 3h4l2-3h4M8 21h8"/>',
  };
  window.gcIcon = (name, width = 1.7) =>
    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${width}" stroke-linecap="round" stroke-linejoin="round">${icons[name] || ""}</svg>`;
  window.gcMark = (size = 30) => `<svg width="${size}" height="${size}" viewBox="0 0 32 32" fill="none">
    <rect x="5.5" y="5.5" width="21" height="21" rx="5" transform="rotate(45 16 16)" stroke="#C2152E" stroke-width="2"/>
    <path d="M16 9 L23 16 L16 23 Z" fill="#C2152E"/><circle cx="13" cy="16" r="2" fill="#ECECEE"/>
  </svg>`;
  window.gcBrand = (size = 28) => `<a class="brand" href="/">
    <span class="brand-mark">${window.gcMark(size)}</span>
    <span class="brand-name"><b>Grey</b> <span>Cardinal</span></span>
  </a>`;
  window.gcTabs = () => {
    document.querySelectorAll("[data-tabs]").forEach((group) => {
      const scope = group.getAttribute("data-tabs");
      const buttons = group.querySelectorAll("[data-tab]");
      buttons.forEach((button) => button.addEventListener("click", () => {
        buttons.forEach((item) => item.classList.remove("active"));
        button.classList.add("active");
        document.querySelectorAll(`[data-panel][data-scope="${scope}"]`).forEach((panel) => {
          panel.style.display = panel.dataset.panel === button.dataset.tab ? "" : "none";
        });
      }));
    });
  };

  window.gcSidebar = (user, role) => {
    const sidebar = document.querySelector(".sidebar");
    if (!sidebar) return;
    const initials = (user.display_name || user.login || "GC")
      .split(/\s+/).map((part) => part[0]).join("").slice(0, 2).toUpperCase();
    const item = (pattern, icon, label, href, roles) =>
      roles.includes(role)
        ? `<a class="nav-item" data-route="${pattern}" href="${href}">${window.gcIcon(icon)}<span>${label}</span></a>`
        : "";
    sidebar.innerHTML = `
      <div class="sidebar-brand">${window.gcBrand(28)}<button class="sidebar-close" type="button" aria-label="Закрыть меню">${window.gcIcon("close")}</button></div>
      <a class="role-chip" href="/app/me">
        <span class="av" style="${user.photo_data_url ? `background-image:url('${user.photo_data_url}');background-size:cover;background-position:center` : "background:#C2152E"}">${user.photo_data_url ? "" : initials}</span>
        <span class="meta grow"><b>${escapeHtml(user.display_name || user.login)}</b><span>${roleLabel(role)}</span></span>
        ${window.gcIcon("cog")}
      </a>
      <div class="nav-group"><div class="nav-label">Командные центры</div>
        ${item("/app/companies", "company", "Компании", "/app/companies", ["director"])}
        ${item("/app/teams/:id", "team", "Команда", firstTeam(user), ["director", "manager"])}
        ${item("/app/employee", "user", "Моя панель", "/app/employee", ["employee"])}
      </div>
      <div class="nav-group"><div class="nav-label">Аккаунт</div>
        ${item("/app/me", "user", "Профиль", "/app/me", ["director", "manager", "employee"])}
        ${item("/app/settings", "cog", "Настройки", "/app/settings", ["director", "manager", "employee"])}
      </div>
      <div class="nav-group"><div class="nav-label">Рабочее пространство</div>
        ${item("/app/teams/:teamId/board", "board", "Grey Board", firstBoard(user), ["director", "manager", "employee"])}
        ${item("/app/teams/:teamId/ai-inbox", "inbox", "AI Inbox", firstInbox(user), ["director", "manager"])}
        ${item("/app/meetings", "meet", "Созвоны", "/app/meetings", ["director", "manager", "employee"])}
        ${item("/app/leaderboard", "trophy", "Лидерборд", "/app/leaderboard", ["director", "manager", "employee"])}
      </div>
      <div class="nav-group"><div class="nav-label">Интеграции</div>
        ${item("/app/integrations", "plug", "Обзор", "/app/integrations", ["director", "manager"])}
        ${item("/app/integrations/telegram", "tg", "Telegram", "/app/integrations/telegram", ["director", "manager", "employee"])}
        ${item("/app/integrations/daemon", "daemon", "Daemon", "/app/integrations/daemon", ["director", "manager", "employee"])}
      </div>
      <div class="sidebar-foot">${item("/app/deploy", "deploy", "Деплой", "/app/deploy", ["director"])}</div>`;
  };

  const extendSidebar = (sidebar, user, role, item) => {
    const teamId = user.teams?.[0]?.id;
    const companyId = user.companies?.[0]?.id;
    const firstGroup = sidebar.querySelector(".nav-group");
    if (firstGroup && teamId) {
      firstGroup.insertAdjacentHTML("beforeend", `
        ${item("/app/teams/:id/board", "board", "Grey Board", `/app/teams/${teamId}/board`, ["director", "manager", "employee"])}
        ${item("/app/teams/:id/ai-inbox", "inbox", "AI Inbox", `/app/teams/${teamId}/ai-inbox`, ["director", "manager"])}
        ${item("/app/teams/:id/setup", "cog", "Setup Wizard", `/app/teams/${teamId}/setup`, ["director", "manager"])}
        ${item("/app/teams/:id/yougile", "plug", "YouGile Sync", `/app/teams/${teamId}/yougile`, ["director", "manager"])}
        ${item("/app/teams/:id/people", "team", "People", `/app/teams/${teamId}/people`, ["director", "manager", "employee"])}
      `);
    }
    if (firstGroup && companyId) {
      firstGroup.insertAdjacentHTML("beforeend", item("/app/companies/:id/map", "map", "Team Map", `/app/companies/${companyId}/map`, ["director"]));
    }
  };

  const originalSidebar = window.gcSidebar;
  window.gcSidebar = (user, role) => {
    originalSidebar(user, role);
    const sidebar = document.querySelector(".sidebar");
    if (!sidebar) return;
    const item = (pattern, icon, label, href, roles) =>
      roles.includes(role)
        ? `<a class="nav-item" data-route="${pattern}" href="${href}">${window.gcIcon(icon)}<span>${label}</span></a>`
        : "";
    extendSidebar(sidebar, user, role, item);
  };

  function firstTeam(user) {
    return user.teams?.[0] ? `/app/teams/${user.teams[0].id}` : "/app/teams";
  }
  function firstBoard(user) {
    return user.teams?.[0] ? `/app/teams/${user.teams[0].id}/board` : "/app/teams";
  }
  function firstInbox(user) {
    return user.teams?.[0] ? `/app/teams/${user.teams[0].id}/ai-inbox` : "/app/teams";
  }
  function roleLabel(role) {
    return { director: "Директор", manager: "Руководитель", employee: "Сотрудник" }[role];
  }
  function escapeHtml(value) {
    return String(value || "").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[char]);
  }
})();

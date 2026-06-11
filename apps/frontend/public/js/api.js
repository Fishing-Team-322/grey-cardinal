const BASE = "";

export class ApiError extends Error {
  constructor(status, code, body) {
    super(`API ${status}: ${code}`);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.body = body;
  }
}

export async function request(method, path, { body, query, headers } = {}) {
  const params = query
    ? new URLSearchParams(Object.entries(query).filter(([, value]) => value != null))
    : null;
  const url = path + (params?.toString() ? `?${params}` : "");
  const response = await fetch(BASE + url, {
    method,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...headers },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (response.status === 401 && !path.startsWith("/api/auth/")) {
    const next = `${location.pathname}${location.search}`;
    window.location.href = `/login.html?next=${encodeURIComponent(next)}`;
    throw new ApiError(401, "unauthorized", null);
  }
  if (response.status === 204) return null;

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail;
    const code = data.error || detail?.error || detail || "error";
    throw new ApiError(response.status, code, data);
  }
  return data;
}

export const api = {
  auth: {
    login(email, password) {
      return request("POST", "/api/auth/login", { body: { email, password } });
    },
    register({ email, login, firstName, lastName, password }) {
      return request("POST", "/api/auth/register", {
        body: { email, login, first_name: firstName, last_name: lastName, password },
      });
    },
    logout() {
      return request("POST", "/api/auth/logout");
    },
    me() {
      return request("GET", "/api/auth/me");
    },
    update(body) {
      return request("PATCH", "/api/auth/me", { body });
    },
    changePassword(oldPassword, newPassword) {
      return request("POST", "/api/auth/change-password", {
        body: { old_password: oldPassword, new_password: newPassword },
      });
    },
  },
  context() {
    return request("GET", "/api/me");
  },
  companies: {
    list() {
      return request("GET", "/api/companies/me");
    },
    create(name, timezone) {
      return request("POST", "/api/companies", { body: { name, timezone } });
    },
    overview(id) {
      return request("GET", `/api/companies/${id}/overview`);
    },
    map(id) {
      return request("GET", `/api/companies/${id}/map`);
    },
    recommendations(id) {
      return request("GET", `/api/companies/${id}/recommendations`);
    },
  },
  teams: {
    create(companyId, name, timezone) {
      return request("POST", `/api/companies/${companyId}/teams`, {
        body: { name, timezone },
      });
    },
    get(id) {
      return request("GET", `/api/teams/${id}`);
    },
    members(id) {
      return request("GET", `/api/teams/${id}/members`);
    },
    updateMemberRole(teamId, userId, role) {
      return request("PATCH", `/api/teams/${teamId}/members/${userId}`, { body: { role } });
    },
    removeMember(teamId, userId) {
      return request("DELETE", `/api/teams/${teamId}/members/${userId}`);
    },
    invite(team, role) {
      return request("POST", `/api/companies/${team.company_id}/invites`, {
        body: { scope: "team", team_id: team.id, role },
      });
    },
    telegramStatus(id) {
      return request("GET", `/api/teams/${id}/telegram/status`);
    },
    telegramBindCode(id) {
      return request("POST", `/api/teams/${id}/telegram/bind-code`);
    },
    botSettings(id) {
      return request("GET", `/api/teams/${id}/bot-settings`);
    },
    saveBotSettings(id, body) {
      return request("PUT", `/api/teams/${id}/bot-settings`, { body });
    },
  },
  invites: {
    preview(token) {
      return request("GET", `/api/invites/${encodeURIComponent(token)}`);
    },
    accept(token) {
      return request("POST", `/api/invites/${encodeURIComponent(token)}/accept`);
    },
  },
  telegram: {
    requestLink() {
      return request("POST", "/api/users/me/telegram/link");
    },
    status() {
      return request("GET", "/api/users/me/telegram/status");
    },
    unlink() {
      return request("DELETE", "/api/users/me/telegram");
    },
  },
  yougile: {
    login(teamId, login, password) {
      return request("POST", `/api/teams/${teamId}/integrations/yougile/login`, {
        body: { login, password },
      });
    },
    connect(teamId, onboardingToken, companyId) {
      return request("POST", `/api/teams/${teamId}/integrations/yougile/connect`, {
        body: { onboarding_token: onboardingToken, company_id: companyId },
      });
    },
    status(teamId) {
      return request("GET", `/api/teams/${teamId}/integrations/yougile/status`);
    },
    disconnect(teamId) {
      return request("DELETE", `/api/teams/${teamId}/integrations/yougile`);
    },
    projects(teamId) {
      return request("GET", `/api/teams/${teamId}/board/projects`);
    },
    boards(teamId, projectId) {
      return request("GET", `/api/teams/${teamId}/board/projects/${projectId}/boards`);
    },
    tasks(teamId, columnId) {
      return request("GET", `/api/teams/${teamId}/board/columns/${columnId}/tasks`);
    },
    syncNow(teamId) {
      return request("POST", `/api/teams/${teamId}/integrations/yougile/sync`);
    },
    mirrorBoards(teamId) {
      return request("GET", `/api/teams/${teamId}/integrations/yougile/boards`);
    },
    selectBoard(teamId, boardId, columnMappings) {
      return request("POST", `/api/teams/${teamId}/integrations/yougile/select-board`, {
        body: { board_id: boardId, column_mappings: columnMappings },
      });
    },
    importBoard(teamId) {
      return request("POST", `/api/teams/${teamId}/integrations/yougile/import`);
    },
    syncEvents(teamId) {
      return request("GET", `/api/teams/${teamId}/integrations/yougile/sync-events`);
    },
  },
  llm: {
    health(teamId) {
      return request("GET", `/api/teams/${teamId}/llm/health`);
    },
    settings(teamId) {
      return request("GET", `/api/teams/${teamId}/llm-settings`);
    },
    saveSettings(teamId, body) {
      return request("POST", `/api/teams/${teamId}/llm-settings`, { body });
    },
  },
  meetings: {
    list(teamId) {
      return request("GET", `/api/teams/${teamId}/meetings`);
    },
    get(id) {
      return request("GET", `/api/meetings/${id}`);
    },
    create(teamId, title, scheduledAt, durationMinutes = 60) {
      return request("POST", `/api/teams/${teamId}/meetings`, {
        body: { title, scheduled_at: scheduledAt, duration_minutes: durationMinutes },
      });
    },
    confirm(id) {
      return request("POST", `/api/meetings/${id}/confirm`);
    },
    rsvp(id, status) {
      return request("POST", `/api/meetings/${id}/rsvp`, { body: { status } });
    },
    cancel(id) {
      return request("POST", `/api/meetings/${id}/cancel`);
    },
  },
  tasks: {
    list(teamId, query = {}) {
      return request("GET", `/api/teams/${teamId}/tasks`, { query });
    },
    statusResponse(taskId, response, reason) {
      return request("POST", `/api/tasks/${taskId}/status-response`, {
        body: { response, reason },
      });
    },
    move(taskId, status) {
      return request("POST", `/api/tasks/${taskId}/move`, { body: { status } });
    },
    assign(taskId, userId) {
      return request("POST", `/api/tasks/${taskId}/assign`, { body: { user_id: userId } });
    },
    deadline(taskId, deadline) {
      return request("POST", `/api/tasks/${taskId}/deadline`, { body: { deadline } });
    },
    askStatus(taskId) {
      return request("POST", `/api/tasks/${taskId}/ask-status`);
    },
    comments(taskId) {
      return request("GET", `/api/tasks/${taskId}/comments`);
    },
    addComment(taskId, body) {
      return request("POST", `/api/tasks/${taskId}/comments`, { body: { body } });
    },
  },
  greyBoard: {
    get(teamId, view) {
      return request("GET", `/api/teams/${teamId}/grey-board`, { query: { view } });
    },
    kanbanConfig(teamId) {
      return request("GET", `/api/teams/${teamId}/kanban-config`);
    },
    saveKanbanConfig(teamId, columns) {
      return request("PUT", `/api/teams/${teamId}/kanban-config`, { body: { columns } });
    },
    createTask(teamId, body) {
      return request("POST", `/api/teams/${teamId}/task-command/confirm`, { body });
    },
  },
  aiInbox: {
    list(teamId) {
      return request("GET", `/api/teams/${teamId}/ai-inbox`).then((data) => data.items || data);
    },
    approve(itemId) {
      return request("POST", `/api/ai-inbox/${itemId}/approve`);
    },
    reject(itemId) {
      return request("POST", `/api/ai-inbox/${itemId}/reject`);
    },
    assign(itemId, userId) {
      return request("POST", `/api/ai-inbox/${itemId}/assign`, { body: { user_id: userId } });
    },
  },
  people: {
    me() {
      return request("GET", "/api/users/me/profile");
    },
    profile(userId) {
      return request("GET", `/api/users/me/profile`, { query: { user_id: userId } });
    },
    team(teamId) {
      return request("GET", `/api/teams/${teamId}/people`);
    },
    update(body) {
      return request("PATCH", "/api/auth/me", { body });
    },
  },
  leaderboards: {
    me() {
      return request("GET", "/api/users/me/gamification");
    },
    team(teamId) {
      return request("GET", `/api/teams/${teamId}/leaderboard`);
    },
    company(companyId) {
      return request("GET", `/api/leaderboards/company/${companyId}`);
    },
  },
  daemon: {
    pairingCode() {
      return request("POST", "/api/agents/pairing-code");
    },
    status() {
      return request("GET", "/api/agents");
    },
    unpair(id) {
      return request("POST", `/api/agents/${id}/unpair`);
    },
  },
  telemost: {
    status() {
      return request("GET", "/api/integrations/telemost/status");
    },
  },
  yandexTelemost: {
    status(teamId) {
      return request("GET", "/api/integrations/yandex-telemost/status", {
        query: { team_id: teamId },
      });
    },
    connectStart(teamId) {
      return request("POST", "/api/integrations/yandex-telemost/connect/start", {
        body: { team_id: teamId },
      });
    },
    disconnect(teamId) {
      return request("POST", "/api/integrations/yandex-telemost/disconnect", {
        body: { team_id: teamId },
      });
    },
    saveSettings(teamId, settings) {
      return request("PATCH", "/api/integrations/yandex-telemost/settings", {
        body: { team_id: teamId, ...settings },
      });
    },
    testCreateRoom(teamId) {
      return request("POST", "/api/integrations/yandex-telemost/test-create-room", {
        body: { team_id: teamId },
      });
    },
    recordingJobs(teamId) {
      return request("GET", "/api/integrations/yandex-telemost/recording-jobs", {
        query: { team_id: teamId },
      });
    },
    startRecordingJob(jobId) {
      return request("POST", `/api/integrations/yandex-telemost/recording-jobs/${jobId}/start`);
    },
    stopRecordingJob(jobId) {
      return request("POST", `/api/integrations/yandex-telemost/recording-jobs/${jobId}/stop`);
    },
  },
  deploy: {
    status() {
      return request("GET", "/api/deploy/status");
    },
  },
  teamPet: {
    get(teamId) {
      return request("GET", `/api/teams/${teamId}/pet`);
    },
    create(teamId, body) {
      return request("POST", `/api/teams/${teamId}/pet`, { body });
    },
    rename(teamId, name) {
      return request("PATCH", `/api/teams/${teamId}/pet`, { body: { name } });
    },
    events(teamId, query = {}) {
      return request("GET", `/api/teams/${teamId}/pet/events`, { query });
    },
    inventory(teamId) {
      return request("GET", `/api/teams/${teamId}/pet/inventory`);
    },
    equip(teamId, itemId) {
      return request("POST", `/api/teams/${teamId}/pet/equip`, { body: { item_id: itemId } });
    },
    wellbeing(teamId) {
      return request("GET", `/api/teams/${teamId}/wellbeing`);
    },
    privacyGet(teamId) {
      return request("GET", `/api/teams/${teamId}/pet/privacy`);
    },
    privacySave(teamId, body) {
      return request("PUT", `/api/teams/${teamId}/pet/privacy`, { body });
    },
    battleCurrent() {
      return request("GET", "/api/team-battles/current");
    },
    battleLeaderboard(teamId) {
      return request("GET", "/api/team-battles/current/leaderboard", { query: { team_id: teamId } });
    },
  },
};

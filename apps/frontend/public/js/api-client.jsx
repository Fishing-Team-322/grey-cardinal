// Grey Cardinal — v2 browser API client.
// Только публичные /api/* эндпоинты + httpOnly cookie-сессия (credentials: include).
// Без internal-токенов и сервисных роутов, без demo-эндпоинтов.

const gcApiOrigin = () => String(window.GC_API_ORIGIN || '').replace(/\/$/, '');

const gcFetch = async (path, options = {}) => {
  const url = gcApiOrigin() + path;
  let response;
  try {
    response = await fetch(url, {
      method: options.method || 'GET',
      credentials: 'include',
      headers: {
        ...(options.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
        ...(options.headers || {}),
      },
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });
  } catch (_) {
    throw new Error('Backend недоступен: проверьте соединение.');
  }
  if (response.status === 204) return null;
  const text = await response.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch (_) { data = { detail: text }; }
  if (!response.ok) {
    const detail = data && (data.detail || data.message);
    const err = new Error(detail || `${response.status} ${response.statusText}`);
    err.status = response.status;
    throw err;
  }
  return data;
};

const GCApi = {
  origin: gcApiOrigin,
  health: () => gcFetch('/health'),

  // ── Auth / identity ──────────────────────────────────────────────────────
  register: (body) => gcFetch('/api/auth/register', { method: 'POST', body }),
  login: (body) => gcFetch('/api/auth/login', { method: 'POST', body }),
  logout: () => gcFetch('/api/auth/logout', { method: 'POST' }),
  authMe: () => gcFetch('/api/auth/me'),
  me: () => gcFetch('/api/me'),

  // ── Companies / teams / invites ──────────────────────────────────────────
  createCompany: (body) => gcFetch('/api/companies', { method: 'POST', body }),
  myCompanies: () => gcFetch('/api/companies/me'),
  companyOverview: (companyId) => gcFetch(`/api/companies/${companyId}/overview`),
  createTeam: (companyId, body) =>
    gcFetch(`/api/companies/${companyId}/teams`, { method: 'POST', body }),
  getTeam: (teamId) => gcFetch(`/api/teams/${teamId}`),
  createInvite: (companyId, body) =>
    gcFetch(`/api/companies/${companyId}/invites`, { method: 'POST', body }),
  getInvite: (token) => gcFetch(`/api/invites/${encodeURIComponent(token)}`),
  acceptInvite: (token) =>
    gcFetch(`/api/invites/${encodeURIComponent(token)}/accept`, { method: 'POST' }),

  // ── PC agent (daemon) token ──────────────────────────────────────────────
  agentToken: () => gcFetch('/api/daemon/token', { method: 'POST' }),

  // ── Personal Telegram link ───────────────────────────────────────────────
  telegramLinkStart: () => gcFetch('/api/users/me/telegram/link', { method: 'POST' }),
  telegramStatus: () => gcFetch('/api/users/me/telegram/status'),
  telegramUnlink: () => gcFetch('/api/users/me/telegram', { method: 'DELETE' }),

  // ── Team Telegram chat binding ───────────────────────────────────────────
  teamBindCode: (teamId) =>
    gcFetch(`/api/teams/${teamId}/telegram/bind-code`, { method: 'POST' }),
  teamTelegramStatus: (teamId) => gcFetch(`/api/teams/${teamId}/telegram/status`),
  teamTelegramUnlink: (teamId) =>
    gcFetch(`/api/teams/${teamId}/telegram`, { method: 'DELETE' }),

  // ── Board (YouGile) ──────────────────────────────────────────────────────
  setBoard: (teamId, body) => gcFetch(`/api/teams/${teamId}/board`, { method: 'POST', body }),
  boardStatus: (teamId) => gcFetch(`/api/teams/${teamId}/board/status`),
  deleteBoard: (teamId) => gcFetch(`/api/teams/${teamId}/board`, { method: 'DELETE' }),

  // ── LLM settings ─────────────────────────────────────────────────────────
  setLLM: (teamId, body) => gcFetch(`/api/teams/${teamId}/llm-settings`, { method: 'POST', body }),
  getLLM: (teamId) => gcFetch(`/api/teams/${teamId}/llm-settings`),
  llmHealth: (teamId) => gcFetch(`/api/teams/${teamId}/llm/health`),

  // ── Meetings ─────────────────────────────────────────────────────────────
  listMeetings: (teamId) => gcFetch(`/api/teams/${teamId}/meetings`),
  createMeeting: (teamId, body) =>
    gcFetch(`/api/teams/${teamId}/meetings`, { method: 'POST', body }),
  confirmMeeting: (id) => gcFetch(`/api/meetings/${id}/confirm`, { method: 'POST' }),
  cancelMeeting: (id) => gcFetch(`/api/meetings/${id}/cancel`, { method: 'POST' }),
  rsvpMeeting: (id, status) =>
    gcFetch(`/api/meetings/${id}/rsvp`, { method: 'POST', body: { status } }),

  // ── Daily sync ───────────────────────────────────────────────────────────
  syncStart: (teamId) => gcFetch(`/api/teams/${teamId}/sync/start`, { method: 'POST' }),
  syncStatus: (teamId) => gcFetch(`/api/teams/${teamId}/sync/status`),
  syncClose: (teamId) => gcFetch(`/api/teams/${teamId}/sync/close`, { method: 'POST' }),
};

const gcGuessTimezone = () => {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || 'Europe/Moscow'; }
  catch (_) { return 'Europe/Moscow'; }
};

const gcFormatDateTime = (value) => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString('ru-RU', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
  });
};

Object.assign(window, { GCApi, gcGuessTimezone, gcFormatDateTime });

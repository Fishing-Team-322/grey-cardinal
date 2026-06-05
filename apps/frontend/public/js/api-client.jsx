// Grey Cardinal - browser API bridge for brain-api.

const GC_API_STORAGE = {
  baseUrl: 'gc.api.baseUrl',
  internalToken: 'gc.api.internalToken',
  desktopIdentity: 'gc.api.desktopIdentity',
};

const gcDefaultApiBaseUrl = () => {
  const configured = window.GC_API_BASE_URL;
  if (configured) return configured.replace(/\/$/, '');
  return '/api';
};

const gcApiConfig = () => ({
  baseUrl: (localStorage.getItem(GC_API_STORAGE.baseUrl) || gcDefaultApiBaseUrl()).replace(/\/$/, ''),
  internalToken: localStorage.getItem(GC_API_STORAGE.internalToken) || window.GC_INTERNAL_TOKEN || 'dev-internal-token',
  desktopIdentity: JSON.parse(localStorage.getItem(GC_API_STORAGE.desktopIdentity) || 'null'),
});

const gcSaveApiConfig = ({ baseUrl, internalToken, desktopIdentity }) => {
  if (baseUrl != null) localStorage.setItem(GC_API_STORAGE.baseUrl, baseUrl.replace(/\/$/, ''));
  if (internalToken != null) localStorage.setItem(GC_API_STORAGE.internalToken, internalToken);
  if (desktopIdentity !== undefined) {
    if (desktopIdentity) {
      localStorage.setItem(GC_API_STORAGE.desktopIdentity, JSON.stringify(desktopIdentity));
    } else {
      localStorage.removeItem(GC_API_STORAGE.desktopIdentity);
    }
  }
};

const gcHeaders = (withToken = true, extra = {}) => {
  const config = gcApiConfig();
  const headers = { ...extra };
  if (withToken && config.internalToken) headers['X-Internal-Token'] = config.internalToken;
  return headers;
};

const gcDesktopHeaders = () => {
  const identity = gcApiConfig().desktopIdentity;
  return identity ? {
    'X-GC-User-Id': identity.user_id,
    'X-GC-Device-Id': identity.device_id,
    'X-GC-Client-Session-Id': identity.client_session_id,
  } : {};
};

const gcRequest = async (path, options = {}) => {
  const config = gcApiConfig();
  const normalizedPath = config.baseUrl.endsWith('/api') && path.startsWith('/api/')
    ? path.slice(4)
    : path;
  const url = normalizedPath.startsWith('http') ? normalizedPath : `${config.baseUrl}${normalizedPath}`;
  let response;
  try {
    response = await fetch(url, {
      ...options,
      headers: {
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        ...gcHeaders(options.internal !== false),
        ...(options.desktop ? gcDesktopHeaders() : {}),
        ...(options.headers || {}),
      },
    });
  } catch (_) {
    throw new Error('brain-api недоступен: проверьте URL backend, порт 8000 и CORS');
  }
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const detail = data && (data.detail || data.message);
    throw new Error(detail || `${response.status} ${response.statusText}`);
  }
  return data;
};

const gcPriorityLabel = (priority) => ({
  critical: 'Critical',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
}[priority] || 'Medium');

const gcStatusColumn = (status) => ({
  proposed: 'Backlog',
  confirmed: 'Todo',
  todo: 'Todo',
  in_progress: 'In Progress',
  blocked: 'Review',
  done: 'Done',
  rejected: 'Backlog',
  cancelled: 'Backlog',
}[status] || 'Todo');

const gcFormatDate = (value) => {
  if (!value) return 'без дедлайна';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString('ru-RU', { day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit' });
};

const gcMapTask = (task, i = 0) => ({
  id: task.id || task.public_id || `task-${i}`,
  publicId: task.public_id,
  title: task.title,
  who: task.assignee_text || 'не назначен',
  whoInit: (task.assignee_text || '?').slice(0, 1).toUpperCase(),
  due: gcFormatDate(task.deadline),
  prio: gcPriorityLabel(task.priority),
  conf: task.source === 'meeting_transcript' ? 87 : 72,
  source: task.source || 'brain-api',
  status: task.status || 'todo',
  boardUrl: task.board_url,
  voice: task.source === 'meeting_transcript',
  risk: ['high', 'critical'].includes(task.priority) || task.status === 'blocked',
  raw: task,
});

const gcMapTranscript = (item, i = 0) => {
  const name = item.speaker_name || item.speaker?.resolved_name || 'Участник';
  const colors = ['#3b82c4', '#3da37a', '#d68b1c', '#e23a52'];
  const date = item.ts || item.created_at;
  return {
    id: item.id || `tr-${i}`,
    name,
    init: name.slice(0, 1).toUpperCase(),
    color: colors[i % colors.length],
    time: date ? new Date(date).toLocaleTimeString('ru-RU', { hour:'2-digit', minute:'2-digit' }) : '--:--',
    text: item.text,
    status: item.is_final === false ? 'proc' : 'final',
    raw: item,
  };
};

const gcBuildKanban = (tasks) => {
  const colors = ['#3b82c4', '#3da37a', '#d68b1c', '#e23a52'];
  const columns = { Backlog: [], Todo: [], 'In Progress': [], Review: [], Done: [] };
  tasks.forEach((task, i) => {
    const col = gcStatusColumn(task.status);
    columns[col].push({
      id: task.id,
      title: task.title,
      who: task.who,
      color: colors[i % colors.length],
      risk: task.risk,
    });
  });
  return columns;
};

const gcDemoCommandPayload = (command) => ({
  update_id: Date.now(),
  message_id: Date.now() % 100000,
  chat: { id: -100777000, type: 'group', title: 'Frontend Demo' },
  sender: { id: 777, username: 'frontend', first_name: 'Frontend' },
  command,
  args: [],
  text: `/${command}`,
  date: new Date().toISOString(),
  raw: { source: 'frontend' },
});

const GCApi = {
  config: gcApiConfig,
  saveConfig: gcSaveApiConfig,
  health: () => gcRequest('/api/health', { internal: false }),
  // --- Account / workspace / daemon pairing ---
  getProfile: (workspaceId) =>
    gcRequest(`/api/profile${workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : ''}`, { internal: false }),
  createPairingCode: (workspaceId) => gcRequest('/api/agents/pairing-code', {
    method: 'POST',
    internal: false,
    body: JSON.stringify({ workspace_id: workspaceId || null }),
  }),
  listAgents: (workspaceId) =>
    gcRequest(`/api/agents${workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : ''}`, { internal: false })
      .then((data) => data.agents || []),
  listDaemonUploads: (workspaceId) =>
    gcRequest(`/api/daemon/uploads${workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : ''}`, { internal: false })
      .then((data) => data.uploads || []),
  unpairAgent: (agentId, workspaceId) =>
    gcRequest(`/api/agents/${agentId}/unpair${workspaceId ? `?workspace_id=${encodeURIComponent(workspaceId)}` : ''}`, {
      method: 'POST',
      internal: false,
    }),
  ready: () => gcRequest('/ready', { internal: false }),
  dependencies: () => gcRequest('/internal/debug/health/dependencies'),
  state: () => gcRequest('/internal/debug/state'),
  tasks: () => gcRequest('/internal/tasks').then((data) => (data.tasks || []).map(gcMapTask)),
  transcripts: () => gcRequest('/internal/audio/transcripts/recent?limit=20').then((data) => (data.items || []).map(gcMapTranscript)),
  meetings: () => gcRequest('/internal/meetings/recent?limit=10').then((data) => data.items || []),
  activeMeeting: () => gcRequest('/internal/meetings/active'),
  demoCommand: (command) => gcRequest('/internal/telegram/command', {
    method: 'POST',
    body: JSON.stringify(gcDemoCommandPayload(command)),
  }),
  registerDesktop: (payload) => gcRequest('/desktop/devices/register', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
  desktopTasks: () => gcRequest('/desktop/tasks', { desktop: true }).then((data) => (data.tasks || []).map(gcMapTask)),
  desktopTranscripts: () => gcRequest('/desktop/transcripts/recent?limit=20', { desktop: true }).then((data) => (data.items || []).map(gcMapTranscript)),
  desktopGamification: () => gcRequest('/desktop/gamification/me', { desktop: true }),
  sendChatMessage: (text, author = 'demo-user') => gcRequest('/api/chat/messages', {
    method: 'POST',
    internal: false,
    body: JSON.stringify({ chat_id: 'demo', message_id: `web-${Date.now()}`, author, text }),
  }),
  getProposals: (status) => gcRequest(`/api/task-proposals${status ? `?status=${encodeURIComponent(status)}` : ''}`, { internal: false })
    .then((data) => data.proposals || []),
  confirmProposal: (proposalId) => gcRequest(`/api/task-proposals/${proposalId}/confirm`, {
    method: 'POST',
    internal: false,
  }).then((data) => data.task),
  rejectProposal: (proposalId) => gcRequest(`/api/task-proposals/${proposalId}/reject`, {
    method: 'POST',
    internal: false,
  }),
  getBoard: () => gcRequest('/api/board', { internal: false }).then((data) => data.columns || []),
  moveTask: (taskId, status) => gcRequest(`/api/tasks/${taskId}/move`, {
    method: 'POST',
    internal: false,
    body: JSON.stringify({ status }),
  }).then((data) => data.task),
  getEveningDigest: () => gcRequest('/api/digest/evening', { internal: false }),
  getYouGileStatus: () => gcRequest('/api/integrations/yougile/status', { internal: false }),
  daemonUploads: () => gcRequest('/api/meetings', { internal: false }).then((data) => data.meetings || []),
  syncTaskYouGile: (taskId) => gcRequest(`/api/tasks/${taskId}/sync-yougile`, {
    method: 'POST',
    internal: false,
  }).then((data) => data.task),
  wsUrl: () => {
    const configured = window.GC_WS_URL;
    if (configured) return configured;
    const base = gcApiConfig().baseUrl;
    if (/^https?:\/\//.test(base) && !base.endsWith('/api')) {
      return base.replace(/^http/, 'ws') + '/ws/events';
    }
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.host}/ws/events`;
  },
  mapTask: gcMapTask,
  mapTranscript: gcMapTranscript,
  buildKanban: gcBuildKanban,
};

Object.assign(window, { GCApi });

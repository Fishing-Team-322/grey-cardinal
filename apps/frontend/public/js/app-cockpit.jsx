// Grey Cardinal - /app cockpit connected to public brain-api demo endpoints.

const statusLabel = (status) => ({
  todo: 'todo',
  in_progress: 'in progress',
  done: 'done',
  pending: 'pending',
  confirmed: 'confirmed',
  rejected: 'rejected',
}[status] || status || 'unknown');

const ygClass = (status) => ({
  synced: 'gca-badge--ok',
  error: 'gca-badge--high',
  pending: 'gca-badge--med',
  disabled: '',
}[status] || '');

const PROFILE_STORAGE_KEY = 'gc.cockpit.profile';
const ORGANIZATION_STORAGE_KEY = 'gc.cockpit.organization';
const AUTH_ACCOUNT_STORAGE_KEY = 'gc.auth.account';
const AUTH_SESSION_STORAGE_KEY = 'gc.auth.session';

const DEFAULT_PROFILE = {
  displayName: 'Grey Cardinal',
  login: 'grey-cardinal',
  email: '',
  role: 'Product operator',
  location: 'Remote',
  status: 'Active',
  bio: 'Runs meeting signals, board decisions, and follow-through from one cockpit.',
  photoDataUrl: '',
};

const DEFAULT_ORGANIZATION = {
  name: 'Grey Cardinal Ops',
  slug: 'grey-cardinal-ops',
  description: 'Frontend-only organization workspace for daemon signals, participants, and prepared work.',
  photoDataUrl: '',
  members: [
    { id:'m-1', name:'Grey Cardinal', role:'Owner', status:'active' },
    { id:'m-2', name:'Аня', role:'Operator', status:'active' },
    { id:'m-3', name:'Дима', role:'Daemon maintainer', status:'invited' },
  ],
  invites: [],
};

const PROFILE_ACHIEVEMENTS = [
  {
    id: 'profile-claimed',
    icon: 'user',
    title: 'Profile claimed',
    desc: 'Participant profile is ready inside the cockpit.',
    tier: 'Base',
    tone: 'brand',
  },
  {
    id: 'photo-ready',
    icon: 'image',
    title: 'Face card',
    desc: 'A profile photo has been uploaded.',
    tier: 'Identity',
    tone: 'info',
  },
  {
    id: 'profile-complete',
    icon: 'checkCircle',
    title: 'Readable profile',
    desc: 'Name, login, role, and bio are filled in.',
    tier: 'Identity',
    tone: 'ok',
  },
  {
    id: 'brain-online',
    icon: 'zap',
    title: 'Live link',
    desc: 'Brain API has answered from the cockpit.',
    tier: 'Ops',
    tone: 'ok',
  },
  {
    id: 'proposal-watch',
    icon: 'list',
    title: 'Proposal watch',
    desc: 'Task proposals are visible in the demo flow.',
    tier: 'Ops',
    tone: 'warn',
  },
  {
    id: 'board-keeper',
    icon: 'kanban',
    title: 'Board keeper',
    desc: 'At least one task is present on the board.',
    tier: 'Board',
    tone: 'brand',
  },
  {
    id: 'closer',
    icon: 'target',
    title: 'Closer',
    desc: 'A task reached the done column.',
    tier: 'Board',
    tone: 'ok',
  },
  {
    id: 'daemon-signal',
    icon: 'download',
    title: 'Daemon signal',
    desc: 'Desktop upload data reached the cockpit.',
    tier: 'Infra',
    tone: 'info',
  },
];

const profileAchievementsForLanguage = (language) => {
  if (language !== 'ru') return PROFILE_ACHIEVEMENTS;
  return [
    { id: 'profile-claimed', icon: 'user', title: 'Профиль открыт', desc: 'Профиль участника готов внутри cockpit.', tier: 'База', tone: 'brand' },
    { id: 'photo-ready', icon: 'image', title: 'Фото профиля', desc: 'Фотография профиля загружена.', tier: 'Идентичность', tone: 'info' },
    { id: 'profile-complete', icon: 'checkCircle', title: 'Заполненный профиль', desc: 'Имя, логин, роль и bio заполнены.', tier: 'Идентичность', tone: 'ok' },
    { id: 'brain-online', icon: 'zap', title: 'Живая связь', desc: 'Brain API ответил из cockpit.', tier: 'Ops', tone: 'ok' },
    { id: 'proposal-watch', icon: 'list', title: 'Контроль предложений', desc: 'Task proposals видны в demo flow.', tier: 'Ops', tone: 'warn' },
    { id: 'board-keeper', icon: 'kanban', title: 'Хранитель доски', desc: 'На доске есть хотя бы одна задача.', tier: 'Доска', tone: 'brand' },
    { id: 'closer', icon: 'target', title: 'Закрытие', desc: 'Задача дошла до колонки done.', tier: 'Доска', tone: 'ok' },
    { id: 'daemon-signal', icon: 'download', title: 'Сигнал daemon', desc: 'Desktop upload data дошли до cockpit.', tier: 'Инфра', tone: 'info' },
  ];
};

const DAEMON_HEARING_HISTORY = [
  {
    id: 'dh-1',
    time: '14:02',
    speaker: 'Петя',
    text: 'Давайте оплату подготовим к четвергу, крайний срок - до конца недели.',
    preparedTask: 'Подготовить оплату',
    assignee: 'Петя',
    due: 'Четверг, 18:00',
    confidence: 87,
    status: 'prepared',
  },
  {
    id: 'dh-2',
    time: '14:03',
    speaker: 'Аня',
    text: 'Я проверю интеграцию с YouGile сегодня вечером, примерно к восьми.',
    preparedTask: 'Проверить интеграцию с YouGile',
    assignee: 'Аня',
    due: 'Сегодня, 20:00',
    confidence: 81,
    status: 'prepared',
  },
  {
    id: 'dh-3',
    time: '14:05',
    speaker: 'Дима',
    text: 'Мне нужно до завтра поднять websocket для dashboard.',
    preparedTask: 'Поднять websocket для dashboard',
    assignee: 'Дима',
    due: 'Завтра, 12:00',
    confidence: 91,
    status: 'ready',
  },
  {
    id: 'dh-4',
    time: '14:09',
    speaker: 'Дима',
    text: 'И еще нужно проверить daemon на Windows перед демо.',
    preparedTask: 'Проверить daemon на Windows',
    assignee: 'Дима',
    due: 'Завтра, 16:00',
    confidence: 84,
    status: 'draft',
  },
];

const daemonHearingHistoryForLanguage = (language) => {
  if (language !== 'ru') {
    return [
      { id:'dh-1', time:'14:02', speaker:'Peter', text:'Let us prepare the payment by Thursday, final deadline is the end of the week.', preparedTask:'Prepare payment', assignee:'Peter', due:'Thursday, 18:00', confidence:87, status:'prepared' },
      { id:'dh-2', time:'14:03', speaker:'Anna', text:'I will check the YouGile integration tonight, around eight.', preparedTask:'Check YouGile integration', assignee:'Anna', due:'Today, 20:00', confidence:81, status:'prepared' },
      { id:'dh-3', time:'14:05', speaker:'Dima', text:'I need to bring up the dashboard websocket by tomorrow.', preparedTask:'Bring up dashboard websocket', assignee:'Dima', due:'Tomorrow, 12:00', confidence:91, status:'ready' },
      { id:'dh-4', time:'14:09', speaker:'Dima', text:'And we need to test the daemon on Windows before the demo.', preparedTask:'Test daemon on Windows', assignee:'Dima', due:'Tomorrow, 16:00', confidence:84, status:'draft' },
    ];
  }
  return [
    { id:'dh-1', time:'14:02', speaker:'Петя', text:'Давайте оплату подготовим к четвергу, крайний срок - до конца недели.', preparedTask:'Подготовить оплату', assignee:'Петя', due:'Четверг, 18:00', confidence:87, status:'prepared' },
    { id:'dh-2', time:'14:03', speaker:'Аня', text:'Я проверю интеграцию с YouGile сегодня вечером, примерно к восьми.', preparedTask:'Проверить интеграцию с YouGile', assignee:'Аня', due:'Сегодня, 20:00', confidence:81, status:'prepared' },
    { id:'dh-3', time:'14:05', speaker:'Дима', text:'Мне нужно до завтра поднять websocket для dashboard.', preparedTask:'Поднять websocket для dashboard', assignee:'Дима', due:'Завтра, 12:00', confidence:91, status:'ready' },
    { id:'dh-4', time:'14:09', speaker:'Дима', text:'И еще нужно проверить daemon на Windows перед демо.', preparedTask:'Проверить daemon на Windows', assignee:'Дима', due:'Завтра, 16:00', confidence:84, status:'draft' },
  ];
};

const loadAuthIdentity = () => {
  try {
    return JSON.parse(localStorage.getItem(AUTH_SESSION_STORAGE_KEY) || 'null')
      || JSON.parse(localStorage.getItem(AUTH_ACCOUNT_STORAGE_KEY) || 'null');
  } catch (_) {
    return null;
  }
};

const normalizeProfile = (value) => {
  const auth = loadAuthIdentity();
  const next = { ...DEFAULT_PROFILE, ...(value || {}) };
  const authName = [auth?.firstName, auth?.lastName].filter(Boolean).join(' ').trim();
  return {
    ...next,
    displayName: next.displayName || authName || DEFAULT_PROFILE.displayName,
    login: next.login || next.handle || auth?.login || DEFAULT_PROFILE.login,
    email: next.email || auth?.email || DEFAULT_PROFILE.email,
  };
};
const normalizeOrganization = (value) => {
  if (!value) return null;
  return {
    ...DEFAULT_ORGANIZATION,
    ...value,
    members: Array.isArray(value.members) ? value.members : DEFAULT_ORGANIZATION.members,
    invites: Array.isArray(value.invites) ? value.invites : [],
  };
};

const loadProfile = () => {
  try {
    return normalizeProfile(JSON.parse(localStorage.getItem(PROFILE_STORAGE_KEY) || 'null'));
  } catch (_) {
    return normalizeProfile();
  }
};

const saveProfile = (profile) => {
  const { handle, team, timezone, ...clean } = normalizeProfile(profile);
  localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(clean));
};

const loadOrganization = () => {
  try {
    return normalizeOrganization(JSON.parse(localStorage.getItem(ORGANIZATION_STORAGE_KEY) || 'null'));
  } catch (_) {
    return null;
  }
};

const saveOrganization = (organization) => {
  if (organization) {
    localStorage.setItem(ORGANIZATION_STORAGE_KEY, JSON.stringify(organization));
  } else {
    localStorage.removeItem(ORGANIZATION_STORAGE_KEY);
  }
};

const initialsFor = (name) => {
  const parts = String(name || '').trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return 'GC';
  return parts.slice(0, 2).map((part) => part[0]).join('').toUpperCase();
};

const isProfileComplete = (profile) => (
  Boolean(profile.displayName?.trim())
  && Boolean(profile.login?.trim())
  && Boolean(profile.role?.trim())
  && Boolean(profile.bio?.trim())
);

const buildAchievements = ({ profile, apiState, proposals, taskCount, doneCount, daemonUploads, language }) => {
  const unlocked = {
    'profile-claimed': true,
    'photo-ready': Boolean(profile.photoDataUrl),
    'profile-complete': isProfileComplete(profile),
    'brain-online': apiState.status === 'online',
    'proposal-watch': proposals.length > 0,
    'board-keeper': taskCount > 0,
    closer: doneCount > 0,
    'daemon-signal': daemonUploads.length > 0,
  };
  return profileAchievementsForLanguage(language).map((item) => ({
    ...item,
    unlocked: Boolean(unlocked[item.id]),
  }));
};

const ProfileAvatar = ({ profile, size = 'md' }) => (
  <span className={'gca-profile-avatar gca-profile-avatar--' + size}>
    {profile.photoDataUrl
      ? <img src={profile.photoDataUrl} alt=""/>
      : <span>{initialsFor(profile.displayName)}</span>}
  </span>
);

const OrganizationAvatar = ({ organization, size = 'md' }) => (
  <span className={'gca-org-avatar gca-org-avatar--' + size}>
    {organization?.photoDataUrl
      ? <img src={organization.photoDataUrl} alt=""/>
      : <span>{initialsFor(organization?.name || 'Organization')}</span>}
  </span>
);

const EmptyState = ({ icon = 'grid', title, desc }) => (
  <div className="gca-empty">
    <span className="gca-empty-ic"><Icon name={icon} size={18}/></span>
    <div>
      <div className="gca-empty-title">{title}</div>
      {desc && <div className="gca-empty-desc">{desc}</div>}
    </div>
  </div>
);

const Sidebar = ({ go, counts, section, setSection, profile, language }) => {
  const tr = (ru, en) => copyText(language, ru, en);
  const nav = [
    { sec:tr('РАБОТА', 'WORK'), items:[
      { id:'overview', icon:'grid', label:tr('Главная', 'Overview') },
      { id:'proposals', icon:'list', label:tr('На подтверждение', 'Proposals'), count: counts.proposals },
      { id:'kanban', icon:'kanban', label:tr('Доска', 'Board'), count: counts.tasks },
      { id:'digest', icon:'bell', label:tr('Сводка', 'Digest') },
    ]},
    { sec:'TEAM', items:[
      { id:'profile', icon:'user', label:tr('Профиль', 'Profile') },
      { id:'organization', icon:'users', label:tr('Организация', 'Organization'), count: counts.organization },
      { id:'achievements', icon:'award', label:tr('Анивки', 'Achievements'), count: counts.achievements },
    ]},
    { sec:tr('ИНТЕГРАЦИИ', 'INTEGRATIONS'), items:[
      { id:'daemon', icon:'download', label:tr('Daemon', 'Daemon'), count: counts.daemonUploads },
      { id:'yougile', icon:'plug', label:'YouGile' },
      { id:'api', icon:'server', label:'Backend' },
    ]},
  ];
  return (
    <aside className="gca-sidebar">
      <div className="gca-side-logo"><Logo size={28} sub="COCKPIT"/></div>
      <nav className="gca-nav">
        {nav.map(group => (
          <div key={group.sec}>
            <div className="gca-nav-sec">{group.sec}</div>
            {group.items.map(it => (
              <div
                key={it.id}
                role="button"
                tabIndex={0}
                className={'gca-nav-item' + (section === it.id ? ' active' : '')}
                onClick={() => setSection(it.id)}
                onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') setSection(it.id); }}
              >
                <Icon name={it.icon} size={16}/>
                <span>{it.label}</span>
                {it.count != null && <span className="count">{it.count}</span>}
              </div>
            ))}
          </div>
        ))}
      </nav>
      <div className="gca-side-foot">
        <div
          role="button"
          tabIndex={0}
          className={'gca-side-profile' + (section === 'profile' ? ' active' : '')}
          onClick={() => setSection('profile')}
          onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') setSection('profile'); }}
        >
          <ProfileAvatar profile={profile} size="xs"/>
          <div className="gca-side-profile-copy">
            <div>{profile.displayName || 'Grey Cardinal'}</div>
            <span>{profile.role || 'public demo flow'}</span>
          </div>
        </div>
        <button className="gca-side-exit" onClick={() => go('/')} aria-label={tr('Выйти из cockpit', 'Exit cockpit')}><Icon name="x" size={15}/></button>
      </div>
    </aside>
  );
};

const Topbar = ({ apiState, onRefresh, refreshing, profile, setSection, language, setLanguage }) => {
  const tr = (ru, en) => copyText(language, ru, en);
  return (
  <header className="gca-topbar">
    <div className="gca-ws">
      <span className="label">Backend</span>
      <span className="gca-api-url">{GCApi.config().baseUrl}</span>
    </div>
    <span className={'gca-chip gca-chip--' + apiState.status}>
      <span className={'dot ' + (apiState.status === 'online' ? 'ok' : apiState.status === 'checking' ? 'live' : '')}></span>
      {apiState.status === 'online' ? tr('Brain online', 'Brain online') : apiState.status === 'checking' ? tr('Проверка', 'Checking') : tr('Offline', 'Offline')}
    </span>
    <div className="gca-topbar-spacer"></div>
    <LanguageToggle language={language} setLanguage={setLanguage}/>
    <button className="gca-top-profile" onClick={() => setSection('profile')}>
      <ProfileAvatar profile={profile} size="xxs"/>
      <span>{profile.displayName || tr('Профиль', 'Profile')}</span>
    </button>
    <button className="gc-btn gc-btn--secondary gc-btn--sm" onClick={onRefresh} disabled={refreshing}>
      <Icon name="refresh" size={14}/>{refreshing ? tr('Обновляем...', 'Refreshing...') : tr('Обновить', 'Refresh')}
    </button>
  </header>
  );
};

const CockpitHero = ({ apiState, metrics, ygStatus, language }) => {
  const tr = (ru, en) => copyText(language, ru, en);
  return (
  <section className={'gca-hero-panel gca-hero-panel--' + apiState.status}>
    <div className="gca-hero-copy">
      <span className="gca-panel-eyebrow">WORK COCKPIT</span>
      <h1>{tr('Рабочий центр', 'Work Center')}</h1>
      <p>{tr('Здесь видно, что требует решения: задачи на подтверждение, текущая доска, сводка по срокам и состояние подключений.', 'Here you can see what needs attention: tasks pending confirmation, the current board, deadline summary and connection status.')}</p>
      <div className="gca-source-strip">
        <span className="gca-source-chip"><b>API</b><small>{apiState.message}</small></span>
        <span className="gca-source-chip"><b>WebSocket</b><small>/ws/events</small></span>
        <span className="gca-source-chip"><b>YouGile</b><small>{ygStatus?.status || 'unknown'}</small></span>
        <span className="gca-source-chip"><b>Token</b><small>{tr('не используется в demo flow', 'not used by demo flow')}</small></span>
      </div>
    </div>
    <div className="gca-hero-side">
      <div className="gca-hero-status">
        <span className={'gca-hero-status-dot ' + apiState.status}></span>
        <div>
          <b>{apiState.status === 'online' ? tr('Подключено', 'Connected') : apiState.status === 'checking' ? tr('Проверяем backend', 'Checking backend') : tr('Backend недоступен', 'Backend unavailable')}</b>
          <small>{apiState.message}</small>
        </div>
      </div>
      <div className="gca-hero-metrics">
        {metrics.map((m) => (
          <div className="gca-hero-metric" key={m.label}>
            <span>{m.label}</span>
            <b>{m.value}</b>
          </div>
        ))}
      </div>
    </div>
  </section>
  );
};

const ChatPanel = ({ text, setText, author, setAuthor, onSend, busy, result }) => (
  <div className="gca-panel">
    <div className="gca-panel-head">
      <div className="gca-panel-title"><Icon name="send" size={15}/>Message to task</div>
      <span className="gca-panel-eyebrow">POST /api/chat/messages</span>
    </div>
    <div className="gca-panel-body">
      <div className="gca-api-config">
        <label>
          <span>Author</span>
          <input className="gc-input" value={author} onChange={(e) => setAuthor(e.target.value)}/>
        </label>
        <label>
          <span>Message</span>
          <textarea
            className="gc-input"
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={3}
            style={{ height:90, paddingTop:12, resize:'vertical' }}
          />
        </label>
        <button className="gc-btn gc-btn--primary" onClick={onSend} disabled={busy || !text.trim()}>
          <Icon name="send" size={14}/>{busy ? 'Sending...' : 'Send'}
        </button>
      </div>
      {result && <div className="gca-inline-warning">{result}</div>}
    </div>
  </div>
);

const ProposalCard = ({ proposal, onConfirm, onReject, busy }) => (
  <div className="gca-task">
    <div className="gca-task-top">
      <span className="gca-task-title">{proposal.title}</span>
      <span className="gca-badge gca-badge--med">{Math.round((proposal.confidence || 0) * 100)}%</span>
    </div>
    <dl className="gca-task-meta">
      <dt>Assignee</dt><dd>{proposal.assignee || 'unassigned'}</dd>
      <dt>Deadline</dt><dd>{proposal.deadline || 'none'}</dd>
      <dt>Status</dt><dd>{statusLabel(proposal.status)}</dd>
      <dt>Source</dt><dd>{proposal.source || 'chat'}</dd>
    </dl>
    <div className="gca-controls">
      <button className="gc-btn gc-btn--primary gc-btn--sm" onClick={() => onConfirm(proposal.proposal_id)} disabled={busy}>
        <Icon name="check" size={13}/>Confirm
      </button>
      <button className="gc-btn gc-btn--secondary gc-btn--sm" onClick={() => onReject(proposal.proposal_id)} disabled={busy}>
        <Icon name="x" size={13}/>Reject
      </button>
    </div>
  </div>
);

const ProposalsPanel = ({ proposals, onConfirm, onReject, busy }) => (
  <div className="gca-panel">
    <div className="gca-panel-head">
      <div className="gca-panel-title"><Icon name="list" size={15}/>Pending proposals</div>
      <span className="gca-panel-eyebrow">{proposals.length} pending</span>
    </div>
    <div className="gca-panel-body">
      {proposals.length === 0
        ? <EmptyState icon="checkCircle" title="No pending proposals" desc="Send a message above to create one."/>
        : proposals.map((p) => <ProposalCard key={p.proposal_id} proposal={p} onConfirm={onConfirm} onReject={onReject} busy={busy}/>)}
    </div>
  </div>
);

const BoardTaskCard = ({ task, currentStatus, onMove, onSync, busy }) => (
  <div className={'gca-kcard' + (task.yougile_status === 'error' ? ' risk' : '')}>
    <div className="gca-kcard-title">{task.title}</div>
    <div className="gca-kcard-foot">
      <span className="gca-kcard-assignee">
        <span className="gca-kdot" style={{ background:'#3b82c433', color:'#3b82c4' }}>{(task.assignee || '?')[0]}</span>
        {task.assignee || 'unassigned'}
      </span>
      <span className={'gca-badge ' + ygClass(task.yougile_status)} title={task.yougile_error || task.yougile_task_id || ''}>
        YG {task.yougile_status || 'disabled'}
      </span>
    </div>
    <div className="gca-controls">
      {['todo', 'in_progress', 'done'].filter((status) => status !== currentStatus).map((status) => (
        <button className="gc-btn gc-btn--ghost gc-btn--sm" key={status} onClick={() => onMove(task.task_id, status)} disabled={busy}>
          {statusLabel(status)}
        </button>
      ))}
      {['error', 'disabled'].includes(task.yougile_status) && (
        <button className="gc-btn gc-btn--secondary gc-btn--sm" onClick={() => onSync(task.task_id)} disabled={busy}>
          <Icon name="refresh" size={13}/>Sync
        </button>
      )}
    </div>
  </div>
);

const BoardPanel = ({ columns, onMove, onSync, busy }) => (
  <div className="gca-panel">
    <div className="gca-panel-head">
      <div className="gca-panel-title"><Icon name="kanban" size={15}/>Board</div>
      <span className="gca-panel-eyebrow">GET /api/board</span>
    </div>
    <div className="gca-panel-body">
      <div className="gca-kanban">
        {columns.map((col) => (
          <div className="gca-kcol" key={col.id}>
            <div className="gca-kcol-head">
              <span className="gca-kcol-title">{col.title || statusLabel(col.id)}</span>
              <span className="gca-kcol-count">{(col.tasks || []).length}</span>
            </div>
            {(col.tasks || []).length === 0
              ? <span className="gca-kcol-empty">no tasks</span>
              : col.tasks.map((task) => (
                <BoardTaskCard
                  key={task.task_id}
                  task={task}
                  currentStatus={col.id}
                  onMove={onMove}
                  onSync={onSync}
                  busy={busy}
                />
              ))}
          </div>
        ))}
      </div>
    </div>
  </div>
);

const DigestPanel = ({ digest, onRefresh }) => (
  <div className="gca-panel">
    <div className="gca-panel-head">
      <div className="gca-panel-title"><Icon name="bell" size={15}/>Evening digest</div>
      <span className="gca-panel-eyebrow">GET /api/digest/evening</span>
    </div>
    <div className="gca-panel-body">
      <button className="gc-btn gc-btn--secondary gc-btn--sm" onClick={onRefresh}><Icon name="refresh" size={13}/>Refresh digest</button>
      {!digest ? (
        <EmptyState icon="bell" title="Digest not loaded" desc="Refresh the backend data."/>
      ) : (
        <div className="gca-status-grid">
          <div><span>Date</span><b>{digest.date}</b></div>
          <div><span>Created today</span><b>{(digest.created_today || []).length}</b></div>
          <div><span>Pending</span><b>{(digest.pending_proposals || []).length}</b></div>
          <div><span>Overdue</span><b>{(digest.overdue || []).length}</b></div>
        </div>
      )}
      {digest && Object.keys(digest.by_assignee || {}).length > 0 && (
        <div className="gca-board">
          {Object.entries(digest.by_assignee).map(([name, tasks], index) => (
            <div className="gca-board-row" key={name}>
              <span className="gca-board-rank">{index + 1}</span>
              <span className="gca-avatar">{name.slice(0, 2).toUpperCase()}</span>
              <span className="gca-board-name">{name}</span>
              <span className="gca-board-xp">{tasks.length} tasks</span>
            </div>
          ))}
        </div>
      )}
    </div>
  </div>
);

const DaemonUploadsPanel = ({ uploads, onRefresh }) => (
  <div className="gca-panel">
    <div className="gca-panel-head">
      <div className="gca-panel-title"><Icon name="download" size={15}/>Daemon uploads</div>
      <span className="gca-panel-eyebrow">GET /api/meetings</span>
    </div>
    <div className="gca-panel-body">
      <button className="gc-btn gc-btn--secondary gc-btn--sm" onClick={onRefresh}>
        <Icon name="refresh" size={13}/>Refresh uploads
      </button>
      {uploads.length === 0 ? (
        <EmptyState icon="download" title="No daemon uploads yet" desc="Run smoke_upload_test.ps1 from the Windows package."/>
      ) : (
        <div className="gca-board">
          {uploads.slice(0, 8).map((item, index) => (
            <div className="gca-board-row" key={item.meeting_id || index}>
              <span className="gca-board-rank">{index + 1}</span>
              <span className="gca-avatar">DA</span>
              <span className="gca-board-name">{item.meeting_id}</span>
              <span className="gca-board-xp">{item.audio_count || 0} wav</span>
              <span className="gca-badge gca-badge--ok">{item.status || 'uploaded'}</span>
            </div>
          ))}
        </div>
      )}
      <div className="gca-inline-warning">
        Audio uploads are stored by brain-api. Real ASR and automatic task creation are not wired to this public upload path yet.
      </div>
    </div>
  </div>
);

const YouGilePanel = ({ status, onRefresh }) => (
  <div className="gca-panel">
    <div className="gca-panel-head">
      <div className="gca-panel-title"><Icon name="plug" size={15}/>YouGile</div>
      <span className="gca-panel-eyebrow">GET /api/integrations/yougile/status</span>
    </div>
    <div className="gca-panel-body">
      <button className="gc-btn gc-btn--secondary gc-btn--sm" onClick={onRefresh}><Icon name="refresh" size={13}/>Refresh</button>
      {!status ? (
        <EmptyState icon="plug" title="Status not loaded" desc="Backend did not return YouGile status yet."/>
      ) : (
        <>
          <div className="gca-status-grid">
            <div><span>Status</span><b>{status.status}</b></div>
            <div><span>Enabled</span><b>{String(status.enabled)}</b></div>
            <div><span>Configured</span><b>{String(status.configured)}</b></div>
            <div><span>Board</span><b>{status.board_id || 'none'}</b></div>
          </div>
          {status.reason && <div className="gca-inline-warning">{status.reason}</div>}
        </>
      )}
    </div>
  </div>
);

const ApiPanel = ({ config, setConfig, onSave, apiState }) => (
  <div className="gca-panel">
    <div className="gca-panel-head">
      <div className="gca-panel-title"><Icon name="server" size={15}/>Backend connection</div>
      <span className="gca-panel-eyebrow">{apiState.message}</span>
    </div>
    <div className="gca-panel-body">
      <div className="gca-api-config">
        <label>
          <span>Brain API base</span>
          <input className="gc-input" value={config.baseUrl} onChange={(e) => setConfig(prev => ({ ...prev, baseUrl:e.target.value }))}/>
        </label>
        <label>
          <span>Dev internal token</span>
          <input className="gc-input" value={config.internalToken} onChange={(e) => setConfig(prev => ({ ...prev, internalToken:e.target.value }))}/>
        </label>
        <button className="gc-btn gc-btn--primary" onClick={onSave}><Icon name="check" size={14}/>Save and refresh</button>
      </div>
      <div className="gca-inline-warning">The main demo flow does not send this token. Keep production secrets out of browser config.</div>
    </div>
  </div>
);

const AchievementBadge = ({ achievement, mode = 'tile' }) => (
  <div className={'gca-achievement gca-achievement--' + mode + ' gca-achievement--' + achievement.tone + (achievement.unlocked ? ' unlocked' : ' locked')}>
    <span className="gca-achievement-medal">
      <Icon name={achievement.icon} size={mode === 'mini' ? 17 : 22}/>
    </span>
    <div className="gca-achievement-copy">
      <div className="gca-achievement-title">{achievement.title}</div>
      {mode !== 'mini' && <div className="gca-achievement-desc">{achievement.desc}</div>}
      {mode !== 'mini' && <div className="gca-achievement-tier">{achievement.unlocked ? achievement.tier : 'Locked'}</div>}
    </div>
  </div>
);

const DaemonHearingPanel = ({ items, language }) => {
  const tr = (ru, en) => copyText(language, ru, en);
  return (
  <div className="gca-panel gca-hearing-panel">
    <div className="gca-panel-head">
      <div className="gca-panel-title"><Icon name="ear" size={15}/>{tr('Что услышал daemon', 'What daemon heard')}</div>
      <span className="gca-panel-eyebrow">{items.length} signals</span>
    </div>
    <div className="gca-panel-body">
      <div className="gca-hearing-list">
        {items.map((item) => (
          <div className="gca-hearing-row" key={item.id}>
            <div className="gca-hearing-meta">
              <span className="gca-hearing-time">{item.time}</span>
              <span className="gca-profile-avatar gca-profile-avatar--xxs">{item.speaker.slice(0, 1).toUpperCase()}</span>
            </div>
            <div className="gca-hearing-copy">
              <div className="gca-hearing-speaker">{item.speaker}</div>
              <div className="gca-hearing-text">{item.text}</div>
              <div className="gca-hearing-task">
                <span><Icon name="checkCircle" size={13}/>{tr('Подготовлена задача', 'Prepared task')}</span>
                <b>{item.preparedTask}</b>
              </div>
            </div>
            <div className="gca-hearing-side">
              <span className="gca-badge gca-badge--brand">{item.status}</span>
              <dl>
                <dt>{tr('Owner', 'Owner')}</dt><dd>{item.assignee}</dd>
                <dt>{tr('Due', 'Due')}</dt><dd>{item.due}</dd>
                <dt>Conf</dt><dd>{item.confidence}%</dd>
              </dl>
            </div>
          </div>
        ))}
      </div>
    </div>
  </div>
  );
};

const OrganizationSummaryCard = ({ organization, onOpen, language }) => {
  const tr = (ru, en) => copyText(language, ru, en);
  const memberCount = organization?.members?.length || 0;
  return (
    <div className="gca-panel gca-org-summary">
      <div className="gca-panel-head">
        <div className="gca-panel-title"><Icon name="users" size={15}/>{tr('Организация', 'Organization')}</div>
        <span className="gca-panel-eyebrow">{organization ? 'workspace' : tr('не вступил', 'not joined')}</span>
      </div>
      <div className="gca-panel-body">
        {organization ? (
          <div className="gca-org-summary-body">
            <OrganizationAvatar organization={organization} size="lg"/>
            <div className="gca-org-summary-copy">
              <b>{organization.name}</b>
              <span>{memberCount} {tr('участников', 'participants')}</span>
              <small>{organization.description}</small>
            </div>
            <button className="gc-btn gc-btn--secondary gc-btn--sm" onClick={onOpen}>
              {tr('Открыть', 'Open')}<Icon name="arrowR" size={13}/>
            </button>
          </div>
        ) : (
          <div className="gca-org-empty">
            <OrganizationAvatar organization={null} size="lg"/>
            <div className="gca-org-summary-copy">
              <b>{tr('Организации пока нет', 'No organization yet')}</b>
              <span>0 {tr('участников', 'participants')}</span>
              <small>{tr('Создайте организацию перед приглашением участников.', 'Create an organization before inviting participants.')}</small>
            </div>
            <button className="gc-btn gc-btn--primary gc-btn--sm" onClick={onOpen}>
              {tr('Создать', 'Create')}<Icon name="arrowR" size={13}/>
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

const ProfilePanel = ({
  profile,
  setProfile,
  achievements,
  onAchievementsOpen,
  onOrganizationOpen,
  organization,
  onPhotoUpload,
  onPhotoRemove,
  onSave,
  profileNotice,
  go,
  language,
}) => {
  const tr = (ru, en) => copyText(language, ru, en);
  const fileInputRef = React.useRef(null);
  const [profileView, setProfileView] = React.useState('home');
  const unlocked = achievements.filter((item) => item.unlocked);
  const completion = Math.round((unlocked.length / achievements.length) * 100);
  const updateProfile = (field, value) => setProfile(prev => ({ ...prev, [field]: value }));
  const openAchievements = () => onAchievementsOpen();
  const onAchievementKey = (event) => {
    if (event.key === 'Enter' || event.key === ' ') openAchievements();
  };
  const organizationName = organization?.name || tr('Без организации', 'No organization');

  return (
    <div className="gca-profile-page">
      <section className="gca-profile-hero-card">
        <div className="gca-profile-hero-main">
          <ProfileAvatar profile={profile} size="xl"/>
          <div className="gca-profile-identity">
            <span className="gca-panel-eyebrow">{tr('ПРОФИЛЬ УЧАСТНИКА', 'PARTICIPANT PROFILE')}</span>
            <h2>{profile.displayName || 'Grey Cardinal'}</h2>
            <p>{profile.bio || DEFAULT_PROFILE.bio}</p>
            <div className="gca-profile-meta">
              <span><Icon name="users" size={13}/>{organizationName}</span>
              <span><Icon name="target" size={13}/>{profile.role || tr('Роль', 'Role')}</span>
              <span><Icon name="user" size={13}/>@{profile.login || DEFAULT_PROFILE.login}</span>
            </div>
          </div>
        </div>
        <div className="gca-profile-photo-actions">
          <button
            className={'gc-btn gc-btn--sm ' + (profileView === 'home' ? 'gc-btn--primary' : 'gc-btn--secondary')}
            onClick={() => setProfileView('home')}
          >
            <Icon name="grid" size={13}/>Home
          </button>
          <button
            className={'gc-btn gc-btn--sm ' + (profileView === 'settings' ? 'gc-btn--primary' : 'gc-btn--secondary')}
            onClick={() => setProfileView('settings')}
          >
            <Icon name="settings" size={13}/>{tr('Настройки профиля', 'Profile settings')}
          </button>
          <button className="gc-btn gc-btn--secondary gc-btn--sm" onClick={() => go('/download')}>
            <Icon name="download" size={13}/>Daemon setup
          </button>
        </div>
      </section>

      {profileView === 'home' && (
        <div className="gca-profile-grid">
          <DaemonHearingPanel items={daemonHearingHistoryForLanguage(language)} language={language}/>

          <div className="gca-profile-side-stack">
            <OrganizationSummaryCard organization={organization} onOpen={onOrganizationOpen} language={language}/>

            <div
              className="gca-panel gca-achievements-preview"
              role="button"
              tabIndex={0}
              onClick={openAchievements}
              onKeyDown={onAchievementKey}
            >
              <div className="gca-panel-head">
                <div>
                  <div className="gca-achievements-label">{tr('Ачивки', 'Achievements')}</div>
                  <div className="gca-achievements-summary">{unlocked.length} {tr('из', 'of')} {achievements.length} {tr('открыто', 'unlocked')}</div>
                </div>
                <span className="gca-achievements-score">{completion}%</span>
              </div>
              <div className="gca-panel-body">
                <div className="gca-achievement-strip">
                  {achievements.slice(0, 6).map((achievement) => (
                    <AchievementBadge key={achievement.id} achievement={achievement} mode="mini"/>
                  ))}
                </div>
                <div className="gca-achievements-open">
                  <span>{tr('Открыть все ачивки', 'Open all achievements')}</span>
                  <Icon name="arrowR" size={14}/>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {profileView === 'settings' && (
        <div className="gca-panel gca-profile-settings-panel">
          <div className="gca-panel-head">
            <div className="gca-panel-title"><Icon name="settings" size={15}/>{tr('Настройки профиля', 'Profile settings')}</div>
            <span className="gca-panel-eyebrow">{profileNotice || 'LOCAL PROFILE'}</span>
          </div>
          <div className="gca-panel-body">
            <div className="gca-profile-photo-settings">
              <ProfileAvatar profile={profile} size="md"/>
              <div className="gca-profile-photo-copy">
                <b>{tr('Фото профиля', 'Profile photo')}</b>
                <span>{tr('Фото хранится локально в этом браузере, пока backend-хранилище профиля не подключено.', 'Photo is stored locally in this browser until backend profile storage is connected.')}</span>
              </div>
              <input
                ref={fileInputRef}
                className="gca-file-input"
                type="file"
                accept="image/*"
                onChange={onPhotoUpload}
              />
              <button className="gc-btn gc-btn--secondary gc-btn--sm" onClick={() => fileInputRef.current?.click()}>
                <Icon name="upload" size={14}/>{tr('Загрузить фото', 'Upload photo')}
              </button>
              <button className="gc-btn gc-btn--secondary gc-btn--sm" onClick={onPhotoRemove} disabled={!profile.photoDataUrl}>
                <Icon name="x" size={13}/>{tr('Удалить', 'Remove')}
              </button>
            </div>
            <div className="gca-profile-form">
              <label>
                <span>{tr('Отображаемое имя', 'Display name')}</span>
                <input className="gc-input" value={profile.displayName} onChange={(event) => updateProfile('displayName', event.target.value)}/>
              </label>
              <label>
                <span>{tr('Логин', 'Login')}</span>
                <input className="gc-input" value={profile.login} onChange={(event) => updateProfile('login', event.target.value)}/>
              </label>
              <label>
                <span>{tr('Роль', 'Role')}</span>
                <input className="gc-input" value={profile.role} onChange={(event) => updateProfile('role', event.target.value)}/>
              </label>
              <label>
                <span>{tr('Локация', 'Location')}</span>
                <input className="gc-input" value={profile.location} onChange={(event) => updateProfile('location', event.target.value)}/>
              </label>
              <label>
                <span>{tr('Статус', 'Status')}</span>
                <input className="gc-input" value={profile.status} onChange={(event) => updateProfile('status', event.target.value)}/>
              </label>
              <label className="gca-profile-form-wide">
                <span>Bio</span>
                <textarea
                  className="gc-input gca-profile-textarea"
                  rows={4}
                  value={profile.bio}
                  onChange={(event) => updateProfile('bio', event.target.value)}
                />
              </label>
            </div>
            <div className="gca-controls">
              <button className="gc-btn gc-btn--primary" onClick={onSave}><Icon name="check" size={14}/>{tr('Сохранить профиль', 'Save profile')}</button>
              <span className="gca-profile-save-note">{profileNotice || tr('Готово', 'Ready')}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

const OrganizationPanel = ({ organization, setOrganization, language }) => {
  const tr = (ru, en) => copyText(language, ru, en);
  const fileInputRef = React.useRef(null);
  const [inviteEmail, setInviteEmail] = React.useState('');
  const [notice, setNotice] = React.useState(tr('Готово', 'Ready'));

  const persistOrganization = (next) => {
    const normalized = normalizeOrganization(next);
    setOrganization(normalized);
    saveOrganization(normalized);
  };

  const createOrganization = () => {
    persistOrganization({ ...DEFAULT_ORGANIZATION });
    setNotice(tr('Организация создана', 'Organization created'));
  };

  const updateOrganization = (field, value) => {
    persistOrganization({ ...organization, [field]: value });
    setNotice(tr('Организация обновлена', 'Organization updated'));
  };

  const inviteUser = () => {
    const email = inviteEmail.trim();
    if (!email) {
      setNotice(tr('Введите email', 'Enter an email'));
      return;
    }
    const nextInvite = { id:String(Date.now()), email, status:'pending' };
    persistOrganization({
      ...organization,
      invites: [nextInvite, ...(organization.invites || [])].slice(0, 8),
    });
    setInviteEmail('');
    setNotice(tr('Инвайт подготовлен', 'Invite prepared'));
  };

  const uploadOrganizationPhoto = (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      setNotice(tr('Выберите файл изображения', 'Select an image file'));
      event.target.value = '';
      return;
    }
    if (file.size > 2.5 * 1024 * 1024) {
      setNotice(tr('Изображение должно быть меньше 2.5 MB', 'Image must be under 2.5 MB'));
      event.target.value = '';
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      persistOrganization({ ...organization, photoDataUrl: String(reader.result || '') });
      setNotice(tr('Фото организации загружено', 'Organization photo uploaded'));
    };
    reader.onerror = () => setNotice(tr('Загрузка фото не удалась', 'Photo upload failed'));
    reader.readAsDataURL(file);
    event.target.value = '';
  };

  const removeOrganizationPhoto = () => {
    persistOrganization({ ...organization, photoDataUrl: '' });
    setNotice(tr('Фото организации удалено', 'Organization photo removed'));
  };

  if (!organization) {
    return (
      <div className="gca-organization-page">
        <section className="gca-org-create">
          <OrganizationAvatar organization={null} size="xl"/>
          <div className="gca-org-create-copy">
            <span className="gca-panel-eyebrow">{tr('ОРГАНИЗАЦИЯ', 'ORGANIZATION')}</span>
            <h2>{tr('Создать организацию', 'Create organization')}</h2>
            <p>{tr('Вы пока не состоите в организации. Сейчас frontend-flow позволяет только создать одну локальную организацию.', 'You are not a member of an organization yet. For now this frontend flow only allows creating one local organization.')}</p>
          </div>
          <button className="gc-btn gc-btn--primary" onClick={createOrganization}>
            <Icon name="plus" size={15}/>{tr('Создать организацию', 'Create organization')}
          </button>
        </section>
      </div>
    );
  }

  const members = organization.members || [];
  const invites = organization.invites || [];

  return (
    <div className="gca-organization-page">
      <section className="gca-org-hero">
        <div className="gca-org-hero-main">
          <OrganizationAvatar organization={organization} size="xl"/>
          <div className="gca-org-hero-copy">
            <span className="gca-panel-eyebrow">{tr('ОРГАНИЗАЦИЯ', 'ORGANIZATION')}</span>
            <h2>{organization.name}</h2>
            <p>{organization.description}</p>
            <div className="gca-profile-meta">
              <span><Icon name="users" size={13}/>{members.length} {tr('участников', 'participants')}</span>
              <span><Icon name="link" size={13}/>@{organization.slug}</span>
              <span><Icon name="bell" size={13}/>{invites.length} {tr('ожидающих инвайтов', 'pending invites')}</span>
            </div>
          </div>
        </div>
        <span className="gca-panel-eyebrow">{notice}</span>
      </section>

      <div className="gca-org-grid">
        <div className="gca-panel">
          <div className="gca-panel-head">
            <div className="gca-panel-title"><Icon name="settings" size={15}/>{tr('Настройки организации', 'Organization settings')}</div>
            <span className="gca-panel-eyebrow">{tr('локальный черновик', 'local draft')}</span>
          </div>
          <div className="gca-panel-body">
            <div className="gca-profile-photo-settings">
              <OrganizationAvatar organization={organization} size="md"/>
              <div className="gca-profile-photo-copy">
                <b>{tr('Фото организации', 'Organization photo')}</b>
                <span>{tr('Показывается на Home профиля и странице организации.', 'Shown on profile Home and the organization page.')}</span>
              </div>
              <input
                ref={fileInputRef}
                className="gca-file-input"
                type="file"
                accept="image/*"
                onChange={uploadOrganizationPhoto}
              />
              <button className="gc-btn gc-btn--secondary gc-btn--sm" onClick={() => fileInputRef.current?.click()}>
                <Icon name="upload" size={14}/>{tr('Загрузить фото', 'Upload photo')}
              </button>
              <button className="gc-btn gc-btn--secondary gc-btn--sm" onClick={removeOrganizationPhoto} disabled={!organization.photoDataUrl}>
                <Icon name="x" size={13}/>{tr('Удалить', 'Remove')}
              </button>
            </div>
            <div className="gca-profile-form">
              <label>
                <span>{tr('Название организации', 'Organization name')}</span>
                <input className="gc-input" value={organization.name} onChange={(event) => updateOrganization('name', event.target.value)}/>
              </label>
              <label>
                <span>Slug</span>
                <input className="gc-input" value={organization.slug} onChange={(event) => updateOrganization('slug', event.target.value)}/>
              </label>
              <label className="gca-profile-form-wide">
                <span>{tr('Описание', 'Description')}</span>
                <textarea
                  className="gc-input gca-profile-textarea"
                  rows={4}
                  value={organization.description}
                  onChange={(event) => updateOrganization('description', event.target.value)}
                />
              </label>
            </div>
          </div>
        </div>

        <div className="gca-panel">
          <div className="gca-panel-head">
            <div className="gca-panel-title"><Icon name="send" size={15}/>{tr('Пригласить пользователей', 'Invite users')}</div>
            <span className="gca-panel-eyebrow">{invites.length} pending</span>
          </div>
          <div className="gca-panel-body">
            <div className="gca-org-invite">
              <input
                className="gc-input"
                value={inviteEmail}
                onChange={(event) => setInviteEmail(event.target.value)}
                placeholder="teammate@example.com"
              />
              <button className="gc-btn gc-btn--primary gc-btn--sm" onClick={inviteUser}>
                <Icon name="send" size={13}/>{tr('Пригласить', 'Invite')}
              </button>
            </div>
            <div className="gca-org-members">
              {members.map((member) => (
                <div className="gca-org-member-row" key={member.id}>
                  <span className="gca-profile-avatar gca-profile-avatar--xxs">{initialsFor(member.name)}</span>
                  <div>
                    <b>{member.name}</b>
                    <span>{member.role}</span>
                  </div>
                  <span className="gca-badge gca-badge--ok">{member.status}</span>
                </div>
              ))}
              {invites.map((invite) => (
                <div className="gca-org-member-row" key={invite.id}>
                  <span className="gca-profile-avatar gca-profile-avatar--xxs">?</span>
                  <div>
                    <b>{invite.email}</b>
                    <span>{tr('Приглашение', 'Invitation')}</span>
                  </div>
                  <span className="gca-badge gca-badge--med">{invite.status}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

const AchievementsPanel = ({ profile, achievements, setSection, language }) => {
  const tr = (ru, en) => copyText(language, ru, en);
  const unlocked = achievements.filter((item) => item.unlocked);
  return (
    <div className="gca-achievements-page">
      <section className="gca-achievements-hero">
        <div className="gca-achievements-hero-copy">
          <span className="gca-panel-eyebrow">{tr('ПРОФИЛЬ УЧАСТНИКА', 'PARTICIPANT PROFILE')}</span>
          <h2>{tr('Ачивки', 'Achievements')}</h2>
          <p>{profile.displayName || 'Grey Cardinal'} {tr('имеет открытых ачивок', 'has unlocked achievements')}: {unlocked.length}.</p>
        </div>
        <div className="gca-achievements-hero-side">
          <ProfileAvatar profile={profile} size="md"/>
          <div>
            <b>@{profile.login || DEFAULT_PROFILE.login}</b>
            <span>{profile.role || 'Product operator'}</span>
          </div>
          <button className="gc-btn gc-btn--secondary gc-btn--sm" onClick={() => setSection('profile')}>
            <Icon name="user" size={13}/>{tr('Профиль', 'Profile')}
          </button>
        </div>
      </section>
      <div className="gca-achievements-grid">
        {achievements.map((achievement) => (
          <AchievementBadge key={achievement.id} achievement={achievement}/>
        ))}
      </div>
    </div>
  );
};

const AppDashboardPage = ({ go, language, setLanguage }) => {
  const tr = (ru, en) => copyText(language, ru, en);
  const [section, setSection] = React.useState('overview');
  const [profile, setProfile] = React.useState(loadProfile);
  const [organization, setOrganization] = React.useState(loadOrganization);
  const [profileNotice, setProfileNotice] = React.useState('Ready');
  const [config, setConfig] = React.useState(() => {
    const saved = GCApi.config();
    return { baseUrl: saved.baseUrl, internalToken: saved.internalToken };
  });
  const [apiState, setApiState] = React.useState({ status:'checking', message:'checking' });
  const [refreshing, setRefreshing] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [chatText, setChatText] = React.useState('Нужно проверить Docker smoke до пятницы, ответственный Иван');
  const [author, setAuthor] = React.useState('Денис');
  const [chatResult, setChatResult] = React.useState('');
  const [proposals, setProposals] = React.useState([]);
  const [columns, setColumns] = React.useState([]);
  const [digest, setDigest] = React.useState(null);
  const [ygStatus, setYgStatus] = React.useState(null);
  const [daemonUploads, setDaemonUploads] = React.useState([]);
  const [signals, setSignals] = React.useState([]);

  const taskCount = React.useMemo(
    () => columns.reduce((sum, col) => sum + (col.tasks || []).length, 0),
    [columns],
  );
  const doneCount = React.useMemo(
    () => (columns.find((col) => col.id === 'done')?.tasks || []).length,
    [columns],
  );
  const achievements = React.useMemo(() => buildAchievements({
    profile,
    apiState,
    proposals,
    taskCount,
    doneCount,
    daemonUploads,
    language,
  }), [profile, apiState.status, proposals.length, taskCount, doneCount, daemonUploads.length, language]);
  const unlockedAchievementCount = React.useMemo(
    () => achievements.filter((item) => item.unlocked).length,
    [achievements],
  );
  const counts = React.useMemo(() => ({
    proposals: proposals.length,
    tasks: taskCount,
    daemonUploads: daemonUploads.length,
    achievements: unlockedAchievementCount,
    organization: organization ? (organization.members || []).length : null,
  }), [proposals.length, taskCount, daemonUploads.length, unlockedAchievementCount, organization]);
  const metrics = React.useMemo(() => [
    { label:tr('Pending', 'Pending'), value:String(proposals.length) },
    { label:tr('Tasks', 'Tasks'), value:String(taskCount) },
    { label:tr('Uploads', 'Uploads'), value:String(daemonUploads.length) },
    { label:tr('Done', 'Done'), value:String(doneCount) },
  ], [proposals.length, taskCount, daemonUploads.length, doneCount, language]);

  const loadDashboard = React.useCallback(async () => {
    setRefreshing(true);
    setApiState({ status:'checking', message:'checking' });
    GCApi.saveConfig(config);
    try {
      await GCApi.health();
      const [proposalRes, boardRes, digestRes, ygRes, daemonRes] = await Promise.allSettled([
        GCApi.getProposals('pending'),
        GCApi.getBoard(),
        GCApi.getEveningDigest(),
        GCApi.getYouGileStatus(),
        GCApi.daemonUploads(),
      ]);
      if (proposalRes.status === 'fulfilled') setProposals(proposalRes.value);
      if (boardRes.status === 'fulfilled') setColumns(boardRes.value);
      if (digestRes.status === 'fulfilled') setDigest(digestRes.value);
      if (ygRes.status === 'fulfilled') setYgStatus(ygRes.value);
      if (daemonRes.status === 'fulfilled') setDaemonUploads(daemonRes.value);
      setSignals(prev => [{
        id:String(Date.now()),
        kind:'create',
        icon:'checkCircle',
        title:'Backend refreshed',
        desc:'Proposals, board, digest, and YouGile status were loaded from brain-api.',
        time:'now',
      }, ...prev].slice(0, 6));
      setApiState({ status:'online', message:'brain-api online' });
    } catch (error) {
      setApiState({ status:'offline', message:error.message || String(error) });
      setSignals(prev => [{
        id:String(Date.now()),
        kind:'risk',
        icon:'alert',
        title:'Backend unavailable',
        desc:error.message || String(error),
        time:'now',
      }, ...prev].slice(0, 6));
    } finally {
      setRefreshing(false);
    }
  }, [config]);

  React.useEffect(() => { loadDashboard(); }, []);

  React.useEffect(() => {
    if (apiState.status !== 'online') return;
    let ws;
    try {
      ws = new WebSocket(GCApi.wsUrl());
      ws.onmessage = (event) => {
        const message = JSON.parse(event.data);
        if (message.event === 'connected') return;
        if (['task_created', 'task_proposed', 'task_status_changed', 'task_rejected'].includes(message.event)) {
          loadDashboard();
        }
        setSignals(prev => [{
          id:String(Date.now()),
          kind:'remind',
          icon:'bell',
          title:message.event || 'websocket event',
          desc:JSON.stringify(message.payload || {}),
          time:'ws',
        }, ...prev].slice(0, 6));
      };
    } catch (_) {
      return;
    }
    return () => { if (ws) ws.close(); };
  }, [apiState.status, loadDashboard]);

  const sendMessage = async () => {
    setBusy(true);
    setChatResult('');
    try {
      const result = await GCApi.sendChatMessage(chatText, author);
      if (result.duplicate) {
        setChatResult(`Duplicate proposal: ${result.existing_proposal_id || 'already known'}`);
      } else if (result.has_task && result.proposal) {
        setChatResult(`Proposal created: ${result.proposal.title}`);
      } else {
        setChatResult('No task detected in this message.');
      }
      await loadDashboard();
    } catch (error) {
      setChatResult(error.message || String(error));
    } finally {
      setBusy(false);
    }
  };

  const confirmProposal = async (proposalId) => {
    setBusy(true);
    try {
      await GCApi.confirmProposal(proposalId);
      await loadDashboard();
    } finally {
      setBusy(false);
    }
  };

  const rejectProposal = async (proposalId) => {
    setBusy(true);
    try {
      await GCApi.rejectProposal(proposalId);
      await loadDashboard();
    } finally {
      setBusy(false);
    }
  };

  const moveTask = async (taskId, status) => {
    setBusy(true);
    try {
      await GCApi.moveTask(taskId, status);
      await loadDashboard();
    } finally {
      setBusy(false);
    }
  };

  const syncTask = async (taskId) => {
    setBusy(true);
    try {
      await GCApi.syncTaskYouGile(taskId);
      await loadDashboard();
    } finally {
      setBusy(false);
    }
  };

  const saveCurrentProfile = () => {
    saveProfile(normalizeProfile(profile));
    setProfileNotice(tr('Профиль сохранен', 'Profile saved'));
  };

  const uploadProfilePhoto = (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      setProfileNotice(tr('Выберите файл изображения', 'Select an image file'));
      event.target.value = '';
      return;
    }
    if (file.size > 2.5 * 1024 * 1024) {
      setProfileNotice(tr('Изображение должно быть меньше 2.5 MB', 'Image must be under 2.5 MB'));
      event.target.value = '';
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const next = normalizeProfile({ ...profile, photoDataUrl: String(reader.result || '') });
      setProfile(next);
      saveProfile(next);
      setProfileNotice(tr('Фото загружено', 'Photo uploaded'));
    };
    reader.onerror = () => setProfileNotice(tr('Загрузка фото не удалась', 'Photo upload failed'));
    reader.readAsDataURL(file);
    event.target.value = '';
  };

  const removeProfilePhoto = () => {
    const next = normalizeProfile({ ...profile, photoDataUrl: '' });
    setProfile(next);
    saveProfile(next);
    setProfileNotice(tr('Фото удалено', 'Photo removed'));
  };

  return (
    <div className="gca-shell">
      <Sidebar go={go} counts={counts} section={section} setSection={setSection} profile={profile} language={language}/>
      <main className="gca-main">
        <Topbar apiState={apiState} onRefresh={loadDashboard} refreshing={refreshing} profile={profile} setSection={setSection} language={language} setLanguage={setLanguage}/>
        <div className="gca-content">
          {!['profile', 'organization', 'achievements'].includes(section) && (
            <div className="gca-page-head">
              <CockpitHero apiState={apiState} metrics={metrics} ygStatus={ygStatus} language={language}/>
            </div>
          )}

          {(section === 'overview' || section === 'proposals') && (
            <div className="gca-theater">
              <ChatPanel
                text={chatText}
                setText={setChatText}
                author={author}
                setAuthor={setAuthor}
                onSend={sendMessage}
                busy={busy}
                result={chatResult}
              />
              <ProposalsPanel proposals={proposals} onConfirm={confirmProposal} onReject={rejectProposal} busy={busy}/>
            </div>
          )}

          {(section === 'overview' || section === 'kanban') && (
            <BoardPanel columns={columns} onMove={moveTask} onSync={syncTask} busy={busy}/>
          )}

          {(section === 'overview' || section === 'digest') && (
            <DigestPanel digest={digest} onRefresh={loadDashboard}/>
          )}

          {(section === 'overview' || section === 'daemon') && (
            <DaemonUploadsPanel uploads={daemonUploads} onRefresh={loadDashboard}/>
          )}

          {(section === 'overview' || section === 'yougile') && (
            <YouGilePanel status={ygStatus} onRefresh={loadDashboard}/>
          )}

          {section === 'api' && (
            <ApiPanel config={config} setConfig={setConfig} onSave={loadDashboard} apiState={apiState}/>
          )}

          {section === 'profile' && (
            <ProfilePanel
              profile={profile}
              setProfile={setProfile}
              achievements={achievements}
              onAchievementsOpen={() => setSection('achievements')}
              onOrganizationOpen={() => setSection('organization')}
              organization={organization}
              onPhotoUpload={uploadProfilePhoto}
              onPhotoRemove={removeProfilePhoto}
              onSave={saveCurrentProfile}
              profileNotice={profileNotice}
              go={go}
              language={language}
            />
          )}

          {section === 'achievements' && (
            <AchievementsPanel profile={profile} achievements={achievements} setSection={setSection} language={language}/>
          )}

          {section === 'organization' && (
            <OrganizationPanel organization={organization} setOrganization={setOrganization} language={language}/>
          )}

          {signals.length > 0 && !['profile', 'organization', 'achievements'].includes(section) && (
            <div className="gca-panel">
              <div className="gca-panel-head">
                <div className="gca-panel-title"><Icon name="zap" size={15}/>{tr('Живые сигналы', 'Live signals')}</div>
                <span className="gca-panel-eyebrow">{signals.length} {tr('событий', 'events')}</span>
              </div>
              <div className="gca-panel-body">
                {signals.map((s) => (
                  <div className={'gca-signal ' + s.kind} key={s.id}>
                    <div className="gca-signal-ic"><Icon name={s.icon} size={16}/></div>
                    <div>
                      <div className="gca-signal-title">{s.title}</div>
                      <div className="gca-signal-desc">{s.desc}</div>
                    </div>
                    <span className="gca-signal-time">{s.time}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
};

Object.assign(window, { AppDashboardPage });

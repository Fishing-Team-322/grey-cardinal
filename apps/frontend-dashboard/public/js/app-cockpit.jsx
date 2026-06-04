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

const EmptyState = ({ icon = 'grid', title, desc }) => (
  <div className="gca-empty">
    <span className="gca-empty-ic"><Icon name={icon} size={18}/></span>
    <div>
      <div className="gca-empty-title">{title}</div>
      {desc && <div className="gca-empty-desc">{desc}</div>}
    </div>
  </div>
);

const Sidebar = ({ go, counts, section, setSection }) => {
  const nav = [
    { sec:'WORK', items:[
      { id:'overview', icon:'grid', label:'Overview' },
      { id:'proposals', icon:'list', label:'Proposals', count: counts.proposals },
      { id:'kanban', icon:'kanban', label:'Board', count: counts.tasks },
      { id:'digest', icon:'bell', label:'Digest' },
    ]},
    { sec:'INTEGRATIONS', items:[
      { id:'yougile', icon:'plug', label:'YouGile' },
      { id:'api', icon:'server', label:'Brain API' },
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
        <div className="gca-avatar">GC</div>
        <div style={{ lineHeight:1.3 }}>
          <div style={{ fontSize:12, color:'var(--rf-fg-1)' }}>Grey Cardinal</div>
          <div style={{ fontSize:10, color:'var(--rf-fg-4)', fontFamily:'var(--rf-font-mono)' }}>public demo flow</div>
        </div>
        <span style={{ marginLeft:'auto', color:'var(--rf-fg-4)', cursor:'pointer' }} onClick={() => go('/')}><Icon name="x" size={15}/></span>
      </div>
    </aside>
  );
};

const Topbar = ({ apiState, onRefresh, refreshing }) => (
  <header className="gca-topbar">
    <div className="gca-ws">
      <span className="label">Backend</span>
      <span className="gca-api-url">{GCApi.config().baseUrl}</span>
    </div>
    <span className={'gca-chip gca-chip--' + apiState.status}>
      <span className={'dot ' + (apiState.status === 'online' ? 'ok' : apiState.status === 'checking' ? 'live' : '')}></span>
      {apiState.status === 'online' ? 'Brain online' : apiState.status === 'checking' ? 'Checking' : 'Offline'}
    </span>
    <div className="gca-topbar-spacer"></div>
    <button className="gc-btn gc-btn--secondary gc-btn--sm" onClick={onRefresh} disabled={refreshing}>
      <Icon name="refresh" size={14}/>{refreshing ? 'Refreshing...' : 'Refresh'}
    </button>
  </header>
);

const CockpitHero = ({ apiState, metrics, ygStatus }) => (
  <section className={'gca-hero-panel gca-hero-panel--' + apiState.status}>
    <div className="gca-hero-copy">
      <span className="gca-panel-eyebrow">BRAIN API / LIVE DEMO</span>
      <h1>Cockpit</h1>
      <p>Send a message, review the extracted proposal, confirm it into the board, and sync it to YouGile.</p>
      <div className="gca-source-strip">
        <span className="gca-source-chip"><b>API</b><small>{apiState.message}</small></span>
        <span className="gca-source-chip"><b>WebSocket</b><small>/ws/events</small></span>
        <span className="gca-source-chip"><b>YouGile</b><small>{ygStatus?.status || 'unknown'}</small></span>
        <span className="gca-source-chip"><b>Token</b><small>not used by demo flow</small></span>
      </div>
    </div>
    <div className="gca-hero-side">
      <div className="gca-hero-status">
        <span className={'gca-hero-status-dot ' + apiState.status}></span>
        <div>
          <b>{apiState.status === 'online' ? 'Connected' : apiState.status === 'checking' ? 'Checking backend' : 'Backend unavailable'}</b>
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

const AppDashboardPage = ({ go }) => {
  const [section, setSection] = React.useState('overview');
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
  const [signals, setSignals] = React.useState([]);

  const taskCount = React.useMemo(
    () => columns.reduce((sum, col) => sum + (col.tasks || []).length, 0),
    [columns],
  );
  const counts = React.useMemo(() => ({
    proposals: proposals.length,
    tasks: taskCount,
  }), [proposals.length, taskCount]);
  const metrics = React.useMemo(() => [
    { label:'Pending', value:String(proposals.length) },
    { label:'Tasks', value:String(taskCount) },
    { label:'Done', value:String((columns.find((col) => col.id === 'done')?.tasks || []).length) },
    { label:'YouGile', value:ygStatus?.status || 'unknown' },
  ], [proposals.length, taskCount, columns, ygStatus]);

  const loadDashboard = React.useCallback(async () => {
    setRefreshing(true);
    setApiState({ status:'checking', message:'checking' });
    GCApi.saveConfig(config);
    try {
      await GCApi.health();
      const [proposalRes, boardRes, digestRes, ygRes] = await Promise.allSettled([
        GCApi.getProposals('pending'),
        GCApi.getBoard(),
        GCApi.getEveningDigest(),
        GCApi.getYouGileStatus(),
      ]);
      if (proposalRes.status === 'fulfilled') setProposals(proposalRes.value);
      if (boardRes.status === 'fulfilled') setColumns(boardRes.value);
      if (digestRes.status === 'fulfilled') setDigest(digestRes.value);
      if (ygRes.status === 'fulfilled') setYgStatus(ygRes.value);
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

  return (
    <div className="gca-shell">
      <Sidebar go={go} counts={counts} section={section} setSection={setSection}/>
      <main className="gca-main">
        <Topbar apiState={apiState} onRefresh={loadDashboard} refreshing={refreshing}/>
        <div className="gca-content">
          <div className="gca-page-head">
            <CockpitHero apiState={apiState} metrics={metrics} ygStatus={ygStatus}/>
          </div>

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

          {(section === 'overview' || section === 'yougile') && (
            <YouGilePanel status={ygStatus} onRefresh={loadDashboard}/>
          )}

          {section === 'api' && (
            <ApiPanel config={config} setConfig={setConfig} onSave={loadDashboard} apiState={apiState}/>
          )}

          {signals.length > 0 && (
            <div className="gca-panel">
              <div className="gca-panel-head">
                <div className="gca-panel-title"><Icon name="zap" size={15}/>Live signals</div>
                <span className="gca-panel-eyebrow">{signals.length} events</span>
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

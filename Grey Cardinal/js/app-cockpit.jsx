// Grey Cardinal — /app cockpit (dashboard for existing clients)

const prioClass = (p) => p==='High'?'high':p==='Medium'?'med':'low';

const TranscriptLine = ({ t }) => (
  <div className={'gca-tline' + (t.fresh ? ' fresh' : '')}>
    <div className="gca-tline-av" style={{ color: t.color, borderColor: t.color+'55' }}>{t.init}</div>
    <div className="gca-tline-body">
      <div className="gca-tline-meta">
        <span className="gca-tline-name">{t.name}</span>
        <span className="gca-tline-time">{t.time}</span>
        <span className={'gca-tline-status ' + (t.status==='final'?'final':'proc')}>{t.status==='final'?'final':'processing'}</span>
      </div>
      <div className="gca-tline-text">{t.text}</div>
    </div>
  </div>
);

const TaskCard = ({ t }) => (
  <div className={'gca-task' + (t.fresh ? ' fresh' : '')}>
    <div className="gca-task-top">
      <span className="gca-task-title">{t.title}</span>
      <span className={'gca-badge gca-badge--' + prioClass(t.prio)}>{t.prio}</span>
    </div>
    <dl className="gca-task-meta">
      <dt>Исполнитель</dt><dd>{t.who}</dd>
      <dt>Дедлайн</dt><dd>{t.due}</dd>
      <dt>Источник</dt><dd>{t.source}</dd>
    </dl>
    <div className="gca-conf">
      <div className="gca-conf-bar"><span style={{ width: t.conf+'%' }}/></div>
      <span className="gca-conf-val">{t.conf}%</span>
    </div>
    <div className="gca-task-foot">
      {t.voice && <span className="gca-badge gca-badge--brand"><Icon name="ear" size={11}/>назначено по голосу</span>}
      {t.fresh && <span className="gca-badge gca-badge--ok">только что</span>}
    </div>
  </div>
);

const Sidebar = ({ go }) => (
  <aside className="gca-sidebar">
    <div className="gca-side-logo"><Logo size={28} sub="COCKPIT"/></div>
    <nav className="gca-nav">
      {GC_NAV.map(group => (
        <div key={group.sec}>
          <div className="gca-nav-sec">{group.sec}</div>
          {group.items.map(it => (
            <div key={it.id} className={'gca-nav-item' + (it.id==='overview'?' active':'')}>
              <Icon name={it.icon} size={16}/>
              <span>{it.label}</span>
              {it.count != null && <span className="count">{it.count}</span>}
            </div>
          ))}
        </div>
      ))}
    </nav>
    <div className="gca-side-foot">
      <div className="gca-avatar">ПС</div>
      <div style={{ lineHeight:1.3 }}>
        <div style={{ fontSize:12, color:'var(--rf-fg-1)' }}>Пётр Смирнов</div>
        <div style={{ fontSize:10, color:'var(--rf-fg-4)', fontFamily:'var(--rf-font-mono)' }}>owner · Hackathon Team</div>
      </div>
      <span style={{ marginLeft:'auto', color:'var(--rf-fg-4)', cursor:'pointer' }} onClick={() => go('/')}><Icon name="x" size={15}/></span>
    </div>
  </aside>
);

const Topbar = ({ onPlay, playing }) => (
  <header className="gca-topbar">
    <div className="gca-ws">
      <span className="label">Workspace</span>
      <span style={{ fontWeight:600, color:'var(--rf-fg-0)' }}>Hackathon Team</span>
    </div>
    <span className="gca-chip"><span className="dot live"></span>Live meeting</span>
    <span className="gca-chip"><span className="dot ok"></span>Daemon online</span>
    <div className="gca-topbar-spacer"></div>
    <button className="gc-btn gc-btn--primary gc-btn--sm" onClick={onPlay}>
      <Icon name={playing?'refresh':'play'} size={14}/>{playing?'Сценарий идёт…':'Запустить сценарий'}
    </button>
  </header>
);

const Signal = ({ s }) => (
  <div className={'gca-signal ' + s.kind}>
    <div className="gca-signal-ic"><Icon name={s.icon} size={16}/></div>
    <div>
      <div className="gca-signal-title">{s.title}</div>
      <div className="gca-signal-desc">{s.desc}</div>
    </div>
    <span className="gca-signal-time">{s.time}</span>
  </div>
);

const AppDashboardPage = ({ go }) => {
  const [transcript, setTranscript] = React.useState(() => GC_TRANSCRIPT.map(t => ({...t})));
  const [tasks, setTasks] = React.useState(() => GC_TASKS.map((t,i) => ({...t, fresh: i===0})));
  const [signals, setSignals] = React.useState(() => GC_SIGNALS.map(s => ({...s})));
  const [playing, setPlaying] = React.useState(false);
  const queueRef = React.useRef([]);

  const reset = () => {
    setTranscript(GC_TRANSCRIPT.map(t => ({...t})));
    setTasks(GC_TASKS.map((t,i) => ({...t, fresh: i===0})));
    setSignals(GC_SIGNALS.map(s => ({...s})));
    setPlaying(false);
  };

  const addLine = () => {
    const pool = GC_TRANSCRIPT_EXTRA;
    setTranscript(prev => {
      const next = prev.map(t => ({...t, fresh:false}));
      const cand = pool.find(p => !prev.some(x => x.id===p.id));
      if (cand) next.push({...cand, fresh:true});
      return next;
    });
  };

  const createTask = () => {
    setTasks(prev => {
      const cand = GC_TASKS_EXTRA.find(p => !prev.some(x => x.id===p.id));
      if (!cand) return prev.map(t => ({...t, fresh:false}));
      return [{...cand, fresh:true}, ...prev.map(t => ({...t, fresh:false}))];
    });
  };

  const triggerRisk = () => {
    const id = 'r' + Date.now();
    setSignals(prev => [{ id, kind:'risk', icon:'alert', title:'Риск обнаружен',
      desc:'Задача «Поднять websocket» приближается к дедлайну и всё ещё в работе.', time:'только что' }, ...prev]);
  };

  const playScenario = () => {
    if (playing) return;
    reset();
    setPlaying(true);
    const steps = [
      () => addLine(),
      () => createTask(),
      () => addLine(),
      () => createTask(),
      () => triggerRisk(),
      () => setPlaying(false),
    ];
    steps.forEach((fn, i) => setTimeout(fn, 700 * (i + 1)));
  };

  const metrics = [
    { label:'Всего задач', value:'12' },
    { label:'Закрыто', value:'5' },
    { label:'В риске', value:'2' },
    { label:'Уверенность', value:'86', unit:'%' },
  ];

  return (
    <div className="gca-shell">
      <Sidebar go={go}/>
      <main className="gca-main">
        <Topbar onPlay={playScenario} playing={playing}/>
        <div className="gca-content">

          <div className="gca-page-head">
            <div>
              <div className="gca-panel-eyebrow" style={{ marginBottom: 8 }}>HACKATHON TEAM · ОБЗОР</div>
              <h1 style={{ fontSize: 26, fontWeight: 600, color:'var(--rf-fg-0)', letterSpacing:'-0.02em', margin:0 }}>Cockpit</h1>
            </div>
            <span className="gc-mute" style={{ fontSize:12, fontFamily:'var(--rf-font-mono)' }}>обновлено · только что</span>
          </div>

          {/* DEMO THEATER */}
          <div className="gca-theater">
            <div className="gca-panel">
              <div className="gca-panel-head">
                <div className="gca-panel-title"><Icon name="ear" size={15}/>Что агент услышал</div>
                <span className="gca-panel-eyebrow">transcript · live</span>
              </div>
              <div className="gca-panel-body">
                {transcript.map(t => <TranscriptLine t={t} key={t.id}/>)}
              </div>
            </div>
            <div className="gca-panel">
              <div className="gca-panel-head">
                <div className="gca-panel-title"><Icon name="brain" size={15}/>Что агент понял</div>
                <span className="gca-panel-eyebrow">{tasks.length} задач</span>
              </div>
              <div className="gca-panel-body">
                {tasks.map(t => <TaskCard t={t} key={t.id}/>)}
              </div>
            </div>
          </div>

          {/* DEMO CONTROLS */}
          <div className="gca-panel">
            <div className="gca-panel-head">
              <div className="gca-panel-title"><Icon name="play" size={15}/>Demo controls</div>
              <span className="gca-panel-eyebrow">локальный сценарий</span>
            </div>
            <div className="gca-panel-body">
              <div className="gca-controls">
                <button className="gc-btn gc-btn--primary gc-btn--sm" onClick={playScenario}><Icon name="play" size={13}/>Play scenario</button>
                <button className="gc-btn gc-btn--secondary gc-btn--sm" onClick={addLine}><Icon name="plus" size={13}/>Add transcript line</button>
                <button className="gc-btn gc-btn--secondary gc-btn--sm" onClick={createTask}><Icon name="check" size={13}/>Create task</button>
                <button className="gc-btn gc-btn--secondary gc-btn--sm" onClick={triggerRisk}><Icon name="alert" size={13}/>Trigger risk</button>
                <button className="gc-btn gc-btn--ghost gc-btn--sm" onClick={reset}><Icon name="refresh" size={13}/>Reset</button>
              </div>
            </div>
          </div>

          {/* KANBAN */}
          <div className="gca-panel">
            <div className="gca-panel-head">
              <div className="gca-panel-title"><Icon name="kanban" size={15}/>Живой канбан</div>
              <span className="gca-panel-eyebrow">зеркало проекта</span>
            </div>
            <div className="gca-panel-body">
              <div className="gca-kanban">
                {Object.entries(GC_KANBAN).map(([col, cards]) => (
                  <div className="gca-kcol" key={col}>
                    <div className="gca-kcol-head">
                      <span className="gca-kcol-title">{col}</span>
                      <span className="gca-kcol-count">{cards.length}</span>
                    </div>
                    {cards.map(c => (
                      <div className={'gca-kcard' + (c.risk?' risk':'')} key={c.id}>
                        <div className="gca-kcard-title">{c.title}</div>
                        <div className="gca-kcard-foot">
                          <span className="gca-kcard-assignee">
                            <span className="gca-kdot" style={{ background:c.color+'33', color:c.color }}>{c.who[0]}</span>{c.who}
                          </span>
                          {c.risk && <span className="gca-badge gca-badge--high">риск</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* SIGNALS + TEAM PULSE */}
          <div className="gca-grid-2">
            <div className="gca-panel">
              <div className="gca-panel-head">
                <div className="gca-panel-title"><Icon name="zap" size={15}/>Автономные действия агента</div>
                <span className="gca-panel-eyebrow">{signals.length} сигналов</span>
              </div>
              <div className="gca-panel-body">
                {signals.map(s => <Signal s={s} key={s.id}/>)}
              </div>
            </div>

            <div style={{ display:'flex', flexDirection:'column', gap:16 }}>
              <div className="gca-metrics">
                {metrics.map(m => (
                  <div className="gca-metric" key={m.label}>
                    <span className="gca-metric-label">{m.label}</span>
                    <span className="gca-metric-value">{m.value}{m.unit && <span className="unit">{m.unit}</span>}</span>
                  </div>
                ))}
              </div>
              <div className="gca-panel">
                <div className="gca-panel-head">
                  <div className="gca-panel-title"><Icon name="users" size={15}/>Командный пульс</div>
                  <span className="gca-panel-eyebrow">активность</span>
                </div>
                <div className="gca-panel-body">
                  <div className="gca-board">
                    {GC_TEAM.map(p => (
                      <div className="gca-board-row" key={p.name}>
                        <span className="gca-board-rank">{p.rank}</span>
                        <span className="gca-board-name" style={{ gridColumn:'2 / 4' }}>{p.name}</span>
                        <span className="gca-board-xp">{p.xp} XP</span>
                        <div className="gca-board-bar"><span style={{ width: p.pct+'%' }}/></div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>

        </div>
      </main>
    </div>
  );
};

Object.assign(window, { AppDashboardPage });

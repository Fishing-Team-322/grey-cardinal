// Grey Cardinal - public header + magnifier hero

const PublicHeader = ({ go }) => {
  const [scrolled, setScrolled] = React.useState(false);
  React.useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);
  const nav = [
    ['Возможности', 'features'],
    ['Как работает', 'how'],
    ['Daemon', 'daemon'],
    ['Безопасность', 'security'],
  ];
  const jump = (id) => {
    const el = document.getElementById(id);
    if (el) window.scrollTo({ top: el.offsetTop - 70, behavior: 'smooth' });
  };
  return (
    <header className={'gc-header' + (scrolled ? ' scrolled' : '')}>
      <div className="gc-header-inner">
        <Logo onClick={() => go('/')} />
        <nav className="gc-nav">
          {nav.map(([label, id]) => (
            <span key={id} className="gc-nav-link" onClick={() => jump(id)}>{label}</span>
          ))}
        </nav>
        <div className="gc-header-actions">
          <button className="gc-btn gc-btn--ghost gc-btn--sm" onClick={() => go('/login')}>Войти</button>
          <button className="gc-btn gc-btn--primary gc-btn--sm" onClick={() => go('/register')}>Desktop identity</button>
        </div>
      </div>
    </header>
  );
};

const RAW_LINES = [
  ['Петя', 'Давайте оплату подготовим к четвергу.'],
  ['Аня', 'Я проверю интеграцию с YouGile сегодня вечером.'],
  ['Дима', 'Мне нужно до завтра поднять websocket для dashboard.'],
  ['Петя', 'Если оплата зависнет в Todo до среды - это риск.'],
  ['Аня', 'Вечерний дайджест соберем в пятницу.'],
  ['Дима', 'И проверить daemon на Windows перед демо.'],
];

const HERO_SIGNALS = [
  ['TASK', '3 задачи найдены', 'из последней встречи'],
  ['RISK', '1 дедлайн близко', 'нужен статус до среды'],
  ['SYNC', 'канбан обновлен', 'без ручного переноса'],
];

const useBrainApiStatus = () => {
  const [state, setState] = React.useState(() => ({
    status: 'checking',
    label: 'Проверяем backend',
    details: GCApi.config().baseUrl,
    latency: null,
  }));

  React.useEffect(() => {
    let alive = true;
    let timer;
    const check = async () => {
      const started = performance.now();
      setState((prev) => ({ ...prev, status: 'checking', label: 'Проверяем backend' }));
      try {
        await GCApi.health();
        const latency = Math.max(1, Math.round(performance.now() - started));
        if (!alive) return;
        setState({
          status: 'online',
          label: 'Brain API отвечает',
          details: `${GCApi.config().baseUrl} / ${latency} ms`,
          latency,
        });
      } catch (error) {
        if (!alive) return;
        setState({
          status: 'offline',
          label: 'Backend пока не запущен',
          details: error.message,
          latency: null,
        });
      }
    };
    check();
    timer = window.setInterval(check, 15000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);

  return state;
};

const BackendPulse = ({ go }) => {
  const api = useBrainApiStatus();
  const config = GCApi.config();
  const tokenState = config.internalToken ? 'token ready' : 'token missing';

  return (
    <div className={'gc-api-ribbon gc-api-ribbon--' + api.status}>
      <div className="gc-api-ribbon-main">
        <span className="gc-api-ribbon-ic">
          <Icon name={api.status === 'online' ? 'checkCircle' : api.status === 'checking' ? 'refresh' : 'alert'} size={18}/>
        </span>
        <div className="gc-api-ribbon-copy">
          <span className="gc-api-ribbon-k">Live backend check</span>
          <strong>{api.label}</strong>
          <small>{api.details}</small>
        </div>
      </div>
      <div className="gc-api-ribbon-chips">
        <span><span className={'gc-api-dot ' + api.status}></span>Brain API</span>
        <span><Icon name="lock" size={12}/>{tokenState}</span>
        <span><Icon name="server" size={12}/>CORS enabled</span>
        <button type="button" onClick={() => go(api.status === 'online' ? '/app' : '/login')}>
          {api.status === 'online' ? 'Открыть cockpit' : 'Настроить URL'}
        </button>
      </div>
    </div>
  );
};

const HeroPipeline = () => {
  const nodes = [
    ['ear', 'Audio', 'daemon'],
    ['waves', 'Transcript', 'stream'],
    ['brain', 'Brain API', 'extract'],
    ['kanban', 'Board', 'sync'],
  ];

  return (
    <div className="gc-hero-pipeline" aria-label="Поток данных Grey Cardinal">
      {nodes.map(([icon, title, desc], index) => (
        <React.Fragment key={title}>
          <div className="gc-hero-pipe-node" style={{ '--i': index }}>
            <Icon name={icon} size={17}/>
            <span>{title}</span>
            <small>{desc}</small>
          </div>
          {index < nodes.length - 1 && <span className="gc-hero-pipe-line" aria-hidden="true"></span>}
        </React.Fragment>
      ))}
    </div>
  );
};

const MagnifierHero = () => {
  const stageRef = React.useRef(null);
  const [pos, setPos] = React.useState({ x: 0.62, y: 0.40 });
  const [active, setActive] = React.useState(false);
  const rafRef = React.useRef(null);
  const driftRef = React.useRef(null);

  React.useEffect(() => {
    let t = 0;
    const tick = () => {
      if (!active) {
        t += 0.008;
        setPos({ x: 0.6 + Math.cos(t) * 0.14, y: 0.42 + Math.sin(t * 0.8) * 0.12 });
      }
      driftRef.current = requestAnimationFrame(tick);
    };
    driftRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(driftRef.current);
  }, [active]);

  const onMove = (e) => {
    const stage = stageRef.current;
    if (!stage) return;
    const rect = stage.getBoundingClientRect();
    const px = (e.clientX - rect.left) / rect.width;
    const py = (e.clientY - rect.top) / rect.height;
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(() => setPos({ x: px, y: py }));
  };

  const lensR = 130;
  const stageVars = {
    '--lens-x': (pos.x * 100) + '%',
    '--lens-y': (pos.y * 100) + '%',
    '--lens-r': lensR + 'px',
  };

  const bars = [14, 22, 32, 18, 36, 26, 14, 28, 18, 34, 24, 14, 26, 20, 12, 30];

  return (
    <div
      className="gc-lens-stage"
      ref={stageRef}
      style={stageVars}
      onMouseMove={onMove}
      onMouseEnter={() => setActive(true)}
      onMouseLeave={() => setActive(false)}
      onTouchMove={(e) => { const t = e.touches[0]; if (t) { setActive(true); onMove(t); } }}
    >
      <span className="gc-lens-tag">
        <span className="rf-dot rf-dot--brand rf-dot--pulse"></span>
        LIVE MEETING / RAW
      </span>

      <div className="gc-raw-layer" aria-hidden="true">
        {RAW_LINES.map(([who, text], i) => (
          <p key={i} className="gc-raw-line" style={{ '--i': i }}>
            <span className="gc-raw-speaker">{who}: </span>{text}
          </p>
        ))}
      </div>

      <div className="gc-struct-layer">
        <div className="gc-struct-inner">
          <div className="gc-wave" style={{ position:'absolute', top:26, left:24, right:24 }}>
            {bars.concat(bars.slice(0,10)).map((h, i) => <i key={i} style={{ height: h + 'px', flex:1, '--i': i }} />)}
          </div>

          <div className="gc-struct-card" style={{ position:'absolute', top:78, left:24, width:240 }}>
            <div className="gc-struct-eyebrow"><span className="rf-dot rf-dot--brand"></span>TASK FOUND</div>
            <div className="gc-struct-title">Подготовить оплату</div>
            <dl className="gc-kv">
              <dt>Исполнитель</dt><dd>Петя</dd>
              <dt>Дедлайн</dt><dd>чт, 18:00</dd>
              <dt>Источник</dt><dd>transcript</dd>
            </dl>
            <div className="gc-conf-row">
              <dl className="gc-kv"><dt>Confidence</dt><dd className="gc-crimson">87%</dd></dl>
              <div className="gc-conf-bar"><span style={{ width: '87%' }} /></div>
            </div>
          </div>

          <div className="gc-struct-chip" style={{ top:88, right:34 }}>
            <span className="gc-dot-brand"></span>Аня / YouGile / 20:00
          </div>
          <div className="gc-struct-chip" style={{ top:150, right:54 }}>
            <span className="gc-dot-brand"></span>Дима / websocket / завтра
          </div>

          <div className="gc-struct-risk" style={{ top:216, right:44 }}>
            <span className="risk-ic">!</span>
            <div>
              <div className="rk-t">РИСК / дедлайн близко</div>
              <div className="rk-d">оплата / Todo / до среды</div>
            </div>
          </div>

          <div className="gc-struct-kanban">
            {['Todo','In Progress','Done'].map((c, i) => (
              <div className="gc-struct-kcol" key={c}>
                <span className="kh">{c}</span>
                <span className="kc" style={{ width: [88,70,54][i]+'%' }}></span>
                <span className="kc" style={{ width: [60,82,40][i]+'%' }}></span>
              </div>
            ))}
          </div>

          <div className="gc-struct-link" style={{ top:120, left:250, width:60 }}></div>
        </div>
      </div>

      <div className="gc-lens-ring"></div>
      <span className="gc-lens-hint" style={{ opacity: active ? 0 : 1 }}>наведите курсор</span>
    </div>
  );
};

const HeroSignals = () => (
  <div className="gc-hero-signals" aria-label="Короткая сводка">
    {HERO_SIGNALS.map(([k, v, d], i) => (
      <div className="gc-hero-signal" key={k} style={{ '--i': i }}>
        <span className="gc-hero-signal-k">{k}</span>
        <span className="gc-hero-signal-v">{v}</span>
        <span className="gc-hero-signal-d">{d}</span>
      </div>
    ))}
  </div>
);

const HeroSection = ({ go }) => (
  <section className="gc-section gc-hero" id="top">
    <div className="gc-wrap">
      <div className="gc-hero-grid">
        <div className="gc-hero-copy">
          <span className="gc-eyebrow">Автономный PM-агент</span>
          <h1 className="gc-display-1">
            Команда <span className="gc-mobile-stack">говорит.</span><br/>
            Проект <span className="gc-crimson gc-hero-word">движется сам.</span>
          </h1>
          <p className="gc-lead gc-hero-sub">
            Grey Cardinal слушает встречи, выделяет договоренности, создает задачи,
            назначает ответственных и заранее подсвечивает риски - без ручного переноса в доску.
          </p>
          <div className="gc-hero-cta">
            <button className="gc-btn gc-btn--primary gc-btn--lg" onClick={() => go('/login')}>Подключить backend</button>
            <button className="gc-btn gc-btn--secondary gc-btn--lg" onClick={() => go('/download')}>
              <Icon name="download" size={16}/>Daemon setup
            </button>
            <button className="gc-btn gc-btn--ghost gc-btn--lg" onClick={() => go('/app')}>
              Открыть cockpit <Icon name="arrowR" size={15} style={{ marginLeft: '4px' }}/>
            </button>
          </div>
          <BackendPulse go={go}/>
          <HeroSignals/>
          <div className="gc-hero-meta">
            <div className="gc-hero-meta-item"><span className="gc-hero-meta-k">0</span><span className="gc-hero-meta-v">ручного переноса</span></div>
            <div className="gc-hero-meta-item"><span className="gc-hero-meta-k">3</span><span className="gc-hero-meta-v">платформы daemon</span></div>
            <div className="gc-hero-meta-item"><span className="gc-hero-meta-k">86%</span><span className="gc-hero-meta-v">средняя уверенность</span></div>
          </div>
        </div>
        <div className="gc-hero-visual">
          <div className="gc-hero-stage-wrap">
            <MagnifierHero/>
          </div>
          <p className="gc-mute gc-lens-caption">
            Разговор остается разговором. Grey Cardinal превращает его в рабочий проект.
          </p>
          <HeroPipeline/>
        </div>
      </div>
    </div>
  </section>
);

Object.assign(window, { PublicHeader, MagnifierHero, BackendPulse, HeroPipeline, HeroSection });


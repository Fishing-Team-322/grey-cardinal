// Grey Cardinal — public header + magnifier hero

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
    if (el) el.scrollIntoView ? window.scrollTo({ top: el.offsetTop - 70, behavior: 'smooth' }) : null;
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
          <button className="gc-btn gc-btn--primary gc-btn--sm" onClick={() => go('/register')}>Регистрация</button>
        </div>
      </div>
    </header>
  );
};

// raw meeting lines shown on the surface
const RAW_LINES = [
  ['Петя', 'Давайте оплату подготовим к четвергу.'],
  ['Аня', 'Я проверю интеграцию с YouGile сегодня вечером.'],
  ['Дима', 'Мне нужно до завтра поднять websocket для дашборда.'],
  ['Петя', 'Если оплата зависнет в Todo до среды — это риск.'],
  ['Аня', 'Вечерний дайджест соберём в пятницу.'],
  ['Дима', 'И проверить daemon на Windows перед демо.'],
];

const MagnifierHero = () => {
  const stageRef = React.useRef(null);
  const [pos, setPos] = React.useState({ x: 0.62, y: 0.40 });
  const [active, setActive] = React.useState(false);
  const rafRef = React.useRef(null);
  const driftRef = React.useRef(null);

  // gentle idle drift before the user interacts
  React.useEffect(() => {
    let t = 0;
    const tick = () => {
      if (!active) {
        t += 0.012;
        setPos({ x: 0.6 + Math.cos(t) * 0.16, y: 0.42 + Math.sin(t * 0.8) * 0.14 });
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

  const lensR = 124;
  const stageVars = {
    '--lens-x': (pos.x * 100) + '%',
    '--lens-y': (pos.y * 100) + '%',
    '--lens-r': lensR + 'px',
  };

  // bars for waveform
  const bars = [10, 18, 26, 14, 30, 22, 12, 24, 16, 28, 20, 11, 23, 17, 9, 25];

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
      <span className="gc-lens-tag"><span className="rf-dot rf-dot--brand rf-dot--pulse"></span>LIVE MEETING · RAW</span>

      {/* surface: raw conversation */}
      <div className="gc-raw-layer" aria-hidden="true">
        {RAW_LINES.map(([who, text], i) => (
          <p key={i} className="gc-raw-line">
            <span className="gc-raw-speaker">{who}: </span>{text}
          </p>
        ))}
      </div>

      {/* under the lens: structure (fills the stage so the lens always reveals something) */}
      <div className="gc-struct-layer">
        <div className="gc-struct-inner">
          {/* waveform across the top */}
          <div className="gc-wave" style={{ position:'absolute', top:26, left:24, right:24 }}>
            {bars.concat(bars.slice(0,10)).map((h, i) => <i key={i} style={{ height: h + 'px', flex:1 }} />)}
          </div>

          {/* main task card */}
          <div className="gc-struct-card" style={{ position:'absolute', top:74, left:24, width:230 }}>
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

          {/* task chips scattered */}
          <div className="gc-struct-chip" style={{ top:88, right:34 }}>
            <span className="gc-dot-brand"></span>Аня · YouGile · 20:00
          </div>
          <div className="gc-struct-chip" style={{ top:150, right:54 }}>
            <span className="gc-dot-brand"></span>Дима · websocket · завтра
          </div>

          {/* deadline / risk row */}
          <div className="gc-struct-risk" style={{ top:216, right:48 }}>
            <span className="risk-ic">!</span>
            <div>
              <div className="rk-t">РИСК · дедлайн близко</div>
              <div className="rk-d">оплата · Todo · до среды</div>
            </div>
          </div>

          {/* mini kanban at the bottom */}
          <div className="gc-struct-kanban">
            {['Todo','In Progress','Done'].map((c, i) => (
              <div className="gc-struct-kcol" key={c}>
                <span className="kh">{c}</span>
                <span className="kc" style={{ width: [88,70,54][i]+'%' }}></span>
                <span className="kc" style={{ width: [60,82,40][i]+'%' }}></span>
              </div>
            ))}
          </div>

          {/* connecting line */}
          <div className="gc-struct-link" style={{ top:120, left:250, width:60 }}></div>
        </div>
      </div>

      <div className="gc-lens-ring"></div>
      <span className="gc-lens-hint" style={{ opacity: active ? 0 : 1 }}>наведите курсор →</span>
    </div>
  );
};

const HeroSection = ({ go }) => (
  <section className="gc-section gc-hero" id="top">
    <div className="gc-wrap">
      <div className="gc-hero-grid">
        <div className="gc-hero-copy">
          <span className="gc-eyebrow">Автономный PM-агент</span>
          <h1 className="gc-display-1">
            Команда говорит.<br/>
            Проект <span className="gc-crimson">обновляется сам.</span>
          </h1>
          <p className="gc-lead gc-hero-sub">
            Grey Cardinal слушает встречи, находит договорённости, создаёт задачи,
            назначает ответственных и сигналит о рисках — без ручного переноса в доску.
          </p>
          <div className="gc-hero-cta">
            <button className="gc-btn gc-btn--primary gc-btn--lg" onClick={() => go('/register')}>Запросить демо</button>
            <button className="gc-btn gc-btn--secondary gc-btn--lg" onClick={() => go('/download')}>
              <Icon name="download" size={16}/>Скачать daemon
            </button>
            <button className="gc-btn gc-btn--ghost gc-btn--lg" onClick={() => go('/app')}>
              Посмотреть cockpit<Icon name="arrowR" size={15}/>
            </button>
          </div>
          <div className="gc-hero-meta">
            <div className="gc-hero-meta-item"><span className="gc-hero-meta-k">0</span><span className="gc-hero-meta-v">ручного переноса</span></div>
            <div className="gc-hero-meta-item"><span className="gc-hero-meta-k">3</span><span className="gc-hero-meta-v">платформы daemon</span></div>
            <div className="gc-hero-meta-item"><span className="gc-hero-meta-k">86%</span><span className="gc-hero-meta-v">средняя уверенность</span></div>
          </div>
        </div>
        <div>
          <MagnifierHero/>
          <p className="gc-mute" style={{ fontSize: 12, marginTop: 14, textAlign: 'center', fontFamily: 'var(--rf-font-mono)', letterSpacing: '0.04em' }}>
            Люди слышат разговор. Серый кардинал видит проект.
          </p>
        </div>
      </div>
    </div>
  </section>
);

Object.assign(window, { PublicHeader, MagnifierHero, HeroSection });

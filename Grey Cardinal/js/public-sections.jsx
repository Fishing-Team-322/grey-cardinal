// Grey Cardinal — public sections (problem, how, capabilities, preview, daemon, security, final, footer)

const ProblemSection = () => (
  <section className="gc-section" id="problem">
    <div className="gc-wrap gc-reveal">
      <span className="gc-eyebrow">Проблема</span>
      <h2 className="gc-display-2" style={{ marginTop: 20, maxWidth: '18ch' }}>
        Встречи заканчиваются. Договорённости исчезают.
      </h2>
      <div className="gc-problem-list">
        {[
          ['01', 'Задачи остаются в разговоре', 'Решения проговорили, но никто не записал.'],
          ['02', 'PM вручную переносит всё в доску', 'Час после каждой встречи уходит на рутину.'],
          ['03', 'Риски всплывают слишком поздно', 'Просроченный дедлайн замечают на следующем созвоне.'],
        ].map(([n, t, note]) => (
          <div className="gc-problem-row" key={n}>
            <span className="gc-problem-num">{n}</span>
            <span className="gc-problem-text">{t}</span>
            <span className="gc-problem-note">{note}</span>
          </div>
        ))}
      </div>
    </div>
  </section>
);

const HowItWorksSection = () => {
  const steps = [
    ['01', 'ear', 'Слышит встречу', 'Daemon запускается на устройстве, где открыта встреча, и захватывает системный звук.'],
    ['02', 'brain', 'Понимает договорённости', 'Агент извлекает задачи, дедлайны, ответственных и контекст из живого разговора.'],
    ['03', 'kanban', 'Ведёт проект', 'Создаёт карточки, обновляет канбан и связывает задачи с источником.'],
    ['04', 'alert', 'Сигналит о рисках', 'Напоминает о дедлайнах, протухших статусах и задачах, которые могут сорваться.'],
  ];
  return (
    <section className="gc-section" id="how">
      <div className="gc-wrap gc-reveal">
        <span className="gc-eyebrow">Процесс</span>
        <h2 className="gc-display-2" style={{ marginTop: 20, maxWidth: '16ch' }}>Как работает Серый кардинал</h2>
        <div className="gc-steps">
          {steps.map(([n, ic, t, d]) => (
            <div className="gc-step" key={n}>
              <span className="gc-step-num">{n}</span>
              <div className="gc-step-title">{t}</div>
              <div className="gc-step-desc">{d}</div>
              <div className="gc-step-ic"><Icon name={ic} size={20}/></div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

const CapabilitiesSection = () => (
  <section className="gc-section" id="features">
    <div className="gc-wrap gc-reveal">
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-end', flexWrap:'wrap', gap:16 }}>
        <div>
          <span className="gc-eyebrow">Возможности</span>
          <h2 className="gc-display-2" style={{ marginTop: 20, maxWidth: '14ch' }}>Операционный мозг проекта</h2>
        </div>
        <p className="gc-mute" style={{ maxWidth: 300, fontSize: 14 }}>
          Не набор виджетов, а связанная система: от звука встречи до риска на доске.
        </p>
      </div>
      <div className="gc-cap-grid">
        {GC_CAPABILITIES.map((c, i) => (
          <div className="gc-cap" key={c.title}>
            <div className="gc-cap-head">
              <span className="gc-cap-ic"><Icon name={c.icon} size={20}/></span>
              <span className="gc-cap-idx">{String(i+1).padStart(2,'0')}</span>
            </div>
            <div className="gc-cap-title">{c.title}</div>
            <div className="gc-cap-desc">{c.desc}</div>
          </div>
        ))}
      </div>
    </div>
  </section>
);

const ProductPreview = ({ go }) => (
  <section className="gc-section" id="preview">
    <div className="gc-wrap gc-reveal">
      <span className="gc-eyebrow">Продукт</span>
      <h2 className="gc-display-2" style={{ marginTop: 20, maxWidth: '16ch' }}>Живой проект из живой встречи</h2>
      <div className="gc-preview-frame">
        <div className="gc-preview-bar">
          <div className="gc-preview-dots"><i/><i/><i/></div>
          <span className="gc-preview-url">app.grey-cardinal.ru / cockpit</span>
          <span className="gca-chip" style={{ marginLeft:'auto', height:22 }}><span className="dot live"></span>Live meeting</span>
        </div>
        <div className="gc-preview-body">
          <div className="gc-preview-pane">
            <div className="gc-preview-pane-head">
              <span className="gc-preview-pane-title">Что агент услышал</span>
            </div>
            {GC_TRANSCRIPT.slice(0,3).map(t => (
              <div className="gca-tline" key={t.id} style={{ marginBottom: 8 }}>
                <div className="gca-tline-av" style={{ color: t.color, borderColor: t.color+'55' }}>{t.init}</div>
                <div className="gca-tline-body">
                  <div className="gca-tline-meta">
                    <span className="gca-tline-name">{t.name}</span>
                    <span className="gca-tline-time">{t.time}</span>
                  </div>
                  <div className="gca-tline-text">{t.text}</div>
                </div>
              </div>
            ))}
          </div>
          <div className="gc-preview-pane">
            <div className="gc-preview-pane-head">
              <span className="gc-preview-pane-title">Что агент понял</span>
            </div>
            {GC_TASKS.slice(0,2).map((t, i) => (
              <div className={'gca-task' + (i===0?' fresh':'')} key={t.id} style={{ marginBottom: 10 }}>
                <div className="gca-task-top">
                  <span className="gca-task-title">{t.title}</span>
                  <span className={'gca-badge gca-badge--' + (t.prio==='High'?'high':t.prio==='Medium'?'med':'low')}>{t.prio}</span>
                </div>
                <dl className="gca-task-meta">
                  <dt>Исполнитель</dt><dd>{t.who}</dd>
                  <dt>Дедлайн</dt><dd>{t.due}</dd>
                </dl>
                <div className="gca-conf">
                  <div className="gca-conf-bar"><span style={{ width: t.conf+'%' }}/></div>
                  <span className="gca-conf-val">{t.conf}%</span>
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="gc-preview-kanban">
          <span className="gc-preview-pane-title">Живой канбан</span>
          <div className="gca-kanban" style={{ marginTop: 14, gridTemplateColumns:'repeat(5,1fr)' }}>
            {Object.entries(GC_KANBAN).map(([col, cards]) => (
              <div className="gca-kcol" key={col} style={{ minHeight: 120 }}>
                <div className="gca-kcol-head">
                  <span className="gca-kcol-title">{col}</span>
                  <span className="gca-kcol-count">{cards.length}</span>
                </div>
                {cards.slice(0,1).map(c => (
                  <div className={'gca-kcard'+(c.risk?' risk':'')} key={c.id}>
                    <div className="gca-kcard-title">{c.title}</div>
                    <div className="gca-kcard-foot">
                      <span className="gca-kcard-assignee"><span className="gca-kdot" style={{ background:c.color+'33', color:c.color }}>{c.who[0]}</span>{c.who}</span>
                    </div>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      </div>
      <div style={{ marginTop: 26, display:'flex', gap:12, flexWrap:'wrap' }}>
        <button className="gc-btn gc-btn--secondary" onClick={() => go('/app')}>
          Открыть cockpit<Icon name="arrowR" size={15}/>
        </button>
      </div>
    </div>
  </section>
);

const DaemonCTA = ({ go }) => (
  <section className="gc-section" id="daemon">
    <div className="gc-wrap gc-reveal">
      <div className="gc-split gc-split--center">
        <div>
          <span className="gc-eyebrow">Daemon</span>
          <h2 className="gc-display-3" style={{ marginTop: 18 }}>Daemon слышит то, что слышит команда</h2>
          <p className="gc-lead" style={{ marginTop: 20 }}>
            Установите Grey Cardinal Daemon на Windows, Linux или macOS. Он захватывает
            системный звук встречи и отправляет в brain-api структурированные события транскрипта.
          </p>
          <div style={{ marginTop: 30, display:'flex', gap:12, flexWrap:'wrap' }}>
            <button className="gc-btn gc-btn--primary gc-btn--lg" onClick={() => go('/download')}>
              <Icon name="download" size={16}/>Скачать daemon
            </button>
          </div>
        </div>
        <div>
          <div className="gc-eyebrow no-rule" style={{ marginBottom: 18 }}>Поток данных</div>
          <div className="gc-flow">
            <div className="gc-flow-node"><span className="gc-flow-k">01</span><span className="gc-flow-v">Встреча</span></div>
            <div className="gc-flow-arrow"><Icon name="arrowR" size={16}/></div>
            <div className="gc-flow-node"><span className="gc-flow-k">02</span><span className="gc-flow-v">Системный звук</span></div>
            <div className="gc-flow-arrow"><Icon name="arrowR" size={16}/></div>
            <div className="gc-flow-node is-accent"><span className="gc-flow-k">03</span><span className="gc-flow-v">Daemon</span></div>
          </div>
          <div className="gc-flow" style={{ marginTop: 12 }}>
            <div className="gc-flow-node"><span className="gc-flow-k">04</span><span className="gc-flow-v">Transcript events</span></div>
            <div className="gc-flow-arrow"><Icon name="arrowR" size={16}/></div>
            <div className="gc-flow-node"><span className="gc-flow-k">05</span><span className="gc-flow-v">brain-api</span></div>
            <div className="gc-flow-arrow"><Icon name="arrowR" size={16}/></div>
            <div className="gc-flow-node is-accent"><span className="gc-flow-k">06</span><span className="gc-flow-v">Задачи и риски</span></div>
          </div>
        </div>
      </div>
    </div>
  </section>
);

const SecuritySection = () => (
  <section className="gc-section" id="security">
    <div className="gc-wrap gc-reveal">
      <div className="gc-split">
        <div>
          <span className="gc-eyebrow">Контроль</span>
          <h2 className="gc-display-3" style={{ marginTop: 18, maxWidth: '12ch' }}>Контроль и приватность</h2>
          <p className="gc-mute" style={{ marginTop: 20, fontSize: 14, maxWidth: 320 }}>
            Звук остаётся на стороне команды. На сервер уходит ровно столько, сколько нужно для работы агента.
          </p>
        </div>
        <div className="gc-sec-list">
          {[
            'Daemon работает на устройстве пользователя.',
            'Сервер не обязан подключаться к звонку.',
            'На сервер можно отправлять уже текст, а не сырой звук.',
            'Задачи создаются через confirmation mode.',
            'История задач и встреч хранится в вашем workspace.',
            'Интеграции подключаются через adapter layer.',
          ].map((t, i) => (
            <div className="gc-sec-item" key={i}>
              <span className="ic"><Icon name={i===0?'server':i===1?'shield':i===2?'eye':i===3?'check':i===4?'history':'plug'} size={20}/></span>
              <p>{t}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  </section>
);

const FinalCTA = ({ go }) => (
  <section className="gc-section gc-final">
    <div className="gc-wrap gc-reveal">
      <span className="gc-eyebrow no-rule" style={{ justifyContent:'center', display:'flex' }}>Серый кардинал</span>
      <h2 className="gc-display-2">Дайте проекту второго менеджера — невидимого</h2>
      <div className="gc-final-cta">
        <button className="gc-btn gc-btn--primary gc-btn--lg" onClick={() => go('/register')}>Регистрация</button>
        <button className="gc-btn gc-btn--secondary gc-btn--lg" onClick={() => go('/download')}><Icon name="download" size={16}/>Скачать daemon</button>
        <button className="gc-btn gc-btn--ghost gc-btn--lg" onClick={() => go('/app')}>Посмотреть cockpit<Icon name="arrowR" size={15}/></button>
      </div>
    </div>
  </section>
);

const PublicFooter = ({ go }) => (
  <footer className="gc-footer">
    <div className="gc-wrap">
      <div className="gc-footer-grid">
        <div className="gc-footer-col">
          <Logo/>
          <p className="gc-mute" style={{ fontSize: 13, marginTop: 18, maxWidth: 280 }}>
            Невидимый project manager, который работает в фоне. Команда говорит — агент действует.
          </p>
        </div>
        <div className="gc-footer-col">
          <h5>Продукт</h5>
          <a onClick={() => go('/')}>Возможности</a>
          <a onClick={() => go('/download')}>Daemon</a>
          <a onClick={() => go('/app')}>Cockpit</a>
        </div>
        <div className="gc-footer-col">
          <h5>Аккаунт</h5>
          <a onClick={() => go('/login')}>Войти</a>
          <a onClick={() => go('/register')}>Регистрация</a>
        </div>
        <div className="gc-footer-col">
          <h5>Домены</h5>
          <a>grey-cardinal.ru</a>
          <a>app.grey-cardinal.ru</a>
          <a>api.grey-cardinal.ru</a>
        </div>
      </div>
      <div className="gc-footer-bottom">
        <span>© 2026 GREY CARDINAL · СЕРЫЙ КАРДИНАЛ</span>
        <span>FEDERATED · PM · OPS</span>
      </div>
    </div>
  </footer>
);

const PublicHomePage = ({ go }) => {
  useReveal();
  return (
    <div>
      <PublicHeader go={go}/>
      <HeroSection go={go}/>
      <hr className="gc-rule"/>
      <ProblemSection/>
      <hr className="gc-rule"/>
      <HowItWorksSection/>
      <hr className="gc-rule"/>
      <CapabilitiesSection/>
      <hr className="gc-rule"/>
      <ProductPreview go={go}/>
      <hr className="gc-rule"/>
      <DaemonCTA go={go}/>
      <hr className="gc-rule"/>
      <SecuritySection/>
      <hr className="gc-rule"/>
      <FinalCTA go={go}/>
      <PublicFooter go={go}/>
    </div>
  );
};

Object.assign(window, { PublicHomePage, ProblemSection, HowItWorksSection, CapabilitiesSection, ProductPreview, DaemonCTA, SecuritySection, FinalCTA, PublicFooter });

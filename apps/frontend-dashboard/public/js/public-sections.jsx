// Grey Cardinal - public sections

const ProblemSection = ({ language }) => {
  const tr = (ru, en) => copyText(language, ru, en);
  const rows = [
    ['01', tr('Решения остаются в разговоре', 'Decisions stay in the conversation'), tr('Все договорились, но никто не перенес задачу в систему.', 'Everyone agreed, but nobody moved the task into the system.'), tr('агент создает карточку', 'agent creates a card')],
    ['02', tr('PM снова собирает доску руками', 'The PM rebuilds the board by hand again'), tr('После созвона час уходит на расшифровку и копипаст.', 'After the call, an hour goes into notes and copy-paste.'), tr('доска обновляется сама', 'board updates itself')],
    ['03', tr('Риски всплывают слишком поздно', 'Risks surface too late'), tr('Проблемный дедлайн замечают уже на следующей встрече.', 'A troubled deadline is noticed only at the next meeting.'), tr('риск подсвечен заранее', 'risk is flagged early')],
  ];
  return (
    <section className="gc-section" id="problem">
      <div className="gc-wrap gc-reveal">
        <span className="gc-eyebrow">{tr('Проблема', 'Problem')}</span>
        <h2 className="gc-display-2" style={{ marginTop: 20, maxWidth: '18ch' }}>
          {tr('Встреча заканчивается. Работа расползается.', 'The meeting ends. Work starts drifting.')}
        </h2>
        <div className="gc-problem-list">
          {rows.map(([n, t, note, action]) => (
          <div className="gc-problem-row" key={n}>
            <span className="gc-problem-num">{n}</span>
            <span className="gc-problem-main">
              <span className="gc-problem-text">{t}</span>
              <span className="gc-problem-action"><Icon name="zap" size={14}/>{action}</span>
            </span>
            <span className="gc-problem-note">{note}</span>
          </div>
          ))}
        </div>
      </div>
    </section>
  );
};

const HowItWorksSection = ({ language }) => {
  const tr = (ru, en) => copyText(language, ru, en);
  const steps = [
    ['01', 'ear', tr('Слушает встречу', 'Listens to the meeting'), tr('Daemon запускается на устройстве участника и забирает системный звук там, где открыт звонок.', 'The daemon runs on a participant device and captures system audio where the call is open.')],
    ['02', 'brain', tr('Понимает договоренности', 'Understands agreements'), tr('Агент извлекает задачи, дедлайны, исполнителей и контекст из живого разговора.', 'The agent extracts tasks, deadlines, owners, and context from live conversation.')],
    ['03', 'kanban', tr('Обновляет проект', 'Updates the project'), tr('Создает карточки, связывает их с источником и аккуратно обновляет канбан.', 'It creates cards, links them to the source, and updates the kanban board cleanly.')],
    ['04', 'alert', tr('Сигналит о рисках', 'Flags risks'), tr('Находит зависшие статусы, близкие дедлайны и задачи, которые могут сорваться.', 'It finds stuck statuses, close deadlines, and tasks likely to slip.')],
  ];
  return (
    <section className="gc-section" id="how">
      <div className="gc-wrap gc-reveal">
        <span className="gc-eyebrow">{tr('Процесс', 'Process')}</span>
        <h2 className="gc-display-2" style={{ marginTop: 20, maxWidth: '16ch' }}>{tr('Как работает Серый кардинал', 'How Grey Cardinal works')}</h2>
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

const OpsSnapshotSection = ({ language }) => {
  const tr = (ru, en) => copyText(language, ru, en);
  const metrics = [
    ['12', tr('решений извлечено', 'decisions extracted'), tr('за неделю встреч', 'from one week of meetings')],
    [tr('7 мин', '7 min'), tr('до первой карточки', 'to the first card'), tr('после созвона', 'after the call')],
    ['94%', tr('задач с источником', 'tasks with source'), tr('видно кто сказал', 'speaker is visible')],
  ];
  const timeline = [
    ['14:02', tr('Реплика', 'Line'), tr('Петя просит подготовить оплату к четвергу.', 'Peter asks to prepare payment by Thursday.')],
    ['14:03', tr('Карточка', 'Card'), tr('Grey Cardinal определяет владельца и дедлайн.', 'Grey Cardinal detects the owner and deadline.')],
    ['14:06', tr('Риск', 'Risk'), tr('Если задача останется в Todo до среды, агент поднимет сигнал.', 'If the task stays in Todo until Wednesday, the agent raises a signal.')],
  ];
  return (
    <section className="gc-section gc-section--tight gc-ops-section">
      <div className="gc-wrap gc-reveal">
        <div className="gc-ops">
          <div className="gc-ops-copy">
            <span className="gc-eyebrow">{tr('Сводка', 'Snapshot')}</span>
            <h2 className="gc-display-3" style={{ marginTop: 18, maxWidth: '16ch' }}>{tr('После встречи уже есть рабочий контур', 'After the meeting, the work loop already exists')}</h2>
            <p className="gc-mute" style={{ marginTop: 18, fontSize: 14, maxWidth: 430 }}>
              {tr(
                'Агент не просто пишет transcript. Он собирает цепочку: кто сказал, что нужно сделать, когда проверить и где появится риск.',
                'The agent does not just write a transcript. It builds the chain: who said what, what must be done, when to check it, and where risk appears.'
              )}
            </p>
          </div>
          <div className="gc-ops-board" aria-label={tr('Операционная сводка', 'Operational snapshot')}>
            <div className="gc-ops-metrics">
              {metrics.map(([v, k, d]) => (
                <div className="gc-ops-metric" key={k}>
                  <span className="gc-ops-metric-v">{v}</span>
                  <span className="gc-ops-metric-k">{k}</span>
                  <span className="gc-ops-metric-d">{d}</span>
                </div>
              ))}
            </div>
            <div className="gc-ops-timeline">
              {timeline.map(([time, type, text], i) => (
                <div className="gc-ops-event" key={time} style={{ '--i': i }}>
                  <span className="gc-ops-event-time">{time}</span>
                  <span className="gc-ops-event-dot"></span>
                  <span className="gc-ops-event-body">
                    <span className="gc-ops-event-type">{type}</span>
                    <span className="gc-ops-event-text">{text}</span>
                  </span>
                </div>
              ))}
            </div>
            <div className="gc-ops-footer">
              <span><Icon name="target" size={15}/> {tr('источник привязан к задаче', 'source is linked to the task')}</span>
              <span><Icon name="bell" size={15}/> {tr('напоминание до дедлайна', 'reminder before deadline')}</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

const capabilitiesForLanguage = (language) => [
  { icon:'ear', title:copyText(language, 'Захват встречи через daemon', 'Meeting capture through daemon'), desc:copyText(language, 'Системный звук снимается на устройстве пользователя, без подключения сервера к звонку.', 'System audio is captured on the user device without the server joining the call.') },
  { icon:'waves', title:copyText(language, 'Распознавание договоренностей', 'Agreement recognition'), desc:copyText(language, 'Агент выделяет задачи, дедлайны, владельцев и контекст из живого разговора.', 'The agent extracts tasks, deadlines, owners, and context from live conversation.') },
  { icon:'check', title:copyText(language, 'Автоматическое создание задач', 'Automatic task creation'), desc:copyText(language, 'Реплика превращается в карточку со ссылкой на источник и уровнем уверенности.', 'A spoken line becomes a card with source link and confidence level.') },
  { icon:'users', title:copyText(language, 'Назначение ответственных', 'Owner assignment'), desc:copyText(language, 'Исполнитель определяется по контексту, голосу и роли участника в обсуждении.', 'The owner is inferred from context, voice, and participant role in the discussion.') },
  { icon:'send', title:copyText(language, 'Telegram-подтверждения', 'Telegram confirmations'), desc:copyText(language, 'Спорные задачи уходят на подтверждение исполнителю, а не тихо ломают процесс.', 'Ambiguous tasks go to the owner for confirmation instead of silently breaking the process.') },
  { icon:'kanban', title:copyText(language, 'Интеграция с канбан-доской', 'Kanban board integration'), desc:copyText(language, 'Колонки и статусы обновляются как зеркало реального проекта, а не отдельная копия.', 'Columns and statuses update as a mirror of the real project, not a separate copy.') },
  { icon:'bell', title:copyText(language, 'Напоминания и дайджесты', 'Reminders and digests'), desc:copyText(language, 'Команда получает сводки и напоминания до того, как дедлайн становится пожаром.', 'The team gets summaries and reminders before a deadline becomes an emergency.') },
  { icon:'alert', title:copyText(language, 'Риски и просрочки', 'Risks and overdue work'), desc:copyText(language, 'Grey Cardinal подсвечивает зависшие статусы, близкие дедлайны и потерянные задачи.', 'Grey Cardinal highlights stuck statuses, close deadlines, and lost tasks.') },
  { icon:'history', title:copyText(language, 'История встреч и решений', 'Meeting and decision history'), desc:copyText(language, 'Каждая задача связана с моментом разговора, где она появилась.', 'Each task is tied to the moment in conversation where it appeared.') },
];

const CapabilitiesSection = ({ language }) => {
  const tr = (ru, en) => copyText(language, ru, en);
  const capabilities = capabilitiesForLanguage(language);
  return (
    <section className="gc-section" id="features">
      <div className="gc-wrap gc-reveal">
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-end', flexWrap:'wrap', gap:16 }}>
          <div>
            <span className="gc-eyebrow">{tr('Возможности', 'Features')}</span>
            <h2 className="gc-display-2" style={{ marginTop: 20, maxWidth: '14ch' }}>{tr('Операционный мозг проекта', 'The operational brain of the project')}</h2>
          </div>
          <p className="gc-mute" style={{ maxWidth: 320, fontSize: 14 }}>
            {tr('Не набор виджетов, а связанная система: от звука встречи до риска на доске.', 'Not a set of widgets, but a connected system: from meeting audio to board risk.')}
          </p>
        </div>
        <div className="gc-cap-grid">
          {capabilities.map((c, i) => (
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
};

const previewTranscriptForLanguage = (language) => {
  if (language === 'ru') return GC_TRANSCRIPT.slice(0, 3);
  return [
    { id:'t1', name:'Peter', init:'P', color:'#3b82c4', time:'14:02', text:'Let us prepare the payment by Thursday, final deadline is the end of the week.', status:'final' },
    { id:'t2', name:'Anna', init:'A', color:'#3da37a', time:'14:03', text:'I will check the YouGile integration tonight, around eight.', status:'final' },
    { id:'t3', name:'Dima', init:'D', color:'#d68b1c', time:'14:05', text:'I need to bring up the dashboard websocket by tomorrow.', status:'final' },
  ];
};

const previewTasksForLanguage = (language) => {
  if (language === 'ru') return GC_TASKS.slice(0, 2);
  return [
    { id:'k1', title:'Prepare payment', who:'Peter', whoInit:'P', due:'Thursday, 18:00', prio:'High', conf:87, source:'meeting', voice:true },
    { id:'k2', title:'Check YouGile integration', who:'Anna', whoInit:'A', due:'Today, 20:00', prio:'Medium', conf:81, source:'meeting', voice:true },
  ];
};

const previewKanbanForLanguage = (language) => {
  if (language === 'ru') return GC_KANBAN;
  return {
    Backlog: [
      { id:'b1', title:'Update daemon onboarding', who:'Anna', color:'#3da37a' },
      { id:'b2', title:'Workspace token docs', who:'Peter', color:'#3b82c4' },
    ],
    Todo: [
      { id:'td1', title:'Prepare payment', who:'Peter', color:'#3b82c4', risk:true },
      { id:'td2', title:'Test daemon on Windows', who:'Dima', color:'#d68b1c' },
    ],
    'In Progress': [
      { id:'ip1', title:'Bring up dashboard websocket', who:'Dima', color:'#d68b1c' },
      { id:'ip2', title:'YouGile integration', who:'Anna', color:'#3da37a' },
    ],
    Review: [
      { id:'rv1', title:'Evening digest v2', who:'Anna', color:'#3da37a' },
    ],
    Done: [
      { id:'dn1', title:'System audio capture', who:'Dima', color:'#d68b1c' },
      { id:'dn2', title:'Telegram confirmations', who:'Peter', color:'#3b82c4' },
    ],
  };
};

const ProductPreview = ({ language }) => {
  const tr = (ru, en) => copyText(language, ru, en);
  const transcript = previewTranscriptForLanguage(language);
  const tasks = previewTasksForLanguage(language);
  const kanban = previewKanbanForLanguage(language);
  const insights = [
    ['TASKS', '+3', tr('созданы из реплик', 'created from speech')],
    ['RISK', '1', tr('поднят до дедлайна', 'raised before deadline')],
    ['SYNC', 'live', tr('канбан обновлен', 'kanban updated')],
  ];
  return (
    <section className="gc-section" id="preview">
      <div className="gc-wrap gc-reveal">
        <span className="gc-eyebrow">{tr('Продукт', 'Product')}</span>
        <h2 className="gc-display-2" style={{ marginTop: 20, maxWidth: '16ch' }}>{tr('Живой проект из живой встречи', 'A live project from a live meeting')}</h2>
        <div className="gc-preview-frame">
          <div className="gc-preview-bar">
            <div className="gc-preview-dots"><i/><i/><i/></div>
            <span className="gc-preview-url">app.grey-cardinal.ru / cockpit</span>
            <span className="gca-chip" style={{ marginLeft:'auto', height:22 }}><span className="dot live"></span>{tr('Живая встреча', 'Live meeting')}</span>
          </div>
          <div className="gc-preview-insights">
            {insights.map(([k, v, d]) => (
            <div className="gc-preview-insight" key={k}>
              <span className="gc-preview-insight-k">{k}</span>
              <span className="gc-preview-insight-v">{v}</span>
              <span className="gc-preview-insight-d">{d}</span>
            </div>
          ))}
          </div>
          <div className="gc-preview-body">
            <div className="gc-preview-pane">
              <div className="gc-preview-pane-head">
                <span className="gc-preview-pane-title">{tr('Что агент услышал', 'What the agent heard')}</span>
              </div>
              {transcript.map(t => (
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
                <span className="gc-preview-pane-title">{tr('Что агент понял', 'What the agent understood')}</span>
              </div>
              {tasks.map((t, i) => (
              <div className={'gca-task' + (i===0?' fresh':'')} key={t.id} style={{ marginBottom: 10 }}>
                <div className="gca-task-top">
                  <span className="gca-task-title">{t.title}</span>
                  <span className={'gca-badge gca-badge--' + (t.prio==='High'?'high':t.prio==='Medium'?'med':'low')}>{t.prio}</span>
                </div>
                <dl className="gca-task-meta">
                  <dt>{tr('Исполнитель', 'Owner')}</dt><dd>{t.who}</dd>
                  <dt>{tr('Дедлайн', 'Deadline')}</dt><dd>{t.due}</dd>
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
            <span className="gc-preview-pane-title">{tr('Живой канбан', 'Live kanban')}</span>
            <div className="gca-kanban" style={{ marginTop: 14, gridTemplateColumns:'repeat(5,1fr)' }}>
              {Object.entries(kanban).map(([col, cards]) => (
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
      </div>
    </section>
  );
};

const DaemonCTA = ({ language }) => {
  const tr = (ru, en) => copyText(language, ru, en);
  return (
    <section className="gc-section" id="daemon">
      <div className="gc-wrap gc-reveal">
        <div className="gc-split gc-split--center">
          <div>
            <span className="gc-eyebrow">Daemon</span>
            <h2 className="gc-display-3" style={{ marginTop: 18 }}>{tr('Daemon слышит то, что слышит команда', 'Daemon hears what the team hears')}</h2>
            <p className="gc-lead" style={{ marginTop: 20 }}>
              {tr(
                'Установите Grey Cardinal Daemon на Windows, Linux или macOS. Он захватывает системный звук встречи и отправляет в brain-api структурированные события transcript stream.',
                'Install Grey Cardinal Daemon on Windows, Linux, or macOS. It captures meeting system audio and sends structured transcript stream events to brain-api.'
              )}
            </p>
          </div>
          <div>
          <div className="gc-daemon-console">
            <div className="gc-daemon-console-head">
              <span className="gc-eyebrow no-rule">{tr('Поток данных', 'Data stream')}</span>
              <span className="gc-pill"><span className="dot pulse"></span>healthy</span>
            </div>
            <div className="gc-flow">
              <div className="gc-flow-node"><span className="gc-flow-k">01</span><span className="gc-flow-v">{tr('Встреча', 'Meeting')}</span></div>
              <div className="gc-flow-arrow"><Icon name="arrowR" size={16}/></div>
              <div className="gc-flow-node"><span className="gc-flow-k">02</span><span className="gc-flow-v">{tr('Системный звук', 'System audio')}</span></div>
              <div className="gc-flow-arrow"><Icon name="arrowR" size={16}/></div>
              <div className="gc-flow-node is-accent"><span className="gc-flow-k">03</span><span className="gc-flow-v">Daemon</span></div>
            </div>
            <div className="gc-flow" style={{ marginTop: 12 }}>
              <div className="gc-flow-node"><span className="gc-flow-k">04</span><span className="gc-flow-v">Transcript events</span></div>
              <div className="gc-flow-arrow"><Icon name="arrowR" size={16}/></div>
              <div className="gc-flow-node"><span className="gc-flow-k">05</span><span className="gc-flow-v">brain-api</span></div>
              <div className="gc-flow-arrow"><Icon name="arrowR" size={16}/></div>
              <div className="gc-flow-node is-accent"><span className="gc-flow-k">06</span><span className="gc-flow-v">{tr('Задачи и риски', 'Tasks and risks')}</span></div>
            </div>
            <div className="gc-daemon-stream">
              {[
                ['14:02:11', 'audio frame captured'],
                ['14:02:14', 'speaker Петя matched'],
                ['14:02:20', 'task candidate sent to brain-api'],
              ].map(([t, d]) => (
                <span key={t}><b>{t}</b>{d}</span>
              ))}
            </div>
          </div>
          </div>
        </div>
      </div>
    </section>
  );
};

const SecuritySection = ({ language }) => {
  const tr = (ru, en) => copyText(language, ru, en);
  const items = [
    tr('Daemon работает на устройстве пользователя.', 'Daemon runs on the user device.'),
    tr('Сервер не обязан подключаться к звонку.', 'The server does not need to join the call.'),
    tr('На сервер можно отправлять уже текст, а не сырой звук.', 'You can send text to the server instead of raw audio.'),
    tr('Сомнительные задачи проходят confirmation mode.', 'Ambiguous tasks go through confirmation mode.'),
    tr('История задач и встреч хранится в вашем workspace.', 'Task and meeting history stays in your workspace.'),
    tr('Интеграции подключаются через adapter layer.', 'Integrations connect through an adapter layer.'),
  ];
  return (
    <section className="gc-section" id="security">
      <div className="gc-wrap gc-reveal">
        <div className="gc-split">
          <div>
            <span className="gc-eyebrow">{tr('Контроль', 'Control')}</span>
            <h2 className="gc-display-3" style={{ marginTop: 18, maxWidth: '12ch' }}>{tr('Контроль и приватность', 'Control and privacy')}</h2>
            <p className="gc-mute" style={{ marginTop: 20, fontSize: 14, maxWidth: 340 }}>
              {tr('Звук остается на стороне команды. На сервер уходит ровно столько, сколько нужно для работы агента.', 'Audio stays on the team side. The server receives only what the agent needs to work.')}
            </p>
          </div>
        <div className="gc-sec-list">
          {items.map((t, i) => (
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
};

const FinalCTA = ({ language }) => (
  <section className="gc-section gc-final">
    <div className="gc-wrap gc-reveal">
      <span className="gc-eyebrow no-rule" style={{ justifyContent:'center', display:'flex' }}>{copyText(language, 'Серый кардинал', 'Grey Cardinal')}</span>
      <h2 className="gc-display-2">{copyText(language, 'Дайте проекту второго менеджера - невидимого', 'Give the project a second manager - an invisible one')}</h2>
    </div>
  </section>
);

const PublicFooter = ({ go, language }) => {
  const tr = (ru, en) => copyText(language, ru, en);
  return (
  <footer className="gc-footer">
    <div className="gc-wrap">
      <div className="gc-footer-grid">
        <div className="gc-footer-col">
          <Logo/>
          <p className="gc-mute" style={{ fontSize: 13, marginTop: 18, maxWidth: 280 }}>
            {tr('Невидимый project manager, который работает в фоне. Команда говорит - агент действует.', 'An invisible project manager working in the background. The team talks, the agent acts.')}
          </p>
        </div>
        <div className="gc-footer-col">
          <h5>{tr('Продукт', 'Product')}</h5>
          <a onClick={() => go('/')}>{tr('Возможности', 'Features')}</a>
          <a onClick={() => go('/download')}>Daemon</a>
          <a onClick={() => go('/app')}>Cockpit</a>
        </div>
        <div className="gc-footer-col">
          <h5>{tr('Аккаунт', 'Account')}</h5>
          <a onClick={() => go('/login')}>{tr('Вход', 'Sign in')}</a>
          <a onClick={() => go('/register')}>{tr('Регистрация', 'Registration')}</a>
        </div>
        <div className="gc-footer-col">
          <h5>{tr('Домены', 'Domains')}</h5>
          <a>grey-cardinal.ru</a>
          <a>app.grey-cardinal.ru</a>
          <a>api.grey-cardinal.ru</a>
        </div>
      </div>
      <div className="gc-footer-bottom">
        <span>© 2026 GREY CARDINAL / СЕРЫЙ КАРДИНАЛ</span>
        <span>FEDERATED / PM / OPS</span>
      </div>
    </div>
  </footer>
  );
};

const PublicHomePage = ({ go, language, setLanguage }) => {
  useReveal();
  return (
    <div>
      <PublicHeader go={go} language={language} setLanguage={setLanguage}/>
      <HeroSection language={language}/>
      <hr className="gc-rule"/>
      <ProblemSection language={language}/>
      <hr className="gc-rule"/>
      <HowItWorksSection language={language}/>
      <hr className="gc-rule"/>
      <OpsSnapshotSection language={language}/>
      <hr className="gc-rule"/>
      <CapabilitiesSection language={language}/>
      <hr className="gc-rule"/>
      <ProductPreview language={language}/>
      <hr className="gc-rule"/>
      <DaemonCTA language={language}/>
      <hr className="gc-rule"/>
      <SecuritySection language={language}/>
      <hr className="gc-rule"/>
      <FinalCTA language={language}/>
      <PublicFooter go={go} language={language}/>
    </div>
  );
};

Object.assign(window, { PublicHomePage, ProblemSection, HowItWorksSection, OpsSnapshotSection, CapabilitiesSection, ProductPreview, DaemonCTA, SecuritySection, FinalCTA, PublicFooter });

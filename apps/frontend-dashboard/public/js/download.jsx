// Grey Cardinal - /download page

const WINDOWS_DAEMON = {
  url: '/downloads/grey-cardinal-daemon-windows.zip',
  version: '0.2.0',
  builtAt: '2026-06-04',
  size: '77.7 KB',
  sha256: '31F1089611D7C59ED74FA9BC81264823CD301AF5E8927AC47E975798DEDD0FDF',
};

const PLATFORMS = [
  { id:'win', icon:'windows', name:'Windows', sub:'Grey Cardinal Daemon for Windows',
    specs:[['Формат','ZIP + .exe'],['Захват','WASAPI microphone / loopback'],['Статус','готов к скачиванию']], cta:'Инструкция Windows' },
  { id:'mac', icon:'apple', name:'macOS', sub:'Grey Cardinal Daemon for macOS',
    specs:[['Формат','.dmg'],['Захват','ScreenCaptureKit'],['Поддержка','Apple Silicon / Intel']], cta:'Инструкция macOS' },
  { id:'linux', icon:'linux', name:'Linux', sub:'Grey Cardinal Daemon for Linux',
    specs:[['Формат','AppImage / deb'],['Захват','PipeWire / Pulse'],['Статус','нужен release artifact']], cta:'Инструкция Linux' },
];

const INSTALL = {
  win: [
    'Скачайте ZIP-пакет и распакуйте его в удобную папку.',
    'Запустите PowerShell в этой папке и выполните Set-ExecutionPolicy -Scope Process Bypass.',
    'Проверьте связь с backend: .\\smoke_upload_test.ps1 -BackendUrl "https://fishingteam.su".',
    'Запустите короткий capture: .\\install_or_start.ps1 -BackendUrl "https://fishingteam.su" -DurationSec 10.',
    'Откройте cockpit, нажмите Refresh и проверьте блок Daemon uploads.',
  ],
  mac: ['Скачайте .dmg.', 'Перенесите приложение в Applications.', 'Разрешите захват системного звука.', 'При необходимости установите virtual audio device.', 'Подключите daemon к workspace.'],
  linux: ['Скачайте AppImage или deb.', 'Проверьте PipeWire/PulseAudio monitor source.', 'Запустите daemon.', 'Введите workspace token.', 'Проверьте тестовую запись.'],
};

const PlatformDownloadCard = ({ p, active, onSelect }) => (
  <div className="gc-plat">
    <div className="gc-plat-ic"><Icon name={p.icon} size={26}/></div>
    <div>
      <div className="gc-plat-name">{p.name}</div>
      <div className="gc-plat-desc">{p.sub}</div>
    </div>
    <dl className="gc-plat-specs">
      {p.specs.map(([k,v]) => (
        <div className="gc-plat-spec" key={k}><dt>{k}</dt><dd>{v}</dd></div>
      ))}
    </dl>
    <button className={'gc-btn gc-btn--block ' + (active ? 'gc-btn--primary' : 'gc-btn--secondary')} onClick={() => onSelect(p.id)}>
      <Icon name="list" size={16}/>{p.cta}
    </button>
  </div>
);

const DownloadPage = ({ go }) => {
  const [tab, setTab] = React.useState('win');
  useReveal();
  return (
    <div>
      <PublicHeader go={go}/>

      <section className="gc-section gc-section--tight">
        <div className="gc-wrap gc-reveal">
          <span className="gc-eyebrow">Daemon</span>
          <h1 className="gc-display-2" style={{ marginTop: 20, maxWidth: '16ch' }}>Установите Grey Cardinal Daemon</h1>
          <p className="gc-lead" style={{ marginTop: 22, maxWidth: 620 }}>
            Daemon запускается на устройстве, где открыта встреча, захватывает системный звук
            и отправляет в Grey Cardinal поток transcript events.
          </p>
          <div className="gc-pill" style={{ marginTop: 24, height:28, padding:'0 14px' }}>
            <Icon name="shield" size={14} style={{ color:'var(--rf-crimson-hi)' }}/>
            Сервер не подключается к звонку. Daemon слышит встречу с клиентского устройства.
          </div>
          <div className="gc-form-status" style={{ marginTop: 14, maxWidth: 760 }}>
            Windows package уже доступен: внутри native agent, production config template, PowerShell запуск,
            smoke upload и README. Секреты в пакет не включены.
          </div>
          <div className="gc-controls" style={{ marginTop: 20, gap: 12, flexWrap: 'wrap' }}>
            <a className="gc-btn gc-btn--primary gc-btn--lg" href={WINDOWS_DAEMON.url} download>
              <Icon name="download" size={16}/>Скачать daemon для Windows
            </a>
            <button className="gc-btn gc-btn--secondary gc-btn--lg" onClick={() => go('/app')}>
              <Icon name="grid" size={16}/>Открыть cockpit
            </button>
          </div>
          <dl className="gc-plat-specs" style={{ maxWidth: 760, marginTop: 18 }}>
            <div className="gc-plat-spec"><dt>URL</dt><dd className="mono">{WINDOWS_DAEMON.url}</dd></div>
            <div className="gc-plat-spec"><dt>Версия</dt><dd className="mono">{WINDOWS_DAEMON.version}</dd></div>
            <div className="gc-plat-spec"><dt>Дата</dt><dd className="mono">{WINDOWS_DAEMON.builtAt}</dd></div>
            <div className="gc-plat-spec"><dt>Размер</dt><dd className="mono">{WINDOWS_DAEMON.size}</dd></div>
            <div className="gc-plat-spec"><dt>SHA256</dt><dd className="mono">{WINDOWS_DAEMON.sha256.slice(0, 18)}...</dd></div>
          </dl>

          <div className="gc-plat-grid">
            {PLATFORMS.map(p => <PlatformDownloadCard p={p} key={p.id} active={tab===p.id} onSelect={setTab}/>)}
          </div>
        </div>
      </section>

      <hr className="gc-rule"/>

      <section className="gc-section gc-section--tight">
        <div className="gc-wrap gc-reveal">
          <span className="gc-eyebrow">Установка</span>
          <h2 className="gc-display-3" style={{ marginTop: 18 }}>Пять шагов до первой встречи</h2>
          <div className="gc-tabs">
            {PLATFORMS.map(p => (
              <span key={p.id} className={'gc-tab' + (tab===p.id?' active':'')} onClick={() => setTab(p.id)}>
                <Icon name={p.icon} size={15}/>{p.name}
              </span>
            ))}
          </div>
          <div className="gc-steps-list">
            {INSTALL[tab].map((s, i) => (
              <div className="gc-step-line" key={i}>
                <span className="n">{String(i+1).padStart(2,'0')}</span>
                <p>{s}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <hr className="gc-rule"/>

      <section className="gc-section gc-section--tight">
        <div className="gc-wrap gc-reveal">
          <span className="gc-eyebrow">Архитектура</span>
          <h2 className="gc-display-3" style={{ marginTop: 18, maxWidth: '18ch' }}>Daemon превращает звук в поток событий</h2>
          <div className="gc-flow" style={{ marginTop: 32 }}>
            <div className="gc-flow-node"><span className="gc-flow-k">01</span><span className="gc-flow-v">Встреча</span></div>
            <div className="gc-flow-arrow"><Icon name="arrowR" size={16}/></div>
            <div className="gc-flow-node"><span className="gc-flow-k">02</span><span className="gc-flow-v">Системный звук</span></div>
            <div className="gc-flow-arrow"><Icon name="arrowR" size={16}/></div>
            <div className="gc-flow-node is-accent"><span className="gc-flow-k">03</span><span className="gc-flow-v">Daemon</span></div>
            <div className="gc-flow-arrow"><Icon name="arrowR" size={16}/></div>
            <div className="gc-flow-node"><span className="gc-flow-k">04</span><span className="gc-flow-v">brain-api</span></div>
            <div className="gc-flow-arrow"><Icon name="arrowR" size={16}/></div>
            <div className="gc-flow-node is-accent"><span className="gc-flow-k">05</span><span className="gc-flow-v">Задачи и риски</span></div>
          </div>
          <p className="gc-mute" style={{ marginTop: 24, fontSize: 14, maxWidth: 640 }}>
            Daemon не ведет проект самостоятельно. Он превращает звук встречи в поток событий.
            Логика задач, подтверждений, доски и напоминаний живет в brain-api.
          </p>
        </div>
      </section>

      <hr className="gc-rule"/>

      <section className="gc-section gc-section--tight">
        <div className="gc-wrap gc-reveal">
          <span className="gc-eyebrow">Релизы</span>
          <h2 className="gc-display-3" style={{ marginTop: 18 }}>Статус сборок</h2>
          <table className="gc-status-table">
            <thead>
              <tr><th>Платформа</th><th>Статус</th><th>Формат</th><th>Захват звука</th></tr>
            </thead>
            <tbody>
              <tr><td>Windows</td><td><span className="gca-badge gca-badge--ok">download ready</span></td><td className="mono">ZIP + .exe</td><td className="mono">WASAPI microphone / loopback</td></tr>
              <tr><td>macOS</td><td><span className="gca-badge gca-badge--med">нужен release endpoint</span></td><td className="mono">.dmg</td><td className="mono">ScreenCaptureKit / virtual device</td></tr>
              <tr><td>Linux</td><td><span className="gca-badge gca-badge--med">нужен release endpoint</span></td><td className="mono">AppImage / deb</td><td className="mono">PipeWire / PulseAudio monitor</td></tr>
            </tbody>
          </table>
        </div>
      </section>

      <PublicFooter go={go}/>
    </div>
  );
};

Object.assign(window, { DownloadPage });

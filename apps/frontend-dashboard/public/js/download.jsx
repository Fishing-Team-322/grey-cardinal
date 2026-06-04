// Grey Cardinal - /download page

const DAEMON_MANIFEST_FALLBACK = {
  version: '0.3.0',
  backend_url: 'https://fishingteam.su',
  built_at: '2026-06-04',
  platforms: {
    windows: {
      label: 'Windows',
      artifact: 'grey-cardinal-daemon-windows-x64.msi',
      url: '/downloads/grey-cardinal-daemon-windows-x64.msi',
      format: 'MSI installer',
      status: 'available',
      status_label: 'ready',
      size: '104 KB',
      size_bytes: 106496,
      sha256: 'B24AA357A349488405133B6CBF4B428FA2FD6D70B45895B98BCDA3296774F241',
      capture: 'WASAPI microphone / loopback',
      support: 'Windows x64',
    },
    macos: {
      label: 'macOS',
      artifact: 'grey-cardinal-daemon-macos-universal.dmg',
      url: '/downloads/grey-cardinal-daemon-macos-universal.dmg',
      format: 'DMG / PKG',
      status: 'preview',
      status_label: 'CI artifact planned',
      size: 'not published',
      sha256: '',
      capture: 'ScreenCaptureKit / microphone',
      support: 'Apple Silicon / Intel',
    },
    linux: {
      label: 'Linux',
      artifact: 'grey-cardinal-daemon-linux-amd64.deb',
      url: '/downloads/grey-cardinal-daemon-linux-amd64.deb',
      format: 'DEB package',
      status: 'preview',
      status_label: 'CI artifact planned',
      size: 'not published',
      sha256: '',
      capture: 'PipeWire / PulseAudio',
      support: 'Debian / Ubuntu amd64',
    },
  },
};

const PLATFORM_ORDER = ['windows', 'macos', 'linux'];

const PLATFORM_UI = {
  windows: {
    icon: 'windows',
    sub: 'Grey Cardinal Daemon for Windows',
    cta: 'Инструкция Windows',
    downloadLabel: 'Скачать MSI для Windows',
    statusClass: 'gca-badge--ok',
    steps: [
      'Скачайте MSI installer.',
      'Запустите installer и установите Grey Cardinal Daemon.',
      'Откройте Grey Cardinal Daemon из Start Menu.',
      'Проверьте backend URL: https://fishingteam.su.',
      'Запустите smoke upload и откройте cockpit, чтобы проверить Daemon uploads.',
    ],
    commands: [
      'msiexec /i grey-cardinal-daemon-windows-x64.msi',
      'powershell -ExecutionPolicy Bypass -File "C:\\Program Files\\Grey Cardinal Daemon\\smoke_upload_test.ps1" -BackendUrl "https://fishingteam.su"',
      'powershell -ExecutionPolicy Bypass -File "C:\\Program Files\\Grey Cardinal Daemon\\open_logs.ps1"',
    ],
    note: 'MSI устанавливает exe, config template, helper scripts и Start Menu shortcut. Секреты в installer не включены.',
  },
  macos: {
    icon: 'apple',
    sub: 'Grey Cardinal Daemon for macOS',
    cta: 'Инструкция macOS',
    downloadLabel: 'Скачать installer для macOS',
    statusClass: 'gca-badge--med',
    steps: [
      'DMG/PKG artifact пока не опубликован.',
      'После релиза скачайте installer и установите Grey Cardinal Daemon.',
      'Разрешите Microphone и Screen Recording/System Audio permissions.',
      'Проверьте backend URL: https://fishingteam.su.',
      'Откройте logs и cockpit после smoke/capture проверки.',
    ],
    commands: [
      'open grey-cardinal-daemon-macos-universal.dmg',
      'tail -f ~/Library/Logs/GreyCardinal/Daemon.log',
      'launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.greycardinal.daemon.plist',
    ],
    note: 'macOS package flow подготовлен для CI. Реальный DMG/PKG требует macOS runner, signing и notarization.',
  },
  linux: {
    icon: 'linux',
    sub: 'Grey Cardinal Daemon for Debian/Ubuntu',
    cta: 'Инструкция Linux',
    downloadLabel: 'Скачать .deb для Debian/Ubuntu',
    statusClass: 'gca-badge--med',
    steps: [
      'DEB artifact пока не опубликован.',
      'После релиза скачайте .deb package.',
      'Установите пакет через dpkg и исправьте зависимости через apt.',
      'Настройте /etc/grey-cardinal-daemon/config.toml.',
      'Запустите systemd service и проверьте journalctl + cockpit.',
    ],
    commands: [
      'sudo dpkg -i grey-cardinal-daemon-linux-amd64.deb',
      'sudo apt-get install -f',
      'sudo systemctl enable --now grey-cardinal-daemon',
      'journalctl -u grey-cardinal-daemon -f',
    ],
    note: 'Linux DEB layout подготовлен. Реальный capture требует PipeWire/PulseAudio daemon implementation.',
  },
};

const detectPlatform = () => {
  const text = `${navigator.platform || ''} ${navigator.userAgent || ''}`.toLowerCase();
  if (text.includes('win')) return 'windows';
  if (text.includes('mac')) return 'macos';
  if (text.includes('linux') || text.includes('x11')) return 'linux';
  return 'windows';
};

const statusText = (status) => ({
  available: 'available',
  preview: 'preview',
  planned: 'planned',
}[status] || status || 'preview');

const artifactAvailable = (platform) => platform.status === 'available' && platform.url;

const PlatformDownloadCard = ({ id, platform, active, onSelect }) => {
  const ui = PLATFORM_UI[id];
  return (
    <div className="gc-plat">
      <div className="gc-plat-ic"><Icon name={ui.icon} size={26}/></div>
      <div>
        <div className="gc-plat-name">{platform.label}</div>
        <div className="gc-plat-desc">{ui.sub}</div>
      </div>
      <dl className="gc-plat-specs">
        <div className="gc-plat-spec"><dt>Формат</dt><dd>{platform.format}</dd></div>
        <div className="gc-plat-spec"><dt>Захват</dt><dd>{platform.capture}</dd></div>
        <div className="gc-plat-spec"><dt>Поддержка</dt><dd>{platform.support}</dd></div>
        <div className="gc-plat-spec"><dt>Статус</dt><dd>{platform.status_label || statusText(platform.status)}</dd></div>
      </dl>
      <button className={'gc-btn gc-btn--block ' + (active ? 'gc-btn--primary' : 'gc-btn--secondary')} onClick={() => onSelect(id, true)}>
        <Icon name="list" size={16}/>{ui.cta}
      </button>
    </div>
  );
};

const SelectedPlatformPanel = ({ id, platform, manifest, go }) => {
  const ui = PLATFORM_UI[id];
  const available = artifactAvailable(platform);
  return (
    <div className="gc-form-status" style={{ marginTop: 20, maxWidth: 820 }}>
      <div className="gc-controls" style={{ gap: 12, flexWrap: 'wrap' }}>
        {available ? (
          <a className="gc-btn gc-btn--primary gc-btn--lg" href={platform.url} download>
            <Icon name="download" size={16}/>{ui.downloadLabel}
          </a>
        ) : (
          <button className="gc-btn gc-btn--secondary gc-btn--lg" disabled>
            <Icon name="download" size={16}/>{ui.downloadLabel}
          </button>
        )}
        <button className="gc-btn gc-btn--secondary gc-btn--lg" onClick={() => go('/app')}>
          <Icon name="grid" size={16}/>Открыть cockpit
        </button>
      </div>
      {!available && (
        <p className="gc-mute" style={{ marginTop: 12, fontSize: 14 }}>
          Artifact not published yet. Кнопка скачивания выключена, чтобы не вести на 404.
        </p>
      )}
      <dl className="gc-plat-specs" style={{ marginTop: 18 }}>
        <div className="gc-plat-spec"><dt>URL</dt><dd className="mono">{platform.url}</dd></div>
        <div className="gc-plat-spec"><dt>Version</dt><dd className="mono">{manifest.version}</dd></div>
        <div className="gc-plat-spec"><dt>Date</dt><dd className="mono">{manifest.built_at}</dd></div>
        <div className="gc-plat-spec"><dt>Size</dt><dd className="mono">{platform.size}</dd></div>
        <div className="gc-plat-spec"><dt>Status</dt><dd><span className={'gca-badge ' + ui.statusClass}>{statusText(platform.status)}</span></dd></div>
        <div className="gc-plat-spec"><dt>SHA256</dt><dd className="mono">{platform.sha256 ? `${platform.sha256.slice(0, 18)}...` : 'not published'}</dd></div>
      </dl>
      <p className="gc-mute" style={{ marginTop: 14, fontSize: 14 }}>{ui.note}</p>
    </div>
  );
};

const DownloadPage = ({ go }) => {
  const [manifest, setManifest] = React.useState(DAEMON_MANIFEST_FALLBACK);
  const [tab, setTab] = React.useState(() => detectPlatform());
  const instructionRef = React.useRef(null);

  React.useEffect(() => {
    fetch('/downloads/daemon-manifest.json')
      .then((response) => response.ok ? response.json() : DAEMON_MANIFEST_FALLBACK)
      .then((data) => setManifest(data))
      .catch(() => setManifest(DAEMON_MANIFEST_FALLBACK));
  }, []);

  useReveal();

  const selectPlatform = (id, scroll = false) => {
    setTab(id);
    if (scroll) {
      window.setTimeout(() => instructionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 80);
    }
  };

  const platforms = manifest.platforms || DAEMON_MANIFEST_FALLBACK.platforms;
  const selected = platforms[tab] || platforms.windows;
  const selectedUi = PLATFORM_UI[tab] || PLATFORM_UI.windows;

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

          <SelectedPlatformPanel id={tab} platform={selected} manifest={manifest} go={go}/>

          <div className="gc-plat-grid">
            {PLATFORM_ORDER.map(id => (
              <PlatformDownloadCard
                key={id}
                id={id}
                platform={platforms[id]}
                active={tab === id}
                onSelect={selectPlatform}
              />
            ))}
          </div>
        </div>
      </section>

      <hr className="gc-rule"/>

      <section className="gc-section gc-section--tight" ref={instructionRef}>
        <div className="gc-wrap gc-reveal">
          <span className="gc-eyebrow">Установка</span>
          <h2 className="gc-display-3" style={{ marginTop: 18 }}>Инструкция: {selected.label}</h2>
          <div className="gc-tabs">
            {PLATFORM_ORDER.map(id => (
              <span key={id} className={'gc-tab' + (tab===id?' active':'')} onClick={() => selectPlatform(id)}>
                <Icon name={PLATFORM_UI[id].icon} size={15}/>{platforms[id].label}
              </span>
            ))}
          </div>
          <div className="gc-steps-list">
            {selectedUi.steps.map((s, i) => (
              <div className="gc-step-line" key={i}>
                <span className="n">{String(i+1).padStart(2,'0')}</span>
                <p>{s}</p>
              </div>
            ))}
          </div>
          <div className="gc-form-status" style={{ marginTop: 22, maxWidth: 820 }}>
            <span className="gc-eyebrow">Команды</span>
            <div className="gc-steps-list" style={{ marginTop: 14 }}>
              {selectedUi.commands.map((command, i) => (
                <div className="gc-step-line" key={i}>
                  <span className="n">{String(i+1).padStart(2,'0')}</span>
                  <p className="mono">{command}</p>
                </div>
              ))}
            </div>
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
              <tr><th>Платформа</th><th>Статус</th><th>Формат</th><th>Artifact</th></tr>
            </thead>
            <tbody>
              {PLATFORM_ORDER.map(id => (
                <tr key={id}>
                  <td>{platforms[id].label}</td>
                  <td><span className={'gca-badge ' + PLATFORM_UI[id].statusClass}>{statusText(platforms[id].status)}</span></td>
                  <td className="mono">{platforms[id].format}</td>
                  <td className="mono">{platforms[id].artifact}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <PublicFooter go={go}/>
    </div>
  );
};

Object.assign(window, { DownloadPage });

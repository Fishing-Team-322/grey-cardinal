// Grey Cardinal - backend connection and desktop identity setup

const AuthAside = ({ quote }) => (
  <div className="gc-auth-aside">
    <Logo size={32}/>
    <div className="gc-auth-aside-quote">{quote}</div>
    <div className="gc-mono-xs" style={{ display:'flex', gap:18, color:'var(--rf-fg-4)' }}>
      <span>brain-api</span>
      <span>/</span>
      <span>CONNECTED COCKPIT</span>
    </div>
  </div>
);

const Field = ({ label, type='text', value, onChange, placeholder, autoComplete }) => (
  <div className="gc-form-field">
    <label>{label}</label>
    <input className="gc-input" type={type} value={value} onChange={onChange} placeholder={placeholder} autoComplete={autoComplete}/>
  </div>
);

const LoginPage = ({ go }) => {
  const initial = GCApi.config();
  const [baseUrl, setBaseUrl] = React.useState(initial.baseUrl);
  const [internalToken, setInternalToken] = React.useState(initial.internalToken);
  const [status, setStatus] = React.useState('');
  const [busy, setBusy] = React.useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setStatus('Проверяю brain-api...');
    try {
      GCApi.saveConfig({ baseUrl, internalToken });
      await GCApi.health();
      await GCApi.dependencies();
      setStatus('Backend доступен. Открываю cockpit.');
      go('/app');
    } catch (error) {
      setStatus(`Не удалось подключиться: ${error.message}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="gc-auth">
      <AuthAside quote={<>Подключите <span className="gc-crimson">brain-api</span> и откройте рабочий cockpit.</>}/>
      <div className="gc-auth-main">
        <div className="gc-auth-card">
          <span className="gc-auth-back" onClick={() => go('/')}><Icon name="chevL" size={14}/>На главную</span>
          <h1 className="gc-display-4">Подключение к backend</h1>
          <p className="gc-mute" style={{ marginTop: 8, fontSize: 14 }}>Это dev-подключение к существующему brain-api. Публичной авторизации в backend пока нет.</p>
          <form className="gc-form" onSubmit={submit}>
            <Field label="Brain API URL" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="http://127.0.0.1:8000"/>
            <Field label="Internal token" value={internalToken} onChange={(e) => setInternalToken(e.target.value)} placeholder="dev-internal-token"/>
            {status && <div className="gc-form-status">{status}</div>}
            <button className="gc-btn gc-btn--primary gc-btn--lg gc-btn--block" type="submit" disabled={busy}>
              {busy ? 'Проверяем...' : 'Сохранить и открыть cockpit'}
            </button>
          </form>
          <p className="gc-form-meta">Нужна desktop identity? <a onClick={() => go('/register')}>Зарегистрировать устройство</a></p>
        </div>
      </div>
    </div>
  );
};

const RegisterPage = ({ go }) => {
  const initial = GCApi.config();
  const [baseUrl, setBaseUrl] = React.useState(initial.baseUrl);
  const [internalToken, setInternalToken] = React.useState(initial.internalToken);
  const [displayName, setDisplayName] = React.useState('Петр Смирнов');
  const [deviceName, setDeviceName] = React.useState('Frontend workstation');
  const [platform, setPlatform] = React.useState('windows');
  const [status, setStatus] = React.useState('');
  const [busy, setBusy] = React.useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setStatus('Регистрирую устройство...');
    try {
      GCApi.saveConfig({ baseUrl, internalToken });
      const identity = await GCApi.registerDesktop({
        display_name: displayName,
        device_name: deviceName,
        platform,
        app_version: 'frontend-dashboard',
        device_fingerprint: `frontend-${platform}-${displayName}`.toLowerCase().replace(/\s+/g, '-'),
      });
      GCApi.saveConfig({ desktopIdentity: { ...identity, platform, app_version: 'frontend-dashboard' } });
      setStatus('Устройство зарегистрировано. Открываю cockpit.');
      go('/app');
    } catch (error) {
      setStatus(`Регистрация не прошла: ${error.message}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="gc-auth">
      <AuthAside quote={<>Зарегистрируйте устройство, чтобы desktop endpoints знали <span className="gc-crimson">кто говорит</span>.</>}/>
      <div className="gc-auth-main">
        <div className="gc-auth-card">
          <span className="gc-auth-back" onClick={() => go('/')}><Icon name="chevL" size={14}/>На главную</span>
          <h1 className="gc-display-4">Desktop identity</h1>
          <p className="gc-mute" style={{ marginTop: 8, fontSize: 14 }}>Форма вызывает реальный endpoint `/desktop/devices/register`.</p>
          <form className="gc-form" onSubmit={submit}>
            <Field label="Brain API URL" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="http://127.0.0.1:8000"/>
            <Field label="Internal token" value={internalToken} onChange={(e) => setInternalToken(e.target.value)} placeholder="dev-internal-token"/>
            <Field label="Имя участника" value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="Петр Смирнов" autoComplete="name"/>
            <Field label="Устройство" value={deviceName} onChange={(e) => setDeviceName(e.target.value)} placeholder="Frontend workstation"/>
            <div className="gc-form-field">
              <label>Платформа</label>
              <select className="gc-input" value={platform} onChange={(e) => setPlatform(e.target.value)}>
                <option value="windows">Windows</option>
                <option value="macos">macOS</option>
                <option value="linux">Linux</option>
              </select>
            </div>
            {status && <div className="gc-form-status">{status}</div>}
            <button className="gc-btn gc-btn--primary gc-btn--lg gc-btn--block" type="submit" disabled={busy}>
              {busy ? 'Регистрируем...' : 'Зарегистрировать устройство'}
            </button>
          </form>
          <p className="gc-form-meta">Уже есть API config? <a onClick={() => go('/login')}>Проверить подключение</a></p>
        </div>
      </div>
    </div>
  );
};

Object.assign(window, { LoginPage, RegisterPage });

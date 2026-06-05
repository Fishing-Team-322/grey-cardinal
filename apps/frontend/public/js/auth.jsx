// Grey Cardinal - frontend account auth screens.

const GC_AUTH_ACCOUNT_KEY = 'gc.auth.account';
const GC_AUTH_SESSION_KEY = 'gc.auth.session';

const AuthAside = ({ quote, mode }) => (
  <div className="gc-auth-aside">
    <Logo size={32}/>
    <div className="gc-auth-aside-quote">{quote}</div>
    <div className="gc-mono-xs" style={{ display:'flex', gap:18, color:'var(--rf-fg-4)' }}>
      <span>account</span>
      <span>/</span>
      <span>{mode}</span>
    </div>
  </div>
);

const Field = ({ label, type='text', value, onChange, placeholder, autoComplete, className = '' }) => (
  <div className={'gc-form-field ' + className}>
    <label>{label}</label>
    <input className="gc-input" type={type} value={value} onChange={onChange} placeholder={placeholder} autoComplete={autoComplete}/>
  </div>
);

const normalizeAuthEmail = (value) => String(value || '').trim().toLowerCase();
const validAuthEmail = (value) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalizeAuthEmail(value));

const hashAuthPassword = (value) => {
  let hash = 2166136261;
  const text = String(value || '');
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return String(hash >>> 0);
};

const loadAuthAccount = () => {
  try {
    return JSON.parse(localStorage.getItem(GC_AUTH_ACCOUNT_KEY) || 'null');
  } catch (_) {
    return null;
  }
};

const saveAuthSession = (account) => {
  const session = {
    email: account.email,
    login: account.login,
    firstName: account.firstName,
    lastName: account.lastName,
    signedAt: new Date().toISOString(),
  };
  localStorage.setItem(GC_AUTH_SESSION_KEY, JSON.stringify(session));
  return session;
};

const LoginPage = ({ go, language, setLanguage }) => {
  const tr = (ru, en) => copyText(language, ru, en);
  const [email, setEmail] = React.useState('');
  const [password, setPassword] = React.useState('');
  const [status, setStatus] = React.useState('');
  const [busy, setBusy] = React.useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setStatus('');

    const normalizedEmail = normalizeAuthEmail(email);
    if (!validAuthEmail(normalizedEmail)) {
      setStatus(tr('Введите корректную почту.', 'Enter a valid email.'));
      setBusy(false);
      return;
    }
    if (!password) {
      setStatus(tr('Введите пароль.', 'Enter a password.'));
      setBusy(false);
      return;
    }

    try {
      const user = await GCApi.login(normalizedEmail, password);
      // Store minimal user info for display (cookie handles auth)
      saveAuthSession({ email: user.email, login: user.login, displayName: user.display_name });
      setStatus(tr('Вход выполнен. Открываю cockpit.', 'Signed in. Opening cockpit.'));
      window.setTimeout(() => go('/app'), 220);
    } catch (err) {
      setStatus(err.message || tr('Ошибка входа.', 'Login failed.'));
      setBusy(false);
    }
  };

  return (
    <div className="gc-auth">
      <AuthAside
        mode="SIGN IN"
        quote={<>{tr('Войдите в', 'Sign in to')} <span className="gc-crimson">Grey Cardinal</span> {tr('и продолжайте работу в cockpit.', 'and continue in cockpit.')}</>}
      />
      <div className="gc-auth-main">
        <div className="gc-auth-card">
          <div className="gc-auth-topline">
            <span className="gc-auth-back" onClick={() => go('/')}><Icon name="chevL" size={14}/>{tr('На главную', 'Home')}</span>
            <LanguageToggle language={language} setLanguage={setLanguage}/>
          </div>
          <h1 className="gc-display-4">{tr('Вход', 'Sign in')}</h1>
          <p className="gc-mute" style={{ marginTop: 8, fontSize: 14 }}>
            {tr('Для входа нужна только почта и пароль.', 'Only email and password are required to sign in.')}
          </p>
          <form className="gc-form" onSubmit={submit}>
            <Field label={tr('Почта', 'Email')} type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@example.com" autoComplete="email"/>
            <Field label={tr('Пароль', 'Password')} type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" autoComplete="current-password"/>
            {status && <div className="gc-form-status">{status}</div>}
            <button className="gc-btn gc-btn--primary gc-btn--lg gc-btn--block" type="submit" disabled={busy}>
              <Icon name="check" size={16}/>{busy ? tr('Входим...', 'Signing in...') : tr('Войти', 'Sign in')}
            </button>
          </form>
          <p className="gc-form-meta">
            {tr('Нет аккаунта?', 'No account?')} <a onClick={() => go('/register')}>{tr('Зарегистрироваться', 'Create account')}</a>
          </p>
        </div>
      </div>
    </div>
  );
};

const RegisterPage = ({ go, language, setLanguage }) => {
  const tr = (ru, en) => copyText(language, ru, en);
  const [email, setEmail] = React.useState('');
  const [login, setLogin] = React.useState('');
  const [lastName, setLastName] = React.useState('');
  const [firstName, setFirstName] = React.useState('');
  const [password, setPassword] = React.useState('');
  const [confirmPassword, setConfirmPassword] = React.useState('');
  const [status, setStatus] = React.useState('');
  const [busy, setBusy] = React.useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setStatus('');

    const normalizedEmail = normalizeAuthEmail(email);
    const normalizedLogin = login.trim();
    const normalizedFirstName = firstName.trim();
    const normalizedLastName = lastName.trim();

    if (!validAuthEmail(normalizedEmail)) {
      setStatus(tr('Введите корректную почту.', 'Enter a valid email.'));
      setBusy(false);
      return;
    }
    if (normalizedLogin.length < 3) {
      setStatus(tr('Логин должен быть минимум 3 символа.', 'Login must be at least 3 characters.'));
      setBusy(false);
      return;
    }
    if (!normalizedLastName || !normalizedFirstName) {
      setStatus(tr('Заполните фамилию и имя.', 'Fill in last name and first name.'));
      setBusy(false);
      return;
    }
    if (password.length < 6) {
      setStatus(tr('Пароль должен быть минимум 6 символов.', 'Password must be at least 6 characters.'));
      setBusy(false);
      return;
    }
    if (password !== confirmPassword) {
      setStatus(tr('Пароли не совпадают.', 'Passwords do not match.'));
      setBusy(false);
      return;
    }

    try {
      const user = await GCApi.register(normalizedEmail, normalizedLogin, normalizedFirstName, normalizedLastName, password);
      saveAuthSession({ email: user.email, login: user.login, displayName: user.display_name });
      setStatus(tr('Аккаунт создан. Открываю cockpit.', 'Account created. Opening cockpit.'));
      window.setTimeout(() => go('/app'), 220);
    } catch (err) {
      const msg = err.message || '';
      if (msg.includes('Email already')) {
        setStatus(tr('Эта почта уже зарегистрирована.', 'This email is already registered.'));
      } else if (msg.includes('Login already')) {
        setStatus(tr('Этот логин уже занят.', 'This login is already taken.'));
      } else {
        setStatus(msg || tr('Ошибка регистрации.', 'Registration failed.'));
      }
      setBusy(false);
    }
  };

  return (
    <div className="gc-auth">
      <AuthAside
        mode="CREATE ACCOUNT"
        quote={<>{tr('Создайте аккаунт для', 'Create an account for')} <span className="gc-crimson">Grey Cardinal</span> {tr('и подключите рабочий cockpit.', 'and enter the working cockpit.')}</>}
      />
      <div className="gc-auth-main">
        <div className="gc-auth-card gc-auth-card--wide">
          <div className="gc-auth-topline">
            <span className="gc-auth-back" onClick={() => go('/')}><Icon name="chevL" size={14}/>{tr('На главную', 'Home')}</span>
            <LanguageToggle language={language} setLanguage={setLanguage}/>
          </div>
          <h1 className="gc-display-4">{tr('Регистрация', 'Registration')}</h1>
          <p className="gc-mute" style={{ marginTop: 8, fontSize: 14 }}>
            {tr('Заполните данные участника. Пока это frontend-only аккаунт для мокового входа.', 'Fill in participant data. For now this is a frontend-only account for mock sign-in.')}
          </p>
          <form className="gc-form" onSubmit={submit}>
            <div className="gc-auth-form-grid">
              <Field className="gc-auth-form-wide" label={tr('Почта', 'Email')} type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@example.com" autoComplete="email"/>
              <Field className="gc-auth-form-wide" label={tr('Логин', 'Login')} value={login} onChange={(e) => setLogin(e.target.value)} placeholder="grey_cardinal" autoComplete="username"/>
              <Field label={tr('Фамилия', 'Last name')} value={lastName} onChange={(e) => setLastName(e.target.value)} placeholder={tr('Смирнов', 'Smirnov')} autoComplete="family-name"/>
              <Field label={tr('Имя', 'First name')} value={firstName} onChange={(e) => setFirstName(e.target.value)} placeholder={tr('Петр', 'Peter')} autoComplete="given-name"/>
              <Field label={tr('Пароль', 'Password')} type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" autoComplete="new-password"/>
              <Field label={tr('Подтверждение пароля', 'Confirm password')} type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} placeholder="••••••••" autoComplete="new-password"/>
            </div>
            {status && <div className="gc-form-status">{status}</div>}
            <button className="gc-btn gc-btn--primary gc-btn--lg gc-btn--block" type="submit" disabled={busy}>
              <Icon name="check" size={16}/>{busy ? tr('Создаем...', 'Creating...') : tr('Зарегистрироваться', 'Create account')}
            </button>
          </form>
          <p className="gc-form-meta">
            {tr('Уже есть аккаунт?', 'Already have an account?')} <a onClick={() => go('/login')}>{tr('Войти', 'Sign in')}</a>
          </p>
        </div>
      </div>
    </div>
  );
};

Object.assign(window, { LoginPage, RegisterPage });

// Grey Cardinal — v2 auth screens (реальные /api/auth/* + cookie-сессия).

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

// Куда вернуться после успешного входа: если ждёт инвайт — на него, иначе в /app.
const gcPostAuthTarget = () => {
  const pending = sessionStorage.getItem('gc.pendingInvite');
  if (pending) return '/i/' + pending;
  return '/app';
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
    try {
      await GCApi.login({ email: email.trim().toLowerCase(), password });
      setStatus(tr('Вход выполнен.', 'Signed in.'));
      go(gcPostAuthTarget());
    } catch (err) {
      setStatus(err.message || tr('Не удалось войти.', 'Sign-in failed.'));
      setBusy(false);
    }
  };

  return (
    <div className="gc-auth">
      <AuthAside
        mode="SIGN IN"
        quote={<>{tr('Войдите в', 'Sign in to')} <span className="gc-crimson">Grey Cardinal</span></>}
      />
      <div className="gc-auth-main">
        <div className="gc-auth-card">
          <div className="gc-auth-topline">
            <span className="gc-auth-back" onClick={() => go('/')}><Icon name="chevL" size={14}/>{tr('На главную', 'Home')}</span>
            <LanguageToggle language={language} setLanguage={setLanguage}/>
          </div>
          <h1 className="gc-display-4">{tr('Вход', 'Sign in')}</h1>
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
    if (password.length < 6) { setStatus(tr('Пароль минимум 6 символов.', 'Password min 6 chars.')); setBusy(false); return; }
    if (password !== confirmPassword) { setStatus(tr('Пароли не совпадают.', 'Passwords do not match.')); setBusy(false); return; }
    try {
      await GCApi.register({
        email: email.trim().toLowerCase(),
        login: login.trim().toLowerCase(),
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        password,
      });
      setStatus(tr('Аккаунт создан.', 'Account created.'));
      go(gcPostAuthTarget());
    } catch (err) {
      setStatus(err.message || tr('Не удалось зарегистрироваться.', 'Registration failed.'));
      setBusy(false);
    }
  };

  return (
    <div className="gc-auth">
      <AuthAside
        mode="CREATE ACCOUNT"
        quote={<>{tr('Создайте аккаунт для', 'Create an account for')} <span className="gc-crimson">Grey Cardinal</span></>}
      />
      <div className="gc-auth-main">
        <div className="gc-auth-card gc-auth-card--wide">
          <div className="gc-auth-topline">
            <span className="gc-auth-back" onClick={() => go('/')}><Icon name="chevL" size={14}/>{tr('На главную', 'Home')}</span>
            <LanguageToggle language={language} setLanguage={setLanguage}/>
          </div>
          <h1 className="gc-display-4">{tr('Регистрация', 'Registration')}</h1>
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

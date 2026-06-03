// Grey Cardinal — /login and /register

const AuthAside = ({ quote }) => (
  <div className="gc-auth-aside">
    <Logo size={32}/>
    <div className="gc-auth-aside-quote">{quote}</div>
    <div className="gc-mono-xs" style={{ display:'flex', gap:18, color:'var(--rf-fg-4)' }}>
      <span>grey-cardinal.ru</span>
      <span>·</span>
      <span>FEDERATED · PM · OPS</span>
    </div>
  </div>
);

const Field = ({ label, type='text', placeholder, autoComplete }) => (
  <div className="gc-form-field">
    <label>{label}</label>
    <input className="gc-input" type={type} placeholder={placeholder} autoComplete={autoComplete}/>
  </div>
);

const LoginPage = ({ go }) => (
  <div className="gc-auth">
    <AuthAside quote={<>Люди слышат разговор.<br/><span className="gc-crimson">Серый кардинал</span> видит проект.</>}/>
    <div className="gc-auth-main">
      <div className="gc-auth-card">
        <span className="gc-auth-back" onClick={() => go('/')}><Icon name="chevL" size={14}/>На главную</span>
        <h1 className="gc-display-4">Вход в Grey Cardinal</h1>
        <p className="gc-mute" style={{ marginTop: 8, fontSize: 14 }}>Войдите в workspace, чтобы открыть cockpit.</p>
        <form className="gc-form" onSubmit={(e) => { e.preventDefault(); go('/app'); }}>
          <Field label="Email" type="email" placeholder="you@team.ru" autoComplete="email"/>
          <Field label="Пароль" type="password" placeholder="••••••••" autoComplete="current-password"/>
          <div className="gc-form-row">
            <label style={{ display:'flex', alignItems:'center', gap:8, color:'var(--rf-fg-2)', cursor:'pointer' }}>
              <input type="checkbox" style={{ accentColor:'var(--rf-crimson)' }}/> Запомнить меня
            </label>
            <a className="gc-form-meta" style={{ margin:0, color:'var(--rf-crimson-hi)', cursor:'pointer' }}>Забыли пароль?</a>
          </div>
          <button className="gc-btn gc-btn--primary gc-btn--lg gc-btn--block" type="submit">Войти</button>
        </form>
        <p className="gc-form-meta">Нет аккаунта? <a onClick={() => go('/register')}>Создать аккаунт</a></p>
      </div>
    </div>
  </div>
);

const RegisterPage = ({ go }) => (
  <div className="gc-auth">
    <AuthAside quote={<>Дайте проекту <span className="gc-crimson">второго менеджера</span> — невидимого.</>}/>
    <div className="gc-auth-main">
      <div className="gc-auth-card">
        <span className="gc-auth-back" onClick={() => go('/')}><Icon name="chevL" size={14}/>На главную</span>
        <h1 className="gc-display-4">Создать workspace</h1>
        <p className="gc-mute" style={{ marginTop: 8, fontSize: 14 }}>Команда говорит — Серый кардинал ведёт проект.</p>
        <form className="gc-form" onSubmit={(e) => { e.preventDefault(); go('/app'); }}>
          <Field label="Имя" placeholder="Пётр Смирнов" autoComplete="name"/>
          <Field label="Email" type="email" placeholder="you@team.ru" autoComplete="email"/>
          <Field label="Название команды" placeholder="Hackathon Team"/>
          <Field label="Пароль" type="password" placeholder="минимум 8 символов" autoComplete="new-password"/>
          <button className="gc-btn gc-btn--primary gc-btn--lg gc-btn--block" type="submit">Зарегистрироваться</button>
        </form>
        <p className="gc-form-meta">Уже есть аккаунт? <a onClick={() => go('/login')}>Войти</a></p>
      </div>
    </div>
  </div>
);

Object.assign(window, { LoginPage, RegisterPage });

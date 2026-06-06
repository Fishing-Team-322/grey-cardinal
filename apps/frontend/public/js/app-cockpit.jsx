// Grey Cardinal — v2 cockpit (director / manager / employee), полностью на /api/*.

const card = { background:'var(--rf-bg-2,#15171c)', border:'1px solid var(--rf-line,#262a31)', borderRadius:12, padding:18, marginBottom:16 };
const lbl = { display:'block', fontSize:12, color:'var(--rf-fg-3,#8b94a3)', margin:'10px 0 4px' };
const row = { display:'flex', gap:10, flexWrap:'wrap', alignItems:'center' };

const Notice = ({ kind='info', children }) => {
  const colors = { info:'#3b82c4', ok:'#3da37a', err:'#e23a52', warn:'#d68b1c' };
  return <div style={{ borderLeft:`3px solid ${colors[kind]}`, background:'rgba(255,255,255,.03)', padding:'8px 12px', borderRadius:6, fontSize:13, margin:'8px 0' }}>{children}</div>;
};

const TextInput = ({ value, onChange, ...rest }) => (
  <input className="gc-input" value={value} onChange={(e) => onChange(e.target.value)} {...rest}/>
);

const useAsync = (fn, deps = []) => {
  const [state, setState] = React.useState({ loading:true, data:null, error:null });
  const reload = React.useCallback(() => {
    setState((s) => ({ ...s, loading:true }));
    fn().then((data) => setState({ loading:false, data, error:null }))
        .catch((error) => setState({ loading:false, data:null, error }));
  }, deps);
  React.useEffect(() => { reload(); }, [reload]);
  return { ...state, reload };
};

// ── Onboarding: создать компанию ────────────────────────────────────────────
const OnboardingCreateCompany = ({ onDone }) => {
  const [name, setName] = React.useState('');
  const [tz, setTz] = React.useState(gcGuessTimezone());
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState('');
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr('');
    try { await GCApi.createCompany({ name: name.trim(), timezone: tz.trim() }); onDone(); }
    catch (ex) { setErr(ex.message); setBusy(false); }
  };
  return (
    <div style={{ maxWidth:520, margin:'40px auto' }}>
      <h2 className="gc-display-4">Создайте компанию</h2>
      <p className="gc-mute">Вы станете директором. Часовой пояс компании используется для дедлайнов и созвонов.</p>
      <form onSubmit={submit} style={card}>
        <label style={lbl}>Название компании</label>
        <TextInput value={name} onChange={setName} placeholder="ООО Рога и Копыта"/>
        <label style={lbl}>Часовой пояс (IANA)</label>
        <TextInput value={tz} onChange={setTz} placeholder="Europe/Moscow"/>
        {err && <Notice kind="err">{err}</Notice>}
        <div style={{ marginTop:14 }}>
          <button className="gc-btn gc-btn--primary" disabled={busy || !name.trim()}>{busy ? 'Создаём…' : 'Создать компанию'}</button>
        </div>
      </form>
    </div>
  );
};

// ── ПК-агент (трей): токен привязки ─────────────────────────────────────────
const AgentCard = () => {
  const [token, setToken] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const get = async () => {
    setBusy(true);
    try {
      const r = await GCApi.agentToken();
      setToken(r.token);
      try { await navigator.clipboard.writeText(r.token); } catch (_) {}
    } finally { setBusy(false); }
  };
  return (
    <div style={card}>
      <h3>ПК-агент (запись созвонов)</h3>
      <p className="gc-mute" style={{ fontSize:13 }}>
        Скачайте агента на странице <a href="#/download">Загрузка</a>, запустите его (появится в трее),
        получите токен ниже и вставьте его в config агента (меню трея → «Вставить токен» → строка <code>agent_token</code>).
      </p>
      <button className="gc-btn gc-btn--primary gc-btn--sm" onClick={get} disabled={busy}>
        {busy ? '…' : 'Получить токен агента'}
      </button>
      {token && <Notice kind="ok">Токен (скопирован):<br/><code style={{ wordBreak:'break-all' }}>{token}</code></Notice>}
      <p className="gc-mute" style={{ fontSize:12 }}>
        Голос с агента → распознавание → задача появится в Telegram-чате вашей команды с кнопкой «Создать карточку».
      </p>
    </div>
  );
};

// ── Профиль: привязка Telegram ──────────────────────────────────────────────
const ProfilePanel = ({ user }) => {
  const st = useAsync(() => GCApi.telegramStatus(), []);
  const [link, setLink] = React.useState(null);
  const [busy, setBusy] = React.useState(false);
  const start = async () => { setBusy(true); try { setLink(await GCApi.telegramLinkStart()); } finally { setBusy(false); } st.reload(); };
  const unlink = async () => { await GCApi.telegramUnlink(); setLink(null); st.reload(); };
  return (
    <div>
      <h2 className="gc-display-4">Профиль</h2>
      <div style={card}>
        <div style={row}><b>{user.display_name}</b> <span className="gc-mute">{user.email}</span></div>
      </div>
      <div style={card}>
        <h3>Telegram</h3>
        {st.loading ? <span className="gc-mute">Загрузка…</span> : st.data && st.data.linked
          ? <Notice kind="ok">Привязан: @{st.data.telegram_username || st.data.telegram_user_id} <a style={{ marginLeft:10, cursor:'pointer' }} onClick={unlink}>отвязать</a></Notice>
          : <>
              <Notice kind="warn">Telegram не привязан. Бот не сможет вас распознать в чате.</Notice>
              <button className="gc-btn gc-btn--primary" onClick={start} disabled={busy}>{busy ? '…' : 'Привязать Telegram'}</button>
              {link && <Notice kind="info">
                Откройте ссылку и нажмите Start: <a href={link.deep_link} target="_blank" rel="noreferrer">{link.deep_link}</a><br/>
                Код: <code>{link.code}</code> (действует до {gcFormatDateTime(link.expires_at)})
              </Notice>}
            </>}
      </div>
      <AgentCard/>
    </div>
  );
};

// ── Директор: обзор компании + команды + инвайты ────────────────────────────
const InviteButton = ({ companyId, teamId, role }) => {
  const [token, setToken] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const create = async () => {
    setBusy(true);
    try {
      const res = await GCApi.createInvite(companyId, { scope:'team', team_id:teamId, role, expires_hours:72 });
      const url = `${window.location.origin}/#/i/${res.token}`;
      setToken(url);
      try { await navigator.clipboard.writeText(url); } catch (_) {}
    } finally { setBusy(false); }
  };
  return (
    <span>
      <button className="gc-btn gc-btn--ghost gc-btn--sm" onClick={create} disabled={busy}>+ инвайт {role === 'manager' ? 'руководителя' : 'сотрудника'}</button>
      {token && <Notice kind="ok">Ссылка (скопирована): <a href={token}>{token}</a></Notice>}
    </span>
  );
};

const DirectorOverview = ({ company, onOpenTeam }) => {
  const ov = useAsync(() => GCApi.companyOverview(company.id), [company.id]);
  const [newTeam, setNewTeam] = React.useState('');
  const createTeam = async () => { if (!newTeam.trim()) return; await GCApi.createTeam(company.id, { name:newTeam.trim() }); setNewTeam(''); ov.reload(); };
  if (ov.loading) return <span className="gc-mute">Загрузка обзора…</span>;
  if (ov.error) return <Notice kind="err">{ov.error.message}</Notice>;
  const d = ov.data;
  return (
    <div>
      <h2 className="gc-display-4">{d.company.name}</h2>
      <p className="gc-mute">Часовой пояс: {d.company.timezone}</p>
      <div style={{ ...row, marginBottom:8 }}>
        {[['Команд', d.totals.teams], ['Открытых задач', d.totals.open_tasks], ['Просрочено', d.totals.overdue_tasks], ['Закрыто за 7 дней', d.totals.completed_last_7_days]].map(([k,v]) => (
          <div key={k} style={{ ...card, flex:'1 1 160px', marginBottom:0 }}><div className="gc-mute" style={{ fontSize:12 }}>{k}</div><div style={{ fontSize:26, fontWeight:700 }}>{v}</div></div>
        ))}
      </div>
      {d.hotspots && d.hotspots.length > 0 && d.hotspots.map((h, i) => <Notice key={i} kind="warn">{h.message}</Notice>)}
      <div style={card}>
        <h3>Команды</h3>
        {d.teams.length === 0 && <p className="gc-mute">Команд пока нет.</p>}
        {d.teams.map((t) => (
          <div key={t.id} style={{ ...row, justifyContent:'space-between', borderBottom:'1px solid var(--rf-line,#262a31)', padding:'10px 0' }}>
            <div>
              <a style={{ cursor:'pointer', fontWeight:600 }} onClick={() => onOpenTeam(t.id)}>{t.name}</a>
              <span className="gc-mute" style={{ marginLeft:10, fontSize:12 }}>участников: {t.members_count} · открыто: {t.open_tasks} · просрочено: {t.overdue_tasks}</span>
            </div>
            <div style={row}>
              <InviteButton companyId={company.id} teamId={t.id} role="manager"/>
              <InviteButton companyId={company.id} teamId={t.id} role="employee"/>
            </div>
          </div>
        ))}
        <div style={{ ...row, marginTop:14 }}>
          <TextInput value={newTeam} onChange={setNewTeam} placeholder="Новая команда" style={{ maxWidth:240 }}/>
          <button className="gc-btn gc-btn--primary gc-btn--sm" onClick={createTeam}>Создать команду</button>
        </div>
      </div>
    </div>
  );
};

// ── Команда: Telegram / Board / LLM / Meetings / Sync ───────────────────────
const TeamPanel = ({ teamId }) => {
  const team = useAsync(() => GCApi.getTeam(teamId), [teamId]);
  const [tab, setTab] = React.useState('telegram');
  if (team.loading) return <span className="gc-mute">Загрузка команды…</span>;
  if (team.error) return <Notice kind="err">{team.error.message}</Notice>;
  const t = team.data;
  const isManager = t.role === 'manager';
  const tabs = [['telegram','Telegram'], ['board','YouGile'], ['llm','LLM'], ['meetings','Созвоны'], ['sync','Синк']];
  return (
    <div>
      <h2 className="gc-display-4">{t.name}</h2>
      <p className="gc-mute">Роль: {t.role} · TZ: {t.timezone}</p>
      <div style={{ ...row, marginBottom:14 }}>
        {tabs.map(([k,v]) => <button key={k} className={'gc-btn gc-btn--sm ' + (tab===k?'gc-btn--primary':'gc-btn--ghost')} onClick={() => setTab(k)}>{v}</button>)}
      </div>
      {tab==='telegram' && <TeamTelegram teamId={teamId} isManager={isManager}/>}
      {tab==='board' && <TeamBoard teamId={teamId} isManager={isManager}/>}
      {tab==='llm' && <TeamLLM teamId={teamId} isManager={isManager}/>}
      {tab==='meetings' && <TeamMeetings teamId={teamId} timezone={t.timezone}/>}
      {tab==='sync' && <TeamSync teamId={teamId} isManager={isManager}/>}
    </div>
  );
};

const TeamTelegram = ({ teamId, isManager }) => {
  const st = useAsync(() => GCApi.teamTelegramStatus(teamId), [teamId]);
  const [code, setCode] = React.useState(null);
  const gen = async () => { setCode(await GCApi.teamBindCode(teamId)); st.reload(); };
  return (
    <div style={card}>
      <h3>Привязка чата команды</h3>
      {st.loading ? <span className="gc-mute">…</span> : st.data && st.data.linked
        ? <Notice kind="ok">Чат привязан (tg_chat_id: {st.data.tg_chat_id})</Notice>
        : <Notice kind="warn">Чат не привязан.</Notice>}
      {isManager && <>
        <ol style={{ fontSize:13, color:'var(--rf-fg-3,#8b94a3)' }}>
          <li>Добавьте бота @grey_cxrdinxl_bot в Telegram-группу.</li>
          <li>В группе выполните <code>/bind_team КОД</code>.</li>
          <li>Дождитесь статуса «чат привязан».</li>
        </ol>
        <button className="gc-btn gc-btn--primary gc-btn--sm" onClick={gen}>Сгенерировать код привязки</button>
        {code && <Notice kind="info">Код: <code style={{ fontSize:18 }}>{code.code}</code> (до {gcFormatDateTime(code.expires_at)})</Notice>}
      </>}
    </div>
  );
};

const TeamBoard = ({ teamId, isManager }) => {
  const st = useAsync(() => GCApi.yougileStatus(teamId), [teamId]);
  const projects = useAsync(
    () => st.data && st.data.connected ? GCApi.yougileProjects(teamId) : Promise.resolve([]),
    [teamId, st.data && st.data.connected, st.data && st.data.last_synced_at]
  );
  const [login, setLogin] = React.useState('');
  const [password, setPassword] = React.useState('');
  const [onboarding, setOnboarding] = React.useState(null);
  const [companyId, setCompanyId] = React.useState('');
  const [projectId, setProjectId] = React.useState('');
  const [msg, setMsg] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const startLogin = async () => {
    setBusy(true); setMsg('');
    const submittedPassword = password;
    setPassword('');
    try {
      const result = await GCApi.yougileLogin(teamId, { login, password:submittedPassword });
      setOnboarding(result);
      setCompanyId(result.companies.length === 1 ? result.companies[0].id : '');
    } catch (ex) { setMsg(ex.message); }
    finally { setBusy(false); }
  };
  const connect = async () => {
    setBusy(true); setMsg('');
    try {
      await GCApi.yougileConnect(teamId, {
        onboarding_token:onboarding.onboarding_token,
        company_id:companyId,
      });
      setOnboarding(null); setMsg('Синхронизация запущена'); st.reload();
    } catch (ex) { setMsg(ex.message); }
    finally { setBusy(false); }
  };
  const refresh = async () => {
    setBusy(true); setMsg('');
    try { await GCApi.yougileSync(teamId); setMsg('Синхронизация запущена'); }
    catch (ex) { setMsg(ex.message); }
    finally { setBusy(false); }
  };
  const choosePrimary = async () => {
    setBusy(true); setMsg('');
    try { await GCApi.yougileSetPrimary(teamId, projectId); setMsg('Основной проект выбран'); st.reload(); }
    catch (ex) { setMsg(ex.message); }
    finally { setBusy(false); }
  };
  const disconnect = async () => {
    setBusy(true); setMsg('');
    try { await GCApi.yougileDisconnect(teamId); setOnboarding(null); st.reload(); }
    catch (ex) { setMsg(ex.message); }
    finally { setBusy(false); }
  };
  const connected = st.data && st.data.connected;
  return (
    <div style={card}>
      <h3>YouGile</h3>
      {!st.loading && <Notice kind={connected?'ok':'warn'}>
        {connected
          ? `Подключено: ${st.data.company && st.data.company.name || 'YouGile'}`
          : st.data && st.data.reconnect_required ? 'Нужно переподключить YouGile' : 'Не подключено'}
      </Notice>}
      {connected && <>
        <div className="gc-mute" style={{ fontSize:13 }}>
          Последняя синхронизация: {st.data.last_synced_at ? gcFormatDateTime(st.data.last_synced_at) : 'в процессе'}
        </div>
        {st.data.primary_project && <div className="gc-mute" style={{ fontSize:13 }}>
          Основной проект: {st.data.primary_project.name}
        </div>}
        {isManager && projects.data && projects.data.length > 0 && <>
          <label style={lbl}>Основной проект</label>
          <select className="gc-input" value={projectId || (st.data.primary_project && st.data.primary_project.id) || ''} onChange={(e) => setProjectId(e.target.value)}>
            <option value="">Выберите проект</option>
            {projects.data.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
          </select>
        </>}
        {isManager && <div style={{ ...row, marginTop:12 }}>
          {projects.data && projects.data.length > 0 && <button className="gc-btn gc-btn--primary gc-btn--sm" onClick={choosePrimary} disabled={busy || !projectId}>Выбрать</button>}
          <button className="gc-btn gc-btn--ghost gc-btn--sm" onClick={refresh} disabled={busy}>Обновить</button>
          <button className="gc-btn gc-btn--ghost gc-btn--sm" onClick={disconnect} disabled={busy}>Отключить</button>
        </div>}
      </>}
      {isManager && !connected && !onboarding && <>
        <label style={lbl}>Email YouGile</label>
        <TextInput value={login} onChange={setLogin} autoComplete="username"/>
        <label style={lbl}>Пароль YouGile</label>
        <TextInput value={password} onChange={setPassword} type="password" autoComplete="current-password"/>
        <div style={{ marginTop:12 }}>
          <button className="gc-btn gc-btn--primary gc-btn--sm" onClick={startLogin} disabled={busy || !login || !password}>Продолжить</button>
        </div>
      </>}
      {isManager && !connected && onboarding && <>
        <label style={lbl}>Компания YouGile</label>
        <select className="gc-input" value={companyId} onChange={(e) => setCompanyId(e.target.value)}>
          <option value="">Выберите компанию</option>
          {onboarding.companies.map((company) => <option key={company.id} value={company.id}>{company.name}</option>)}
        </select>
        <div style={{ ...row, marginTop:12 }}>
          <button className="gc-btn gc-btn--primary gc-btn--sm" onClick={connect} disabled={busy || !companyId}>Подключить</button>
          <button className="gc-btn gc-btn--ghost gc-btn--sm" onClick={() => setOnboarding(null)} disabled={busy}>Назад</button>
        </div>
      </>}
      {msg && <Notice kind={msg.includes('запущена') || msg.includes('выбран')?'ok':'err'}>{msg}</Notice>}
    </div>
  );
};

const TeamLLM = ({ teamId, isManager }) => {
  const [f, setF] = React.useState({ provider:'local', base_url:'http://ollama:11434/v1', model:'qwen2.5:7b', api_key:'' });
  const [msg, setMsg] = React.useState('');
  const [health, setHealth] = React.useState(null);
  const upd = (k) => (v) => setF((s) => ({ ...s, [k]: v }));
  const save = async () => { setMsg(''); try { await GCApi.setLLM(teamId, f); setMsg('Сохранено'); } catch (ex) { setMsg(ex.message); } };
  const check = async () => { setHealth({ status:'…' }); try { setHealth(await GCApi.llmHealth(teamId)); } catch (ex) { setHealth({ status:'error', message:ex.message }); } };
  return (
    <div style={card}>
      <h3>LLM</h3>
      {isManager ? <>
        <label style={lbl}>Провайдер</label>
        <select className="gc-input" value={f.provider} onChange={(e) => upd('provider')(e.target.value)}>
          <option value="local">local (ollama)</option><option value="external_api">external_api</option>
        </select>
        <label style={lbl}>Base URL</label><TextInput value={f.base_url} onChange={upd('base_url')}/>
        <label style={lbl}>Модель</label><TextInput value={f.model} onChange={upd('model')}/>
        {f.provider==='external_api' && <><label style={lbl}>API ключ</label><TextInput value={f.api_key} onChange={upd('api_key')}/></>}
        {msg && <Notice kind={msg==='Сохранено'?'ok':'err'}>{msg}</Notice>}
        <div style={{ ...row, marginTop:12 }}>
          <button className="gc-btn gc-btn--primary gc-btn--sm" onClick={save}>Сохранить</button>
          <button className="gc-btn gc-btn--ghost gc-btn--sm" onClick={check}>Проверить LLM</button>
        </div>
        {health && <Notice kind={health.status==='ok'?'ok':'err'}>LLM: {health.status} {health.model?`(${health.model}, ${health.latency_ms}ms)`:''} {health.message||''}</Notice>}
      </> : <span className="gc-mute">Только руководитель команды.</span>}
    </div>
  );
};

const TeamMeetings = ({ teamId, timezone }) => {
  const ms = useAsync(() => GCApi.listMeetings(teamId), [teamId]);
  const [title, setTitle] = React.useState('Созвон');
  const [when, setWhen] = React.useState('');
  const create = async () => {
    if (!when) return;
    await GCApi.createMeeting(teamId, { title, scheduled_at:new Date(when).toISOString(), duration_minutes:60 });
    setWhen(''); ms.reload();
  };
  const act = async (fn) => { await fn(); ms.reload(); };
  return (
    <div style={card}>
      <h3>Созвоны</h3>
      <div style={{ ...row, marginBottom:12 }}>
        <TextInput value={title} onChange={setTitle} placeholder="Название" style={{ maxWidth:180 }}/>
        <input className="gc-input" type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} style={{ maxWidth:220 }}/>
        <button className="gc-btn gc-btn--primary gc-btn--sm" onClick={create}>Создать</button>
      </div>
      {ms.loading ? <span className="gc-mute">…</span> : (ms.data.items || []).length === 0 ? <p className="gc-mute">Созвонов нет.</p> :
        (ms.data.items || []).map((m) => (
          <div key={m.id} style={{ ...row, justifyContent:'space-between', borderBottom:'1px solid var(--rf-line,#262a31)', padding:'8px 0' }}>
            <span>{m.public_id} · {m.title} · <b>{m.state}</b> · {gcFormatDateTime(m.scheduled_at)}</span>
            <span style={row}>
              <button className="gc-btn gc-btn--ghost gc-btn--sm" onClick={() => act(() => GCApi.confirmMeeting(m.id))}>Подтвердить</button>
              <button className="gc-btn gc-btn--ghost gc-btn--sm" onClick={() => act(() => GCApi.rsvpMeeting(m.id, 'yes'))}>Приду</button>
              <button className="gc-btn gc-btn--ghost gc-btn--sm" onClick={() => act(() => GCApi.cancelMeeting(m.id))}>Отмена</button>
            </span>
          </div>
        ))}
    </div>
  );
};

const TeamSync = ({ teamId, isManager }) => {
  const st = useAsync(() => GCApi.syncStatus(teamId), [teamId]);
  const act = async (fn) => { await fn(); st.reload(); };
  return (
    <div style={card}>
      <h3>Вечерний синк</h3>
      {st.loading ? <span className="gc-mute">…</span> : <Notice kind={st.data.open?'ok':'info'}>{st.data.open ? 'Синк открыт' : 'Синк закрыт'}</Notice>}
      {isManager && <div style={row}>
        <button className="gc-btn gc-btn--primary gc-btn--sm" onClick={() => act(() => GCApi.syncStart(teamId))}>Открыть синк</button>
        <button className="gc-btn gc-btn--ghost gc-btn--sm" onClick={() => act(() => GCApi.syncClose(teamId))}>Закрыть синк</button>
      </div>}
    </div>
  );
};

// ── Корневой dashboard ──────────────────────────────────────────────────────
const NavItem = ({ active, onClick, children }) => (
  <div onClick={onClick} style={{ cursor:'pointer', padding:'7px 10px', borderRadius:7, fontSize:14, margin:'2px 0', background: active ? 'rgba(226,58,82,.14)' : 'transparent', color: active ? '#fff' : 'var(--rf-fg-2,#c7cdd6)' }}>{children}</div>
);

const AppDashboardPage = ({ go }) => {
  const me = useAsync(() => GCApi.me(), []);
  const [view, setView] = React.useState({ kind:'home' });
  const triedTg = React.useRef(false);

  React.useEffect(() => {
    const tg = window.Telegram && window.Telegram.WebApp;
    if (tg) { try { tg.ready(); tg.expand(); } catch (_) {} }
  }, []);

  React.useEffect(() => {
    if (!(me.error && me.error.status === 401)) return;
    const tg = window.Telegram && window.Telegram.WebApp;
    if (tg && tg.initData && !triedTg.current) {
      // Открыто как Telegram Mini App — авто-вход по подписи initData.
      triedTg.current = true;
      GCApi.telegramWebappAuth(tg.initData).then(() => me.reload()).catch(() => go('/login'));
    } else {
      go('/login');
    }
  }, [me.error]);

  if (me.loading) return <div style={{ padding:40 }} className="gc-mute">Загрузка…</div>;
  if (me.error) return <div style={{ padding:40 }}><Notice kind="err">{me.error.message}</Notice><button className="gc-btn" onClick={() => go('/login')}>Войти</button></div>;

  const data = me.data;
  const companies = data.companies || [];
  const teams = data.teams || [];
  const noOrg = companies.length === 0 && teams.length === 0;

  if (noOrg) return <OnboardingCreateCompany onDone={() => me.reload()}/>;

  const logout = async () => { await GCApi.logout(); go('/login'); };

  return (
    <div style={{ display:'flex', minHeight:'100vh', background:'var(--rf-bg-1,#0e0f13)', color:'var(--rf-fg-1,#e8ebf0)' }}>
      <aside style={{ width:248, borderRight:'1px solid var(--rf-line,#262a31)', padding:18, flexShrink:0 }}>
        <div style={{ ...row, marginBottom:18 }}><Logo size={26}/></div>
        <div style={{ fontSize:11, color:'var(--rf-fg-4,#5a626f)', textTransform:'uppercase', margin:'8px 0' }}>Аккаунт</div>
        <NavItem active={view.kind==='profile'} onClick={() => setView({ kind:'profile' })}>Профиль · Telegram</NavItem>
        {companies.length > 0 && <>
          <div style={{ fontSize:11, color:'var(--rf-fg-4,#5a626f)', textTransform:'uppercase', margin:'14px 0 8px' }}>Компании</div>
          {companies.map((c) => <NavItem key={c.id} active={view.kind==='company' && view.id===c.id} onClick={() => setView({ kind:'company', id:c.id })}>{c.name} <span className="gc-mute">({c.role})</span></NavItem>)}
        </>}
        <div style={{ fontSize:11, color:'var(--rf-fg-4,#5a626f)', textTransform:'uppercase', margin:'14px 0 8px' }}>Команды</div>
        {teams.length === 0 && <span className="gc-mute" style={{ fontSize:12 }}>нет команд</span>}
        {teams.map((t) => <NavItem key={t.id} active={view.kind==='team' && view.id===t.id} onClick={() => setView({ kind:'team', id:t.id })}>{t.name} <span className="gc-mute">({t.role})</span></NavItem>)}
        <div style={{ marginTop:24 }}>
          <a className="gc-mute" style={{ cursor:'pointer', fontSize:13 }} onClick={logout}>Выйти</a>
        </div>
      </aside>
      <main style={{ flex:1, padding:'28px 32px', maxWidth:900 }}>
        {view.kind==='home' && <div className="gc-mute">Выберите раздел слева. {companies.length>0 ? 'Откройте компанию, чтобы создать команды и инвайты.' : 'Откройте команду или профиль.'}</div>}
        {view.kind==='profile' && <ProfilePanel user={data.user}/>}
        {view.kind==='company' && <DirectorOverview company={companies.find((c) => c.id===view.id)} onOpenTeam={(id) => setView({ kind:'team', id })}/>}
        {view.kind==='team' && <TeamPanel teamId={view.id}/>}
      </main>
    </div>
  );
};

// ── Приём инвайта (#/i/<token>) ─────────────────────────────────────────────
const InviteAcceptPage = ({ go, token }) => {
  const inv = useAsync(() => GCApi.getInvite(token), [token]);
  const [msg, setMsg] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const accept = async () => {
    setBusy(true); setMsg('');
    try { await GCApi.acceptInvite(token); sessionStorage.removeItem('gc.pendingInvite'); go('/app'); }
    catch (ex) {
      if (ex.status === 401) { sessionStorage.setItem('gc.pendingInvite', token); go('/login'); return; }
      setMsg(ex.message); setBusy(false);
    }
  };
  return (
    <div style={{ maxWidth:520, margin:'60px auto' }}>
      <h2 className="gc-display-4">Приглашение в команду</h2>
      {inv.loading ? <span className="gc-mute">Загрузка…</span> : inv.error ? <Notice kind="err">{inv.error.message}</Notice> :
        inv.data.expired ? <Notice kind="err">Приглашение истекло.</Notice> :
        <div style={card}>
          <p>Роль: <b>{inv.data.role}</b></p>
          {msg && <Notice kind="err">{msg}</Notice>}
          <button className="gc-btn gc-btn--primary" onClick={accept} disabled={busy}>{busy ? '…' : 'Принять приглашение'}</button>
          <p className="gc-mute" style={{ fontSize:12, marginTop:8 }}>Нужен вход в аккаунт. Если вы не вошли — откроется страница входа, потом вернётесь сюда.</p>
        </div>}
    </div>
  );
};

Object.assign(window, { AppDashboardPage, InviteAcceptPage });

// Grey Cardinal — Telegram Mini App: настройки бота (без кабинета).
// Открывается из меню бота. Авто-вход по initData. Только настройки + тумблеры.

const TG = () => (typeof window !== 'undefined' && window.Telegram && window.Telegram.WebApp) || null;

const tgTheme = () => {
  const p = (TG() && TG().themeParams) || {};
  return {
    bg: p.bg_color || '#0e0f13',
    card: p.secondary_bg_color || '#171a21',
    text: p.text_color || '#e8ebf0',
    hint: p.hint_color || '#8b94a3',
    accent: p.button_color || '#e23a52',
    line: '#2a2f37',
  };
};

const DIGEST_MODES = [
  ['off', 'Выкл'],
  ['morning', 'Утром'],
  ['evening', 'Вечером'],
  ['both', '2 раза'],
  ['thrice', '3 раза'],
];

const Switch = ({ on, onChange, c }) => (
  <div
    onClick={() => onChange(!on)}
    style={{
      width: 48, height: 28, borderRadius: 14, flexShrink: 0, cursor: 'pointer',
      background: on ? (c.accent) : '#4b515c', transition: 'background .15s', position: 'relative',
    }}
  >
    <div style={{
      position: 'absolute', top: 3, left: on ? 23 : 3, width: 22, height: 22,
      borderRadius: '50%', background: '#fff', transition: 'left .15s',
      boxShadow: '0 1px 3px rgba(0,0,0,.4)',
    }}/>
  </div>
);

const Row = ({ title, sub, right, c }) => (
  <div style={{
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    gap: 14, padding: '14px 0', borderBottom: `1px solid ${c.line}`,
  }}>
    <div>
      <div style={{ fontSize: 15, color: c.text }}>{title}</div>
      {sub && <div style={{ fontSize: 12, color: c.hint, marginTop: 3 }}>{sub}</div>}
    </div>
    {right}
  </div>
);

const Card = ({ title, children, c }) => (
  <div style={{ background: c.card, borderRadius: 16, padding: '6px 16px', margin: '14px 0' }}>
    {title && <div style={{ fontSize: 12, color: c.hint, textTransform: 'uppercase', letterSpacing: .5, padding: '12px 0 2px' }}>{title}</div>}
    {children}
  </div>
);

const BotSettingsPage = () => {
  const c = tgTheme();
  const [state, setState] = React.useState({ loading: true, error: null });
  const [teams, setTeams] = React.useState([]);
  const [teamId, setTeamId] = React.useState(null);
  const [s, setS] = React.useState(null);       // settings
  const [hoursStr, setHoursStr] = React.useState('');
  const [saving, setSaving] = React.useState(false);
  const [saved, setSaved] = React.useState(false);

  React.useEffect(() => {
    const tg = TG();
    if (tg) { try { tg.ready(); tg.expand(); } catch (_) {} }
    document.body.style.background = c.bg;
    const boot = async () => {
      try {
        let me;
        try { me = await GCApi.me(); }
        catch (e) {
          if (e.status === 401 && tg && tg.initData) {
            await GCApi.telegramWebappAuth(tg.initData);
            me = await GCApi.me();
          } else { throw e; }
        }
        const mgr = (me.teams || []).filter((t) => t.role === 'manager');
        const list = mgr.length ? mgr : (me.teams || []);
        if (!list.length) { setState({ loading: false, error: 'no_team' }); return; }
        setTeams(list);
        const tid = list[0].id;
        setTeamId(tid);
        const bs = await GCApi.getBotSettings(tid);
        setS(bs);
        setHoursStr((bs.digest_hours || []).join(', '));
        setState({ loading: false, error: null });
      } catch (e) {
        setState({ loading: false, error: e.status === 401 ? 'auth' : (e.message || 'error') });
      }
    };
    boot();
  }, []);

  const switchTeam = async (tid) => {
    setTeamId(tid);
    const bs = await GCApi.getBotSettings(tid);
    setS(bs); setHoursStr((bs.digest_hours || []).join(', '));
  };

  const save = async () => {
    setSaving(true); setSaved(false);
    const hours = hoursStr.split(/[,\s]+/).map((x) => parseInt(x, 10)).filter((n) => n >= 0 && n <= 23);
    try {
      const body = {
        digest_mode: s.digest_mode,
        digest_hours: hours.length ? hours : null,
        meeting_reminders: s.meeting_reminders,
        daemon_autorecord: s.daemon_autorecord,
      };
      const res = await GCApi.setBotSettings(teamId, body);
      setS(res); setHoursStr((res.digest_hours || []).join(', '));
      setSaved(true);
      const tg = TG(); if (tg) { try { tg.HapticFeedback.notificationOccurred('success'); } catch (_) {} }
    } catch (e) {
      setState((p) => ({ ...p, error: e.message }));
    } finally { setSaving(false); }
  };

  const wrap = { minHeight: '100vh', background: c.bg, color: c.text, fontFamily: 'system-ui, -apple-system, sans-serif', padding: '18px 16px 90px', maxWidth: 560, margin: '0 auto' };

  if (state.loading) return <div style={{ ...wrap, color: c.hint }}>Загрузка…</div>;
  if (state.error === 'no_team') return <div style={wrap}><h2>⚙️ Настройки бота</h2><p style={{ color: c.hint }}>Вы не состоите ни в одной команде.</p></div>;
  if (state.error === 'auth') return <div style={wrap}><h2>⚙️ Настройки бота</h2><p style={{ color: c.hint }}>Откройте эту страницу из меню Telegram-бота, либо привяжите Telegram в кабинете.</p></div>;
  if (state.error) return <div style={wrap}><h2>⚙️ Настройки бота</h2><p style={{ color: '#e23a52' }}>{state.error}</p></div>;

  return (
    <div style={wrap}>
      <h2 style={{ margin: '4px 0 2px', fontSize: 22 }}>⚙️ Настройки бота</h2>
      <div style={{ color: c.hint, fontSize: 13 }}>{s.team_name} · {s.timezone}</div>

      {teams.length > 1 && (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 12 }}>
          {teams.map((t) => (
            <button key={t.id} onClick={() => switchTeam(t.id)} style={{
              padding: '6px 12px', borderRadius: 10, border: 'none', cursor: 'pointer', fontSize: 13,
              background: t.id === teamId ? c.accent : c.card, color: t.id === teamId ? '#fff' : c.text,
            }}>{t.name}</button>
          ))}
        </div>
      )}

      <Card title="Дайджест задач" c={c}>
        <div style={{ padding: '12px 0' }}>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {DIGEST_MODES.map(([m, label]) => (
              <button key={m} onClick={() => setS({ ...s, digest_mode: m })} style={{
                padding: '8px 12px', borderRadius: 10, border: 'none', cursor: 'pointer', fontSize: 13,
                background: s.digest_mode === m ? c.accent : '#2a2f37',
                color: s.digest_mode === m ? '#fff' : c.text,
              }}>{label}</button>
            ))}
          </div>
          <div style={{ color: c.hint, fontSize: 12, marginTop: 8 }}>
            Когда присылать сводку активных задач команды в чат.
          </div>
        </div>
        <Row
          title="Свои часы (по таймзоне команды)"
          sub="Через запятую, напр. 9, 14, 19. Пусто — по режиму выше."
          c={c}
          right={(
            <input
              value={hoursStr}
              onChange={(e) => setHoursStr(e.target.value)}
              placeholder="9, 20"
              inputMode="numeric"
              style={{ width: 90, padding: '8px 10px', borderRadius: 10, border: `1px solid ${c.line}`, background: c.bg, color: c.text, textAlign: 'center' }}
            />
          )}
        />
      </Card>

      <Card title="Созвоны и даемон" c={c}>
        <Row
          title="Напоминать о созвоне"
          sub="Пинг участникам за ~5 минут до начала"
          c={c}
          right={<Switch on={!!s.meeting_reminders} onChange={(v) => setS({ ...s, meeting_reminders: v })} c={c}/>}
        />
        <Row
          title="Авто-запись даемоном"
          sub="ПК-агент пишет звук только во время созвонов"
          c={c}
          right={<Switch on={!!s.daemon_autorecord} onChange={(v) => setS({ ...s, daemon_autorecord: v })} c={c}/>}
        />
      </Card>

      <div style={{ position: 'fixed', left: 0, right: 0, bottom: 0, padding: 14, background: c.bg, borderTop: `1px solid ${c.line}` }}>
        <button onClick={save} disabled={saving} style={{
          width: '100%', maxWidth: 530, margin: '0 auto', display: 'block', padding: '14px',
          borderRadius: 12, border: 'none', cursor: 'pointer', fontSize: 16, fontWeight: 600,
          background: c.accent, color: '#fff', opacity: saving ? .6 : 1,
        }}>{saving ? 'Сохраняю…' : (saved ? 'Сохранено ✓' : 'Сохранить')}</button>
      </div>
    </div>
  );
};

Object.assign(window, { BotSettingsPage });

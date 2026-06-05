// Grey Cardinal - router + mount

const ROUTES = {
  '/':         (props) => <PublicHomePage {...props}/>,
  '/download': (props) => <DownloadPage {...props}/>,
  '/login':    (props) => <LoginPage {...props}/>,
  '/register': (props) => <RegisterPage {...props}/>,
  '/app':      (props) => <AppDashboardPage {...props}/>,
};

const rawHash = (hash) => {
  let h = (hash || '').replace(/^#/, '');
  if (!h) h = '/';
  if (h.length > 1 && h.endsWith('/')) h = h.slice(0, -1);
  return h;
};

const App = () => {
  const [route, setRoute] = React.useState(() => rawHash(window.location.hash));
  const [language, setLanguage] = React.useState(getInitialLanguage);

  React.useEffect(() => { saveLanguage(language); }, [language]);

  React.useEffect(() => {
    const onHash = () => { setRoute(rawHash(window.location.hash)); window.scrollTo(0, 0); };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const go = React.useCallback((path) => {
    const target = '#' + path;
    if (window.location.hash === target) window.scrollTo({ top: 0, behavior: 'smooth' });
    else window.location.hash = path;
  }, []);

  const props = { go, language, setLanguage };

  // Приём инвайта: #/i/<token>
  if (route.startsWith('/i/')) {
    return <InviteAcceptPage {...props} token={decodeURIComponent(route.slice(3))}/>;
  }
  const render = ROUTES[route] || ROUTES['/'];
  return render(props);
};

ReactDOM.createRoot(document.getElementById('root')).render(<App/>);

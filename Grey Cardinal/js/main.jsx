// Grey Cardinal — router + mount

const ROUTES = {
  '/':         (go) => <PublicHomePage go={go}/>,
  '/download': (go) => <DownloadPage go={go}/>,
  '/login':    (go) => <LoginPage go={go}/>,
  '/register': (go) => <RegisterPage go={go}/>,
  '/app':      (go) => <AppDashboardPage go={go}/>,
};

const normalize = (hash) => {
  let h = (hash || '').replace(/^#/, '');
  if (!h || h === '') h = '/';
  if (h.length > 1 && h.endsWith('/')) h = h.slice(0, -1);
  return ROUTES[h] ? h : '/';
};

const App = () => {
  const [route, setRoute] = React.useState(() => normalize(window.location.hash));

  React.useEffect(() => {
    const onHash = () => {
      setRoute(normalize(window.location.hash));
      window.scrollTo(0, 0);
    };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const go = React.useCallback((path) => {
    const target = '#' + path;
    if (window.location.hash === target) {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } else {
      window.location.hash = path;
    }
  }, []);

  return ROUTES[route](go);
};

ReactDOM.createRoot(document.getElementById('root')).render(<App/>);

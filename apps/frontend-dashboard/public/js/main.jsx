// Grey Cardinal - router + mount

const ROUTES = {
  '/':         (props) => <PublicHomePage {...props}/>,
  '/download': (props) => <DownloadPage {...props}/>,
  '/login':    (props) => <LoginPage {...props}/>,
  '/register': (props) => <RegisterPage {...props}/>,
  '/app':      (props) => <AppDashboardPage {...props}/>,
};

const normalize = (hash) => {
  let h = (hash || '').replace(/^#/, '');
  if (!h || h === '') h = '/';
  if (h.length > 1 && h.endsWith('/')) h = h.slice(0, -1);
  return ROUTES[h] ? h : '/';
};

const App = () => {
  const [route, setRoute] = React.useState(() => normalize(window.location.hash));
  const [language, setLanguage] = React.useState(getInitialLanguage);

  React.useEffect(() => {
    saveLanguage(language);
  }, [language]);

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

  return ROUTES[route]({ go, language, setLanguage });
};

ReactDOM.createRoot(document.getElementById('root')).render(<App/>);

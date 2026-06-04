// Grey Cardinal - shared icon set (Lucide-style, 1.6 stroke) + Logo + helpers
// Exposed on window for cross-file use.

const GC_ICON_PATHS = {
  ear:      'M6 8.5a6 6 0 0 1 12 0c0 3-1.5 4-2.5 5.2-.8 1-.5 2.3-.5 3.3a3 3 0 0 1-5.7 1.3M9 9a3 3 0 0 1 5 2.2',
  waves:    'M2 12h2l2-7 4 16 3-11 2 5h7',
  brain:    'M12 5a3 3 0 0 0-5.6-1.5A3 3 0 0 0 4 8a3 3 0 0 0 1 5.8A3 3 0 0 0 9 18a3 3 0 0 0 3 1.5M12 5a3 3 0 0 1 5.6-1.5A3 3 0 0 1 20 8a3 3 0 0 1-1 5.8A3 3 0 0 1 15 18a3 3 0 0 1-3 1.5M12 5v14.5',
  kanban:   'M5 3v14M12 3v9M19 3v6',
  alert:    'M10.3 4l-7 12A2 2 0 0 0 5 19h14a2 2 0 0 0 1.7-3l-7-12a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01',
  bell:     'M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9M13.7 21a2 2 0 0 1-3.4 0',
  send:     'M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z',
  check:    'M20 6L9 17l-5-5',
  checkCircle:'M22 11.1V12a10 10 0 1 1-5.9-9.1M22 4L12 14.1l-3-3',
  link:     'M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7',
  users:    'M17 21v-2a4 4 0 0 0-3-3.9M9 21v-2a4 4 0 0 1 3-3.9M16 3.1a4 4 0 0 1 0 7.8M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z',
  clock:    'M12 6v6l4 2M12 22a10 10 0 1 1 0-20 10 10 0 0 1 0 20z',
  history:  'M3 3v5h5M3.05 13A9 9 0 1 0 6 5.3L3 8M12 7v5l4 2',
  layers:   'M12 2l9 5-9 5-9-5 9-5zM3 12l9 5 9-5M3 17l9 5 9-5',
  shield:   'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z',
  lock:     'M19 11H5a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7a2 2 0 0 0-2-2zM7 11V7a5 5 0 0 1 10 0v4',
  server:   'M20 4H4a2 2 0 0 0-2 2v3a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2zM20 13H4a2 2 0 0 0-2 2v3a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2zM6 8h.01M6 17h.01',
  download: 'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3',
  arrowR:   'M5 12h14M13 5l7 7-7 7',
  arrowDown:'M12 5v14M5 12l7 7 7-7',
  chevR:    'M9 18l6-6-6-6',
  chevL:    'M15 18l-6-6 6-6',
  play:     'M5 3l14 9-14 9V3z',
  plus:     'M12 5v14M5 12h14',
  refresh:  'M23 4v6h-6M1 20v-6h6M3.5 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15',
  settings: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9c.36.15.66.4.88.71',
  grid:     'M3 3h7v9H3zM14 3h7v5h-7zM14 12h7v9h-7zM3 16h7v5H3z',
  list:     'M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01',
  plug:     'M9 2v6M15 2v6M6 8h12v3a6 6 0 0 1-12 0V8zM12 17v5',
  zap:      'M13 2L3 14h9l-1 8 10-12h-9l1-8z',
  windows:  'M3 5.7l7.5-1v7H3zM3 12.7h7.5v7L3 18.7zM11.5 4.5L21 3.2v8.5h-9.5zM11.5 12.7H21v8.5l-9.5-1.3z',
  apple:    'M16.5 12.3c0-2.4 2-3.5 2.1-3.6-1.1-1.7-2.9-1.9-3.5-1.9-1.5-.15-2.9 .88-3.65 .88-.75 0-1.9-.86-3.13-.84-1.6 .02-3.08 .93-3.9 2.37-1.67 2.9-.43 7.18 1.2 9.53 .8 1.15 1.74 2.44 2.98 2.4 1.2-.05 1.65-.77 3.1-.77 1.44 0 1.85 .77 3.12 .75 1.29-.02 2.1-1.17 2.89-2.33 .91-1.34 1.28-2.64 1.3-2.7-.03-.02-2.5-.96-2.52-3.8zM14.2 4.8c.67-.8 1.12-1.93 1-3.05-.96 .04-2.12 .64-2.8 1.45-.62 .71-1.16 1.85-1.02 2.94 1.07 .08 2.16-.54 2.82-1.34z',
  linux:    'M12 2c-1.5 0-2.5 1.4-2.5 3.2 0 1.1.2 1.7.2 2.6 0 .9-.7 1.6-1.4 2.8-.8 1.3-1.8 2.7-1.8 4.6 0 .7.2 1.3.5 1.7-.3.3-.5.7-.5 1.2 0 1 1 1.5 2.3 1.8 1 .25 1.6 .9 2.9 .9s1.9-.65 2.9-.9c1.3-.3 2.3-.8 2.3-1.8 0-.5-.2-.9-.5-1.2.3-.4.5-1 .5-1.7 0-1.9-1-3.3-1.8-4.6-.7-1.2-1.4-1.9-1.4-2.8 0-.9.2-1.5.2-2.6C14.5 3.4 13.5 2 12 2zM10.5 7.2c.4 0 .7.4.7.9s-.3.9-.7.9-.7-.4-.7-.9.3-.9.7-.9zm3 0c.4 0 .7.4.7.9s-.3.9-.7.9-.7-.4-.7-.9.3-.9.7-.9z',
  mail:     'M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2zM22 6l-10 7L2 6',
  eye:      'M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z',
  x:        'M18 6L6 18M6 6l12 12',
  target:   'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 18a6 6 0 1 0 0-12 6 6 0 0 0 0 12zM12 14a2 2 0 1 0 0-4 2 2 0 0 0 0 4z',
  dots:     'M12 5v.01M12 12v.01M12 19v.01',
};

const GC_CLOSED = { checkCircle: 0 };

const Icon = ({ name, size = 18, strokeWidth = 1.6, className = '', style }) => {
  const circles = {
    users: null,
  };
  const d = GC_ICON_PATHS[name] || '';
  // a few icons need explicit circles for closed shapes
  return (
    <svg className={className} style={style} width={size} height={size} viewBox="0 0 24 24"
         fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round">
      {name === 'target'
        ? (<><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/></>)
        : <path d={d}/>}
    </svg>
  );
};

// Brand logo - mark (inline SVG so it inherits crispness) + wordmark.
const GCMark = ({ size = 30 }) => (
  <svg width={size} height={size} viewBox="0 0 64 64" fill="none" aria-hidden="true">
    <rect x="1" y="1" width="62" height="62" rx="8" fill="#14161b" stroke="#2a2f38" strokeWidth="1.5"/>
    <g fill="#6c7280">
      <rect x="11.5" y="24" width="2.6" height="16" rx="1.3"/>
      <rect x="16.5" y="19" width="2.6" height="26" rx="1.3"/>
      <rect x="21.5" y="27" width="2.6" height="10" rx="1.3"/>
      <rect x="26.5" y="22" width="2.6" height="20" rx="1.3"/>
    </g>
    <line x1="33" y1="17" x2="33" y2="47" stroke="#c8253a" strokeWidth="2" strokeLinecap="round"/>
    <circle cx="33" cy="32" r="3" fill="#c8253a"/>
    <circle cx="33" cy="32" r="3" fill="none" stroke="#14161b" strokeWidth="1"/>
    <rect x="38.5" y="22.5" width="3" height="3" rx="0.6" fill="#c8253a"/>
    <rect x="44" y="22.5" width="9" height="3" rx="1.5" fill="#f4f5f7"/>
    <rect x="38.5" y="30.5" width="14.5" height="3" rx="1.5" fill="#d8dbe1"/>
    <rect x="38.5" y="38.5" width="11" height="3" rx="1.5" fill="#9aa0ad"/>
    <path d="M 7 7 H 12 M 7 7 V 12" stroke="#3a414c" strokeWidth="1.2"/>
    <path d="M 57 7 H 52 M 57 7 V 12" stroke="#3a414c" strokeWidth="1.2"/>
    <path d="M 7 57 H 12 M 7 57 V 52" stroke="#3a414c" strokeWidth="1.2"/>
    <path d="M 57 57 H 52 M 57 57 V 52" stroke="#3a414c" strokeWidth="1.2"/>
  </svg>
);

const Logo = ({ size = 30, onClick, sub = 'СЕРЫЙ КАРДИНАЛ' }) => (
  <div className="gc-logo" onClick={onClick}>
    <GCMark size={size}/>
    <div className="gc-logo-text">
      <div className="gc-logo-name">Grey Cardinal</div>
      {sub && <div className="gc-logo-sub">{sub}</div>}
    </div>
  </div>
);

// scroll-reveal hook - reveals on intersect, with viewport + safety fallbacks
const useReveal = () => {
  React.useEffect(() => {
    const els = [...document.querySelectorAll('.gc-reveal:not(.in)')];
    if (!els.length) return;

    const revealIfVisible = (el) => {
      const r = el.getBoundingClientRect();
      if (r.top < window.innerHeight * 0.92 && r.bottom > 0) { el.classList.add('in'); return true; }
      return false;
    };
    // anything already on screen at mount > reveal immediately
    els.forEach(revealIfVisible);

    if (!('IntersectionObserver' in window)) {
      els.forEach(e => e.classList.add('in'));
      return;
    }
    const io = new IntersectionObserver((entries) => {
      entries.forEach(e => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } });
    }, { threshold: 0, rootMargin: '0px 0px -6% 0px' });
    els.forEach(e => { if (!e.classList.contains('in')) io.observe(e); });

    // safety: if the observer never fires (some embedded contexts), reveal on scroll + a hard timeout
    const onScroll = () => els.forEach(e => { if (!e.classList.contains('in')) revealIfVisible(e); });
    window.addEventListener('scroll', onScroll, { passive: true });
    const t = setTimeout(() => els.forEach(e => e.classList.add('in')), 1600);

    return () => { io.disconnect(); window.removeEventListener('scroll', onScroll); clearTimeout(t); };
  }, []);
};

Object.assign(window, { Icon, GCMark, Logo, useReveal });


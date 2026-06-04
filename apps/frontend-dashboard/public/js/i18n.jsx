// Grey Cardinal - lightweight frontend language state.

const GC_LANGUAGE_STORAGE_KEY = 'gc.language';
const GC_SUPPORTED_LANGUAGES = ['ru', 'en'];

const normalizeLanguage = (value) => {
  const lang = String(value || '').toLowerCase().slice(0, 2);
  return GC_SUPPORTED_LANGUAGES.includes(lang) ? lang : 'ru';
};

const getInitialLanguage = () => {
  try {
    const saved = localStorage.getItem(GC_LANGUAGE_STORAGE_KEY);
    if (saved) return normalizeLanguage(saved);
  } catch (_) {}
  return 'ru';
};

const saveLanguage = (language) => {
  const next = normalizeLanguage(language);
  try {
    localStorage.setItem(GC_LANGUAGE_STORAGE_KEY, next);
  } catch (_) {}
  document.documentElement.lang = next;
  return next;
};

const copyText = (language, ru, en) => (normalizeLanguage(language) === 'ru' ? ru : en);

const LanguageToggle = ({ language, setLanguage, className = '' }) => {
  const current = normalizeLanguage(language);
  const choose = (next) => setLanguage(saveLanguage(next));
  return (
    <div className={'gc-lang-toggle ' + className} aria-label="Language switcher">
      {GC_SUPPORTED_LANGUAGES.map((lang) => (
        <button
          key={lang}
          type="button"
          className={current === lang ? 'active' : ''}
          aria-pressed={current === lang}
          onClick={() => choose(lang)}
        >
          {lang.toUpperCase()}
        </button>
      ))}
    </div>
  );
};

Object.assign(window, {
  GC_LANGUAGE_STORAGE_KEY,
  GC_SUPPORTED_LANGUAGES,
  normalizeLanguage,
  getInitialLanguage,
  saveLanguage,
  copyText,
  LanguageToggle,
});

function compile(pattern) {
  const keys = [];
  const source = pattern
    .replace(/\/+$/, "")
    .replace(/:[^/]+/g, (segment) => {
      keys.push(segment.slice(1));
      return "([^/]+)";
    });
  return { regex: new RegExp(`^${source || "/"}\\/?$`), keys };
}

function normalizePath(path) {
  return (path || "/").replace(/\/+$/, "") || "/";
}

function pathFromHref(href) {
  try {
    return normalizePath(new URL(href, location.origin).pathname);
  } catch {
    return "";
  }
}

function isNavItemActive(item, match, path) {
  const current = normalizePath(path);
  const pattern = item.dataset.route || "";
  if (pattern) {
    if (pattern === match.route.pattern) return true;
    if (compile(pattern).regex.test(current)) return true;
  }

  const hrefPath = pathFromHref(item.getAttribute("href") || "");
  if (hrefPath && hrefPath === current) return true;
  if (hrefPath === "/app/employee" && current === "/app/me") return true;
  if (hrefPath === "/app/meetings" && current.startsWith("/app/meetings/")) return true;
  return false;
}

export const Router = {
  routes: [],
  current: null,
  cleanup: null,
  cache: new Map(),

  register(pattern, partialPath, view, guard = null) {
    this.routes.push({ pattern, partialPath, view, guard, ...compile(pattern) });
  },

  reset() {
    this.cleanup?.();
    this.routes = [];
    this.current = null;
    this.cleanup = null;
    this.cache.clear();
  },

  start() {
    window.addEventListener("popstate", () => this._render());
    document.addEventListener("click", (event) => this._intercept(event));
    return this._render();
  },

  navigate(path, replace = false) {
    if (replace) history.replaceState({}, "", path);
    else history.pushState({}, "", path);
    return this._render();
  },

  highlightNav() {
    const match = this._matchRoute(location.pathname);
    document.querySelectorAll(".nav-item").forEach((item) => {
      item.classList.toggle("active", match ? isNavItemActive(item, match, location.pathname) : false);
    });
  },

  _intercept(event) {
    const link = event.target?.closest?.("a[href]");
    if (!link || link.target === "_blank" || event.defaultPrevented) return;
    const url = new URL(link.href, location.origin);
    if (url.origin !== location.origin || !url.pathname.startsWith("/app")) return;
    event.preventDefault();
    this.navigate(`${url.pathname}${url.search}${url.hash}`);
  },

  _matchRoute(path) {
    for (const route of this.routes) {
      const match = route.regex.exec(path.replace(/\/+$/, "") || "/");
      if (!match) continue;
      const params = Object.fromEntries(
        route.keys.map((key, index) => [key, decodeURIComponent(match[index + 1])]),
      );
      return { route, params };
    }
    return null;
  },

  async _render() {
    const match = this._matchRoute(location.pathname);
    const root = document.getElementById("view");
    if (!match) {
      root.innerHTML = '<div class="page"><div class="note warn">Страница не найдена.</div></div>';
      return;
    }
    const guardResult = match.route.guard ? await match.route.guard(match.params) : true;
    if (typeof guardResult === "string") return this.navigate(guardResult, true);
    if (!guardResult) return;

    this.cleanup?.();
    this.cleanup = null;
    root.innerHTML = '<div class="view-loading">Загрузка...</div>';
    let html = this.cache.get(match.route.partialPath);
    if (!html) {
      const response = await fetch(match.route.partialPath, { credentials: "include" });
      if (!response.ok) throw new Error(`Partial ${match.route.partialPath}: ${response.status}`);
      html = await response.text();
      this.cache.set(match.route.partialPath, html);
    }
    root.innerHTML = html;
    const query = Object.fromEntries(new URLSearchParams(location.search));
    const cleanup = await match.route.view(root, match.params, query);
    this.cleanup = typeof cleanup === "function" ? cleanup : null;
    this.current = {
      path: location.pathname,
      params: match.params,
      partial: match.route.partialPath,
      view: match.route.view,
    };
    document.querySelectorAll(".nav-item").forEach((item) => {
      item.classList.toggle("active", isNavItemActive(item, match, location.pathname));
    });
    window.scrollTo?.(0, 0);
  },
};

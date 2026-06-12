import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { Router } from "../js/router.js";

function browser(path = "/") {
  globalThis.location = { pathname: path, search: "", origin: "https://example.test" };
  globalThis.history = {
    pushState(_state, _title, next) { location.pathname = next; },
    replaceState(_state, _title, next) { location.pathname = next; },
  };
  globalThis.window = {
    addEventListener() {},
    scrollTo() {},
  };
}

test("register stores and matches parameterized route", () => {
  Router.reset();
  Router.register("/app/teams/:id", "/partials/manager.html", async () => {});
  assert.equal(Router.routes.length, 1);
  assert.deepEqual(Router._matchRoute("/app/teams/abc").params, { id: "abc" });
});

test("shell and views import the same router module instance", () => {
  const shellPath = fileURLToPath(new URL("../js/shell.js", import.meta.url));
  const shell = readFileSync(shellPath, "utf8");
  assert.match(shell, /from ["']\.\/router\.js["']/);
  assert.doesNotMatch(shell, /router\.js\?/);
});

test("navigate changes history without reload", async () => {
  browser("/");
  const previous = Router._render;
  Router._render = async () => {};
  await Router.navigate("/app/meetings");
  assert.equal(location.pathname, "/app/meetings");
  Router._render = previous;
});

test("intercept ignores external and target blank links", () => {
  browser("/app");
  let prevented = false;
  Router._intercept({
    defaultPrevented: false,
    target: { closest: () => ({ href: "https://other.test/app", target: "" }) },
    preventDefault() { prevented = true; },
  });
  assert.equal(prevented, false);
  Router._intercept({
    defaultPrevented: false,
    target: { closest: () => ({ href: "https://example.test/app", target: "_blank" }) },
    preventDefault() { prevented = true; },
  });
  assert.equal(prevented, false);
});

test("cleanup runs before route replacement", async () => {
  browser("/app/a");
  let cleaned = false;
  const root = { innerHTML: "" };
  globalThis.document = {
    getElementById: () => root,
    querySelectorAll: () => [],
  };
  globalThis.fetch = async () => new Response("<div>A</div>", { status: 200 });
  Router.reset();
  Router.register("/app/a", "/partials/a.html", async () => () => { cleaned = true; });
  Router.register("/app/b", "/partials/b.html", async () => {});
  await Router._render();
  location.pathname = "/app/b";
  await Router._render();
  assert.equal(cleaned, true);
});

test("sidebar active state matches parameterized nav routes", async () => {
  browser("/app/teams/team-1/board");
  const boardItem = navItem("/app/teams/:id/board", "/app/teams/team-1/board");
  const meetingsItem = navItem("/app/meetings", "/app/meetings");
  const root = { innerHTML: "" };
  globalThis.document = {
    getElementById: () => root,
    querySelectorAll: () => [boardItem, meetingsItem],
  };
  globalThis.fetch = async () => new Response("<div>Board</div>", { status: 200 });
  Router.reset();
  Router.register("/app/teams/:teamId/board", "/partials/board.html", async () => {});

  await Router._render();

  assert.equal(boardItem.active, true);
  assert.equal(meetingsItem.active, false);
});

test("sidebar active state maps /app/me to employee panel", async () => {
  browser("/app/me");
  const employeeItem = navItem("/app/employee", "/app/employee");
  const root = { innerHTML: "" };
  globalThis.document = {
    getElementById: () => root,
    querySelectorAll: () => [employeeItem],
  };
  globalThis.fetch = async () => new Response("<div>Me</div>", { status: 200 });
  Router.reset();
  Router.register("/app/me", "/partials/agentic.html", async () => {});

  await Router._render();

  assert.equal(employeeItem.active, true);
});

function navItem(route, href) {
  const item = {
    active: false,
    dataset: { route },
    getAttribute(name) {
      return name === "href" ? href : null;
    },
  };
  item.classList = {
    toggle(_className, value) {
      item.active = value;
    },
  };
  return item;
}

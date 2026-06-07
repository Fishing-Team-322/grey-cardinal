import test from "node:test";
import assert from "node:assert/strict";
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

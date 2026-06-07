import test from "node:test";
import assert from "node:assert/strict";
import { ApiError, request } from "../js/api.js";

test("request always includes credentials", async () => {
  let options;
  globalThis.fetch = async (_url, init) => {
    options = init;
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  await request("GET", "/api/health");
  assert.equal(options.credentials, "include");
});

test("ApiError preserves status and code", async () => {
  globalThis.fetch = async () => new Response(JSON.stringify({ error: "broken" }), {
    status: 422,
    headers: { "Content-Type": "application/json" },
  });
  await assert.rejects(
    request("GET", "/api/auth/test"),
    (error) => error instanceof ApiError && error.status === 422 && error.code === "broken",
  );
});

test("401 redirects non-auth calls to login", async () => {
  globalThis.location = { pathname: "/app/teams/abc", search: "?tab=x" };
  globalThis.window = { location: { href: "" } };
  globalThis.fetch = async () => new Response("{}", {
    status: 401,
    headers: { "Content-Type": "application/json" },
  });
  await assert.rejects(request("GET", "/api/me"), ApiError);
  assert.equal(
    window.location.href,
    "/login.html?next=%2Fapp%2Fteams%2Fabc%3Ftab%3Dx",
  );
});

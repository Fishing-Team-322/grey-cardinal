import test from "node:test";
import assert from "node:assert/strict";
import { ApiError, api, request } from "../js/api.js";

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

test("windows agent (daemon) API maps to the tenant-scoped agent endpoints", async () => {
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push(`${init.method} ${url}`);
    return new Response(JSON.stringify({ agents: [] }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  await api.daemon.pairingCode();
  await api.daemon.status();
  await api.daemon.unpair("dev-1");
  assert.deepEqual(calls, [
    "POST /api/agents/pairing-code",
    "GET /api/agents",
    "POST /api/agents/dev-1/unpair",
  ]);
});

test("yandex telemost API maps to the OAuth integration endpoints", async () => {
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push(`${init.method} ${url}`);
    return new Response(JSON.stringify({ ok: true, connected: false }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  await api.yandexTelemost.status("team-1");
  await api.yandexTelemost.connectStart("team-1");
  await api.yandexTelemost.disconnect("team-1");
  await api.yandexTelemost.testCreateRoom("team-1");
  assert.deepEqual(calls, [
    "GET /api/integrations/yandex-telemost/status?team_id=team-1",
    "POST /api/integrations/yandex-telemost/connect/start",
    "POST /api/integrations/yandex-telemost/disconnect",
    "POST /api/integrations/yandex-telemost/test-create-room",
  ]);
});

test("team bot settings API maps to the team settings endpoints", async () => {
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push(`${init.method} ${url}`);
    return new Response(JSON.stringify({ require_cardinal_mention: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  await api.teams.botSettings("team-1");
  await api.teams.saveBotSettings("team-1", { require_cardinal_mention: true });
  assert.deepEqual(calls, [
    "GET /api/teams/team-1/bot-settings",
    "PUT /api/teams/team-1/bot-settings",
  ]);
});

test("people profile API keeps the selected team context", async () => {
  let call;
  globalThis.fetch = async (url, init) => {
    call = `${init.method} ${url}`;
    return new Response(JSON.stringify({ user: {}, tasks: [] }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
  await api.people.profile("user-1", "team-1");
  assert.equal(call, "GET /api/users/me/profile?user_id=user-1&team_id=team-1");
});

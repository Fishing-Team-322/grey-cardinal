import test from "node:test";
import assert from "node:assert/strict";
import { guardFor, homeForUser, roleForUser } from "../js/auth.js";

test("director with one company opens its overview", () => {
  const user = { companies: [{ id: "c1", role: "director" }], teams: [] };
  assert.equal(roleForUser(user), "director");
  assert.equal(homeForUser(user), "/app/companies/c1");
});

test("manager opens the first managed team", () => {
  const user = {
    companies: [],
    teams: [{ id: "e1", role: "employee" }, { id: "m1", role: "manager" }],
  };
  assert.equal(roleForUser(user), "manager");
  assert.equal(homeForUser(user), "/app/teams/m1");
});

test("new user is sent to company onboarding", () => {
  assert.equal(homeForUser({ companies: [], teams: [] }), "/app/companies");
});

test("employee opens personal dashboard", () => {
  const user = { companies: [], teams: [{ id: "e1", role: "employee" }] };
  assert.equal(roleForUser(user), "employee");
  assert.equal(homeForUser(user), "/app/employee");
});

test("empty account may open company onboarding", async () => {
  globalThis.window = { gcCurrentUser: { companies: [], teams: [] } };
  globalThis.location = { pathname: "/app/companies" };
  assert.equal(await guardFor("director")(), true);
});

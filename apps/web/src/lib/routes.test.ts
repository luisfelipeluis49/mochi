import { test } from "node:test";
import assert from "node:assert/strict";
import { NAV_SCREENS, SCREENS, pathOf, routeOf } from "./routes.ts";

test("every screen path maps to its screen", () => {
  for (const s of SCREENS) assert.deepEqual(routeOf(pathOf(s)), { screen: s, redirected: false });
});

test("/ redirects to the session", () => {
  assert.deepEqual(routeOf("/"), { screen: "session", redirected: true });
  assert.deepEqual(routeOf(""), { screen: "session", redirected: true });
});

test("an unknown path redirects to the session", () => {
  assert.deepEqual(routeOf("/home"), { screen: "session", redirected: true });
  assert.deepEqual(routeOf("/m"), { screen: "session", redirected: true });
});

test("a trailing slash or other case still finds the screen", () => {
  assert.deepEqual(routeOf("/digest/"), { screen: "digest", redirected: false });
  assert.deepEqual(routeOf("/Training"), { screen: "training", redirected: true });
});

test("the navigation has four items in order", () => {
  assert.deepEqual(NAV_SCREENS, ["session", "training", "digest", "analytics"]);
});

import assert from "node:assert/strict";
import test from "node:test";
import { isPublicAppPath } from "./public-routes";

test("login and about are public", () => {
  assert.equal(isPublicAppPath("/login"), true);
  assert.equal(isPublicAppPath("/login/"), true);
  assert.equal(isPublicAppPath("/about"), true);
  assert.equal(isPublicAppPath("/about/"), true);
});

test("archive and home are not public shells", () => {
  assert.equal(isPublicAppPath("/"), false);
  assert.equal(isPublicAppPath("/archive"), false);
  assert.equal(isPublicAppPath("/library"), false);
});

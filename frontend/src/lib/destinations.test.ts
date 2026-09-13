import assert from "node:assert/strict";
import test from "node:test";
import { asDestination, asFilingDestination } from "./destinations";

test("asDestination only keeps built-in shelves", () => {
  assert.equal(asDestination("notes"), "notes");
  assert.equal(asDestination("junior"), "additions");
});

test("asFilingDestination keeps custom shelves such as Junior", () => {
  assert.equal(asFilingDestination("junior"), "junior");
  assert.equal(asFilingDestination("editions"), "editions");
  assert.equal(asFilingDestination("notes"), "notes");
  assert.equal(asFilingDestination("", "notes"), "notes");
  assert.equal(asFilingDestination(null, "additions"), "additions");
});

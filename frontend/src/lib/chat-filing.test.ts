import assert from "node:assert/strict";
import test from "node:test";
import { folderNameForFinishedChat, shelfForFinishedChat } from "./chat-filing";

test("a named pane becomes the folder on the selected shelf", () => {
  assert.equal(folderNameForFinishedChat("Storykeep"), "Storykeep");
  assert.equal(shelfForFinishedChat("Storykeep", "notes"), "notes");
});

test("a school pane with the default shelf files under Schoolwork", () => {
  assert.equal(shelfForFinishedChat("Dat 325 School Work", "notes"), "schoolwork");
  assert.equal(folderNameForFinishedChat("Dat 325 School Work"), "Dat 325 School Work");
});

test("an explicit shelf is kept", () => {
  assert.equal(shelfForFinishedChat("Dat 325 School Work", "vault"), "vault");
});

test("a default Junior pane files into Junior chats", () => {
  assert.equal(folderNameForFinishedChat("Junior"), "Junior chats");
  assert.equal(folderNameForFinishedChat("Junior 2"), "Junior chats");
});

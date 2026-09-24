import assert from "node:assert/strict";
import test from "node:test";

import { agentFollowUpPending } from "./agent-followup.ts";

test("pending after a start and clear after the update", () => {
  assert.equal(
    agentFollowUpPending([
      { role: "user", content: "Start a cursor agent to fix mail" },
      { role: "assistant", content: "Cursor Cloud Agent started. Open: https://cursor.com/agents/bc-1" },
    ]),
    true,
  );
  assert.equal(
    agentFollowUpPending([
      { role: "assistant", content: "Cursor Cloud Agent started. Open: https://cursor.com/agents/bc-1" },
      { role: "assistant", content: "Cloud Agent update\n\nFinished. Branch: `cursor/mail`" },
    ]),
    false,
  );
});

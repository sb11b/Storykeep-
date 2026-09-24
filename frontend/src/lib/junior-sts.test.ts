import assert from "node:assert/strict";
import test from "node:test";
import {
  STS_REARM_AFTER_TURN_MS,
  STS_REARM_DEFER_MAX,
  nextStsRearmDeferMs,
  shouldRearmSts,
  shouldRearmStsAfterMicTake,
  type StsRearmGate,
} from "./junior-sts";

const ready: StsRearmGate = {
  stsModeOn: true,
  ttsPaused: false,
  sttPhase: "idle",
  busy: false,
  inFlight: false,
  listenPhase: "idle",
};

test("STS rearm after a finished turn waits 120ms", () => {
  assert.equal(STS_REARM_AFTER_TURN_MS, 120);
});

test("STS rearms when conversation mode is on and Castor is idle", () => {
  assert.equal(shouldRearmSts(ready), true);
});

test("STS does not rearm while a chat turn is still in flight or busy", () => {
  assert.equal(shouldRearmSts({ ...ready, busy: true }), false);
  assert.equal(shouldRearmSts({ ...ready, inFlight: true }), false);
});

test("STS does not rearm while Castor is loading, playing, or paused", () => {
  assert.equal(shouldRearmSts({ ...ready, listenPhase: "loading" }), false);
  assert.equal(shouldRearmSts({ ...ready, listenPhase: "playing" }), false);
  assert.equal(shouldRearmSts({ ...ready, listenPhase: "paused" }), false);
});

test("STS does not rearm after the user paused Listen or left conversation mode", () => {
  assert.equal(shouldRearmSts({ ...ready, ttsPaused: true }), false);
  assert.equal(shouldRearmSts({ ...ready, stsModeOn: false }), false);
});

test("STS does not rearm while the mic is already live or transcribing", () => {
  assert.equal(shouldRearmSts({ ...ready, sttPhase: "listening" }), false);
  assert.equal(shouldRearmSts({ ...ready, sttPhase: "transcribing" }), false);
});

test("empty or failed STS takes rearm; a submitted turn waits for the pane", () => {
  assert.equal(shouldRearmStsAfterMicTake({ stsModeOn: true, submittedTurn: false }), true);
  assert.equal(shouldRearmStsAfterMicTake({ stsModeOn: true, submittedTurn: true }), false);
  assert.equal(shouldRearmStsAfterMicTake({ stsModeOn: false, submittedTurn: false }), false);
});

test("skipped rearm defers a few times then stops", () => {
  assert.equal(nextStsRearmDeferMs(0), 50);
  assert.equal(nextStsRearmDeferMs(STS_REARM_DEFER_MAX - 1), 50);
  assert.equal(nextStsRearmDeferMs(STS_REARM_DEFER_MAX), null);
});

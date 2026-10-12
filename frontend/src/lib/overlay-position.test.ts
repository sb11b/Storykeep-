import assert from "node:assert/strict";
import test from "node:test";
import {
  computeOverlayPosition,
  DEFAULT_OVERLAY_MARGIN,
  type OverlayMonitorLike,
} from "./overlay-position";

const PRIMARY: OverlayMonitorLike = {
  position: { x: 0, y: 0 },
  size: { width: 1920, height: 1080 },
};

test("bubble lands bottom-right with the default margin", () => {
  const pos = computeOverlayPosition(PRIMARY, { width: 72, height: 72 });
  assert.equal(DEFAULT_OVERLAY_MARGIN, 24);
  assert.equal(pos.x, 1920 - 72 - 24);
  assert.equal(pos.y, 1080 - 72 - 24);
});

test("a custom margin moves the bubble inward", () => {
  const pos = computeOverlayPosition(PRIMARY, { width: 72, height: 72 }, 8);
  assert.equal(pos.x, 1920 - 72 - 8);
  assert.equal(pos.y, 1080 - 72 - 8);
});

test("the expanded panel is placed by the same rule", () => {
  const pos = computeOverlayPosition(PRIMARY, { width: 248, height: 176 });
  assert.equal(pos.x, 1920 - 248 - 24);
  assert.equal(pos.y, 1080 - 176 - 24);
  assert.ok(pos.x >= 0 && pos.y >= 0);
});

test("a monitor smaller than the bubble clamps to its top-left corner", () => {
  const tiny: OverlayMonitorLike = {
    position: { x: 0, y: 0 },
    size: { width: 40, height: 40 },
  };
  const pos = computeOverlayPosition(tiny, { width: 72, height: 72 });
  assert.equal(pos.x, 0);
  assert.equal(pos.y, 0);
});

test("a monitor that exactly fits the bubble plus margin is not clamped", () => {
  const exact: OverlayMonitorLike = {
    position: { x: 0, y: 0 },
    size: { width: 72 + 48, height: 72 + 48 },
  };
  const pos = computeOverlayPosition(exact, { width: 72, height: 72 });
  assert.equal(pos.x, 24);
  assert.equal(pos.y, 24);
});

test("a secondary monitor is placed relative to its own origin", () => {
  const secondary: OverlayMonitorLike = {
    position: { x: 1920, y: 0 },
    size: { width: 1920, height: 1080 },
  };
  const pos = computeOverlayPosition(secondary, { width: 72, height: 72 });
  assert.equal(pos.x, 1920 + 1920 - 72 - 24);
  assert.equal(pos.y, 1080 - 72 - 24);
});

test("scaleFactor converts the logical bubble and margin to physical pixels", () => {
  const hidpi: OverlayMonitorLike = {
    position: { x: 0, y: 0 },
    size: { width: 3840, height: 2160 },
    scaleFactor: 2,
  };
  const pos = computeOverlayPosition(hidpi, { width: 72, height: 72 });
  // 3840 - (72 * 2) - (24 * 2)
  assert.equal(pos.x, 3648);
  assert.equal(pos.y, 2160 - 144 - 48);
  // The bubble plus its margin must still be inside the monitor.
  assert.ok(pos.x + 144 <= 3840);
  assert.ok(pos.y + 144 <= 2160);
});

test("a missing or bogus scaleFactor is treated as 1", () => {
  const noScale: OverlayMonitorLike = {
    position: { x: 0, y: 0 },
    size: { width: 1920, height: 1080 },
  };
  const bogus: OverlayMonitorLike = { ...noScale, scaleFactor: 0 };
  const base = computeOverlayPosition(noScale, { width: 72, height: 72 });
  const zeroed = computeOverlayPosition(bogus, { width: 72, height: 72 });
  assert.deepEqual(zeroed, base);
});

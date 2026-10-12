import assert from "node:assert/strict";
import test from "node:test";

// No `window` global in this runner: isDesktopWindow() is false and
// checkForUpdate() must return null WITHOUT ever importing the Tauri
// plugin JS — that is the browser/PWA no-op contract, tested here for
// real. The packaged-window path needs the Tauri runtime and is verified
// by Steve's Windows build (see the PR body).

test("isDesktopWindow is false without a Tauri runtime (browser/PWA no-op)", async () => {
  const { isDesktopWindow } = await import("./auto-update");
  assert.equal(isDesktopWindow(), false);
});

test("checkForUpdate resolves to null in the browser and never throws", async () => {
  // Would have thrown (or hung) if the guard were missing: the plugin JS
  // calls into Tauri IPC that does not exist here.
  const { checkForUpdate } = await import("./auto-update");
  assert.equal(await checkForUpdate(), null);
});

test("isNewerVersion compares components numerically, not lexically", async () => {
  const { isNewerVersion } = await import("./auto-update");
  assert.equal(isNewerVersion("0.1.1", "0.1.0"), true);
  assert.equal(isNewerVersion("0.2.0", "0.1.9"), true);
  // The lexicographic trap: "0.10.0" < "0.9.0" as strings but is newer
  // as a version.
  assert.equal(isNewerVersion("0.10.0", "0.9.0"), true);
  assert.equal(isNewerVersion("1.2.3", "1.2.10"), false);
});

test("isNewerVersion is false for equal, older, or unparseable versions", async () => {
  const { isNewerVersion } = await import("./auto-update");
  assert.equal(isNewerVersion("0.1.0", "0.1.0"), false);
  assert.equal(isNewerVersion("0.0.9", "0.1.0"), false);
  assert.equal(isNewerVersion("", "0.1.0"), false);
  assert.equal(isNewerVersion("not-a-version", "0.1.0"), false);
  assert.equal(isNewerVersion("0.1", "0.1.0"), false);
  assert.equal(isNewerVersion("  0.2.0  ", "0.1.0"), true);
});

test("isNewerVersion follows semver pre-release ordering on equal cores", async () => {
  const { isNewerVersion } = await import("./auto-update");
  // A stable release beats any pre-release of the same core version.
  assert.equal(isNewerVersion("1.0.0", "1.0.0-beta"), true);
  assert.equal(isNewerVersion("1.0.0-beta", "1.0.0"), false);
  // Pre-release labels compare lexically when both are pre-releases.
  assert.equal(isNewerVersion("1.0.0-rc.2", "1.0.0-rc.1"), true);
  assert.equal(isNewerVersion("1.0.0-rc.1", "1.0.0-rc.2"), false);
  assert.equal(isNewerVersion("1.0.0-rc.1", "1.0.0-rc.1"), false);
});

test("buildLatestJson produces the Tauri v2 manifest with the arm64 platform key", async () => {
  const { buildLatestJson } = await import("./auto-update");
  const json = buildLatestJson({
    version: "0.1.1",
    pubDate: "2026-10-12T06:30:00Z",
    platform: "windows-aarch64",
    signature: "dW50cnVzdGVkIGNvbW1lbnQ=",
    url: "https://github.com/sb11b/Storykeep-/releases/download/v0.1.1/StoryKeep_0.1.1_arm64_en-US.msi",
    notes: "https://github.com/sb11b/Storykeep-/releases/tag/v0.1.1",
  });
  const parsed = JSON.parse(json);
  assert.equal(parsed.version, "0.1.1");
  assert.equal(parsed.notes, "https://github.com/sb11b/Storykeep-/releases/tag/v0.1.1");
  assert.equal(parsed.pub_date, "2026-10-12T06:30:00Z");
  // Steve builds Windows ARM64 only: exactly one platform key.
  assert.deepEqual(Object.keys(parsed.platforms), ["windows-aarch64"]);
  assert.equal(parsed.platforms["windows-aarch64"].signature, "dW50cnVzdGVkIGNvbW1lbnQ=");
  assert.equal(
    parsed.platforms["windows-aarch64"].url,
    "https://github.com/sb11b/Storykeep-/releases/download/v0.1.1/StoryKeep_0.1.1_arm64_en-US.msi",
  );
  // Trailing newline so the file diffs cleanly in the release tag.
  assert.ok(json.endsWith("}\n"));
});

test("buildLatestJson defaults notes to an empty string", async () => {
  const { buildLatestJson } = await import("./auto-update");
  const parsed = JSON.parse(
    buildLatestJson({
      version: "0.2.0",
      pubDate: "2026-10-12T06:30:00Z",
      platform: "windows-aarch64",
      signature: "sig",
      url: "https://example.com/StoryKeep_0.2.0_arm64_en-US.msi",
    }),
  );
  assert.equal(parsed.notes, "");
});

test("shouldShowUpdateBanner is visible only while an update is actionable", async () => {
  const { shouldShowUpdateBanner, INITIAL_UPDATE_STATE } = await import("./auto-update");
  const base = { ...INITIAL_UPDATE_STATE };
  assert.equal(shouldShowUpdateBanner({ ...base, status: "idle" }), false);
  // Never flicker a banner during the startup fetch.
  assert.equal(shouldShowUpdateBanner({ ...base, status: "checking" }), false);
  assert.equal(
    shouldShowUpdateBanner({ ...base, status: "available", version: "0.1.1" }),
    true,
  );
  assert.equal(
    shouldShowUpdateBanner({ ...base, status: "downloading", version: "0.1.1" }),
    true,
  );
  // Failure is invisible: the app just keeps running on the old version.
  assert.equal(shouldShowUpdateBanner({ ...base, status: "error" }), false);
});

test("shouldShowUpdateBanner stays hidden once dismissed, for the session", async () => {
  const { shouldShowUpdateBanner, INITIAL_UPDATE_STATE } = await import("./auto-update");
  assert.equal(
    shouldShowUpdateBanner({
      ...INITIAL_UPDATE_STATE,
      status: "available",
      version: "0.1.1",
      dismissed: true,
    }),
    false,
  );
  assert.equal(
    shouldShowUpdateBanner({
      ...INITIAL_UPDATE_STATE,
      status: "downloading",
      version: "0.1.1",
      dismissed: true,
    }),
    false,
  );
});

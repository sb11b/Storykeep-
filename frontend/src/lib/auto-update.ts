/**
 * Desktop auto-update — click-to-install, shipped via GitHub Releases.
 *
 * The packaged Tauri window polls the static endpoint configured in
 * `tauri.conf.json` (`plugins.updater.endpoints`, signed with the pubkey
 * beside it) through `@tauri-apps/plugin-updater`. The rules Steve set:
 *
 * - **Nothing installs without his click.** The startup check only fetches
 *   the manifest; the download starts exclusively from the banner's
 *   "Install & restart" button (see `src/components/update-banner.tsx`).
 * - **Never blocks startup.** The check is fire-and-forget from a mount
 *   effect; a slow or dead endpoint never delays a render or a route.
 * - **Silent on failure.** Offline, 404, signing mismatch, any plugin/RPC
 *   error → `checkForUpdate()` returns null and no UI appears. Updating is
 *   a convenience, never a requirement.
 * - **No-op in the browser/PWA.** Guarded on `isDesktopWindow()` (the
 *   documented `__TAURI_INTERNALS__` runtime global) before the plugin is
 *   even dynamically imported, so the web app never ships the plugin code
 *   into an executed path and tests run without a Tauri runtime.
 *
 * The pure pieces (version comparison, latest.json shape, banner
 * visibility) live here as exported functions so they are unit-testable
 * without the Tauri runtime — the `check()` call itself is a thin typed
 * wrapper around the plugin API.
 */

import type { Update } from "@tauri-apps/plugin-updater";

/** Lifecycle of the update banner, independent of any remote state. */
export type UpdateStatus =
  | "idle" // no update (or not applicable) — no banner
  | "checking" // manifest fetch in flight — no banner
  | "available" // update fetched and ready to install — banner with button
  | "downloading" // user clicked; download + install in flight — banner, no buttons
  | "error"; // check or install failed — silent, no banner

export interface UpdateState {
  status: UpdateStatus;
  /** Remote version, when one is available or downloading. */
  version: string | null;
  /** True once the user dismisses the banner; stays dismissed for the session. */
  dismissed: boolean;
}

export const INITIAL_UPDATE_STATE: UpdateState = {
  status: "idle",
  version: null,
  dismissed: false,
};

/**
 * True only inside the packaged desktop window.
 *
 * Mirrors the packaged-window detection in `api-base.ts` (the documented
 * Tauri runtime global `__TAURI_INTERNALS__`): in the browser or the
 * installed PWA there is no Tauri runtime, so every updater call would
 * throw — the guard keeps the module a total no-op there.
 */
export function isDesktopWindow(): boolean {
  if (typeof window === "undefined") return false;
  return "__TAURI_INTERNALS__" in window;
}

/** Parse `MAJOR.MINOR.PATCH[-prerelease]` into comparable parts. */
function parseVersion(
  value: string,
): { core: [number, number, number]; prerelease: string | null } | null {
  const match = /^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$/.exec(value.trim());
  if (!match) return null;
  return {
    core: [Number(match[1]), Number(match[2]), Number(match[3])],
    prerelease: match[4] ?? null,
  };
}

/**
 * True when `candidate` is a strictly newer version than `current`.
 *
 * Numeric per-component comparison (0.10.0 is newer than 0.9.0 — never
 * lexicographic), and semver's pre-release ordering when the cores match:
 * a stable release beats any pre-release of the same core, and two
 * pre-releases compare by label. Unparseable input is never "newer" —
 * the plugin's own server-side comparison stays the source of truth and
 * this guard only prevents a bogus manifest from reopening a dismissed
 * update. (This repo ships plain `0.1.0` versions; pre-release labels are
 * handled conservatively for future use.)
 */
export function isNewerVersion(candidate: string, current: string): boolean {
  const next = parseVersion(candidate);
  const now = parseVersion(current);
  if (!next || !now) return false;
  for (let i = 0; i < 3; i++) {
    if (next.core[i] !== now.core[i]) return next.core[i] > now.core[i];
  }
  if (next.prerelease === now.prerelease) return false;
  if (next.prerelease === null) return true; // stable > prerelease, same core
  if (now.prerelease === null) return false; // prerelease < stable, same core
  return next.prerelease > now.prerelease;
}

/**
 * Build the `latest.json` manifest the updater endpoint serves.
 *
 * Tauri v2 format: `{ version, notes, pub_date, platforms: { "<os>-<arch>":
 * { signature, url } } }`. The platform key is OS-ARCH — Steve builds
 * Windows ARM64 only, so `windows-aarch64` is the only key. This mirrors
 * the generation step in `scripts/release.ps1` (kept in TS here so the
 * shape is unit-tested and the release script and the app agree on it).
 */
export function buildLatestJson(args: {
  version: string;
  pubDate: string;
  platform: string;
  signature: string;
  url: string;
  notes?: string;
}): string {
  const manifest = {
    version: args.version,
    notes: args.notes ?? "",
    pub_date: args.pubDate,
    platforms: {
      [args.platform]: { signature: args.signature, url: args.url },
    },
  };
  return `${JSON.stringify(manifest, null, 2)}\n`;
}

/**
 * Banner visibility — the whole "non-intrusive" contract in one place.
 *
 * Visible only while an update is actually actionable: `available` (the
 * button) and `downloading` (progress text). Silent for `idle`,
 * `checking` (never flicker a banner during the startup fetch) and
 * `error` (failure is invisible). A dismissed banner stays hidden until
 * the next launch, whatever the status.
 */
export function shouldShowUpdateBanner(state: UpdateState): boolean {
  if (state.dismissed) return false;
  return state.status === "available" || state.status === "downloading";
}

export interface UpdateInfo {
  version: string;
  /** Live plugin handle; `downloadAndInstall()` starts only on user click. */
  update: Update;
}

/**
 * Fetch the update manifest and report a genuinely newer version.
 *
 * Returns null — silently — in the browser (no Tauri runtime), offline,
 * on any plugin error, when the endpoint says "no update", or when the
 * manifest's version is not newer than the running app's. Callers never
 * see a throw: the banner simply never appears.
 */
export async function checkForUpdate(): Promise<UpdateInfo | null> {
  if (!isDesktopWindow()) return null;
  try {
    // Dynamic import: the plugin's JS (and its Tauri RPC plumbing) is only
    // pulled in where a Tauri runtime actually exists.
    const [{ check }, { getVersion }] = await Promise.all([
      import("@tauri-apps/plugin-updater"),
      import("@tauri-apps/api/app"),
    ]);
    const [update, currentVersion] = await Promise.all([
      check(),
      getVersion(),
    ]);
    if (!update) return null;
    if (!isNewerVersion(update.version, currentVersion)) return null;
    return { version: update.version, update };
  } catch {
    return null;
  }
}

/**
 * Download and install the update, then restart the app.
 *
 * Passive mode (the plugin default): the plugin's own progress window
 * shows download progress and the app relaunches once the new binary is
 * staged — no further interaction needed. Only ever called from the
 * banner's click handler.
 */
export async function installUpdate(update: Update): Promise<void> {
  await update.downloadAndInstall();
}

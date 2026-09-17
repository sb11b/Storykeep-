export const JUNIOR_RAIL_STORAGE_KEY = "storykeep-junior-rail";
export const JUNIOR_RAIL_HIDDEN = "hidden";
export const JUNIOR_RAIL_SHOWN = "shown";

export type JuniorRailFlags = {
  showJobs: boolean;
  showMemory: boolean;
  showChats: boolean;
};

export const JUNIOR_RAIL_DEFAULT: JuniorRailFlags = {
  showJobs: true,
  showMemory: true,
  showChats: true,
};

function storage(): Storage | null {
  try {
    const store = globalThis.localStorage;
    return store ?? null;
  } catch {
    return null;
  }
}

function asBool(value: unknown, fallback: boolean): boolean {
  if (typeof value === "boolean") return value;
  return fallback;
}

export function parseJuniorRailFlags(raw: string | null | undefined): JuniorRailFlags {
  if (!raw) return { ...JUNIOR_RAIL_DEFAULT };
  if (raw === JUNIOR_RAIL_HIDDEN) {
    return { showJobs: false, showMemory: false, showChats: false };
  }
  if (raw === JUNIOR_RAIL_SHOWN) return { ...JUNIOR_RAIL_DEFAULT };
  try {
    const parsed = JSON.parse(raw) as Partial<JuniorRailFlags>;
    if (!parsed || typeof parsed !== "object") return { ...JUNIOR_RAIL_DEFAULT };
    return {
      showJobs: asBool(parsed.showJobs, true),
      showMemory: asBool(parsed.showMemory, true),
      showChats: asBool(parsed.showChats, true),
    };
  } catch {
    return { ...JUNIOR_RAIL_DEFAULT };
  }
}

export function loadJuniorRailFlags(): JuniorRailFlags {
  const store = storage();
  if (!store) return { ...JUNIOR_RAIL_DEFAULT };
  try {
    return parseJuniorRailFlags(store.getItem(JUNIOR_RAIL_STORAGE_KEY));
  } catch {
    return { ...JUNIOR_RAIL_DEFAULT };
  }
}

export function saveJuniorRailFlags(flags: JuniorRailFlags): void {
  const store = storage();
  if (!store) return;
  try {
    store.setItem(
      JUNIOR_RAIL_STORAGE_KEY,
      JSON.stringify({
        showJobs: flags.showJobs,
        showMemory: flags.showMemory,
        showChats: flags.showChats,
      }),
    );
  } catch {
    /* ignore quota / private mode */
  }
}

export function patchJuniorRailFlags(
  current: JuniorRailFlags,
  patch: Partial<JuniorRailFlags>,
): JuniorRailFlags {
  return {
    showJobs: patch.showJobs ?? current.showJobs,
    showMemory: patch.showMemory ?? current.showMemory,
    showChats: patch.showChats ?? current.showChats,
  };
}

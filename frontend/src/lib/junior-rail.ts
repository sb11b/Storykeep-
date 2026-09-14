export const JUNIOR_RAIL_STORAGE_KEY = "storykeep-junior-rail";
export const JUNIOR_RAIL_HIDDEN = "hidden";
export const JUNIOR_RAIL_SHOWN = "shown";

function storage(): Storage | null {
  try {
    const store = globalThis.localStorage;
    return store ?? null;
  } catch {
    return null;
  }
}

export function loadJuniorRailHidden(): boolean {
  const store = storage();
  if (!store) return false;
  try {
    return store.getItem(JUNIOR_RAIL_STORAGE_KEY) === JUNIOR_RAIL_HIDDEN;
  } catch {
    return false;
  }
}

export function saveJuniorRailHidden(hidden: boolean): void {
  const store = storage();
  if (!store) return;
  try {
    store.setItem(JUNIOR_RAIL_STORAGE_KEY, hidden ? JUNIOR_RAIL_HIDDEN : JUNIOR_RAIL_SHOWN);
  } catch {
    /* ignore quota / private mode */
  }
}

export type Pinnable = {
  pinned?: boolean;
  pinned_at?: string | null;
};

/** Pinned rows first. Among pins, later pin-time stays above earlier pins. */
export function comparePinned<T extends Pinnable>(a: T, b: T, tieBreak: (left: T, right: T) => number = () => 0): number {
  const pin = Number(Boolean(b.pinned)) - Number(Boolean(a.pinned));
  if (pin) return pin;
  if (a.pinned && b.pinned) {
    const at = a.pinned_at || "";
    const bt = b.pinned_at || "";
    if (at !== bt) return bt.localeCompare(at);
  }
  return tieBreak(a, b);
}

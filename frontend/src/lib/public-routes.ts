/** Paths that do not require a session. Keep Junior off these pages. */
const PUBLIC_PREFIXES = ["/login", "/about"];

export function isPublicAppPath(pathname: string | null | undefined): boolean {
  const raw = (pathname || "/").split("?")[0] || "/";
  const path = raw.replace(/\/+$/, "") || "/";
  return PUBLIC_PREFIXES.some((prefix) => path === prefix || path.startsWith(`${prefix}/`));
}

import type { Profile, User } from "./types";

/** Merge a partial profile/me response into the library user without dropping preferences. */
export function mergeUserProfile(base: User, patch: Partial<Profile>): User {
  return {
    ...base,
    ...patch,
    preferences: patch.preferences ?? base.preferences ?? {},
  };
}

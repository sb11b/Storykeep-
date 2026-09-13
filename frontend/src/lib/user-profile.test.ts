import assert from "node:assert/strict";
import test from "node:test";
import { mergeUserProfile } from "./user-profile";
import type { User } from "./types";

const base: User = {
  id: "u1",
  email: "a@example.com",
  display_name: "Ada",
  avatar_url: "/api/v1/media/old",
  birthdate: null,
  preferences: {
    appearance: { rail_preset: "navy", font_family: "serif" },
    items_per_page: 40,
  },
  profile_read_only: false,
  created_at: "2026-01-01T00:00:00Z",
};

test("mergeUserProfile keeps preferences when patch omits them", () => {
  const next = mergeUserProfile(base, {
    avatar_url: "/api/v1/media/new",
    totp_enabled: false,
    email_otp_enabled: false,
    email_otp_available: false,
    has_backup_codes: false,
  });
  assert.equal(next.avatar_url, "/api/v1/media/new");
  assert.deepEqual(next.preferences.appearance, { rail_preset: "navy", font_family: "serif" });
});

test("mergeUserProfile replaces preferences when patch includes them", () => {
  const next = mergeUserProfile(base, {
    preferences: { appearance: { rail_preset: "forest" } },
    totp_enabled: false,
    email_otp_enabled: false,
    email_otp_available: false,
    has_backup_codes: false,
  });
  assert.deepEqual(next.preferences, { appearance: { rail_preset: "forest" } });
});

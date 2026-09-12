"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { ArrowLeft, Camera, Loader2 } from "lucide-react";
import { ApiError, api } from "@/lib/api";
import type { Profile, TotpSetup } from "@/lib/types";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

type ProfilePageProps = {
  /** When embedded in library chrome or a modal, use this instead of routing home. */
  onClose?: () => void;
  className?: string;
};

export function ProfilePage({ onClose, className }: ProfilePageProps = {}) {
  const router = useRouter();
  const close = onClose ?? (() => router.push("/"));
  const fileRef = useRef<HTMLInputElement>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [displayName, setDisplayName] = useState("");
  const [birthdate, setBirthdate] = useState("");
  const [savingProfile, setSavingProfile] = useState(false);
  const [uploadingPhoto, setUploadingPhoto] = useState(false);

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [changingPassword, setChangingPassword] = useState(false);

  const [newEmail, setNewEmail] = useState("");
  const [emailCode, setEmailCode] = useState("");
  const [emailStep, setEmailStep] = useState<"idle" | "code">("idle");
  const [changingEmail, setChangingEmail] = useState(false);

  const [totpSetup, setTotpSetup] = useState<TotpSetup | null>(null);
  const [totpCode, setTotpCode] = useState("");
  const [backupCodes, setBackupCodes] = useState<string[] | null>(null);
  const [disableTotpCode, setDisableTotpCode] = useState("");
  const [busy2fa, setBusy2fa] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.profile();
      setProfile(data);
      setDisplayName(data.display_name || "");
      setBirthdate(data.birthdate || "");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        router.replace("/login");
        return;
      }
      toast.error(error instanceof ApiError ? error.message : "Could not load profile");
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    void load();
  }, [load]);

  async function saveProfile() {
    if (!profile || profile.profile_read_only) return;
    setSavingProfile(true);
    try {
      const updated = await api.updateProfile({
        display_name: displayName.trim() || null,
        birthdate: birthdate || null,
      });
      setProfile(updated);
      toast.success("Profile updated");
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not save profile");
    } finally {
      setSavingProfile(false);
    }
  }

  async function onPhotoSelected(file: File | null) {
    if (!file || !profile || profile.profile_read_only) return;
    setUploadingPhoto(true);
    try {
      const uploaded = await api.uploadNoteMedia(file);
      const updated = await api.updateProfile({ avatar_media_id: uploaded.id });
      setProfile(updated);
      toast.success("Profile photo updated");
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not upload photo");
    } finally {
      setUploadingPhoto(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function onChangePassword(event: React.FormEvent) {
    event.preventDefault();
    if (!profile || profile.profile_read_only) return;
    setChangingPassword(true);
    try {
      await api.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
        confirm_password: confirmPassword,
      });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      toast.success("Password changed");
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not change password");
    } finally {
      setChangingPassword(false);
    }
  }

  async function onRequestEmailChange(event: React.FormEvent) {
    event.preventDefault();
    if (!profile || profile.profile_read_only) return;
    setChangingEmail(true);
    try {
      await api.requestEmailChange(newEmail.trim());
      setEmailStep("code");
      toast.success("Confirmation code sent to the new email");
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not start email change");
    } finally {
      setChangingEmail(false);
    }
  }

  async function onConfirmEmailChange(event: React.FormEvent) {
    event.preventDefault();
    if (!profile || profile.profile_read_only) return;
    setChangingEmail(true);
    try {
      const updated = await api.confirmEmailChange(emailCode.trim());
      setProfile(updated);
      setNewEmail("");
      setEmailCode("");
      setEmailStep("idle");
      toast.success("Email updated");
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not confirm email");
    } finally {
      setChangingEmail(false);
    }
  }

  async function startTotpSetup() {
    if (!profile || profile.profile_read_only) return;
    setBusy2fa(true);
    try {
      const setup = await api.setupTotp();
      setTotpSetup(setup);
      setBackupCodes(null);
      setTotpCode("");
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not start authenticator setup");
    } finally {
      setBusy2fa(false);
    }
  }

  async function confirmTotpSetup(event: React.FormEvent) {
    event.preventDefault();
    if (!profile || profile.profile_read_only) return;
    setBusy2fa(true);
    try {
      const result = await api.confirmTotp(totpCode.trim());
      setBackupCodes(result.backup_codes);
      setTotpSetup(null);
      setTotpCode("");
      await load();
      toast.success("Authenticator app enabled");
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Incorrect code");
    } finally {
      setBusy2fa(false);
    }
  }

  async function disableTotp(event: React.FormEvent) {
    event.preventDefault();
    if (!profile || profile.profile_read_only) return;
    setBusy2fa(true);
    try {
      await api.disableTotp(disableTotpCode.trim());
      setDisableTotpCode("");
      await load();
      toast.success("Authenticator app disabled");
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not disable authenticator");
    } finally {
      setBusy2fa(false);
    }
  }

  async function toggleEmailOtp(enabled: boolean) {
    if (!profile || profile.profile_read_only) return;
    setBusy2fa(true);
    try {
      if (enabled) await api.enableEmailOtp();
      else await api.disableEmailOtp();
      await load();
      toast.success(enabled ? "Email code at login enabled" : "Email code at login disabled");
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not update email 2FA");
    } finally {
      setBusy2fa(false);
    }
  }

  if (loading || !profile) {
    return (
      <div className={cn("flex h-full min-h-0 items-center justify-center text-sm text-muted-foreground", className)}>
        Loading profile…
      </div>
    );
  }

  const readOnly = profile.profile_read_only;

  return (
    <div className={cn("flex h-full min-h-0 flex-col bg-background", className)}>
      <header className="sticky top-0 z-10 shrink-0 border-b border-border/80 bg-background/95 px-4 py-3 backdrop-blur supports-[backdrop-filter]:bg-background/80">
        <div className="mx-auto flex max-w-2xl items-center gap-3">
          <button type="button" className={cn(buttonVariants({ variant: "ghost", size: "icon-sm" }))} onClick={close} aria-label="Close profile">
            <ArrowLeft className="size-4" />
          </button>
          <div className="min-w-0 flex-1">
            <h1 className="font-[family-name:var(--font-serif)] text-2xl tracking-tight">Profile</h1>
            <p className="truncate text-sm text-muted-foreground">Account settings and sign-in security</p>
          </div>
          {!readOnly ? (
            <Button type="button" size="sm" onClick={() => void saveProfile()} disabled={savingProfile}>
              {savingProfile ? "Saving…" : "Save profile"}
            </Button>
          ) : null}
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
        <div className="mx-auto max-w-2xl space-y-6 px-4 py-6 pb-10">
        {readOnly ? (
          <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
            Demo account profile is read-only.
          </p>
        ) : null}

        <Card>
          <CardHeader>
            <CardTitle>Profile</CardTitle>
            <CardDescription>Your name and photo appear in the sidebar.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center gap-4">
              <div className="relative size-16 overflow-hidden rounded-full bg-muted">
                {profile.avatar_url ? (
                  <img src={profile.avatar_url} alt="" className="size-full object-cover" />
                ) : (
                  <div className="flex size-full items-center justify-center text-lg font-medium text-muted-foreground">
                    {(profile.display_name || profile.email).slice(0, 1).toUpperCase()}
                  </div>
                )}
              </div>
              <div>
                <input
                  ref={fileRef}
                  type="file"
                  accept="image/png,image/jpeg,image/gif,image/webp"
                  className="hidden"
                  disabled={readOnly || uploadingPhoto}
                  onChange={(event) => void onPhotoSelected(event.target.files?.[0] || null)}
                />
                <Button type="button" variant="secondary" size="sm" disabled={readOnly || uploadingPhoto} onClick={() => fileRef.current?.click()}>
                  {uploadingPhoto ? <Loader2 className="size-3.5 animate-spin" /> : <Camera className="size-3.5" />}
                  Change photo
                </Button>
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="display_name">Display name</Label>
              <Input id="display_name" value={displayName} disabled={readOnly} onChange={(e) => setDisplayName(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input id="email" value={profile.email} disabled />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="birthdate">Birthdate (optional)</Label>
              <Input id="birthdate" type="date" value={birthdate} disabled={readOnly} onChange={(e) => setBirthdate(e.target.value)} />
            </div>
          </CardContent>
        </Card>

        {!readOnly ? (
          <>
            <Card>
              <CardHeader>
                <CardTitle>Change password</CardTitle>
              </CardHeader>
              <CardContent>
                <form className="space-y-3" onSubmit={onChangePassword}>
                  <div className="space-y-1.5">
                    <Label htmlFor="current_password">Current password</Label>
                    <Input id="current_password" type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} required />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="new_password">New password</Label>
                    <Input id="new_password" type="password" minLength={8} value={newPassword} onChange={(e) => setNewPassword(e.target.value)} required />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="confirm_password">Confirm new password</Label>
                    <Input id="confirm_password" type="password" minLength={8} value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} required />
                  </div>
                  <Button type="submit" disabled={changingPassword}>{changingPassword ? "Updating…" : "Update password"}</Button>
                </form>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Change email</CardTitle>
                <CardDescription>We send a confirmation code to the new address before switching.</CardDescription>
              </CardHeader>
              <CardContent>
                {emailStep === "idle" ? (
                  <form className="space-y-3" onSubmit={onRequestEmailChange}>
                    <div className="space-y-1.5">
                      <Label htmlFor="new_email">New email</Label>
                      <Input id="new_email" type="email" value={newEmail} onChange={(e) => setNewEmail(e.target.value)} required />
                    </div>
                    <Button type="submit" disabled={changingEmail}>{changingEmail ? "Sending…" : "Send confirmation code"}</Button>
                  </form>
                ) : (
                  <form className="space-y-3" onSubmit={onConfirmEmailChange}>
                    <div className="space-y-1.5">
                      <Label htmlFor="email_code">6-digit code</Label>
                      <Input id="email_code" inputMode="numeric" maxLength={6} value={emailCode} onChange={(e) => setEmailCode(e.target.value)} required />
                    </div>
                    <div className="flex gap-2">
                      <Button type="submit" disabled={changingEmail}>{changingEmail ? "Confirming…" : "Confirm new email"}</Button>
                      <Button type="button" variant="ghost" onClick={() => setEmailStep("idle")}>Cancel</Button>
                    </div>
                  </form>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Two-factor authentication</CardTitle>
                <CardDescription>Add a second step after your password at sign-in.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="space-y-3">
                  <p className="text-sm font-medium">Authenticator app</p>
                  {profile.totp_enabled ? (
                    <form className="space-y-2 max-w-xs" onSubmit={disableTotp}>
                      <Label htmlFor="disable_totp">Enter a code to disable</Label>
                      <Input id="disable_totp" inputMode="numeric" maxLength={6} value={disableTotpCode} onChange={(e) => setDisableTotpCode(e.target.value)} />
                      <Button type="submit" variant="secondary" disabled={busy2fa}>Disable authenticator</Button>
                    </form>
                  ) : totpSetup ? (
                    <div className="space-y-3">
                      <img src={totpSetup.qr_code_data_url} alt="Authenticator QR code" className="size-40 rounded-md border bg-white p-2" />
                      <p className="text-xs text-muted-foreground break-all">Secret (shown once): {totpSetup.secret}</p>
                      <form className="space-y-2 max-w-xs" onSubmit={confirmTotpSetup}>
                        <Label htmlFor="totp_confirm">6-digit code from your app</Label>
                        <Input id="totp_confirm" inputMode="numeric" maxLength={6} value={totpCode} onChange={(e) => setTotpCode(e.target.value)} required />
                        <Button type="submit" disabled={busy2fa}>{busy2fa ? "Confirming…" : "Enable authenticator"}</Button>
                      </form>
                    </div>
                  ) : (
                    <Button type="button" onClick={() => void startTotpSetup()} disabled={busy2fa}>
                      Set up authenticator app
                    </Button>
                  )}
                </div>

                {backupCodes ? (
                  <div className="rounded-lg border bg-muted/40 p-3 space-y-2">
                    <p className="text-sm font-medium">Backup codes (save these now — shown once)</p>
                    <ul className="grid grid-cols-2 gap-1 font-mono text-sm">
                      {backupCodes.map((code) => (
                        <li key={code}>{code}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}

                <div className="space-y-3 border-t pt-4">
                  <p className="text-sm font-medium">Email code at login</p>
                  {profile.email_otp_available ? (
                    profile.email_otp_enabled ? (
                      <Button type="button" variant="secondary" disabled={busy2fa} onClick={() => void toggleEmailOtp(false)}>
                        Disable email code
                      </Button>
                    ) : (
                      <Button type="button" disabled={busy2fa} onClick={() => void toggleEmailOtp(true)}>
                        Enable email code at login
                      </Button>
                    )
                  ) : (
                    <p className="text-sm text-muted-foreground">Email codes require SMTP configuration on this server.</p>
                  )}
                </div>
              </CardContent>
            </Card>
          </>
        ) : null}
        </div>
      </div>
    </div>
  );
}

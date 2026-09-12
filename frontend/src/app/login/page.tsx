"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { buttonVariants } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";
import { cn } from "@/lib/utils";

type TwoFactorState = {
  challengeId: string;
  totpAvailable: boolean;
  emailOtpAvailable: boolean;
};

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [twoFactor, setTwoFactor] = useState<TwoFactorState | null>(null);
  const [code, setCode] = useState("");
  const [useBackupCode, setUseBackupCode] = useState(false);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    event.stopPropagation();
    if (busy) return;
    setBusy(true);
    try {
      if (mode === "register") {
        await api.register(email, password, displayName || undefined);
        router.replace("/");
        return;
      }
      if (twoFactor) {
        await api.verifyLogin2fa({
          challenge_id: twoFactor.challengeId,
          code: code.trim(),
          use_backup_code: useBackupCode,
        });
        router.replace("/");
        return;
      }
      const result = await api.login(email, password);
      if (result.requires_2fa && result.challenge_id) {
        setTwoFactor({
          challengeId: result.challenge_id,
          totpAvailable: Boolean(result.totp_available),
          emailOtpAvailable: Boolean(result.email_otp_available),
        });
        setCode("");
        setUseBackupCode(false);
        return;
      }
      router.replace("/");
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not sign in");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,#f3e3c8_0%,transparent_42%),linear-gradient(180deg,#f6f1e8,#efe6d6)] flex items-center justify-center px-4 py-10">
      <div className="w-full max-w-md space-y-8">
        <div className="text-center">
          <p className="font-[family-name:var(--font-serif)] text-4xl tracking-tight">Storykeep</p>
          <p className="mt-2 text-sm text-muted-foreground">
            Keep the stories that matter. Search them decades from now.
          </p>
        </div>
        <Card className="shadow-none border-border/80">
          <CardHeader>
            <CardTitle className="font-[family-name:var(--font-serif)] text-2xl">
              {twoFactor ? "Verify sign-in" : "Open your archive"}
            </CardTitle>
            <CardDescription>
              {twoFactor
                ? useBackupCode
                  ? "Enter one of your backup codes."
                  : twoFactor.totpAvailable
                    ? "Enter the 6-digit code from your authenticator app."
                    : "Enter the 6-digit code sent to your email."
                : "Sign in with your StoryKeep account."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            {!twoFactor ? (
              <div className="grid grid-cols-2 gap-1 rounded-lg bg-muted p-1 mb-4">
                <button
                  type="button"
                  className={cn(
                    "h-7 rounded-md text-sm",
                    mode === "login" ? "bg-background shadow-sm" : "text-muted-foreground",
                  )}
                  onClick={() => setMode("login")}
                >
                  Sign in
                </button>
                <button
                  type="button"
                  className={cn(
                    "h-7 rounded-md text-sm",
                    mode === "register" ? "bg-background shadow-sm" : "text-muted-foreground",
                  )}
                  onClick={() => setMode("register")}
                >
                  Create account
                </button>
              </div>
            ) : null}
            <form className="space-y-3" method="post" action="/login" onSubmit={onSubmit}>
              {!twoFactor && mode === "register" ? (
                <div className="space-y-1.5">
                  <Label htmlFor="display_name">Name</Label>
                  <Input
                    id="display_name"
                    name="display_name"
                    value={displayName}
                    onChange={(event) => setDisplayName(event.target.value)}
                    placeholder="Steve"
                    autoComplete="name"
                  />
                </div>
              ) : null}
              {!twoFactor ? (
                <>
                  <div className="space-y-1.5">
                    <Label htmlFor="email">Email</Label>
                    <Input
                      id="email"
                      name="email"
                      type="email"
                      required
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      autoComplete="username"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="password">Password</Label>
                    <Input
                      id="password"
                      name="password"
                      type="password"
                      required
                      minLength={8}
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                      autoComplete="current-password"
                    />
                  </div>
                </>
              ) : (
                <>
                  <div className="space-y-1.5">
                    <Label htmlFor="code">{useBackupCode ? "Backup code" : "6-digit code"}</Label>
                    <Input
                      id="code"
                      name="code"
                      inputMode={useBackupCode ? "text" : "numeric"}
                      required
                      value={code}
                      onChange={(event) => setCode(event.target.value)}
                      autoComplete="one-time-code"
                    />
                  </div>
                  {twoFactor?.totpAvailable ? (
                    <button
                      type="button"
                      className="text-sm text-muted-foreground underline-offset-4 hover:underline"
                      onClick={() => {
                        setUseBackupCode((value) => !value);
                        setCode("");
                      }}
                    >
                      {useBackupCode ? "Use authenticator code instead" : "Use a backup code instead"}
                    </button>
                  ) : null}
                </>
              )}
              <button type="submit" className={cn(buttonVariants(), "w-full")} disabled={busy}>
                {busy ? "Opening…" : twoFactor ? "Verify" : mode === "register" ? "Start an archive" : "Enter the library"}
              </button>
              {twoFactor ? (
                <button
                  type="button"
                  className="w-full text-sm text-muted-foreground underline-offset-4 hover:underline"
                  onClick={() => {
                    setTwoFactor(null);
                    setCode("");
                    setUseBackupCode(false);
                  }}
                >
                  Back to password
                </button>
              ) : null}
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

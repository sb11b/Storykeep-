"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { generateSaltB64, rememberSaltB64, unlockMessageCrypto } from "@/lib/message-crypto";

export function CryptoUnlockGate({
  enabled,
  salt,
  onUnlocked,
}: {
  enabled: boolean;
  salt: string | null;
  onUnlocked: () => void;
}) {
  const [passphrase, setPassphrase] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!passphrase.trim()) {
      setError("Enter your passphrase.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      let saltB64 = salt || undefined;
      if (!enabled) {
        saltB64 = generateSaltB64();
        const status = await api.enableMessageCrypto(saltB64);
        saltB64 = status.salt || saltB64;
        rememberSaltB64(saltB64);
      }
      if (!saltB64) {
        setError("Salt is missing. Reload and try again.");
        return;
      }
      await unlockMessageCrypto(passphrase, saltB64);
      const afterUnlock = await api.messageCryptoStatus();
      if (afterUnlock.plaintext_count > 0) {
        await api.migratePlaintextMessages(async (messages) => {
          const { encryptMessageBody } = await import("@/lib/message-crypto");
          const out = [];
          for (const item of messages) {
            const blob = await encryptMessageBody(item.content);
            out.push({ id: item.id, iv: blob.iv, ct: blob.ct });
          }
          return out;
        });
      }
      onUnlocked();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not unlock.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full min-h-[240px] flex-col items-center justify-center gap-4 px-6 py-8 text-sm">
      <p className="max-w-sm text-center text-muted-foreground">
        {enabled
          ? "Junior messages are encrypted at rest. Enter your passphrase to read or send."
          : "Encrypt Junior messages at rest. The key stays in this browser; the server stores ciphertext only."}
      </p>
      <form onSubmit={submit} className="flex w-full max-w-xs flex-col gap-3">
        <Input
          type="password"
          autoComplete={enabled ? "current-password" : "new-password"}
          placeholder="Passphrase"
          value={passphrase}
          onChange={(event) => setPassphrase(event.target.value)}
          disabled={busy}
        />
        {error ? <p className="text-xs text-destructive">{error}</p> : null}
        <Button type="submit" disabled={busy}>
          Continue
        </Button>
      </form>
    </div>
  );
}

"use client";

import { useCallback, useState } from "react";
import { isCryptoUnlocked } from "@/lib/message-crypto";
import type { MessageCryptoStatus } from "@/lib/types";

export function useCryptoGate(cryptoStatus: MessageCryptoStatus | null) {
  const [cryptoReady, setCryptoReady] = useState(() => isCryptoUnlocked());
  const [showCryptoSetup, setShowCryptoSetup] = useState(false);

  const messageCryptoEnabled = Boolean(cryptoStatus?.enabled);
  const needsCryptoUnlock = messageCryptoEnabled && !cryptoReady;
  const showCryptoGate = needsCryptoUnlock || showCryptoSetup;

  return {
    cryptoReady,
    setCryptoReady,
    showCryptoSetup,
    setShowCryptoSetup,
    messageCryptoEnabled,
    needsCryptoUnlock,
    showCryptoGate,
  };
}

export function buildCryptoUnlockHandler(
  setCryptoReady: (value: boolean) => void,
  setShowCryptoSetup: (value: boolean) => void,
  onCryptoStatusRefresh: () => void,
) {
  return () => {
    setCryptoReady(true);
    setShowCryptoSetup(false);
    onCryptoStatusRefresh();
  };
}

/** Browser-held AES-GCM-256 for Junior message bodies. Key stays in memory only. */

const PBKDF2_ITERATIONS = 310_000;
const SALT_STORAGE_KEY = "storykeep-message-crypto-salt";

let unlocked = false;
let cryptoKey: CryptoKey | null = null;
let activeSaltB64: string | null = null;

export function isCryptoUnlocked(): boolean {
  return unlocked && cryptoKey !== null;
}

export function lockMessageCrypto(): void {
  unlocked = false;
  cryptoKey = null;
  activeSaltB64 = null;
}

export function cachedSaltB64(): string | null {
  try {
    return window.localStorage.getItem(SALT_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function rememberSaltB64(salt: string): void {
  activeSaltB64 = salt;
  try {
    window.localStorage.setItem(SALT_STORAGE_KEY, salt);
  } catch {
    /* ignore */
  }
}

function b64ToBytes(value: string): Uint8Array {
  const binary = atob(value);
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) out[i] = binary.charCodeAt(i);
  return out;
}

function bytesToB64(bytes: Uint8Array): string {
  let binary = "";
  for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i]!);
  return btoa(binary);
}

async function deriveKey(passphrase: string, salt: Uint8Array): Promise<CryptoKey> {
  const material = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(passphrase),
    "PBKDF2",
    false,
    ["deriveKey"],
  );
  const saltBytes = new Uint8Array(salt);
  return crypto.subtle.deriveKey(
    { name: "PBKDF2", salt: saltBytes, iterations: PBKDF2_ITERATIONS, hash: "SHA-256" },
    material,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"],
  );
}

export async function unlockMessageCrypto(passphrase: string, saltB64: string): Promise<void> {
  const salt = b64ToBytes(saltB64);
  cryptoKey = await deriveKey(passphrase, salt);
  activeSaltB64 = saltB64;
  unlocked = true;
  rememberSaltB64(saltB64);
}

export function generateSaltB64(): string {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  return bytesToB64(salt);
}

export type EncryptedBlob = { iv: string; ct: string };

export async function encryptMessageBody(plaintext: string): Promise<EncryptedBlob> {
  if (!cryptoKey) throw new Error("Unlock message encryption first.");
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const encoded = new TextEncoder().encode(plaintext);
  const ctBuf = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, cryptoKey, encoded);
  return { iv: bytesToB64(iv), ct: bytesToB64(new Uint8Array(ctBuf)) };
}

export async function decryptMessageBody(ivB64: string, ctB64: string): Promise<string> {
  if (!cryptoKey) throw new Error("Unlock message encryption first.");
  const iv = new Uint8Array(b64ToBytes(ivB64));
  const ct = new Uint8Array(b64ToBytes(ctB64));
  const plainBuf = await crypto.subtle.decrypt({ name: "AES-GCM", iv }, cryptoKey, ct);
  return new TextDecoder().decode(plainBuf);
}

export type OpaqueOrPlainMessage = {
  id: string;
  role: "user" | "assistant";
  content?: string | null;
  iv?: string | null;
  ct?: string | null;
  encrypted?: boolean;
};

export async function decryptStoredMessage(message: OpaqueOrPlainMessage): Promise<string> {
  if (message.encrypted) {
    if (!message.iv || !message.ct) throw new Error("Missing ciphertext.");
    return decryptMessageBody(message.iv, message.ct);
  }
  return message.content || "";
}

/** Fail closed: callers must check before listing or sending bodies. */
export const CRYPTO_UNLOCKED = {
  get value() {
    return isCryptoUnlocked();
  },
};

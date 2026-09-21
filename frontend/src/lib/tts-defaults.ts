import type { TtsVoice } from "@/lib/types";

export const DEFAULT_TTS_VOICE_ID = "castor";
export const DEFAULT_TTS_VOICE_NAME = "Castor";

const BLOCKED_DEFAULT_VOICES = new Set(["altair", "eve"]);

export function fallbackTtsVoices(): TtsVoice[] {
  return [{ voice_id: DEFAULT_TTS_VOICE_ID, name: DEFAULT_TTS_VOICE_NAME }];
}

/** Pick Listen voice — Castor from server/env, never Altair as the default. */
export function resolveTtsVoiceId(
  voices: TtsVoice[],
  serverDefault?: string | null,
  stored?: string | null,
): string {
  const preferred = (serverDefault || DEFAULT_TTS_VOICE_ID).trim().toLowerCase();
  const known = new Set(voices.map((voice) => voice.voice_id.toLowerCase()));
  const storedId = (stored || "").trim().toLowerCase();
  if (storedId && !BLOCKED_DEFAULT_VOICES.has(storedId) && known.has(storedId)) {
    return voices.find((voice) => voice.voice_id.toLowerCase() === storedId)!.voice_id;
  }
  if (known.has(preferred)) {
    return voices.find((voice) => voice.voice_id.toLowerCase() === preferred)!.voice_id;
  }
  const castor = voices.find((voice) => voice.voice_id.toLowerCase() === DEFAULT_TTS_VOICE_ID);
  if (castor) return castor.voice_id;
  const notAltair = voices.find((voice) => voice.voice_id.toLowerCase() !== "altair");
  return notAltair?.voice_id || DEFAULT_TTS_VOICE_ID;
}

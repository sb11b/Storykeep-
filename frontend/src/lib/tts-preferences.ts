export const TTS_SPEED_KEY = "storykeep-tts-speed";
export const TTS_VOICE_KEY = "storykeep-tts-voice";

export const TTS_SPEEDS = [0.7, 0.8, 1, 1.2, 1.5, 1.8, 2, 2.2, 2.5, 2.8, 3] as const;

export function readStoredTtsSpeed(): number {
  if (typeof window === "undefined") return 1;
  const raw = window.localStorage.getItem(TTS_SPEED_KEY);
  const value = raw ? Number(raw) : 1;
  return TTS_SPEEDS.includes(value as (typeof TTS_SPEEDS)[number]) ? value : 1;
}

export function writeStoredTtsSpeed(rate: number) {
  try {
    window.localStorage.setItem(TTS_SPEED_KEY, String(rate));
  } catch {
    /* ignore */
  }
}

export function readStoredTtsVoice(fallback = "castor"): string {
  if (typeof window === "undefined") return fallback;
  try {
    return window.localStorage.getItem(TTS_VOICE_KEY) || fallback;
  } catch {
    return fallback;
  }
}

export function writeStoredTtsVoice(voiceId: string) {
  try {
    window.localStorage.setItem(TTS_VOICE_KEY, voiceId);
  } catch {
    /* ignore */
  }
}

import type { TtsWord } from "@/lib/types";

/**
 * Find the word index for audio.currentTime (seconds).
 * Active when start <= time < end. In gaps between words, hold the last started word.
 */
export function wordIndexAtTime(words: TtsWord[], time: number): number | null {
  if (!words.length) return null;
  for (let i = 0; i < words.length; i += 1) {
    const w = words[i];
    if (time >= w.start && time < w.end) return i;
  }
  for (let i = words.length - 1; i >= 0; i -= 1) {
    if (time >= words[i].start) return i;
  }
  return null;
}

/** Timestamps must exist and match the spoken script word count for this chunk. */
export function timestampsMatchChunk(words: TtsWord[], chunkIndex: number, chunkWordCounts: number[]): boolean {
  if (!words.length) return false;
  const expected = chunkWordCounts[chunkIndex];
  if (expected == null || expected <= 0) return false;
  return words.length === expected;
}

/** Map a global visible-word index onto a synth chunk, then seek with audio.currentTime. */
export function chunkForWord(counts: number[], wordIndex: number): { chunk: number; local: number } {
  const target = Math.max(0, wordIndex);
  let remaining = target;
  for (let i = 0; i < counts.length; i += 1) {
    const n = counts[i] ?? 0;
    if (remaining < n) return { chunk: i, local: remaining };
    remaining -= n;
  }
  const last = Math.max(0, counts.length - 1);
  return { chunk: last, local: Math.max(0, (counts[last] ?? 1) - 1) };
}

/** True when the chosen word's start is materially after playback time (highlight ahead of voice). */
export function cueAheadOfVoice(words: TtsWord[], localIndex: number, currentTime: number, epsilon = 0.02): boolean {
  const w = words[localIndex];
  if (!w) return false;
  return currentTime + epsilon < w.start;
}

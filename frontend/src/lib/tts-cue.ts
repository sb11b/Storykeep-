import type { TtsWord } from "@/lib/types";

/** Map playback time (seconds) to a word index in the same chunk's words[] array. */
export function wordIndexAtTime(words: TtsWord[], time: number): number {
  if (!words.length) return 0;
  let index = 0;
  for (let i = 0; i < words.length; i += 1) {
    if (time >= words[i].start) index = i;
    else break;
  }
  return index;
}

/** Timestamps must exist and match the spoken script word count for this chunk. */
export function timestampsMatchChunk(words: TtsWord[], chunkIndex: number, chunkWordCounts: number[]): boolean {
  if (!words.length) return false;
  const expected = chunkWordCounts[chunkIndex];
  if (expected == null || expected <= 0) return false;
  return words.length === expected;
}

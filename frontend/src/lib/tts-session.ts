type StopFn = () => void;

let activeStop: StopFn | null = null;

/** Ensure only one TTS source plays (article reader or Grok reply). */
export function claimTtsPlayback(stop: StopFn) {
  if (activeStop && activeStop !== stop) activeStop();
  activeStop = stop;
}

export function releaseTtsPlayback(stop: StopFn) {
  if (activeStop === stop) activeStop = null;
}

export function stopActiveTtsPlayback() {
  activeStop?.();
}

export function isTtsPlaybackActive() {
  return activeStop != null;
}

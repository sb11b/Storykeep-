"use client";

import { TTS_SPEEDS } from "@/lib/tts-preferences";
import type { TtsVoice } from "@/lib/types";
import { cn } from "@/lib/utils";

type GrokVoiceControlsProps = {
  visible: boolean;
  voiceId: string;
  playbackSpeed: number;
  voices: TtsVoice[];
  selectClassName: string;
  onVoiceChange: (voiceId: string) => void;
  onSpeedChange: (speed: number) => void;
};

export function GrokVoiceControls({
  visible,
  voiceId,
  playbackSpeed,
  voices,
  selectClassName,
  onVoiceChange,
  onSpeedChange,
}: GrokVoiceControlsProps) {
  return visible ? (
    <>
      <label className="inline-flex items-center gap-1">
        <span className="text-muted-foreground">Voice</span>
        <select
          aria-label="TTS voice"
          value={voiceId}
          onChange={(event) => onVoiceChange(event.target.value)}
          className={selectClassName}
        >
          {voices.map((option) => (
            <option key={option.voice_id} value={option.voice_id}>
              {option.name}
            </option>
          ))}
        </select>
      </label>
      <label className="inline-flex items-center gap-1">
        <span className="text-muted-foreground">Speed</span>
        <select
          aria-label="Playback speed"
          value={playbackSpeed}
          onChange={(event) => onSpeedChange(Number(event.target.value))}
          className={cn(selectClassName, "max-w-[4rem]")}
        >
          {TTS_SPEEDS.map((rate) => (
            <option key={rate} value={rate}>
              {rate === 1 ? "1×" : `${rate}×`}
            </option>
          ))}
        </select>
      </label>
    </>
  ) : null;
}

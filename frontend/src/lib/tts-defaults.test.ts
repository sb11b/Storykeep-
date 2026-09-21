import assert from "node:assert/strict";
import test from "node:test";
import { DEFAULT_TTS_VOICE_ID, resolveTtsVoiceId } from "./tts-defaults";

test("resolveTtsVoiceId prefers castor over altair", () => {
  const voices = [
    { voice_id: "altair", name: "Altair" },
    { voice_id: "castor", name: "Castor" },
  ];
  assert.equal(resolveTtsVoiceId(voices, DEFAULT_TTS_VOICE_ID, null), "castor");
  assert.equal(resolveTtsVoiceId(voices, DEFAULT_TTS_VOICE_ID, "altair"), "castor");
});

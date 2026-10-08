import pathlib

p = pathlib.Path(r'C:\Users\steve\Documents\Storykeep\frontend\src\components\grok-pane.tsx')
c = p.read_text(encoding='utf-8')

# 1) Remove voice.listenPhaseRef / voice.maybeRearmStsRef
c = c.replace('  const voice.listenPhaseRef = useRef<"idle" | "loading" | "playing" | "paused">("idle");\r\n  const voice.maybeRearmStsRef = useRef<() => void>(() => {});\r\n\r\n', '')

# 2) Rename voice.submitVoiceTranscript -> submitVoiceTranscript
c = c.replace('const voice.submitVoiceTranscript = useCallback(', 'const submitVoiceTranscript = useCallback(')

# 3) Fix the JSX prop
c = c.replace('onStsSubmit={voice.submitVoiceTranscript}', 'onStsSubmit={submitVoiceTranscript}')

# 4) Remove orphaned dependency block
c = c.replace('\r\n\r\n\r\n    [voice.clearSttEmptyHint],\r\n  );\r\n\r\n', '\r\n')

# 5) Remove function voice.handleVoiceChange
c = c.replace('  function voice.handleVoiceChange(next: string) {\r\n    if (voice.listen.isActive) {\r\n      voice.listenApiRef.current.stop();\r\n    }\r\n    voice.setVoiceId(next);\r\n    voice.writeStoredTtsVoice(next);\r\n    void api.updatePreferences({ tts_voice_id: next }).catch(() => {\r\n      /* ignore */\r\n    });\r\n  }\r\n\r\n', '')

# 6) Remove function voice.handleSpeedChange
c = c.replace('  function voice.handleSpeedChange(next: number) {\r\n    voice.setPlaybackSpeed(next);\r\n    voice.writeStoredTtsSpeed(next);\r\n    voice.listen.changeSpeed(next);\r\n  }\r\n\r\n', '')

p.write_text(c, encoding='utf-8')
print('Fixed grok-pane.tsx')

# Now fix the hook
p2 = pathlib.Path(r'C:\Users\steve\Documents\Storykeep\frontend\src\lib\usePaneVoice.ts')
c2 = p2.read_text(encoding='utf-8')

c2 = c2.replace('  userStoppedTtsRef: React.RefObject<boolean>;', '  userStoppedTtsRef: React.RefObject<boolean>;\r\n  streamAssistantIdRef: React.RefObject<string | null>;\r\n  writeStoredTtsAutoRead: (on: boolean) => void;')
c2 = c2.replace('  const userStoppedTtsRef = useRef(false);', '  const userStoppedTtsRef = useRef(false);\r\n  const streamAssistantIdRef = useRef<string | null>(null);')
c2 = c2.replace('    userStoppedTtsRef,', '    userStoppedTtsRef,\r\n    streamAssistantIdRef,\r\n    writeStoredTtsAutoRead,')

p2.write_text(c2, encoding='utf-8')
print('Fixed usePaneVoice.ts')

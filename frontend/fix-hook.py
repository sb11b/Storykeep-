import pathlib

p = pathlib.Path(r'src\lib\usePaneVoice.ts')
h = p.read_text(encoding='utf-8')

h = h.replace(
    'showSttEmptyHint: () => void;\n}\nexport function usePaneVoice',
    'showSttEmptyHint: () => void;\n  messagesRef: React.RefObject<ChatLine[]>;\n  micAbortRef: React.RefObject<(() => void) | null>;\n  registerMicAbort: (abort: (() => void) | null) => void;\n  registerStsRearm: (rearm: (() => void) | null) => void;\n  sttBusy: boolean;\n  registerBody: (messageId: string, element: HTMLElement | null) => void;\n}\nexport function usePaneVoice'
)

h = h.replace(
    'const streamAssistantIdRef = useRef<string | null>(null);\n  const clickedWordRef',
    'const streamAssistantIdRef = useRef<string | null>(null);\n  const micAbortRef = useRef<(() => void) | null>(null);\n  const clickedWordRef'
)

h = h.replace(
    'const handleStsModeChange = useCallback((active: boolean) => {\n    stsModeOnRef.curre',
    'const registerMicAbort = useCallback((abort: (() => void) | null) => {\n    micAbortRef.current = abort;\n  }, []);\n\n  const registerStsRearm = useCallback((rearm: (() => void) | null) => {\n    stsRearmRef.current = rearm;\n  }, []);\n\n  const registerBody = useCallback((messageId: string, element: HTMLElement | null) => {\n    if (element) bodyElementsRef.current.set(messageId, element);\n    else bodyElementsRef.current.delete(messageId);\n  }, [bodyElementsRef]);\n\n  const handleStsModeChange = useCallback((active: boolean) => {\n    stsModeOnRef.curre'
)

h = h.replace(
    "const [stsModeOn, setStsModeOn] = useState(false);\n\n  // -- refs --",
    'const [stsModeOn, setStsModeOn] = useState(false);\n  const sttBusy = sttPhase === "listening" || sttPhase === "transcribing";\n\n  // -- refs --'
)

h = h.replace(
    'showSttEmptyHint,\n  };',
    'showSttEmptyHint,\n    messagesRef,\n    micAbortRef,\n    registerMicAbort,\n    registerStsRearm,\n    sttBusy,\n    registerBody,\n  };'
)

p.write_text(h, encoding='utf-8')
print('Hook repatched')

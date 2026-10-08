import pathlib

p = pathlib.Path(r'src\components\grok-pane.tsx')
code = p.read_text(encoding='utf-8')

# Fix messagesRef: create before hook, sync on every render
code = code.replace(
    '    messagesRef: useRef<ChatLine[]>([]),\n    bodyElementsRef: useRef(new Map<string, HTMLElement>()),',
    '    messagesRef,\n    bodyElementsRef,'
)

# Add refs before busy declaration
code = code.replace(
    '  const [busy, setBusy] = useState(false);\n\n  /* ── Voice hook ── */',
    '  const messagesRef = useRef<ChatLine[]>(pane.messages);\n  messagesRef.current = pane.messages;\n  const bodyElementsRef = useRef(new Map<string, HTMLElement>());\n\n  const [busy, setBusy] = useState(false);\n\n  /* ── Voice hook ── */'
)

# Fix STS re-arm: use voice.maybeRearmStsRef instead of window.setTimeout
code = code.replace(
    'window.setTimeout(() => maybeRearmSts(), 120);',
    'voice.maybeRearmStsRef.current?.();'
)

# Add maybeRearmStsRef to hook call options
# Find the usePaneVoice options block and add it
code = code.replace(
    '    messagesRef,\n    bodyElementsRef,',
    '    messagesRef,\n    bodyElementsRef,\n    maybeRearmStsRef: useRef<(() => void) | null>(null),'
)

p.write_text(code, encoding='utf-8')
print('grok-pane.tsx patched')

# ── Fix usePaneVoice.ts: expose maybeRearmStsRef ──
h = pathlib.Path(r'src\lib\usePaneVoice.ts').read_text(encoding='utf-8')

# Add to return type interface
h = h.replace(
    '  sttBusy: boolean;\n  registerBody:',
    '  sttBusy: boolean;\n  maybeRearmStsRef: React.RefObject<(() => void) | null>;\n  registerBody:'
)

# Add to return object
h = h.replace(
    '    sttBusy,\n    registerBody,',
    '    sttBusy,\n    maybeRearmStsRef,\n    registerBody,'
)

# Wire up maybeRearmStsRef in the completion block
h = h.replace(
    'requestAutoListen(streamAssistantIdRef.current || assistantId, streamedText);\n  };',
    'requestAutoListen(streamAssistantIdRef.current || assistantId, streamedText);\n    maybeRearmStsRef.current?.();\n  };'
)

pathlib.Path(r'src\lib\usePaneVoice.ts').write_text(h, encoding='utf-8')
print('usePaneVoice.ts patched')

import pathlib

# ── Fix the hook ──
hook = pathlib.Path(r'C:\Users\steve\Documents\Storykeep\frontend\src\lib\usePaneVoice.ts').read_text(encoding='utf-8')

hook = hook.replace(
    'showSttEmptyHint: () => void;\n}\nexport function usePaneVoice',
    'showSttEmptyHint: () => void;\n  messagesRef: React.RefObject<ChatLine[]>;\n  micAbortRef: React.RefObject<(() => void) | null>;\n  registerMicAbort: (abort: (() => void) | null) => void;\n  registerStsRearm: (rearm: (() => void) | null) => void;\n  sttBusy: boolean;\n  registerBody: (messageId: string, element: HTMLElement | null) => void;\n}\nexport function usePaneVoice'
)

hook = hook.replace(
    'const streamAssistantIdRef = useRef<string | null>(null);\n  const clickedWordRef',
    'const streamAssistantIdRef = useRef<string | null>(null);\n  const micAbortRef = useRef<(() => void) | null>(null);\n  const clickedWordRef'
)

hook = hook.replace(
    'const handleStsModeChange = useCallback((active: boolean) => {\n    stsModeOnRef.curre',
    'const registerMicAbort = useCallback((abort: (() => void) | null) => {\n    micAbortRef.current = abort;\n  }, []);\n\n  const registerStsRearm = useCallback((rearm: (() => void) | null) => {\n    stsRearmRef.current = rearm;\n  }, []);\n\n  const registerBody = useCallback((messageId: string, element: HTMLElement | null) => {\n    if (element) bodyElementsRef.current.set(messageId, element);\n    else bodyElementsRef.current.delete(messageId);\n  }, [bodyElementsRef]);\n\n  const handleStsModeChange = useCallback((active: boolean) => {\n    stsModeOnRef.curre'
)

hook = hook.replace(
    'const [stsModeOn, setStsModeOn] = useState(false);\n\n  // -- refs --',
    'const [stsModeOn, setStsModeOn] = useState(false);\n  const sttBusy = sttPhase === "listening" || sttPhase === "transcribing";\n\n  // -- refs --'
)

hook = hook.replace(
    'showSttEmptyHint,\n  };',
    'showSttEmptyHint,\n    messagesRef,\n    micAbortRef,\n    registerMicAbort,\n    registerStsRearm,\n    sttBusy,\n    registerBody,\n  };'
)

pathlib.Path(r'C:\Users\steve\Documents\Storykeep\frontend\src\lib\usePaneVoice.ts').write_text(hook)
print('Hook fixed')

# ── Fix the component ──
comp = pathlib.Path(r'C:\Users\steve\Documents\Storykeep\frontend\src\components\grok-pane.tsx').read_text(encoding='utf-8')
lines = comp.split('\n')

# Move busy declaration before hook call
hook_start = None
for i, line in enumerate(lines):
    if '/* \u2500\u2500 Voice hook \u2500\u2500 */' in line:
        hook_start = i
        break

if hook_start is None:
    print('ERROR: Voice hook comment not found')
    exit(1)

hook_end = None
for i in range(hook_start, min(hook_start + 20, len(lines))):
    if lines[i].strip() == '});':
        hook_end = i
        break

busy_line = None
for i in range(hook_start, len(lines)):
    if 'const [busy, setBusy] = useState(false);' in lines[i]:
        busy_line = i
        break

if busy_line is None or busy_line < hook_start:
    print('ERROR: busy declaration not found after hook')
    exit(1)

# Extract hook block
hook_block = lines[hook_start:hook_end+1]

# Build new list
indices_to_delete = set(range(hook_start, hook_end + 1))
indices_to_delete.add(521)  # voice.requestAutoListenRef.current = requestAutoListen

# Find maybeRearmSts() call
for i, line in enumerate(lines):
    if 'maybeRearmSts()' in line and 'maybeRearmStsRef' not in line:
        indices_to_delete.add(i)
        break

new_lines = []
hook_inserted = False
for i, line in enumerate(lines):
    if i in indices_to_delete:
        continue
    if i == busy_line and not hook_inserted:
        new_lines.append(line)
        new_lines.append('')
        new_lines.extend(hook_block)
        hook_inserted = True
        continue
    new_lines.append(line)

# Add createNonceRef/createInFlightRef after sendRef
for i, line in enumerate(new_lines):
    if ');' in line and i > 300 and i < 330:
        new_lines.insert(i+1, '')
        new_lines.insert(i+2, '  /* \u2500\u2500 Chat creation refs \u2500\u2500 */')
        new_lines.insert(i+3, '  const createNonceRef = useRef<string | null>(null);')
        new_lines.insert(i+4, '  const createInFlightRef = useRef<Promise<string> | null>(null);')
        break

comp_result = '\n'.join(new_lines)
comp_result = comp_result.replace('setAutoReadReplies(on);', 'voice.setAutoReadReplies(on);')
comp_result = comp_result.replace('onRegisterBody={registerBody}', 'onRegisterBody={voice.registerBody}')
comp_result = comp_result.replace('onListen={requestListen}', 'onListen={voice.requestListen}')

pathlib.Path(r'C:\Users\steve\Documents\Storykeep\frontend\src\components\grok-pane.tsx').write_text(comp_result, encoding='utf-8')
print('Component fixed')


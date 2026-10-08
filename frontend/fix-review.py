import pathlib

comp = pathlib.Path(r'src\components\grok-pane.tsx')
code = comp.read_text(encoding='utf-8')

# 1. Strip BOM
if code.startswith('\ufeff'):
    code = code[1:]

# 2. Fix inline refs → pass the variables created above
code = code.replace('messagesRef: useRef<ChatLine[]>([]),', 'messagesRef,')
code = code.replace('bodyElementsRef: useRef(new Map<string, HTMLElement>()),', 'bodyElementsRef,')

# 3. Restore STS re-arm after auto-listen triggers
code = code.replace(
    'voice.requestAutoListen(voice.streamAssistantIdRef.current ?? assistantId, streamedText);',
    'voice.requestAutoListen(voice.streamAssistantIdRef.current ?? assistantId, streamedText);\n        voice.maybeRearmStsRef.current?.();'
)

comp.write_text(code, encoding='utf-8')
print('✓ Patched')

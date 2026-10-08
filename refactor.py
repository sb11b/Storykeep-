#!/usr/bin/env python3
import re

def main():
    with open('frontend/src/components/grok-pane.tsx', 'r', encoding='utf-8') as f:
        lines = f.readlines()

    print(f'Total lines: {len(lines)}')

    # Find voice-related line ranges (same logic as before)
    voice_start = None
    voice_end = None
    for i, line in enumerate(lines):
        if 'const [voiceId' in line:
            voice_start = i
        if voice_start and i > voice_start and 'const micAbortRef' in line:
            voice_end = i
            break

    refs_start = None
    refs_end = None
    for i, line in enumerate(lines):
        if 'const pendingListenRef' in line:
            refs_start = i
        if refs_start and i > refs_start and 'const streamAssistantIdRef' in line:
            refs_end = i
            break

    effect1_start = None
    effect1_end = None
    for i, line in enumerate(lines):
        if effect1_start is None and i > 480 and 'useEffect(() => {' in line:
            for j in range(i+1, min(i+10, len(lines))):
                if 'getPreferences' in lines[j]:
                    effect1_start = i
                    break
        if effect1_start is not None and i > effect1_start and line.strip() == '}, [defaultTtsVoiceId, ttsVoices]);':
            effect1_end = i + 1
            break

    listen_start = None
    listen_end = None
    for i, line in enumerate(lines):
        if 'useGrokMessageListen({' in line:
            listen_start = i
        if listen_start and i > listen_start and line.strip() == '});':
            listen_end = i + 1
            break

    handlers_start = None
    handlers_end = None
    for i, line in enumerate(lines):
        if 'function listenLatestReply' in line:
            handlers_start = i
        if handlers_start and 'function listenFromHere' in line:
            brace_count = 0
            for j in range(i, min(i + 200, len(lines))):
                brace_count += lines[j].count('{')
                brace_count -= lines[j].count('}')
                if brace_count == 0 and j > i:
                    handlers_end = j + 1
                    break
            break

    stt_start = None
    stt_end = None
    for i, line in enumerate(lines):
        if 'const clearSttEmptyHint' in line:
            stt_start = i
        if stt_start and 'const handleStsModeChange' in line:
            brace_count = 0
            for j in range(i, min(i + 50, len(lines))):
                brace_count += lines[j].count('{')
                brace_count -= lines[j].count('}')
                if brace_count == 0 and j > i:
                    stt_end = j + 1
                    break
            break

    voice_change_start = None
    voice_change_end = None
    for i, line in enumerate(lines):
        if 'function handleVoiceChange' in line:
            voice_change_start = i
        if voice_change_start and 'function handleSpeedChange' in line:
            brace_count = 0
            for j in range(i, min(i + 50, len(lines))):
                brace_count += lines[j].count('{')
                brace_count -= lines[j].count('}')
                if brace_count == 0 and j > i:
                    voice_change_end = j + 1
                    break
            break

    print(f'Voice block: lines {voice_start + 1} to {voice_end}')
    print(f'Refs block: lines {refs_start + 1} to {refs_end}')
    print(f'Effect 1: lines {effect1_start + 1 if effect1_start else None} to {effect1_end}')
    print(f'Listen hook: lines {listen_start + 1 if listen_start else None} to {listen_end}')
    print(f'Handlers: lines {handlers_start + 1 if handlers_start else None} to {handlers_end}')
    print(f'STT handlers: lines {stt_start + 1 if stt_start else None} to {stt_end}')
    print(f'Voice change: lines {voice_change_start + 1 if voice_change_start else None} to {voice_change_end}')

    # Now do the actual refactoring
    new_lines = []
    for i, line in enumerate(lines):
        line_num = i + 1  # 1-indexed

        # Skip voice state declarations (lines 286-298, but keep uploadingFiles at 291)
        if 286 <= line_num <= 298 and line_num != 291:
            continue

        # Skip voice refs (lines 329-337)
        if 329 <= line_num <= 337:
            continue

        # Skip voice init effect (lines 487-508)
        if 487 <= line_num <= 508:
            continue

        # Skip useGrokMessageListen call (lines 576-593)
        if 576 <= line_num <= 593:
            continue

        # Skip handler functions (lines 632-764)
        if 632 <= line_num <= 764:
            continue

        # Skip STT handlers (lines 1742-1778)
        if 1742 <= line_num <= 1778:
            continue

        # Skip voice change handlers (lines 2286-2301)
        if 2286 <= line_num <= 2301:
            continue

        # Insert hook call after bodyElementsRef and messagesRef are set up
        # This is at line 355 (0-indexed 354): messagesRef.current = pane.messages;
        if line_num == 355:
            new_lines.append(line)
            new_lines.append('  const voice = usePaneVoice({\n')
            new_lines.append('    ttsEnabled,\n')
            new_lines.append('    locked,\n')
            new_lines.append('    panelOpen,\n')
            new_lines.append('    busy,\n')
            new_lines.append('    inFlightRef,\n')
            new_lines.append('    onStopArticleListen,\n')
            new_lines.append('    onActivateListen,\n')
            new_lines.append('    paneMessages: pane.messages,\n')
            new_lines.append('    defaultTtsVoiceId,\n')
            new_lines.append('    ttsVoices,\n')
            new_lines.append('    bodyElementsRef,\n')
            new_lines.append('    messagesRef,\n')
            new_lines.append('  });\n')
            continue

        new_lines.append(line)

    with open('frontend/src/components/grok-pane.tsx', 'w', encoding='utf-8') as f:
        f.writelines(new_lines)

    print(f'\nOriginal lines: {len(lines)}')
    print(f'New lines: {len(new_lines)}')
    print(f'Removed: {len(lines) - len(new_lines)}')

if __name__ == '__main__':
    main()

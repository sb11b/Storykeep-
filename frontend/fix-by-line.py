import pathlib

p = pathlib.Path(r'C:\Users\steve\Documents\Storykeep\frontend\src\components\grok-pane.tsx')
lines = p.read_text(encoding='utf-8').split('\n')

# Delete from bottom to top so earlier line numbers don't shift
# 3) Delete function voice.handleVoiceChange + handleSpeedChange (lines 2013-2029)
# 2) Delete orphaned dependency block (lines 1509-1512)
# 1) Delete voice.listenPhaseRef/maybeRearmStsRef (lines 510-512)

to_delete = set()

# Lines 2013-2029: handleVoiceChange (11 lines) + handleSpeedChange (4 lines) + blank (1 line) = 16 lines
for i in range(2012, 2029):
    to_delete.add(i)

# Lines 1509-1512: orphaned block (4 lines)
for i in range(1508, 1512):
    to_delete.add(i)

# Lines 510-512: stray refs (3 lines)
for i in range(509, 512):
    to_delete.add(i)

new_lines = [line for i, line in enumerate(lines) if i not in to_delete]
p.write_text('\n'.join(new_lines), encoding='utf-8')
print(f'Deleted {len(to_delete)} lines. New file: {len(new_lines)} lines')

import pathlib

p = pathlib.Path(r'C:\Users\steve\Documents\Storykeep\frontend\src\components\grok-pane.tsx')
lines = p.read_text(encoding='utf-8').split('\n')

# Print what's actually at the error lines so we can see exact content
for n in [509, 510, 511, 512, 1489, 1490, 1491, 1498, 1499, 1500, 1501, 1508, 1509, 1510, 1511, 2012, 2013, 2014, 2022, 2023, 2024, 2025, 2028, 2029]:
    if n < len(lines):
        print(f"LINE {n+1}: {repr(lines[n][:120])}")

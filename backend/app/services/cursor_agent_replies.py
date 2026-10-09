from __future__ import annotations

import re

_LOCAL_MERGE_RE = re.compile(
    r"needs merge|unmerged files|resolve your current index|Merging is not possible|Pulling is not possible"
    r"|(?:ubuntu|ubantu).{0,80}(?:error|paste|fix|correct)"
    r"|(?:error|paste|fix|correct).{0,80}(?:ubuntu|ubantu)"
    r"|(?:fix|correct) the error.{0,50}paste",
    re.I | re.S,
)

LOCAL_MERGE_REPLY = """Your local Storykeep checkout is in the middle of a merge. GitHub main already has this work. Do not push.

```bash
cd ~/Storykeep
git merge --abort
git fetch github
git checkout main
git reset --hard github/main
```
"""


_WSL_SWITCH_RE = re.compile(
    r"powershell\s*wsl|powershellwsl|from powershell to wsl|switch .{0,40}wsl|"
    r"wsl\s*-d|-d\s*ubuntu|dubantu|commandnotfound",
    re.I,
)

WSL_SWITCH_REPLY = """You are in PowerShell. The prompt starts with PS.

Type this on one line. Leave a space between each word:

```powershell
wsl -d Ubuntu
```

Ubuntu starts, and the prompt no longer starts with PS.

If Windows says that name is missing, list the installed names:

```powershell
wsl -l -v
```

Use the name from that list, still with spaces:

```powershell
wsl -d Ubuntu
```

Do not type powershell in front of wsl.
Do not join the words into powershellwsl- or -dUbuntu.
"""


def wsl_switch_reply(message: str) -> str | None:
    text = message or ""
    if re.search(r"needs merge|unmerged files|resolve your current index", text, re.I):
        return None
    if _WSL_SWITCH_RE.search(text):
        return WSL_SWITCH_REPLY
    return None


_DIVERGED_FF_RE = re.compile(
    r"not possible to fast-forward|can(?:'t|not) be fast-forwarded|diverging branches",
    re.I,
)

DIVERGED_FF_REPLY = """Your local main already matches GitHub. The reset landed. Stop. Do not run more git commands.

"There is no merge to abort" is fine. No merge was in progress.

Leave cursor/next-step-in-sequence-b515 alone. That branch is one commit beside main, so a fast-forward cannot work. Do not merge that branch into main. Do not push. "Everything up-to-date" is the correct push result.

Junior read the word "is" in "Your branch is behind" as a branch name. Ignore "Branch 'is' does not exist."
"""


def diverged_ff_reply(message: str) -> str | None:
    """Git already finished. A fast-forward failure is not a Cloud Agent task."""
    from app.services import junior_model

    text = message or ""
    if junior_model.fast_forward_reply(text) is not None:
        return None
    if _DIVERGED_FF_RE.search(text):
        return DIVERGED_FF_REPLY
    if re.search(r"branch\s+['\"]is['\"]\s+does not exist", text, re.I) and re.search(
        r"fast-forward|github/main|merge --ff-only|MERGE_HEAD missing",
        text,
        re.I,
    ):
        return DIVERGED_FF_REPLY
    return None


def local_merge_repair(message: str) -> str | None:
    if wsl_switch_reply(message) or diverged_ff_reply(message):
        return None
    if _LOCAL_MERGE_RE.search(message or ""):
        return LOCAL_MERGE_REPLY
    return None


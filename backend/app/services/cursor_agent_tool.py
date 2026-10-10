"""Back-compat re-export shim: the Cursor Cloud Agent code now lives in cursor_agent_transport, cursor_agent_start, cursor_agent_run, cursor_agent_instructions, and cursor_agent_bugbot; this module keeps the cursor_agent_tool.<name> names resolving for existing callers."""

from __future__ import annotations

# Re-exported from cursor_agent_transport so existing callers
# (chat_stream, junior_model) keep resolving
# cursor_agent_tool.<name>; the canonical home is cursor_agent_transport.
from app.services.cursor_agent_transport import TIMEOUT_SEC, configured, owner_can_use
# Re-exported from cursor_agent_start so existing callers keep resolving
# cursor_agent_tool.<name>; the canonical home is cursor_agent_start
# (extracted start cluster: constants, response formatting, entry points).
from app.services.cursor_agent_start import (
    CURSOR_OFF_APPEND,
    CURSOR_ON_APPEND,
    execute_tool_call,
    start_agent,
)

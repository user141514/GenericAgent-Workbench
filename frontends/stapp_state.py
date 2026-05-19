"""stapp.py session_state default initialisation.

Does NOT import streamlit.  Callers pass ``st.session_state`` explicitly.
"""

from __future__ import annotations


_DEFAULTS: dict[str, object] = {
    "autonomous_enabled": False,
    "show_history": False,
    "show_memory": False,
    "show_watchtower": False,
    "compact_assistant_history": True,
    "uploaded_files": None,
    "processed_upload_cache": None,
    "upload_widget_nonce": 0,
    "agent_running": False,
    "_stream_dq": None,
    "content_event": 0,
    "routing_mode": "auto",
    "pending_routing": None,
    "partial_response": "",
    "current_turn": 0,
    "stream_started": False,
    "stop_requested": False,
    "stop_requested_at": 0.0,
    "orchestrator": None,
    "last_submitted_input": "",
    "messages": None,
    "msg_counter": 0,
}

_LIST_DEFAULTS = frozenset({"uploaded_files", "messages"})
_DICT_DEFAULTS = frozenset({"processed_upload_cache"})


def ensure_stapp_session_state(state: object) -> None:
    """Ensure required Streamlit ``session_state`` keys exist.

    *state* is ``st.session_state`` or a compatible dict-like object.
    Only initialises missing keys — never overwrites existing values.
    No Streamlit dependency, no side effects beyond writing to *state*.
    """
    for key, default in _DEFAULTS.items():
        if key not in state:
            if key in _LIST_DEFAULTS:
                state[key] = []
                continue
            if key in _DICT_DEFAULTS:
                state[key] = {}
                continue
            state[key] = default

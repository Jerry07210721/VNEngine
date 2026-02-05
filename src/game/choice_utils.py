from __future__ import annotations


def normalize_choice_timeout_config(entry: dict | None, option_count: int) -> tuple[float | None, int]:
    """Normalize choice timeout/default config from a choice entry.

    Returns (timeout_seconds_or_None, default_index).

    - timeout: clamped to [0, 600]; 0/invalid -> None
    - default_index: 0-based; invalid -> -1
    """

    if not isinstance(option_count, int) or option_count < 0:
        option_count = 0

    if not isinstance(entry, dict):
        return None, -1

    # timeout
    try:
        timeout = float(entry.get("choice_timeout_seconds", 0.0) or 0.0)
    except Exception:
        timeout = 0.0
    timeout = max(0.0, min(600.0, timeout))
    timeout_norm: float | None = timeout if timeout > 0.0 else None

    # default index
    raw_idx = entry.get("choice_default_index", -1)
    try:
        default_idx = int(raw_idx)
    except Exception:
        default_idx = -1

    if default_idx < 0 or default_idx >= option_count:
        default_idx = -1

    return timeout_norm, default_idx

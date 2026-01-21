# -*- coding: utf-8 -*-
"""Save slot helper utilities.

Pure utilities (no pygame) so they can be unit-tested.
"""

from __future__ import annotations

import math
from pathlib import Path

AUTO_SAVE_SLOT = 0
DEFAULT_PAGE_SIZE = 10


def slot_file_path(save_dir: Path, slot: int) -> Path:
    """Return the save file path for a slot.

    - Manual slots: 1..N => slot_<n>.json
    - Auto slot: 0 => autosave.json
    """
    if int(slot) == AUTO_SAVE_SLOT:
        return save_dir / "autosave.json"
    return save_dir / f"slot_{int(slot)}.json"


def page_count(total_slots: int, page_size: int = DEFAULT_PAGE_SIZE) -> int:
    total = max(0, int(total_slots))
    size = max(1, int(page_size))
    return max(1, int(math.ceil(total / size)))


def clamp_page(page: int, total_slots: int, page_size: int = DEFAULT_PAGE_SIZE) -> int:
    p = int(page)
    max_pages = page_count(total_slots, page_size)
    if p < 0:
        return 0
    if p >= max_pages:
        return max_pages - 1
    return p


def digit_to_page_pos(digit: int, page_size: int = DEFAULT_PAGE_SIZE) -> int | None:
    """Map a digit key (0-9) to 1..page_size position.

    For 10-per-page: 1..9 => 1..9, 0 => 10.
    """
    d = int(digit)
    size = max(1, int(page_size))
    if size != 10:
        # Generic mapping: only accept 1..min(9,size)
        if 1 <= d <= min(9, size):
            return d
        return None
    if 1 <= d <= 9:
        return d
    if d == 0:
        return 10
    return None


def page_pos_to_slot(page: int, pos: int, page_size: int = DEFAULT_PAGE_SIZE) -> int:
    p = max(0, int(page))
    size = max(1, int(page_size))
    position = int(pos)
    return p * size + position


def digit_to_slot(page: int, digit: int, page_size: int = DEFAULT_PAGE_SIZE) -> int | None:
    pos = digit_to_page_pos(digit, page_size=page_size)
    if pos is None:
        return None
    return page_pos_to_slot(page, pos, page_size=page_size)

# -*- coding: utf-8 -*-

from pathlib import Path

from src.game.save_slot_utils import (
    AUTO_SAVE_SLOT,
    clamp_page,
    digit_to_slot,
    page_count,
    slot_file_path,
    slot_thumbnail_path,
)


def test_slot_file_path_manual_and_auto():
    base = Path("C:/tmp/saves")
    assert slot_file_path(base, AUTO_SAVE_SLOT).name == "autosave.json"
    assert slot_file_path(base, 1).name == "slot_1.json"
    assert slot_file_path(base, 15).name == "slot_15.json"


def test_slot_thumbnail_path_manual_and_auto():
    base = Path("C:/tmp/saves")
    assert slot_thumbnail_path(base, AUTO_SAVE_SLOT).name == "autosave_thumb.png"
    assert slot_thumbnail_path(base, 1).name == "slot_1_thumb.png"
    assert slot_thumbnail_path(base, 15).name == "slot_15_thumb.png"


def test_page_count_and_clamp():
    assert page_count(0, 10) == 1
    assert page_count(1, 10) == 1
    assert page_count(10, 10) == 1
    assert page_count(11, 10) == 2

    assert clamp_page(-1, 25, 10) == 0
    assert clamp_page(0, 25, 10) == 0
    assert clamp_page(1, 25, 10) == 1
    assert clamp_page(2, 25, 10) == 2
    assert clamp_page(3, 25, 10) == 2


def test_digit_to_slot_default_10_per_page():
    # page 0
    assert digit_to_slot(0, 1) == 1
    assert digit_to_slot(0, 9) == 9
    assert digit_to_slot(0, 0) == 10

    # page 1
    assert digit_to_slot(1, 1) == 11
    assert digit_to_slot(1, 0) == 20

    # invalid
    assert digit_to_slot(0, -1) is None
    assert digit_to_slot(0, 10) is None

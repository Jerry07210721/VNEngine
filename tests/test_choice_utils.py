from __future__ import annotations

from src.game.choice_utils import normalize_choice_timeout_config


def test_normalize_choice_timeout_config_defaults():
    t, idx = normalize_choice_timeout_config({}, 3)
    assert t is None
    assert idx == -1


def test_normalize_choice_timeout_config_valid():
    t, idx = normalize_choice_timeout_config({"choice_timeout_seconds": 5, "choice_default_index": 1}, 3)
    assert t == 5.0
    assert idx == 1


def test_normalize_choice_timeout_config_clamps_and_invalid_default():
    t, idx = normalize_choice_timeout_config({"choice_timeout_seconds": 9999, "choice_default_index": 10}, 2)
    assert t == 600.0
    assert idx == -1


def test_normalize_choice_timeout_config_timeout_zero_disables():
    t, idx = normalize_choice_timeout_config({"choice_timeout_seconds": 0, "choice_default_index": 0}, 2)
    assert t is None
    assert idx == 0


def test_normalize_choice_timeout_config_non_dict_entry():
    t, idx = normalize_choice_timeout_config(None, 2)
    assert t is None
    assert idx == -1

# -*- coding: utf-8 -*-
"""Secret storage helpers for VNEngine.

This module provides at-rest encryption for sensitive values stored in YAML config
files (e.g., API keys). It uses a per-user Fernet key stored outside the project
folder so secrets can be safely committed in encrypted form.

Design goals:
- ConfigManager keeps secrets decrypted in memory for normal usage.
- On disk, secrets are stored encrypted with a clear prefix.
- The encryption key is stored in the user's data directory (not the repo).

Environment overrides:
- VNENGINE_SECRET_KEY: a base64url-encoded Fernet key string.
- VNENGINE_SECRET_KEY_FILE: path to a file containing the Fernet key.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

try:
    from platformdirs import user_data_dir
except Exception:  # pragma: no cover
    user_data_dir = None  # type: ignore


_ENC_PREFIX = "ENC::"  # visible marker for encrypted values


def get_secret_key_storage_path() -> Optional[Path]:
    """Return the key file path if a file is used, else None.

    If VNENGINE_SECRET_KEY is set, the key is provided via env var and no file
    path applies.
    If VNENGINE_SECRET_KEY_FILE is set, that file is used.
    Otherwise, the default per-user file is used.
    """
    if os.environ.get("VNENGINE_SECRET_KEY"):
        return None
    env_key_file = os.environ.get("VNENGINE_SECRET_KEY_FILE")
    if env_key_file:
        return Path(env_key_file)
    return _default_key_path()


def get_secret_key_storage_display() -> str:
    """Human-readable description for UI."""
    if os.environ.get("VNENGINE_SECRET_KEY"):
        return "环境变量 VNENGINE_SECRET_KEY（不落盘）"
    env_key_file = os.environ.get("VNENGINE_SECRET_KEY_FILE")
    if env_key_file:
        return str(Path(env_key_file))
    return str(_default_key_path())


def _default_key_path() -> Path:
    if user_data_dir is not None:
        base = Path(user_data_dir(appname="VNEngine", appauthor="VNEngine"))
    else:  # pragma: no cover
        base = Path.home() / ".vnengine"
    return base / "secret.key"


def _read_key_from_file(path: Path) -> Optional[bytes]:
    try:
        data = path.read_text(encoding="utf-8").strip()
        if not data:
            return None
        return data.encode("utf-8")
    except Exception:
        return None


def _load_or_create_key_bytes() -> bytes:
    env_key = os.environ.get("VNENGINE_SECRET_KEY")
    if env_key:
        return env_key.strip().encode("utf-8")

    env_key_file = os.environ.get("VNENGINE_SECRET_KEY_FILE")
    if env_key_file:
        kb = _read_key_from_file(Path(env_key_file))
        if kb:
            return kb

    key_path = _default_key_path()
    kb = _read_key_from_file(key_path)
    if kb:
        return kb

    key_path.parent.mkdir(parents=True, exist_ok=True)
    kb = Fernet.generate_key()
    try:
        key_path.write_text(kb.decode("utf-8"), encoding="utf-8")
    except Exception:
        # If we fail to persist, we can still use the generated key for this run,
        # but secrets won't be decryptable next time.
        pass
    return kb


def _fernet() -> Fernet:
    return Fernet(_load_or_create_key_bytes())


def is_encrypted(value: object) -> bool:
    return isinstance(value, str) and value.startswith(_ENC_PREFIX)


def encrypt_str(plain: str) -> str:
    if plain is None:
        return plain
    if not isinstance(plain, str):
        plain = str(plain)
    if plain == "" or is_encrypted(plain):
        return plain
    token = _fernet().encrypt(plain.encode("utf-8")).decode("utf-8")
    return f"{_ENC_PREFIX}{token}"


def decrypt_str(value: str) -> str:
    if value is None:
        return value
    if not isinstance(value, str):
        return str(value)
    if not is_encrypted(value):
        return value
    token = value[len(_ENC_PREFIX) :]
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        # Wrong key or corrupted value; keep original so callers can show it.
        return value
    except Exception:
        return value

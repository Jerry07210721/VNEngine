# -*- coding: utf-8 -*-
"""Basic quality validator placeholder."""

from typing import List, Tuple, Iterable
from pathlib import Path


class QualityValidator:
    """Performs lightweight checks (existence/extension) to gate downstream steps."""

    def validate_files(self, files: Iterable[str], allowed_exts: Iterable[str] = ()) -> Tuple[bool, List[str]]:
        missing_or_bad: List[str] = []
        allowed_set = {ext.lower().lstrip('.') for ext in allowed_exts} if allowed_exts else None

        for file_path in files:
            p = Path(file_path)
            if not p.exists():
                missing_or_bad.append(file_path)
                continue
            if allowed_set is not None and p.suffix.lower().lstrip('.') not in allowed_set:
                missing_or_bad.append(file_path)

        return (len(missing_or_bad) == 0, missing_or_bad)

    def validate_naming(self, files: Iterable[str], required_prefix: str = "") -> Tuple[bool, List[str]]:
        bad: List[str] = []
        for file_path in files:
            name = Path(file_path).name
            if required_prefix and not name.startswith(required_prefix):
                bad.append(file_path)
        return (len(bad) == 0, bad)

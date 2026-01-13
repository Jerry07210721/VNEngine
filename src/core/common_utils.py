# -*- coding: utf-8 -*-
"""Common utilities for VNEngine core."""
import os
import sys
from pathlib import Path


def get_project_root() -> Path:
    """Return project root directory (Windows-friendly)."""
    return Path(os.path.abspath(sys.argv[0])).parent.parent


def ensure_dir_exists(dir_path: str) -> None:
    """Create directory if missing."""
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)


def validate_project_path(file_path: str):
    """Validate project file path (expects .vngproj)."""
    if not file_path.endswith(".vngproj"):
        return f"{file_path} 不是有效的工程文件（后缀需为.vngproj）"
    return None


def get_default_resource_dir(project_path: str) -> str:
    """Get default resource directory beside project file."""
    project_dir = os.path.dirname(project_path)
    resource_dir = os.path.join(project_dir, "resources")
    ensure_dir_exists(resource_dir)
    return resource_dir

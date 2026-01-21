"""图像工具：安全命名、轻量校验、可选尺寸调整（Pillow可选依赖）。"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Tuple

try:  # Pillow 是可选依赖
    from PIL import Image
except Exception:  # pragma: no cover - pillow 缺失时退化
    Image = None


_slug_pattern = re.compile(r"[^a-z0-9]+")


def slugify_name(name: str, max_length: int = 64) -> str:
    """将任意名称转换为安全的、可用于文件名的 slug。"""
    normalized = name.strip().lower()
    normalized = normalized.encode("ascii", errors="ignore").decode()
    slug = _slug_pattern.sub("_", normalized).strip("_")
    if not slug:
        slug = "item"
    return slug[:max_length]


def ensure_extension(path: Path | str, ext: str) -> Path:
    """强制文件后缀为 ext（自动补全点）。"""
    p = Path(path)
    suffix = ext if ext.startswith(".") else f".{ext}"
    return p.with_suffix(suffix)


def validate_image_format(path: Path, allowed: Optional[set[str]] = None) -> bool:
    """仅基于后缀的轻量校验，不读取文件字节。"""
    allowed = allowed or {".png", ".jpg", ".jpeg"}
    return path.suffix.lower() in allowed


def get_image_size(path: Path) -> Optional[Tuple[int, int]]:
    """返回图像尺寸，Pillow 不可用或读取失败时返回 None。"""
    if Image is None:
        return None
    try:
        with Image.open(path) as img:
            return img.size
    except Exception:
        return None


def ensure_rgba(path: Path, dest: Optional[Path] = None) -> Optional[Path]:
    """确保图像为 RGBA；若 dest 为空则覆盖原文件。Pillow 不可用则返回 None。"""
    if Image is None:
        return None
    try:
        with Image.open(path) as img:
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            dest_path = dest or path
            img.save(dest_path)
            return dest_path
    except Exception:
        return None


def resize_image_to_fit(
    path: Path,
    max_width: int,
    max_height: int,
    dest: Optional[Path] = None,
) -> Optional[Path]:
    """按比例缩放使图像不超过指定尺寸；未缩放则直接返回原路径。"""
    if Image is None:
        return None
    try:
        with Image.open(path) as img:
            width, height = img.size
            scale = min(max_width / width, max_height / height, 1.0)
            if scale >= 1.0:
                return path
            new_size = (int(width * scale), int(height * scale))
            resized = img.resize(new_size, Image.LANCZOS)
            dest_path = dest or path
            resized.save(dest_path)
            return dest_path
    except Exception:
        return None

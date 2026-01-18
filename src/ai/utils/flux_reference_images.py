# -*- coding: utf-8 -*-
"""FLUX 参考图处理工具。

目标：
- 支持 1~3 张参考图（JPG/PNG/WebP）
- 自动解析 MIME/尺寸/文件大小
- 发送前尽量压缩到安全体积，避免 413
- 生成 data URL 格式的 b64（data:image/...;base64,xxx）

注：Pillow 为可选依赖；缺失时仅做最小处理（不缩放/不重编码）。
"""

from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:  # Pillow 是可选依赖
    from PIL import Image
except Exception:  # pragma: no cover
    Image = None


_ALLOWED_SUFFIX_TO_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def _guess_mime(path: Path) -> str:
    return _ALLOWED_SUFFIX_TO_MIME.get(path.suffix.lower(), "image/png")


def _encode_image(img, mime: str) -> bytes:
    buf = io.BytesIO()
    if mime == "image/png":
        # PNG：尽量压缩
        img.save(buf, format="PNG", optimize=True, compress_level=9)
    elif mime in {"image/jpg", "image/jpeg"}:
        # JPEG：用 RGB，调质量
        if getattr(img, "mode", "RGB") not in {"RGB", "L"}:
            img = img.convert("RGB")
        # 使用较高质量起步，后续由外层控制降级
        img.save(buf, format="JPEG", quality=85, optimize=True)
    elif mime == "image/webp":
        if getattr(img, "mode", "RGB") not in {"RGB", "L"}:
            img = img.convert("RGB")
        img.save(buf, format="WEBP", quality=85, method=6)
    else:
        img.save(buf, format="PNG", optimize=True, compress_level=9)
    return buf.getvalue()


def _resize_with_max_side(img, max_side: int):
    w, h = img.size
    scale = min(1.0, float(max_side) / float(max(w, h)))
    if scale >= 0.999:
        return img
    new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
    return img.resize(new_size)


def prepare_flux_reference_image(
    image_path: Path,
    max_bytes: int = 420_000,
    max_sides: Tuple[int, ...] = (1024, 900, 768, 640, 512),
) -> Optional[Dict[str, Any]]:
    """将本地图片处理成 FLUX images[] 所需结构。

    返回：{"type","size","w","h","b64"}（b64 为 data URL）。
    """

    path = Path(image_path)
    if not path.exists() or not path.is_file():
        return None

    mime = _guess_mime(path)
    raw = path.read_bytes()

    # Pillow 不可用：不做重编码/缩放，尽量按原始 bytes 发送（可能过大）。
    if Image is None:
        b64 = base64.b64encode(raw).decode("ascii")
        # 尺寸未知
        return {
            "type": mime,
            "size": len(raw),
            "w": 0,
            "h": 0,
            "b64": f"data:{mime};base64,{b64}",
        }

    try:
        img = Image.open(io.BytesIO(raw))
        # 统一走 RGBA/ RGB
        if mime == "image/png":
            img = img.convert("RGBA")
        else:
            img = img.convert("RGB")

        # 多级缩放 + 重编码，尽量压到 max_bytes
        data = None
        final_img = img
        for max_side in max_sides:
            scaled = _resize_with_max_side(img, max_side)
            data_try = _encode_image(scaled, mime)
            data = data_try
            final_img = scaled
            if len(data_try) <= max_bytes:
                break

        if data is None:
            return None

        if len(data) > max_bytes:
            # 仍过大，放弃，避免 413
            return None

        w, h = final_img.size
        b64 = base64.b64encode(data).decode("ascii")
        return {
            "type": mime,
            "size": len(data),
            "w": int(w),
            "h": int(h),
            "b64": f"data:{mime};base64,{b64}",
        }

    except Exception:
        return None


def prepare_flux_reference_images(paths: Iterable[Path], limit: int = 3) -> List[Dict[str, Any]]:
    """批量处理参考图（过滤失败项），最多 limit 张。"""

    out: List[Dict[str, Any]] = []
    for p in paths:
        if len(out) >= limit:
            break
        item = prepare_flux_reference_image(Path(p))
        if item:
            out.append(item)
    return out

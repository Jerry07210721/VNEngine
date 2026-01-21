"""音频工具：命名、轻量校验与时长读取（可选依赖 moviepy/wave）。"""
from __future__ import annotations

import contextlib
import wave
from pathlib import Path
from typing import Optional

try:  # moviepy 用于时长读取，可选
    from moviepy.editor import AudioFileClip
except Exception:  # pragma: no cover
    AudioFileClip = None

from .image_utils import slugify_name, ensure_extension


def validate_audio_format(path: Path, allowed: Optional[set[str]] = None) -> bool:
    """基于后缀的轻量校验，不解析音频字节。"""
    allowed = allowed or {".mp3", ".wav", ".ogg"}
    return path.suffix.lower() in allowed


def get_audio_duration(path: Path) -> Optional[float]:
    """返回音频秒数；优先使用 moviepy，其次 wave(仅 WAV)。失败返回 None。"""
    if AudioFileClip is not None:
        try:
            with AudioFileClip(str(path)) as clip:
                return float(clip.duration)
        except Exception:
            pass

    if path.suffix.lower() == ".wav":
        try:
            with contextlib.closing(wave.open(str(path), "rb")) as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                return frames / float(rate)
        except Exception:
            return None

    return None


def voice_filename(speaker: str, slug: str, index: int, ext: str = "mp3") -> str:
    """生成统一的语音文件名，如 'alice_line_001.mp3'。"""
    base = slugify_name(slug or "line")
    sp = slugify_name(speaker or "voice")
    suffix = f"{index:03d}"
    return ensure_extension(Path(f"{sp}_{base}_{suffix}"), ext).name


def bgm_filename(name: str, ext: str = "mp3") -> str:
    """生成统一的 BGM 文件名。"""
    base = slugify_name(name or "bgm")
    return ensure_extension(Path(base), ext).name

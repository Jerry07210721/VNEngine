# -*- coding: utf-8 -*-
"""语音情绪/语气相关的纯函数工具。

目的：
- VoiceAgent 与 UI 共用同一套“情绪归一化→ext 参数”逻辑
- 支持中文/英文情绪输入
- ext 统一为 8 维，且值 clamp 到 0-1
"""

from __future__ import annotations

from typing import Any, Dict

EXT_KEYS = [
    "happy",
    "angry",
    "sad",
    "afraid",
    "disgusted",
    "melancholic",
    "surprised",
    "calm",
]


def normalize_emotion(emotion: str) -> str:
    if not isinstance(emotion, str):
        return "neutral"

    s = emotion.strip().lower()
    if not s:
        return "neutral"

    # 英文/代码态
    aliases = {
        "neutral": ["neutral", "normal", "default", "none"],
        "calm": ["calm", "peace", "peaceful"],
        "happy": ["happy", "joy", "cheerful", "glad"],
        "sad": ["sad", "down"],
        "melancholic": ["melancholic", "melancholy", "blue"],
        "angry": ["angry", "rage", "mad"],
        "afraid": ["afraid", "fear", "scared", "nervous"],
        "disgusted": ["disgusted", "disgust"],
        "surprised": ["surprised", "surprise", "shock"],
        "embarrassed": ["embarrassed", "awkward"],
        "worried": ["worried", "worry", "anxious", "anxiety"],
    }
    for k, vs in aliases.items():
        if s in vs:
            return k

    # 中文常见
    if any(x in s for x in ["平静", "冷静", "镇定", "淡定", "中性", "正常", "一般"]):
        return "neutral"
    if any(x in s for x in ["开心", "高兴", "愉快", "欢快", "喜悦", "兴奋"]):
        return "happy"
    if any(x in s for x in ["生气", "愤怒", "恼火", "暴怒"]):
        return "angry"
    if any(x in s for x in ["难过", "悲伤", "伤心", "沮丧"]):
        return "sad"
    if any(x in s for x in ["忧郁", "抑郁", "低落", "惆怅"]):
        return "melancholic"
    if any(x in s for x in ["害怕", "恐惧", "惊恐", "胆怯"]):
        return "afraid"
    if any(x in s for x in ["厌恶", "恶心", "嫌弃"]):
        return "disgusted"
    if any(x in s for x in ["惊讶", "震惊", "吃惊"]):
        return "surprised"
    if any(x in s for x in ["尴尬", "害羞", "羞涩"]):
        return "embarrassed"
    if any(x in s for x in ["担心", "忧虑", "焦虑", "紧张"]):
        return "worried"

    return "neutral"


def emotion_to_ext(emotion: str) -> Dict[str, float]:
    """把情绪映射到 ext（可能是稀疏字典）。"""

    e = normalize_emotion(emotion)

    emotion_mapping: Dict[str, Dict[str, float]] = {
        "happy": {"happy": 0.8, "calm": 0.2},
        "sad": {"melancholic": 0.7, "calm": 0.3},
        "melancholic": {"melancholic": 0.9, "calm": 0.1},
        "angry": {"angry": 0.8, "afraid": 0.2},
        "afraid": {"afraid": 0.9, "calm": 0.1},
        "disgusted": {"disgusted": 0.8, "calm": 0.2},
        "surprised": {"surprised": 0.9, "happy": 0.1},
        "embarrassed": {"afraid": 0.3, "happy": 0.3, "calm": 0.4},
        "worried": {"afraid": 0.5, "melancholic": 0.3, "calm": 0.2},
        "neutral": {"calm": 1.0},
        "calm": {"calm": 1.0},
    }

    return emotion_mapping.get(e, {"calm": 1.0})


def normalize_ext(ext: Dict[str, Any]) -> Dict[str, float]:
    """把 ext 规范成 8 维并 clamp 到 0-1；若全为 0 则 calm=1。"""

    normalized: Dict[str, float] = {k: 0.0 for k in EXT_KEYS}
    if not isinstance(ext, dict):
        normalized["calm"] = 1.0
        return normalized

    for k, v in ext.items():
        kk = str(k)
        if kk not in normalized:
            continue
        try:
            fv = float(v)
        except Exception:
            continue
        if fv < 0.0:
            fv = 0.0
        if fv > 1.0:
            fv = 1.0
        normalized[kk] = fv

    if all(abs(v) < 1e-9 for v in normalized.values()):
        normalized["calm"] = 1.0

    return normalized

from __future__ import annotations

import re
from typing import Any, Dict


def extract_persona_map(personas_data: Any) -> Dict[str, str]:
    """从 Step1 角色人设结果中提取 char_id -> persona 文本。

    兼容多种格式：
    - {"structured": {...}} / {"structured": [...]}（优先）
    - {"characters": [{"char_id":..., "persona":...}, ...]} 等列表字段
    - {"char_001": {"persona": "..."}, ...} 或 {"char_001": "..."}
    - list: [{"char_id":..., "persona":...}, ...]
    - raw_response 为 Markdown：通过 "## 角色名 (char_xxx)" 分段解析
    """

    if not personas_data:
        return {}

    data = personas_data

    # 兼容 structured 包装（优先）：{"structured": {...}} / {"structured": [...]}。
    if isinstance(data, dict) and isinstance(data.get("structured"), (dict, list)):
        data = data.get("structured")

    # 常见包装：{"raw_response": "...", "structured": null|... , "timestamp": ..., "parameters": ...}
    # structured 不可用时，从 raw_response Markdown 解析。
    elif isinstance(data, dict) and "raw_response" in data and (
        "timestamp" in data or "parameters" in data or "structured" in data
    ):
        raw_text = data.get("raw_response")
        if isinstance(raw_text, str) and raw_text.strip():
            return _extract_persona_map_from_markdown(raw_text)
        return {}

    persona_map: Dict[str, str] = {}

    # list: [{char_id, persona}, ...]
    if isinstance(data, list):
        for it in data:
            if not isinstance(it, dict):
                continue
            cid = (it.get("char_id") or it.get("id") or "").strip()
            persona = (it.get("persona") or it.get("profile") or it.get("description") or "").strip()
            if cid and persona:
                persona_map[cid] = persona
        return persona_map

    # dict formats
    if isinstance(data, dict):
        # 若包含列表字段
        for key in ("characters", "personas", "roles"):
            lst = data.get(key)
            if isinstance(lst, list):
                for it in lst:
                    if not isinstance(it, dict):
                        continue
                    cid = (it.get("char_id") or it.get("id") or "").strip()
                    persona = (it.get("persona") or it.get("profile") or it.get("description") or "").strip()
                    if cid and persona:
                        persona_map[cid] = persona
                if persona_map:
                    return persona_map

        # 字典直映射（更像 {"char_001": {...}, "char_002": {...}} 这种）
        # 保护：跳过明显的包装字段，避免误把 raw_response 等当成角色ID。
        skip_keys = {"raw_response", "structured", "timestamp", "parameters"}
        for cid, obj in data.items():
            if not isinstance(cid, str) or cid in skip_keys:
                continue
            if isinstance(obj, dict):
                persona = (obj.get("persona") or obj.get("profile") or obj.get("description") or "").strip()
                if persona:
                    persona_map[cid] = persona
            elif isinstance(obj, str) and obj.strip():
                persona_map[cid] = obj.strip()

        if persona_map:
            return persona_map

        # 若仍为空，尝试从 raw_response Markdown 解析
        raw_text = data.get("raw_response")
        if isinstance(raw_text, str) and raw_text.strip():
            return _extract_persona_map_from_markdown(raw_text)

    # 兜底：如果直接给了 markdown 字符串
    if isinstance(data, str) and data.strip():
        return _extract_persona_map_from_markdown(data)

    return {}


_HEADER_RE = re.compile(r"^##\s*(?P<name>.*?)\s*\((?P<char_id>[^)]+)\)\s*(?:-\s*(?P<role>.*))?$")


def _extract_persona_map_from_markdown(raw_text: str) -> Dict[str, str]:
    persona_map: Dict[str, str] = {}

    current_id: str | None = None
    current_lines: list[str] = []

    def _flush():
        nonlocal current_id, current_lines
        if not current_id:
            current_lines = []
            return
        text = "\n".join(current_lines).strip()
        # 清理可能的分隔线
        text = re.sub(r"\n-{3,}\n", "\n", text)
        if text:
            persona_map[current_id] = text
        current_id = None
        current_lines = []

    for line in raw_text.splitlines():
        m = _HEADER_RE.match(line.strip())
        if m:
            _flush()
            current_id = (m.group("char_id") or "").strip()
            # 也把标题行信息放入 persona 文本中，便于提示词直接引用
            title_line = line.strip()
            current_lines = [title_line]
            continue

        if current_id is not None:
            current_lines.append(line.rstrip())

    _flush()

    return {k: v.strip() for k, v in persona_map.items() if k and v.strip()}

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from src.ai.core.models import AIProject, VoicePendingItem


@dataclass
class VoiceBulkImportStats:
    scanned: int = 0
    added: int = 0
    updated_voice_fields: int = 0
    skipped_first_person: int = 0
    skipped_empty_text: int = 0
    skipped_existing_voice: int = 0
    deduped_existing_pending: int = 0


def _safe_strip(v: Any) -> str:
    if isinstance(v, str):
        return v.strip()
    return ""


def sanitize_id(name: str) -> str:
    s = _safe_strip(name).lower()
    if not s:
        return "unknown"

    out = []
    for ch in s:
        if ch.isalnum() or ch in {"_", "-"}:
            out.append(ch)
        elif ch.isspace() or ch in {"/", "\\", "."}:
            out.append("_")
        # drop other punctuation
    cleaned = "".join(out)
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    cleaned = cleaned.strip("_-")
    return cleaned or "unknown"


def build_first_person_speakers(project: AIProject) -> set[str]:
    names: set[str] = set()

    try:
        fp_name = _safe_strip(getattr(project.story_config, "first_person_name", "我") or "我")
        if fp_name:
            names.add(fp_name)
    except Exception:
        pass

    try:
        for c in list(getattr(project, "character_config", []) or []):
            if bool(getattr(c, "is_first_person", False)) or bool(getattr(c, "is_player", False)):
                n = _safe_strip(getattr(c, "char_name", ""))
                if n:
                    names.add(n)
    except Exception:
        pass

    return names


def is_narrator_speaker(speaker: str) -> bool:
    s = _safe_strip(speaker)
    if not s:
        return True
    return s.lower() in {"旁白", "叙述", "narrator"}


def resolve_char_id(project: AIProject, speaker: str, *, narrator_id: str = "narrator") -> Tuple[str, Optional[str]]:
    spk = _safe_strip(speaker)
    if is_narrator_speaker(spk):
        return narrator_id, None

    # name -> (char_id, voice_model_id)
    try:
        for c in list(getattr(project, "character_config", []) or []):
            if _safe_strip(getattr(c, "char_name", "")) == spk:
                return _safe_strip(getattr(c, "char_id", "")) or sanitize_id(spk), getattr(c, "voice_model_id", None)
    except Exception:
        pass

    return sanitize_id(spk), None


def iter_vng_dialogue_refs(project_data: Dict[str, Any]) -> Iterable[Tuple[str, Optional[int], str, str, Dict[str, Any], str]]:
    """Yield (node_id, sub_id, speaker, text, container, voice_key).

    container[voice_key] is the field that will be updated.
    """

    flow = project_data.get("flow_nodes") if isinstance(project_data, dict) else None
    nodes = (flow or {}).get("nodes") if isinstance(flow, dict) else None
    if not isinstance(nodes, list):
        return

    for node in nodes:
        if not isinstance(node, dict):
            continue

        node_id = str(node.get("id") if node.get("id") is not None else node.get("node_id") or "")

        speaker = _safe_strip(node.get("speaker"))
        text = _safe_strip(node.get("content"))

        subs = node.get("sub_dialogues")
        if isinstance(subs, list):
            # 某些工程会同时把第一句对白写在 node.content 与 sub_dialogues[0].text，导致导入重复。
            # 这里按 (speaker,text) 去重：若 base 与任一 sub 相同则跳过 base。
            sub_pairs: set[Tuple[str, str]] = set()
            for sub in subs:
                if not isinstance(sub, dict):
                    continue
                s = _safe_strip(sub.get("speaker")) or speaker
                t = _safe_strip(sub.get("text"))
                if t:
                    sub_pairs.add((s, t))

            if text and (speaker, text) not in sub_pairs:
                yield node_id, None, speaker, text, node, "voice"

            for idx, sub in enumerate(subs):
                if not isinstance(sub, dict):
                    continue
                s = _safe_strip(sub.get("speaker")) or speaker
                t = _safe_strip(sub.get("text"))
                yield node_id, int(idx), s, t, sub, "voice"
        else:
            # no sub_dialogues
            yield node_id, None, speaker, text, node, "voice"


def bulk_import_voices_from_vng_project(
    *,
    project: AIProject,
    vng_project_data: Dict[str, Any],
    existing_pending: List[VoicePendingItem],
    only_fill_empty_voice_fields: bool = True,
    source: str = "manual",
    voice_ext: str = "mp3",
) -> Tuple[List[VoicePendingItem], Dict[str, Any], VoiceBulkImportStats]:
    """从 .vngproj 的 flow_nodes 中批量导入对白为 VoicePendingItem，并回填 voice 路径。

    - 默认只回填空的 voice 字段（避免覆盖已有配音路径）。
    - 自动去重：如果 pending 里已存在同 (node_id, sub_id, speaker, text) 的条目，就不重复创建。
    """

    stats = VoiceBulkImportStats()

    first_person = build_first_person_speakers(project)

    existing_keys: set[Tuple[str, Optional[int], str, str]] = set()
    for it in existing_pending or []:
        try:
            existing_keys.add((str(it.node_id), getattr(it, "sub_id", None), _safe_strip(it.speaker), _safe_strip(it.text)))
        except Exception:
            continue

    next_item_index = len(existing_pending or [])

    per_char_counter: Dict[str, int] = {}

    new_pending: List[VoicePendingItem] = list(existing_pending or [])

    for node_id, sub_id, speaker, text, container, voice_key in iter_vng_dialogue_refs(vng_project_data):
        stats.scanned += 1

        if not _safe_strip(text):
            stats.skipped_empty_text += 1
            continue

        spk_effective = _safe_strip(speaker)
        if is_narrator_speaker(spk_effective):
            spk_effective = "旁白"

        if spk_effective in first_person and not is_narrator_speaker(spk_effective):
            stats.skipped_first_person += 1
            continue

        # voice field overwrite policy
        existing_voice = _safe_strip(container.get(voice_key)) if isinstance(container, dict) else ""

        key = (str(node_id), sub_id, spk_effective, text)
        if key in existing_keys:
            stats.deduped_existing_pending += 1
            # 已在 pending 中存在同条目：仍可选择回填 voice 字段（当 voice 为空时）
            if isinstance(container, dict) and (not existing_voice):
                # 为保证与新条目一致，按角色编号生成一个“期望路径”
                char_id, _ = resolve_char_id(project, spk_effective)
                per_char_counter[char_id] = int(per_char_counter.get(char_id, 0)) + 1
                voice_id = f"{char_id}_{per_char_counter[char_id]:04d}"
                file_path = f"resources/voices/{char_id}/{voice_id}.{voice_ext}"
                container[voice_key] = file_path
                stats.updated_voice_fields += 1
        else:
            char_id, voice_model_id = resolve_char_id(project, spk_effective)

            per_char_counter[char_id] = int(per_char_counter.get(char_id, 0)) + 1
            voice_id = f"{char_id}_{per_char_counter[char_id]:04d}"
            file_path = existing_voice or f"resources/voices/{char_id}/{voice_id}.{voice_ext}"

            next_item_index += 1
            item_id = f"manual_voice_item_{next_item_index:05d}"
            new_pending.append(
                VoicePendingItem(
                    source=source,  # type: ignore[arg-type]
                    item_id=item_id,
                    voice_id=voice_id,
                    node_id=str(node_id or "manual"),
                    sub_id=sub_id,
                    speaker=spk_effective,
                    char_id=char_id,
                    text=text,
                    emotion="平静",
                    voice_model_id=voice_model_id,
                    status="pending",
                    file_path=file_path,
                )
            )
            existing_keys.add(key)
            stats.added += 1

            # backfill
            if isinstance(container, dict) and (not existing_voice):
                container[voice_key] = file_path
                stats.updated_voice_fields += 1
            elif isinstance(container, dict) and existing_voice:
                stats.skipped_existing_voice += 1

    return new_pending, vng_project_data, stats

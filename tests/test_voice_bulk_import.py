from __future__ import annotations

from pathlib import Path

import pytest

from src.ai.core.ai_project_manager import AIProjectManager
from src.ai.utils.voice_bulk_import import bulk_import_voices_from_vng_project


def _make_project(tmp_path: Path):
    mgr = AIProjectManager()
    save_path = tmp_path / "voice_import.vnai"
    mgr.create_new_project(
        project_name="测试工程",
        save_path=str(save_path),
        story_title="测试",
        description="用于语音导入测试",
    )
    proj = mgr.load_project(str(save_path))
    assert proj is not None
    return proj


def test_bulk_import_dedup_base_vs_sub_same_text(tmp_path: Path):
    project = _make_project(tmp_path)

    vng = {
        "flow_nodes": {
            "nodes": [
                {
                    "id": "n1",
                    "speaker": "Alice",
                    "content": "你好",
                    "voice": "",
                    "sub_dialogues": [
                        {"speaker": "Alice", "text": "你好", "voice": ""},
                    ],
                }
            ]
        }
    }

    pending, updated_vng, stats = bulk_import_voices_from_vng_project(
        project=project,
        vng_project_data=vng,
        existing_pending=[],
        only_fill_empty_voice_fields=True,
        source="manual",
        voice_ext="mp3",
    )

    # base(content) 与 sub_dialogues[0].text 相同，只导入一条
    assert len(pending) == 1
    assert stats.added == 1

    # 回填应写入子对白 voice（base 可保持空，避免重复/歧义）
    node = updated_vng["flow_nodes"]["nodes"][0]
    assert node["sub_dialogues"][0]["voice"].startswith("resources/voices/")


def test_bulk_import_keeps_base_when_different_from_sub(tmp_path: Path):
    project = _make_project(tmp_path)

    vng = {
        "flow_nodes": {
            "nodes": [
                {
                    "id": "n1",
                    "speaker": "Alice",
                    "content": "第一句",
                    "voice": "",
                    "sub_dialogues": [
                        {"speaker": "Alice", "text": "第二句", "voice": ""},
                    ],
                }
            ]
        }
    }

    pending, updated_vng, stats = bulk_import_voices_from_vng_project(
        project=project,
        vng_project_data=vng,
        existing_pending=[],
        only_fill_empty_voice_fields=True,
        source="manual",
        voice_ext="mp3",
    )

    assert len(pending) == 2
    assert stats.added == 2

    node = updated_vng["flow_nodes"]["nodes"][0]
    assert node["voice"].startswith("resources/voices/")
    assert node["sub_dialogues"][0]["voice"].startswith("resources/voices/")

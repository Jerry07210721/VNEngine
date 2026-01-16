# -*- coding: utf-8 -*-
"""
VNEngine 多智能体协作系统 - 语音Agent
负责生成角色对白语音
"""

from typing import Dict, Any, List, Optional
from pathlib import Path
import time
from datetime import datetime
import json

from ..api.api_manager import APIManager
from ..core.config_manager import ConfigManager
from ..core.models import TaskAssignment, AgentResponse
from ..log.logger import get_logger


class VoiceAgent:
    """语音合成Agent"""

    def __init__(
        self,
        config_manager: Optional[ConfigManager] = None,
        api_manager: Optional[APIManager] = None,
    ):
        self.config_manager = config_manager or ConfigManager()
        self.api_manager = api_manager or APIManager(self.config_manager)
        self.logger = get_logger("VoiceAgent")

        self.voice_client = self.api_manager.get_gptsovits_client()

        if not self.voice_client:
            raise RuntimeError("无法获取语音合成客户端")

        self.logger.info("VoiceAgent初始化完成")

    def execute(self, task: TaskAssignment) -> AgentResponse:
        start_time = time.time()

        try:
            if task.task_type == "synthesize_voice":  # 兼容旧流程（剧情批量）
                result = self._synthesize_voice(task.parameters)
            elif task.task_type in {"generate_voice_item", "synthesize_voice_item"}:
                result = self._synthesize_single(task.parameters)
            elif task.task_type in {"generate_voice_batch", "synthesize_voice_batch"}:
                result = self._synthesize_batch(task.parameters)
            else:
                raise ValueError(f"不支持的任务类型: {task.task_type}")

            return AgentResponse(
                agent_name="voice_agent",
                task_type=task.task_type,
                status="success",
                output_files=result["files"],
                metadata=result["metadata"],
                time_cost=time.time() - start_time,
            )
        except Exception as e:
            self.logger.error(f"语音合成失败: {e}")
            return AgentResponse(
                agent_name="voice_agent",
                task_type=task.task_type,
                status="failure",
                output_files=[],
                metadata={
                    "error": str(e),
                },
                error_message=str(e),
                time_cost=time.time() - start_time,
            )

    def _synthesize_voice(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """兼容旧流程：按角色批量生成对白语音。"""
        characters_param = parameters.get("characters", [])
        voice_style = parameters.get("voice_style", "natural")
        project_root = self._project_root(parameters)

        # 兼容字符串列表输入
        if characters_param and isinstance(characters_param[0], str):
            characters = [{"name": name, "voice_model_id": None} for name in characters_param]
        else:
            characters = characters_param

        self.logger.info(f"语音合成: 角色数={len(characters)}, 风格={voice_style}")

        dialogues = self._load_dialogues_from_plot(project_root)

        output_dir = project_root / "resources" / "voice"
        output_dir.mkdir(parents=True, exist_ok=True)

        output_files: List[str] = []
        synthesized_count = 0

        char_dialogues = {c.get("name") or "": [] for c in characters}
        audio_id_map = {c.get("name"): c.get("voice_model_id") for c in characters}

        for dialogue in dialogues:
            speaker = dialogue.get("speaker", "")
            if speaker in char_dialogues:
                char_dialogues[speaker].append(dialogue)

        for char_name, char_lines in char_dialogues.items():
            if not char_name:
                continue
            self.logger.info(f"合成角色 {char_name} 的语音...")

            char_dir = output_dir / char_name
            char_dir.mkdir(exist_ok=True)

            for idx, dialogue in enumerate(char_lines):
                try:
                    single_params = {
                        "speaker": char_name,
                        "text": dialogue.get("content", ""),
                        "emotion": dialogue.get("emotion", "neutral"),
                        "voice_model_id": audio_id_map.get(char_name),
                        "output_path": str(char_dir / f"{char_name}_{idx+1}.mp3"),
                        "project_root": str(project_root),
                    }
                    single_result = self._synthesize_single(single_params)
                    output_files.extend(single_result["files"])
                    synthesized_count += 1
                except Exception as exc:
                    self.logger.warning(f"  跳过 {char_name}_{idx+1}: {exc}")

        metadata = {
            "character_count": len(characters),
            "total_synthesized": synthesized_count,
            "style": voice_style,
            "generation_time": datetime.now().isoformat(),
        }

        return {"files": output_files, "metadata": metadata}

    def _synthesize_single(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """生成单条语音，带简单重试。"""
        project_root = self._project_root(parameters)
        speaker = parameters.get("speaker") or parameters.get("char_name") or parameters.get("character_name") or ""
        text = parameters.get("text") or parameters.get("content") or ""
        emotion = parameters.get("emotion", "neutral")
        audio_id = parameters.get("voice_model_id") or parameters.get("audio_id")
        retries = int(parameters.get("retries", 2))
        output_path = self._resolve_output_path(parameters, project_root)

        if not text:
            raise ValueError("文本为空，无法生成语音")

        ext = self._map_emotion(emotion)
        audio_id = self._get_audio_id_for_character(speaker, audio_id)

        last_error = None
        for attempt in range(1, retries + 1):
            try:
                success, voice_url = self.voice_client.synthesize_and_download(
                    content=text,
                    audio_id=audio_id,
                    save_path=str(output_path),
                    ext=ext,
                )
                if success:
                    rel = self._to_relative(output_path, project_root)
                    metadata = {
                        "speaker": speaker,
                        "emotion": emotion,
                        "audio_id": audio_id,
                        "voice_url": voice_url,
                        "generation_time": datetime.now().isoformat(),
                        "retries": attempt - 1,
                    }
                    return {"files": [rel], "metadata": metadata}
                last_error = "download_failed"
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                self.logger.warning(f"尝试{attempt}/{retries}失败: {exc}")
        raise RuntimeError(last_error or "语音合成失败")

    def _synthesize_batch(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """批量生成，逐条容错继续。"""
        project_root = self._project_root(parameters)
        items = parameters.get("items") or []
        if not isinstance(items, list):
            raise ValueError("batch参数错误，items应为列表")

        success_files: List[str] = []
        failures: List[str] = []

        for idx, item in enumerate(items):
            try:
                merged = dict(parameters)
                merged.update(item or {})
                merged["project_root"] = str(project_root)
                single = self._synthesize_single(merged)
                success_files.extend(single["files"])
            except Exception as exc:  # noqa: BLE001
                ident = item.get("voice_id") or item.get("node_id") or str(idx)
                failures.append(f"{ident}:{exc}")
                self.logger.warning(f"批量跳过 {ident}: {exc}")

        metadata = {
            "success": len(success_files),
            "failures": failures,
            "generation_time": datetime.now().isoformat(),
        }
        return {"files": success_files, "metadata": metadata}
    
    def _load_dialogues_from_plot(self, project_root: Path) -> List[Dict[str, Any]]:
        """从工程内剧情文件加载对白"""
        plot_dir = project_root / "resources" / "plot"

        if not plot_dir.exists():
            self.logger.warning("剧情目录不存在，返回示例对白")
            return self._get_sample_dialogues()

        chapter_files = list(plot_dir.glob("chapters_*.json"))

        if not chapter_files:
            self.logger.warning("未找到章节文件，返回示例对白")
            return self._get_sample_dialogues()

        latest_file = max(chapter_files, key=lambda p: p.stat().st_mtime)

        self.logger.info(f"加载对白from {latest_file}")

        with open(latest_file, 'r', encoding='utf-8') as f:
            chapters = json.load(f)

        all_dialogues = []
        for chapter in chapters:
            scenes = chapter.get("scenes", [])
            for scene in scenes:
                dialogues = scene.get("dialogues", [])
                all_dialogues.extend(dialogues)

        return all_dialogues
    
    def _get_sample_dialogues(self) -> List[Dict[str, Any]]:
        """获取示例对白"""
        return [
            {"speaker": "主角", "content": "你好，很高兴认识你。", "emotion": "happy"},
            {"speaker": "女主角", "content": "嗯，我也是。", "emotion": "neutral"},
            {"speaker": "主角", "content": "今天天气真好呢。", "emotion": "neutral"},
        ]
    
    def _map_emotion(self, emotion: str) -> Dict[str, float]:
        """映射情绪到GPT-SoVITS参数"""

        emotion_mapping = {
            "happy": {"happy": 0.8, "calm": 0.2},
            "sad": {"melancholic": 0.7, "calm": 0.3},
            "angry": {"angry": 0.8, "afraid": 0.2},
            "surprised": {"surprised": 0.9, "happy": 0.1},
            "embarrassed": {"afraid": 0.3, "happy": 0.3, "calm": 0.4},
            "neutral": {"calm": 1.0},
            "worried": {"afraid": 0.5, "melancholic": 0.3, "calm": 0.2},
        }

        return emotion_mapping.get(emotion, {"calm": 1.0})
    
    def _get_audio_id_for_character(self, char_name: str, configured_id: Optional[str]) -> str:
        """优先使用角色配置中的audio_id，fallback到示例值"""

        if configured_id:
            return configured_id

        audio_id_map = {
            "主角": "sample_audio_id_1",
            "女主角": "sample_audio_id_2",
            "配角": "sample_audio_id_3",
        }

        return audio_id_map.get(char_name, "default_audio_id")

    def _project_root(self, parameters: Dict[str, Any]) -> Path:
        root = parameters.get("project_root")
        if root:
            return Path(root).expanduser().resolve()
        output_path = parameters.get("output_path") or parameters.get("file_path")
        if output_path:
            p = Path(output_path).expanduser().resolve()
            for candidate in p.parents:
                if candidate.name == "resources" and candidate.parent.exists():
                    return candidate.parent
            return p.parent
        return Path.cwd() / "output" / "project"

    def _resolve_output_path(self, parameters: Dict[str, Any], project_root: Path) -> Path:
        output_path = parameters.get("output_path") or parameters.get("file_path")
        if output_path:
            p = Path(output_path)
            return p if p.is_absolute() else (project_root / p).resolve()
        # 默认按 char_id/voice_id 命名
        speaker = parameters.get("speaker") or parameters.get("char_id") or "voice"
        voice_id = parameters.get("voice_id") or parameters.get("voice_name") or "line"
        return (project_root / f"resources/voices/{speaker}/{voice_id}.mp3").resolve()

    def _to_relative(self, path: Path, project_root: Path) -> str:
        try:
            return path.resolve().relative_to(project_root).as_posix()
        except Exception:
            return path.as_posix()
    
    def cleanup(self):
        self.logger.info("VoiceAgent资源清理完成")

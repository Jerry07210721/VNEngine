# -*- coding: utf-8 -*-

from src.ai.core.config_manager import ConfigManager
from src.ai.core.step_generator import StepGenerator


def test_try_parse_json_repairs_unescaped_quotes_in_string_values():
    sg = StepGenerator(ConfigManager())

    # 注意：这是“坏 JSON”（字符串值里包含未转义的英文双引号）。
    # 真实场景：LLM 在 dialogues[].text 里写了 "面对" 之类。
    raw = """```json
{
  \"chapter_id\": \"1\",
  \"scenes\": [
    {
      \"type\": \"text\",
      \"dialogues\": [
        {\"speaker\": \"旁白\", \"text\": \"让它\"面对\"着自己。\"}
      ]
    }
  ]
}
```"""

    parsed = sg._try_parse_json(raw)
    assert isinstance(parsed, dict)
    assert parsed.get("chapter_id") == "1"
    scenes = parsed.get("scenes")
    assert isinstance(scenes, list) and scenes
    dlg = scenes[0]["dialogues"][0]
    assert dlg["text"] == '让它"面对"着自己。'


def test_try_parse_json_accepts_python_dict_literal_for_tts_ext():
    sg = StepGenerator(ConfigManager())

    raw = "{'melancholic': 0.8, 'calm': 0.6, 'happy': 0.2}"
    parsed = sg._try_parse_json(raw)
    assert isinstance(parsed, dict)
    assert abs(float(parsed.get("melancholic")) - 0.8) < 1e-9
    assert abs(float(parsed.get("calm")) - 0.6) < 1e-9
    assert abs(float(parsed.get("happy")) - 0.2) < 1e-9


def test_try_parse_json_accepts_python_dict_literal_inside_fence():
    sg = StepGenerator(ConfigManager())

    raw = """```json
{'afraid': 0.7, 'surprised': 0.3}
```"""
    parsed = sg._try_parse_json(raw)
    assert isinstance(parsed, dict)
    assert abs(float(parsed.get("afraid")) - 0.7) < 1e-9
    assert abs(float(parsed.get("surprised")) - 0.3) < 1e-9

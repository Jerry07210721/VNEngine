# -*- coding: utf-8 -*-
"""Game runtime window using Pygame."""
import sys
import random
from datetime import datetime
from pathlib import Path
import pygame
import yaml
import json
import numpy as np


class VNGameRuntime:
    """视觉小说游戏运行时，负责游戏窗口的初始化和事件循环"""

    def __init__(self, game_title: str = "我的视觉小说", window_size=(800, 600), project_path: str | None = None):
        self.project_path = Path(project_path).resolve() if project_path else None
        cfg = self._probe_game_config(self.project_path) if self.project_path else {}
        init_w = int(cfg.get("window_width", window_size[0])) if isinstance(cfg, dict) else window_size[0]
        init_h = int(cfg.get("window_height", window_size[1])) if isinstance(cfg, dict) else window_size[1]
        init_size = (max(320, init_w), max(240, init_h))
        self.project_resolution = init_size  # logical render resolution driven by project
        self.windowed_size = init_size  # remember windowed size for exiting fullscreen
        resolved_title = cfg.get("game_title") if isinstance(cfg, dict) else None

        pygame.init()
        pygame.display.set_caption(resolved_title or game_title)
        self.base_window_size = init_size
        self.window_size = init_size
        self.render_size = self.project_resolution
        self.render_surface = pygame.Surface(self.render_size)
        self.is_fullscreen = False
        self.screen = pygame.display.set_mode(self.window_size)
        self.mode = "menu"  # menu or game
        self.clock = pygame.time.Clock()
        self.running = False

        self.font = self._load_font(22)
        self.name_font = self._load_font(24, bold=True)
        self.text_color = (235, 235, 240)
        self.box_color = (0, 0, 0, 190)
        self.bg_color = (28, 32, 40)
        self.text_margin = 24
        self.text_area = None
        self.name_area = None
        self._portrait_cache = {}
        self._portrait_scaled_cache = {}
        self._bg_cache = {}
        self.portrait_scale = 1.0
        self._ui_layout_cache: dict[Path, dict] = {}
        self._active_ui_layout: dict | None = None
        self._apply_window_size(self.window_size)
        self.branch_strategy = "first"
        self.save_dir = (self.project_path.parent / "saves") if self.project_path else Path.cwd() / "saves"
        self.settings_path = (self.project_path.parent / "settings.yaml") if self.project_path else Path.cwd() / "settings.yaml"
        self.graph_mode = False
        self.nodes_map: dict[int | str, dict] = {}
        self.adjacency: dict[int | str, list[int | str]] = {}
        self._connection_order: dict[int | str, list[int | str]] = {}
        self.current_node_id: int | str | None = None
        self.variables: dict[str, str | int | float | bool] = {}
        self.project_data: dict | None = None
        self._global_var_defs: list[dict] = []
        self._choice_overlay = False
        self._choice_options: list[str] = []
        self._choice_targets: list[int | str] = []
        self._menu_bg: pygame.Surface | None = None
        self._menu_bg_path: str = ""
        self._menu_video_path: str = ""
        self._menu_video_loop: bool = False
        self._menu_bgm_path: str | None = None
        self._menu_bgm_loop: bool = True
        self._menu_title = "VNEngine"
        self._menu_overlay_alpha: int = 0
        self._menu_title_pos: tuple[int, int] = (60, 60)
        self._menu_title_color: tuple[int, int, int] = (240, 240, 255)
        self._menu_option_pos: tuple[int, int] = (80, 140)
        self._menu_option_color: tuple[int, int, int] = (255, 255, 255)
        self._menu_title_image_path: str = ""
        self._menu_title_image_surface: pygame.Surface | None = None
        self._menu_title_image_pos: tuple[int, int] = (400, 80)
        self.dialogues = self._load_dialogues()
        self.current_index = 0
        self.current_visible_len = 0
        self.typing_speed = 24.0  # chars per second
        self.typing_progress = 0.0
        self._triangle_phase = 0.0
        self._sub_index = 0
        self._current_bg_path = None
        self._portrait_surface = None
        self._portrait_target_surface = None
        self._portrait_current_path = None
        self._portrait_fade_alpha = 255
        self._portrait_target_alpha = 255
        self._portrait_fade_start_alpha = 255
        self._portrait_fade_duration = 0.4
        self._portrait_fade_time = 0.0
        self._portrait_fadeout_active = False
        self._pending_sub_advance = False
        self._voice_cache: dict[Path, pygame.mixer.Sound] = {}
        self._voice_channel = None
        self._bgm_current = None
        self._bgm_current_loop = True
        self._voice_played_index = None
        self._voice_cache: dict[Path, pygame.mixer.Sound] = {}
        self._pending_voice_path: Path | None = None
        self._pending_voice_delay = 0.0
        self._last_dt = 0.0
        self._save_overlay = False
        self._load_overlay = False
        self._settings_overlay = False
        self._overlay_return_mode: str | None = None
        self._save_slots = 5
        self._settings = self._load_settings()
        self._apply_settings()
        self.fast_skip = False
        self._fast_skip_timer = 0.0
        self._fast_skip_interval = 0.1
        self.debug_hud = False
        self._bg_surface: pygame.Surface | None = None
        self._bg_target_surface: pygame.Surface | None = None
        self._bg_fade_time = 0.0
        self._bg_fade_duration = 0.45
        self._bg_current_path: Path | None = None
        self._bg_target_path: Path | None = None
        self._video_clip = None
        self._video_path: Path | None = None
        self._video_loop: bool = False
        self._video_time: float = 0.0
        self._video_duration: float | None = None
        self._video_surface: pygame.Surface | None = None
        self._menu_items = [
            {"label": "开始游戏", "action": "start"},
            {"label": "继续", "action": "continue"},
            {"label": "读取存档", "action": "load"},
            {"label": "设置", "action": "settings"},
            {"label": "退出", "action": "exit"},
        ]
        self._menu_selected = 0
        self._history: list[dict] = []
        self._history_overlay: bool = False
        self._splash_time: float = 2.5
        self._splash_elapsed: float = 0.0

    def _probe_game_config(self, path: Path | None) -> dict:
        if not path or not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            cfg = data.get("game_config", {}) if isinstance(data, dict) else {}
            return cfg if isinstance(cfg, dict) else {}
        except Exception:
            return {}

    def _load_dialogues(self):
        """Load dialogues from project flow_nodes (YAML), else fallback samples."""
        if self.project_path and self.project_path.exists():
            try:
                with open(self.project_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                self.project_data = data if isinstance(data, dict) else None
                if isinstance(data, dict):
                    game_cfg = (data.get("game_config", {}) or {})
                    self._global_var_defs = data.get("global_variables", []) or []
                    self.branch_strategy = game_cfg.get("branch_strategy") or "first"
                    self._apply_menu_config(game_cfg)
                    self._load_graph_from_flow(data)
                    if self.graph_mode and self.current_node_id is not None:
                        return []
                    dialogues = self._build_dialogues_from_flow(data)
                    if dialogues:
                        self._preload_initial_assets(dialogues)
                        return dialogues
            except Exception as exc:
                print(f"加载工程对白失败，使用示例对白: {exc}")
        self._global_var_defs = []
        # fallback sample dialogues
        sample = [
            {"speaker": "旁白", "content": "这是示例对白 1：欢迎使用 VNEngine 预览模式。"},
            {"speaker": "旁白", "content": "这是示例对白 2：在设计界面添加节点并保存后，预览可读取节点文本为对白内容。"},
            {"speaker": "旁白", "content": "这是示例对白 3：后续版本将支持角色名、立绘、背景等。"},
        ]
        self._preload_initial_assets(sample)
        return sample

    def _preload_initial_assets(self, dialogues: list[dict], limit: int = 6):
        """Preload first few backgrounds/voices/portraits to reduce首次卡顿."""
        if not dialogues:
            return
        count = 0
        for dlg in dialogues:
            if count >= limit:
                break
            if not isinstance(dlg, dict):
                continue
            bg = dlg.get("background") or dlg.get("bg")
            voice = dlg.get("voice")
            portrait = dlg.get("portrait")
            if bg:
                self._preload_background(bg)
            if voice:
                self._preload_voice(voice)
            if portrait:
                self._preload_portrait(portrait)
            count += 1

    def _warm_caches_from_flow(self, nodes: list[dict], preload_limit: int = 100):
        """预热节点素材缓存（背景/语音/立绘），减少首帧卡顿。"""
        if not nodes:
            return
        bgs: list[str] = []
        voices: list[str] = []
        portraits: list[str] = []
        for n in nodes:
            if not isinstance(n, dict):
                continue
            candidates = [n]
            if n.get("node_type") == "text":
                candidates.extend(n.get("sub_dialogues") or [])
            for item in candidates:
                if not isinstance(item, dict):
                    continue
                bg = item.get("background") or item.get("bg")
                voice = item.get("voice")
                portrait = item.get("portrait")
                if bg and bg not in bgs:
                    bgs.append(bg)
                if voice and voice not in voices:
                    voices.append(voice)
                if portrait and portrait not in portraits:
                    portraits.append(portrait)
                if len(bgs) + len(voices) + len(portraits) >= preload_limit:
                    break
            if len(bgs) + len(voices) + len(portraits) >= preload_limit:
                break
        for bg in bgs:
            self._preload_background(bg)
        for voice in voices:
            self._preload_voice(voice)
        for portrait in portraits:
            self._preload_portrait(portrait)

    def _prefetch_next_assets(self):
        """在进入节点后预取下一步素材，降低跳转卡顿。"""
        assets: list[dict] = []
        if self.graph_mode:
            next_ids = self.adjacency.get(self.current_node_id, []) if self.current_node_id is not None else []
            for nid in next_ids[:3]:
                node = self.nodes_map.get(nid) or {}
                assets.append(node)
                if node.get("node_type") == "text":
                    subs = node.get("sub_dialogues") or []
                    if subs:
                        assets.append(subs[0])
        else:
            for i in range(1, 4):
                idx = self.current_index + i
                if 0 <= idx < len(self.dialogues):
                    assets.append(self.dialogues[idx])
        for item in assets:
            if not isinstance(item, dict):
                continue
            bg = item.get("background") or item.get("bg")
            voice = item.get("voice")
            portrait = item.get("portrait")
            if bg:
                self._preload_background(bg)
            if voice:
                self._preload_voice(voice)
            if portrait:
                self._preload_portrait(portrait)

    def _preload_background(self, bg_path: str):
        if not bg_path:
            return
        abs_path = self._resolve_path(bg_path)
        if not abs_path.exists():
            return
        if abs_path in self._bg_cache:
            return
        try:
            img = pygame.image.load(str(abs_path)).convert()
            img = pygame.transform.scale(img, self.render_size)
            self._bg_cache[abs_path] = img
        except Exception:
            return

    def _preload_voice(self, voice_path: str):
        if not voice_path:
            return
        abs_path = self._resolve_path(voice_path)
        if not abs_path.exists():
            return
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            if abs_path not in self._voice_cache:
                self._voice_cache[abs_path] = pygame.mixer.Sound(str(abs_path))
        except Exception:
            return

    def _preload_portrait(self, portrait_path: str):
        if not portrait_path:
            return
        abs_path = self._resolve_path(portrait_path)
        if not abs_path.exists():
            return
        if abs_path in self._portrait_cache:
            return
        try:
            img = pygame.image.load(str(abs_path)).convert_alpha()
            max_w = int(self.render_size[0] * 0.35)
            max_h = int(self.render_size[1] * 0.7)
            img = self._scale_to_fit(img, max_w, max_h)
            self._portrait_cache[abs_path] = img
        except Exception:
            return

    def _reload_dialogues(self):
        """Reload dialogues from project file for quick preview refresh."""
        self._bg_cache.clear()
        self._portrait_cache.clear()
        self._choice_overlay = False
        self._choice_options = []
        self._choice_targets = []
        try:
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
        except Exception:
            pass
        self._bgm_current = None
        self.dialogues = self._load_dialogues()
        self.current_index = 0 if self.dialogues else 0
        if self.graph_mode:
            self._voice_played_index = None
            self._on_enter_node()
            self._reset_typing_state()
            print("剧情已重新加载 (图模式)")
            return
        self._voice_played_index = None
        self._on_enter_node()
        self._reset_typing_state()
        print("剧情已重新加载")

    def _apply_menu_config(self, cfg: dict):
        self._menu_title = cfg.get("menu_title") or (self.project_path.stem if self.project_path else "VNEngine")
        self._menu_bg_path = cfg.get("menu_background") or ""
        self._menu_video_path = cfg.get("menu_video") or ""
        self._menu_video_loop = bool(cfg.get("menu_video_loop", False))
        self._menu_bgm_path = cfg.get("menu_bgm") or None
        self._menu_bgm_loop = bool(cfg.get("menu_bgm_loop", True))
        try:
            self._menu_overlay_alpha = max(0, min(255, int(cfg.get("menu_overlay_alpha", 0))))
        except Exception:
            self._menu_overlay_alpha = 0
        self._menu_title_pos = self._pair_from_cfg(cfg.get("menu_title_pos"), (60, 60))
        self._menu_option_pos = self._pair_from_cfg(cfg.get("menu_option_pos"), (80, 140))
        self._menu_title_color = self._color_from_cfg(cfg.get("menu_title_color"), (240, 240, 255))
        self._menu_option_color = self._color_from_cfg(cfg.get("menu_option_color"), (255, 255, 255))
        self._menu_title_image_path = cfg.get("menu_title_image") or ""
        self._menu_title_image_pos = self._pair_from_cfg(cfg.get("menu_title_image_pos"), (400, 80))

    def _enter_menu(self):
        self.mode = "menu"
        self._save_overlay = False
        self._load_overlay = False
        self._settings_overlay = False
        self._choice_overlay = False
        self._history_overlay = False
        self._overlay_return_mode = None
        self._menu_selected = 0
        self._stop_voice_playback()
        self._stop_video()
        # stop current bgm before menu bgm
        try:
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
        except Exception:
            pass
        self._bgm_current = None
        self._load_menu_assets()
        if self._menu_bgm_path:
            self._ensure_bgm(self._menu_bgm_path, loop=self._menu_bgm_loop, fade=True)

    def _start_new_game(self):
        self.mode = "game"
        self._save_overlay = False
        self._load_overlay = False
        self._settings_overlay = False
        self._choice_overlay = False
        self._history = []
        self._history_overlay = False
        self._stop_bgm()
        self._stop_video()
        self._init_variables_from_defs()
        self.fast_skip = False
        self._fast_skip_timer = 0.0
        self.current_index = 0
        self._sub_index = 0
        self.current_node_id = None
        self._voice_played_index = None
        self._bgm_current = None
        self._stop_voice_playback()
        self._reload_dialogues()

    def _continue_latest(self):
        latest_slot = self._find_latest_slot()
        if latest_slot is None:
            print("没有可继续的存档，自动开始新游戏")
            self._start_new_game()
            return
        self.mode = "game"
        self._save_overlay = False
        self._load_overlay = False
        self._settings_overlay = False
        self._choice_overlay = False
        self.fast_skip = False
        self._fast_skip_timer = 0.0
        self.load_game(latest_slot)

    def _open_load_from_menu(self):
        self._overlay_return_mode = "menu"
        self._load_overlay = True
        self._save_overlay = False
        self._settings_overlay = False
        self._choice_overlay = False
        self._history_overlay = False

    def _open_settings_from_menu(self):
        self._overlay_return_mode = "menu"
        self._settings_overlay = True
        self._save_overlay = False
        self._load_overlay = False
        self._choice_overlay = False
        self._history_overlay = False

    def _move_menu(self, delta: int):
        count = len(self._menu_items)
        self._menu_selected = (self._menu_selected + delta) % count

    def _activate_menu_item(self):
        if not self._menu_items:
            return
        action = self._menu_items[self._menu_selected].get("action")
        if action == "start":
            self._start_new_game()
        elif action == "continue":
            self._continue_latest()
        elif action == "load":
            self._open_load_from_menu()
        elif action == "settings":
            self._open_settings_from_menu()
        elif action == "exit":
            self.quit_game()

    def _find_latest_slot(self) -> int | None:
        latest = None
        latest_time = None
        for idx in range(1, self._save_slots + 1):
            path = self.save_dir / f"slot_{idx}.json"
            if not path.exists():
                continue
            try:
                mtime = path.stat().st_mtime
            except Exception:
                continue
            if latest_time is None or mtime > latest_time:
                latest_time = mtime
                latest = idx
        return latest

    def _init_variables_from_defs(self):
        self.variables = {}
        for item in self._global_var_defs or []:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not name:
                continue
            try:
                init_val = float(item.get("initial", 0.0))
            except Exception:
                init_val = 0.0
            self.variables[name] = init_val

    def _load_menu_assets(self):
        # optional title background and bgm (config first, then fallbacks)
        candidates_img = []
        if self._menu_bg_path:
            candidates_img.append(self._menu_bg_path)
        candidates_img.extend([
            "resources/images/menu_bg.png",
            "resources/images/title.png",
        ])
        bg_surface = None
        for rel in candidates_img:
            p = self._resolve_path(rel)
            if p.exists():
                try:
                    img = pygame.image.load(str(p)).convert()
                    img = pygame.transform.scale(img, self.render_size)
                    bg_surface = img
                    break
                except Exception:
                    continue
        self._menu_bg = bg_surface

        candidates_bgm = []
        if self._menu_bgm_path:
            candidates_bgm.append(self._menu_bgm_path)
        candidates_bgm.extend([
            "resources/audios/menu_bgm.ogg",
            "resources/audios/menu_bgm.mp3",
            "resources/audios/title.ogg",
            "resources/audios/title.mp3",
        ])
        bgm_path = None
        for rel in candidates_bgm:
            p = self._resolve_path(rel)
            if p.exists():
                bgm_path = str(p)
                break
        self._menu_bgm_path = bgm_path

        candidates_video: list[str] = []
        if self._menu_video_path:
            candidates_video.append(self._menu_video_path)
        candidates_video.extend([
            "resources/videos/menu.mp4",
            "resources/videos/title.mp4",
        ])
        video_path = None
        for rel in candidates_video:
            p = self._resolve_path(rel)
            if p.exists():
                video_path = str(p)
                break
        self._menu_video_path = video_path or ""

        # title image
        self._menu_title_image_surface = None
        img_path = None
        if self._menu_title_image_path:
            img_path = self._resolve_path(self._menu_title_image_path)
        if img_path and img_path.exists():
            try:
                self._menu_title_image_surface = pygame.image.load(str(img_path)).convert_alpha()
            except Exception:
                self._menu_title_image_surface = None

    def _preload_menu_media(self):
        """预加载主菜单媒体，避免进入时黑屏或卡顿。"""
        self._load_menu_assets()
        # 预取视频首帧
        if self._menu_video_path:
            self._video_time = 0.0
            self._update_video(self._menu_video_path, self._menu_video_loop, 0.0)
        # 预加载BGM到缓冲（不播放）
        if self._menu_bgm_path:
            try:
                if not pygame.mixer.get_init():
                    pygame.mixer.init()
                pygame.mixer.music.load(self._menu_bgm_path)
                pygame.mixer.music.stop()
            except Exception:
                pass

    def _start_splash(self):
        self.mode = "splash"
        self._splash_elapsed = 0.0
        self._preload_menu_media()

    def _render_splash(self, dt: float):
        self._splash_elapsed += dt
        self.render_surface.fill((16, 18, 26))
        title = "VNEngine"
        sub = "Loading..."
        title_surf = self.name_font.render(title, True, (220, 230, 255))
        sub_surf = self.font.render(sub, True, (200, 200, 200))
        cx = self.render_size[0] // 2
        cy = self.render_size[1] // 2
        self.render_surface.blit(title_surf, (cx - title_surf.get_width() // 2, cy - title_surf.get_height()))
        self.render_surface.blit(sub_surf, (cx - sub_surf.get_width() // 2, cy + 12))
        if self._splash_elapsed >= self._splash_time:
            self._enter_menu()

    def start_game(self):
        """启动游戏（进入事件循环）"""
        self.running = True
        print("游戏预览窗口已启动，点击关闭按钮或按ESC退出")
        self._start_splash()

        while self.running:
            dt = self.clock.tick(60) / 1000.0
            self._last_dt = dt
            self.render_surface.fill(self.bg_color)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.quit_game()
                if event.type == pygame.KEYDOWN:
                    if self.mode == "splash":
                        if event.key == pygame.K_ESCAPE:
                            self.quit_game()
                            break
                        else:
                            self._enter_menu()
                            continue
                    # global overlay handling (works in menu or game)
                    if event.key == pygame.K_ESCAPE and (self._save_overlay or self._load_overlay or self._settings_overlay or self._choice_overlay or self._history_overlay):
                        self._save_overlay = False
                        self._load_overlay = False
                        self._settings_overlay = False
                        self._choice_overlay = False
                        self._history_overlay = False
                        self._restore_mode_if_needed()
                        continue
                    if self._settings_overlay:
                        if self._handle_settings_key(event.key):
                            self._restore_mode_if_needed()
                            continue
                    if self._load_overlay and event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5, pygame.K_KP1, pygame.K_KP2, pygame.K_KP3, pygame.K_KP4, pygame.K_KP5):
                        key_map = {
                            pygame.K_1: 1,
                            pygame.K_2: 2,
                            pygame.K_3: 3,
                            pygame.K_4: 4,
                            pygame.K_5: 5,
                            pygame.K_KP1: 1,
                            pygame.K_KP2: 2,
                            pygame.K_KP3: 3,
                            pygame.K_KP4: 4,
                            pygame.K_KP5: 5,
                        }
                        slot = key_map.get(event.key)
                        if slot:
                            self.load_game(slot)
                            self._load_overlay = False
                            self._overlay_return_mode = None
                            continue
                    if self._save_overlay and event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5, pygame.K_KP1, pygame.K_KP2, pygame.K_KP3, pygame.K_KP4, pygame.K_KP5):
                        key_map = {
                            pygame.K_1: 1,
                            pygame.K_2: 2,
                            pygame.K_3: 3,
                            pygame.K_4: 4,
                            pygame.K_5: 5,
                            pygame.K_KP1: 1,
                            pygame.K_KP2: 2,
                            pygame.K_KP3: 3,
                            pygame.K_KP4: 4,
                            pygame.K_KP5: 5,
                        }
                        slot = key_map.get(event.key)
                        if slot:
                            self.save_game(slot)
                            self._save_overlay = False
                            self._restore_mode_if_needed()
                            continue

                    if self.mode == "menu":
                        if event.key in (pygame.K_UP, pygame.K_w):
                            self._move_menu(-1)
                            continue
                        if event.key in (pygame.K_DOWN, pygame.K_s):
                            self._move_menu(1)
                            continue
                        if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                            self._activate_menu_item()
                            continue
                        if event.key == pygame.K_ESCAPE:
                            self.quit_game()
                            break
                        # ignore other keys in menu
                        continue
                    # below: game mode
                    if event.key == pygame.K_ESCAPE:
                        self._enter_menu()
                        continue
                    elif event.key == pygame.K_SPACE or event.key == pygame.K_RETURN:
                        if self._settings_overlay:
                            if self._handle_settings_key(event.key):
                                self._restore_mode_if_needed()
                                continue
                        elif not (self._save_overlay or self._load_overlay or self._choice_overlay):
                            self.advance_dialogue()
                    elif event.key == pygame.K_F11:
                        self.toggle_fullscreen()
                    elif event.key == pygame.K_F5:
                        self._overlay_return_mode = self.mode
                        self._save_overlay = True
                        self._load_overlay = False
                        self._settings_overlay = False
                        self._history_overlay = False
                    elif event.key == pygame.K_F9:
                        self._overlay_return_mode = self.mode
                        self._load_overlay = True
                        self._save_overlay = False
                        self._settings_overlay = False
                        self._history_overlay = False
                    elif event.key == pygame.K_F10:
                        self._overlay_return_mode = self.mode
                        self._settings_overlay = True
                        self._save_overlay = False
                        self._load_overlay = False
                        self._history_overlay = False
                    elif event.key == pygame.K_TAB:
                        if not (self._save_overlay or self._load_overlay or self._settings_overlay):
                            self.fast_skip = not self.fast_skip
                            self._fast_skip_timer = 0.0
                            self._reset_typing_state()
                        continue
                    elif event.key == pygame.K_s:
                        if not (self._save_overlay or self._load_overlay or self._settings_overlay or self._choice_overlay or self._history_overlay):
                            self.fast_skip = True
                            self._fast_skip_timer = 0.0
                            self._reset_typing_state()
                        continue
                    elif event.key == pygame.K_h:
                        # history overlay is same level as save/load/settings
                        self._history_overlay = not self._history_overlay
                        if self._history_overlay:
                            self._save_overlay = False
                            self._load_overlay = False
                            self._settings_overlay = False
                            self._choice_overlay = False
                        continue
                    elif event.key == pygame.K_F3:
                        self.debug_hud = not self.debug_hud
                        continue
                    elif event.key == pygame.K_r:
                        if not (self._save_overlay or self._load_overlay or self._settings_overlay):
                            self._reload_dialogues()
                        continue
                    elif self._choice_overlay and event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5, pygame.K_6, pygame.K_7, pygame.K_8, pygame.K_9):
                        key_map = {
                            pygame.K_1: 0,
                            pygame.K_2: 1,
                            pygame.K_3: 2,
                            pygame.K_4: 3,
                            pygame.K_5: 4,
                            pygame.K_6: 5,
                            pygame.K_7: 6,
                            pygame.K_8: 7,
                            pygame.K_9: 8,
                        }
                        self._apply_choice(key_map.get(event.key, -1))
                        continue
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if self.mode == "menu":
                        self._activate_menu_item()
                        continue
                    if not (self._save_overlay or self._load_overlay or self._settings_overlay or self._history_overlay):
                        self.advance_dialogue()
                if event.type == pygame.KEYUP:
                    if event.key == pygame.K_s:
                        self.fast_skip = False
                        self._fast_skip_timer = 0.0

            if not self.running:
                break

            if self.mode == "splash":
                self._render_splash(dt)
            elif self.mode == "menu":
                self._render_menu(dt)
                if self._save_overlay or self._load_overlay or self._settings_overlay:
                    self._render_overlay()
            else:
                # overlays pause dialogue progression but still render current frame
                if not (self._save_overlay or self._load_overlay or self._settings_overlay or self._choice_overlay or self._history_overlay):
                    self._update_typing(dt)
                self._process_pending_audio(dt)
                self._render_scene(dt)
                self._update_fast_skip(dt)
                if self._pending_sub_advance:
                    self._pending_sub_advance = False
                    # advance to next sub-dialogue after fade-out
                    self.advance_dialogue()
            self._blit_to_window()
            pygame.display.flip()

    def advance_dialogue(self):
        entry = self._current_entry()
        if not entry:
            return
        full_text = entry.get("content") or entry.get("title") or ""
        if self.current_visible_len < len(full_text):
            self.current_visible_len = len(full_text)
            return

        # leaving current子节点/节点时先停止当前语音，避免残留播放
        self._stop_voice_playback()

        if self.graph_mode:
            node_type = entry.get("node_type", "text")
            if node_type == "text":
                subs = (self.nodes_map.get(self.current_node_id, {}) or {}).get("sub_dialogues") or []
                if subs and self._sub_index < len(subs) - 1:
                    if self._maybe_start_portrait_fade_out(subs[self._sub_index]):
                        return
                    self._sub_index += 1
                    self._voice_played_index = None
                    # 同一节点子对话切换，避免重复刷新BGM/UI以防卡顿
                    self._on_enter_node(skip_media=True)
                    self._reset_typing_state()
                    return
            if node_type == "choice":
                self._open_choice_overlay(entry)
                return
            if node_type == "condition":
                self._resolve_condition_branch(entry)
                return
            self._advance_to_next_in_graph()
        else:
            if self.current_index < len(self.dialogues) - 1:
                self.current_index += 1
                self._on_enter_node()
                self._reset_typing_state()
            else:
                print("对白结束，按 ESC 退出或点击关闭窗口。")

    def _render_scene(self, dt: float):
        entry = self._current_entry()
        speaker = entry.get("speaker") or "角色"
        content = entry.get("content") or entry.get("title") or ""
        bg_path = entry.get("background") or ""
        portrait_path = entry.get("portrait") or ""
        voice_path = entry.get("voice") or ""
        video_path = entry.get("video") or ""
        bgm_path = entry.get("bgm") or ""
        stop_bgm = bool(entry.get("stop_bgm"))
        hide_textbox = bool(entry.get("hide_textbox", False))
        portrait_fade = bool(entry.get("portrait_fade", False))

        # draw video or background image
        if video_path:
            self._update_video(video_path, bool(entry.get("video_loop", False)), dt)
            if self._video_surface is not None:
                self.render_surface.blit(self._video_surface, (0, 0))
            else:
                if bg_path:
                    self._update_background(bg_path, fade_in=bool(entry.get("bg_fade_in", False)))
                    self._render_background(dt)
                else:
                    # video加载失败时至少不要复用上一个背景
                    self.render_surface.fill(self.bg_color)
        else:
            if self._video_clip:
                self._stop_video()
            self._update_background(bg_path, fade_in=bool(entry.get("bg_fade_in", False)))
            self._render_background(dt)

        # draw portrait (character sprite) if available
        self._draw_portrait(portrait_path, portrait_fade, dt)

        # ensure bgm if provided and not explicitly stopped on this node
        if not stop_bgm:
            self._ensure_bgm(bgm_path, loop=bool(entry.get("bgm_loop", True)))

        if not hide_textbox:
            # draw text box (semi-transparent)
            box_surface = pygame.Surface((self.text_area.width, self.text_area.height), pygame.SRCALPHA)
            box_surface.fill(self.box_color)
            self.render_surface.blit(box_surface, (self.text_area.x, self.text_area.y))

            # draw name box
            name_surface = pygame.Surface((self.name_area.width, self.name_area.height), pygame.SRCALPHA)
            name_surface.fill((0, 0, 0, 180))
            self.render_surface.blit(name_surface, (self.name_area.x, self.name_area.y))
            name_text = self.name_font.render(speaker, True, (220, 220, 220))
            left_pad = min(self.text_margin, max(4, self.name_area.width - 10))
            vert_pad = max(4, (self.name_area.height - name_text.get_height()) // 2)
            self.render_surface.blit(name_text, (self.name_area.x + left_pad, self.name_area.y + vert_pad))

            # render dialogue text with simple wrapping
            shown_text = content[: self.current_visible_len] if content else ""
            self._render_wrapped_text(shown_text, self.text_area, self.font, self.text_color)

            # draw small triangle indicator when line finished
            if self.current_visible_len >= len(content):
                self._draw_indicator()

        if self.debug_hud:
            self._render_debug_hud(entry)

        if self._history_overlay:
            self._render_history_overlay()

        if self._save_overlay or self._load_overlay or self._settings_overlay:
            self._render_overlay()
        if self._choice_overlay:
            self._render_choice_overlay()

    def _render_history_overlay(self):
        overlay = pygame.Surface(self.render_size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))

        title = "历史记录 (H 关闭)"
        title_surf = self.name_font.render(title, True, (255, 255, 255))
        overlay.blit(title_surf, (40, 40))

        max_width = self.render_size[0] - 80
        y = 90

        def _wrap_line(text: str) -> list[str]:
            lines: list[str] = []
            current = ""
            for ch in text:
                test = current + ch
                if current and self.font.size(test)[0] > max_width:
                    lines.append(current)
                    current = ch
                else:
                    current = test
            if current:
                lines.append(current)
            return lines

        for item in reversed(self._history):
            speaker = item.get("speaker") or ""
            content = item.get("content") or ""
            if not content:
                continue
            text = f"{speaker}: {content}" if speaker else content
            for line in _wrap_line(text):
                surf = self.font.render(line, True, (230, 230, 230))
                overlay.blit(surf, (40, y))
                y += self.font.get_linesize()
                if y > self.render_size[1] - 60:
                    break
            if y > self.render_size[1] - 60:
                break
            # add one blank line between entries
            y += self.font.get_linesize()

        hint = "ESC 关闭"
        hint_surf = self.font.render(hint, True, (200, 200, 200))
        overlay.blit(hint_surf, (40, self.render_size[1] - 40))

        self.render_surface.blit(overlay, (0, 0))

    def _render_menu(self, dt: float):
        # background (video > image > solid)
        if self._menu_video_path:
            self._update_video(self._menu_video_path, self._menu_video_loop, dt)
            if self._video_surface is not None:
                self.render_surface.blit(self._video_surface, (0, 0))
            elif self._menu_bg:
                self.render_surface.blit(self._menu_bg, (0, 0))
            else:
                self.render_surface.fill((20, 24, 30))
        else:
            if self._video_clip:
                self._stop_video()
            if self._menu_bg:
                self.render_surface.blit(self._menu_bg, (0, 0))
            else:
                self.render_surface.fill((20, 24, 30))

        # optional dim overlay
        if self._menu_overlay_alpha > 0:
            overlay = pygame.Surface(self.render_size, pygame.SRCALPHA)
            overlay.fill((0, 0, 0, self._menu_overlay_alpha))
            self.render_surface.blit(overlay, (0, 0))

        title = self._menu_title or (self.project_path.stem if self.project_path else "VNEngine")
        title_pos = self._menu_title_pos
        menu_font = self._load_font(26)
        title_color = self._menu_title_color
        option_color = self._menu_option_color

        if self._menu_title_image_surface:
            img = self._menu_title_image_surface
            x = self._menu_title_image_pos[0]
            y = self._menu_title_image_pos[1]
            self.render_surface.blit(img, (x - img.get_width() // 2, y - img.get_height() // 2))
        else:
            title_surf = self.name_font.render(title, True, title_color)
            self.render_surface.blit(title_surf, (title_pos[0], title_pos[1]))

        start_x, start_y = self._menu_option_pos
        for idx, item in enumerate(self._menu_items):
            label = item.get("label", "")
            sel = idx == self._menu_selected
            base = option_color
            color = base if sel else (int(base[0] * 0.75), int(base[1] * 0.75), int(base[2] * 0.75))
            surf = menu_font.render(label, True, color)
            x = start_x
            y = start_y + idx * (menu_font.get_linesize() + 10)
            self.render_surface.blit(surf, (x, y))

        hint = "↑↓选择, 回车确认, ESC退出"
        hint_surf = self.font.render(hint, True, (200, 200, 200))
        self.render_surface.blit(hint_surf, (60, self.render_size[1] - 60))

    def _render_wrapped_text(self, text: str, area: pygame.Rect, font, color):
        words = list(text)
        lines = []
        current = ""
        for ch in words:
            test = current + ch
            if font.size(test)[0] > area.width - self.text_margin * 2:
                lines.append(current)
                current = ch
            else:
                current = test
        if current:
            lines.append(current)

        y = area.y + self.text_margin
        for line in lines:
            surf = font.render(line, True, color)
            self.render_surface.blit(surf, (area.x + self.text_margin, y))
            y += font.get_linesize()

    def _update_typing(self, dt: float):
        entry = self._current_entry()
        if not entry:
            return
        content = entry.get("content") or entry.get("title") or ""
        if self.fast_skip:
            self.current_visible_len = len(content)
            self.typing_progress = len(content)
            self._triangle_phase = (self._triangle_phase + dt) % 1.0
            return
        if self.current_visible_len < len(content):
            self.typing_progress += self.typing_speed * dt
            new_len = int(self.typing_progress)
            if new_len > self.current_visible_len:
                self.current_visible_len = min(new_len, len(content))
        self._triangle_phase = (self._triangle_phase + dt) % 1.0

    def _update_fast_skip(self, dt: float):
        if not self.fast_skip:
            self._fast_skip_timer = 0.0
            return
        if self.mode != "game":
            return
        if self._save_overlay or self._load_overlay or self._settings_overlay or self._choice_overlay or self._history_overlay:
            return
        if self._pending_sub_advance:
            return
        entry = self._current_entry()
        if not entry:
            return
        content = entry.get("content") or entry.get("title") or ""
        self.current_visible_len = len(content)
        self.typing_progress = len(content)
        self._fast_skip_timer += dt
        if self._fast_skip_timer >= self._fast_skip_interval:
            self._fast_skip_timer = 0.0
            self.advance_dialogue()

    def _reset_typing_state(self):
        self.current_visible_len = 0
        self.typing_progress = 0.0
        self._triangle_phase = 0.0
        if self.fast_skip:
            entry = self._current_entry()
            content = (entry.get("content") or entry.get("title") or "") if entry else ""
            self.current_visible_len = len(content)
            self.typing_progress = len(content)

    def _resolve_operand(self, token: str | int | float | None, is_const: bool) -> float:
        if is_const:
            try:
                return float(token)
            except Exception:
                return 0.0
        if token is None:
            return 0.0
        return float(self.variables.get(str(token), 0.0) or 0.0)

    def _apply_var_ops(self, entry: dict):
        ops = entry.get("var_ops") if isinstance(entry, dict) else None
        if not ops:
            return
        for item in ops:
            if not isinstance(item, dict):
                continue
            dest = item.get("dest")
            if not dest:
                continue
            left = self._resolve_operand(item.get("left"), bool(item.get("left_const", False)))
            right = self._resolve_operand(item.get("right"), bool(item.get("right_const", False)))
            op = item.get("op", "+")
            try:
                if op == "=":
                    result = right
                elif op == "+":
                    result = left + right
                elif op == "-":
                    result = left - right
                elif op == "*":
                    result = left * right
                elif op == "/":
                    result = left if right == 0 else left / right
                else:
                    result = left + right
            except Exception:
                result = 0.0
            self.variables[str(dest)] = result

    def _on_enter_node(self, skip_media: bool = False):
        entry = self._current_entry()
        self._apply_var_ops(entry)
        stop_bgm = bool(entry.get("stop_bgm")) if entry else False
        bgm = entry.get("bgm") or "" if entry else ""
        voice = entry.get("voice") or "" if entry else ""
        ui_file = entry.get("ui_file") or ""

        if entry and entry.get("video"):
            # 清空旧背景，避免视频节点复用上一背景
            self._bg_surface = None
            self._bg_target_surface = None
            self._bg_current_path = None
            self._bg_target_path = None

        if not skip_media:
            if stop_bgm:
                try:
                    if pygame.mixer.get_init():
                        pygame.mixer.music.stop()
                except Exception:
                    pass
                self._bgm_current = None
            if bgm:
                self._ensure_bgm(bgm, loop=bool(entry.get("bgm_loop", True)), fade=True)
            # apply ui layout if provided
            self._apply_ui_file(ui_file)

        # avoid replaying voice if already played for this index
        voice_key = (self.current_node_id, self._sub_index) if self.graph_mode else self.current_index
        if self._voice_played_index != voice_key:
            self._schedule_voice(voice)
            self._voice_played_index = voice_key

        self._append_history(entry)
        # 预取下一个节点/对白的素材，进一步降低跳转卡顿
        self._prefetch_next_assets()

    def _apply_ui_file(self, ui_file: str):
        if not ui_file:
            self._active_ui_layout = None
            self._apply_window_size(self.window_size)
            return

        abs_path = self._resolve_path(ui_file)
        if not abs_path.exists():
            self._active_ui_layout = None
            self._apply_window_size(self.window_size)
            return

        if abs_path not in self._ui_layout_cache:
            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self._ui_layout_cache[abs_path] = data
                else:
                    self._ui_layout_cache[abs_path] = {}
            except Exception:
                self._ui_layout_cache[abs_path] = {}

        self._active_ui_layout = self._ui_layout_cache.get(abs_path) or None
        self._apply_window_size(self.window_size)

    def _draw_indicator(self):
        # small blinking triangle at bottom-right of text box
        alpha = 150 + int(80 * abs(0.5 - self._triangle_phase))
        tri_surface = pygame.Surface((20, 20), pygame.SRCALPHA)
        points = [(2, 2), (18, 2), (10, 14)]
        pygame.draw.polygon(tri_surface, (255, 255, 255, alpha), points)
        self.render_surface.blit(tri_surface, (self.text_area.right - 30, self.text_area.bottom - 26))

    def _update_background(self, bg_path: str, fade_in: bool):
        # prepare background surfaces and fade state
        if not bg_path:
            # 保留当前背景，避免子节点切换时短暂闪黑；若本就无背景则维持空状态
            if self._bg_surface is None and self._bg_target_surface is None:
                self._bg_current_path = None
            return

        abs_path = self._resolve_path(bg_path)
        if not abs_path.exists():
            return
        if abs_path not in self._bg_cache:
            try:
                img = pygame.image.load(str(abs_path)).convert()
                img = pygame.transform.scale(img, self.render_size)
                self._bg_cache[abs_path] = img
            except Exception:
                return

        new_surface = self._bg_cache[abs_path]
        # skip if already showing or already fading toward this background
        if self._bg_target_surface is None and self._bg_surface is new_surface:
            return
        if self._bg_target_surface is not None and self._bg_target_path == abs_path:
            return

        if fade_in and self._bg_surface is not None:
            self._bg_target_surface = new_surface
            self._bg_target_path = abs_path
            self._bg_fade_time = 0.0
        else:
            self._bg_surface = new_surface
            self._bg_target_surface = None
            self._bg_target_path = None
            self._bg_fade_time = 0.0
            self._bg_current_path = abs_path

    def _render_background(self, dt: float):
        if self._bg_target_surface is not None and self._bg_surface is not None:
            self._bg_fade_time += dt
            progress = min(1.0, self._bg_fade_time / max(0.001, self._bg_fade_duration))
            # crossfade current -> target
            temp = pygame.Surface(self.render_size)
            temp.blit(self._bg_surface, (0, 0))
            overlay = self._bg_target_surface.copy()
            overlay.set_alpha(int(255 * progress))
            temp.blit(overlay, (0, 0))
            self.render_surface.blit(temp, (0, 0))
            if progress >= 1.0:
                self._bg_surface = self._bg_target_surface
                self._bg_target_surface = None
                self._bg_current_path = self._bg_target_path or self._bg_current_path
                self._bg_target_path = None
        elif self._bg_target_surface is not None and self._bg_surface is None:
            # 没有当前背景时直接显示目标，避免瞬时黑屏
            self.render_surface.blit(self._bg_target_surface, (0, 0))
            self._bg_surface = self._bg_target_surface
            self._bg_target_surface = None
            self._bg_current_path = self._bg_target_path or self._bg_current_path
            self._bg_target_path = None
        elif self._bg_surface is not None:
            self.render_surface.blit(self._bg_surface, (0, 0))
        else:
            # fallback to solid color if no background
            self.render_surface.fill(self.bg_color)

    def _ensure_video_clip(self, abs_path: Path):
        if self._video_path == abs_path and self._video_clip is not None:
            return True
        # release previous clip
        self._stop_video()
        try:
            try:
                from moviepy.editor import VideoFileClip  # type: ignore[import]
            except ImportError:
                from moviepy.video.io.VideoFileClip import VideoFileClip  # type: ignore[import]

            # disable audio to减少解码失败概率，依赖 ffmpeg
            clip = VideoFileClip(str(abs_path), audio=False)
            self._video_clip = clip
            self._video_duration = float(clip.duration) if clip.duration else None
            self._video_path = abs_path
            self._video_time = 0.0
            return True
        except ImportError as exc:
            print("加载视频失败: 缺少 moviepy 依赖，请安装 'pip install moviepy imageio-ffmpeg'")
            self._video_clip = None
            self._video_duration = None
            self._video_path = None
            return False
        except Exception as exc:
            ffmpeg_hint = ""
            try:
                import imageio_ffmpeg  # type: ignore

                ffmpeg_hint = f" ffmpeg at: {imageio_ffmpeg.get_ffmpeg_exe()}"
            except Exception:
                ffmpeg_hint = " (未检测到 imageio-ffmpeg，安装后会自带 ffmpeg)"
            print(f"加载视频失败: {exc}{ffmpeg_hint}")
            self._video_clip = None
            self._video_duration = None
            self._video_path = None
            return False

    def _update_video(self, path_str: str, loop: bool, dt: float):
        abs_path = self._resolve_path(path_str)
        if not abs_path.exists():
            self._stop_video()
            print(f"视频文件不存在: {abs_path}")
            return
        if not self._ensure_video_clip(abs_path):
            return
        self._video_loop = loop
        self._video_time += dt
        duration = self._video_duration or 0.0
        if duration <= 0:
            return
        t = self._video_time
        if loop:
            t = t % duration
        else:
            if t > duration:
                t = duration
                self._video_time = duration
        try:
            frame = self._video_clip.get_frame(t)
            surf = pygame.surfarray.make_surface(np.transpose(frame, (1, 0, 2)))
            surf = pygame.transform.smoothscale(surf, self.render_size)
            self._video_surface = surf
        except Exception as exc:
            print(f"渲染视频帧失败: {exc}")
            self._video_surface = None

    def _stop_video(self):
        try:
            if self._video_clip:
                self._video_clip.close()
        except Exception:
            pass
        self._video_clip = None
        self._video_path = None
        self._video_surface = None
        self._video_duration = None
        self._video_time = 0.0

    def _draw_portrait(self, portrait_path: str, fade_in: bool, dt: float):
        # allow fade-out to continue even if next sub has no portrait
        if not portrait_path:
            if not self._portrait_fadeout_active:
                self._portrait_surface = None
                self._portrait_target_surface = None
                self._portrait_current_path = None
                return
            # keep rendering existing portrait while fading out
            abs_path = self._portrait_current_path
        else:
            abs_path = self._resolve_path(portrait_path)
            if not abs_path.exists() and self.project_path:
                alt = (self.project_path.parent / "resources" / "portraits" / Path(portrait_path).name)
                if alt.exists():
                    abs_path = alt
            if not abs_path.exists():
                return
        if abs_path is None:
            return
        if abs_path not in self._portrait_cache:
            try:
                img = pygame.image.load(str(abs_path)).convert_alpha()
                max_w = int(self.render_size[0] * 0.35)
                max_h = int(self.render_size[1] * 0.7)
                img = self._scale_to_fit(img, max_w, max_h)
                self._portrait_cache[abs_path] = img
                self._portrait_scaled_cache.pop(abs_path, None)
            except Exception:
                return

        base_img = self._portrait_cache[abs_path]
        scale = getattr(self, "portrait_scale", 1.0) or 1.0
        scale = max(0.1, min(5.0, float(scale)))
        if scale != 1.0:
            key = (abs_path, scale)
            target_img = self._portrait_scaled_cache.get(key)
            if target_img is None:
                w = max(1, int(base_img.get_width() * scale))
                h = max(1, int(base_img.get_height() * scale))
                target_img = pygame.transform.smoothscale(base_img, (w, h))
                self._portrait_scaled_cache[key] = target_img
        else:
            target_img = base_img

        # manage fade state
        if self._portrait_current_path != abs_path:
            self._portrait_current_path = abs_path
            self._portrait_fadeout_active = False
            self._portrait_fade_start_alpha = 255
            if fade_in:
                self._portrait_target_surface = target_img
                self._portrait_surface = target_img.copy()
                self._portrait_fade_alpha = 0
                self._portrait_target_alpha = 255
                self._portrait_fade_time = 0.0
            else:
                self._portrait_surface = target_img
                self._portrait_target_surface = None
                self._portrait_fade_alpha = 255
                self._portrait_target_alpha = 255
                self._portrait_fade_time = 0.0

        if fade_in and self._portrait_surface is not None:
            self._portrait_fade_time += dt
            progress = min(1.0, self._portrait_fade_time / max(0.001, self._portrait_fade_duration))
            self._portrait_fade_alpha = int(self._portrait_target_alpha * progress)
            img = self._portrait_surface.copy()
            img.set_alpha(self._portrait_fade_alpha)
        elif self._portrait_fadeout_active and self._portrait_surface is not None:
            self._portrait_fade_time += dt
            progress = min(1.0, self._portrait_fade_time / max(0.001, self._portrait_fade_duration))
            start_alpha = self._portrait_fade_start_alpha if self._portrait_fade_start_alpha is not None else 255
            self._portrait_fade_alpha = int(start_alpha * max(0.0, 1.0 - progress))
            img = self._portrait_surface.copy()
            img.set_alpha(self._portrait_fade_alpha)
            if progress >= 1.0:
                self._portrait_surface = None
                self._portrait_target_surface = None
                self._portrait_current_path = None
                self._portrait_fadeout_active = False
                self._pending_sub_advance = True
        else:
            img = self._portrait_surface if self._portrait_surface is not None else target_img

        if img is None:
            return
        if self.portrait_pos:
            x = int(self.portrait_pos[0] - img.get_width() / 2)
            y = int(self.portrait_pos[1] - img.get_height() / 2)
        else:
            x = self.render_size[0] - img.get_width() - 40
            y = self.render_size[1] - img.get_height() - 60
        self.render_surface.blit(img, (x, y))

    def _maybe_start_portrait_fade_out(self, sub_entry: dict) -> bool:
        if not sub_entry or not sub_entry.get("portrait_fade_out"):
            return False
        if self._portrait_surface is None:
            return False
        self._portrait_fadeout_active = True
        current_alpha = self._portrait_surface.get_alpha()
        self._portrait_fade_start_alpha = current_alpha if current_alpha is not None else 255
        self._portrait_fade_time = 0.0
        return True

    def _resolve_path(self, path_str: str) -> Path:
        p = Path(path_str)
        if p.is_absolute():
            return p
        base = self.project_path.parent if self.project_path else Path.cwd()
        return (base / p).resolve()

    def _pair_from_cfg(self, val, default: tuple[int, int]) -> tuple[int, int]:
        if isinstance(val, (list, tuple)) and len(val) >= 2:
            try:
                return (int(val[0]), int(val[1]))
            except Exception:
                return default
        return default

    def _color_from_cfg(self, val, default: tuple[int, int, int]) -> tuple[int, int, int]:
        if isinstance(val, (list, tuple)) and len(val) >= 3:
            try:
                r, g, b = int(val[0]), int(val[1]), int(val[2])
                return (
                    max(0, min(255, r)),
                    max(0, min(255, g)),
                    max(0, min(255, b)),
                )
            except Exception:
                return default
        return default

    def _current_entry(self) -> dict:
        if self.graph_mode:
            if self.current_node_id is None:
                return {}
            node = self.nodes_map.get(self.current_node_id, {}) or {}
            if node.get("node_type") == "text":
                subs = node.get("sub_dialogues") or []
                if subs and 0 <= self._sub_index < len(subs):
                    sub = subs[self._sub_index]
                    merged = dict(node)
                    merged.update({
                        "speaker": sub.get("speaker", merged.get("speaker", "")),
                        "content": sub.get("text", merged.get("content", "")),
                        "portrait": sub.get("portrait", merged.get("portrait", "")),
                        "voice": sub.get("voice", merged.get("voice", "")),
                        "hide_textbox": bool(sub.get("hide_textbox", False)),
                        "portrait_fade": bool(sub.get("portrait_fade", False)),
                    })
                    return merged
            return node
        if self.dialogues and 0 <= self.current_index < len(self.dialogues):
            return self.dialogues[self.current_index]
        return {}

    def _load_graph_from_flow(self, data: dict):
        flow = data.get("flow_nodes") or {}
        nodes = flow.get("nodes") or []
        connections = flow.get("connections") or []
        self.nodes_map = {n.get("id"): n for n in nodes if n.get("id") is not None}
        self.adjacency = {nid: [] for nid in self.nodes_map}
        self._connection_order = {nid: [] for nid in self.nodes_map}
        indegree = {nid: 0 for nid in self.nodes_map}
        for conn in connections:
            s = conn.get("source")
            t = conn.get("target")
            if s in self.nodes_map and t in self.nodes_map and s != t:
                self.adjacency[s].append(t)
                self._connection_order.setdefault(s, []).append(t)
                indegree[t] = indegree.get(t, 0) + 1
        start_candidates = [nid for nid, deg in indegree.items() if deg == 0]
        if start_candidates:
            self.current_node_id = sorted(start_candidates, key=lambda x: str(x))[0]
        elif self.nodes_map:
            self.current_node_id = sorted(self.nodes_map.keys(), key=lambda x: str(x))[0]
        else:
            self.current_node_id = None
        self.graph_mode = bool(self.nodes_map)
        self._sub_index = 0
        # 预热节点素材，减少首次进入卡顿
        self._warm_caches_from_flow(nodes, preload_limit=100)

    def _advance_to_next_in_graph(self):
        if self.current_node_id is None:
            return
        next_nodes = self._connection_order.get(self.current_node_id) or self.adjacency.get(self.current_node_id, [])
        if not next_nodes:
            print("剧情结束，按 ESC 退出或关闭窗口。")
            return
        self._choice_overlay = False
        self._choice_options = []
        self._choice_targets = []
        target = self._choose_next_branch(next_nodes)
        if target not in self.nodes_map:
            print("分支目标不存在，无法继续。")
            return
        self.current_node_id = target
        self._sub_index = 0
        self._voice_played_index = None
        self._on_enter_node()
        self._reset_typing_state()

    def _open_choice_overlay(self, entry: dict):
        targets = []
        if self.current_node_id is not None:
            targets = self._connection_order.get(self.current_node_id) or self.adjacency.get(self.current_node_id, [])
        options = entry.get("options") or []
        if not targets:
            self._advance_to_next_in_graph()
            return
        if not options:
            options = [f"选项 {i+1}" for i in range(len(targets))]
        if len(options) > len(targets):
            options = options[: len(targets)]
        else:
            targets = targets[: len(options)]
        self._choice_options = options
        self._choice_targets = targets
        self._choice_overlay = True

    def _apply_choice(self, idx: int):
        if not self._choice_overlay:
            return
        if idx is None or idx < 0 or idx >= len(self._choice_targets):
            return
        target = self._choice_targets[idx]
        self._choice_overlay = False
        self._choice_options = []
        self._choice_targets = []
        self.variables["last_choice"] = idx
        if target not in self.nodes_map:
            print("选择目标不存在，结束剧情。")
            return
        self.current_node_id = target
        self._sub_index = 0
        self._voice_played_index = None
        self._on_enter_node()
        self._reset_typing_state()

    def _resolve_condition_branch(self, entry: dict):
        targets = self.adjacency.get(self.current_node_id, []) if self.current_node_id is not None else []
        if not targets:
            self._advance_to_next_in_graph()
            return
        var_name = (entry.get("condition_var") or "").strip()
        value_token = entry.get("condition_value")
        op = entry.get("condition_op", "==")
        is_const = bool(entry.get("condition_const", False))
        chosen = None

        def _as_float(val):
            try:
                return float(val)
            except Exception:
                return None

        if var_name and targets:
            left_val = self.variables.get(var_name)
            right_val = value_token if is_const else self.variables.get(str(value_token), 0.0)
            lf = _as_float(left_val)
            rf = _as_float(right_val)
            if lf is not None and rf is not None:
                l_cmp, r_cmp = lf, rf
            else:
                l_cmp, r_cmp = str(left_val), str(right_val)

            result = False
            if op == "==":
                result = l_cmp == r_cmp
            elif op == "!=":
                result = l_cmp != r_cmp
            elif op == ">":
                result = l_cmp > r_cmp
            elif op == ">=":
                result = l_cmp >= r_cmp
            elif op == "<":
                result = l_cmp < r_cmp
            elif op == "<=":
                result = l_cmp <= r_cmp

            if result:
                chosen = targets[0] if targets else None
            elif len(targets) > 1:
                chosen = targets[1]

        if chosen is None and targets:
            chosen = self._choose_next_branch(targets)
        if chosen is None:
            print("条件节点无有效分支，结束剧情。")
            return
        if chosen not in self.nodes_map:
            print("条件分支目标不存在，无法继续。")
            return
        self.current_node_id = chosen
        self._sub_index = 0
        self._voice_played_index = None
        self._on_enter_node()
        self._reset_typing_state()

    def _scale_to_fit(self, img: pygame.Surface, max_w: int, max_h: int) -> pygame.Surface:
        w, h = img.get_size()
        scale = min(max_w / w, max_h / h, 1.0)
        if scale >= 0.999:
            return img
        new_size = (int(w * scale), int(h * scale))
        return pygame.transform.smoothscale(img, new_size)

    def _blit_to_window(self):
        """Letterbox project render surface到真实窗口，保持工程分辨率的宽高比。"""
        screen_w, screen_h = self.screen.get_size()
        target_w, target_h = self.render_size
        scale = min(screen_w / target_w, screen_h / target_h)
        scaled_w = int(target_w * scale)
        scaled_h = int(target_h * scale)

        blit_surface = self.render_surface
        if scaled_w != target_w or scaled_h != target_h:
            blit_surface = pygame.transform.smoothscale(self.render_surface, (scaled_w, scaled_h))

        x = (screen_w - scaled_w) // 2
        y = (screen_h - scaled_h) // 2
        self.screen.fill((0, 0, 0))
        self.screen.blit(blit_surface, (x, y))

    def _build_dialogues_from_flow(self, data: dict) -> list[dict]:
        """Traverse nodes following connections to build dialogue order."""
        flow = data.get("flow_nodes") or {}
        nodes = flow.get("nodes") or []
        connections = flow.get("connections") or []

        nodes_map = {n.get("id"): n for n in nodes if n.get("id") is not None}
        if not nodes_map:
            return []

        indegree = {nid: 0 for nid in nodes_map}
        adjacency: dict[int | str, list[int | str]] = {nid: [] for nid in nodes_map}
        for conn in connections:
            s = conn.get("source")
            t = conn.get("target")
            if s in nodes_map and t in nodes_map and s != t:
                adjacency.setdefault(s, []).append(t)
                indegree[t] = indegree.get(t, 0) + 1

        start_candidates = [nid for nid, deg in indegree.items() if deg == 0]
        if start_candidates:
            current = sorted(start_candidates, key=lambda x: str(x))[0]
        else:
            current = sorted(nodes_map.keys(), key=lambda x: str(x))[0]

        dialogues: list[dict] = []
        visited: set[int | str] = set()
        while current is not None and current in nodes_map and current not in visited:
            n = nodes_map[current]
            visited.add(current)
            node_id = n.get("id")
            title = n.get("title", "")
            base_content = n.get("content") or title
            base_speaker = n.get("speaker") or ""
            background = n.get("background") or ""
            portrait = n.get("portrait") or ""
            voice = n.get("voice") or ""
            video = n.get("video") or ""
            video_loop = bool(n.get("video_loop", False))
            bgm = n.get("bgm") or ""
            bgm_loop = bool(n.get("bgm_loop", True))
            bg_fade_in = bool(n.get("bg_fade_in", False))
            stop_bgm = bool(n.get("stop_bgm"))
            node_type = n.get("node_type", "text")
            options = n.get("options", [])
            condition_var = n.get("condition_var", "")
            condition_value = n.get("condition_value", "")
            condition_op = n.get("condition_op", "==")
            condition_const = bool(n.get("condition_const", False))
            var_ops = n.get("var_ops", [])
            sub_items = n.get("sub_dialogues") or []
            if node_type == "text" and sub_items:
                for sub in sub_items:
                    if not isinstance(sub, dict):
                        continue
                    dialogues.append({
                        "node_id": node_id,
                        "speaker": sub.get("speaker") or base_speaker,
                        "content": sub.get("text") or base_content,
                        "background": background,
                        "portrait": sub.get("portrait") or portrait,
                        "voice": sub.get("voice") or voice,
                        "bgm": bgm,
                        "bgm_loop": bgm_loop,
                        "bg_fade_in": bg_fade_in,
                        "stop_bgm": stop_bgm,
                        "node_type": node_type,
                        "options": options,
                        "condition_var": condition_var,
                        "condition_value": condition_value,
                        "condition_op": condition_op,
                        "condition_const": condition_const,
                        "var_ops": var_ops,
                        "video": video,
                        "video_loop": video_loop,
                        "hide_textbox": bool(sub.get("hide_textbox", False)),
                        "portrait_fade": bool(sub.get("portrait_fade", False)),
                        "portrait_fade_out": bool(sub.get("portrait_fade_out", False)),
                    })
            else:
                if base_content or base_speaker or background or portrait or voice or bgm or stop_bgm:
                    dialogues.append({
                        "node_id": node_id,
                        "speaker": base_speaker,
                        "content": base_content,
                        "background": background,
                        "portrait": portrait,
                        "voice": voice,
                        "video": video,
                        "video_loop": video_loop,
                        "bgm": bgm,
                        "bgm_loop": bgm_loop,
                        "bg_fade_in": bg_fade_in,
                        "stop_bgm": stop_bgm,
                        "node_type": node_type,
                        "options": options,
                        "condition_var": condition_var,
                        "condition_value": condition_value,
                        "condition_op": condition_op,
                        "condition_const": condition_const,
                        "var_ops": var_ops,
                        "hide_textbox": False,
                        "portrait_fade": False,
                    })

            next_nodes = [cid for cid in adjacency.get(current, []) if cid not in visited]
            if not next_nodes:
                break
            current = self._choose_next_branch(next_nodes)

        return dialogues

    def _apply_window_size(self, size: tuple[int, int]):
        """Recalculate layout based on current window size."""
        try:
            w = max(320, int(size[0]))
            h = max(240, int(size[1]))
        except Exception:
            w, h = self.window_size

        self.window_size = (w, h)
        if not self.is_fullscreen:
            self.windowed_size = (w, h)
        self.render_size = self.project_resolution
        self.render_surface = pygame.Surface(self.render_size)
        layout = self._active_ui_layout or {}

        def _rect_or_default(key: str, fallback: list[int]):
            val = layout.get(key)
            if isinstance(val, (list, tuple)) and len(val) == 4:
                try:
                    return pygame.Rect(int(val[0]), int(val[1]), int(val[2]), int(val[3]))
                except Exception:
                    return pygame.Rect(*fallback)
            return pygame.Rect(*fallback)

        self.text_area = _rect_or_default("text_area", [40, self.render_size[1] - 200, self.render_size[0] - 80, 160])
        self.name_area = _rect_or_default("name_area", [40, self.render_size[1] - 240, 200, 32])
        portrait_pos = layout.get("portrait_pos") if isinstance(layout, dict) else None
        if isinstance(portrait_pos, (list, tuple)) and len(portrait_pos) == 2:
            try:
                self.portrait_pos = (int(portrait_pos[0]), int(portrait_pos[1]))
            except Exception:
                self.portrait_pos = None
        else:
            self.portrait_pos = None

        ps = 1.0
        if isinstance(layout, dict):
            try:
                ps = float(layout.get("portrait_scale", 1.0) or 1.0)
            except Exception:
                ps = 1.0
        self.portrait_scale = max(0.1, min(5.0, ps))
        self._bg_cache.clear()
        self._portrait_scaled_cache.clear()

    def _append_history(self, entry: dict | None):
        if not entry:
            return
        speaker = entry.get("speaker") or ""
        content = entry.get("content") or ""
        if not content:
            return
        self._history.append({"speaker": speaker, "content": content})
        if len(self._history) > 10:
            self._history = self._history[-10:]

    def _load_font(self, size: int, bold: bool = False):
        try:
            return pygame.font.SysFont("SimHei", size, bold=bold)
        except Exception:
            return pygame.font.Font(None, size)

    def toggle_fullscreen(self):
        """Toggle fullscreen mode with F11."""
        if not self.is_fullscreen:
            self.windowed_size = self.window_size
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
            self.is_fullscreen = True
        else:
            self.screen = pygame.display.set_mode(self.windowed_size)
            self.is_fullscreen = False

        new_size = self.screen.get_size()
        self._apply_window_size(new_size)
        self._bg_cache.clear()  # force re-scale backgrounds for new resolution

    def _choose_next_branch(self, candidates: list[int | str]) -> int | str:
        if not candidates:
            return None
        if self.branch_strategy == "random":
            return random.choice(candidates)
        # default: pick smallest id for deterministic order
        return sorted(candidates, key=lambda x: str(x))[0]

    def _ensure_bgm(self, bgm_path: str, loop: bool = True, fade: bool = False):
        if not bgm_path:
            return
        abs_path = self._resolve_path(bgm_path)
        if not abs_path.exists():
            return
        if self._bgm_current == abs_path and self._bgm_current_loop == loop:
            return
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            if fade and self._bgm_current:
                try:
                    pygame.mixer.music.fadeout(400)
                except Exception:
                    pass
            pygame.mixer.music.load(str(abs_path))
            master = float(self._settings.get("master_volume", 1.0))
            bgm_vol = float(self._settings.get("bgm_volume", 1.0))
            volume = max(0.0, min(1.0, master * bgm_vol))
            pygame.mixer.music.set_volume(volume)
            loops = -1 if loop else 0
            pygame.mixer.music.play(loops)
            self._bgm_current = abs_path
            self._bgm_current_loop = loop
        except Exception:
            pass

    def _ensure_voice(self, voice_path: str):
        if not voice_path:
            return
        abs_path = self._resolve_path(voice_path)
        if not abs_path.exists():
            return
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            if abs_path not in self._voice_cache:
                self._voice_cache[abs_path] = pygame.mixer.Sound(str(abs_path))
            sound = self._voice_cache[abs_path]
            if self._voice_channel and self._voice_channel.get_busy():
                self._voice_channel.stop()
            master = float(self._settings.get("master_volume", 1.0))
            voice_vol = float(self._settings.get("voice_volume", 1.0))
            volume = max(0.0, min(1.0, master * voice_vol))
            sound.set_volume(volume)
            self._voice_channel = sound.play()
        except Exception:
            pass

    def _schedule_voice(self, voice_path: str, delay: float = 0.05):
        if not voice_path:
            self._pending_voice_path = None
            self._pending_voice_delay = 0.0
            return
        abs_path = self._resolve_path(voice_path)
        if not abs_path.exists():
            self._pending_voice_path = None
            self._pending_voice_delay = 0.0
            return
        self._pending_voice_path = abs_path
        self._pending_voice_delay = max(0.0, delay)

    def _process_pending_audio(self, dt: float):
        if not self._pending_voice_path:
            return
        self._pending_voice_delay -= dt
        if self._pending_voice_delay <= 0:
            self._ensure_voice(str(self._pending_voice_path))
            self._pending_voice_path = None
            self._pending_voice_delay = 0.0

    def _stop_bgm(self):
        """Stop current BGM playback and clear state."""
        try:
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
        except Exception:
            pass
        self._bgm_current = None

    def _stop_voice_playback(self):
        """Stop any playing voice and clear pending schedule."""
        self._pending_voice_path = None
        self._pending_voice_delay = 0.0
        try:
            if self._voice_channel and self._voice_channel.get_busy():
                self._voice_channel.stop()
        except Exception:
            pass
        self._voice_channel = None

    def save_game(self, slot: int = 1):
        try:
            self.save_dir.mkdir(parents=True, exist_ok=True)
            save_data = {
                "current_index": self.current_index,
                "current_node_id": self.current_node_id,
                "graph_mode": self.graph_mode,
                "variables": self.variables,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "branch_strategy": self.branch_strategy,
                "window_size": list(self.window_size),
                "summary": self._build_summary(),
            }
            save_path = self.save_dir / f"slot_{slot}.json"
            with open(save_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(save_data, f, allow_unicode=True)
            print(f"存档完成：{save_path}")
        except Exception as exc:
            print(f"存档失败: {exc}")

    def load_game(self, slot: int = 1):
        try:
            save_path = self.save_dir / f"slot_{slot}.json"
            if not save_path.exists():
                print("未找到存档文件")
                return
            self.fast_skip = False
            self._fast_skip_timer = 0.0
            with open(save_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            self.branch_strategy = data.get("branch_strategy", self.branch_strategy)
            self.variables = data.get("variables", {})
            self._history = []
            self._history_overlay = False
            saved_graph = bool(data.get("graph_mode", False))
            if saved_graph and self.nodes_map:
                node_id = data.get("current_node_id")
                if node_id not in self.nodes_map:
                    print("存档数据已过期或无效")
                    return
                self.graph_mode = True
                self.current_node_id = node_id
                self.current_index = 0
            else:
                idx = int(data.get("current_index", 0))
                if idx < 0 or idx >= len(self.dialogues):
                    print("存档数据已过期或无效")
                    return
                self.graph_mode = False
                self.current_index = idx
            size_data = data.get("window_size")
            if isinstance(size_data, (list, tuple)) and len(size_data) == 2:
                self.screen = pygame.display.set_mode(size_data)
                self._apply_window_size(tuple(size_data))
            self._stop_bgm()
            self._voice_played_index = None
            self._on_enter_node()
            self._reset_typing_state()
            print(f"读取存档完成：{save_path}")
            self.mode = "game"
            self._overlay_return_mode = None
        except Exception as exc:
            print(f"读档失败: {exc}")

    def _build_summary(self) -> str:
        entry = self._current_entry() or {"speaker": "", "content": ""}
        speaker = entry.get("speaker") or ""
        content = entry.get("content") or entry.get("title") or ""
        snippet = content[:20] + ("..." if len(content) > 20 else "")
        return f"{speaker}: {snippet}" if speaker or snippet else ""

    def _render_debug_hud(self, entry: dict):
        def _wrap_text(text: str, max_width: int) -> list[str]:
            wrapped: list[str] = []
            current = ""
            for ch in text:
                test = current + ch
                if current and self.font.size(test)[0] > max_width:
                    wrapped.append(current)
                    current = ch
                else:
                    current = test
            if current:
                wrapped.append(current)
            return wrapped or [""]

        max_width = 620
        mv = float(self._settings.get("master_volume", 1.0))
        bv = float(self._settings.get("bgm_volume", 1.0))
        vv = float(self._settings.get("voice_volume", 1.0))

        if self.graph_mode:
            node_id = entry.get("id") or entry.get("node_id") or self.current_node_id
            node_type = entry.get("node_type", "text") if isinstance(entry, dict) else "text"
            header = f"Node: {node_id if node_id is not None else '-'} ({node_type})"
        else:
            idx = self.current_index + 1
            total = len(self.dialogues)
            node_id = entry.get("node_id") if isinstance(entry, dict) else None
            header = f"Node: {node_id if node_id is not None else '-'} ({idx}/{total})"

        base_lines = [
            header,
            f"Skip: {'ON' if self.fast_skip else 'OFF'}  Vol M/B/V: {mv:.2f}/{bv:.2f}/{vv:.2f}",
        ]

        content_text = entry.get("content") or entry.get("title") or ""
        if content_text:
            base_lines.append(f"Text: {content_text}")

        if self.variables:
            vars_str = ", ".join(f"{k}={v}" for k, v in sorted(self.variables.items()))
        else:
            vars_str = "<无全局变量>"
        base_lines.append(f"Vars: {vars_str}")

        rendered_lines: list[str] = []
        for line in base_lines:
            rendered_lines.extend(_wrap_text(line, max_width))

        height = 12 + len(rendered_lines) * self.font.get_linesize() + 8
        surface = pygame.Surface((max_width + 20, height), pygame.SRCALPHA)
        surface.fill((0, 0, 0, 160))
        y = 8
        for line in rendered_lines:
            text_surf = self.font.render(line, True, (180, 220, 180))
            surface.blit(text_surf, (10, y))
            y += self.font.get_linesize()
        self.render_surface.blit(surface, (10, 10))

    def _render_overlay(self):
        overlay = pygame.Surface(self.render_size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        if self._settings_overlay:
            title = "设置 (F10)"
            title_surf = self.name_font.render(title, True, (255, 255, 255))
            overlay.blit(title_surf, (40, 40))
            y = 90
            mv = float(self._settings.get("master_volume", 1.0))
            bv = float(self._settings.get("bgm_volume", 1.0))
            vv = float(self._settings.get("voice_volume", 1.0))
            info_lines = [
                f"文本速度: {self.typing_speed:.1f} ( +/- 调整 )",
                f"主音量: {mv:.2f} ( , . 调整, M 静音切换 )",
                f"BGM音量: {bv:.2f} ( [ ] 调整 )",
                f"语音音量: {vv:.2f} ( ; ' 调整 )",
                "Enter 保存并关闭, ESC 取消",
            ]
            for line in info_lines:
                surf = self.font.render(line, True, (230, 230, 230))
                overlay.blit(surf, (40, y))
                y += self.font.get_linesize() + 6
        else:
            title = "保存到槽位 (1-5)" if self._save_overlay else "读取槽位 (1-5)"
            title_surf = self.name_font.render(title, True, (255, 255, 255))
            overlay.blit(title_surf, (40, 40))

            slots = self._read_slots_meta()
            y = 90
            for idx in range(1, self._save_slots + 1):
                meta = slots.get(idx)
                line = f"[{idx}] "
                if meta:
                    line += f"{meta.get('timestamp','')} - {meta.get('summary','')}"
                else:
                    line += "<空>"
                surf = self.font.render(line, True, (230, 230, 230))
                overlay.blit(surf, (40, y))
                y += self.font.get_linesize() + 6

            hint = "ESC 取消" if (self._save_overlay or self._load_overlay) else ""
            if hint:
                hint_surf = self.font.render(hint, True, (200, 200, 200))
                overlay.blit(hint_surf, (40, y + 10))

        self.render_surface.blit(overlay, (0, 0))

    def _render_choice_overlay(self):
        overlay = pygame.Surface(self.render_size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        title = "请选择 (数字键)"
        title_surf = self.name_font.render(title, True, (255, 255, 255))
        overlay.blit(title_surf, (40, 40))

        y = 100
        for idx, text in enumerate(self._choice_options):
            line = f"[{idx + 1}] {text}"
            surf = self.font.render(line, True, (230, 230, 230))
            overlay.blit(surf, (60, y))
            y += self.font.get_linesize() + 6

        hint = "ESC 取消"
        hint_surf = self.font.render(hint, True, (200, 200, 200))
        overlay.blit(hint_surf, (60, y + 10))

        self.render_surface.blit(overlay, (0, 0))

    def _restore_mode_if_needed(self):
        if self._overlay_return_mode:
            self.mode = self._overlay_return_mode
            self._overlay_return_mode = None

    def _read_slots_meta(self) -> dict[int, dict]:
        meta = {}
        if not self.save_dir.exists():
            return meta
        for idx in range(1, self._save_slots + 1):
            path = self.save_dir / f"slot_{idx}.json"
            if not path.exists():
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                meta[idx] = {
                    "timestamp": data.get("timestamp", ""),
                    "summary": data.get("summary", ""),
                }
            except Exception:
                continue
        return meta

    def _load_settings(self) -> dict:
        defaults = {
            "typing_speed": 24.0,
            "master_volume": 1.0,
            "bgm_volume": 1.0,
            "voice_volume": 1.0,
        }
        if not self.settings_path.exists():
            return defaults
        try:
            with open(self.settings_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            defaults.update({k: data.get(k) for k in defaults.keys() if k in data})
        except Exception:
            pass
        return defaults

    def _save_settings(self):
        try:
            with open(self.settings_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(self._settings, f, allow_unicode=True)
            print(f"设置已保存: {self.settings_path}")
        except Exception as exc:
            print(f"保存设置失败: {exc}")

    def _apply_settings(self):
        self.typing_speed = float(self._settings.get("typing_speed", 24.0))
        master_volume = float(self._settings.get("master_volume", 1.0))
        master_volume = max(0.0, min(1.0, master_volume))
        self._settings["master_volume"] = master_volume
        bgm_volume = float(self._settings.get("bgm_volume", 1.0))
        bgm_volume = max(0.0, min(1.0, bgm_volume))
        self._settings["bgm_volume"] = bgm_volume
        voice_volume = float(self._settings.get("voice_volume", 1.0))
        voice_volume = max(0.0, min(1.0, voice_volume))
        self._settings["voice_volume"] = voice_volume
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.music.set_volume(master_volume * bgm_volume)
        except Exception:
            pass

    def _handle_settings_key(self, key) -> bool:
        """Handle keys in settings overlay; return True if consumed."""
        changed = False
        if key in (pygame.K_EQUALS, pygame.K_PLUS):
            self._settings["typing_speed"] = min(120.0, self.typing_speed + 4)
            changed = True
        elif key == pygame.K_MINUS:
            self._settings["typing_speed"] = max(4.0, self.typing_speed - 4)
            changed = True
        elif key == pygame.K_COMMA:
            self._settings["master_volume"] = max(0.0, self._settings.get("master_volume", 1.0) - 0.1)
            changed = True
        elif key == pygame.K_PERIOD:
            self._settings["master_volume"] = min(1.0, self._settings.get("master_volume", 1.0) + 0.1)
            changed = True
        elif key == pygame.K_LEFTBRACKET:
            self._settings["bgm_volume"] = max(0.0, self._settings.get("bgm_volume", 1.0) - 0.1)
            changed = True
        elif key == pygame.K_RIGHTBRACKET:
            self._settings["bgm_volume"] = min(1.0, self._settings.get("bgm_volume", 1.0) + 0.1)
            changed = True
        elif key == pygame.K_SEMICOLON:
            self._settings["voice_volume"] = max(0.0, self._settings.get("voice_volume", 1.0) - 0.1)
            changed = True
        elif key == pygame.K_QUOTE:
            self._settings["voice_volume"] = min(1.0, self._settings.get("voice_volume", 1.0) + 0.1)
            changed = True
        elif key == pygame.K_m:
            mv = self._settings.get("master_volume", 1.0)
            self._settings["master_volume"] = 0.0 if mv > 0 else 1.0
            changed = True
        elif key == pygame.K_RETURN:
            self._apply_settings()
            self._save_settings()
            self._settings_overlay = False
            return True
        elif key == pygame.K_ESCAPE:
            self._settings_overlay = False
            return True

        if changed:
            self._apply_settings()
            return True
        return False

    def quit_game(self):
        """退出游戏，释放资源"""
        self._stop_voice_playback()
        try:
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
        except Exception:
            pass
        self.running = False
        pygame.quit()
        print("游戏预览窗口已关闭")


if __name__ == "__main__":
    runtime = VNGameRuntime()
    runtime.start_game()

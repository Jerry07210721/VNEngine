# -*- coding: utf-8 -*-
"""Game runtime window using Pygame."""
import sys
import os
import subprocess
import random
import threading
import builtins
from datetime import datetime
from pathlib import Path
import shutil
import glob
import re
from decimal import Decimal, InvalidOperation
import pygame
import yaml
import json
import math
import numpy as np

from src.game.var_expr import eval_var_expr

from src.game.choice_utils import normalize_choice_timeout_config

from src.game.save_slot_utils import (
    AUTO_SAVE_SLOT,
    DEFAULT_PAGE_SIZE,
    clamp_page,
    digit_to_slot,
    page_count,
    slot_file_path,
    slot_thumbnail_path,
)


class VNGameRuntime:
    """视觉小说游戏运行时，负责游戏窗口的初始化和事件循环"""

    def __init__(self, game_title: str = "我的视觉小说", window_size=(800, 600), project_path: str | None = None):
        self.project_path = Path(project_path).resolve() if project_path else None

        # 工程目录：用于资源解析/脚本沙盒/默认存档目录等。
        # 必须在 _load_dialogues() 之前初始化，因为读取工程配置时会用到。
        try:
            self._project_dir = self.project_path.parent if self.project_path else Path.cwd().resolve()
        except Exception:
            self._project_dir = Path.cwd()
        self._function_fs_root: Path = self._project_dir
        self._allow_unsafe_function_scripts: bool = False

        cfg = self._probe_game_config(self.project_path) if self.project_path else {}
        init_w = int(cfg.get("window_width", window_size[0])) if isinstance(cfg, dict) else window_size[0]
        init_h = int(cfg.get("window_height", window_size[1])) if isinstance(cfg, dict) else window_size[1]
        init_size = (max(320, init_w), max(240, init_h))
        self.project_resolution = init_size  # logical render resolution driven by project
        self.windowed_size = init_size  # remember windowed size for exiting fullscreen
        resolved_title = cfg.get("game_title") if isinstance(cfg, dict) else None

        pygame.init()
        pygame.display.set_caption(resolved_title or game_title)
        self._set_default_window_icon()
        self.base_window_size = init_size
        self.window_size = init_size
        self.render_size = self.project_resolution
        self.render_surface = pygame.Surface(self.render_size)
        self.is_fullscreen = False
        self.screen = pygame.display.set_mode(self.window_size)

        # Loading progress UI (blocking): staged 0-100% updates.
        self._loading_active: bool = False
        self._loading_stack: list[tuple[float, float]] = []  # (base, span)
        self._loading_message: str = ""
        self._loading_subtitle: str | None = None

        # Loading overlay style/config (designer driven)
        self._loading_overlay_cfg: dict = {}
        try:
            self._loading_overlay_cfg = self._normalize_loading_overlay_cfg((cfg or {}).get("loading_overlay"))
        except Exception:
            self._loading_overlay_cfg = self._normalize_loading_overlay_cfg({})

        # Persistent variables for protected globals
        self._persistent_vars_path = (self._project_dir / "persistent_vars.yaml")
        self._persistent_vars: dict[str, float] = {}
        self._persistent_vars_dirty: bool = False
        self._protected_vars: set[str] = set()
        self._load_persistent_vars()

        # Staged boot progress so large projects don't look frozen.
        if self._loading_overlay_enabled_for("load_game"):
            self._loading_begin("加载工程中...", subtitle=(self.project_path.name if self.project_path else None))
            self._loading_progress(0.10, "初始化运行环境...", subtitle=(self.project_path.name if self.project_path else None))
        self.mode = "menu"  # menu or game
        self.clock = pygame.time.Clock()
        self.running = False

        # 存档缩略图缓存：key=(path, w, h, mtime)
        self._slot_thumbnail_cache: dict[tuple[str, int, int, float], pygame.Surface] = {}

        # 存档/菜单配置（来自 game_config，可被项目覆盖）
        try:
            self._save_slots = int((cfg or {}).get("save_slots", 5))
        except Exception:
            self._save_slots = 5
        self._save_slots = max(1, min(200, self._save_slots))
        self._save_page_size = DEFAULT_PAGE_SIZE
        self._save_page = 0
        self._enable_autosave_on_menu = bool((cfg or {}).get("enable_autosave_on_menu", True))
        self._help_overlay = False
        self._help_hotkey_name = str((cfg or {}).get("help_hotkey", "F1") or "F1")
        self._help_key = None  # pygame keycode
        self._help_right_click = bool((cfg or {}).get("help_right_click", True))
        self._exit_confirm_overlay = False
        self._exit_confirm_choice = 1  # 1=确认, 0=取消

        # 一键隐藏UI（用于截图）：隐藏对话框/姓名框/功能菜单按钮组
        self._screenshot_hide_ui: bool = False

        # 主菜单多套样式：缓存 game_config + 当前选中的主菜单索引
        self._game_cfg_cache: dict | None = cfg if isinstance(cfg, dict) else None
        self._active_menu_index: int = 0

        # 从主菜单“开始游戏”是否重置全局变量（可在主菜单设计器配置）
        self._reset_globals_on_start: bool = bool((cfg or {}).get("reset_globals_on_start", True))

        # global text styles (dialogue/name)
        self._dialogue_style: dict = {}
        self._name_style: dict = {}
        # per-entry optional text style overrides cache
        self._entry_text_style_cache: dict[str, tuple[dict, dict, object, object]] = {}
        self._apply_text_style_config(cfg if isinstance(cfg, dict) else {})

        self._loading_progress(0.20, "加载字体与界面配置...", subtitle=(self.project_path.name if self.project_path else None))

        self.box_color = (0, 0, 0, 190)
        self.bg_color = (28, 32, 40)
        self.text_margin = 24
        self.text_area = None
        self.name_area = None
        self.portrait_pos = None
        self.portrait_size = None
        self.portrait2_pos = None
        self.portrait2_size = None
        self._portrait_cache = {}
        self._portrait_scaled_cache = {}
        self._portrait2_scaled_cache = {}
        self._bg_cache = {}
        self.portrait_scale = 1.0
        self.portrait2_scale = 1.0
        self._ui_layout_cache: dict[Path, dict] = {}
        self._ui_frame_cache: dict[tuple[Path, int, int, int], pygame.Surface] = {}
        self._ui_overlay_bg_cache: dict[tuple[Path, int, int], pygame.Surface] = {}
        self._active_ui_layout: dict | None = None
        self.branch_strategy = "first"
        self.save_dir = (self.project_path.parent / "saves") if self.project_path else Path.cwd() / "saves"
        self.settings_path = (self.project_path.parent / "settings.yaml") if self.project_path else Path.cwd() / "settings.yaml"
        self.graph_mode = False
        self.nodes_map: dict[int | str, dict] = {}
        self.adjacency: dict[int | str, list[int | str]] = {}
        self._connection_order: dict[int | str, list[int | str]] = {}
        self.current_node_id: int | str | None = None
        self._preview_start_node_id: int | str | None = None
        self.variables: dict[str, str | int | float | bool] = {}
        self.project_data: dict | None = None
        self._global_var_defs: list[dict] = []
        self._choice_overlay = False
        self._choice_options: list[str] = []
        self._choice_targets: list[int | str] = []
        self._choice_timeout_remaining: float | None = None
        self._choice_default_index: int = -1

        # choice button group (optional, from UI layout json; mouse-enabled)
        self._choice_buttons_enabled: bool = False
        self._choice_button_pos: tuple[int, int] = (120, 140)
        self._choice_button_spacing: int = 12
        self._choice_button_scale: float = 1.0
        self._choice_button_hover_zoom: float = 1.08
        self._choice_button_orientation: str = "vertical"  # 'vertical' | 'horizontal'
        self._choice_button_font_size: int = 20
        self._choice_button_text_color: tuple[int, int, int] = (230, 230, 230)
        self._choice_button_text_hover_color: tuple[int, int, int] = (255, 255, 255)
        self._choice_overlay_alpha: int = 180
        self._choice_button_bg_image: str = ""
        self._choice_button_bg_alpha: int = 255
        self._choice_button_padding: tuple[int, int] = (18, 10)
        self._choice_button_min_size: tuple[int, int] = (0, 0)
        self._choice_selected: int = -1
        self._choice_button_hitboxes: list[pygame.Rect | None] = []
        self._choice_button_bg_surface_cache: dict[str, pygame.Surface] = {}
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
        self._menu_title_scale: float = 1.0
        self._menu_option_pos: tuple[int, int] = (80, 140)
        self._menu_option_color: tuple[int, int, int] = (255, 255, 255)
        self._menu_option_scale: float = 1.0
        self._menu_title_image_path: str = ""
        self._menu_title_image_surface: pygame.Surface | None = None
        self._menu_title_image_pos: tuple[int, int] = (400, 80)
        self._menu_title_image_scale: float = 1.0

        # menu items defaults (may be overridden by project config in _load_dialogues/_apply_menu_config)
        self._menu_items = [
            {"label": "开始游戏", "action": "start"},
            {"label": "继续", "action": "continue"},
            {"label": "读取存档", "action": "load"},
            {"label": "设置", "action": "settings"},
            {"label": "退出", "action": "exit"},
        ]
        self._menu_option_spacing: int = 10
        self._menu_option_selected_zoom: float = 1.08
        self._menu_option_hover_color: tuple[int, int, int] = (255, 255, 255)
        self._menu_option_indicator: bool = False
        self._menu_option_indicator_image_path: str = ""
        self._menu_option_indicator_image_scale: float = 1.0
        self._menu_option_indicator_image_surface: pygame.Surface | None = None
        self._menu_option_image_surfaces: dict[str, pygame.Surface] = {}
        self._menu_selected = 0
        # runtime-only: menu hit boxes (render-surface coordinates)
        self._menu_item_hitboxes: list[pygame.Rect | None] = []

        # mouse cursor state (hand over clickable items)
        self._mouse_cursor_is_hand: bool = False

        # function script runtime UI/FX + timers
        self._script_time_now: float = 0.0
        self._script_timer_lock = threading.Lock()
        self._script_timer_next_id: int = 1
        self._script_timers: dict[int, dict] = {}

        self._script_toasts: list[dict] = []
        self._script_modal_message: dict | None = None

        self._script_flash: dict | None = None
        self._script_shake: dict | None = None
        self._script_shake_offset: tuple[float, float] = (0.0, 0.0)

        # script-driven top-most image overlays
        self._script_images: dict[str, dict] = {}
        self._script_image_cache: dict[tuple[str, int, int, int], pygame.Surface] = {}
        self._script_image_next_id: int = 1

        # script-driven input lock (game mode): time-based and/or until-expression
        self._script_input_lock_remaining: float | None = None
        self._script_input_lock_until_expr: str | None = None
        self._script_input_lock_until_timeout: float | None = None

        # when set, auto cursor changes are overridden
        self._script_cursor_lock_style: str | None = None

        # function menu overlays (save/load/settings/history/help)
        self._function_menus_enabled: bool = False
        self._function_menus_cfg: dict = {}
        self._function_menus_from_project: bool = False
        self._overlay_hover: str | None = None
        self._overlay_hitboxes: dict[str, pygame.Rect] = {}
        self._overlay_slot_hitboxes: list[tuple[int, pygame.Rect]] = []
        self._overlay_dragging_slider: str | None = None
        self._overlay_settings_snapshot: dict | None = None
        self._overlay_scroll_offset: int = 0

        # in-game HUD button group (mouse-only)
        self._hud_buttons_enabled: bool = False
        self._hud_button_pos: tuple[int, int] = (20, 20)
        self._hud_button_spacing: int = 10
        self._hud_button_scale: float = 1.0
        self._hud_button_selected_zoom: float = 1.08
        self._hud_button_orientation: str = "vertical"  # 'vertical' | 'horizontal'
        self._hud_button_color: tuple[int, int, int] = (255, 255, 255)
        self._hud_button_hover_color: tuple[int, int, int] = (255, 255, 255)
        self._hud_buttons: list[dict] = []
        self._hud_selected: int = -1
        self._hud_button_hitboxes: list[pygame.Rect | None] = []
        self._hud_button_image_surfaces: dict[str, pygame.Surface] = {}

        # prefer project-level function menu config (game_config.function_menus)
        self._apply_function_menus_from_game_config(cfg)

        # now apply window/layout (HUD + function menus need to exist first)
        self._apply_window_size(self.window_size)

        # Project parsing / graph building can be slow on large projects.
        self._loading_push(0.22, 0.90)
        self.dialogues = self._load_dialogues()
        self._loading_pop()
        self._loading_progress(0.98, "准备启动...", subtitle=(self.project_path.name if self.project_path else None))
        self._loading_end()
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
        self._portrait_fade_in_duration = 0.4
        self._portrait_fade_out_duration = 0.4
        self._portrait_fade_time = 0.0
        self._portrait_fadeout_active = False
        self._portrait_bounce_active = False
        self._portrait_bounce_time = 0.0
        self._portrait_bounce_duration = 0.22
        self._portrait_bounce_amplitude = 18
        self._portrait2_surface = None
        self._portrait2_target_surface = None
        self._portrait2_current_path = None
        self._portrait2_fade_alpha = 255
        self._portrait_bounce_played_key = None
        self._portrait2_bounce_played_key = None
        self._portrait2_target_alpha = 255
        self._portrait2_fade_start_alpha = 255
        self._portrait2_fade_in_duration = 0.4
        self._portrait2_fade_out_duration = 0.4
        self._portrait2_fade_time = 0.0
        self._portrait2_fadeout_active = False
        self._portrait2_bounce_active = False
        self._portrait2_bounce_time = 0.0
        self._portrait2_bounce_duration = 0.22
        self._portrait2_bounce_amplitude = 18
        self._pending_sub_advance = False
        self._pending_sub_advance_waiting = 0
        self._auto_next_remaining: float | None = None
        self._voice_cache: dict[Path, pygame.mixer.Sound] = {}
        self._voice_channel = None
        self._sfx_cache: dict[Path, pygame.mixer.Sound] = {}
        self._sfx_channel = None
        self._bgm_current = None
        self._bgm_current_loop = True
        self._voice_played_index = None
        self._sfx_played_index = None
        self._function_played_key = None
        self._function_nodes_by_host: dict[int | str, list[dict]] = {}
        self._script_queue_lock = threading.Lock()
        self._script_main_queue: list[callable] = []
        self._voice_cache: dict[Path, pygame.mixer.Sound] = {}
        self._pending_voice_path: Path | None = None
        self._pending_voice_delay = 0.0
        self._pending_sfx_path: Path | None = None
        self._pending_sfx_delay = 0.0
        self._last_dt = 0.0
        self._save_overlay = False
        self._load_overlay = False
        self._settings_overlay = False
        self._overlay_return_mode: str | None = None
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
        # NOTE: menu defaults are initialized before _load_dialogues; do not overwrite here.
        self._history: list[dict] = []
        self._history_overlay: bool = False
        self._splash_time: float = 2.5
        self._splash_elapsed: float = 0.0

    def _set_default_window_icon(self) -> None:
        """Set a small window icon to avoid blank/default icon during loading."""

        try:
            icon = pygame.Surface((32, 32), pygame.SRCALPHA)
            icon.fill((22, 24, 34, 255))
            try:
                font = pygame.font.SysFont(None, 18, bold=True)
                text = font.render("VN", True, (235, 235, 245))
                icon.blit(text, ((32 - text.get_width()) // 2, (32 - text.get_height()) // 2))
            except Exception:
                pass
            pygame.display.set_icon(icon)
        except Exception:
            pass

    def _normalize_loading_overlay_cfg(self, raw: object) -> dict:
        cfg = raw if isinstance(raw, dict) else {}
        out: dict = {
            "enabled": bool(cfg.get("enabled", True)),
            # per-operation toggles
            "use_on_load_game": bool(cfg.get("use_on_load_game", True)),
            "use_on_enter_menu": bool(cfg.get("use_on_enter_menu", True)),
            "use_on_start_game": bool(cfg.get("use_on_start_game", True)),
            "use_on_load_save": bool(cfg.get("use_on_load_save", True)),

            # per-component visibility
            "show_logo": bool(cfg.get("show_logo", True)),
            "show_title": bool(cfg.get("show_title", True)),
            "show_message": bool(cfg.get("show_message", True)),
            "show_subtitle": bool(cfg.get("show_subtitle", True)),
            "show_bar": bool(cfg.get("show_bar", True)),

            # visuals
            "background_color": cfg.get("background_color", [16, 18, 26]),
            "background_alpha": int(cfg.get("background_alpha", 255) or 255),
            "background_image": str(cfg.get("background_image", "") or ""),

            "logo_image": str(cfg.get("logo_image", "") or ""),
            "logo_rect": cfg.get("logo_rect"),  # [x,y,w,h]

            "title_text": str(cfg.get("title_text", "VNEngine") or "VNEngine"),
            "title_rect": cfg.get("title_rect"),
            "title_style": cfg.get("title_style", {}),

            "message_template": str(cfg.get("message_template", "{message}") or "{message}"),
            "message_rect": cfg.get("message_rect"),
            "message_style": cfg.get("message_style", {}),

            "subtitle_template": str(cfg.get("subtitle_template", "{subtitle}") or "{subtitle}"),
            "subtitle_rect": cfg.get("subtitle_rect"),
            "subtitle_style": cfg.get("subtitle_style", {}),

            "bar_rect": cfg.get("bar_rect"),
            "bar_bg_color": cfg.get("bar_bg_color", [60, 60, 70]),
            "bar_fg_color": cfg.get("bar_fg_color", [110, 160, 255]),
            "bar_radius": int(cfg.get("bar_radius", 6) or 6),

            "show_percent": bool(cfg.get("show_percent", True)),
            "percent_template": str(cfg.get("percent_template", "{percent}%") or "{percent}%"),
            "percent_rect": cfg.get("percent_rect"),
            "percent_style": cfg.get("percent_style", {}),
        }
        # clamp alpha/radius lightly
        try:
            out["background_alpha"] = max(0, min(255, int(out.get("background_alpha", 255))))
        except Exception:
            out["background_alpha"] = 255
        try:
            out["bar_radius"] = max(0, min(30, int(out.get("bar_radius", 6))))
        except Exception:
            out["bar_radius"] = 6
        return out

    def _loading_overlay_enabled_for(self, context: str) -> bool:
        cfg = getattr(self, "_loading_overlay_cfg", None)
        if not isinstance(cfg, dict):
            return True
        if not bool(cfg.get("enabled", True)):
            return False
        key = None
        c = str(context or "").strip().lower()
        if c in {"load_game", "boot", "startup"}:
            key = "use_on_load_game"
        elif c in {"enter_menu", "return_to_title", "to_title", "back_to_title"}:
            key = "use_on_enter_menu"
        elif c in {"start_game", "new_game"}:
            key = "use_on_start_game"
        elif c in {"load_save", "load", "load_slot"}:
            key = "use_on_load_save"
        if key is None:
            return True
        return bool(cfg.get(key, True))

    def _render_blocking_loading_screen(self, message: str, subtitle: str | None = None) -> None:
        """Render a single loading frame and pump events.

        For staged progress, use _loading_begin/_loading_progress/_loading_end.
        """

        self._render_blocking_loading_screen_with_progress(message, subtitle=subtitle, progress=None)

    def _render_blocking_loading_screen_with_progress(self, message: str, subtitle: str | None = None, progress: float | None = None) -> None:
        try:
            screen = getattr(self, "screen", None)
            if screen is None:
                return
            w, h = screen.get_size()
            cfg = getattr(self, "_loading_overlay_cfg", None)
            cfg = cfg if isinstance(cfg, dict) else {}

            surf = pygame.Surface((w, h), pygame.SRCALPHA)

            def _color(val, default: tuple[int, int, int]) -> tuple[int, int, int]:
                try:
                    return self._overlay_color(val, default)
                except Exception:
                    return default

            def _rect(val, default: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
                if isinstance(val, (list, tuple)) and len(val) == 4:
                    try:
                        return (int(val[0]), int(val[1]), int(val[2]), int(val[3]))
                    except Exception:
                        return default
                return default

            def _load_img(rel_path: str, size: tuple[int, int]) -> pygame.Surface | None:
                s = (rel_path or "").strip()
                if not s:
                    return None
                try:
                    p = self._resolve_path(s)
                    if not p.exists():
                        return None
                except Exception:
                    return None

                tw, th = max(1, int(size[0])), max(1, int(size[1]))
                cache = getattr(self, "_loading_overlay_img_cache", None)
                if cache is None:
                    cache = {}
                    self._loading_overlay_img_cache = cache
                key = (str(p), tw, th)
                if key in cache:
                    return cache[key]
                try:
                    img = pygame.image.load(str(p)).convert_alpha()
                    if img.get_width() != tw or img.get_height() != th:
                        try:
                            img = pygame.transform.smoothscale(img, (tw, th))
                        except Exception:
                            img = pygame.transform.scale(img, (tw, th))
                    cache[key] = img
                    return img
                except Exception:
                    return None

            def _font_from_style(style: object, default_size: int, *, bold_default: bool) -> object:
                st = style if isinstance(style, dict) else {}
                try:
                    size = int(st.get("size", default_size) or default_size)
                except Exception:
                    size = int(default_size)
                size = max(8, min(96, int(size)))
                try:
                    bold = bool(st.get("bold", bold_default))
                except Exception:
                    bold = bool(bold_default)
                family = str(st.get("family", "Microsoft YaHei") or "Microsoft YaHei")
                try:
                    return self._load_font(size, bold=bold, family=family)
                except Exception:
                    return pygame.font.Font(None, size)

            def _draw_text(text: str, *, rect: tuple[int, int, int, int], style: object, default_color: tuple[int, int, int]) -> None:
                st = style if isinstance(style, dict) else {}
                if st.get("visible", True) is False:
                    return
                font = _font_from_style(st, int(st.get("size", 24) or 24), bold_default=bool(st.get("bold", False)))
                color = _color(st.get("color"), default_color)
                align = str(st.get("align", "center") or "center").lower()

                x, y, rw, rh = rect
                max_w = max(1, int(rw))
                try:
                    lines = self._wrap_text_lines(str(text or ""), font, max_w)
                except Exception:
                    lines = [str(text or "")] if str(text or "") else []
                if not lines:
                    return

                line_h = int(getattr(font, "get_linesize", lambda: 0)() or 0)
                if line_h <= 0:
                    line_h = 18
                total_h = len(lines) * line_h
                cy = y + (rh - total_h) // 2
                for i, line in enumerate(lines):
                    surf_line = font.render(line, True, color)
                    if align == "left":
                        tx = x
                    elif align == "right":
                        tx = x + rw - surf_line.get_width()
                    else:
                        tx = x + (rw - surf_line.get_width()) // 2
                    surf.blit(surf_line, (int(tx), int(cy + i * line_h)))

            # background
            bg_color = _color(cfg.get("background_color"), (16, 18, 26))
            try:
                bg_alpha = int(cfg.get("background_alpha", 255) or 255)
            except Exception:
                bg_alpha = 255
            bg_alpha = max(0, min(255, int(bg_alpha)))

            bg_img = _load_img(str(cfg.get("background_image") or ""), (w, h))
            if bg_img is not None:
                if bg_alpha < 255:
                    try:
                        img2 = bg_img.copy()
                        img2.set_alpha(bg_alpha)
                        surf.blit(img2, (0, 0))
                    except Exception:
                        surf.blit(bg_img, (0, 0))
                else:
                    surf.blit(bg_img, (0, 0))
            else:
                surf.fill((bg_color[0], bg_color[1], bg_color[2], bg_alpha))

            # progress
            try:
                p = 0.55 if progress is None else float(progress)
            except Exception:
                p = 0.55
            p = max(0.0, min(1.0, p))
            percent = int(round(p * 100.0))

            # logo
            logo_rect = _rect(cfg.get("logo_rect"), (w // 2 - 60, h // 2 - 180, 120, 120))
            if bool(cfg.get("show_logo", True)):
                logo_img = _load_img(str(cfg.get("logo_image") or ""), (logo_rect[2], logo_rect[3]))
                if logo_img is not None:
                    surf.blit(logo_img, (logo_rect[0], logo_rect[1]))

            # title/message/subtitle
            title_text = str(cfg.get("title_text", "VNEngine") or "VNEngine")
            title_rect = _rect(cfg.get("title_rect"), (0, h // 2 - 90, w, 60))
            if bool(cfg.get("show_title", True)):
                _draw_text(title_text, rect=title_rect, style=cfg.get("title_style"), default_color=(220, 230, 255))

            class _SafeDict(dict):
                def __missing__(self, key):
                    return ""

            fmt = _SafeDict(
                message=str(message or ""),
                subtitle=str(subtitle or ""),
                percent=str(percent),
                pct=str(percent),
            )

            msg_tpl = str(cfg.get("message_template", "{message}") or "{message}")
            try:
                msg_text = msg_tpl.format_map(fmt)
            except Exception:
                msg_text = str(message or "")
            msg_rect = _rect(cfg.get("message_rect"), (0, h // 2 - 30, w, 40))
            if bool(cfg.get("show_message", True)):
                _draw_text(msg_text, rect=msg_rect, style=cfg.get("message_style"), default_color=(210, 210, 210))

            sub_text = ""
            if subtitle:
                sub_tpl = str(cfg.get("subtitle_template", "{subtitle}") or "{subtitle}")
                try:
                    sub_text = sub_tpl.format_map(fmt)
                except Exception:
                    sub_text = str(subtitle)
            sub_rect = _rect(cfg.get("subtitle_rect"), (0, h // 2 + 4, w, 40))
            if bool(cfg.get("show_subtitle", True)):
                _draw_text(sub_text, rect=sub_rect, style=cfg.get("subtitle_style"), default_color=(170, 170, 170))

            # bar
            bar_w = min(420, w - 120)
            bar_rect = _rect(cfg.get("bar_rect"), (w // 2 - bar_w // 2, h // 2 + 44, bar_w, 10))
            bar_bg = _color(cfg.get("bar_bg_color"), (60, 60, 70))
            bar_fg = _color(cfg.get("bar_fg_color"), (110, 160, 255))
            try:
                radius = int(cfg.get("bar_radius", 6) or 6)
            except Exception:
                radius = 6
            radius = max(0, min(30, int(radius)))
            if bool(cfg.get("show_bar", True)):
                pygame.draw.rect(surf, bar_bg, pygame.Rect(*bar_rect), border_radius=radius)
                fill_w = int(max(0, min(bar_rect[2], int(round(bar_rect[2] * p)))))
                if fill_w > 0:
                    pygame.draw.rect(surf, bar_fg, pygame.Rect(bar_rect[0], bar_rect[1], fill_w, bar_rect[3]), border_radius=radius)

            # percent
            if bool(cfg.get("show_percent", True)):
                pct_tpl = str(cfg.get("percent_template", "{percent}%") or "{percent}%")
                try:
                    pct_text = pct_tpl.format_map(fmt)
                except Exception:
                    pct_text = f"{percent}%"
                pct_rect = _rect(cfg.get("percent_rect"), (0, bar_rect[1] + bar_rect[3] + 8, w, 28))
                _draw_text(pct_text, rect=pct_rect, style=cfg.get("percent_style"), default_color=(170, 180, 200))

            # Clear display first to avoid alpha blending trails/ghosting when using SRCALPHA.
            try:
                screen.fill(bg_color)
            except Exception:
                pass
            screen.blit(surf, (0, 0))
            pygame.display.flip()
            pygame.event.pump()
        except Exception:
            pass

    def _project_changed_since_last_dialogue_load(self) -> bool:
        p = getattr(self, "project_path", None)
        if not p or not isinstance(p, Path) or not p.exists():
            return True
        try:
            cur = int(p.stat().st_mtime_ns)
        except Exception:
            return True
        last = getattr(self, "_project_loaded_mtime_ns", None)
        if last is None:
            return True
        try:
            return int(last) != cur
        except Exception:
            return True

    def _select_graph_start_node_id(self):
        if not getattr(self, "nodes_map", None):
            self.current_node_id = None
            return
        try:
            indegree = {nid: 0 for nid in self.nodes_map}
            for s, targets in (self.adjacency or {}).items():
                if s not in self.nodes_map:
                    continue
                for t in (targets or []):
                    if t in indegree:
                        indegree[t] = indegree.get(t, 0) + 1
            start_candidates = [nid for nid, deg in indegree.items() if deg == 0]
            if start_candidates:
                chosen = sorted(start_candidates, key=lambda x: str(x))[0]
            else:
                chosen = sorted(self.nodes_map.keys(), key=lambda x: str(x))[0]
        except Exception:
            try:
                chosen = sorted(self.nodes_map.keys(), key=lambda x: str(x))[0]
            except Exception:
                chosen = None

        # preview override
        requested = getattr(self, "_preview_start_node_id", None)
        if requested is not None and getattr(self, "nodes_map", None):
            if requested in self.nodes_map:
                chosen = requested
            else:
                try:
                    req_int = int(requested)
                    if req_int in self.nodes_map:
                        chosen = req_int
                except Exception:
                    pass
                if chosen is None:
                    req_str = str(requested)
                    if req_str in self.nodes_map:
                        chosen = req_str
        self.current_node_id = chosen

    def _loading_begin(self, message: str, subtitle: str | None = None) -> None:
        self._loading_active = True
        self._loading_stack = [(0.0, 1.0)]
        self._loading_message = str(message or "")
        self._loading_subtitle = subtitle
        self._render_blocking_loading_screen_with_progress(self._loading_message, subtitle=self._loading_subtitle, progress=0.0)

    def _loading_push(self, start: float, end: float) -> None:
        if not getattr(self, "_loading_active", False) or not getattr(self, "_loading_stack", None):
            return
        base, span = self._loading_stack[-1]
        try:
            s = float(start)
            e = float(end)
        except Exception:
            s, e = 0.0, 1.0
        s = max(0.0, min(1.0, s))
        e = max(0.0, min(1.0, e))
        if e < s:
            s, e = e, s
        self._loading_stack.append((base + span * s, span * (e - s)))

    def _loading_pop(self) -> None:
        if not getattr(self, "_loading_active", False):
            return
        if isinstance(self._loading_stack, list) and len(self._loading_stack) > 1:
            self._loading_stack.pop()

    def _loading_progress(self, progress: float, message: str | None = None, subtitle: str | None = None) -> None:
        if not getattr(self, "_loading_active", False) or not getattr(self, "_loading_stack", None):
            return
        base, span = self._loading_stack[-1]
        try:
            p = float(progress)
        except Exception:
            p = 0.0
        p = max(0.0, min(1.0, p))
        overall = base + span * p
        if message is not None:
            self._loading_message = str(message or "")
        if subtitle is not None:
            self._loading_subtitle = subtitle
        self._render_blocking_loading_screen_with_progress(self._loading_message, subtitle=self._loading_subtitle, progress=overall)

    def _loading_end(self) -> None:
        if not getattr(self, "_loading_active", False):
            return
        try:
            self._render_blocking_loading_screen_with_progress(self._loading_message or "", subtitle=self._loading_subtitle, progress=1.0)
        except Exception:
            pass
        self._loading_active = False
        self._loading_stack = []
        self._loading_message = ""
        self._loading_subtitle = None

    def _protected_var_names_from_defs(self) -> set[str]:
        out: set[str] = set()
        for item in (self._global_var_defs or []):
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not name:
                continue
            if bool(item.get("protected", False)):
                out.add(str(name))
        return out

    def _refresh_protected_vars(self) -> None:
        try:
            self._protected_vars = self._protected_var_names_from_defs()
        except Exception:
            self._protected_vars = set()

    def _load_persistent_vars(self) -> None:
        try:
            p = getattr(self, "_persistent_vars_path", None)
            if not p or not isinstance(p, Path) or not p.exists():
                self._persistent_vars = {}
                self._persistent_vars_dirty = False
                return
            with open(p, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            if isinstance(data, dict) and isinstance(data.get("variables"), dict):
                raw = data.get("variables") or {}
            elif isinstance(data, dict):
                raw = data
            else:
                raw = {}
            out: dict[str, float] = {}
            for k, v in (raw or {}).items():
                if not k:
                    continue
                try:
                    out[str(k)] = float(v)
                except Exception:
                    continue
            self._persistent_vars = out
            self._persistent_vars_dirty = False
        except Exception:
            self._persistent_vars = {}
            self._persistent_vars_dirty = False

    def _save_persistent_vars(self) -> None:
        if not getattr(self, "_persistent_vars_dirty", False):
            return
        try:
            p: Path = getattr(self, "_persistent_vars_path")
            p.parent.mkdir(parents=True, exist_ok=True)
            data = {"version": 1, "variables": dict(self._persistent_vars or {})}
            with open(p, "w", encoding="utf-8") as f:
                yaml.safe_dump(data, f, allow_unicode=True)
            self._persistent_vars_dirty = False
        except Exception:
            pass

    def _update_persistent_from_runtime(self) -> None:
        protected = getattr(self, "_protected_vars", set()) or set()
        if not protected:
            return
        if not isinstance(self.variables, dict):
            return
        changed = False
        for name in protected:
            if name not in self.variables:
                continue
            try:
                v = float(self.variables.get(name))
            except Exception:
                continue
            if self._persistent_vars.get(name) != v:
                self._persistent_vars[name] = v
                changed = True
        if changed:
            self._persistent_vars_dirty = True

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
                try:
                    self._project_loaded_mtime_ns = int(self.project_path.stat().st_mtime_ns)
                except Exception:
                    self._project_loaded_mtime_ns = None
                self._loading_progress(0.05, "读取工程文件...")
                with open(self.project_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                self.project_data = data if isinstance(data, dict) else None
                if isinstance(data, dict):
                    self._loading_progress(0.25, "解析工程配置...")
                    game_cfg = (data.get("game_config", {}) or {})
                    self._game_cfg_cache = game_cfg if isinstance(game_cfg, dict) else None
                    try:
                        self._loading_overlay_cfg = self._normalize_loading_overlay_cfg((game_cfg or {}).get("loading_overlay"))
                    except Exception:
                        self._loading_overlay_cfg = self._normalize_loading_overlay_cfg({})
                    self._global_var_defs = data.get("global_variables", []) or []
                    self._refresh_protected_vars()
                    self.branch_strategy = game_cfg.get("branch_strategy") or "first"
                    self._allow_unsafe_function_scripts = bool(game_cfg.get("allow_unsafe_function_scripts", False))

                    # 功能节点脚本：安全模式文件系统根目录（可选覆盖）
                    try:
                        fs_root = game_cfg.get("function_script_fs_root")
                        if isinstance(fs_root, str) and fs_root.strip():
                            p = Path(fs_root)
                            if not p.is_absolute():
                                p = (self._project_dir / p).resolve()
                            self._function_fs_root = p
                        else:
                            self._function_fs_root = self._project_dir
                    except Exception:
                        self._function_fs_root = self._project_dir
                    self._apply_text_style_config(game_cfg if isinstance(game_cfg, dict) else {})
                    # 覆盖运行时存档/帮助配置
                    try:
                        self._save_slots = int(game_cfg.get("save_slots", self._save_slots))
                    except Exception:
                        pass
                    self._save_slots = max(1, min(200, int(self._save_slots)))
                    self._enable_autosave_on_menu = bool(game_cfg.get("enable_autosave_on_menu", self._enable_autosave_on_menu))
                    self._help_hotkey_name = str(game_cfg.get("help_hotkey", self._help_hotkey_name) or self._help_hotkey_name)
                    self._help_right_click = bool(game_cfg.get("help_right_click", self._help_right_click))
                    self._apply_menu_config(game_cfg)
                    self._apply_function_menus_from_game_config(game_cfg)
                    self._loading_progress(0.55, "构建流程图...")
                    self._load_graph_from_flow(data)
                    if self.graph_mode and self.current_node_id is not None:
                        return []
                    self._loading_progress(0.75, "生成对白数据...")
                    dialogues = self._build_dialogues_from_flow(data)
                    if dialogues:
                        self._loading_progress(0.90, "预加载首批资源...")
                        self._preload_initial_assets(dialogues)
                        self._loading_progress(0.98, "完成")
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
            # Cache raw portrait to avoid quality loss from double-scaling.
            img = pygame.image.load(str(abs_path)).convert_alpha()
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
        cfg = cfg or {}

        def _menu_var_context() -> dict:
            # Prefer current runtime variables when returning to menu.
            if isinstance(self.variables, dict) and self.variables:
                return dict(self.variables)
            # Otherwise, use initial values from global variable definitions.
            out: dict[str, float] = {}
            for item in (self._global_var_defs or []):
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                if not name:
                    continue
                try:
                    out[str(name)] = float(item.get("initial", 0.0))
                except Exception:
                    out[str(name)] = 0.0
            return out

        def _select_main_menu_cfg(game_cfg: dict) -> tuple[int, dict]:
            raw = game_cfg.get("main_menus")
            if not isinstance(raw, list) or not raw:
                return 0, {}
            menus: list[dict] = []
            for it in raw[:3]:
                menus.append(it if isinstance(it, dict) else {})
            while len(menus) < 3:
                menus.append({})

            ctx = _menu_var_context()
            default_idx: int | None = None
            for idx, m in enumerate(menus):
                cond = str(m.get("trigger_condition") or "").strip()
                if not cond:
                    if default_idx is None:
                        default_idx = idx
                    continue
                if eval_var_expr(cond, ctx):
                    return idx, m

            if default_idx is not None:
                return int(default_idx), menus[int(default_idx)]
            return 0, menus[0]

        # multi-menu: choose by trigger condition (1->2->3 priority)
        chosen_idx, chosen = _select_main_menu_cfg(cfg)
        self._active_menu_index = int(chosen_idx)
        if isinstance(chosen, dict) and chosen:
            merged = dict(cfg)
            merged.update({k: v for k, v in chosen.items() if k not in {"trigger_condition"}})
            cfg = merged

        # menu-start behavior
        self._reset_globals_on_start = bool(cfg.get("reset_globals_on_start", True))

        # allow menu config to override save/help settings
        try:
            self._save_slots = int(cfg.get("save_slots", self._save_slots))
        except Exception:
            pass
        self._save_slots = max(1, min(200, int(self._save_slots)))
        self._enable_autosave_on_menu = bool(cfg.get("enable_autosave_on_menu", self._enable_autosave_on_menu))
        self._help_hotkey_name = str(cfg.get("help_hotkey", self._help_hotkey_name) or self._help_hotkey_name)
        self._help_right_click = bool(cfg.get("help_right_click", self._help_right_click))

        def _normalize_buttons(raw) -> list[dict]:
            defaults = [
                {"label": "开始游戏", "action": "start"},
                {"label": "继续", "action": "continue"},
                {"label": "读取存档", "action": "load"},
                {"label": "设置", "action": "settings"},
                {"label": "退出", "action": "exit"},
            ]
            by_action: dict[str, dict] = {}
            if isinstance(raw, list):
                for it in raw:
                    if not isinstance(it, dict):
                        continue
                    action = str(it.get("action") or "").strip()
                    if action not in {"start", "continue", "load", "settings", "exit"}:
                        continue
                    by_action[action] = dict(it)
            out: list[dict] = []
            for base in defaults:
                action = base["action"]
                it = by_action.get(action, {})
                label = str(it.get("label") or base["label"])
                image = str(it.get("image") or it.get("image_path") or "")
                style_raw = it.get("style") or it.get("mode")
                if style_raw is None or str(style_raw).strip() == "":
                    style = "image" if image else "text"
                else:
                    style = str(style_raw).strip().lower()
                if style not in {"text", "image"}:
                    style = "image" if image else "text"

                image_scale = it.get("image_scale", None)
                if image_scale is not None:
                    try:
                        image_scale = float(image_scale)
                    except Exception:
                        image_scale = None
                if isinstance(image_scale, (int, float)):
                    image_scale = max(0.1, min(5.0, float(image_scale)))
                out.append({
                    "action": action,
                    "label": label,
                    "style": style,
                    "image": image,
                    "image_scale": image_scale,
                })
            return out

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
        self._menu_option_hover_color = self._color_from_cfg(cfg.get("menu_option_hover_color"), self._menu_option_color)
        try:
            self._menu_title_scale = float(cfg.get("menu_title_scale", 1.0) or 1.0)
        except Exception:
            self._menu_title_scale = 1.0
        self._menu_title_scale = max(0.1, min(5.0, float(self._menu_title_scale)))
        try:
            self._menu_option_scale = float(cfg.get("menu_option_scale", 1.0) or 1.0)
        except Exception:
            self._menu_option_scale = 1.0
        self._menu_option_scale = max(0.5, min(5.0, float(self._menu_option_scale)))

        try:
            self._menu_option_spacing = int(cfg.get("menu_option_spacing", 10) or 10)
        except Exception:
            self._menu_option_spacing = 10
        self._menu_option_spacing = max(0, min(200, int(self._menu_option_spacing)))

        try:
            self._menu_option_selected_zoom = float(cfg.get("menu_option_selected_zoom", 1.08) or 1.08)
        except Exception:
            self._menu_option_selected_zoom = 1.08
        self._menu_option_selected_zoom = max(1.0, min(1.5, float(self._menu_option_selected_zoom)))

        self._menu_option_indicator = bool(cfg.get("menu_option_indicator", False))

        self._menu_option_indicator_image_path = str(cfg.get("menu_option_indicator_image") or "")
        try:
            self._menu_option_indicator_image_scale = float(cfg.get("menu_option_indicator_image_scale", 1.0) or 1.0)
        except Exception:
            self._menu_option_indicator_image_scale = 1.0
        self._menu_option_indicator_image_scale = max(0.1, min(5.0, float(self._menu_option_indicator_image_scale)))
        self._menu_title_image_path = cfg.get("menu_title_image") or ""
        self._menu_title_image_pos = self._pair_from_cfg(cfg.get("menu_title_image_pos"), (400, 80))
        try:
            self._menu_title_image_scale = float(cfg.get("menu_title_image_scale", 1.0) or 1.0)
        except Exception:
            self._menu_title_image_scale = 1.0
        self._menu_title_image_scale = max(0.1, min(5.0, float(self._menu_title_image_scale)))

        # menu buttons (optional override)
        self._menu_items = _normalize_buttons(cfg.get("menu_buttons"))
        self._menu_selected = 0

    def _ui_hidden_for_current_node(self) -> bool:
        if self._screenshot_hide_ui:
            return True
        try:
            entry = self._current_entry() or {}
        except Exception:
            entry = {}
        return bool(entry.get("hide_textbox", False))

    def _apply_hud_buttons_from_ui_layout(self, layout: dict | None):
        """Read in-game HUD button group config from UI layout JSON."""

        def _normalize_buttons(raw) -> list[dict]:
            defaults = [
                {"label": "存档", "action": "save"},
                {"label": "读档", "action": "load"},
                {"label": "设置", "action": "settings"},
                {"label": "历史记录", "action": "history"},
                {"label": "返回主菜单", "action": "menu"},
                {"label": "全屏", "action": "fullscreen"},
            ]
            by_action: dict[str, dict] = {}
            if isinstance(raw, list):
                for it in raw:
                    if not isinstance(it, dict):
                        continue
                    action = str(it.get("action") or "").strip()
                    if action not in {"save", "load", "settings", "history", "menu", "fullscreen"}:
                        continue
                    by_action[action] = dict(it)

            out: list[dict] = []
            for base in defaults:
                action = base["action"]
                it = by_action.get(action, {})
                label = str(it.get("label") or base["label"])
                image = str(it.get("image") or it.get("image_path") or "")
                style_raw = it.get("style") or it.get("mode")
                if style_raw is None or str(style_raw).strip() == "":
                    style = "image" if image else "text"
                else:
                    style = str(style_raw).strip().lower()
                if style not in {"text", "image"}:
                    style = "image" if image else "text"

                image_scale = it.get("image_scale", None)
                if image_scale is not None:
                    try:
                        image_scale = float(image_scale)
                    except Exception:
                        image_scale = None
                if isinstance(image_scale, (int, float)):
                    image_scale = max(0.1, min(5.0, float(image_scale)))
                out.append({
                    "action": action,
                    "label": label,
                    "style": style,
                    "image": image,
                    "image_scale": image_scale,
                })
            return out

        layout = layout or {}
        self._hud_buttons_enabled = bool(layout.get("hud_buttons_enabled", False))
        self._hud_button_pos = self._pair_from_cfg(layout.get("hud_button_pos"), (20, 20))
        try:
            self._hud_button_spacing = int(layout.get("hud_button_spacing", 10) or 10)
        except Exception:
            self._hud_button_spacing = 10
        self._hud_button_spacing = max(0, min(200, int(self._hud_button_spacing)))

        try:
            self._hud_button_scale = float(layout.get("hud_button_scale", 1.0) or 1.0)
        except Exception:
            self._hud_button_scale = 1.0
        self._hud_button_scale = max(0.5, min(5.0, float(self._hud_button_scale)))

        try:
            self._hud_button_selected_zoom = float(layout.get("hud_button_selected_zoom", 1.08) or 1.08)
        except Exception:
            self._hud_button_selected_zoom = 1.08
        self._hud_button_selected_zoom = max(1.0, min(1.5, float(self._hud_button_selected_zoom)))

        orient = str(layout.get("hud_button_orientation") or "vertical").strip().lower()
        self._hud_button_orientation = "horizontal" if orient in {"h", "horizontal", "row", "x"} else "vertical"

        self._hud_button_color = self._color_from_cfg(layout.get("hud_button_color"), (255, 255, 255))
        self._hud_button_hover_color = self._color_from_cfg(layout.get("hud_button_hover_color"), self._hud_button_color)
        self._hud_buttons = _normalize_buttons(layout.get("hud_buttons"))
        # hover-only selection (mouse)
        self._hud_selected = -1
        # reset cached hitboxes to align with buttons
        self._hud_button_hitboxes = [None] * len(self._hud_buttons)

        # load images for image-style buttons
        self._hud_button_image_surfaces = {}
        for it in self._hud_buttons:
            if not isinstance(it, dict):
                continue
            if str(it.get("style") or "text") != "image":
                continue
            action = str(it.get("action") or "")
            img_rel = str(it.get("image") or "")
            if not action or not img_rel:
                continue
            p = self._resolve_path(img_rel)
            if not p.exists():
                continue
            try:
                img = pygame.image.load(str(p)).convert_alpha()
                self._hud_button_image_surfaces[action] = img
            except Exception:
                continue

    def _apply_choice_buttons_from_ui_layout(self, layout: dict | None) -> None:
        """Read choice button group config from UI layout JSON.

        This is only used when a *choice node* is active and opens the choice overlay.
        """

        layout = layout or {}
        self._choice_buttons_enabled = bool(layout.get("choice_buttons_enabled", False))
        self._choice_button_pos = self._pair_from_cfg(layout.get("choice_button_pos"), (120, 140))

        try:
            self._choice_button_spacing = int(layout.get("choice_button_spacing", 12) or 12)
        except Exception:
            self._choice_button_spacing = 12
        self._choice_button_spacing = max(0, min(300, int(self._choice_button_spacing)))

        try:
            self._choice_button_scale = float(layout.get("choice_button_scale", 1.0) or 1.0)
        except Exception:
            self._choice_button_scale = 1.0
        self._choice_button_scale = max(0.5, min(5.0, float(self._choice_button_scale)))

        try:
            self._choice_button_hover_zoom = float(layout.get("choice_button_hover_zoom", 1.08) or 1.08)
        except Exception:
            self._choice_button_hover_zoom = 1.08
        self._choice_button_hover_zoom = max(1.0, min(1.8, float(self._choice_button_hover_zoom)))

        orient = str(layout.get("choice_button_orientation") or "vertical").strip().lower()
        self._choice_button_orientation = "horizontal" if orient in {"h", "horizontal", "row", "x"} else "vertical"

        try:
            self._choice_button_font_size = int(layout.get("choice_button_font_size", 20) or 20)
        except Exception:
            self._choice_button_font_size = 20
        self._choice_button_font_size = max(8, min(72, int(self._choice_button_font_size)))

        self._choice_button_text_color = self._color_from_cfg(layout.get("choice_button_text_color"), (230, 230, 230))
        self._choice_button_text_hover_color = self._color_from_cfg(
            layout.get("choice_button_text_hover_color"),
            self._choice_button_text_color,
        )

        try:
            self._choice_overlay_alpha = int(layout.get("choice_overlay_alpha", 180))
        except Exception:
            self._choice_overlay_alpha = 180
        self._choice_overlay_alpha = max(0, min(255, int(self._choice_overlay_alpha)))

        self._choice_button_bg_image = str(layout.get("choice_button_bg_image") or "").strip()
        try:
            self._choice_button_bg_alpha = int(layout.get("choice_button_bg_alpha", 255))
        except Exception:
            self._choice_button_bg_alpha = 255
        self._choice_button_bg_alpha = max(0, min(255, int(self._choice_button_bg_alpha)))

        pad = layout.get("choice_button_padding")
        if isinstance(pad, (list, tuple)) and len(pad) >= 2:
            try:
                self._choice_button_padding = (max(0, int(pad[0])), max(0, int(pad[1])))
            except Exception:
                self._choice_button_padding = (18, 10)
        else:
            self._choice_button_padding = (18, 10)

        ms = layout.get("choice_button_min_size")
        if isinstance(ms, (list, tuple)) and len(ms) >= 2:
            try:
                self._choice_button_min_size = (max(0, int(ms[0])), max(0, int(ms[1])))
            except Exception:
                self._choice_button_min_size = (0, 0)
        else:
            self._choice_button_min_size = (0, 0)

        # reset hover selection + cached hitboxes when layout changes
        if not self._choice_overlay:
            self._choice_selected = -1
        self._choice_button_hitboxes = [None] * len(self._choice_options)

    def _apply_function_menus_from_game_config(self, cfg: dict | None) -> None:
        cfg = cfg or {}
        fm = cfg.get("function_menus") if isinstance(cfg, dict) else None
        if not isinstance(fm, dict):
            self._function_menus_from_project = False
            # do not force-disable here; allow UI-layout fallback if present
            return
        self._function_menus_from_project = True
        self._function_menus_enabled = bool(fm.get("enabled", False))
        self._function_menus_cfg = fm

    def _apply_function_menus_from_ui_layout(self, layout: dict | None) -> None:
        """Read configurable function-menu overlays (save/load/settings/history/help) from UI layout JSON."""
        layout = layout or {}
        fm = layout.get("function_menus") if isinstance(layout, dict) else None
        if not isinstance(fm, dict):
            self._function_menus_enabled = False
            self._function_menus_cfg = {}
            return
        self._function_menus_enabled = bool(fm.get("enabled", False))
        self._function_menus_cfg = fm

    def _overlay_type(self) -> str | None:
        if self._save_overlay:
            return "save"
        if self._load_overlay:
            return "load"
        if self._settings_overlay:
            return "settings"
        if self._history_overlay:
            return "history"
        if self._help_overlay:
            return "help"
        return None

    def _get_function_menu_cfg(self, name: str) -> dict:
        fm = self._function_menus_cfg if isinstance(self._function_menus_cfg, dict) else {}
        common = fm.get("common") if isinstance(fm.get("common"), dict) else {}
        specific = fm.get(name) if isinstance(fm.get(name), dict) else {}

        merged = dict(common)
        merged.update(specific)

        # defaults
        merged.setdefault("overlay_alpha", 160)
        merged.setdefault("background_image", "")
        merged.setdefault("background_alpha", 255)
        merged.setdefault("font_size", 18)
        merged.setdefault("title_font_size", 22)
        merged.setdefault("title_color", [255, 255, 255])
        merged.setdefault("text_color", [230, 230, 230])
        merged.setdefault("hint_color", [200, 200, 200])
        merged.setdefault("hover_color", [255, 255, 255])
        merged.setdefault("title_pos", [40, 40])
        merged.setdefault("content_pos", [40, 90])
        merged.setdefault(
            "close_button",
            {"pos": [self.render_size[0] - 60, 40], "size": [32, 32], "text": "×"},
        )

        if name in {"save", "load"}:
            merged.setdefault("slot_list_pos", [40, 120])
            merged.setdefault("slot_list_width", self.render_size[0] - 80)
            merged.setdefault("slot_row_height", 34)
            merged.setdefault("slot_row_spacing", 8)
            merged.setdefault("slot_bg_alpha", 90)
            merged.setdefault("slot_hover_alpha", 140)
            merged.setdefault("page_prev_pos", [40, self.render_size[1] - 60])
            merged.setdefault("page_next_pos", [140, self.render_size[1] - 60])
            merged.setdefault("page_text_pos", [240, self.render_size[1] - 60])
            merged.setdefault("page_size", DEFAULT_PAGE_SIZE)

        if name == "settings":
            merged.setdefault("slider_pos", [80, 140])
            merged.setdefault("slider_width", self.render_size[0] - 160)
            merged.setdefault("slider_height", 10)
            merged.setdefault("slider_gap", 70)
            merged.setdefault("button_row_pos", [80, self.render_size[1] - 90])
            merged.setdefault("button_size", [120, 36])

        if name in {"history", "help"}:
            merged.setdefault("text_area", [40, 100, self.render_size[0] - 80, self.render_size[1] - 160])

        return merged

    def _active_slot_page_size(self, overlay_type: str | None = None) -> int:
        """Slots-per-page for save/load overlays.

        Value comes from function menu config when enabled; clamped to 1..10.
        """

        ot = overlay_type or self._overlay_type()
        if ot not in {"save", "load"}:
            return int(DEFAULT_PAGE_SIZE)
        if not getattr(self, "_function_menus_enabled", False):
            return int(DEFAULT_PAGE_SIZE)
        try:
            cfg = self._get_function_menu_cfg(str(ot))
            size = int(cfg.get("page_size", DEFAULT_PAGE_SIZE))
        except Exception:
            size = int(DEFAULT_PAGE_SIZE)
        return max(1, min(10, int(size)))

    def _load_overlay_background(self, rel_path: str) -> pygame.Surface | None:
        s = (rel_path or "").strip()
        if not s:
            return None
        p = self._resolve_path(s)
        if not p.exists():
            return None
        w, h = self.render_size
        key = (p, int(w), int(h))
        if key in self._ui_overlay_bg_cache:
            return self._ui_overlay_bg_cache[key]
        try:
            img = pygame.image.load(str(p)).convert_alpha()
            if img.get_width() != w or img.get_height() != h:
                try:
                    img = pygame.transform.smoothscale(img, (w, h))
                except Exception:
                    img = pygame.transform.scale(img, (w, h))
            self._ui_overlay_bg_cache[key] = img
            return img
        except Exception:
            return None

    def _overlay_close(self) -> None:
        if self._save_overlay:
            self._save_overlay = False
        if self._load_overlay:
            self._load_overlay = False
        if self._settings_overlay:
            self._settings_overlay = False
        if self._history_overlay:
            self._history_overlay = False
        if self._help_overlay:
            self._help_overlay = False
        self._overlay_dragging_slider = None
        self._overlay_hover = None
        self._overlay_hitboxes = {}
        self._overlay_slot_hitboxes = []

    def _overlay_update_slider_value(self, key: str, mx: int) -> None:
        r = (self._overlay_hitboxes or {}).get(f"slider:{key}")
        if r is None:
            return
        t = 0.0
        if r.w > 0:
            t = (mx - r.x) / float(r.w)
        t = max(0.0, min(1.0, t))
        if key == "typing_speed":
            self._settings["typing_speed"] = 4.0 + t * (120.0 - 4.0)
        else:
            self._settings[key] = t
        self._apply_settings()

    def _overlay_handle_mouse_motion(self, render_pos) -> bool:
        if not self._function_menus_enabled:
            return False
        ot = self._overlay_type()
        if not ot:
            return False
        if render_pos is None:
            self._overlay_hover = None
            return False

        mx, my = render_pos
        hand = False
        hovered = None

        if self._overlay_dragging_slider:
            # drag updates value continuously
            hovered = self._overlay_dragging_slider
            hand = True
            try:
                self._overlay_update_slider_value(str(self._overlay_dragging_slider), int(mx))
            except Exception:
                pass
        else:
            for k, rect in (self._overlay_hitboxes or {}).items():
                if rect.collidepoint(mx, my):
                    hovered = k
                    hand = True
                    break
            if not hand and self._overlay_slot_hitboxes:
                for slot_id, rect in self._overlay_slot_hitboxes:
                    if rect.collidepoint(mx, my):
                        hovered = f"slot:{slot_id}"
                        hand = True
                        break

        self._overlay_hover = hovered
        return hand

    def _overlay_handle_mouse_down(self, render_pos) -> bool:
        if not self._function_menus_enabled:
            return False
        ot = self._overlay_type()
        if not ot:
            return False
        if render_pos is None:
            return True

        def _slot_exists(slot_id: int) -> bool:
            try:
                return bool(slot_file_path(self.save_dir, int(slot_id)).exists())
            except Exception:
                return False

        mx, my = render_pos

        r_close = (self._overlay_hitboxes or {}).get("close")
        if r_close is not None and r_close.collidepoint(mx, my):
            if ot == "settings" and isinstance(self._overlay_settings_snapshot, dict):
                self._settings = dict(self._overlay_settings_snapshot)
                self._apply_settings()
            self._overlay_close()
            self._overlay_settings_snapshot = None
            return True

        if ot in {"save", "load"}:
            for slot_id, rect in self._overlay_slot_hitboxes:
                if rect.collidepoint(mx, my):
                    if ot == "save":
                        self.save_game(slot_id)
                        # 保持停留在存档界面，仅刷新显示（缩略图缓存按槽位失效）
                        try:
                            self._invalidate_slot_thumbnail_cache(int(slot_id))
                        except Exception:
                            pass
                    else:
                        # 空槽位点击：吞掉事件但不退出读档界面
                        if not _slot_exists(slot_id):
                            return True
                        self.load_game(slot_id)
                        self._load_overlay = False
                    return True

            r_prev = (self._overlay_hitboxes or {}).get("page_prev")
            r_next = (self._overlay_hitboxes or {}).get("page_next")
            if r_prev is not None and r_prev.collidepoint(mx, my):
                self._save_page = max(0, int(self._save_page) - 1)
                return True
            if r_next is not None and r_next.collidepoint(mx, my):
                self._save_page = int(self._save_page) + 1
                return True

        if ot == "settings":
            r_save = (self._overlay_hitboxes or {}).get("settings_save")
            r_cancel = (self._overlay_hitboxes or {}).get("settings_cancel")
            if r_save is not None and r_save.collidepoint(mx, my):
                self._apply_settings()
                self._save_settings()
                self._settings_overlay = False
                self._overlay_settings_snapshot = None
                return True
            if r_cancel is not None and r_cancel.collidepoint(mx, my):
                if isinstance(self._overlay_settings_snapshot, dict):
                    self._settings = dict(self._overlay_settings_snapshot)
                    self._apply_settings()
                self._settings_overlay = False
                self._overlay_settings_snapshot = None
                return True

            for key in ("typing_speed", "master_volume", "bgm_volume", "voice_volume"):
                r = (self._overlay_hitboxes or {}).get(f"slider:{key}")
                if r is not None and r.collidepoint(mx, my):
                    self._overlay_dragging_slider = key
                    self._overlay_update_slider_value(key, mx)
                    return True

        return True

    def _overlay_handle_mouse_up(self) -> None:
        self._overlay_dragging_slider = None

    def _overlay_handle_wheel(self, y_delta: int) -> None:
        if not self._function_menus_enabled:
            return
        ot = self._overlay_type()
        if ot not in {"history", "help"}:
            return
        step = int(self.font.get_linesize() * 3)
        self._overlay_scroll_offset = int(self._overlay_scroll_offset) - int(y_delta) * step
        self._overlay_scroll_offset = max(0, int(self._overlay_scroll_offset))

    def _hit_test_hud_button(self, render_pos):
        if not self._hud_button_hitboxes:
            return None
        x, y = render_pos
        for idx, rect in enumerate(self._hud_button_hitboxes):
            if rect is not None and rect.collidepoint(x, y):
                return idx
        return None

    def _hit_test_choice_button(self, render_pos):
        if not self._choice_button_hitboxes:
            return None
        x, y = render_pos
        for idx, rect in enumerate(self._choice_button_hitboxes):
            if rect is not None and rect.collidepoint(x, y):
                return idx
        return None

    def _activate_hud_button(self, idx: int):
        if not self._hud_buttons or idx < 0 or idx >= len(self._hud_buttons):
            return
        action = str((self._hud_buttons[idx] or {}).get("action") or "")
        if action == "save":
            self._overlay_return_mode = self.mode
            self._save_overlay = True
            self._load_overlay = False
            self._settings_overlay = False
            self._history_overlay = False
            self._help_overlay = False
            self._exit_confirm_overlay = False
            self._save_page = 0
            return
        if action == "load":
            self._overlay_return_mode = self.mode
            self._load_overlay = True
            self._save_overlay = False
            self._settings_overlay = False
            self._history_overlay = False
            self._help_overlay = False
            self._exit_confirm_overlay = False
            self._save_page = 0
            return
        if action == "settings":
            self._overlay_return_mode = self.mode
            self._settings_overlay = True
            self._save_overlay = False
            self._load_overlay = False
            self._history_overlay = False
            self._help_overlay = False
            self._exit_confirm_overlay = False
            return
        if action == "history":
            self._overlay_return_mode = self.mode
            self._history_overlay = True
            self._save_overlay = False
            self._load_overlay = False
            self._settings_overlay = False
            self._help_overlay = False
            self._exit_confirm_overlay = False
            return
        if action == "menu":
            # mouse-only trigger: return to menu immediately (same as confirm-yes path)
            if self._enable_autosave_on_menu and self.mode == "game":
                self.save_game(AUTO_SAVE_SLOT)
            self._enter_menu()
            return
        if action == "fullscreen":
            self.toggle_fullscreen()
            return

    def _render_hud_buttons(self):
        if self.mode != "game":
            return
        if not self._hud_buttons_enabled:
            return
        if not self._hud_buttons:
            return

        start_x, start_y = self._hud_button_pos
        spacing = int(self._hud_button_spacing)
        zoom = float(self._hud_button_selected_zoom)
        orientation = str(self._hud_button_orientation or "vertical")
        scale0 = float(self._hud_button_scale or 1.0)
        base_color = self._hud_button_color
        hover_color = getattr(self, "_hud_button_hover_color", base_color)
        font = self._load_font(max(8, int(18 * scale0)))

        # stable layout with unzoomed sizes
        layout: list[dict] = []
        cur_x = int(start_x)
        cur_y = int(start_y)
        for idx, item in enumerate(self._hud_buttons):
            if not isinstance(item, dict):
                continue
            style = str(item.get("style") or "text")
            action = str(item.get("action") or "")
            label = str(item.get("label") or "")
            raw = None
            base_w = 0
            base_h = 0
            img_scale = None
            if style == "image":
                raw = (getattr(self, "_hud_button_image_surfaces", {}) or {}).get(action)
                if raw is not None:
                    img_scale = item.get("image_scale", None)
                    if img_scale is None:
                        try:
                            img_scale = 20.0 / max(1.0, float(raw.get_height()))
                        except Exception:
                            img_scale = 1.0
                    else:
                        try:
                            img_scale = float(img_scale)
                        except Exception:
                            img_scale = 1.0
                    img_scale = max(0.1, min(5.0, float(img_scale)))
                    final_scale = float(scale0) * float(img_scale)
                    base_w = max(1, int(raw.get_width() * final_scale))
                    base_h = max(1, int(raw.get_height() * final_scale))
                else:
                    style = "text"  # fallback

            if style != "image":
                try:
                    base_w = max(1, int(font.size(label)[0]))
                except Exception:
                    base_w = 1
                base_h = int(font.get_linesize())

            layout.append({
                "idx": idx,
                "style": style,
                "action": action,
                "label": label,
                "x": int(cur_x),
                "y": int(cur_y),
                "w": int(base_w),
                "h": int(base_h),
                "raw": raw,
            })

            if orientation == "horizontal":
                cur_x += int(base_w) + spacing
            else:
                cur_y += int(base_h) + spacing

        if not self._hud_button_hitboxes or len(self._hud_button_hitboxes) != len(self._hud_buttons):
            self._hud_button_hitboxes = [None] * len(self._hud_buttons)

        for it in layout:
            idx = int(it["idx"])
            sel = idx == self._hud_selected
            style = str(it["style"])
            x = int(it["x"])
            y = int(it["y"])

            if style == "image" and it.get("raw") is not None:
                raw = it["raw"]
                base_w = int(it["w"])
                base_h = int(it["h"])
                z = float(zoom if sel else 1.0)
                w = max(1, int(base_w * z))
                h = max(1, int(base_h * z))
                try:
                    img = pygame.transform.smoothscale(raw, (w, h))
                except Exception:
                    img = pygame.transform.scale(raw, (w, h))
                dx = x - (w - base_w) // 2
                dy = y - (h - base_h) // 2
                self.render_surface.blit(img, (dx, dy))
                if 0 <= idx < len(self._hud_button_hitboxes):
                    self._hud_button_hitboxes[idx] = pygame.Rect(dx, dy, w, h)
                continue

            # text style
            color0 = hover_color if sel else base_color
            color = color0 if sel else (int(color0[0] * 0.75), int(color0[1] * 0.75), int(color0[2] * 0.75))
            surf = font.render(str(it.get("label") or ""), True, color)
            self.render_surface.blit(surf, (x, y))
            if 0 <= idx < len(self._hud_button_hitboxes):
                self._hud_button_hitboxes[idx] = pygame.Rect(x, y, surf.get_width(), surf.get_height())

    def _set_mouse_cursor(self, *, hand: bool) -> None:
        """Switch system cursor between arrow and hand.

        Safe on platforms that don't support system cursors.
        """
        # script lock overrides auto cursor behavior
        if isinstance(getattr(self, "_script_cursor_lock_style", None), str) and self._script_cursor_lock_style:
            self._set_system_cursor(self._script_cursor_lock_style)
            return

        desired = bool(hand)
        if desired == bool(getattr(self, "_mouse_cursor_is_hand", False)):
            return
        try:
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_HAND if desired else pygame.SYSTEM_CURSOR_ARROW)
            self._mouse_cursor_is_hand = desired
        except Exception:
            # ignore if system cursor is not supported
            self._mouse_cursor_is_hand = desired

    def _set_system_cursor(self, style: str) -> None:
        s = str(style or "").strip().lower()
        mapping = {
            "arrow": pygame.SYSTEM_CURSOR_ARROW,
            "hand": pygame.SYSTEM_CURSOR_HAND,
            "ibeam": pygame.SYSTEM_CURSOR_IBEAM,
            "wait": pygame.SYSTEM_CURSOR_WAIT,
            "crosshair": pygame.SYSTEM_CURSOR_CROSSHAIR,
        }
        cur = mapping.get(s, pygame.SYSTEM_CURSOR_ARROW)
        try:
            pygame.mouse.set_cursor(cur)
        except Exception:
            pass

    def _enter_menu(self):
        self.mode = "menu"
        self._save_overlay = False
        self._load_overlay = False
        self._settings_overlay = False
        self._choice_overlay = False
        self._history_overlay = False
        self._help_overlay = False
        self._exit_confirm_overlay = False
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
        if isinstance(self._game_cfg_cache, dict):
            self._apply_menu_config(self._game_cfg_cache)
        show_overlay = self._loading_overlay_enabled_for("enter_menu")
        if show_overlay:
            self._loading_begin("正在加载主菜单...", subtitle=None)
        self._load_menu_assets()
        if show_overlay:
            self._loading_end()
        if self._menu_bgm_path:
            self._ensure_bgm(self._menu_bgm_path, loop=self._menu_bgm_loop, fade=True)

    def _start_new_game(self, reset_globals: bool | None = None):
        show_overlay = self._loading_overlay_enabled_for("start_game")
        if show_overlay:
            self._loading_begin("正在开始游戏...", subtitle=None)
        self._loading_progress(0.12, "初始化游戏状态...")
        self.mode = "game"
        self._save_overlay = False
        self._load_overlay = False
        self._settings_overlay = False
        self._choice_overlay = False
        self._history = []
        self._history_overlay = False
        self._stop_bgm()
        self._stop_video()
        do_reset = self._reset_globals_on_start if reset_globals is None else bool(reset_globals)
        # reset_globals_on_start=False 的语义是“不要清空已存在的运行时变量”。
        # 但首次开局 variables 为空时仍应从定义初始化，否则 F3 会看到空变量。
        if do_reset or not (isinstance(self.variables, dict) and self.variables):
            self._init_variables_from_defs()
        self._loading_progress(0.45, "加载对白与流程...")
        self.fast_skip = False
        self._fast_skip_timer = 0.0
        self.current_index = 0
        self._sub_index = 0
        self.current_node_id = None
        self._voice_played_index = None
        self._bgm_current = None
        self._stop_voice_playback()
        # Fast path: if project file unchanged since last load, reuse loaded dialogues/graph and cached assets.
        if not self._project_changed_since_last_dialogue_load():
            if self.graph_mode:
                self._select_graph_start_node_id()
                self._sub_index = 0
            else:
                self.current_index = 0
                self._sub_index = 0
                self.current_node_id = None
            self._on_enter_node()
            self._reset_typing_state()
        else:
            self._reload_dialogues()
        self._loading_progress(0.95, "进入游戏...")
        if show_overlay:
            self._loading_end()

    def _continue_latest(self):
        latest_slot = self._find_latest_slot(include_autosave=True)
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

    def _continue_autosave(self):
        """主菜单继续：优先读取自动存档点；无则回退到最新手动存档；仍无则新开游戏。"""
        autosave_path = slot_file_path(self.save_dir, AUTO_SAVE_SLOT)
        if autosave_path.exists():
            slot = AUTO_SAVE_SLOT
        else:
            slot = self._find_latest_slot(include_autosave=False)
        if slot is None:
            print("没有可继续的存档（含自动存档），自动开始新游戏")
            self._start_new_game()
            return
        self.mode = "game"
        self._save_overlay = False
        self._load_overlay = False
        self._settings_overlay = False
        self._choice_overlay = False
        self.fast_skip = False
        self._fast_skip_timer = 0.0
        self.load_game(slot)

    def _open_load_from_menu(self):
        self._overlay_return_mode = "menu"
        self._load_overlay = True
        self._save_overlay = False
        self._settings_overlay = False
        self._choice_overlay = False
        self._history_overlay = False
        self._help_overlay = False
        self._exit_confirm_overlay = False
        self._save_page = 0
        self._overlay_scroll_offset = 0
        self._overlay_dragging_slider = None

    def _open_settings_from_menu(self):
        self._overlay_return_mode = "menu"
        self._settings_overlay = True
        self._save_overlay = False
        self._load_overlay = False
        self._choice_overlay = False
        self._history_overlay = False
        self._help_overlay = False
        self._exit_confirm_overlay = False
        self._overlay_scroll_offset = 0
        self._overlay_dragging_slider = None
        if self._function_menus_enabled:
            self._overlay_settings_snapshot = dict(self._settings)

    def _move_menu(self, delta: int):
        count = len(self._menu_items)
        self._menu_selected = (self._menu_selected + delta) % count

    def _activate_menu_item(self):
        if not self._menu_items:
            return
        action = self._menu_items[self._menu_selected].get("action")
        if action == "start":
            self._start_new_game(reset_globals=self._reset_globals_on_start)
        elif action == "continue":
            self._continue_autosave()
        elif action == "load":
            self._open_load_from_menu()
        elif action == "settings":
            self._open_settings_from_menu()
        elif action == "exit":
            self.quit_game()

    def _find_latest_slot(self, include_autosave: bool = True) -> int | None:
        latest = None
        latest_time = None
        indices = [AUTO_SAVE_SLOT, *range(1, self._save_slots + 1)] if include_autosave else list(range(1, self._save_slots + 1))
        for idx in indices:
            path = slot_file_path(self.save_dir, idx)
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
        protected = getattr(self, "_protected_vars", set()) or set()
        old = dict(self.variables) if isinstance(self.variables, dict) else {}
        out: dict[str, float] = {}
        for item in self._global_var_defs or []:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not name:
                continue
            name = str(name)
            try:
                init_val = float(item.get("initial", 0.0))
            except Exception:
                init_val = 0.0

            if name in protected:
                if name in old:
                    try:
                        out[name] = float(old.get(name))
                    except Exception:
                        out[name] = init_val
                elif name in (self._persistent_vars or {}):
                    try:
                        out[name] = float(self._persistent_vars.get(name))
                    except Exception:
                        out[name] = init_val
                else:
                    out[name] = init_val
            else:
                out[name] = init_val

        self.variables = out
        self._update_persistent_from_runtime()
        self._save_persistent_vars()

    def _invalidate_slot_thumbnail_cache(self, slot: int) -> None:
        """Remove cached thumbnails for a given slot (all sizes/mtimes)."""

        try:
            p = str(slot_thumbnail_path(self.save_dir, int(slot)))
        except Exception:
            return
        try:
            for k in list(self._slot_thumbnail_cache.keys()):
                if k and k[0] == p:
                    self._slot_thumbnail_cache.pop(k, None)
        except Exception:
            return

    def _load_menu_assets(self):
        self._loading_progress(0.05, "加载主菜单资源...")
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
        self._loading_progress(0.35, "加载主菜单资源...")

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
        self._loading_progress(0.55, "加载主菜单资源...")

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
        self._loading_progress(0.65, "加载主菜单资源...")

        # title image
        self._menu_title_image_surface = None
        img_path = None
        if self._menu_title_image_path:
            img_path = self._resolve_path(self._menu_title_image_path)
        if img_path and img_path.exists():
            try:
                img = pygame.image.load(str(img_path)).convert_alpha()
                scale = getattr(self, "_menu_title_image_scale", 1.0) or 1.0
                try:
                    scale = float(scale)
                except Exception:
                    scale = 1.0
                scale = max(0.1, min(5.0, scale))
                if abs(scale - 1.0) > 1e-6:
                    w = max(1, int(img.get_width() * scale))
                    h = max(1, int(img.get_height() * scale))
                    img = pygame.transform.smoothscale(img, (w, h))
                self._menu_title_image_surface = img
            except Exception:
                self._menu_title_image_surface = None
        self._loading_progress(0.78, "加载主菜单资源...")

        # option button images
        self._menu_option_image_surfaces = {}
        for it in getattr(self, "_menu_items", []) or []:
            if not isinstance(it, dict):
                continue
            if str(it.get("style") or "text") != "image":
                continue
            action = str(it.get("action") or "")
            img_rel = str(it.get("image") or "")
            if not action or not img_rel:
                continue
            p = self._resolve_path(img_rel)
            if not p.exists():
                continue
            try:
                img = pygame.image.load(str(p)).convert_alpha()
                self._menu_option_image_surfaces[action] = img
            except Exception:
                continue
        self._loading_progress(0.92, "加载主菜单资源...")

        # indicator image (optional)
        self._menu_option_indicator_image_surface = None
        if getattr(self, "_menu_option_indicator_image_path", ""):
            p = self._resolve_path(self._menu_option_indicator_image_path)
            if p.exists():
                try:
                    self._menu_option_indicator_image_surface = pygame.image.load(str(p)).convert_alpha()
                except Exception:
                    self._menu_option_indicator_image_surface = None
        self._loading_progress(1.0, "加载主菜单资源...")

    def _preload_menu_media(self):
        """预加载主菜单媒体，避免进入时黑屏或卡顿。"""
        self._loading_push(0.0, 0.55)
        self._load_menu_assets()
        self._loading_pop()
        self._loading_progress(0.62, "预加载主菜单媒体...")
        # 预取视频首帧
        if self._menu_video_path:
            self._video_time = 0.0
            self._update_video(self._menu_video_path, self._menu_video_loop, 0.0)
        self._loading_progress(0.78, "预加载主菜单媒体...")
        # 预加载BGM到缓冲（不播放）
        if self._menu_bgm_path:
            try:
                if not pygame.mixer.get_init():
                    pygame.mixer.init()
                pygame.mixer.music.load(self._menu_bgm_path)
                pygame.mixer.music.stop()
            except Exception:
                pass
        self._loading_progress(1.0, "预加载主菜单媒体...")

    def _start_splash(self):
        self.mode = "splash"
        self._splash_elapsed = 0.0
        show_overlay = self._loading_overlay_enabled_for("load_game")
        if show_overlay:
            self._loading_begin("启动中...", subtitle=(self.project_path.name if self.project_path else None))
        self._loading_progress(0.05, "预加载主菜单媒体...")
        self._preload_menu_media()
        if show_overlay:
            self._loading_end()

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
            # 设计器“从节点开始预览”：跳过主菜单，直接进入游戏
            if self._preview_start_node_id is not None:
                self._start_new_game(reset_globals=True)
            else:
                self._enter_menu()

    def set_preview_start_node(self, node_id: int | str | None):
        """设置预览起始节点（仅影响本次进程）。"""
        self._preview_start_node_id = node_id

    def start_game(self):
        """启动游戏（进入事件循环）"""
        self.running = True
        print("游戏预览窗口已启动，点击关闭按钮或按ESC退出")
        self._start_splash()

        while self.running:
            dt = self.clock.tick(60) / 1000.0
            self._last_dt = dt
            self._process_main_thread_script_actions()
            self._update_script_runtime(dt)
            self.render_surface.fill(self.bg_color)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.quit_game()

                # modal alert from function scripts: swallow inputs until dismissed

                # modal alert from function scripts: swallow inputs until dismissed
                if self._script_modal_message is not None:
                    if event.type == pygame.KEYDOWN:
                        self._script_modal_message = None
                        continue
                    if event.type == pygame.MOUSEBUTTONDOWN and getattr(event, "button", None) == 1:
                        self._script_modal_message = None
                        continue
                    # keep blocking all other inputs while modal is showing
                    continue

                # input lock from function scripts (game mode only)
                if self.mode == "game" and self._is_script_input_locked():
                    if event.type in (
                        pygame.KEYDOWN,
                        pygame.KEYUP,
                        pygame.MOUSEMOTION,
                        pygame.MOUSEBUTTONDOWN,
                        pygame.MOUSEBUTTONUP,
                        pygame.MOUSEWHEEL,
                        pygame.TEXTINPUT,
                    ):
                        continue

                if event.type == pygame.KEYDOWN:
                    # lazy init help hotkey mapping after pygame init
                    if self._help_key is None:
                        self._help_key = self._parse_hotkey_to_pygame_key(self._help_hotkey_name) or pygame.K_F1

                    if self.mode == "splash":
                        if event.key == pygame.K_ESCAPE:
                            self.quit_game()
                            break
                        else:
                            if self._preview_start_node_id is not None:
                                self._start_new_game(reset_globals=True)
                            else:
                                self._enter_menu()
                            continue

                    # 截图模式：任意键恢复（并吞掉该次输入，避免误推进对白/触发按钮）
                    if self.mode == "game" and self._screenshot_hide_ui:
                        self._screenshot_hide_ui = False
                        continue
                    # global overlay handling (works in menu or game)
                    if event.key == pygame.K_ESCAPE and (
                        self._save_overlay
                        or self._load_overlay
                        or self._settings_overlay
                        or self._choice_overlay
                        or self._history_overlay
                        or self._help_overlay
                        or self._exit_confirm_overlay
                    ):
                        self._save_overlay = False
                        self._load_overlay = False
                        self._settings_overlay = False
                        self._choice_overlay = False
                        self._history_overlay = False
                        self._help_overlay = False
                        self._exit_confirm_overlay = False
                        self._restore_mode_if_needed()
                        continue

                    # exit confirm overlay
                    if self._exit_confirm_overlay:
                        if event.key in (pygame.K_LEFT, pygame.K_a, pygame.K_UP, pygame.K_w):
                            self._exit_confirm_choice = 0
                            continue
                        if event.key in (pygame.K_RIGHT, pygame.K_d, pygame.K_DOWN, pygame.K_s):
                            self._exit_confirm_choice = 1
                            continue
                        if event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_y):
                            if self._enable_autosave_on_menu and self.mode == "game":
                                self.save_game(AUTO_SAVE_SLOT)
                            self._exit_confirm_overlay = False
                            self._enter_menu()
                            continue
                        if event.key in (pygame.K_ESCAPE, pygame.K_n):
                            self._exit_confirm_overlay = False
                            self._restore_mode_if_needed()
                            continue

                    # help overlay toggle
                    if event.key == self._help_key:
                        self._toggle_help_overlay()
                        continue

                    # 截图模式切换（游戏内）
                    if self.mode == "game" and event.key == pygame.K_F12:
                        self._screenshot_hide_ui = not self._screenshot_hide_ui
                        continue

                    # save/load overlay paging (10 slots per page)
                    if (self._save_overlay or self._load_overlay) and event.key in (pygame.K_UP, pygame.K_DOWN, pygame.K_PAGEUP, pygame.K_PAGEDOWN):
                        delta = -1 if event.key in (pygame.K_UP, pygame.K_PAGEUP) else 1
                        ps = self._active_slot_page_size()
                        self._save_page = clamp_page(self._save_page + delta, self._save_slots, ps)
                        continue

                    # load autosave (A)
                    if self._load_overlay and event.key == pygame.K_a:
                        # 空的自动存档：不做任何事，也不退出读档界面
                        try:
                            if slot_file_path(self.save_dir, AUTO_SAVE_SLOT).exists():
                                self.load_game(AUTO_SAVE_SLOT)
                                self._load_overlay = False
                                self._overlay_return_mode = None
                        except Exception:
                            pass
                        continue

                    # save/load overlay digit selection (0-9)
                    if self._save_overlay or self._load_overlay:
                        digit = self._key_to_digit(event.key)
                        if digit is not None:
                            ps = self._active_slot_page_size()
                            slot = digit_to_slot(self._save_page, digit, page_size=ps)
                            if slot is not None and 1 <= slot <= self._save_slots:
                                if self._load_overlay:
                                    # 空槽位数字键：不做任何事，也不退出读档界面
                                    try:
                                        if slot_file_path(self.save_dir, slot).exists():
                                            self.load_game(slot)
                                            self._load_overlay = False
                                            self._overlay_return_mode = None
                                    except Exception:
                                        pass
                                    continue
                                if self._save_overlay:
                                    self.save_game(slot)
                                    # 保持停留在存档界面，仅刷新显示
                                    try:
                                        self._invalidate_slot_thumbnail_cache(int(slot))
                                    except Exception:
                                        pass
                                    continue
                    if self._settings_overlay:
                        if self._handle_settings_key(event.key):
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
                        # ESC 返回主菜单：二次确认 + 自动存档
                        self._open_exit_confirm()
                        continue
                    elif event.key == pygame.K_SPACE or event.key == pygame.K_RETURN:
                        if self._settings_overlay:
                            if self._handle_settings_key(event.key):
                                self._restore_mode_if_needed()
                                continue
                        elif not (self._save_overlay or self._load_overlay or self._choice_overlay):
                                if self._auto_next_lock_active():
                                    self._reveal_current_text()
                                else:
                                    self.advance_dialogue()
                    elif event.key == pygame.K_F11:
                        self.toggle_fullscreen()
                    elif event.key == pygame.K_F5:
                        self._overlay_return_mode = self.mode
                        self._save_overlay = True
                        self._load_overlay = False
                        self._settings_overlay = False
                        self._history_overlay = False
                        self._help_overlay = False
                        self._exit_confirm_overlay = False
                        self._save_page = 0
                        self._overlay_scroll_offset = 0
                        self._overlay_dragging_slider = None
                    elif event.key == pygame.K_F9:
                        self._overlay_return_mode = self.mode
                        self._load_overlay = True
                        self._save_overlay = False
                        self._settings_overlay = False
                        self._history_overlay = False
                        self._help_overlay = False
                        self._exit_confirm_overlay = False
                        self._save_page = 0
                        self._overlay_scroll_offset = 0
                        self._overlay_dragging_slider = None
                    elif event.key == pygame.K_F10:
                        self._overlay_return_mode = self.mode
                        self._settings_overlay = True
                        self._save_overlay = False
                        self._load_overlay = False
                        self._history_overlay = False
                        self._help_overlay = False
                        self._exit_confirm_overlay = False
                        self._overlay_scroll_offset = 0
                        self._overlay_dragging_slider = None
                        if self._function_menus_enabled:
                            self._overlay_settings_snapshot = dict(self._settings)
                    elif event.key == pygame.K_TAB:
                        if not (self._save_overlay or self._load_overlay or self._settings_overlay or self._help_overlay or self._exit_confirm_overlay):
                            self.fast_skip = not self.fast_skip
                            self._fast_skip_timer = 0.0
                            self._reset_typing_state()
                        continue
                    elif event.key == pygame.K_s:
                        if not (self._save_overlay or self._load_overlay or self._settings_overlay or self._choice_overlay or self._history_overlay or self._help_overlay or self._exit_confirm_overlay):
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
                            self._help_overlay = False
                            self._exit_confirm_overlay = False
                            self._overlay_scroll_offset = 0
                            self._overlay_dragging_slider = None
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
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
                    # 截图模式：右键恢复（并吞掉该次输入）
                    if self.mode == "game" and self._screenshot_hide_ui:
                        self._screenshot_hide_ui = False
                        continue
                    if self._help_right_click:
                        self._toggle_help_overlay()
                        continue
                if event.type == pygame.MOUSEMOTION:
                    # default: arrow
                    cursor_hand = False

                    # function-menu overlays (mouse-enabled)
                    if self._function_menus_enabled and self._overlay_type() is not None:
                        rp = self._window_pos_to_render_pos(getattr(event, "pos", None))
                        cursor_hand = bool(self._overlay_handle_mouse_motion(rp))
                        self._set_mouse_cursor(hand=cursor_hand)
                        continue

                    # choice overlay hover (mouse-enabled)
                    if self.mode == "game" and self._choice_overlay and self._choice_buttons_enabled:
                        rp = self._window_pos_to_render_pos(getattr(event, "pos", None))
                        if rp is not None:
                            hit = self._hit_test_choice_button(rp)
                            self._choice_selected = int(hit) if hit is not None else -1
                            cursor_hand = hit is not None
                        self._set_mouse_cursor(hand=cursor_hand)
                        continue

                    if self.mode == "game" and self._hud_buttons_enabled and not (
                        self._save_overlay
                        or self._load_overlay
                        or self._settings_overlay
                        or self._choice_overlay
                        or self._history_overlay
                        or self._help_overlay
                        or self._exit_confirm_overlay
                    ) and not self._ui_hidden_for_current_node():
                        rp = self._window_pos_to_render_pos(getattr(event, "pos", None))
                        if rp is not None:
                            hit = self._hit_test_hud_button(rp)
                            self._hud_selected = hit if hit is not None else -1
                            cursor_hand = hit is not None
                    if self.mode == "menu" and not (
                        self._save_overlay
                        or self._load_overlay
                        or self._settings_overlay
                        or self._history_overlay
                        or self._help_overlay
                        or self._exit_confirm_overlay
                    ):
                        rp = self._window_pos_to_render_pos(getattr(event, "pos", None))
                        if rp is not None:
                            hit = self._hit_test_menu_item(rp)
                            if hit is not None and hit != self._menu_selected:
                                self._menu_selected = hit
                            cursor_hand = hit is not None

                    # apply cursor change (menu/hud clickable areas)
                    self._set_mouse_cursor(hand=cursor_hand)
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    # 截图模式：左键恢复（并吞掉该次输入）
                    if self.mode == "game" and self._screenshot_hide_ui:
                        self._screenshot_hide_ui = False
                        continue
                    # function-menu overlays (mouse-enabled)
                    if self._function_menus_enabled and self._overlay_type() is not None:
                        rp = self._window_pos_to_render_pos(getattr(event, "pos", None))
                        self._overlay_handle_mouse_down(rp)
                        continue

                    # choice overlay (mouse-enabled, only when enabled by UI layout)
                    if self.mode == "game" and self._choice_overlay and self._choice_buttons_enabled:
                        rp = self._window_pos_to_render_pos(getattr(event, "pos", None))
                        if rp is not None:
                            hit = self._hit_test_choice_button(rp)
                            if hit is not None:
                                self._choice_selected = int(hit)
                                self._apply_choice(int(hit))
                        # do not fall through to advance_dialogue when choice overlay is open
                        continue

                    if self.mode == "menu":
                        # menu mouse click: prefer hovered item
                        if not (
                            self._save_overlay
                            or self._load_overlay
                            or self._settings_overlay
                            or self._history_overlay
                            or self._help_overlay
                            or self._exit_confirm_overlay
                        ):
                            rp = self._window_pos_to_render_pos(getattr(event, "pos", None))
                            if rp is not None:
                                hit = self._hit_test_menu_item(rp)
                                if hit is not None:
                                    self._menu_selected = hit
                                    self._activate_menu_item()
                        # overlay open in menu: ignore click (mouse overlay not implemented)
                        continue
                    if self.mode == "game" and self._hud_buttons_enabled and not (
                        self._save_overlay
                        or self._load_overlay
                        or self._settings_overlay
                        or self._choice_overlay
                        or self._history_overlay
                        or self._help_overlay
                        or self._exit_confirm_overlay
                    ) and not self._ui_hidden_for_current_node():
                        rp = self._window_pos_to_render_pos(getattr(event, "pos", None))
                        if rp is not None:
                            hit = self._hit_test_hud_button(rp)
                            if hit is not None:
                                self._hud_selected = hit
                                self._activate_hud_button(hit)
                                continue
                    if not (
                        self._save_overlay
                        or self._load_overlay
                        or self._settings_overlay
                        or self._choice_overlay
                        or self._history_overlay
                        or self._help_overlay
                        or self._exit_confirm_overlay
                    ):
                        if self._auto_next_lock_active():
                            self._reveal_current_text()
                        else:
                            self.advance_dialogue()
                if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    if self._function_menus_enabled and self._overlay_type() is not None:
                        self._overlay_handle_mouse_up()
                        continue

                if event.type == pygame.MOUSEWHEEL:
                    if self._function_menus_enabled and self._overlay_type() is not None:
                        try:
                            self._overlay_handle_wheel(int(getattr(event, "y", 0)))
                        except Exception:
                            pass
                        continue
                if event.type == pygame.KEYUP:
                    if event.key == pygame.K_s:
                        self.fast_skip = False
                        self._fast_skip_timer = 0.0

            if not self.running:
                break

            self._update_choice_timeout(dt)

            if self.mode == "splash":
                self._render_splash(dt)
            elif self.mode == "menu":
                self._render_menu(dt)
                if self._save_overlay or self._load_overlay or self._settings_overlay or self._help_overlay:
                    self._render_overlay()
            else:
                # overlays pause dialogue progression but still render current frame
                if not (self._save_overlay or self._load_overlay or self._settings_overlay or self._choice_overlay or self._history_overlay or self._help_overlay or self._exit_confirm_overlay):
                    self._update_typing(dt)
                    self._update_auto_next(dt)
                self._process_pending_audio(dt)
                advanced_this_tick = False
                # 如果淡出动画已结束并需要推进到下一子节点：先推进再渲染，避免渲染后重建 surface 导致闪黑。
                if self._pending_sub_advance:
                    self._pending_sub_advance = False
                    self.advance_dialogue()
                    advanced_this_tick = True
                self._render_scene(dt)
                # 避免同一帧内由于 fast-skip 再次推进
                if not advanced_this_tick:
                    self._update_fast_skip(dt)

            self._render_script_layers(dt)
            self._blit_to_window()
            pygame.display.flip()

    def _update_choice_timeout(self, dt: float) -> None:
        if not self._choice_overlay:
            self._choice_timeout_remaining = None
            self._choice_default_index = -1
            return

        # pause countdown while other overlays are open
        if self._save_overlay or self._load_overlay or self._settings_overlay or self._history_overlay or self._help_overlay or self._exit_confirm_overlay:
            return

        remaining = getattr(self, "_choice_timeout_remaining", None)
        if remaining is None:
            return
        try:
            remaining = float(remaining) - max(0.0, float(dt))
        except Exception:
            remaining = 0.0
        self._choice_timeout_remaining = remaining
        if remaining > 0.0:
            return

        default_idx = int(getattr(self, "_choice_default_index", -1))
        if default_idx < 0:
            self._choice_timeout_remaining = None
            return
        if default_idx >= len(self._choice_targets or []):
            self._choice_timeout_remaining = None
            return

        # Ensure we only fire once
        self._choice_timeout_remaining = None
        self._apply_choice(default_idx)

    def _update_script_runtime(self, dt: float) -> None:
        """Update timers and transient script-driven state (main thread)."""
        try:
            self._script_time_now += max(0.0, float(dt))
        except Exception:
            return

        # toast life
        try:
            if self._script_toasts:
                alive: list[dict] = []
                for t in self._script_toasts:
                    if not isinstance(t, dict):
                        continue
                    rem = float(t.get("remaining", 0.0)) - max(0.0, float(dt))
                    if rem > 0.0:
                        t["remaining"] = rem
                        alive.append(t)
                self._script_toasts = alive
        except Exception:
            pass

        # flash
        try:
            if isinstance(self._script_flash, dict):
                rem = float(self._script_flash.get("remaining", 0.0)) - max(0.0, float(dt))
                if rem <= 0.0:
                    self._script_flash = None
                else:
                    self._script_flash["remaining"] = rem
        except Exception:
            self._script_flash = None

        # shake
        try:
            if isinstance(self._script_shake, dict):
                rem = float(self._script_shake.get("remaining", 0.0)) - max(0.0, float(dt))
                if rem <= 0.0:
                    self._script_shake = None
                    self._script_shake_offset = (0.0, 0.0)
                else:
                    self._script_shake["remaining"] = rem
                    duration = max(0.001, float(self._script_shake.get("duration", 0.001)))
                    strength = float(self._script_shake.get("strength", 0.0))
                    decay = bool(self._script_shake.get("decay", True))
                    if decay:
                        strength = strength * max(0.0, min(1.0, rem / duration))
                    self._script_shake_offset = (
                        random.uniform(-strength, strength),
                        random.uniform(-strength, strength),
                    )
        except Exception:
            self._script_shake = None
            self._script_shake_offset = (0.0, 0.0)

        # input lock
        try:
            if self._script_input_lock_remaining is not None:
                rem = float(self._script_input_lock_remaining) - max(0.0, float(dt))
                if rem <= 0.0:
                    self._script_input_lock_remaining = None
                else:
                    self._script_input_lock_remaining = rem
        except Exception:
            self._script_input_lock_remaining = None

        try:
            expr = getattr(self, "_script_input_lock_until_expr", None)
            if isinstance(expr, str) and expr.strip():
                # optional timeout to prevent deadlocks
                if self._script_input_lock_until_timeout is not None:
                    t_rem = float(self._script_input_lock_until_timeout) - max(0.0, float(dt))
                    if t_rem <= 0.0:
                        self._script_input_lock_until_expr = None
                        self._script_input_lock_until_timeout = None
                    else:
                        self._script_input_lock_until_timeout = t_rem
                # unlock once condition becomes True
                if self._script_input_lock_until_expr is not None and self._eval_script_input_lock_expr(str(expr)):
                    self._script_input_lock_until_expr = None
                    self._script_input_lock_until_timeout = None
            else:
                self._script_input_lock_until_expr = None
                self._script_input_lock_until_timeout = None
        except Exception:
            self._script_input_lock_until_expr = None
            self._script_input_lock_until_timeout = None

        # script images life
        try:
            if isinstance(self._script_images, dict) and self._script_images:
                alive: dict[str, dict] = {}
                for k, info in list(self._script_images.items()):
                    if not isinstance(info, dict):
                        continue
                    rem = info.get("remaining", None)
                    if rem is None:
                        alive[str(k)] = info
                        continue
                    try:
                        rem2 = float(rem) - max(0.0, float(dt))
                    except Exception:
                        rem2 = 0.0
                    if rem2 > 0.0:
                        info["remaining"] = rem2
                        alive[str(k)] = info
                self._script_images = alive
        except Exception:
            pass

        # timers
        now = float(self._script_time_now)
        due: list[dict] = []
        with self._script_timer_lock:
            for tid, info in list(self._script_timers.items()):
                if not isinstance(info, dict):
                    continue
                try:
                    if float(info.get("next", 0.0)) <= now:
                        due.append(dict(info))
                except Exception:
                    continue

        for info in sorted(due, key=lambda x: float(x.get("next", 0.0))):
            self._fire_script_timer(info)

    def _create_script_timer(self, seconds: float, script: str, *, interval: float = 0.0, repeat: int = 0, host_node_id=None) -> int:
        delay = max(0.0, float(seconds))
        interval = max(0.0, float(interval))
        rep = int(repeat)
        # normalize repeat for interval timers:
        # - rep < 0: infinite
        # - rep == 0: run once
        if interval > 0.0 and rep == 0:
            rep = 1

        with self._script_timer_lock:
            tid = int(self._script_timer_next_id)
            self._script_timer_next_id += 1
            self._script_timers[tid] = {
                "id": tid,
                "next": float(self._script_time_now) + delay,
                "interval": interval,
                "repeat": rep,
                "script": str(script or ""),
                "host_node_id": host_node_id,
            }
        return tid

    def _clear_script_timer(self, timer_id: int) -> bool:
        with self._script_timer_lock:
            return self._script_timers.pop(int(timer_id), None) is not None

    def _fire_script_timer(self, info: dict) -> None:
        tid = int(info.get("id", 0) or 0)
        script = str(info.get("script", "") or "")
        if tid <= 0 or not script.strip():
            return

        # reschedule/remove under lock (avoid double-fire)
        with self._script_timer_lock:
            cur = self._script_timers.get(tid)
            if not isinstance(cur, dict):
                return
            interval = float(cur.get("interval", 0.0) or 0.0)
            repeat = int(cur.get("repeat", 0) or 0)

            if interval > 0.0:
                if repeat > 0:
                    repeat -= 1
                    cur["repeat"] = repeat
                if repeat == 0:
                    self._script_timers.pop(tid, None)
                else:
                    cur["next"] = float(self._script_time_now) + max(0.001, interval)
                    self._script_timers[tid] = cur
            else:
                self._script_timers.pop(tid, None)

        host_node_id = info.get("host_node_id")
        t = threading.Thread(
            target=self._execute_timer_script_worker,
            args=(tid, host_node_id, script),
            daemon=True,
        )
        t.start()

    def _execute_timer_script_worker(self, timer_id: int, host_node_id, script: str) -> None:
        try:
            entry_snapshot = dict(self._current_entry() or {})
        except Exception:
            entry_snapshot = {}
        try:
            vars_snapshot = dict(self.variables) if isinstance(getattr(self, "variables", None), dict) else {}
        except Exception:
            vars_snapshot = {}

        fn = {"node_type": "timer", "id": int(timer_id)}
        api = VNGameRuntime._FunctionScriptAPI(self, host_node_id, fn)
        try:
            self._exec_function_script(str(script), api, entry_snapshot, vars_snapshot, fn, -1)
        except Exception as exc:
            api.log(f"timer script error: {exc}")

    def _render_script_layers(self, dt: float) -> None:
        """Draw script-driven overlays on the render surface."""
        # flash overlay
        try:
            if isinstance(self._script_flash, dict):
                duration = max(0.001, float(self._script_flash.get("duration", 0.001)))
                remaining = max(0.0, float(self._script_flash.get("remaining", 0.0)))
                base_alpha = int(self._script_flash.get("alpha", 180) or 180)
                base_alpha = max(0, min(255, base_alpha))
                p = max(0.0, min(1.0, remaining / duration))
                alpha = int(round(base_alpha * p))
                color = self._script_flash.get("color", (255, 255, 255))
                try:
                    r, g, b = int(color[0]), int(color[1]), int(color[2])
                except Exception:
                    r, g, b = 255, 255, 255
                if alpha > 0:
                    overlay = pygame.Surface(self.render_size, pygame.SRCALPHA)
                    overlay.fill((max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)), alpha))
                    self.render_surface.blit(overlay, (0, 0))
        except Exception:
            pass

        # toasts
        try:
            if self._script_toasts:
                font = getattr(self, "font", None)
                if font is not None:
                    margin = 14
                    y = self.render_size[1] - 60
                    for t in self._script_toasts[-3:]:
                        text = str(t.get("text", "") or "")
                        if not text:
                            continue
                        surf = font.render(text, True, (255, 255, 255))
                        pad_x, pad_y = 12, 8
                        w = surf.get_width() + pad_x * 2
                        h = surf.get_height() + pad_y * 2
                        x = (self.render_size[0] - w) // 2
                        bg = pygame.Surface((w, h), pygame.SRCALPHA)
                        bg.fill((0, 0, 0, 170))
                        self.render_surface.blit(bg, (x, y))
                        self.render_surface.blit(surf, (x + pad_x, y + pad_y))
                        y -= (h + margin)
        except Exception:
            pass

        # modal alert
        try:
            if isinstance(self._script_modal_message, dict):
                text = str(self._script_modal_message.get("text", "") or "")
                if text:
                    overlay = pygame.Surface(self.render_size, pygame.SRCALPHA)
                    overlay.fill((0, 0, 0, 140))
                    self.render_surface.blit(overlay, (0, 0))
                    font = getattr(self, "font", None)
                    title_font = getattr(self, "name_font", None)
                    title = str(self._script_modal_message.get("title", "提示") or "提示")
                    if font is not None and title_font is not None:
                        max_w = self.render_size[0] - 160
                        lines: list[str] = []
                        cur = ""
                        for ch in text:
                            test = cur + ch
                            if cur and font.size(test)[0] > max_w:
                                lines.append(cur)
                                cur = ch
                            else:
                                cur = test
                        if cur:
                            lines.append(cur)
                        lines = lines[:10]

                        title_surf = title_font.render(title, True, (255, 255, 255))
                        line_surfs = [font.render(ln, True, (235, 235, 235)) for ln in lines]
                        hint_surf = font.render("按任意键关闭", True, (210, 210, 210))
                        w = max(title_surf.get_width(), hint_surf.get_width(), *(s.get_width() for s in line_surfs)) + 40
                        h = title_surf.get_height() + hint_surf.get_height() + sum(s.get_height() for s in line_surfs) + 48
                        w = min(self.render_size[0] - 80, w)
                        x = (self.render_size[0] - w) // 2
                        y = (self.render_size[1] - h) // 2
                        box = pygame.Surface((w, h), pygame.SRCALPHA)
                        box.fill((20, 22, 28, 235))
                        self.render_surface.blit(box, (x, y))
                        yy = y + 18
                        self.render_surface.blit(title_surf, (x + 20, yy))
                        yy += title_surf.get_height() + 14
                        for s in line_surfs:
                            self.render_surface.blit(s, (x + 20, yy))
                            yy += s.get_height() + 6
                        self.render_surface.blit(hint_surf, (x + 20, y + h - hint_surf.get_height() - 16))
        except Exception:
            pass

        # top-most script images
        try:
            if isinstance(self._script_images, dict) and self._script_images:
                items = [v for v in self._script_images.values() if isinstance(v, dict)]
                items.sort(key=lambda x: float(x.get("z", 1000.0)))
                for info in items:
                    surf = info.get("surface")
                    rect = info.get("rect")
                    if surf is None or rect is None:
                        continue
                    self.render_surface.blit(surf, rect)
        except Exception:
            pass

    def _is_script_input_locked(self) -> bool:
        try:
            if self._script_input_lock_remaining is not None and float(self._script_input_lock_remaining) > 0.0:
                return True
        except Exception:
            pass
        try:
            expr = getattr(self, "_script_input_lock_until_expr", None)
            return bool(isinstance(expr, str) and expr.strip())
        except Exception:
            return False

    def _eval_script_input_lock_expr(self, expr: str) -> bool:
        """Evaluate an input-lock 'until' expression safely on the main thread."""
        s = str(expr or "").strip()
        if not s:
            return True
        try:
            safe_builtins = {
                "True": True,
                "False": False,
                "None": None,
                "int": int,
                "float": float,
                "str": str,
                "bool": bool,
                "len": len,
                "min": min,
                "max": max,
                "abs": abs,
                "sum": sum,
            }
            g = {"__builtins__": safe_builtins}
            l = {"vars": dict(self.variables) if isinstance(getattr(self, "variables", None), dict) else {}}
            code = compile(s, "<function-input-lock-until>", "eval")
            return bool(eval(code, g, l))
        except Exception:
            # On error, keep locked.
            return False

    def _window_pos_to_render_pos(self, window_pos):
        """Convert window/screen mouse position to render_surface coordinates.

        Accounts for letterboxing behavior implemented in `_blit_to_window`.
        Returns None if the position is outside the rendered game area.
        """
        if window_pos is None:
            return None

        wx, wy = window_pos
        screen = getattr(self, "screen", None)
        if screen is None:
            return None
        win_w, win_h = screen.get_size()
        base_w, base_h = self.render_surface.get_size()
        if win_w <= 0 or win_h <= 0 or base_w <= 0 or base_h <= 0:
            return None

        scale = min(win_w / base_w, win_h / base_h)
        scaled_w = int(base_w * scale)
        scaled_h = int(base_h * scale)
        offset_x = (win_w - scaled_w) // 2
        offset_y = (win_h - scaled_h) // 2

        if wx < offset_x or wy < offset_y or wx >= offset_x + scaled_w or wy >= offset_y + scaled_h:
            return None

        rx = int((wx - offset_x) / scale)
        ry = int((wy - offset_y) / scale)
        rx = max(0, min(base_w - 1, rx))
        ry = max(0, min(base_h - 1, ry))
        return rx, ry

    def _hit_test_menu_item(self, render_pos):
        if not self._menu_item_hitboxes:
            return None
        x, y = render_pos
        for idx, rect in enumerate(self._menu_item_hitboxes):
            if rect is not None and rect.collidepoint(x, y):
                return idx
        return None

    def advance_dialogue(self):
        entry = self._current_entry()
        if not entry:
            return
        full_text = entry.get("content") or entry.get("title") or ""
        try:
            full_text = self._interpolate_dialogue_template(str(full_text))
        except Exception:
            pass
        if self.current_visible_len < len(full_text):
            self.current_visible_len = len(full_text)
            return

        # leaving current子节点/节点：清理自动下一句倒计时（若有）
        self._auto_next_remaining = None

        # leaving current子节点/节点时先停止当前语音，避免残留播放
        self._stop_voice_playback()

        if self.graph_mode:
            node_type = entry.get("node_type", "text")
            if node_type == "text":
                subs = (self.nodes_map.get(self.current_node_id, {}) or {}).get("sub_dialogues") or []
                if subs and 0 <= self._sub_index < len(subs):
                    # leaving current sub-dialogue
                    if self._sub_index < len(subs) - 1:
                        # advance within the same text node
                        started_1 = self._maybe_start_portrait_fade_out(subs[self._sub_index])
                        started_2 = self._maybe_start_portrait2_fade_out(subs[self._sub_index])
                        if started_1 or started_2:
                            return
                        self._sub_index += 1
                        self._voice_played_index = None
                        # 同一节点子对话切换，避免重复刷新BGM/UI以防卡顿
                        self._on_enter_node(skip_media=True)
                        self._reset_typing_state()
                        return
                    else:
                        # leaving the LAST sub-dialogue: also respect fade-out before jumping to next node
                        started_1 = self._maybe_start_portrait_fade_out(subs[self._sub_index])
                        started_2 = self._maybe_start_portrait2_fade_out(subs[self._sub_index])
                        if started_1 or started_2:
                            return
            if node_type == "choice":
                # If already in choice overlay, do not reopen/reset it.
                if getattr(self, "_choice_overlay", False):
                    return
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
        dlg_style, name_style, dlg_font, name_font = self._effective_text_style_for_entry(entry)
        speaker = entry.get("speaker") or "角色"
        content = entry.get("content") or entry.get("title") or ""
        try:
            speaker = self._interpolate_dialogue_template(str(speaker))
            content = self._interpolate_dialogue_template(str(content))
        except Exception:
            pass
        bg_path = entry.get("background") or ""
        portrait_path = entry.get("portrait") or ""
        portrait2_path = entry.get("portrait2") or ""
        voice_path = entry.get("voice") or ""
        video_path = entry.get("video") or ""
        bgm_path = entry.get("bgm") or ""
        stop_bgm = bool(entry.get("stop_bgm"))
        hide_textbox = bool(entry.get("hide_textbox", False)) or bool(self._screenshot_hide_ui)
        portrait_fade = bool(entry.get("portrait_fade", False))
        portrait_fade_duration = entry.get("portrait_fade_duration", None)
        portrait2_fade = bool(entry.get("portrait2_fade", False))
        portrait2_fade_duration = entry.get("portrait2_fade_duration", None)
        bg_fade_duration = entry.get("bg_fade_duration", None)

        # draw video or background image
        if video_path:
            self._update_video(video_path, bool(entry.get("video_loop", False)), dt)
            if self._video_surface is not None:
                self.render_surface.blit(self._video_surface, (0, 0))
            else:
                if bg_path:
                    self._update_background(bg_path, fade_in=bool(entry.get("bg_fade_in", False)), duration=bg_fade_duration)
                    self._render_background(dt)
                else:
                    # video加载失败时至少不要复用上一个背景
                    self.render_surface.fill(self.bg_color)
        else:
            if self._video_clip:
                self._stop_video()
            self._update_background(bg_path, fade_in=bool(entry.get("bg_fade_in", False)), duration=bg_fade_duration)
            self._render_background(dt)

        # draw portraits (character sprites) if available
        self._draw_portrait2(portrait2_path, portrait2_fade, dt, fade_in_duration=portrait2_fade_duration)
        self._draw_portrait(portrait_path, portrait_fade, dt, fade_in_duration=portrait_fade_duration)

        # ensure bgm if provided and not explicitly stopped on this node
        if not stop_bgm:
            self._ensure_bgm(bgm_path, loop=bool(entry.get("bgm_loop", True)))

        if not hide_textbox:
            layout = self._active_ui_layout or {}
            text_frame_path = str(layout.get("text_frame_image") or "").strip()
            name_frame_path = str(layout.get("name_frame_image") or "").strip()
            try:
                text_frame_alpha = int(layout.get("text_frame_alpha", 255))
            except Exception:
                text_frame_alpha = 255
            try:
                name_frame_alpha = int(layout.get("name_frame_alpha", 255))
            except Exception:
                name_frame_alpha = 255
            text_frame_alpha = max(0, min(255, text_frame_alpha))
            name_frame_alpha = max(0, min(255, name_frame_alpha))

            # draw text box
            text_frame = None
            if text_frame_path:
                text_frame = self._load_ui_frame_surface(text_frame_path, (self.text_area.width, self.text_area.height), text_frame_alpha)
            if text_frame is not None:
                self.render_surface.blit(text_frame, (self.text_area.x, self.text_area.y))
            else:
                box_surface = pygame.Surface((self.text_area.width, self.text_area.height), pygame.SRCALPHA)
                box_surface.fill(self.box_color)
                self.render_surface.blit(box_surface, (self.text_area.x, self.text_area.y))

            # draw name box
            name_frame = None
            if name_frame_path:
                name_frame = self._load_ui_frame_surface(name_frame_path, (self.name_area.width, self.name_area.height), name_frame_alpha)
            if name_frame is not None:
                self.render_surface.blit(name_frame, (self.name_area.x, self.name_area.y))
            else:
                name_surface = pygame.Surface((self.name_area.width, self.name_area.height), pygame.SRCALPHA)
                name_surface.fill((0, 0, 0, 180))
                self.render_surface.blit(name_surface, (self.name_area.x, self.name_area.y))

            name_color = name_style.get("color", (220, 220, 220))
            name_ow = int(name_style.get("outline_width", 0) or 0)
            name_oc = name_style.get("outline_color", (0, 0, 0))
            name_surf = self._render_text_surface(str(speaker), name_font, name_color, name_ow, name_oc)
            left_pad = min(self.text_margin, max(4, self.name_area.width - 10))
            vert_pad = max(4, (self.name_area.height - name_surf.get_height()) // 2)
            self.render_surface.blit(name_surf, (self.name_area.x + left_pad, self.name_area.y + vert_pad))

            # render dialogue text with simple wrapping
            shown_text = content[: min(self.current_visible_len, len(content))] if content else ""
            self._render_wrapped_text(
                shown_text,
                self.text_area,
                dlg_font,
                dlg_style.get("color", (235, 235, 240)),
                int(dlg_style.get("outline_width", 0) or 0),
                dlg_style.get("outline_color", (0, 0, 0)),
            )

            # draw small triangle indicator when line finished
            if self.current_visible_len >= len(content):
                self._draw_indicator()

        if self.debug_hud:
            self._render_debug_hud(entry)

        # in-game HUD button group (mouse-only)
        # hide when textbox is hidden (node directive) or in screenshot mode
        if not hide_textbox:
            self._render_hud_buttons()

        if self._history_overlay:
            self._render_history_overlay()

        if self._exit_confirm_overlay:
            self._render_exit_confirm_overlay()

        if self._save_overlay or self._load_overlay or self._settings_overlay or self._help_overlay:
            self._render_overlay()
        if self._choice_overlay:
            self._render_choice_overlay()

    def _key_to_digit(self, key) -> int | None:
        key_map = {
            pygame.K_0: 0,
            pygame.K_1: 1,
            pygame.K_2: 2,
            pygame.K_3: 3,
            pygame.K_4: 4,
            pygame.K_5: 5,
            pygame.K_6: 6,
            pygame.K_7: 7,
            pygame.K_8: 8,
            pygame.K_9: 9,
            pygame.K_KP0: 0,
            pygame.K_KP1: 1,
            pygame.K_KP2: 2,
            pygame.K_KP3: 3,
            pygame.K_KP4: 4,
            pygame.K_KP5: 5,
            pygame.K_KP6: 6,
            pygame.K_KP7: 7,
            pygame.K_KP8: 8,
            pygame.K_KP9: 9,
        }
        return key_map.get(key)

    def _parse_hotkey_to_pygame_key(self, text: str) -> int | None:
        s = (text or "").strip().upper()
        if not s:
            return None
        # Function keys
        if s.startswith("F") and s[1:].isdigit():
            try:
                n = int(s[1:])
            except Exception:
                n = 1
            return getattr(pygame, f"K_F{n}", None)
        # Single letter
        if len(s) == 1 and "A" <= s <= "Z":
            return getattr(pygame, f"K_{s.lower()}", None)
        # Common names
        aliases = {
            "HELP": pygame.K_F1,
            "H": pygame.K_h,
        }
        return aliases.get(s)

    def _toggle_help_overlay(self):
        self._help_overlay = not self._help_overlay
        if self._help_overlay:
            self._overlay_return_mode = self.mode
            self._save_overlay = False
            self._load_overlay = False
            self._settings_overlay = False
            self._choice_overlay = False
            self._history_overlay = False
            self._exit_confirm_overlay = False
            self._overlay_scroll_offset = 0
            self._overlay_dragging_slider = None

    def _open_exit_confirm(self):
        if self.mode != "game":
            return
        self._overlay_return_mode = self.mode
        self._exit_confirm_overlay = True
        self._exit_confirm_choice = 1
        self._save_overlay = False
        self._load_overlay = False
        self._settings_overlay = False
        self._choice_overlay = False
        self._history_overlay = False
        self._help_overlay = False

    def _render_history_overlay(self):
        if self._function_menus_enabled:
            self._render_function_menu_history_overlay()
            return

        # legacy overlays: ensure mouse hit boxes are cleared
        self._overlay_hover = None
        self._overlay_hitboxes = {}
        self._overlay_slot_hitboxes = []

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
        menu_font = self._load_font(max(8, int(20 * (getattr(self, "_menu_option_scale", 1.0) or 1.0))))
        title_color = self._menu_title_color
        option_color = self._menu_option_color
        hover_color = getattr(self, "_menu_option_hover_color", option_color)

        if self._menu_title_image_surface:
            img = self._menu_title_image_surface
            x = self._menu_title_image_pos[0]
            y = self._menu_title_image_pos[1]
            self.render_surface.blit(img, (x - img.get_width() // 2, y - img.get_height() // 2))
        else:
            title_font = self._load_font(max(10, int(36 * (getattr(self, "_menu_title_scale", 1.0) or 1.0))), bold=True)
            title_surf = title_font.render(title, True, title_color)
            self.render_surface.blit(title_surf, (title_pos[0], title_pos[1]))

        start_x, start_y = self._menu_option_pos
        spacing = int(getattr(self, "_menu_option_spacing", 10) or 10)
        zoom = float(getattr(self, "_menu_option_selected_zoom", 1.08) or 1.08)

        # Precompute stable layout positions using UNZOOMED sizes.
        layout: list[dict] = []
        cur_y = int(start_y)
        for idx, item in enumerate(self._menu_items):
            if not isinstance(item, dict):
                continue
            style = str(item.get("style") or "text")
            action = str(item.get("action") or "")
            label = str(item.get("label", ""))

            raw = None
            base_w = 0
            base_h = 0
            img_scale = None
            if style == "image":
                raw = (getattr(self, "_menu_option_image_surfaces", {}) or {}).get(action)
                if raw is not None:
                    img_scale = item.get("image_scale", None)
                    if img_scale is None:
                        try:
                            img_scale = 20.0 / max(1.0, float(raw.get_height()))
                        except Exception:
                            img_scale = 1.0
                    else:
                        try:
                            img_scale = float(img_scale)
                        except Exception:
                            img_scale = 1.0
                    img_scale = max(0.1, min(5.0, float(img_scale)))
                    final_scale = float(self._menu_option_scale) * float(img_scale)
                    base_w = max(1, int(raw.get_width() * final_scale))
                    base_h = max(1, int(raw.get_height() * final_scale))
                else:
                    style = "text"  # fallback if missing image

            if style != "image":
                base_w = 0
                base_h = int(menu_font.get_linesize())

            layout.append({
                "idx": idx,
                "style": style,
                "action": action,
                "label": label,
                "x": int(start_x),
                "y": int(cur_y),
                "w": int(base_w),
                "h": int(base_h),
                "raw": raw,
                "img_scale": img_scale,
            })

            cur_y += int(base_h) + spacing

        # Draw items with stable layout; selected image is scaled around its CENTER.
        if bool(getattr(self, "_menu_option_indicator", False)) and layout:
            sel_item = None
            for it in layout:
                if int(it.get("idx", -1)) == int(self._menu_selected):
                    sel_item = it
                    break
            if sel_item is not None:
                x0 = int(sel_item.get("x", start_x))
                y0 = int(sel_item.get("y", start_y))
                h0 = int(sel_item.get("h", int(menu_font.get_linesize())))
                scale0 = float(getattr(self, "_menu_option_scale", 1.0) or 1.0)
                gap = max(4, int(12 * scale0))
                cy = y0 + h0 // 2

                ind_raw = getattr(self, "_menu_option_indicator_image_surface", None)
                ind_scale = float(getattr(self, "_menu_option_indicator_image_scale", 1.0) or 1.0)
                ind_scale = max(0.1, min(5.0, float(ind_scale)))
                if ind_raw is not None:
                    final_scale = max(0.1, float(scale0) * float(ind_scale))
                    w = max(1, int(ind_raw.get_width() * final_scale))
                    h = max(1, int(ind_raw.get_height() * final_scale))
                    try:
                        img = pygame.transform.smoothscale(ind_raw, (w, h))
                    except Exception:
                        img = pygame.transform.scale(ind_raw, (w, h))
                    dx = x0 - gap - w
                    dy = cy - h // 2
                    self.render_surface.blit(img, (dx, dy))
                else:
                    aw = max(6, int(14 * scale0))
                    ah = max(8, int(18 * scale0))
                    tip_x = x0 - gap
                    base_x = tip_x - aw
                    pts = [(tip_x, cy), (base_x, cy - ah // 2), (base_x, cy + ah // 2)]
                    try:
                        pygame.draw.polygon(self.render_surface, option_color, pts)
                    except Exception:
                        pass

        for it in layout:
            idx = int(it["idx"])
            sel = idx == self._menu_selected
            style = str(it["style"])
            x = int(it["x"])
            y = int(it["y"])

            # keep hitboxes aligned with original menu item indices
            if not self._menu_item_hitboxes or len(self._menu_item_hitboxes) != len(self._menu_items):
                self._menu_item_hitboxes = [None] * len(self._menu_items)

            if style == "image" and it.get("raw") is not None:
                raw = it["raw"]
                base_w = int(it["w"])
                base_h = int(it["h"])
                z = float(zoom if sel else 1.0)
                w = max(1, int(base_w * z))
                h = max(1, int(base_h * z))
                try:
                    img = pygame.transform.smoothscale(raw, (w, h))
                except Exception:
                    img = pygame.transform.scale(raw, (w, h))
                dx = x - (w - base_w) // 2
                dy = y - (h - base_h) // 2
                self.render_surface.blit(img, (dx, dy))
                if 0 <= idx < len(self._menu_item_hitboxes):
                    self._menu_item_hitboxes[idx] = pygame.Rect(dx, dy, w, h)
                continue

            # text style (existing behavior)
            base = option_color
            active = hover_color if sel else base
            color = active if sel else (int(active[0] * 0.75), int(active[1] * 0.75), int(active[2] * 0.75))
            surf = menu_font.render(str(it.get("label") or ""), True, color)
            self.render_surface.blit(surf, (x, y))
            if 0 <= idx < len(self._menu_item_hitboxes):
                self._menu_item_hitboxes[idx] = pygame.Rect(x, y, surf.get_width(), surf.get_height())

        hint = "↑↓选择, 回车确认, ESC退出"
        hint_surf = self.font.render(hint, True, (200, 200, 200))
        self.render_surface.blit(hint_surf, (60, self.render_size[1] - 60))

    def _render_wrapped_text(self, text: str, area: pygame.Rect, font, color, outline_width: int = 0, outline_color=(0, 0, 0)):
        words = list(text)
        lines = []
        current = ""
        try:
            ow = max(0, int(outline_width))
        except Exception:
            ow = 0
        for ch in words:
            test = current + ch
            avail = area.width - self.text_margin * 2 - ow * 2
            if font.size(test)[0] > max(10, avail):
                lines.append(current)
                current = ch
            else:
                current = test
        if current:
            lines.append(current)

        y = area.y + self.text_margin
        for line in lines:
            surf = self._render_text_surface(line, font, color, ow, outline_color)
            self.render_surface.blit(surf, (area.x + self.text_margin - ow, y - ow))
            y += font.get_linesize()

    def _update_typing(self, dt: float):
        entry = self._current_entry()
        if not entry:
            return
        content = entry.get("content") or entry.get("title") or ""
        try:
            content = self._interpolate_dialogue_template(str(content))
        except Exception:
            pass
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
        try:
            content = self._interpolate_dialogue_template(str(content))
        except Exception:
            pass
        self.current_visible_len = len(content)
        self.typing_progress = len(content)

        # auto-next 倒计时期间：允许快速显示文字，但禁止推进到下一句/下一节点
        if self._auto_next_lock_active():
            self._fast_skip_timer = 0.0
            return

        self._fast_skip_timer += dt
        if self._fast_skip_timer >= self._fast_skip_interval:
            self._fast_skip_timer = 0.0
            self.advance_dialogue()

    def _auto_next_lock_active(self) -> bool:
        try:
            return self._auto_next_remaining is not None and float(self._auto_next_remaining) > 0.0
        except Exception:
            return False

    def _reveal_current_text(self):
        entry = self._current_entry()
        if not entry:
            return
        content = entry.get("content") or entry.get("title") or ""
        try:
            content = self._interpolate_dialogue_template(str(content))
        except Exception:
            pass
        self.current_visible_len = len(content)
        self.typing_progress = len(content)

    def _update_auto_next(self, dt: float):
        if self.mode != "game":
            return
        # overlays pause countdown too
        if self._save_overlay or self._load_overlay or self._settings_overlay or self._choice_overlay or self._history_overlay or self._help_overlay or self._exit_confirm_overlay:
            return
        if self._pending_sub_advance:
            return
        if self._auto_next_remaining is None:
            return

        try:
            self._auto_next_remaining = float(self._auto_next_remaining) - float(dt)
        except Exception:
            self._auto_next_remaining = None
            return

        if self._auto_next_remaining > 0.0:
            return

        # time's up: reveal then advance immediately
        self._auto_next_remaining = None
        self._reveal_current_text()
        self.advance_dialogue()

    def _reset_typing_state(self):
        self.current_visible_len = 0
        self.typing_progress = 0.0
        self._triangle_phase = 0.0
        if self.fast_skip:
            entry = self._current_entry()
            content = (entry.get("content") or entry.get("title") or "") if entry else ""
            try:
                content = self._interpolate_dialogue_template(str(content))
            except Exception:
                pass
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
            # protected vars persist across save/load/new-game resets
            try:
                dest_name = str(dest)
                if dest_name in (getattr(self, "_protected_vars", set()) or set()):
                    self._persistent_vars[dest_name] = float(result)
                    self._persistent_vars_dirty = True
            except Exception:
                pass

    def _on_enter_node(self, skip_media: bool = False, apply_var_ops: bool = True):
        entry = self._current_entry()
        # reset auto-next countdown whenever we enter a node/sub-dialogue
        self._auto_next_remaining = None
        if entry and self.graph_mode and entry.get("node_type") == "text":
            try:
                secs = float(entry.get("auto_next_seconds") or 0.0)
                if secs > 0:
                    self._auto_next_remaining = max(0.0, min(600.0, secs))
            except Exception:
                self._auto_next_remaining = None
        if apply_var_ops:
            self._apply_var_ops(entry)

        # 功能节点：仅在“进入宿主节点”时触发一次（文本节点的后续子对白不重复触发）
        if self.graph_mode and self.current_node_id is not None and self._sub_index == 0:
            fn_key = self.current_node_id
            if self._function_played_key != fn_key:
                self._trigger_function_nodes_for_host(fn_key, entry)
                self._function_played_key = fn_key
        stop_bgm = bool(entry.get("stop_bgm")) if entry else False
        bgm = entry.get("bgm") or "" if entry else ""
        voice = entry.get("voice") or "" if entry else ""
        sfx = entry.get("sfx") or "" if entry else ""
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

        # per-sub UI：即使 skip_media=True（避免重复刷新 BGM），也需要允许切换 UI 布局。
        self._apply_ui_file(ui_file)

        # one-shot portrait bounce per current entry (node or sub-dialogue).
        # Use a key to avoid duplicate triggering if _on_enter_node is called repeatedly for the same entry.
        if entry:
            bounce_key = (self.current_node_id, self._sub_index) if self.graph_mode else self.current_index
            if bool(entry.get("portrait_bounce", False)) and self._portrait_bounce_played_key != bounce_key:
                self._start_portrait_bounce(is_second=False)
                self._portrait_bounce_played_key = bounce_key
            if bool(entry.get("portrait2_bounce", False)) and self._portrait2_bounce_played_key != bounce_key:
                self._start_portrait_bounce(is_second=True)
                self._portrait2_bounce_played_key = bounce_key

        # avoid replaying voice if already played for this index
        voice_key = (self.current_node_id, self._sub_index) if self.graph_mode else self.current_index
        if self._voice_played_index != voice_key:
            self._schedule_voice(voice)
            self._voice_played_index = voice_key

        sfx_key = (self.current_node_id, self._sub_index) if self.graph_mode else self.current_index
        if self._sfx_played_index != sfx_key:
            self._schedule_sfx(sfx)
            self._sfx_played_index = sfx_key

        self._append_history(entry)
        # 预取下一个节点/对白的素材，进一步降低跳转卡顿
        self._prefetch_next_assets()

        # Auto-enter behavior for skip-dialogue choice/condition nodes.
        # Important: avoid triggering during load/restore where apply_var_ops=False.
        if apply_var_ops and entry and self.graph_mode:
            try:
                ntype = str(entry.get("node_type") or "text").lower()
            except Exception:
                ntype = "text"
            if ntype == "choice" and bool(entry.get("skip_dialogue", False)):
                if not getattr(self, "_choice_overlay", False):
                    self._open_choice_overlay(entry)
                return
            if ntype == "condition" and bool(entry.get("skip_dialogue", False)):
                self._resolve_condition_branch(entry)
                return

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

    def _update_background(self, bg_path: str, fade_in: bool, duration: float | None = None):
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
            # allow per-node override for fade duration
            if duration is not None:
                try:
                    d = float(duration)
                    self._bg_fade_duration = max(0.0, min(10.0, d))
                except Exception:
                    pass
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

    def _draw_portrait(self, portrait_path: str, fade_in: bool, dt: float, fade_in_duration: float | None = None):
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
                self._portrait_cache[abs_path] = img
            except Exception:
                return

        raw_img = self._portrait_cache[abs_path]

        # Determine base size (independent from portrait_scale).
        base_w = None
        base_h = None
        psz = getattr(self, "portrait_size", None)
        if isinstance(psz, (list, tuple)) and len(psz) == 2:
            try:
                w0 = int(psz[0])
                h0 = int(psz[1])
                if w0 > 0 and h0 > 0:
                    base_w, base_h = w0, h0
            except Exception:
                base_w, base_h = None, None

        if base_w is None or base_h is None:
            max_w = int(self.render_size[0] * 0.35)
            max_h = int(self.render_size[1] * 0.7)
            rw, rh = raw_img.get_size()
            fit_scale = min(max_w / max(1, rw), max_h / max(1, rh), 1.0)
            base_w = max(1, int(rw * fit_scale))
            base_h = max(1, int(rh * fit_scale))

        scale = getattr(self, "portrait_scale", 1.0) or 1.0
        scale = max(0.1, min(5.0, float(scale)))
        final_w = max(1, int(base_w * scale))
        final_h = max(1, int(base_h * scale))

        # Always scale from the original to avoid quality loss from double-scaling.
        key = (abs_path, final_w, final_h)
        target_img = self._portrait_scaled_cache.get(key)
        if target_img is None:
            target_img = pygame.transform.smoothscale(raw_img, (final_w, final_h))
            self._portrait_scaled_cache[key] = target_img

        # manage fade state
        if self._portrait_current_path != abs_path:
            self._portrait_current_path = abs_path
            self._portrait_fadeout_active = False
            self._portrait_fade_start_alpha = 255
            if fade_in:
                if fade_in_duration is not None:
                    try:
                        d = float(fade_in_duration)
                        self._portrait_fade_in_duration = max(0.0, min(10.0, d))
                    except Exception:
                        pass
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

        # IMPORTANT: fade-out has priority (fix: fade-in + fade-out on same entry should still advance)
        if self._portrait_fadeout_active and self._portrait_surface is not None:
            self._portrait_fade_time += dt
            progress = min(1.0, self._portrait_fade_time / max(0.001, self._portrait_fade_out_duration))
            start_alpha = self._portrait_fade_start_alpha if self._portrait_fade_start_alpha is not None else 255
            self._portrait_fade_alpha = int(start_alpha * max(0.0, 1.0 - progress))
            img = self._portrait_surface.copy()
            img.set_alpha(self._portrait_fade_alpha)
            if progress >= 1.0:
                self._portrait_surface = None
                self._portrait_target_surface = None
                self._portrait_current_path = None
                self._portrait_fadeout_active = False
                self._on_sub_fade_out_done()
        elif fade_in and self._portrait_surface is not None:
            self._portrait_fade_time += dt
            progress = min(1.0, self._portrait_fade_time / max(0.001, self._portrait_fade_in_duration))
            self._portrait_fade_alpha = int(self._portrait_target_alpha * progress)
            img = self._portrait_surface.copy()
            img.set_alpha(self._portrait_fade_alpha)
        else:
            img = self._portrait_surface if self._portrait_surface is not None else target_img

        if img is None:
            return
        bounce_offset_y = self._update_bounce(dt, is_second=False)

        if self.portrait_pos:
            x = int(self.portrait_pos[0] - img.get_width() / 2)
            y = int(self.portrait_pos[1] - img.get_height() / 2) + bounce_offset_y
        else:
            x = self.render_size[0] - img.get_width() - 40
            y = self.render_size[1] - img.get_height() - 60 + bounce_offset_y
        self.render_surface.blit(img, (x, y))

    def _maybe_start_portrait_fade_out(self, sub_entry: dict) -> bool:
        if not sub_entry or not sub_entry.get("portrait_fade_out"):
            return False
        if self._portrait_fadeout_active:
            return True
        if self._portrait_surface is None:
            return False
        try:
            d = float(sub_entry.get("portrait_fade_out_duration", self._portrait_fade_out_duration))
            self._portrait_fade_out_duration = max(0.0, min(10.0, d))
        except Exception:
            pass
        self._portrait_fadeout_active = True
        current_alpha = self._portrait_surface.get_alpha()
        self._portrait_fade_start_alpha = current_alpha if current_alpha is not None else 255
        self._portrait_fade_time = 0.0
        self._pending_sub_advance_waiting += 1
        return True

    def _on_sub_fade_out_done(self):
        if self._pending_sub_advance_waiting > 0:
            self._pending_sub_advance_waiting -= 1
        if self._pending_sub_advance_waiting <= 0:
            self._pending_sub_advance_waiting = 0
            self._pending_sub_advance = True

    def _maybe_start_portrait2_fade_out(self, sub_entry: dict) -> bool:
        if not sub_entry or not sub_entry.get("portrait2_fade_out"):
            return False
        if self._portrait2_fadeout_active:
            return True
        if self._portrait2_surface is None:
            return False
        try:
            d = float(sub_entry.get("portrait2_fade_out_duration", self._portrait2_fade_out_duration))
            self._portrait2_fade_out_duration = max(0.0, min(10.0, d))
        except Exception:
            pass
        self._portrait2_fadeout_active = True
        current_alpha = self._portrait2_surface.get_alpha()
        self._portrait2_fade_start_alpha = current_alpha if current_alpha is not None else 255
        self._portrait2_fade_time = 0.0
        self._pending_sub_advance_waiting += 1
        return True

    def _draw_portrait2(self, portrait_path: str, fade_in: bool, dt: float, fade_in_duration: float | None = None):
        # allow fade-out to continue even if next sub has no portrait2
        if not portrait_path:
            if not self._portrait2_fadeout_active:
                self._portrait2_surface = None
                self._portrait2_target_surface = None
                self._portrait2_current_path = None
                return
            abs_path = self._portrait2_current_path
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
                self._portrait_cache[abs_path] = img
            except Exception:
                return

        raw_img = self._portrait_cache[abs_path]

        # Determine base size (independent from portrait2_scale).
        base_w = None
        base_h = None
        psz = getattr(self, "portrait2_size", None)
        if isinstance(psz, (list, tuple)) and len(psz) == 2:
            try:
                w0 = int(psz[0])
                h0 = int(psz[1])
                if w0 > 0 and h0 > 0:
                    base_w, base_h = w0, h0
            except Exception:
                base_w, base_h = None, None

        if base_w is None or base_h is None:
            max_w = int(self.render_size[0] * 0.35)
            max_h = int(self.render_size[1] * 0.7)
            rw, rh = raw_img.get_size()
            fit_scale = min(max_w / max(1, rw), max_h / max(1, rh), 1.0)
            base_w = max(1, int(rw * fit_scale))
            base_h = max(1, int(rh * fit_scale))

        scale = getattr(self, "portrait2_scale", 1.0) or 1.0
        scale = max(0.1, min(5.0, float(scale)))
        final_w = max(1, int(base_w * scale))
        final_h = max(1, int(base_h * scale))

        key = (abs_path, final_w, final_h)
        target_img = self._portrait2_scaled_cache.get(key)
        if target_img is None:
            target_img = pygame.transform.smoothscale(raw_img, (final_w, final_h))
            self._portrait2_scaled_cache[key] = target_img

        # manage fade state
        if self._portrait2_current_path != abs_path:
            self._portrait2_current_path = abs_path
            self._portrait2_fadeout_active = False
            self._portrait2_fade_start_alpha = 255
            if fade_in:
                if fade_in_duration is not None:
                    try:
                        d = float(fade_in_duration)
                        self._portrait2_fade_in_duration = max(0.0, min(10.0, d))
                    except Exception:
                        pass
                self._portrait2_target_surface = target_img
                self._portrait2_surface = target_img.copy()
                self._portrait2_fade_alpha = 0
                self._portrait2_target_alpha = 255
                self._portrait2_fade_time = 0.0
            else:
                self._portrait2_surface = target_img
                self._portrait2_target_surface = None
                self._portrait2_fade_alpha = 255
                self._portrait2_target_alpha = 255
                self._portrait2_fade_time = 0.0

        # IMPORTANT: fade-out has priority
        if self._portrait2_fadeout_active and self._portrait2_surface is not None:
            self._portrait2_fade_time += dt
            progress = min(1.0, self._portrait2_fade_time / max(0.001, self._portrait2_fade_out_duration))
            start_alpha = self._portrait2_fade_start_alpha if self._portrait2_fade_start_alpha is not None else 255
            self._portrait2_fade_alpha = int(start_alpha * max(0.0, 1.0 - progress))
            img = self._portrait2_surface.copy()
            img.set_alpha(self._portrait2_fade_alpha)
            if progress >= 1.0:
                self._portrait2_surface = None
                self._portrait2_target_surface = None
                self._portrait2_current_path = None
                self._portrait2_fadeout_active = False
                self._on_sub_fade_out_done()
        elif fade_in and self._portrait2_surface is not None:
            self._portrait2_fade_time += dt
            progress = min(1.0, self._portrait2_fade_time / max(0.001, self._portrait2_fade_in_duration))
            self._portrait2_fade_alpha = int(self._portrait2_target_alpha * progress)
            img = self._portrait2_surface.copy()
            img.set_alpha(self._portrait2_fade_alpha)
        else:
            img = self._portrait2_surface if self._portrait2_surface is not None else target_img

        if img is None:
            return
        bounce_offset_y = self._update_bounce(dt, is_second=True)

        if self.portrait2_pos:
            x = int(self.portrait2_pos[0] - img.get_width() / 2)
            y = int(self.portrait2_pos[1] - img.get_height() / 2) + bounce_offset_y
        else:
            x = 40
            y = self.render_size[1] - img.get_height() - 60 + bounce_offset_y
        self.render_surface.blit(img, (x, y))

    def _start_portrait_bounce(self, is_second: bool):
        # Only start if currently visible (or will be visible this frame).
        if is_second:
            self._portrait2_bounce_active = True
            self._portrait2_bounce_time = 0.0
        else:
            self._portrait_bounce_active = True
            self._portrait_bounce_time = 0.0

    def _update_bounce(self, dt: float, is_second: bool) -> int:
        if is_second:
            if not self._portrait2_bounce_active:
                return 0
            self._portrait2_bounce_time += max(0.0, float(dt))
            duration = max(0.01, float(self._portrait2_bounce_duration))
            p = min(1.0, self._portrait2_bounce_time / duration)
            amp = int(self._portrait2_bounce_amplitude)
            offset = -int(round(amp * math.sin(math.pi * p)))
            if p >= 1.0:
                self._portrait2_bounce_active = False
            return offset

        if not self._portrait_bounce_active:
            return 0
        self._portrait_bounce_time += max(0.0, float(dt))
        duration = max(0.01, float(self._portrait_bounce_duration))
        p = min(1.0, self._portrait_bounce_time / duration)
        amp = int(self._portrait_bounce_amplitude)
        offset = -int(round(amp * math.sin(math.pi * p)))
        if p >= 1.0:
            self._portrait_bounce_active = False
        return offset

    def _resolve_path(self, path_str: str) -> Path:
        p = Path(path_str)
        if p.is_absolute():
            return p
        base = self.project_path.parent if self.project_path else Path.cwd()
        return (base / p).resolve()

    def _load_ui_frame_surface(self, path_str: str, size: tuple[int, int], alpha: int) -> pygame.Surface | None:
        """Load a UI frame image (textbox/namebox), scale to size, apply alpha, and cache."""
        if not path_str:
            return None
        try:
            abs_path = self._resolve_path(path_str)
            if not abs_path.exists():
                return None
            w, h = int(size[0]), int(size[1])
            w = max(1, w)
            h = max(1, h)
            a = max(0, min(255, int(alpha)))
            key = (abs_path, w, h, a)
            if key in self._ui_frame_cache:
                return self._ui_frame_cache[key]

            surf = pygame.image.load(str(abs_path)).convert_alpha()
            if surf.get_width() != w or surf.get_height() != h:
                surf = pygame.transform.smoothscale(surf, (w, h))
            surf.set_alpha(a)
            self._ui_frame_cache[key] = surf
            return surf
        except Exception:
            return None

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
        if isinstance(val, str):
            s = val.strip()
            if len(s) == 7 and s.startswith("#"):
                try:
                    r = int(s[1:3], 16)
                    g = int(s[3:5], 16)
                    b = int(s[5:7], 16)
                    return (r, g, b)
                except Exception:
                    return default
        return default

    def _current_entry(self) -> dict:
        if self.graph_mode:
            if self.current_node_id is None:
                return {}
            node = self.nodes_map.get(self.current_node_id, {}) or {}
            try:
                ntype = str(node.get("node_type") or "text").lower()
            except Exception:
                ntype = "text"
            if ntype in {"choice", "condition"} and bool(node.get("skip_dialogue", False)):
                # Skip dialogue presentation for choice/condition nodes (designer option).
                masked = dict(node)
                masked["speaker"] = ""
                masked["content"] = ""
                masked["portrait"] = ""
                masked["portrait2"] = ""
                masked["voice"] = ""
                masked["sfx"] = ""
                masked["hide_textbox"] = True
                masked["portrait_fade"] = False
                masked["portrait2_fade"] = False
                masked["portrait_bounce"] = False
                masked["portrait2_bounce"] = False
                return masked
            if node.get("node_type") == "text":
                subs = node.get("sub_dialogues") or []
                if subs and 0 <= self._sub_index < len(subs):
                    sub = subs[self._sub_index]
                    merged = dict(node)
                    sub_has_style_enabled = isinstance(sub, dict) and ("text_style_enabled" in sub)
                    sub_has_styles = isinstance(sub, dict) and ("text_styles" in sub)
                    merged.update({
                        "speaker": sub.get("speaker", merged.get("speaker", "")),
                        "content": sub.get("text", merged.get("content", "")),
                        "portrait": sub.get("portrait", merged.get("portrait", "")),
                        "portrait2": sub.get("portrait2", merged.get("portrait2", "")),
                        "voice": sub.get("voice", merged.get("voice", "")),
                        "sfx": sub.get("sfx", merged.get("sfx", "")),
                        "text_style_enabled": (
                            bool(sub.get("text_style_enabled", False))
                            if sub_has_style_enabled
                            else bool(merged.get("text_style_enabled", False))
                        ),
                        "text_styles": (
                            sub.get("text_styles")
                            if sub_has_styles and isinstance(sub.get("text_styles"), dict)
                            else (merged.get("text_styles") if isinstance(merged.get("text_styles"), dict) else {})
                        ),
                        # 变量处理：
                        # - 子对话可独立存储并在进入该子对话时执行；
                        # - 兼容旧数据：若子对话未配置 var_ops，则仅在第 1 条子对话时回退到节点级 var_ops（避免多条子对话重复执行）。
                        "var_ops": (
                            sub.get("var_ops")
                            if isinstance(sub.get("var_ops"), list)
                            else (merged.get("var_ops") if self._sub_index == 0 and isinstance(merged.get("var_ops"), list) else [])
                        ),
                        # UI 配置迁移：优先使用子对话的 ui_file；若未配置则回退到节点级（兼容旧数据）
                        "ui_file": sub.get("ui_file") or merged.get("ui_file", ""),
                        "hide_textbox": bool(sub.get("hide_textbox", False)),
                        "portrait_fade": bool(sub.get("portrait_fade", False)),
                        "portrait_fade_out": bool(sub.get("portrait_fade_out", False)),
                        "portrait2_fade": bool(sub.get("portrait2_fade", False)),
                        "portrait2_fade_out": bool(sub.get("portrait2_fade_out", False)),
                        "portrait_bounce": bool(sub.get("portrait_bounce", False)),
                        "portrait2_bounce": bool(sub.get("portrait2_bounce", False)),
                        "portrait_fade_duration": sub.get("portrait_fade_duration", None),
                        "portrait_fade_out_duration": sub.get("portrait_fade_out_duration", None),
                        "portrait2_fade_duration": sub.get("portrait2_fade_duration", None),
                        "portrait2_fade_out_duration": sub.get("portrait2_fade_out_duration", None),
                        "auto_next_seconds": sub.get("auto_next_seconds", None),
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
        # function nodes are not part of the traversal graph; they are bound to host nodes.
        function_nodes = [n for n in nodes if isinstance(n, dict) and str(n.get("node_type", "")).lower() == "function"]
        self._function_nodes_by_host = {}
        for fn in function_nodes:
            host = fn.get("bound_to")
            if host is None:
                continue
            self._function_nodes_by_host.setdefault(host, []).append(fn)

        graph_nodes = [n for n in nodes if isinstance(n, dict) and n.get("id") is not None and str(n.get("node_type", "")).lower() != "function"]
        self.nodes_map = {n.get("id"): n for n in graph_nodes if n.get("id") is not None}
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

        # 预览：从指定节点开始（仅当节点存在时生效）
        if self._preview_start_node_id is not None and self.nodes_map:
            requested = self._preview_start_node_id
            chosen = None
            if requested in self.nodes_map:
                chosen = requested
            else:
                try:
                    req_int = int(requested)
                    if req_int in self.nodes_map:
                        chosen = req_int
                except Exception:
                    pass
                if chosen is None:
                    req_str = str(requested)
                    if req_str in self.nodes_map:
                        chosen = req_str
            if chosen is not None:
                self.current_node_id = chosen
        self._sub_index = 0
        # 预热节点素材，减少首次进入卡顿
        self._warm_caches_from_flow(nodes, preload_limit=100)

    def _process_main_thread_script_actions(self):
        # Execute queued actions produced by function-node scripts.
        try:
            with self._script_queue_lock:
                if not self._script_main_queue:
                    return
                tasks = list(self._script_main_queue)
                self._script_main_queue.clear()
        except Exception:
            return
        for fn in tasks:
            try:
                fn()
            except Exception as exc:
                print(f"[功能节点] 主线程任务执行失败: {exc}")

    def _enqueue_main_thread_action(self, fn):
        try:
            with self._script_queue_lock:
                self._script_main_queue.append(fn)
        except Exception:
            pass

    class _FunctionScriptAPI:
        def __init__(self, runtime: "VNGameRuntime", host_node_id, function_node: dict):
            self._rt = runtime
            self.host_node_id = host_node_id
            self.function_node = function_node
            self.fs = VNGameRuntime._FunctionFSAPI(runtime)
            self.ui = VNGameRuntime._FunctionUIAPI(runtime)
            self.fx = VNGameRuntime._FunctionFXAPI(runtime)
            self.audio = VNGameRuntime._FunctionAudioAPI(runtime)
            self.time = VNGameRuntime._FunctionTimeAPI(runtime, host_node_id)

        def log(self, *args):
            try:
                nid = self.function_node.get("id")
            except Exception:
                nid = None
            prefix = f"[功能节点 host={self.host_node_id} fn={nid}]"
            try:
                print(prefix, *args)
            except Exception:
                print(prefix)

        def set_var(self, name, value):
            key = str(name)
            self._rt._enqueue_main_thread_action(lambda: self._rt.variables.__setitem__(key, value))

        def get_var(self, name, default=None):
            try:
                return self._rt.variables.get(str(name), default)
            except Exception:
                return default

        def request_exit(self):
            self._rt._enqueue_main_thread_action(self._rt.quit_game)

        def request_restart(self, reset_globals: bool = False):
            self._rt._enqueue_main_thread_action(lambda: self._rt._start_new_game(reset_globals=bool(reset_globals)))

    class _FunctionFSAPI:
        """A capability-based filesystem API for function-node scripts.

        - Safe mode (default): restricts all operations to runtime._function_fs_root
        - Unsafe mode: allows absolute paths and escaping root
        """

        def __init__(self, runtime: "VNGameRuntime"):
            self._rt = runtime

        def _allow_unsafe(self) -> bool:
            return bool(getattr(self._rt, "_allow_unsafe_function_scripts", False))

        def _root(self) -> Path:
            try:
                return Path(getattr(self._rt, "_function_fs_root", getattr(self._rt, "_project_dir", Path.cwd()))).resolve()
            except Exception:
                return Path.cwd().resolve()

        def _resolve(self, user_path: str | Path) -> Path:
            p = Path(user_path)
            if p.is_absolute():
                if self._allow_unsafe():
                    return p.resolve()
                raise PermissionError("Absolute paths are not allowed in safe mode")
            resolved = (self._root() / p).resolve()
            if self._allow_unsafe():
                return resolved
            try:
                resolved.relative_to(self._root())
            except Exception:
                raise PermissionError("Path escapes function_script_fs_root")
            return resolved

        def abspath(self, user_path: str | Path) -> str:
            return str(self._resolve(user_path))

        def exists(self, user_path: str | Path) -> bool:
            try:
                return self._resolve(user_path).exists()
            except Exception:
                return False

        def is_file(self, user_path: str | Path) -> bool:
            try:
                return self._resolve(user_path).is_file()
            except Exception:
                return False

        def is_dir(self, user_path: str | Path) -> bool:
            try:
                return self._resolve(user_path).is_dir()
            except Exception:
                return False

        def mkdir(self, user_path: str | Path, parents: bool = True, exist_ok: bool = True) -> str:
            p = self._resolve(user_path)
            p.mkdir(parents=bool(parents), exist_ok=bool(exist_ok))
            return str(p)

        def listdir(self, user_path: str | Path = ".", pattern: str | None = None, recursive: bool = False) -> list[str]:
            base = self._resolve(user_path)
            if not base.exists() or not base.is_dir():
                return []
            if pattern and recursive:
                return [str(p) for p in base.rglob(pattern)]
            if pattern:
                return [str(p) for p in base.glob(pattern)]
            return [str(p) for p in base.iterdir()]

        def glob(self, pattern: str) -> list[str]:
            # safe mode: glob is relative to root
            if self._allow_unsafe() and ("\\" in pattern or ":" in pattern or pattern.startswith("/")):
                return [str(Path(p)) for p in glob.glob(pattern, recursive=True)]
            base = self._root()
            return [str(Path(p)) for p in glob.glob(str((base / pattern).resolve()), recursive=True)]

        def read_text(self, user_path: str | Path, encoding: str = "utf-8") -> str:
            p = self._resolve(user_path)
            return p.read_text(encoding=encoding)

        def write_text(self, user_path: str | Path, content: str, encoding: str = "utf-8", append: bool = False) -> str:
            p = self._resolve(user_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            mode = "a" if append else "w"
            with open(p, mode, encoding=encoding) as f:
                f.write(str(content))
            return str(p)

        def read_bytes(self, user_path: str | Path) -> bytes:
            p = self._resolve(user_path)
            return p.read_bytes()

        def write_bytes(self, user_path: str | Path, content: bytes, append: bool = False) -> str:
            p = self._resolve(user_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            mode = "ab" if append else "wb"
            with open(p, mode) as f:
                f.write(content)
            return str(p)

        def copy(self, src: str | Path, dst: str | Path, overwrite: bool = True) -> str:
            s = self._resolve(src)
            d = self._resolve(dst)
            d.parent.mkdir(parents=True, exist_ok=True)
            if d.exists() and not overwrite:
                raise FileExistsError(str(d))
            shutil.copy2(s, d)
            return str(d)

        def copytree(self, src: str | Path, dst: str | Path, overwrite: bool = True) -> str:
            s = self._resolve(src)
            d = self._resolve(dst)
            if d.exists() and overwrite:
                shutil.rmtree(d)
            shutil.copytree(s, d)
            return str(d)

        def move(self, src: str | Path, dst: str | Path, overwrite: bool = True) -> str:
            s = self._resolve(src)
            d = self._resolve(dst)
            d.parent.mkdir(parents=True, exist_ok=True)
            if d.exists() and overwrite:
                if d.is_dir():
                    shutil.rmtree(d)
                else:
                    d.unlink(missing_ok=True)
            return str(Path(shutil.move(str(s), str(d))))

        def remove(self, user_path: str | Path, missing_ok: bool = True) -> bool:
            p = self._resolve(user_path)
            if not p.exists():
                return bool(missing_ok)
            if p.is_dir():
                shutil.rmtree(p)
                return True
            p.unlink(missing_ok=bool(missing_ok))
            return True

        def delete(self, user_path: str | Path, missing_ok: bool = True, recursive: bool = False) -> bool:
            """Delete a file (or optionally a directory).

            - Safe mode restrictions apply via _resolve().
            - By default, directories are NOT deleted unless recursive=True.
            """

            p = self._resolve(user_path)
            if not p.exists():
                return bool(missing_ok)
            if p.is_dir():
                if not bool(recursive):
                    raise IsADirectoryError(str(p))
                shutil.rmtree(p)
                return True
            p.unlink(missing_ok=bool(missing_ok))
            return True

        def open(self, user_path: str | Path) -> str:
            """Open a file/folder using the OS default application.

            Security note:
            - Safe mode: only allows opening common document/media types (and directories).
              Executable/script types require unsafe mode.
            """

            p = self._resolve(user_path)
            if not p.exists():
                raise FileNotFoundError(str(p))

            if not self._allow_unsafe() and p.is_file():
                ext = p.suffix.lower()
                # deny potentially executable/script types in safe mode
                if ext in {".exe", ".bat", ".cmd", ".com", ".ps1", ".vbs", ".js", ".msi", ".lnk"}:
                    raise PermissionError("Opening executable/script files is not allowed in safe mode")

                # allow common docs/media; other extensions require unsafe mode
                allowed = {
                    ".txt",
                    ".md",
                    ".log",
                    ".json",
                    ".yaml",
                    ".yml",
                    ".csv",
                    ".png",
                    ".jpg",
                    ".jpeg",
                    ".webp",
                    ".gif",
                    ".bmp",
                    ".wav",
                    ".mp3",
                    ".ogg",
                    ".flac",
                    ".mp4",
                    ".webm",
                    ".pdf",
                }
                if ext and ext not in allowed:
                    raise PermissionError("File type not allowed to open in safe mode")

            # Fire-and-forget open
            if sys.platform.startswith("win"):
                os.startfile(str(p))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(p)])
            else:
                subprocess.Popen(["xdg-open", str(p)])
            return str(p)

    class _FunctionUIAPI:
        def __init__(self, runtime: "VNGameRuntime"):
            self._rt = runtime

        def _resolve_media_path(self, path_str: str) -> Path:
            p = Path(str(path_str or ""))
            allow_unsafe = bool(getattr(self._rt, "_allow_unsafe_function_scripts", False))
            if allow_unsafe:
                if p.is_absolute():
                    return p.resolve()
                return (getattr(self._rt, "_project_dir", Path.cwd()) / p).resolve()

            if p.is_absolute():
                raise PermissionError("Absolute path not allowed in safe mode")
            root = Path(getattr(self._rt, "_function_fs_root", getattr(self._rt, "_project_dir", Path.cwd()))).resolve()
            resolved = (root / p).resolve()
            try:
                resolved.relative_to(root)
            except Exception:
                raise PermissionError("Path escapes function_script_fs_root")
            return resolved

        def toast(self, text: str, duration: float = 2.0) -> None:
            msg = str(text or "")
            dur = max(0.2, float(duration))
            self._rt._enqueue_main_thread_action(lambda: self._rt._script_toasts.append({"text": msg, "remaining": dur}))

        def alert(self, text: str, title: str = "提示") -> None:
            msg = str(text or "")
            ttl = str(title or "提示")
            self._rt._enqueue_main_thread_action(lambda: setattr(self._rt, "_script_modal_message", {"text": msg, "title": ttl}))

        def close_alert(self) -> None:
            self._rt._enqueue_main_thread_action(lambda: setattr(self._rt, "_script_modal_message", None))

        def set_cursor(self, style: str, lock: bool = False) -> None:
            s = str(style or "arrow")

            def _apply():
                if lock:
                    setattr(self._rt, "_script_cursor_lock_style", s)
                self._rt._set_system_cursor(s)

            self._rt._enqueue_main_thread_action(_apply)

        def clear_cursor_lock(self) -> None:
            self._rt._enqueue_main_thread_action(lambda: setattr(self._rt, "_script_cursor_lock_style", None))

        def show_image(
            self,
            path: str,
            x: int,
            y: int,
            width: int,
            height: int,
            duration: float = 0.0,
            *,
            key: str | None = None,
            alpha: int = 255,
            z: float = 1000.0,
        ) -> str:
            """Show a top-most overlay image in render-surface coordinates.

            - duration <= 0: persistent until hide_image/clear_images
            """

            try:
                if key is None:
                    kid = int(getattr(self._rt, "_script_image_next_id", 1))
                    setattr(self._rt, "_script_image_next_id", kid + 1)
                    key = f"img_{kid}"
            except Exception:
                key = key or "img"

            s = str(path or "")
            xi, yi = int(x), int(y)
            w = int(width)
            h = int(height)
            dur = float(duration or 0.0)
            a = max(0, min(255, int(alpha)))
            zz = float(z)

            def _apply():
                try:
                    abs_path = self._resolve_media_path(s)
                except Exception:
                    return
                if not abs_path.exists():
                    return
                try:
                    img = None
                    cache_key = (str(abs_path), max(1, w), max(1, h), a)
                    if w > 0 and h > 0:
                        img = self._rt._script_image_cache.get(cache_key)
                    if img is None:
                        base = pygame.image.load(str(abs_path)).convert_alpha()
                        if w > 0 and h > 0:
                            base = pygame.transform.smoothscale(base, (max(1, w), max(1, h)))
                        if a < 255:
                            base.set_alpha(a)
                        img = base
                        if w > 0 and h > 0:
                            self._rt._script_image_cache[cache_key] = img
                except Exception:
                    return

                ww = img.get_width() if w <= 0 else max(1, w)
                hh = img.get_height() if h <= 0 else max(1, h)
                rect = pygame.Rect(int(xi), int(yi), int(ww), int(hh))
                rem = None if dur <= 0.0 else max(0.001, float(dur))
                self._rt._script_images[str(key)] = {"surface": img, "rect": rect, "remaining": rem, "z": zz}

            self._rt._enqueue_main_thread_action(_apply)
            return str(key)

        def hide_image(self, key: str) -> None:
            k = str(key or "")
            if not k:
                return
            self._rt._enqueue_main_thread_action(lambda: self._rt._script_images.pop(k, None))

        def clear_images(self) -> None:
            self._rt._enqueue_main_thread_action(lambda: setattr(self._rt, "_script_images", {}))

        def lock_input(self, seconds: float) -> None:
            dur = max(0.0, float(seconds or 0.0))

            def _apply():
                self._rt._script_input_lock_remaining = dur if dur > 0.0 else None
                self._rt._script_input_lock_until_expr = None
                self._rt._script_input_lock_until_timeout = None

            self._rt._enqueue_main_thread_action(_apply)

        def lock_input_until(self, expr: str, timeout: float = 0.0) -> None:
            e = str(expr or "").strip()
            t = max(0.0, float(timeout or 0.0))

            def _apply():
                self._rt._script_input_lock_remaining = None
                self._rt._script_input_lock_until_expr = e if e else None
                self._rt._script_input_lock_until_timeout = t if t > 0.0 else None

            self._rt._enqueue_main_thread_action(_apply)

        def unlock_input(self) -> None:
            def _apply():
                self._rt._script_input_lock_remaining = None
                self._rt._script_input_lock_until_expr = None
                self._rt._script_input_lock_until_timeout = None

            self._rt._enqueue_main_thread_action(_apply)

        def is_input_locked(self) -> bool:
            return bool(self._rt._is_script_input_locked())

        def toggle_fullscreen(self) -> None:
            self._rt._enqueue_main_thread_action(self._rt.toggle_fullscreen)

        def set_fullscreen(self, enabled: bool = True) -> None:
            want = bool(enabled)

            def _apply():
                cur = bool(getattr(self._rt, "is_fullscreen", False))
                if cur != want:
                    self._rt.toggle_fullscreen()

            self._rt._enqueue_main_thread_action(_apply)

        def is_fullscreen(self) -> bool:
            return bool(getattr(self._rt, "is_fullscreen", False))

    class _FunctionFXAPI:
        def __init__(self, runtime: "VNGameRuntime"):
            self._rt = runtime

        def shake(self, duration: float = 0.25, strength: float = 6.0, decay: bool = True) -> None:
            dur = max(0.01, float(duration))
            amp = max(0.0, float(strength))

            def _apply():
                self._rt._script_shake = {
                    "duration": dur,
                    "remaining": dur,
                    "strength": amp,
                    "decay": bool(decay),
                }

            self._rt._enqueue_main_thread_action(_apply)

        def flash(self, color=(255, 255, 255), duration: float = 0.18, alpha: int = 180) -> None:
            dur = max(0.01, float(duration))
            try:
                c = (int(color[0]), int(color[1]), int(color[2]))
            except Exception:
                c = (255, 255, 255)
            a = max(0, min(255, int(alpha)))

            def _apply():
                self._rt._script_flash = {
                    "color": c,
                    "duration": dur,
                    "remaining": dur,
                    "alpha": a,
                }

            self._rt._enqueue_main_thread_action(_apply)

    class _FunctionAudioAPI:
        def __init__(self, runtime: "VNGameRuntime"):
            self._rt = runtime

        def _resolve_media_path(self, path_str: str) -> Path:
            p = Path(str(path_str or ""))
            allow_unsafe = bool(getattr(self._rt, "_allow_unsafe_function_scripts", False))
            if allow_unsafe:
                if p.is_absolute():
                    return p.resolve()
                return (getattr(self._rt, "_project_dir", Path.cwd()) / p).resolve()

            # safe mode: forbid absolute and restrict to function_fs_root
            if p.is_absolute():
                raise PermissionError("Absolute path not allowed in safe mode")
            root = Path(getattr(self._rt, "_function_fs_root", getattr(self._rt, "_project_dir", Path.cwd()))).resolve()
            resolved = (root / p).resolve()
            try:
                resolved.relative_to(root)
            except Exception:
                raise PermissionError("Path escapes function_script_fs_root")
            return resolved

        def play_sfx(self, path: str, delay: float = 0.0) -> None:
            s = str(path or "")
            d = max(0.0, float(delay))

            def _apply():
                try:
                    abs_path = self._resolve_media_path(s)
                except Exception:
                    return
                if not abs_path.exists():
                    return
                if d <= 0.0:
                    self._rt._ensure_sfx(str(abs_path))
                else:
                    self._rt._pending_sfx_path = abs_path
                    self._rt._pending_sfx_delay = d

            self._rt._enqueue_main_thread_action(_apply)

        def stop_sfx(self) -> None:
            self._rt._enqueue_main_thread_action(self._rt._stop_sfx_playback)

        def play_bgm(self, path: str, loop: bool = True, fade: bool = False) -> None:
            s = str(path or "")

            def _apply():
                try:
                    abs_path = self._resolve_media_path(s)
                except Exception:
                    return
                if not abs_path.exists():
                    return
                self._rt._ensure_bgm(str(abs_path), loop=bool(loop), fade=bool(fade))

            self._rt._enqueue_main_thread_action(_apply)

        def stop_bgm(self) -> None:
            self._rt._enqueue_main_thread_action(self._rt._stop_bgm)

    class _FunctionTimeAPI:
        def __init__(self, runtime: "VNGameRuntime", host_node_id):
            self._rt = runtime
            self._host_node_id = host_node_id

        def set_timeout(self, seconds: float, script: str) -> int:
            return int(self._rt._create_script_timer(float(seconds), str(script or ""), interval=0.0, repeat=0, host_node_id=self._host_node_id))

        def set_interval(self, seconds: float, script: str, repeat: int = -1) -> int:
            sec = max(0.001, float(seconds))
            rep = int(repeat)
            return int(self._rt._create_script_timer(sec, str(script or ""), interval=sec, repeat=rep, host_node_id=self._host_node_id))

        def clear_timer(self, timer_id: int) -> bool:
            return bool(self._rt._clear_script_timer(int(timer_id)))

    def _trigger_function_nodes_for_host(self, host_node_id, host_entry: dict | None):
        fn_nodes = self._function_nodes_by_host.get(host_node_id) or []
        if not fn_nodes:
            return

        entry_snapshot = dict(host_entry) if isinstance(host_entry, dict) else {}
        vars_snapshot = dict(self.variables) if isinstance(getattr(self, "variables", None), dict) else {}

        t = threading.Thread(
            target=self._execute_function_nodes_worker,
            args=(host_node_id, entry_snapshot, vars_snapshot, list(fn_nodes)),
            daemon=True,
        )
        t.start()

    def _execute_function_nodes_worker(self, host_node_id, entry_snapshot: dict, vars_snapshot: dict, fn_nodes: list[dict]):
        for fn in fn_nodes:
            if not isinstance(fn, dict):
                continue
            rules = fn.get("rules")
            if not isinstance(rules, list):
                continue
            api = VNGameRuntime._FunctionScriptAPI(self, host_node_id, fn)
            for idx, rule in enumerate(rules):
                if not isinstance(rule, dict):
                    continue
                if not bool(rule.get("enabled", True)):
                    continue
                cond = str(rule.get("condition", rule.get("when", "")) or "")
                action = str(rule.get("action", rule.get("script", "")) or "")
                if not action.strip():
                    continue

                try:
                    if cond.strip():
                        ok = bool(self._eval_function_script_expr(cond, api, entry_snapshot, vars_snapshot, fn, idx))
                        if not ok:
                            continue
                    self._exec_function_script(action, api, entry_snapshot, vars_snapshot, fn, idx)
                except Exception as exc:
                    api.log(f"规则执行异常: {exc}")

    def _build_function_script_env(self, api, entry_snapshot: dict, vars_snapshot: dict, fn_node: dict, rule_index: int):
        allow_unsafe = bool(getattr(self, "_allow_unsafe_function_scripts", False))

        def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
            if allow_unsafe:
                return builtins.__import__(name, globals, locals, fromlist, level)
            root = str(name).split(".")[0]
            if root in {"math", "random", "re", "time"}:
                return builtins.__import__(name, globals, locals, fromlist, level)
            raise ImportError(f"Import not allowed: {name}")

        if allow_unsafe:
            globals_dict = {"__builtins__": builtins.__dict__}
        else:
            safe_builtins = {
                "True": True,
                "False": False,
                "None": None,
                "len": len,
                "min": min,
                "max": max,
                "range": range,
                "int": int,
                "float": float,
                "str": str,
                "bool": bool,
                "dict": dict,
                "list": list,
                "tuple": tuple,
                "set": set,
                "abs": abs,
                "sum": sum,
                "__import__": safe_import,
            }
            globals_dict = {"__builtins__": safe_builtins}

        locals_dict = {
            "engine": api,
            "entry": dict(entry_snapshot) if isinstance(entry_snapshot, dict) else {},
            "vars": dict(vars_snapshot) if isinstance(vars_snapshot, dict) else {},
            "host_node_id": api.host_node_id,
            "function_node": dict(fn_node) if isinstance(fn_node, dict) else {},
            "rule_index": int(rule_index),
        }
        return globals_dict, locals_dict

    def _eval_function_script_expr(self, expr: str, api, entry_snapshot: dict, vars_snapshot: dict, fn_node: dict, rule_index: int):
        g, l = self._build_function_script_env(api, entry_snapshot, vars_snapshot, fn_node, rule_index)
        # Allow multiline expressions from the Designer UI:
        # treat line breaks as spaces to avoid SyntaxError in eval mode.
        expr_norm = " ".join(str(expr or "").splitlines())
        code = compile(expr_norm, "<function-node-condition>", "eval")
        return eval(code, g, l)

    def _exec_function_script(self, script: str, api, entry_snapshot: dict, vars_snapshot: dict, fn_node: dict, rule_index: int):
        g, l = self._build_function_script_env(api, entry_snapshot, vars_snapshot, fn_node, rule_index)
        code = compile(script, "<function-node-action>", "exec")
        exec(code, g, l)

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
        self._choice_timeout_remaining = None
        self._choice_default_index = -1
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
        # Allow {$var} placeholders inside option labels.
        try:
            options = [self._interpolate_dialogue_template(str(o)) for o in (options or [])]
        except Exception:
            pass
        if len(options) > len(targets):
            options = options[: len(targets)]
        else:
            targets = targets[: len(options)]
        self._choice_options = options
        self._choice_targets = targets
        self._choice_overlay = True
        self._choice_selected = -1
        self._choice_button_hitboxes = [None] * len(self._choice_options)

        timeout_norm, default_idx = normalize_choice_timeout_config(entry if isinstance(entry, dict) else {}, len(self._choice_options))
        self._choice_default_index = default_idx
        # only start timer when both timeout + default are valid
        if timeout_norm is not None and default_idx >= 0:
            self._choice_timeout_remaining = float(timeout_norm)
        else:
            self._choice_timeout_remaining = None

    def _apply_choice(self, idx: int):
        if not self._choice_overlay:
            return
        if idx is None or idx < 0 or idx >= len(self._choice_targets):
            return
        target = self._choice_targets[idx]
        self._choice_overlay = False
        self._choice_options = []
        self._choice_targets = []
        self._choice_timeout_remaining = None
        self._choice_default_index = -1
        self._choice_selected = -1
        self._choice_button_hitboxes = []
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

        # New: rules list (ordered). Rule i maps to outgoing edge i; last edge is the default-else branch.
        rules = entry.get("condition_rules")
        if not (isinstance(rules, list) and rules):
            # Strict mode: legacy single-condition fields are NOT supported.
            # If a condition node has no rules, treat the last outgoing edge as the default-else.
            chosen = targets[-1] if targets else None
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
            return

        if isinstance(rules, list) and rules:
            chosen = None

            def _eval_rule(rule_obj: dict) -> bool:
                if not isinstance(rule_obj, dict):
                    return False
                logic = str(rule_obj.get("logic") or "and").strip().lower()
                if logic not in {"and", "or"}:
                    logic = "and"
                exprs = rule_obj.get("exprs")
                if isinstance(exprs, str):
                    expr_list = [line.strip() for line in exprs.splitlines() if line.strip()]
                elif isinstance(exprs, list):
                    expr_list = [str(x).strip() for x in exprs if str(x).strip()]
                else:
                    expr_list = []
                if not expr_list:
                    return False
                if logic == "and":
                    return all(eval_var_expr(e, self.variables) for e in expr_list)
                return any(eval_var_expr(e, self.variables) for e in expr_list)

            matched = False
            for idx, r in enumerate(rules[:50]):
                if _eval_rule(r):
                    matched = True
                    if idx < len(targets):
                        chosen = targets[idx]
                    break

            if not matched:
                else_idx = len(rules)
                if else_idx < len(targets):
                    chosen = targets[else_idx]

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
            return

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

        # apply script shake (render coords -> window coords)
        try:
            ox, oy = getattr(self, "_script_shake_offset", (0.0, 0.0))
            x += int(round(float(ox) * float(scale)))
            y += int(round(float(oy) * float(scale)))
        except Exception:
            pass
        self.screen.fill((0, 0, 0))
        self.screen.blit(blit_surface, (x, y))

    def _build_dialogues_from_flow(self, data: dict) -> list[dict]:
        """Traverse nodes following connections to build dialogue order."""
        flow = data.get("flow_nodes") or {}
        nodes = flow.get("nodes") or []
        connections = flow.get("connections") or []

        nodes_map = {
            n.get("id"): n
            for n in nodes
            if isinstance(n, dict) and n.get("id") is not None and str(n.get("node_type", "")).lower() != "function"
        }
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

        # apply HUD button group config from UI layout (if any)
        self._apply_hud_buttons_from_ui_layout(layout)

        # apply choice button group config from UI layout (if any)
        self._apply_choice_buttons_from_ui_layout(layout)

        # apply function menu overlays config from UI layout (only if project config is absent)
        if not bool(getattr(self, "_function_menus_from_project", False)):
            self._apply_function_menus_from_ui_layout(layout)
        # layout changes can invalidate overlay hit boxes
        self._overlay_hitboxes = {}
        self._overlay_slot_hitboxes = []

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

        portrait2_pos = layout.get("portrait2_pos") if isinstance(layout, dict) else None
        if isinstance(portrait2_pos, (list, tuple)) and len(portrait2_pos) == 2:
            try:
                self.portrait2_pos = (int(portrait2_pos[0]), int(portrait2_pos[1]))
            except Exception:
                self.portrait2_pos = None
        else:
            self.portrait2_pos = None

        ps = 1.0
        if isinstance(layout, dict):
            try:
                ps = float(layout.get("portrait_scale", 1.0) or 1.0)
            except Exception:
                ps = 1.0
        self.portrait_scale = max(0.1, min(5.0, ps))

        ps2 = 1.0
        if isinstance(layout, dict):
            try:
                ps2 = float(layout.get("portrait2_scale", 1.0) or 1.0)
            except Exception:
                ps2 = 1.0
        self.portrait2_scale = max(0.1, min(5.0, ps2))

        self.portrait_size = None
        if isinstance(layout, dict):
            psz = layout.get("portrait_size")
            if isinstance(psz, (list, tuple)) and len(psz) == 2:
                try:
                    pw = int(psz[0])
                    ph = int(psz[1])
                    if pw > 0 and ph > 0:
                        self.portrait_size = (pw, ph)
                except Exception:
                    self.portrait_size = None

        self.portrait2_size = None
        if isinstance(layout, dict):
            psz2 = layout.get("portrait2_size")
            if isinstance(psz2, (list, tuple)) and len(psz2) == 2:
                try:
                    pw2 = int(psz2[0])
                    ph2 = int(psz2[1])
                    if pw2 > 0 and ph2 > 0:
                        self.portrait2_size = (pw2, ph2)
                except Exception:
                    self.portrait2_size = None
        self._bg_cache.clear()
        self._portrait_scaled_cache.clear()
        self._portrait2_scaled_cache.clear()

    def _append_history(self, entry: dict | None):
        if not entry:
            return
        speaker = entry.get("speaker") or ""
        content = entry.get("content") or ""
        try:
            speaker = self._interpolate_dialogue_template(str(speaker))
            content = self._interpolate_dialogue_template(str(content))
        except Exception:
            pass
        if not content:
            return
        self._history.append({"speaker": speaker, "content": content})
        if len(self._history) > 10:
            self._history = self._history[-10:]

    _DIALOGUE_VAR_TOKEN_RE = re.compile(r"\{\$\s*([^}]+?)\s*\}")

    def _format_var_value_for_dialogue(self, val) -> str:
        # bool should stay bool-like, not 0/1
        if isinstance(val, bool):
            return "True" if val else "False"
        # normalize numpy scalars
        try:
            if hasattr(val, "item") and callable(getattr(val, "item")):
                val = val.item()
        except Exception:
            pass
        if isinstance(val, int):
            return str(val)
        if isinstance(val, float):
            try:
                if not math.isfinite(val):
                    return str(val)
            except Exception:
                pass
            # Use Decimal(str(x)) to reduce float representation noise and trim trailing zeros.
            try:
                d = Decimal(str(val))
                s = format(d, "f")
            except (InvalidOperation, ValueError):
                s = str(val)
            if "." in s:
                s = s.rstrip("0").rstrip(".")
            return s
        if val is None:
            return ""
        return str(val)

    def _interpolate_dialogue_template(self, text: str) -> str:
        # Fast path: only do regex work when token is present.
        if not text or "{$" not in text:
            return text

        def _repl(m: re.Match) -> str:
            raw = m.group(1) or ""
            name = str(raw).strip()
            if not name:
                return m.group(0)
            # Allow unicode identifiers (Python style); ignore invalid placeholders.
            try:
                if not name.isidentifier():
                    return m.group(0)
            except Exception:
                return m.group(0)
            try:
                val = (self.variables or {}).get(name, 0)
            except Exception:
                val = 0
            return self._format_var_value_for_dialogue(val)

        try:
            return self._DIALOGUE_VAR_TOKEN_RE.sub(_repl, text)
        except Exception:
            return text

    def _load_font(self, size: int, bold: bool = False, family: str | None = None, font_path: str | None = None):
        # Prefer font file if provided
        try:
            fp = (font_path or "").strip()
            if fp:
                abs_path = self._resolve_path(fp)
                if abs_path.exists():
                    f = pygame.font.Font(str(abs_path), size)
                    try:
                        f.set_bold(bool(bold))
                    except Exception:
                        pass
                    return f
        except Exception:
            pass

        # Fallback to system font family (try to resolve a real font file first).
        try:
            preferred = [str(family or "").strip(), "Microsoft YaHei", "SimHei", "SimSun", "NSimSun", "Arial Unicode MS", "Noto Sans CJK SC", "Source Han Sans SC"]
            for fam in preferred:
                if not fam:
                    continue
                try:
                    fp2 = pygame.font.match_font(fam)
                except Exception:
                    fp2 = None
                if fp2:
                    f2 = pygame.font.Font(fp2, size)
                    try:
                        f2.set_bold(bool(bold))
                    except Exception:
                        pass
                    return f2
        except Exception:
            pass

        # Last resort
        try:
            fam = (family or "SimHei")
            return pygame.font.SysFont(fam, size, bold=bold)
        except Exception:
            return pygame.font.Font(None, size)

    def _default_text_styles(self) -> dict:
        return {
            "dialogue": {
                "font_family": "SimHei",
                "font_path": "",
                "size": 22,
                "color": [235, 235, 240],
                "bold": False,
                "outline_color": [0, 0, 0],
                "outline_width": 0,
            },
            "name": {
                "font_family": "SimHei",
                "font_path": "",
                "size": 24,
                "color": [220, 220, 220],
                "bold": True,
                "outline_color": [0, 0, 0],
                "outline_width": 0,
            },
        }

    def _coerce_rgb(self, val, default_rgb: tuple[int, int, int]) -> tuple[int, int, int]:
        if isinstance(val, (list, tuple)) and len(val) >= 3:
            try:
                r, g, b = int(val[0]), int(val[1]), int(val[2])
                return (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))
            except Exception:
                return default_rgb
        return default_rgb

    def _apply_text_style_config(self, cfg: dict):
        styles = {}
        try:
            styles = (cfg or {}).get("text_styles", {})
        except Exception:
            styles = {}
        if not isinstance(styles, dict):
            styles = {}
        dlg_style, name_style, dlg_font, name_font = self._compute_text_styles_from_text_styles(styles)
        self._dialogue_style = dlg_style
        self._name_style = name_style
        self.font = dlg_font
        self.name_font = name_font

    def _render_text_surface(self, text: str, font, color, outline_width: int = 0, outline_color=(0, 0, 0)):
        try:
            ow = max(0, int(outline_width))
        except Exception:
            ow = 0
        if ow <= 0:
            return font.render(str(text), True, color)
        base = font.render(str(text), True, color)
        outline = font.render(str(text), True, outline_color)
        w = base.get_width() + ow * 2
        h = base.get_height() + ow * 2
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        for dx in range(-ow, ow + 1):
            for dy in range(-ow, ow + 1):
                if dx * dx + dy * dy > ow * ow:
                    continue
                surf.blit(outline, (ow + dx, ow + dy))
        surf.blit(base, (ow, ow))
        return surf

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
        if self._pending_voice_path:
            self._pending_voice_delay -= dt
            if self._pending_voice_delay <= 0:
                self._ensure_voice(str(self._pending_voice_path))
                self._pending_voice_path = None
                self._pending_voice_delay = 0.0

        if self._pending_sfx_path:
            self._pending_sfx_delay -= dt
            if self._pending_sfx_delay <= 0:
                self._ensure_sfx(str(self._pending_sfx_path))
                self._pending_sfx_path = None
                self._pending_sfx_delay = 0.0

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

    def _stop_sfx_playback(self):
        """Stop any playing sfx and clear pending schedule."""
        self._pending_sfx_path = None
        self._pending_sfx_delay = 0.0
        try:
            if self._sfx_channel and self._sfx_channel.get_busy():
                self._sfx_channel.stop()
        except Exception:
            pass
        self._sfx_channel = None

    def _ensure_sfx(self, sfx_path: str):
        if not sfx_path:
            return
        abs_path = self._resolve_path(sfx_path)
        if not abs_path.exists():
            return
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            if abs_path not in self._sfx_cache:
                self._sfx_cache[abs_path] = pygame.mixer.Sound(str(abs_path))
            sound = self._sfx_cache[abs_path]
            if self._sfx_channel and self._sfx_channel.get_busy():
                self._sfx_channel.stop()
            master = float(self._settings.get("master_volume", 1.0))
            sfx_vol = float(self._settings.get("sfx_volume", 1.0))
            volume = max(0.0, min(1.0, master * sfx_vol))
            sound.set_volume(volume)
            self._sfx_channel = sound.play()
        except Exception:
            pass

    def _schedule_sfx(self, sfx_path: str, delay: float = 0.05):
        if not sfx_path:
            self._pending_sfx_path = None
            self._pending_sfx_delay = 0.0
            return
        abs_path = self._resolve_path(sfx_path)
        if not abs_path.exists():
            self._pending_sfx_path = None
            self._pending_sfx_delay = 0.0
            return
        self._pending_sfx_path = abs_path
        self._pending_sfx_delay = max(0.0, delay)

    def _effective_text_style_for_entry(self, entry: dict) -> tuple[dict, dict, object, object]:
        """Return (dialogue_style, name_style, dialogue_font, name_font) for current entry.

        Entry may opt-in to override via:
        - text_style_enabled: bool
        - text_styles: {dialogue:{...}, name:{...}}
        """
        try:
            if isinstance(entry, dict) and bool(entry.get("text_style_enabled", False)) and isinstance(entry.get("text_styles"), dict):
                key = json.dumps(entry.get("text_styles") or {}, ensure_ascii=False, sort_keys=True)
                cached = self._entry_text_style_cache.get(key)
                if cached:
                    return cached
                dlg_style, name_style, dlg_font, name_font = self._compute_text_styles_from_text_styles(entry.get("text_styles") or {})
                self._entry_text_style_cache[key] = (dlg_style, name_style, dlg_font, name_font)
                return self._entry_text_style_cache[key]
        except Exception:
            pass
        return (self._dialogue_style, self._name_style, self.font, self.name_font)

    def _compute_text_styles_from_text_styles(self, text_styles: dict) -> tuple[dict, dict, object, object]:
        styles = text_styles if isinstance(text_styles, dict) else {}
        defaults = self._default_text_styles()

        dlg = defaults["dialogue"].copy()
        nm = defaults["name"].copy()
        try:
            if isinstance(styles.get("dialogue"), dict):
                dlg.update(styles.get("dialogue") or {})
            if isinstance(styles.get("name"), dict):
                nm.update(styles.get("name") or {})
        except Exception:
            pass

        dlg_family = str(dlg.get("font_family") or defaults["dialogue"]["font_family"])
        nm_family = str(nm.get("font_family") or defaults["name"]["font_family"])
        dlg_font_path = str(dlg.get("font_path") or "").strip()
        nm_font_path = str(nm.get("font_path") or "").strip()
        try:
            dlg_size = int(dlg.get("size") or defaults["dialogue"]["size"])
        except Exception:
            dlg_size = int(defaults["dialogue"]["size"])
        try:
            nm_size = int(nm.get("size") or defaults["name"]["size"])
        except Exception:
            nm_size = int(defaults["name"]["size"])
        dlg_size = max(8, min(120, dlg_size))
        nm_size = max(8, min(120, nm_size))

        dlg_bold = bool(dlg.get("bold", defaults["dialogue"]["bold"]))
        nm_bold = bool(nm.get("bold", defaults["name"]["bold"]))

        dlg_color = self._coerce_rgb(dlg.get("color"), (235, 235, 240))
        nm_color = self._coerce_rgb(nm.get("color"), (220, 220, 220))
        dlg_outline_color = self._coerce_rgb(dlg.get("outline_color"), (0, 0, 0))
        nm_outline_color = self._coerce_rgb(nm.get("outline_color"), (0, 0, 0))
        try:
            dlg_ow = int(dlg.get("outline_width") or 0)
        except Exception:
            dlg_ow = 0
        try:
            nm_ow = int(nm.get("outline_width") or 0)
        except Exception:
            nm_ow = 0
        dlg_ow = max(0, min(20, dlg_ow))
        nm_ow = max(0, min(20, nm_ow))

        dlg_style = {
            "font_family": dlg_family,
            "font_path": dlg_font_path,
            "size": dlg_size,
            "bold": dlg_bold,
            "color": dlg_color,
            "outline_color": dlg_outline_color,
            "outline_width": dlg_ow,
        }
        name_style = {
            "font_family": nm_family,
            "font_path": nm_font_path,
            "size": nm_size,
            "bold": nm_bold,
            "color": nm_color,
            "outline_color": nm_outline_color,
            "outline_width": nm_ow,
        }
        dlg_font = self._load_font(dlg_size, bold=dlg_bold, family=dlg_family, font_path=dlg_font_path)
        name_font = self._load_font(nm_size, bold=nm_bold, family=nm_family, font_path=nm_font_path)
        return dlg_style, name_style, dlg_font, name_font

    def save_game(self, slot: int = 1):
        try:
            self.save_dir.mkdir(parents=True, exist_ok=True)
            self._update_persistent_from_runtime()
            self._save_persistent_vars()
            save_data = {
                "current_index": self.current_index,
                "current_node_id": self.current_node_id,
                "graph_mode": self.graph_mode,
                "sub_index": int(getattr(self, "_sub_index", 0) or 0),
                "variables": self.variables,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "branch_strategy": self.branch_strategy,
                "window_size": list(self.window_size),
                "summary": self._build_summary(),
            }
            save_path = slot_file_path(self.save_dir, slot)
            with open(save_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(save_data, f, allow_unicode=True)

            # 保存缩略图（尽量不影响存档流程，失败不阻断）
            try:
                self._save_slot_thumbnail(int(slot))
            except Exception:
                pass

            print(f"存档完成：{save_path}")
        except Exception as exc:
            print(f"存档失败: {exc}")

    def _capture_scene_only_surface_for_thumbnail(self, dt: float = 0.0) -> pygame.Surface | None:
        """Render a UI-free scene snapshot for save thumbnails.

        Intentionally excludes textbox UI, HUD buttons, and all overlays (save/load/settings/help/history/choice/etc).
        """

        entry = self._current_entry()
        if not entry:
            return None

        try:
            w, h = int(self.render_size[0]), int(self.render_size[1])
        except Exception:
            return None
        if w <= 0 or h <= 0:
            return None

        try:
            dst = pygame.Surface((w, h))
        except Exception:
            return None

        old_surface = getattr(self, "render_surface", None)
        try:
            self.render_surface = dst

            bg_path = entry.get("background") or ""
            portrait_path = entry.get("portrait") or ""
            portrait2_path = entry.get("portrait2") or ""
            video_path = entry.get("video") or ""
            bg_fade_duration = entry.get("bg_fade_duration", None)

            portrait_fade = bool(entry.get("portrait_fade", False))
            portrait_fade_duration = entry.get("portrait_fade_duration", None)
            portrait2_fade = bool(entry.get("portrait2_fade", False))
            portrait2_fade_duration = entry.get("portrait2_fade_duration", None)

            # Draw video or background (match scene visuals, but skip UI/overlays)
            if video_path:
                try:
                    self._update_video(video_path, bool(entry.get("video_loop", False)), float(dt))
                except Exception:
                    pass

                if getattr(self, "_video_surface", None) is not None:
                    self.render_surface.blit(self._video_surface, (0, 0))
                else:
                    if bg_path:
                        try:
                            self._update_background(bg_path, fade_in=bool(entry.get("bg_fade_in", False)), duration=bg_fade_duration)
                            self._render_background(float(dt))
                        except Exception:
                            self.render_surface.fill(self.bg_color)
                    else:
                        self.render_surface.fill(self.bg_color)
            else:
                try:
                    if getattr(self, "_video_clip", None):
                        self._stop_video()
                except Exception:
                    pass

                try:
                    self._update_background(bg_path, fade_in=bool(entry.get("bg_fade_in", False)), duration=bg_fade_duration)
                    self._render_background(float(dt))
                except Exception:
                    self.render_surface.fill(self.bg_color)

            # Draw portraits (character sprites)
            try:
                self._draw_portrait2(portrait2_path, portrait2_fade, float(dt), fade_in_duration=portrait2_fade_duration)
                self._draw_portrait(portrait_path, portrait_fade, float(dt), fade_in_duration=portrait_fade_duration)
            except Exception:
                pass

            return dst
        finally:
            self.render_surface = old_surface

    def _save_slot_thumbnail(self, slot: int, *, max_width: int = 320) -> str:
        """Capture a save thumbnail.

        Prefer a UI-free scene snapshot, falling back to current render_surface on failure.
        """

        src = None
        try:
            src = self._capture_scene_only_surface_for_thumbnail()
        except Exception:
            src = None

        if src is None:
            try:
                src = self.render_surface
            except Exception:
                return ""

        if src is None:
            return ""

        w, h = int(src.get_width()), int(src.get_height())
        if w <= 0 or h <= 0:
            return ""

        mw = max(64, int(max_width))
        tw = min(mw, w)
        th = max(1, int(round(tw * (h / float(w)))))

        try:
            thumb = pygame.transform.smoothscale(src, (int(tw), int(th)))
        except Exception:
            thumb = pygame.transform.scale(src, (int(tw), int(th)))

        out_path = slot_thumbnail_path(self.save_dir, int(slot))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        pygame.image.save(thumb, str(out_path))
        return str(out_path)

    def _load_slot_thumbnail_surface(self, slot: int, size: tuple[int, int]) -> pygame.Surface | None:
        """Load & scale a slot thumbnail, with caching."""

        p = slot_thumbnail_path(self.save_dir, int(slot))
        if not p.exists():
            return None
        try:
            mtime = float(p.stat().st_mtime)
        except Exception:
            mtime = 0.0

        tw, th = max(1, int(size[0])), max(1, int(size[1]))
        key = (str(p), tw, th, mtime)
        cached = self._slot_thumbnail_cache.get(key)
        if cached is not None:
            return cached

        try:
            img = pygame.image.load(str(p)).convert()
        except Exception:
            return None

        try:
            scaled = pygame.transform.smoothscale(img, (tw, th))
        except Exception:
            scaled = pygame.transform.scale(img, (tw, th))

        # 清理旧缓存（同 path+size 不同 mtime 的旧键）
        try:
            prefix = (str(p), tw, th)
            for k in list(self._slot_thumbnail_cache.keys()):
                if k[:3] == prefix and k != key:
                    self._slot_thumbnail_cache.pop(k, None)
        except Exception:
            pass

        self._slot_thumbnail_cache[key] = scaled
        return scaled

    def load_game(self, slot: int = 1):
        save_path = slot_file_path(self.save_dir, slot)
        if not save_path.exists():
            print("未找到存档文件")
            return

        show_overlay = self._loading_overlay_enabled_for("load_save")
        if show_overlay:
            self._loading_begin("正在读取存档...", subtitle=f"槽位 {slot}")

        try:
            self.fast_skip = False
            self._fast_skip_timer = 0.0
            self._loading_progress(0.18, "读取存档文件...", subtitle=f"槽位 {slot}")
            with open(save_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            self._loading_progress(0.45, "恢复游戏状态...", subtitle=f"槽位 {slot}")
            self.branch_strategy = data.get("branch_strategy", self.branch_strategy)
            # protected vars do NOT rollback on load: ignore save values for protected names.
            protected = getattr(self, "_protected_vars", set()) or set()
            old_vars = dict(self.variables) if isinstance(self.variables, dict) else {}
            saved_vars = data.get("variables", {})
            self.variables = saved_vars if isinstance(saved_vars, dict) else {}
            if protected:
                init_map: dict[str, float] = {}
                try:
                    for item in (self._global_var_defs or []):
                        if not isinstance(item, dict):
                            continue
                        n = item.get("name")
                        if not n:
                            continue
                        try:
                            init_map[str(n)] = float(item.get("initial", 0.0))
                        except Exception:
                            init_map[str(n)] = 0.0
                except Exception:
                    init_map = {}

                for name in protected:
                    # Prefer current runtime value (no rollback), then persistent, then initial.
                    if name in old_vars:
                        try:
                            self.variables[name] = float(old_vars.get(name))
                        except Exception:
                            self.variables[name] = float(init_map.get(name, 0.0))
                        continue
                    if isinstance(self._persistent_vars, dict) and name in self._persistent_vars:
                        try:
                            self.variables[name] = float(self._persistent_vars.get(name))
                        except Exception:
                            self.variables[name] = float(init_map.get(name, 0.0))
                        continue
                    self.variables[name] = float(init_map.get(name, 0.0))
            self._history = []
            self._history_overlay = False
            try:
                self._sub_index = int(data.get("sub_index", 0) or 0)
            except Exception:
                self._sub_index = 0
            saved_graph = bool(data.get("graph_mode", False))
            if saved_graph and self.nodes_map:
                node_id = data.get("current_node_id")
                if node_id not in self.nodes_map:
                    print("存档数据已过期或无效")
                    return
                self.graph_mode = True
                self.current_node_id = node_id
                self.current_index = 0

                # clamp sub_index for text nodes with sub_dialogues; other nodes force 0
                try:
                    node = self.nodes_map.get(self.current_node_id, {}) or {}
                    if str(node.get("node_type") or "").lower() == "text":
                        subs = node.get("sub_dialogues") or []
                        if isinstance(subs, list) and subs:
                            self._sub_index = max(0, min(int(self._sub_index), len(subs) - 1))
                        else:
                            self._sub_index = 0
                    else:
                        self._sub_index = 0
                except Exception:
                    self._sub_index = 0
            else:
                idx = int(data.get("current_index", 0))
                if idx < 0 or idx >= len(self.dialogues):
                    print("存档数据已过期或无效")
                    return
                self.graph_mode = False
                self.current_index = idx
                self._sub_index = 0
            size_data = data.get("window_size")
            if isinstance(size_data, (list, tuple)) and len(size_data) == 2:
                self.screen = pygame.display.set_mode(size_data)
                self._apply_window_size(tuple(size_data))
            self._stop_bgm()
            self._voice_played_index = None
            # 读档：恢复到当前节点/子对话位置时，不应重复执行 var_ops（变量处理）。
            # 变量处理应只在“真实推进进入该 entry”时触发，而不是加载存档时重放。
            self._on_enter_node(apply_var_ops=False)
            self._reset_typing_state()
            self._update_persistent_from_runtime()
            self._save_persistent_vars()
            print(f"读取存档完成：{save_path}")
            self.mode = "game"
            self._overlay_return_mode = None
            self._loading_progress(1.0, "读取存档完成", subtitle=f"槽位 {slot}")
        except Exception as exc:
            print(f"读档失败: {exc}")
        finally:
            if show_overlay:
                try:
                    self._loading_end()
                except Exception:
                    pass

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

    def _overlay_font(self, size: int, *, bold: bool = False):
        cache = getattr(self, "_ui_overlay_font_cache", None)
        if cache is None:
            cache = {}
            self._ui_overlay_font_cache = cache
        key = (int(size), bool(bold))
        if key not in cache:
            cache[key] = self._load_font(int(size), bold=bold)
        return cache[key]

    def _overlay_color(self, val, default: tuple[int, int, int]) -> tuple[int, int, int]:
        if isinstance(val, str):
            s = val.strip()
            if s.startswith("#") and len(s) == 7:
                try:
                    return (int(s[1:3], 16), int(s[3:5], 16), int(s[5:7], 16))
                except Exception:
                    return default
        if isinstance(val, (list, tuple)) and len(val) == 3:
            try:
                r = max(0, min(255, int(val[0])))
                g = max(0, min(255, int(val[1])))
                b = max(0, min(255, int(val[2])))
                return (r, g, b)
            except Exception:
                return default
        return default

    def _wrap_text_lines(self, text: str, font, max_width: int) -> list[str]:
        if not text:
            return []
        lines: list[str] = []
        current = ""
        for ch in str(text):
            test = current + ch
            if current and font.size(test)[0] > max_width:
                lines.append(current)
                current = ch
            else:
                current = test
        if current:
            lines.append(current)
        return lines

    def _render_function_menu_common(self, name: str, *, title: str):
        cfg = self._get_function_menu_cfg(name)
        w, h = self.render_size
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)

        bg = self._load_overlay_background(str(cfg.get("background_image") or ""))
        if bg is not None:
            try:
                bg_alpha = int(cfg.get("background_alpha", 255))
            except Exception:
                bg_alpha = 255
            bg_alpha = max(0, min(255, bg_alpha))
            if bg_alpha < 255:
                bg2 = bg.copy()
                bg2.set_alpha(bg_alpha)
                overlay.blit(bg2, (0, 0))
            else:
                overlay.blit(bg, (0, 0))

        try:
            overlay_alpha = int(cfg.get("overlay_alpha", 160))
        except Exception:
            overlay_alpha = 160
        overlay_alpha = max(0, min(255, overlay_alpha))
        if overlay_alpha > 0:
            dim = pygame.Surface((w, h), pygame.SRCALPHA)
            dim.fill((0, 0, 0, overlay_alpha))
            overlay.blit(dim, (0, 0))

        title_font = self._overlay_font(int(cfg.get("title_font_size", 22)), bold=True)
        font = self._overlay_font(int(cfg.get("font_size", 18)), bold=False)

        title_pos = cfg.get("title_pos", [40, 40])
        try:
            tx, ty = int(title_pos[0]), int(title_pos[1])
        except Exception:
            tx, ty = 40, 40
        title_color = self._overlay_color(cfg.get("title_color"), (255, 255, 255))
        title_surf = title_font.render(title, True, title_color)
        overlay.blit(title_surf, (tx, ty))

        hitboxes: dict[str, pygame.Rect] = {}
        close_cfg = cfg.get("close_button") if isinstance(cfg.get("close_button"), dict) else {}
        cpos = close_cfg.get("pos", [w - 60, 40])
        csize = close_cfg.get("size", [32, 32])
        ctext = str(close_cfg.get("text", "×") or "×")
        try:
            cx, cy = int(cpos[0]), int(cpos[1])
        except Exception:
            cx, cy = w - 60, 40
        try:
            cw, ch = int(csize[0]), int(csize[1])
        except Exception:
            cw, ch = 32, 32
        cw = max(18, cw)
        ch = max(18, ch)
        close_rect = pygame.Rect(cx, cy, cw, ch)
        hitboxes["close"] = close_rect
        btn_bg = pygame.Surface((cw, ch), pygame.SRCALPHA)
        btn_bg.fill((255, 255, 255, 70 if self._overlay_hover == "close" else 50))
        overlay.blit(btn_bg, (cx, cy))
        t_surf = title_font.render(ctext, True, (255, 255, 255))
        overlay.blit(t_surf, (cx + (cw - t_surf.get_width()) // 2, cy + (ch - t_surf.get_height()) // 2 - 1))

        return overlay, cfg, font, title_font, hitboxes

    def _render_function_menu_overlay(self):
        ot = self._overlay_type()
        if ot is None:
            return

        self._overlay_hitboxes = {}
        self._overlay_slot_hitboxes = []

        if ot == "help":
            overlay, cfg, font, _title_font, hit = self._render_function_menu_common("help", title="帮助")
            self._overlay_hitboxes.update(hit)
            text_color = self._overlay_color(cfg.get("text_color"), (230, 230, 230))
            hint_color = self._overlay_color(cfg.get("hint_color"), (200, 200, 200))
            area = cfg.get("text_area", [40, 100, self.render_size[0] - 80, self.render_size[1] - 160])
            try:
                ax, ay, aw, ah = int(area[0]), int(area[1]), int(area[2]), int(area[3])
            except Exception:
                ax, ay, aw, ah = 40, 100, self.render_size[0] - 80, self.render_size[1] - 160
            aw = max(20, aw)
            ah = max(20, ah)

            key_name = self._help_hotkey_name or "F1"
            ps = self._active_slot_page_size("save")
            if ps == 10:
                slot_hint = f"↑/↓ 翻页（每页{ps}个） | 数字 0-9 选择槽位（0=第10个）"
            else:
                slot_hint = f"↑/↓ 翻页（每页{ps}个） | 数字 1-{ps} 选择槽位"
            base_lines = [
                "基础：左键/Space/Enter 下一句",
                "ESC 返回主菜单（会二次确认，并自动存档）",
                "F5 打开保存  |  F9 打开读取  |  F10 设置",
                "F12 截图模式：隐藏对话框/姓名框/功能按钮；任意按键或鼠标左右键恢复",
                slot_hint,
                "A 读取自动存档（仅读档界面）",
                "TAB 切换快进 | 按住 S 快进 | H 历史记录 | F11 全屏",
                f"帮助菜单：右键 或 {key_name}",
                "",
                "鼠标交互：右上角 × 关闭；保存/读取可点槽位和翻页；设置可拖动滑块。",
            ]
            lines: list[str] = []
            for ln in base_lines:
                if not ln:
                    lines.append("")
                else:
                    lines.extend(self._wrap_text_lines(ln, font, aw))

            line_h = font.get_linesize() + 2
            total_h = len(lines) * line_h
            max_scroll = max(0, total_h - ah)
            self._overlay_scroll_offset = max(0, min(int(self._overlay_scroll_offset), int(max_scroll)))

            content = pygame.Surface((aw, ah), pygame.SRCALPHA)
            y = -int(self._overlay_scroll_offset)
            for ln in lines:
                if y > ah:
                    break
                if ln:
                    surf = font.render(ln, True, text_color)
                    if y + surf.get_height() >= 0:
                        content.blit(surf, (0, y))
                y += line_h
            overlay.blit(content, (ax, ay))
            hint = font.render("滚轮滚动 | 点击 × 关闭", True, hint_color)
            overlay.blit(hint, (ax, ay + ah + 14))
            self.render_surface.blit(overlay, (0, 0))
            return

        if ot == "settings":
            overlay, cfg, font, title_font, hit = self._render_function_menu_common("settings", title="设置")
            self._overlay_hitboxes.update(hit)
            text_color = self._overlay_color(cfg.get("text_color"), (230, 230, 230))
            hint_color = self._overlay_color(cfg.get("hint_color"), (200, 200, 200))
            hover_color = self._overlay_color(cfg.get("hover_color"), (255, 255, 255))

            slider_pos = cfg.get("slider_pos", [80, 140])
            try:
                sx, sy = int(slider_pos[0]), int(slider_pos[1])
            except Exception:
                sx, sy = 80, 140
            try:
                sw = int(cfg.get("slider_width", self.render_size[0] - 160))
            except Exception:
                sw = self.render_size[0] - 160
            try:
                sh = int(cfg.get("slider_height", 10))
            except Exception:
                sh = 10
            try:
                gap = int(cfg.get("slider_gap", 70))
            except Exception:
                gap = 70
            sw = max(80, sw)
            sh = max(6, sh)

            items = [
                ("typing_speed", "文本速度"),
                ("master_volume", "主音量"),
                ("bgm_volume", "BGM音量"),
                ("voice_volume", "语音音量"),
                ("sfx_volume", "音效音量"),
            ]
            for i, (key, label) in enumerate(items):
                y = sy + i * gap
                bar = pygame.Rect(sx, y, sw, sh)
                self._overlay_hitboxes[f"slider:{key}"] = bar

                if key == "typing_speed":
                    v = float(self.typing_speed)
                    t = (v - 4.0) / (120.0 - 4.0)
                    t = max(0.0, min(1.0, t))
                    value_text = f"{v:.1f}"
                else:
                    v = float(self._settings.get(key, 1.0))
                    v = max(0.0, min(1.0, v))
                    t = v
                    value_text = f"{v:.2f}"

                lab_color = hover_color if self._overlay_hover == f"slider:{key}" else text_color
                lab = font.render(f"{label}: {value_text}", True, lab_color)
                overlay.blit(lab, (sx, y - lab.get_height() - 8))

                track = pygame.Surface((bar.w, bar.h), pygame.SRCALPHA)
                track.fill((255, 255, 255, 60))
                overlay.blit(track, (bar.x, bar.y))
                fill_w = int(bar.w * t)
                if fill_w > 0:
                    fill = pygame.Surface((fill_w, bar.h), pygame.SRCALPHA)
                    fill.fill((255, 255, 255, 110))
                    overlay.blit(fill, (bar.x, bar.y))
                knob_x = bar.x + fill_w
                pygame.draw.circle(overlay, (255, 255, 255), (knob_x, bar.y + bar.h // 2), max(6, bar.h))

            btn_pos = cfg.get("button_row_pos", [80, self.render_size[1] - 90])
            try:
                bx, by = int(btn_pos[0]), int(btn_pos[1])
            except Exception:
                bx, by = 80, self.render_size[1] - 90
            bsize = cfg.get("button_size", [120, 36])
            try:
                bw, bh = int(bsize[0]), int(bsize[1])
            except Exception:
                bw, bh = 120, 36
            bw = max(60, bw)
            bh = max(26, bh)

            save_rect = pygame.Rect(bx, by, bw, bh)
            cancel_rect = pygame.Rect(bx + bw + 20, by, bw, bh)
            self._overlay_hitboxes["settings_save"] = save_rect
            self._overlay_hitboxes["settings_cancel"] = cancel_rect

            for key, rect, text in (
                ("settings_save", save_rect, "保存"),
                ("settings_cancel", cancel_rect, "取消"),
            ):
                a = 70 if self._overlay_hover == key else 50
                btn = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
                btn.fill((255, 255, 255, a))
                overlay.blit(btn, rect.topleft)
                ts = title_font.render(text, True, (255, 255, 255))
                overlay.blit(ts, (rect.x + (rect.w - ts.get_width()) // 2, rect.y + (rect.h - ts.get_height()) // 2))

            hint = font.render("拖动滑块调整 | 点击 × 关闭（等同取消）", True, hint_color)
            overlay.blit(hint, (bx, by + bh + 14))
            self.render_surface.blit(overlay, (0, 0))
            return

        if ot in {"save", "load"}:
            ps = self._active_slot_page_size(ot)
            pages = page_count(self._save_slots, ps)
            self._save_page = clamp_page(self._save_page, self._save_slots, ps)
            page_tip = f"第{self._save_page + 1}/{pages}页"
            title = f"保存 {page_tip}" if ot == "save" else f"读取 {page_tip}"

            overlay, cfg, font, _title_font, hit = self._render_function_menu_common(ot, title=title)
            self._overlay_hitboxes.update(hit)
            text_color = self._overlay_color(cfg.get("text_color"), (230, 230, 230))
            hint_color = self._overlay_color(cfg.get("hint_color"), (200, 200, 200))

            slots = self._read_slots_meta()

            list_pos = cfg.get("slot_list_pos", [40, 120])
            try:
                lx, ly = int(list_pos[0]), int(list_pos[1])
            except Exception:
                lx, ly = 40, 120
            try:
                lw = int(cfg.get("slot_list_width", self.render_size[0] - 80))
            except Exception:
                lw = self.render_size[0] - 80
            try:
                rh = int(cfg.get("slot_row_height", 34))
            except Exception:
                rh = 34
            try:
                sp = int(cfg.get("slot_row_spacing", 8))
            except Exception:
                sp = 8
            try:
                bg_a = int(cfg.get("slot_bg_alpha", 90))
            except Exception:
                bg_a = 90
            try:
                hov_a = int(cfg.get("slot_hover_alpha", 140))
            except Exception:
                hov_a = 140
            rh = max(20, rh)
            lw = max(100, lw)
            bg_a = max(0, min(255, bg_a))
            hov_a = max(0, min(255, hov_a))

            y = ly
            if ot == "load":
                slot_id = AUTO_SAVE_SLOT
                meta = slots.get(slot_id)
                line = "自动存档  " + (f"{meta.get('timestamp','')} - {meta.get('summary','')}" if meta else "<空>")
                rect = pygame.Rect(lx, y, lw, rh)
                self._overlay_slot_hitboxes.append((slot_id, rect))
                a = hov_a if self._overlay_hover == f"slot:{slot_id}" else bg_a
                row = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
                row.fill((255, 255, 255, a))
                overlay.blit(row, rect.topleft)

                # thumbnail
                thumb_h = max(24, rect.h - 6)
                ratio = float(self.render_size[0]) / float(self.render_size[1]) if self.render_size[1] else 1.6
                thumb_w = max(40, min(180, int(thumb_h * ratio)))
                tx0 = rect.x + 10
                ty0 = rect.y + (rect.h - thumb_h) // 2
                box = pygame.Surface((thumb_w, thumb_h), pygame.SRCALPHA)
                box.fill((0, 0, 0, 90))
                overlay.blit(box, (tx0, ty0))
                thumb = self._load_slot_thumbnail_surface(slot_id, (thumb_w, thumb_h))
                if thumb is not None:
                    overlay.blit(thumb, (tx0, ty0))

                surf = font.render(line, True, text_color)
                text_x = tx0 + thumb_w + 12
                overlay.blit(surf, (text_x, rect.y + (rect.h - surf.get_height()) // 2))
                y += rh + sp

            start = self._save_page * ps + 1
            end = min(self._save_slots, start + ps - 1)
            for slot_id in range(start, end + 1):
                meta = slots.get(slot_id)
                line = f"槽位{slot_id}  " + (f"{meta.get('timestamp','')} - {meta.get('summary','')}" if meta else "<空>")
                rect = pygame.Rect(lx, y, lw, rh)
                self._overlay_slot_hitboxes.append((slot_id, rect))
                a = hov_a if self._overlay_hover == f"slot:{slot_id}" else bg_a
                row = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
                row.fill((255, 255, 255, a))
                overlay.blit(row, rect.topleft)

                thumb_h = max(24, rect.h - 6)
                ratio = float(self.render_size[0]) / float(self.render_size[1]) if self.render_size[1] else 1.6
                thumb_w = max(40, min(180, int(thumb_h * ratio)))
                tx0 = rect.x + 10
                ty0 = rect.y + (rect.h - thumb_h) // 2
                box = pygame.Surface((thumb_w, thumb_h), pygame.SRCALPHA)
                box.fill((0, 0, 0, 90))
                overlay.blit(box, (tx0, ty0))
                thumb = self._load_slot_thumbnail_surface(slot_id, (thumb_w, thumb_h))
                if thumb is not None:
                    overlay.blit(thumb, (tx0, ty0))

                surf = font.render(line, True, text_color)
                text_x = tx0 + thumb_w + 12
                overlay.blit(surf, (text_x, rect.y + (rect.h - surf.get_height()) // 2))
                y += rh + sp

            prev_pos = cfg.get("page_prev_pos", [40, self.render_size[1] - 60])
            next_pos = cfg.get("page_next_pos", [140, self.render_size[1] - 60])
            page_text_pos = cfg.get("page_text_pos", [240, self.render_size[1] - 60])
            try:
                px, py = int(prev_pos[0]), int(prev_pos[1])
            except Exception:
                px, py = 40, self.render_size[1] - 60
            try:
                nx, ny = int(next_pos[0]), int(next_pos[1])
            except Exception:
                nx, ny = 140, self.render_size[1] - 60
            try:
                tx, ty = int(page_text_pos[0]), int(page_text_pos[1])
            except Exception:
                tx, ty = 240, self.render_size[1] - 60

            btn_w, btn_h = 80, 34
            prev_rect = pygame.Rect(px, py, btn_w, btn_h)
            next_rect = pygame.Rect(nx, ny, btn_w, btn_h)
            self._overlay_hitboxes["page_prev"] = prev_rect
            self._overlay_hitboxes["page_next"] = next_rect
            for key, rect, text in (
                ("page_prev", prev_rect, "上一页"),
                ("page_next", next_rect, "下一页"),
            ):
                a = 70 if self._overlay_hover == key else 50
                btn = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
                btn.fill((255, 255, 255, a))
                overlay.blit(btn, rect.topleft)
                ts = font.render(text, True, (255, 255, 255))
                overlay.blit(ts, (rect.x + (rect.w - ts.get_width()) // 2, rect.y + (rect.h - ts.get_height()) // 2))

            tip = font.render(page_tip + " | 点击 × 关闭", True, hint_color)
            overlay.blit(tip, (tx, ty + 6))
            self.render_surface.blit(overlay, (0, 0))
            return

    def _render_function_menu_history_overlay(self):
        self._overlay_hitboxes = {}
        self._overlay_slot_hitboxes = []

        overlay, cfg, font, _title_font, hit = self._render_function_menu_common("history", title="历史记录")
        self._overlay_hitboxes.update(hit)
        text_color = self._overlay_color(cfg.get("text_color"), (230, 230, 230))
        hint_color = self._overlay_color(cfg.get("hint_color"), (200, 200, 200))

        area = cfg.get("text_area", [40, 100, self.render_size[0] - 80, self.render_size[1] - 160])
        try:
            ax, ay, aw, ah = int(area[0]), int(area[1]), int(area[2]), int(area[3])
        except Exception:
            ax, ay, aw, ah = 40, 100, self.render_size[0] - 80, self.render_size[1] - 160
        aw = max(20, aw)
        ah = max(20, ah)

        lines: list[str] = []
        for item in reversed(self._history):
            speaker = item.get("speaker") or ""
            content = item.get("content") or ""
            if not content:
                continue
            txt = f"{speaker}: {content}" if speaker else content
            lines.extend(self._wrap_text_lines(txt, font, aw))
            lines.append("")

        line_h = font.get_linesize() + 2
        total_h = len(lines) * line_h
        max_scroll = max(0, total_h - ah)
        self._overlay_scroll_offset = max(0, min(int(self._overlay_scroll_offset), int(max_scroll)))

        content = pygame.Surface((aw, ah), pygame.SRCALPHA)
        y = -int(self._overlay_scroll_offset)
        for ln in lines:
            if y > ah:
                break
            if ln:
                surf = font.render(ln, True, text_color)
                if y + surf.get_height() >= 0:
                    content.blit(surf, (0, y))
            y += line_h
        overlay.blit(content, (ax, ay))

        hint = font.render("滚轮滚动 | 点击 × 关闭", True, hint_color)
        overlay.blit(hint, (ax, ay + ah + 14))
        self.render_surface.blit(overlay, (0, 0))

    def _render_overlay(self):
        if self._function_menus_enabled and self._overlay_type() in {"save", "load", "settings", "help"}:
            self._render_function_menu_overlay()
            return

        # legacy overlays: ensure mouse hit boxes are cleared
        self._overlay_hover = None
        self._overlay_hitboxes = {}
        self._overlay_slot_hitboxes = []

        overlay = pygame.Surface(self.render_size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        if self._help_overlay:
            title = "帮助 (右键/快捷键关闭)"
            title_surf = self.name_font.render(title, True, (255, 255, 255))
            overlay.blit(title_surf, (40, 40))
            y = 90
            key_name = self._help_hotkey_name or "F1"
            info_lines = [
                "基础：左键/Space/Enter 下一句",
                "ESC 返回主菜单（会二次确认，并自动存档）",
                "F5 打开保存  |  F9 打开读取  |  F10 设置",
                "↑/↓ 翻页（每页10个） | 数字 0-9 选择槽位（0=第10个）",
                "A 读取自动存档（仅读档界面）",
                "TAB 切换快进 | 按住 S 快进 | H 历史记录 | F11 全屏",
                f"帮助菜单：右键 或 {key_name}",
            ]
            for line in info_lines:
                surf = self.font.render(line, True, (230, 230, 230))
                overlay.blit(surf, (40, y))
                y += self.font.get_linesize() + 6
        elif self._settings_overlay:
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
            pages = page_count(self._save_slots, self._save_page_size)
            self._save_page = clamp_page(self._save_page, self._save_slots, self._save_page_size)
            page_tip = f"第{self._save_page + 1}/{pages}页"
            title = f"保存到槽位 (0-9) {page_tip}" if self._save_overlay else f"读取槽位 (0-9) {page_tip}"
            title_surf = self.name_font.render(title, True, (255, 255, 255))
            overlay.blit(title_surf, (40, 40))

            slots = self._read_slots_meta()
            y = 90
            if self._load_overlay:
                auto_meta = slots.get(AUTO_SAVE_SLOT)
                auto_line = "[A] 自动存档 "
                if auto_meta:
                    auto_line += f"{auto_meta.get('timestamp','')} - {auto_meta.get('summary','')}"
                else:
                    auto_line += "<空>"
                surf = self.font.render(auto_line, True, (220, 220, 240))
                overlay.blit(surf, (40, y))
                y += self.font.get_linesize() + 10

            start = self._save_page * self._save_page_size + 1
            end = min(self._save_slots, start + self._save_page_size - 1)
            for slot_id in range(start, end + 1):
                meta = slots.get(slot_id)
                digit = slot_id - start + 1
                # digit label: 1..9, 0 for 10th
                label = str(digit) if digit < 10 else "0"
                line = f"[{label}] (槽位{slot_id}) "
                if meta:
                    line += f"{meta.get('timestamp','')} - {meta.get('summary','')}"
                else:
                    line += "<空>"
                surf = self.font.render(line, True, (230, 230, 230))
                overlay.blit(surf, (40, y))
                y += self.font.get_linesize() + 6

            hint = "↑↓翻页 | ESC 取消" if (self._save_overlay or self._load_overlay) else ""
            if hint:
                hint_surf = self.font.render(hint, True, (200, 200, 200))
                overlay.blit(hint_surf, (40, y + 10))

        self.render_surface.blit(overlay, (0, 0))

    def _render_choice_overlay(self):
        # Custom choice button group from UI layout (mouse + hover zoom)
        if self._choice_buttons_enabled:
            overlay = pygame.Surface(self.render_size, pygame.SRCALPHA)
            if int(self._choice_overlay_alpha) > 0:
                overlay.fill((0, 0, 0, int(self._choice_overlay_alpha)))

            # Build stable layout positions using UNZOOMED sizes.
            base_size = max(8, int(float(self._choice_button_font_size) * float(self._choice_button_scale)))
            choice_font = self._load_font(base_size)
            pad_x, pad_y = self._choice_button_padding
            min_w, min_h = self._choice_button_min_size
            center_x, center_y = self._choice_button_pos
            spacing = int(self._choice_button_spacing)
            zoom = float(self._choice_button_hover_zoom)

            raw_bg = None
            bg_path = (self._choice_button_bg_image or "").strip()
            if bg_path:
                p = self._resolve_path(bg_path)
                if p.exists():
                    key = str(p)
                    raw_bg = self._choice_button_bg_surface_cache.get(key)
                    if raw_bg is None:
                        try:
                            raw_bg = pygame.image.load(str(p)).convert_alpha()
                            self._choice_button_bg_surface_cache[key] = raw_bg
                        except Exception:
                            raw_bg = None

            # reset hitboxes to match current options
            self._choice_button_hitboxes = [None] * len(self._choice_options)

            layout: list[dict] = []

            # Pre-compute base sizes (unzoomed) per option.
            sizes: list[tuple[int, int]] = []
            labels: list[str] = []
            for text in self._choice_options:
                label = str(text)
                labels.append(label)
                text_surf = choice_font.render(label, True, (255, 255, 255))
                bw = max(int(min_w), int(text_surf.get_width() + pad_x * 2))
                bh = max(int(min_h), int(text_surf.get_height() + pad_y * 2))
                sizes.append((int(bw), int(bh)))

            cx, cy = int(center_x), int(center_y)
            if self._choice_button_orientation == "horizontal":
                total_w = sum(w for w, _ in sizes) + spacing * max(0, len(sizes) - 1)
                cur_x = int(cx - total_w / 2)
                for idx, (label, (bw, bh)) in enumerate(zip(labels, sizes)):
                    y = int(cy - bh / 2)
                    layout.append({
                        "idx": idx,
                        "label": label,
                        "x": int(cur_x),
                        "y": int(y),
                        "w": int(bw),
                        "h": int(bh),
                    })
                    cur_x += int(bw) + spacing
            else:
                total_h = sum(h for _, h in sizes) + spacing * max(0, len(sizes) - 1)
                cur_y = int(cy - total_h / 2)
                for idx, (label, (bw, bh)) in enumerate(zip(labels, sizes)):
                    x = int(cx - bw / 2)
                    layout.append({
                        "idx": idx,
                        "label": label,
                        "x": int(x),
                        "y": int(cur_y),
                        "w": int(bw),
                        "h": int(bh),
                    })
                    cur_y += int(bh) + spacing

            for it in layout:
                idx = int(it["idx"])
                sel = idx == int(self._choice_selected)
                x0 = int(it["x"])
                y0 = int(it["y"])
                bw = int(it["w"])
                bh = int(it["h"])
                z = float(zoom if sel else 1.0)
                w = max(1, int(bw * z))
                h = max(1, int(bh * z))
                dx = x0 - (w - bw) // 2
                dy = y0 - (h - bh) // 2

                if raw_bg is not None:
                    try:
                        img = pygame.transform.smoothscale(raw_bg, (w, h))
                    except Exception:
                        img = pygame.transform.scale(raw_bg, (w, h))
                    if int(self._choice_button_bg_alpha) != 255:
                        try:
                            img = img.copy()
                            img.set_alpha(int(self._choice_button_bg_alpha))
                        except Exception:
                            pass
                    overlay.blit(img, (dx, dy))
                else:
                    box = pygame.Surface((w, h), pygame.SRCALPHA)
                    box.fill((0, 0, 0, 140))
                    overlay.blit(box, (dx, dy))
                    try:
                        pygame.draw.rect(overlay, (255, 255, 255, 120), pygame.Rect(dx, dy, w, h), width=2)
                    except Exception:
                        pass

                base_col = self._choice_button_text_color
                hov_col = self._choice_button_text_hover_color
                col = hov_col if sel else base_col
                label = str(it.get("label") or "")
                txt = choice_font.render(label, True, col)
                if z != 1.0:
                    try:
                        tw = max(1, int(txt.get_width() * z))
                        th = max(1, int(txt.get_height() * z))
                        txt = pygame.transform.smoothscale(txt, (tw, th))
                    except Exception:
                        pass
                tx = int(dx + w / 2 - txt.get_width() / 2)
                ty = int(dy + h / 2 - txt.get_height() / 2)
                overlay.blit(txt, (tx, ty))

                if 0 <= idx < len(self._choice_button_hitboxes):
                    self._choice_button_hitboxes[idx] = pygame.Rect(dx, dy, w, h)

            hint = "ESC 取消 | 鼠标点击选择 | 数字键 1-9"
            hint_surf = self.font.render(hint, True, (200, 200, 200))
            overlay.blit(hint_surf, (40, self.render_size[1] - 50))

            self.render_surface.blit(overlay, (0, 0))
            return

        # Default choice overlay (keyboard digits)
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

        # autosave
        auto_path = slot_file_path(self.save_dir, AUTO_SAVE_SLOT)
        if auto_path.exists():
            try:
                with open(auto_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                thumb_path = slot_thumbnail_path(self.save_dir, AUTO_SAVE_SLOT)
                meta[AUTO_SAVE_SLOT] = {
                    "timestamp": data.get("timestamp", ""),
                    "summary": data.get("summary", ""),
                    "thumbnail": str(thumb_path) if thumb_path.exists() else "",
                }
            except Exception:
                pass

        for idx in range(1, self._save_slots + 1):
            path = slot_file_path(self.save_dir, idx)
            if not path.exists():
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                thumb_path = slot_thumbnail_path(self.save_dir, idx)
                meta[idx] = {
                    "timestamp": data.get("timestamp", ""),
                    "summary": data.get("summary", ""),
                    "thumbnail": str(thumb_path) if thumb_path.exists() else "",
                }
            except Exception:
                continue
        return meta

    def _render_exit_confirm_overlay(self):
        overlay = pygame.Surface(self.render_size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 190))

        title = "返回主菜单？"
        title_surf = self.name_font.render(title, True, (255, 255, 255))
        overlay.blit(title_surf, (40, 40))

        msg = "将自动保存到【自动存档】。"
        msg_surf = self.font.render(msg, True, (220, 220, 220))
        overlay.blit(msg_surf, (40, 90))

        y = 140
        yes_color = (255, 255, 255) if self._exit_confirm_choice == 1 else (180, 180, 180)
        no_color = (255, 255, 255) if self._exit_confirm_choice == 0 else (180, 180, 180)
        yes = self.font.render("[确认] Enter/Space/Y", True, yes_color)
        no = self.font.render("[取消] ESC/N", True, no_color)
        overlay.blit(yes, (60, y))
        overlay.blit(no, (60, y + self.font.get_linesize() + 10))

        hint = "←/→ 或 ↑/↓ 切换选项"
        hint_surf = self.font.render(hint, True, (200, 200, 200))
        overlay.blit(hint_surf, (40, y + 90))

        self.render_surface.blit(overlay, (0, 0))

    def _load_settings(self) -> dict:
        defaults = {
            "typing_speed": 24.0,
            "master_volume": 1.0,
            "bgm_volume": 0.6,
            "voice_volume": 1.0,
            "sfx_volume": 1.0,
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
        sfx_volume = float(self._settings.get("sfx_volume", 1.0))
        sfx_volume = max(0.0, min(1.0, sfx_volume))
        self._settings["sfx_volume"] = sfx_volume
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
        self._stop_sfx_playback()
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

"""Configuration management for EveGoggles."""
import json
import os
from dataclasses import dataclass, field, asdict
from typing import Optional

CONFIG_PATH = os.path.expanduser("~/.config/evegoggles/config.json")


@dataclass
class ThumbnailConfig:
    x: int = 0
    y: int = 0
    width: int = 320
    height: int = 180
    opacity: float = 0.9


@dataclass
class AppConfig:
    active_preset: str = "default"
    refresh_rate_ms: int = 200          # thumbnail refresh interval
    highlight_color: str = "#00aaff"    # active client border color
    highlight_thickness: int = 3
    thumbnail_opacity: float = 0.9
    auto_minimize_inactive: bool = False
    show_client_name: bool = True
    hotkey_cycle_next: str = "<ctrl>+<shift>+<next>"      # Ctrl+Shift+PageDown
    hotkey_cycle_prev: str = "<ctrl>+<shift>+<prior>"     # Ctrl+Shift+PageUp
    hotkey_toggle_thumbnails: str = "<ctrl>+<shift>+h"
    snap_to_grid: bool = True
    snap_grid_size: int = 20
    window_filter: str = "EVE - "       # window title prefix to match
    preview_monitor_index: int = 1      # 0 = leftmost monitor, 1 = tweede monitor
    last_window_positions: dict = field(default_factory=dict)


def load_config() -> AppConfig:
    if not os.path.exists(CONFIG_PATH):
        return AppConfig()
    try:
        with open(CONFIG_PATH, "r") as f:
            data = json.load(f)
        cfg = AppConfig()
        for k, v in data.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
        return cfg
    except Exception:
        return AppConfig()


def save_config(cfg: AppConfig) -> None:
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(asdict(cfg), f, indent=2)

"""Layout preset management - static JSON + dynamic tile modes."""
import json
import math
import os
from dataclasses import dataclass, field, asdict
from typing import Optional, TYPE_CHECKING

PRESETS_DIR = os.path.expanduser("~/.config/evegoggles/presets")
BUNDLED_PRESETS_DIR = os.path.join(os.path.dirname(__file__), "..", "presets")


@dataclass
class ThumbnailLayout:
    index: int
    x: int
    y: int
    width: int
    height: int


@dataclass
class Preset:
    name: str
    description: str
    mode: str = "static"          # "static" | "mining" | "productivity"
    thumbnails: list[ThumbnailLayout] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Preset":
        thumbnails = [ThumbnailLayout(**t) for t in d.get("thumbnails", [])]
        return Preset(
            name=d["name"],
            description=d.get("description", ""),
            mode=d.get("mode", "static"),
            thumbnails=thumbnails,
        )

    def is_dynamic(self) -> bool:
        return self.mode in ("stacked", "mosaic")


def compute_mosaic_layout(
    n_clients: int,
    preview_monitor_x: int,
    preview_monitor_y: int,
    preview_monitor_w: int,
    preview_monitor_h: int,
    aspect_ratio: float = 16 / 9,  # unused, kept for consistent signature
) -> list[ThumbnailLayout]:
    """
    Fill the entire preview monitor with thumbnails in the best grid layout.
    Uses ceil(sqrt(n)) columns to produce the most square-ish grid, which
    gives well-proportioned cells on widescreen monitors.
      n=1  → 1×1
      n=2  → 2×1
      n=3  → 2×2  (1 empty slot bottom-right)
      n=4  → 2×2
      n=5  → 3×2  (1 empty slot)
      n=6  → 3×2
      n=7  → 3×3  (2 empty slots)
      n=8  → 3×3  (1 empty slot)
      n=9  → 3×3
    """
    if n_clients < 1:
        return []

    cols = math.ceil(math.sqrt(n_clients))
    rows = math.ceil(n_clients / cols)

    # Fill each cell completely — no aspect ratio constraint
    thumb_w = preview_monitor_w // cols
    thumb_h = preview_monitor_h // rows

    layouts = []
    for i in range(n_clients):
        row = i // cols
        col = i % cols
        layouts.append(ThumbnailLayout(
            index=i,
            x=preview_monitor_x + col * thumb_w,
            y=preview_monitor_y + row * thumb_h,
            width=thumb_w,
            height=thumb_h,
        ))
    return layouts


def compute_stacked_layout(
    n_clients: int,
    preview_monitor_x: int,
    preview_monitor_y: int,
    preview_monitor_w: int,
    preview_monitor_h: int,
    max_column_pct: float = 0.25,
    aspect_ratio: float = 16 / 9,
) -> list[ThumbnailLayout]:
    """
    Vertical column on the left side of the preview monitor, max 25% width.
    Height is derived from width / aspect_ratio to preserve source proportions.
    """
    if n_clients < 1:
        return []

    col_w = int(preview_monitor_w * max_column_pct)
    thumb_h_from_width = int(col_w / aspect_ratio)
    thumb_h_max = preview_monitor_h // n_clients
    if thumb_h_from_width <= thumb_h_max:
        thumb_h = thumb_h_from_width
    else:
        # Stack would overflow — derive width from max height instead
        thumb_h = thumb_h_max
        col_w = int(thumb_h * aspect_ratio)

    layouts = []
    for i in range(n_clients):
        layouts.append(ThumbnailLayout(
            index=i,
            x=preview_monitor_x,
            y=preview_monitor_y + i * thumb_h,
            width=col_w,
            height=thumb_h,
        ))
    return layouts


# ── File IO ───────────────────────────────────────────────────────────────────

def _load_file(path: str) -> Optional[Preset]:
    try:
        with open(path) as f:
            return Preset.from_dict(json.load(f))
    except Exception:
        return None


def load_all_presets() -> dict[str, Preset]:
    presets: dict[str, Preset] = {}
    for d in [BUNDLED_PRESETS_DIR, PRESETS_DIR]:
        if not os.path.isdir(d):
            continue
        for fname in sorted(os.listdir(d)):
            if fname.endswith(".json"):
                p = _load_file(os.path.join(d, fname))
                if p:
                    presets[p.name] = p
    return presets


def save_preset(preset: Preset) -> None:
    os.makedirs(PRESETS_DIR, exist_ok=True)
    safe = preset.name.lower().replace(" ", "_")
    path = os.path.join(PRESETS_DIR, f"{safe}.json")
    with open(path, "w") as f:
        json.dump(preset.to_dict(), f, indent=2)

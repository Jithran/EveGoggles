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
    mode: str = "static"          # "static" | "stacked" | "mosaic" | "zone"
    thumbnails: list[ThumbnailLayout] = field(default_factory=list)
    # Zone mode parameters (ignored for other modes)
    zone_x_pct: float = 0.0       # left edge as fraction of monitor width  (0–1)
    zone_y_pct: float = 0.0       # top edge as fraction of monitor height (0–1)
    zone_w_pct: float = 1.0       # zone width as fraction of monitor width
    zone_h_pct: float = 1.0       # zone height as fraction of monitor height
    zone_fill: str = "grid"       # "grid" | "column" | "row"
    zone_lock_aspect: bool = False
    zone_reverse: bool = False    # fill in reverse order (bottom-up / right-to-left)

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
            zone_x_pct=d.get("zone_x_pct", 0.0),
            zone_y_pct=d.get("zone_y_pct", 0.0),
            zone_w_pct=d.get("zone_w_pct", 1.0),
            zone_h_pct=d.get("zone_h_pct", 1.0),
            zone_fill=d.get("zone_fill", "grid"),
            zone_lock_aspect=d.get("zone_lock_aspect", False),
            zone_reverse=d.get("zone_reverse", False),
        )

    def is_dynamic(self) -> bool:
        return self.mode in ("stacked", "mosaic", "zone")


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


def compute_zone_layout(
    n_clients: int,
    monitor_x: int,
    monitor_y: int,
    monitor_w: int,
    monitor_h: int,
    zone_x_pct: float,
    zone_y_pct: float,
    zone_w_pct: float,
    zone_h_pct: float,
    fill_mode: str = "grid",
    lock_aspect: bool = False,
    reverse: bool = False,
    aspect_ratio: float = 16 / 9,
) -> list[ThumbnailLayout]:
    """
    Fill a user-defined rectangular zone with thumbnails.

    The zone is expressed as fractions of the monitor (0.0–1.0) so the
    layout stays correct across different resolutions and monitor sizes.

    fill_mode:
      "grid"   — mini-mosaic; cells stretch to fill the zone
      "column" — vertical stack; lock_aspect preserves game AR
      "row"    — horizontal row; lock_aspect preserves game AR

    reverse:
      column → fills bottom-up instead of top-down
      row    → fills right-to-left instead of left-to-right
      grid   → fills from bottom-right instead of top-left
    """
    if n_clients < 1:
        return []

    zone_x = monitor_x + int(zone_x_pct * monitor_w)
    zone_y = monitor_y + int(zone_y_pct * monitor_h)
    zone_w = max(1, int(zone_w_pct * monitor_w))
    zone_h = max(1, int(zone_h_pct * monitor_h))

    if fill_mode == "grid":
        layouts = compute_mosaic_layout(n_clients, zone_x, zone_y, zone_w, zone_h)
        if reverse:
            cols = math.ceil(math.sqrt(n_clients))
            rows = math.ceil(n_clients / cols)
            thumb_w = zone_w // cols
            thumb_h = zone_h // rows
            layouts = [
                ThumbnailLayout(
                    index=i,
                    x=zone_x + (cols - 1 - (i % cols)) * thumb_w,
                    y=zone_y + (rows - 1 - (i // cols)) * thumb_h,
                    width=thumb_w,
                    height=thumb_h,
                )
                for i in range(n_clients)
            ]
        return layouts

    if fill_mode == "column":
        if lock_aspect:
            layouts = compute_stacked_layout(
                n_clients, zone_x, zone_y, zone_w, zone_h,
                max_column_pct=1.0,   # zone width is already the column
                aspect_ratio=aspect_ratio,
            )
            if reverse:
                # Flip y-positions within the zone
                total_h = sum(l.height for l in layouts)
                bottom = zone_y + zone_h
                layouts = [
                    ThumbnailLayout(l.index, l.x, bottom - total_h + (total_h - l.height - (l.y - zone_y)), l.width, l.height)
                    for l in layouts
                ]
            return layouts
        thumb_h = zone_h // n_clients
        if reverse:
            return [
                ThumbnailLayout(i, zone_x, zone_y + zone_h - (i + 1) * thumb_h, zone_w, thumb_h)
                for i in range(n_clients)
            ]
        return [
            ThumbnailLayout(i, zone_x, zone_y + i * thumb_h, zone_w, thumb_h)
            for i in range(n_clients)
        ]

    if fill_mode == "row":
        if lock_aspect:
            thumb_h = zone_h
            thumb_w = int(thumb_h * aspect_ratio)
            max_w = zone_w // n_clients
            if thumb_w > max_w:
                thumb_w = max_w
                thumb_h = int(thumb_w / aspect_ratio)
        else:
            thumb_w = zone_w // n_clients
            thumb_h = zone_h
        if reverse:
            return [
                ThumbnailLayout(i, zone_x + zone_w - (i + 1) * thumb_w, zone_y, thumb_w, thumb_h)
                for i in range(n_clients)
            ]
        return [
            ThumbnailLayout(i, zone_x + i * thumb_w, zone_y, thumb_w, thumb_h)
            for i in range(n_clients)
        ]

    return []


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

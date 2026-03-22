"""Main application logic - discovery, background capture, hotkeys, presets."""
import time
from typing import Optional

from PyQt6.QtCore import QTimer, QThread, pyqtSignal, QObject, QRect
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication

from .config import AppConfig, save_config
from .window_manager import WindowManager, EveWindow
from .thumbnail import ThumbnailWidget
from .hotkeys import HotkeyManager
from .presets import (
    Preset, ThumbnailLayout, load_all_presets, save_preset,
    compute_mosaic_layout, compute_stacked_layout,
)
from . import capture


# ── Background capture thread ─────────────────────────────────────────────────

class CaptureThread(QThread):
    """Captures all EVE window thumbnails in a background thread."""
    frame_ready = pyqtSignal(int, QPixmap)   # xid, pixmap

    def __init__(self, parent=None):
        super().__init__(parent)
        self._targets: list[tuple[int, int, int]] = []  # (xid, tw, th)
        self._interval_ms: int = 100
        self._running = False
        self._disp = None

    def set_targets(self, targets: list[tuple[int, int, int]]) -> None:
        self._targets = targets

    def set_interval(self, ms: int) -> None:
        self._interval_ms = ms

    def run(self):
        self._running = True
        self._disp = capture.make_display()
        while self._running:
            t0 = time.monotonic()
            for xid, tw, th in list(self._targets):
                if not self._running:
                    break
                img = capture.capture_xid(self._disp, xid, tw, th)
                if img:
                    pix = capture.pil_to_qpixmap(img)
                    self.frame_ready.emit(xid, pix)
            elapsed = (time.monotonic() - t0) * 1000
            sleep = max(0.0, self._interval_ms - elapsed)
            if sleep > 0:
                time.sleep(sleep / 1000)

    def stop(self):
        self._running = False
        if self._disp:
            try:
                self._disp.close()
            except Exception:
                pass
            self._disp = None
        self.quit()
        self.wait(2000)


# ── Main app ──────────────────────────────────────────────────────────────────

class EveGogglesApp:
    def __init__(self, config: AppConfig, qt_app: QApplication):
        self._cfg = config
        self._qt = qt_app
        self._wm = WindowManager(config.window_filter)
        self._hotkeys = HotkeyManager()
        self._thumbnails: dict[int, ThumbnailWidget] = {}   # xid → widget
        self._eve_windows: list[EveWindow] = []
        self._active_idx: int = 0
        self._presets = load_all_presets()
        self._visible = True
        self._locked = False

        # Background capture thread
        self._capture_thread = CaptureThread()
        self._capture_thread.frame_ready.connect(self._on_frame_ready)
        self._capture_thread.set_interval(self._cfg.refresh_rate_ms)

        # Discovery timer (slow: every 2s)
        self._discover_timer = QTimer()
        self._discover_timer.timeout.connect(self._discover_windows)
        self._discover_timer.setInterval(2000)

        # Active window highlight timer (fast: 200ms)
        self._active_timer = QTimer()
        self._active_timer.timeout.connect(self._update_active_from_wm)
        self._active_timer.setInterval(200)

        self._setup_hotkeys()

    # ── Monitor detection ─────────────────────────────────────────────────────

    def get_monitors(self) -> list[QRect]:
        """Return monitor rects (full geometry) sorted left to right."""
        screens = self._qt.screens()
        rects = [s.geometry() for s in screens]
        rects.sort(key=lambda r: r.x())
        return rects

    def get_preview_monitor(self) -> QRect:
        """Return the configured preview monitor rect (full geometry)."""
        monitors = self.get_monitors()
        idx = min(self._cfg.preview_monitor_index, len(monitors) - 1)
        return monitors[idx] if monitors else QRect(0, 0, 1920, 1080)

    def _taskbar_height(self) -> int:
        """Detect taskbar/panel height.
        On Wayland/XWayland, Qt's availableGeometry() often returns the full
        monitor height. Fall back to querying _NET_WORKAREA via Xlib, which
        always reflects the actual usable area set by the window manager.
        """
        primary = self._qt.primaryScreen()
        if primary:
            reserved = primary.geometry().height() - primary.availableGeometry().height()
            if reserved > 0:
                return reserved

        # Fallback: read _NET_WORKAREA from X11 root window
        try:
            from Xlib import display as xdisplay
            disp = xdisplay.Display()
            root = disp.screen().root
            atom = disp.intern_atom("_NET_WORKAREA")
            prop = root.get_full_property(atom, 0)
            disp.close()
            if prop and len(prop.value) >= 4:
                workarea_h = prop.value[3]   # height of usable area
                screen_h = self._qt.primaryScreen().geometry().height() if primary else 1080
                return max(0, screen_h - workarea_h)
        except Exception:
            pass
        return 0

    def get_preview_monitor_available(self) -> QRect:
        """Return available geometry of the preview monitor, excluding taskbar/panels."""
        screens = sorted(self._qt.screens(), key=lambda s: s.geometry().x())
        idx = min(self._cfg.preview_monitor_index, len(screens) - 1)
        if screens:
            geom = screens[idx].geometry()
            reserved = self._taskbar_height()
            return QRect(geom.x(), geom.y(), geom.width(), geom.height() - reserved)
        return QRect(0, 0, 1920, 1040)

    def get_game_monitor(self) -> QRect:
        screens = sorted(self._qt.screens(), key=lambda s: s.geometry().x())
        return screens[-1].geometry() if screens else QRect(1920, 0, 1920, 1080)

    def set_preview_monitor(self, index: int) -> None:
        self._cfg.preview_monitor_index = index

    # ── Hotkeys ───────────────────────────────────────────────────────────────

    def _setup_hotkeys(self):
        self._hotkeys.update({
            self._cfg.hotkey_cycle_next: self._cycle_next,
            self._cfg.hotkey_cycle_prev: self._cycle_prev,
            self._cfg.hotkey_toggle_thumbnails: self._toggle_thumbnails,
        })

    def _cycle_next(self):
        if not self._eve_windows:
            return
        self._active_idx = (self._active_idx + 1) % len(self._eve_windows)
        self._wm.activate(self._eve_windows[self._active_idx])

    def _cycle_prev(self):
        if not self._eve_windows:
            return
        self._active_idx = (self._active_idx - 1) % len(self._eve_windows)
        self._wm.activate(self._eve_windows[self._active_idx])

    def _toggle_thumbnails(self):
        self._visible = not self._visible
        for w in self._thumbnails.values():
            w.setVisible(self._visible)

    # ── Window discovery ──────────────────────────────────────────────────────

    def _discover_windows(self):
        found = self._wm.discover()
        found_xids = {w.xid for w in found}
        current_xids = set(self._thumbnails.keys())
        layout_changed = bool((found_xids - current_xids) or (current_xids - found_xids))

        for xid in current_xids - found_xids:
            self._thumbnails[xid].close()
            del self._thumbnails[xid]

        for win in found:
            if win.xid not in self._thumbnails:
                tw = ThumbnailWidget(
                    xid=win.xid,
                    title=win.title,
                    short_name=win.short_name,
                    on_activate=self._on_thumbnail_activate,
                    on_resize=self._on_thumbnail_resize,
                    snap_grid=self._cfg.snap_grid_size if self._cfg.snap_to_grid else 0,
                )
                tw.set_highlight(self._cfg.highlight_color, self._cfg.highlight_thickness)
                tw.set_client_name_visible(self._cfg.show_client_name)
                tw.set_locked(self._locked)
                if self._cfg.thumbnail_opacity < 1.0:
                    tw.set_opacity(self._cfg.thumbnail_opacity)
                tw.show()
                self._thumbnails[win.xid] = tw

        self._eve_windows = found
        self._update_capture_targets()

        # Re-apply active dynamic preset whenever client count changes
        if layout_changed and self._cfg.active_preset in self._presets:
            preset = self._presets[self._cfg.active_preset]
            if preset.is_dynamic():
                self.apply_preset(preset)

    def _update_capture_targets(self):
        targets = []
        for win in self._eve_windows:
            tw = self._thumbnails.get(win.xid)
            if tw:
                targets.append((win.xid, tw.width(), tw.height()))
        self._capture_thread.set_targets(targets)

    # ── Frame handling ────────────────────────────────────────────────────────

    def _on_frame_ready(self, xid: int, pixmap: QPixmap):
        tw = self._thumbnails.get(xid)
        if tw:
            tw.update_pixmap(pixmap)

    def _update_active_from_wm(self):
        active_xid = self._wm.get_active_xid()
        for xid, tw in self._thumbnails.items():
            tw.set_active(xid == active_xid)
        if active_xid:
            for i, win in enumerate(self._eve_windows):
                if win.xid == active_xid:
                    self._active_idx = i
                    break

    def _on_thumbnail_activate(self, xid: int):
        for win in self._eve_windows:
            if win.xid == xid:
                self._wm.activate(win)
                break

    def _on_thumbnail_resize(self, source_xid: int, w: int, h: int):
        """Sync all other thumbnails to the same size as the one being resized."""
        if not self._cfg.sync_resize:
            return
        for xid, tw in self._thumbnails.items():
            if xid != source_xid:
                tw.resize(w, h)
        self._update_capture_targets()

    # ── Lock ─────────────────────────────────────────────────────────────────

    def set_locked(self, locked: bool):
        self._locked = locked
        for tw in self._thumbnails.values():
            tw.set_locked(locked)

    # ── Presets ───────────────────────────────────────────────────────────────

    def _get_source_aspect_ratio(self) -> float:
        """Return aspect ratio based on the game monitor (always accurate via Qt)."""
        gm = self.get_game_monitor()
        if gm.height() > 0:
            return gm.width() / gm.height()
        return 16 / 9

    def apply_preset(self, preset: Preset):
        n = len(self._eve_windows)
        pm = self.get_preview_monitor_available()
        ar = self._get_source_aspect_ratio()
        if preset.mode == "mosaic":
            layouts = compute_mosaic_layout(
                n, pm.x(), pm.y(), pm.width(), pm.height(),
                aspect_ratio=ar,
            )
        elif preset.mode == "stacked":
            layouts = compute_stacked_layout(
                n, pm.x(), pm.y(), pm.width(), pm.height(),
                aspect_ratio=ar,
            )
        else:
            layouts = preset.thumbnails

        for layout in layouts:
            if layout.index < len(self._eve_windows):
                win = self._eve_windows[layout.index]
                tw = self._thumbnails.get(win.xid)
                if tw:
                    tw.move(layout.x, layout.y)
                    tw.resize(layout.width, layout.height)

        self._cfg.active_preset = preset.name
        self._update_capture_targets()

    def save_current_as_preset(self, name: str, description: str = "") -> Preset:
        layouts = []
        for i, win in enumerate(self._eve_windows):
            tw = self._thumbnails.get(win.xid)
            if tw:
                state = tw.get_layout_state()
                layouts.append(ThumbnailLayout(
                    index=i,
                    x=state["x"], y=state["y"],
                    width=state["width"], height=state["height"],
                ))
        preset = Preset(name=name, description=description, thumbnails=layouts)
        save_preset(preset)
        self._presets[name] = preset
        return preset

    def get_presets(self) -> dict[str, Preset]:
        return self._presets

    def reload_presets(self):
        self._presets = load_all_presets()

    # ── Refresh rate ──────────────────────────────────────────────────────────

    def set_refresh_rate(self, ms: int):
        self._cfg.refresh_rate_ms = ms
        self._capture_thread.set_interval(ms)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        self._hotkeys.start()
        self._discover_windows()        # immediate first scan
        self._discover_timer.start()
        self._active_timer.start()
        self._capture_thread.start()
        # Auto-apply last used preset after windows are discovered
        if self._cfg.active_preset in self._presets and self._eve_windows:
            QTimer.singleShot(500, lambda: self.apply_preset(
                self._presets[self._cfg.active_preset]
            ))

    def stop(self):
        self._capture_thread.stop()
        self._hotkeys.stop()
        self._discover_timer.stop()
        self._active_timer.stop()
        self._save_positions()
        save_config(self._cfg)
        for tw in self._thumbnails.values():
            tw.close()

    def _save_positions(self):
        for xid, tw in self._thumbnails.items():
            self._cfg.last_window_positions[str(xid)] = tw.get_layout_state()

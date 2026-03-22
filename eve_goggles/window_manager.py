"""X11 window discovery and activation for EveGoggles."""
import subprocess
import time
from dataclasses import dataclass
from typing import Optional

from Xlib import X, display as xdisplay
from Xlib.ext import composite
from ewmh import EWMH


@dataclass
class EveWindow:
    xid: int
    title: str
    pid: int
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0

    @property
    def short_name(self) -> str:
        """Return character name from 'EVE - CharName' title."""
        if " - " in self.title:
            return self.title.split(" - ", 1)[1]
        return self.title


class WindowManager:
    def __init__(self, window_filter: str = "EVE - "):
        self._filter = window_filter
        self._ewmh = EWMH()
        self._display = xdisplay.Display()
        self._composite_available = self._init_composite()

    def _init_composite(self) -> bool:
        try:
            composite.query_version(self._display, 0, 4)
            return True
        except Exception:
            return False

    def discover(self) -> list[EveWindow]:
        """Return list of EVE windows currently open."""
        windows = []
        try:
            client_list = self._ewmh.getClientList()
            if not client_list:
                return windows
            for win in client_list:
                try:
                    title = self._ewmh.getWmName(win)
                    if isinstance(title, bytes):
                        title = title.decode("utf-8", errors="replace")
                    if not title or self._filter not in title:
                        continue
                    pid = self._ewmh.getWmPid(win) or 0
                    geom = self._get_geometry(win.id)
                    windows.append(EveWindow(
                        xid=win.id,
                        title=title,
                        pid=pid,
                        x=geom[0],
                        y=geom[1],
                        width=geom[2],
                        height=geom[3],
                    ))
                except Exception:
                    continue
        except Exception:
            pass
        return windows

    def _get_geometry(self, xid: int) -> tuple[int, int, int, int]:
        try:
            win = self._display.create_resource_object("window", xid)
            geom = win.get_geometry()
            # Translate to screen coords
            translated = win.translate_coords(self._display.screen().root, 0, 0)
            return (translated.x, translated.y, geom.width, geom.height)
        except Exception:
            return (0, 0, 800, 600)

    def activate(self, eve_win: EveWindow) -> None:
        """Bring EVE window to foreground and give it focus."""
        try:
            win = self._display.create_resource_object("window", eve_win.xid)
            self._ewmh.setActiveWindow(win)
            self._ewmh.display.flush()
            # Also use xdotool as fallback for focus
            subprocess.run(
                ["xdotool", "windowactivate", "--sync", str(eve_win.xid)],
                capture_output=True, timeout=2
            )
        except Exception:
            try:
                subprocess.run(
                    ["wmctrl", "-ia", hex(eve_win.xid)],
                    capture_output=True, timeout=2
                )
            except Exception:
                pass

    def get_active_xid(self) -> Optional[int]:
        """Return XID of currently focused window."""
        try:
            win = self._ewmh.getActiveWindow()
            return win.id if win else None
        except Exception:
            return None

    def capture_screenshot(self, eve_win: EveWindow) -> Optional[bytes]:
        """Capture window as PNG bytes using scrot/import."""
        try:
            result = subprocess.run(
                ["import", "-window", str(eve_win.xid), "png:-"],
                capture_output=True, timeout=3
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout
        except Exception:
            pass
        # Fallback: use xwd + convert
        try:
            xwd = subprocess.run(
                ["xwd", "-id", str(eve_win.xid), "-silent"],
                capture_output=True, timeout=3
            )
            if xwd.returncode == 0:
                result = subprocess.run(
                    ["convert", "xwd:-", "png:-"],
                    input=xwd.stdout, capture_output=True, timeout=3
                )
                if result.returncode == 0:
                    return result.stdout
        except Exception:
            pass
        return None

    def capture_region(self, x: int, y: int, w: int, h: int) -> Optional[bytes]:
        """Capture screen region as PNG bytes (for visible windows)."""
        try:
            result = subprocess.run(
                ["import", "-window", "root",
                 "-crop", f"{w}x{h}+{x}+{y}", "+repage", "png:-"],
                capture_output=True, timeout=3
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout
        except Exception:
            pass
        return None

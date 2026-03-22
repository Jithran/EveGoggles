"""Global hotkey listener using python-xlib XGrabKey (no evdev needed)."""
import select
import threading
from typing import Callable, Optional

from Xlib import X, XK
from Xlib import display as xdisplay
from Xlib import error as xerror


_MOD_MAP = {
    "ctrl":  X.ControlMask,
    "shift": X.ShiftMask,
    "alt":   X.Mod1Mask,
    "mod4":  X.Mod4Mask,
}

_MASK_STRIP = X.ControlMask | X.ShiftMask | X.Mod1Mask | X.Mod4Mask


def _parse_combo(combo: str) -> tuple[int, str]:
    parts = [p.strip("<>") for p in combo.lower().split("+")]
    mods, key = 0, ""
    for part in parts:
        if part in _MOD_MAP:
            mods |= _MOD_MAP[part]
        else:
            key = part
    return mods, key


def _silent_error_handler(err, req):
    """Suppress BadAccess on XGrabKey (key already grabbed by another app)."""
    pass


class HotkeyManager:
    def __init__(self):
        self._bindings: dict[str, Callable] = {}
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._disp = None

    def update(self, bindings: dict[str, Callable]) -> None:
        self._bindings = bindings
        self.start()

    def start(self) -> None:
        self.stop()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._listen, daemon=True, name="hotkeys")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._disp:
            try:
                self._disp.close()
            except Exception:
                pass
            self._disp = None
        if self._thread:
            self._thread.join(timeout=1)
            self._thread = None

    def _listen(self):
        disp = None
        root = None
        grabbed: list[tuple[int, int, Callable]] = []
        try:
            disp = xdisplay.Display()
            self._disp = disp
            # Suppress BadAccess errors from XGrabKey (key already taken)
            disp.set_error_handler(_silent_error_handler)
            root = disp.screen().root

            for combo, cb in self._bindings.items():
                mods, keyname = _parse_combo(combo)
                keysym = XK.string_to_keysym(keyname)
                if keysym == 0:
                    keysym = XK.string_to_keysym(keyname.capitalize())
                if keysym == 0:
                    continue
                keycode = disp.keysym_to_keycode(keysym)
                if keycode == 0:
                    continue
                # Grab with common modifier lock combinations
                for extra in [0, X.Mod2Mask, X.LockMask, X.Mod2Mask | X.LockMask]:
                    root.grab_key(keycode, mods | extra, True,
                                  X.GrabModeAsync, X.GrabModeAsync)
                grabbed.append((mods, keycode, cb))

            disp.flush()

            while not self._stop_event.is_set():
                r, _, _ = select.select([disp.fileno()], [], [], 0.1)
                if not r:
                    continue
                while disp.pending_events():
                    event = disp.next_event()
                    if event.type == X.KeyPress:
                        pressed_mods = event.state & _MASK_STRIP
                        for mods, keycode, cb in grabbed:
                            if event.detail == keycode and pressed_mods == mods:
                                try:
                                    cb()
                                except Exception:
                                    pass
        except Exception:
            pass
        finally:
            if root and disp:
                try:
                    root.ungrab_key(X.AnyKey, X.AnyModifier)
                    disp.flush()
                    disp.close()
                except Exception:
                    pass

"""Fast window thumbnail capture - XGetImage in dedicated thread context."""
import io
from typing import Optional

from Xlib import X, display as xdisplay, error as xerror
from PIL import Image


def make_display() -> object:
    """Create a fresh Display connection (one per thread)."""
    return xdisplay.Display()


def capture_xid(disp, xid: int, target_w: int, target_h: int) -> Optional[Image.Image]:
    """Capture window by XID and return resized PIL Image. Thread-safe when
    each thread passes its own Display instance."""
    try:
        win = disp.create_resource_object("window", xid)
        geom = win.get_geometry()
        w, h = geom.width, geom.height
        if w < 1 or h < 1:
            return None
        raw = win.get_image(0, 0, w, h, X.ZPixmap, 0xFFFFFFFF)
        # BGRA → RGB
        img = Image.frombytes("RGBA", (w, h), raw.data, "raw", "BGRA")
        img = img.convert("RGB")
        img = img.resize((target_w, target_h), Image.BILINEAR)  # faster than LANCZOS
        return img
    except xerror.BadDrawable:
        return None
    except xerror.BadMatch:
        return _capture_region_fallback(disp, xid, target_w, target_h)
    except Exception:
        return None


def _capture_region_fallback(disp, xid: int, target_w: int, target_h: int) -> Optional[Image.Image]:
    """XComposite fallback for occluded/minimized windows."""
    try:
        from Xlib.ext import composite
        win = disp.create_resource_object("window", xid)
        composite.redirect_window(win, composite.RedirectAutomatic)
        disp.sync()
        pixmap = win.composite_name_window_pixmap()
        geom = win.get_geometry()
        w, h = geom.width, geom.height
        if w < 1 or h < 1:
            return None
        raw = pixmap.get_image(0, 0, w, h, X.ZPixmap, 0xFFFFFFFF)
        img = Image.frombytes("RGBA", (w, h), raw.data, "raw", "BGRA")
        img = img.convert("RGB")
        img = img.resize((target_w, target_h), Image.BILINEAR)
        pixmap.free()
        return img
    except Exception:
        return None


def pil_to_qpixmap(img: Image.Image):
    """Convert PIL Image to QPixmap WITHOUT going through PNG (much faster)."""
    from PyQt6.QtGui import QImage, QPixmap
    img_rgb = img.convert("RGB")
    data = img_rgb.tobytes("raw", "RGB")
    w, h = img_rgb.size
    qimg = QImage(data, w, h, w * 3, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimg.copy())  # .copy() detaches from the bytes buffer

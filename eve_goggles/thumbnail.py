"""Floating thumbnail widget for a single EVE client."""
from typing import Callable, Optional

from PyQt6.QtCore import Qt, QPoint, QRect
from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor, QCursor, QFont
from PyQt6.QtWidgets import QWidget, QLabel


RESIZE_HANDLE = 16   # px corner resize zone
DRAG_THRESHOLD = 4   # px minimum move to count as drag


class ThumbnailWidget(QWidget):
    """Frameless, draggable, resizable EVE client preview."""

    def __init__(
        self,
        xid: int,
        title: str,
        short_name: str,
        on_activate: Callable[[int], None],
        snap_grid: int = 0,
        parent=None,
    ):
        super().__init__(parent)
        self.xid = xid
        self.title = title
        self.short_name = short_name
        self._on_activate = on_activate
        self._snap_grid = snap_grid

        self._locked = False
        self._is_active = False
        self._highlight_color = "#00aaff"
        self._highlight_thickness = 3

        self._drag_pos: Optional[QPoint] = None
        self._drag_start: Optional[QPoint] = None
        self._did_drag = False
        self._resizing = False
        self._resize_start_pos: Optional[QPoint] = None
        self._resize_start_size: Optional[tuple[int, int]] = None

        self._setup_ui()

    def _setup_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        # No WA_TranslucentBackground - makes everything invisible on some compositors
        self.setStyleSheet("background: #111;")
        self.setMinimumSize(120, 68)
        self.resize(320, 180)

        self._img_label = QLabel(self)
        self._img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_label.setStyleSheet("background: #111;")
        self._img_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._name_label = QLabel(self.short_name, self)
        self._name_label.setStyleSheet(
            "color: white; background: rgba(0,0,0,170); "
            "padding: 1px 5px; font-size: 10px; border-radius: 2px;"
        )
        self._name_label.adjustSize()

        self._lock_label = QLabel("🔒", self)
        self._lock_label.setStyleSheet(
            "color: white; background: rgba(0,0,0,170); "
            "padding: 1px 3px; font-size: 10px; border-radius: 2px;"
        )
        self._lock_label.adjustSize()
        self._lock_label.hide()

    def _img_inset(self) -> int:
        return self._highlight_thickness if self._is_active else 0

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_img_geometry()
        self._name_label.move(4, 4)
        self._lock_label.move(self.width() - self._lock_label.width() - 4, 4)

    def _update_img_geometry(self):
        i = self._img_inset()
        self._img_label.setGeometry(i, i, self.width() - 2 * i, self.height() - 2 * i)

    # ── Public API ────────────────────────────────────────────────────────────

    def update_pixmap(self, pixmap: QPixmap) -> None:
        scaled = pixmap.scaled(
            self._img_label.size(),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        self._img_label.setPixmap(scaled)

    def set_active(self, active: bool) -> None:
        if self._is_active != active:
            self._is_active = active
            self._update_img_geometry()
            self.update()

    def set_highlight(self, color: str, thickness: int) -> None:
        self._highlight_color = color
        self._highlight_thickness = thickness
        self.update()

    def set_client_name_visible(self, visible: bool) -> None:
        self._name_label.setVisible(visible)

    def set_opacity(self, opacity: float) -> None:
        self.setWindowOpacity(opacity)

    def set_locked(self, locked: bool) -> None:
        self._locked = locked
        self._lock_label.setVisible(locked)
        self.update()

    def get_layout_state(self) -> dict:
        return {"x": self.x(), "y": self.y(), "width": self.width(), "height": self.height()}

    # ── Paint: active border ──────────────────────────────────────────────────

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._is_active:
            painter = QPainter(self)
            pen = QPen(QColor(self._highlight_color))
            pen.setWidth(self._highlight_thickness)
            painter.setPen(pen)
            half = self._highlight_thickness // 2
            painter.drawRect(half, half,
                             self.width() - self._highlight_thickness,
                             self.height() - self._highlight_thickness)

    # ── Mouse: drag + resize + click ─────────────────────────────────────────

    def _in_resize_zone(self, pos: QPoint) -> bool:
        return (pos.x() > self.width() - RESIZE_HANDLE and
                pos.y() > self.height() - RESIZE_HANDLE)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._locked:
            self._on_activate(self.xid)
            return
        if self._in_resize_zone(event.pos()):
            self._resizing = True
            self._resize_start_pos = event.globalPosition().toPoint()
            self._resize_start_size = (self.width(), self.height())
        else:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._drag_start = event.globalPosition().toPoint()
            self._did_drag = False

    def mouseMoveEvent(self, event):
        gpos = event.globalPosition().toPoint()

        if self._resizing and self._resize_start_pos and self._resize_start_size:
            delta = gpos - self._resize_start_pos
            new_w = max(120, self._resize_start_size[0] + delta.x())
            new_h = max(68,  self._resize_start_size[1] + delta.y())
            self.resize(new_w, new_h)
            self.setCursor(QCursor(Qt.CursorShape.SizeFDiagCursor))
            return

        if self._drag_pos is not None:
            if self._drag_start and (gpos - self._drag_start).manhattanLength() > DRAG_THRESHOLD:
                self._did_drag = True
            if self._did_drag:
                new_pos = gpos - self._drag_pos
                if self._snap_grid > 0:
                    g = self._snap_grid
                    new_pos.setX(round(new_pos.x() / g) * g)
                    new_pos.setY(round(new_pos.y() / g) * g)
                self.move(new_pos)
                self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
                return

        # Hover cursor hint
        if not self._locked and self._in_resize_zone(event.pos()):
            self.setCursor(QCursor(Qt.CursorShape.SizeFDiagCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        was_resizing = self._resizing
        self._resizing = False
        self._resize_start_pos = None
        self._drag_pos = None
        self._drag_start = None
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

        if not was_resizing and not self._did_drag:
            self._on_activate(self.xid)
        self._did_drag = False

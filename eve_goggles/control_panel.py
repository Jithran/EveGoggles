"""Control panel - preset picker, lock toggle, settings."""
import math
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QRect, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen, QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QListWidget, QGroupBox, QSlider, QCheckBox,
    QLineEdit, QDialog, QDialogButtonBox, QSpinBox, QColorDialog,
    QSystemTrayIcon, QGridLayout, QApplication,
)

from .presets import Preset


class SavePresetDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Save Preset")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Name:"))
        self.name_edit = QLineEdit()
        layout.addWidget(self.name_edit)
        layout.addWidget(QLabel("Description (optional):"))
        self.desc_edit = QLineEdit()
        layout.addWidget(self.desc_edit)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_values(self) -> tuple[str, str]:
        return self.name_edit.text().strip(), self.desc_edit.text().strip()


class ScreenSelectOverlay(QWidget):
    """Full-screen drag-to-select overlay for picking a zone on the monitor."""
    selection_made = pyqtSignal(float, float, float, float)  # x%, y%, w%, h% relative to monitor
    closed = pyqtSignal()

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.X11BypassWindowManagerHint |
            Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setCursor(Qt.CursorShape.CrossCursor)

        # Cover all screens
        all_rect = QRect()
        for screen in QApplication.instance().screens():
            all_rect = all_rect.united(screen.geometry())
        self._origin = all_rect.topLeft()
        self.setGeometry(all_rect)

        self._p1: Optional[QPoint] = None
        self._p2: Optional[QPoint] = None
        self._dragging = False

    def _sel_rect(self) -> Optional[QRect]:
        if self._p1 and self._p2:
            return QRect(self._p1, self._p2).normalized()
        return None

    def paintEvent(self, _):
        p = QPainter(self)

        # Dark overlay over everything
        p.fillRect(self.rect(), QColor(0, 0, 0, 110))

        sel = self._sel_rect()
        if sel:
            # Lighten the selected area
            p.fillRect(sel, QColor(255, 255, 255, 25))
            p.setPen(QPen(QColor(0, 170, 255), 2))
            p.drawRect(sel)
            # Corner handles
            p.setPen(QPen(QColor(0, 170, 255), 3))
            for cx, cy in [
                (sel.left(), sel.top()), (sel.right(), sel.top()),
                (sel.left(), sel.bottom()), (sel.right(), sel.bottom()),
            ]:
                p.drawLine(cx - 7, cy, cx + 7, cy)
                p.drawLine(cx, cy - 7, cx, cy + 7)
            # Size label near top-left of selection
            p.setPen(QColor(255, 255, 255))
            label_x = sel.x() + 4
            label_y = sel.y() - 6 if sel.y() > 20 else sel.y() + 18
            p.drawText(label_x, label_y, f"{sel.width()} × {sel.height()} px")

        # Instruction banner
        f = QFont()
        f.setPointSize(11)
        p.setFont(f)
        p.setPen(QColor(220, 220, 220))
        msg = "Drag to select zone — ESC to cancel"
        fm = p.fontMetrics()
        p.fillRect(
            (self.width() - fm.horizontalAdvance(msg)) // 2 - 8, 6,
            fm.horizontalAdvance(msg) + 16, fm.height() + 8,
            QColor(0, 0, 0, 160),
        )
        p.drawText(
            (self.width() - fm.horizontalAdvance(msg)) // 2,
            6 + fm.ascent() + 4,
            msg,
        )
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._p1 = event.position().toPoint()
            self._p2 = self._p1
            self._dragging = True

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._p2 = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            self._p2 = event.position().toPoint()
            sel = self._sel_rect()
            if sel and sel.width() > 5 and sel.height() > 5:
                # Find which monitor the selection center is on
                global_center = sel.center() + self._origin
                monitor_rect: Optional[QRect] = None
                for screen in QApplication.instance().screens():
                    if screen.geometry().contains(global_center):
                        monitor_rect = screen.geometry()
                        break
                if monitor_rect is None:
                    monitor_rect = QApplication.instance().primaryScreen().geometry()

                # Convert to percentages relative to that monitor
                sel_global = QRect(sel.topLeft() + self._origin, sel.size())
                x_pct = (sel_global.x() - monitor_rect.x()) / monitor_rect.width()
                y_pct = (sel_global.y() - monitor_rect.y()) / monitor_rect.height()
                w_pct = sel_global.width() / monitor_rect.width()
                h_pct = sel_global.height() / monitor_rect.height()
                # Clamp
                x_pct = max(0.0, min(0.99, x_pct))
                y_pct = max(0.0, min(0.99, y_pct))
                w_pct = max(0.01, min(1.0 - x_pct, w_pct))
                h_pct = max(0.01, min(1.0 - y_pct, h_pct))
                self.selection_made.emit(x_pct, y_pct, w_pct, h_pct)
            self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)


class ZonePreviewWidget(QWidget):
    """Paints a scaled monitor with the selected zone and thumbnail slots."""

    _MONITOR_BG   = QColor(30, 30, 30)
    _MONITOR_EDGE = QColor(70, 70, 70)
    _ZONE_FILL    = QColor(0, 120, 200, 50)
    _ZONE_EDGE    = QColor(0, 170, 255)
    _THUMB_FILL   = QColor(0, 170, 255, 35)
    _THUMB_EDGE   = QColor(0, 170, 255, 160)
    _ARROW_COL    = QColor(255, 200, 0)
    _N_PREVIEW    = 4   # number of fake clients shown in the preview

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(260, 146)   # ~16:9
        self._sx = 0.0
        self._sy = 0.0
        self._ex = 0.25
        self._ey = 1.0
        self._fill = "column"
        self._reverse = False

    def set_zone(self, sx: int, sy: int, ex: int, ey: int, fill: str, reverse: bool = False):
        self._sx = sx / 100
        self._sy = sy / 100
        self._ex = ex / 100
        self._ey = ey / 100
        self._fill = fill.lower()
        self._reverse = reverse
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()

        # Monitor background
        p.fillRect(0, 0, W, H, self._MONITOR_BG)
        p.setPen(QPen(self._MONITOR_EDGE, 1))
        p.drawRect(0, 0, W - 1, H - 1)

        # Zone rectangle
        zx = int(self._sx * W)
        zy = int(self._sy * H)
        zw = max(4, int((self._ex - self._sx) * W))
        zh = max(4, int((self._ey - self._sy) * H))
        p.fillRect(zx, zy, zw, zh, self._ZONE_FILL)
        p.setPen(QPen(self._ZONE_EDGE, 2))
        p.drawRect(zx, zy, zw, zh)

        # Thumbnail slots
        n = self._N_PREVIEW
        p.setPen(QPen(self._THUMB_EDGE, 1))
        if self._fill == "grid":
            cols = math.ceil(math.sqrt(n))
            rows = math.ceil(n / cols)
            tw = zw // cols
            th = zh // rows
            for i in range(n):
                row, col = divmod(i, cols)
                p.fillRect(zx + col * tw + 1, zy + row * th + 1, tw - 2, th - 2, self._THUMB_FILL)
                p.drawRect(zx + col * tw + 1, zy + row * th + 1, tw - 2, th - 2)
        elif self._fill == "column":
            th = zh // n
            for i in range(n):
                p.fillRect(zx + 1, zy + i * th + 1, zw - 2, th - 2, self._THUMB_FILL)
                p.drawRect(zx + 1, zy + i * th + 1, zw - 2, th - 2)
        elif self._fill == "row":
            tw = zw // n
            for i in range(n):
                p.fillRect(zx + i * tw + 1, zy + 1, tw - 2, zh - 2, self._THUMB_FILL)
                p.drawRect(zx + i * tw + 1, zy + 1, tw - 2, zh - 2)

        # Direction arrow inside the zone
        p.setPen(QPen(self._ARROW_COL, 2))
        cx = zx + zw // 2
        cy = zy + zh // 2
        aw = min(zw, zh) // 4
        if self._fill == "column":
            if self._reverse:
                # Arrow pointing up
                p.drawLine(cx, cy + aw, cx, cy - aw)
                p.drawLine(cx, cy - aw, cx - aw // 2, cy - aw // 2)
                p.drawLine(cx, cy - aw, cx + aw // 2, cy - aw // 2)
            else:
                # Arrow pointing down
                p.drawLine(cx, cy - aw, cx, cy + aw)
                p.drawLine(cx, cy + aw, cx - aw // 2, cy + aw // 2)
                p.drawLine(cx, cy + aw, cx + aw // 2, cy + aw // 2)
        elif self._fill == "row":
            if self._reverse:
                # Arrow pointing left
                p.drawLine(cx + aw, cy, cx - aw, cy)
                p.drawLine(cx - aw, cy, cx - aw // 2, cy - aw // 2)
                p.drawLine(cx - aw, cy, cx - aw // 2, cy + aw // 2)
            else:
                # Arrow pointing right
                p.drawLine(cx - aw, cy, cx + aw, cy)
                p.drawLine(cx + aw, cy, cx + aw // 2, cy - aw // 2)
                p.drawLine(cx + aw, cy, cx + aw // 2, cy + aw // 2)
        elif self._fill == "grid":
            # Grid symbol: small cross
            p.drawLine(cx - aw, cy, cx + aw, cy)
            p.drawLine(cx, cy - aw, cx, cy + aw)

        p.end()


class ZonePresetDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Zone Preset")
        self._original_name: Optional[str] = None
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Name:"))
        self.name_edit = QLineEdit()
        layout.addWidget(self.name_edit)

        layout.addWidget(QLabel("Description (optional):"))
        self.desc_edit = QLineEdit()
        layout.addWidget(self.desc_edit)

        zone_box = QGroupBox("Zone (% of monitor)")
        zl = QGridLayout(zone_box)
        zl.addWidget(QLabel("Start X:"), 0, 0)
        self.start_x = QSpinBox()
        self.start_x.setRange(0, 99)
        self.start_x.setSuffix("%")
        zl.addWidget(self.start_x, 0, 1)
        zl.addWidget(QLabel("Start Y:"), 0, 2)
        self.start_y = QSpinBox()
        self.start_y.setRange(0, 99)
        self.start_y.setSuffix("%")
        zl.addWidget(self.start_y, 0, 3)
        zl.addWidget(QLabel("End X:"), 1, 0)
        self.end_x = QSpinBox()
        self.end_x.setRange(1, 100)
        self.end_x.setSuffix("%")
        self.end_x.setValue(25)
        zl.addWidget(self.end_x, 1, 1)
        zl.addWidget(QLabel("End Y:"), 1, 2)
        self.end_y = QSpinBox()
        self.end_y.setRange(1, 100)
        self.end_y.setSuffix("%")
        self.end_y.setValue(100)
        zl.addWidget(self.end_y, 1, 3)
        select_btn = QPushButton("Select on screen...")
        select_btn.setToolTip("Hide this dialog and drag a rectangle on the monitor to set the zone")
        select_btn.clicked.connect(self._select_on_screen)
        zl.addWidget(select_btn, 2, 0, 1, 4)
        layout.addWidget(zone_box)

        fill_row = QHBoxLayout()
        fill_row.addWidget(QLabel("Fill mode:"))
        self.fill_combo = QComboBox()
        self.fill_combo.addItems(["Grid", "Column", "Row"])
        self.fill_combo.setCurrentText("Column")
        fill_row.addWidget(self.fill_combo)
        layout.addLayout(fill_row)

        self.lock_aspect_cb = QCheckBox("Lock aspect ratio")
        layout.addWidget(self.lock_aspect_cb)

        self.reverse_cb = QCheckBox("Reverse order (bottom-up / right-to-left)")
        layout.addWidget(self.reverse_cb)

        # Live visual preview
        preview_box = QGroupBox("Preview (4 clients)")
        pb = QVBoxLayout(preview_box)
        self._preview = ZonePreviewWidget()
        pb.addWidget(self._preview, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(preview_box)

        # Connect all inputs to preview update
        self.start_x.valueChanged.connect(self._update_preview)
        self.start_y.valueChanged.connect(self._update_preview)
        self.end_x.valueChanged.connect(self._update_preview)
        self.end_y.valueChanged.connect(self._update_preview)
        self.fill_combo.currentTextChanged.connect(self._update_preview)
        self.reverse_cb.toggled.connect(self._update_preview)
        self._update_preview()

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._validate_and_accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _select_on_screen(self):
        self._overlay = ScreenSelectOverlay()
        self._overlay.selection_made.connect(self._on_screen_selection)
        self._overlay.closed.connect(self.raise_)
        self._overlay.closed.connect(self.activateWindow)
        self._overlay.show()
        self._overlay.raise_()
        self._overlay.activateWindow()

    def _on_screen_selection(self, x_pct: float, y_pct: float, w_pct: float, h_pct: float):
        self.start_x.setValue(round(x_pct * 100))
        self.start_y.setValue(round(y_pct * 100))
        self.end_x.setValue(min(100, round((x_pct + w_pct) * 100)))
        self.end_y.setValue(min(100, round((y_pct + h_pct) * 100)))

    def prefill(self, preset: "Preset"):
        self._original_name = preset.name
        self.name_edit.setText(preset.name)
        self.desc_edit.setText(preset.description)
        self.start_x.setValue(int(preset.zone_x_pct * 100))
        self.start_y.setValue(int(preset.zone_y_pct * 100))
        self.end_x.setValue(int((preset.zone_x_pct + preset.zone_w_pct) * 100))
        self.end_y.setValue(int((preset.zone_y_pct + preset.zone_h_pct) * 100))
        self.fill_combo.setCurrentText(preset.zone_fill.capitalize())
        self.lock_aspect_cb.setChecked(preset.zone_lock_aspect)
        self.reverse_cb.setChecked(preset.zone_reverse)

    def _update_preview(self, *_):
        self._preview.set_zone(
            self.start_x.value(), self.start_y.value(),
            self.end_x.value(), self.end_y.value(),
            self.fill_combo.currentText(),
            reverse=self.reverse_cb.isChecked(),
        )

    def _validate_and_accept(self):
        if not self.name_edit.text().strip():
            self.name_edit.setPlaceholderText("Name is required")
            return
        if self.end_x.value() <= self.start_x.value():
            self.end_x.setStyleSheet("border: 1px solid red;")
            return
        if self.end_y.value() <= self.start_y.value():
            self.end_y.setStyleSheet("border: 1px solid red;")
            return
        self.accept()

    def get_values(self) -> dict:
        sx = self.start_x.value() / 100
        sy = self.start_y.value() / 100
        ex = self.end_x.value() / 100
        ey = self.end_y.value() / 100
        return {
            "name": self.name_edit.text().strip(),
            "description": self.desc_edit.text().strip(),
            "original_name": self._original_name,
            "zone_x_pct": sx,
            "zone_y_pct": sy,
            "zone_w_pct": ex - sx,
            "zone_h_pct": ey - sy,
            "zone_fill": self.fill_combo.currentText().lower(),
            "zone_lock_aspect": self.lock_aspect_cb.isChecked(),
            "zone_reverse": self.reverse_cb.isChecked(),
        }


class ControlPanel(QWidget):
    preset_requested = pyqtSignal(str)
    save_preset_requested = pyqtSignal(str, str)
    zone_preset_requested = pyqtSignal(dict)
    preset_delete_requested = pyqtSignal(str)
    settings_changed = pyqtSignal(dict)
    lock_toggled = pyqtSignal(bool)
    monitor_changed = pyqtSignal(int)   # preview monitor index
    quit_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("EveGoggles")
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)
        self.resize(300, 580)
        self._locked = False
        self._presets: dict = {}
        self._deletable: set = set()
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)

        title = QLabel("<b>EveGoggles</b>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(title)

        # ── Monitor info ──────────────────────────────────────────────────────
        mon_box = QGroupBox("Monitors")
        ml = QVBoxLayout(mon_box)
        self.monitor_info = QLabel("Detecting...")
        self.monitor_info.setStyleSheet("font-size: 10px; color: gray;")
        self.monitor_info.setWordWrap(True)
        ml.addWidget(self.monitor_info)
        mon_row = QHBoxLayout()
        mon_row.addWidget(QLabel("Preview monitor:"))
        self.monitor_combo = QComboBox()
        self.monitor_combo.currentIndexChanged.connect(
            lambda i: self.monitor_changed.emit(i))
        mon_row.addWidget(self.monitor_combo)
        ml.addLayout(mon_row)
        root.addWidget(mon_box)

        # ── Client list ───────────────────────────────────────────────────────
        clients_box = QGroupBox("Active EVE Clients")
        cl = QVBoxLayout(clients_box)
        self.client_list = QListWidget()
        self.client_list.setMaximumHeight(100)
        cl.addWidget(self.client_list)
        root.addWidget(clients_box)

        # ── Presets ───────────────────────────────────────────────────────────
        preset_box = QGroupBox("Presets")
        pl = QVBoxLayout(preset_box)
        self.preset_combo = QComboBox()
        pl.addWidget(self.preset_combo)

        self.preset_desc = QLabel("")
        self.preset_desc.setWordWrap(True)
        self.preset_desc.setStyleSheet("color: gray; font-size: 10px;")
        pl.addWidget(self.preset_desc)

        btn_row = QHBoxLayout()
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.clicked.connect(self._apply_preset)
        self.save_btn = QPushButton("Save Current")
        self.save_btn.clicked.connect(self._save_preset)
        btn_row.addWidget(self.apply_btn)
        btn_row.addWidget(self.save_btn)
        pl.addLayout(btn_row)

        self.zone_btn = QPushButton("New Zone...")
        self.zone_btn.setToolTip(
            "Create a dynamic preset that fills a custom area of the monitor"
        )
        self.zone_btn.clicked.connect(self._create_zone_preset)
        pl.addWidget(self.zone_btn)

        edit_del_row = QHBoxLayout()
        self.edit_btn = QPushButton("Edit")
        self.edit_btn.setEnabled(False)
        self.edit_btn.clicked.connect(self._edit_preset)
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self._delete_preset)
        edit_del_row.addWidget(self.edit_btn)
        edit_del_row.addWidget(self.delete_btn)
        pl.addLayout(edit_del_row)

        root.addWidget(preset_box)

        self.preset_combo.currentTextChanged.connect(self._on_preset_selected)

        # ── Lock ──────────────────────────────────────────────────────────────
        self.lock_btn = QPushButton("🔓 Lock Thumbnails")
        self.lock_btn.setCheckable(True)
        self.lock_btn.setStyleSheet("font-weight: bold;")
        self.lock_btn.toggled.connect(self._on_lock_toggled)
        root.addWidget(self.lock_btn)

        # ── Settings ──────────────────────────────────────────────────────────
        settings_box = QGroupBox("Settings")
        sl = QVBoxLayout(settings_box)

        self.show_names_cb = QCheckBox("Show client names")
        self.show_names_cb.setChecked(True)
        self.show_names_cb.toggled.connect(
            lambda v: self.settings_changed.emit({"show_client_name": v}))
        sl.addWidget(self.show_names_cb)

        self.snap_cb = QCheckBox("Snap to grid")
        self.snap_cb.setChecked(True)
        self.snap_cb.toggled.connect(
            lambda v: self.settings_changed.emit({"snap_to_grid": v}))
        sl.addWidget(self.snap_cb)

        self.sync_resize_cb = QCheckBox("Sync resize (all same size)")
        self.sync_resize_cb.setChecked(True)
        self.sync_resize_cb.toggled.connect(
            lambda v: self.settings_changed.emit({"sync_resize": v}))
        sl.addWidget(self.sync_resize_cb)

        opacity_row = QHBoxLayout()
        opacity_row.addWidget(QLabel("Opacity:"))
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(20, 100)
        self.opacity_slider.setValue(90)
        self.opacity_val = QLabel("90%")
        self.opacity_slider.valueChanged.connect(
            lambda v: (
                self.opacity_val.setText(f"{v}%"),
                self.settings_changed.emit({"thumbnail_opacity": v / 100})
            ))
        opacity_row.addWidget(self.opacity_slider)
        opacity_row.addWidget(self.opacity_val)
        sl.addLayout(opacity_row)

        refresh_row = QHBoxLayout()
        refresh_row.addWidget(QLabel("Refresh (ms):"))
        self.refresh_spin = QSpinBox()
        self.refresh_spin.setRange(30, 2000)
        self.refresh_spin.setSingleStep(10)
        self.refresh_spin.setValue(100)
        self.refresh_spin.valueChanged.connect(
            lambda v: self.settings_changed.emit({"refresh_rate_ms": v}))
        refresh_row.addWidget(self.refresh_spin)
        sl.addLayout(refresh_row)

        highlight_row = QHBoxLayout()
        highlight_row.addWidget(QLabel("Active border:"))
        self.highlight_btn = QPushButton()
        self.highlight_btn.setFixedSize(40, 20)
        self._highlight_color = "#00aaff"
        self._update_highlight_button()
        self.highlight_btn.clicked.connect(self._pick_highlight_color)
        highlight_row.addWidget(self.highlight_btn)
        highlight_row.addStretch()
        sl.addLayout(highlight_row)

        root.addWidget(settings_box)

        # ── Hotkeys info ──────────────────────────────────────────────────────
        hint_box = QGroupBox("Hotkeys")
        hl = QVBoxLayout(hint_box)
        hl.addWidget(QLabel("Ctrl+Shift+PageDown → next client"))
        hl.addWidget(QLabel("Ctrl+Shift+PageUp   → previous client"))
        hl.addWidget(QLabel("Ctrl+Shift+H        → show/hide thumbnails"))
        root.addWidget(hint_box)

        quit_btn = QPushButton("Quit")
        quit_btn.clicked.connect(self.quit_requested.emit)
        root.addWidget(quit_btn)


    # ── Slots ─────────────────────────────────────────────────────────────────

    def update_monitors(self, rects, current_index: int = 0):
        """Populate monitor dropdown with detected screens."""
        self.monitor_combo.blockSignals(True)
        self.monitor_combo.clear()
        info_lines = []
        for i, r in enumerate(rects):
            label = f"Monitor {i}: {r.width()}×{r.height()} @ ({r.x()},{r.y()})"
            self.monitor_combo.addItem(label)
            info_lines.append(label)
        self.monitor_combo.setCurrentIndex(min(current_index, len(rects) - 1))
        self.monitor_info.setText("\n".join(info_lines) or "No monitors found")
        self.monitor_combo.blockSignals(False)

    def update_clients(self, names: list[str], active_idx: int = -1):
        self.client_list.clear()
        for i, name in enumerate(names):
            prefix = "▶ " if i == active_idx else "   "
            self.client_list.addItem(prefix + name)

    def load_presets(self, presets: dict[str, "Preset"], deletable: set[str] = None):
        self._presets = presets
        self._deletable = deletable or set()
        current = self.preset_combo.currentText()
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        for name in presets:
            self.preset_combo.addItem(name)
        if current in presets:
            self.preset_combo.setCurrentText(current)
        self.preset_combo.blockSignals(False)
        self._on_preset_selected(self.preset_combo.currentText())

    def _on_preset_selected(self, name: str):
        preset = self._presets.get(name)
        self.edit_btn.setEnabled(preset is not None and preset.mode in ("zone", "static"))
        self.delete_btn.setEnabled(name in self._deletable)

    def set_preset_description(self, desc: str):
        self.preset_desc.setText(desc)

    def _apply_preset(self):
        name = self.preset_combo.currentText()
        if name:
            self.preset_requested.emit(name)

    def _save_preset(self):
        dlg = SavePresetDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            name, desc = dlg.get_values()
            if name:
                self.save_preset_requested.emit(name, desc)

    def _on_lock_toggled(self, locked: bool):
        self._locked = locked
        if locked:
            self.lock_btn.setText("🔒 Thumbnails locked")
        else:
            self.lock_btn.setText("🔓 Lock Thumbnails")
        self.lock_toggled.emit(locked)

    def _create_zone_preset(self):
        dlg = ZonePresetDialog(self)
        dlg.setWindowModality(Qt.WindowModality.NonModal)
        dlg.accepted.connect(lambda: self.zone_preset_requested.emit(dlg.get_values()))
        dlg.show()
        self._zone_dlg = dlg   # keep reference to prevent garbage collection

    def _edit_preset(self):
        name = self.preset_combo.currentText()
        preset = self._presets.get(name)
        if not preset:
            return
        if preset.mode == "zone":
            dlg = ZonePresetDialog(self)
            dlg.setWindowModality(Qt.WindowModality.NonModal)
            dlg.prefill(preset)
            dlg.accepted.connect(lambda: self.zone_preset_requested.emit(dlg.get_values()))
            dlg.show()
            self._zone_dlg = dlg
        else:
            # Static preset: allow rename / description change
            dlg = SavePresetDialog(self)
            dlg.name_edit.setText(preset.name)
            dlg.desc_edit.setText(preset.description)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                new_name, new_desc = dlg.get_values()
                if new_name:
                    self.save_preset_requested.emit(new_name, new_desc)

    def _delete_preset(self):
        name = self.preset_combo.currentText()
        if name:
            self.preset_delete_requested.emit(name)

    def _pick_highlight_color(self):
        col = QColorDialog.getColor(QColor(self._highlight_color), self)
        if col.isValid():
            self._highlight_color = col.name()
            self._update_highlight_button()
            self.settings_changed.emit({"highlight_color": self._highlight_color})

    def _update_highlight_button(self):
        self.highlight_btn.setStyleSheet(
            f"background-color: {self._highlight_color}; border: 1px solid #555;")

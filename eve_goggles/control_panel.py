"""Control panel - preset picker, lock toggle, settings."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QListWidget, QGroupBox, QSlider, QCheckBox,
    QLineEdit, QDialog, QDialogButtonBox, QSpinBox, QColorDialog,
    QSystemTrayIcon,
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


class ControlPanel(QWidget):
    preset_requested = pyqtSignal(str)
    save_preset_requested = pyqtSignal(str, str)
    settings_changed = pyqtSignal(dict)
    lock_toggled = pyqtSignal(bool)
    monitor_changed = pyqtSignal(int)   # preview monitor index
    quit_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("EveGoggles")
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)
        self.resize(300, 560)
        self._locked = False
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
        self.refresh_spin.setRange(50, 2000)
        self.refresh_spin.setSingleStep(50)
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

    def load_presets(self, presets: dict[str, "Preset"]):
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
        # Will be connected externally to get description
        pass

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

    def _pick_highlight_color(self):
        col = QColorDialog.getColor(QColor(self._highlight_color), self)
        if col.isValid():
            self._highlight_color = col.name()
            self._update_highlight_button()
            self.settings_changed.emit({"highlight_color": self._highlight_color})

    def _update_highlight_button(self):
        self.highlight_btn.setStyleSheet(
            f"background-color: {self._highlight_color}; border: 1px solid #555;")

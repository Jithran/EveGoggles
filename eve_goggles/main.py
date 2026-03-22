"""EveGoggles entry point."""
import sys
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QColor, QPixmap, QPainter
from PyQt6.QtCore import QTimer, Qt

from .config import load_config, save_config
from .app import EveGogglesApp
from .control_panel import ControlPanel


def _make_tray_icon() -> QIcon:
    pix = QPixmap(32, 32)
    pix.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#00aaff"))
    painter.setPen(QColor("#0077cc"))
    painter.drawEllipse(2, 2, 28, 28)
    painter.setPen(QColor("white"))
    painter.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "EG")
    painter.end()
    return QIcon(pix)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("EveGoggles")
    app.setQuitOnLastWindowClosed(False)

    cfg = load_config()
    goggles = EveGogglesApp(cfg, app)

    panel = ControlPanel()
    panel.load_presets(goggles.get_presets())
    panel.opacity_slider.setValue(int(cfg.thumbnail_opacity * 100))
    panel.refresh_spin.setValue(cfg.refresh_rate_ms)
    panel.show_names_cb.setChecked(cfg.show_client_name)
    panel.snap_cb.setChecked(cfg.snap_to_grid)

    # Show detected monitors immediately
    monitors = goggles.get_monitors()
    panel.update_monitors(monitors, cfg.preview_monitor_index)

    # ── Signal wiring ─────────────────────────────────────────────────────────

    def on_preset(name):
        presets = goggles.get_presets()
        if name in presets:
            goggles.apply_preset(presets[name])
            panel.set_preset_description(presets[name].description)

    def on_save_preset(name, desc):
        goggles.save_current_as_preset(name, desc)
        panel.load_presets(goggles.get_presets())

    def on_settings(changes: dict):
        for k, v in changes.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
        for tw in goggles._thumbnails.values():
            if "highlight_color" in changes or "highlight_thickness" in changes:
                tw.set_highlight(cfg.highlight_color, cfg.highlight_thickness)
            if "show_client_name" in changes:
                tw.set_client_name_visible(cfg.show_client_name)
            if "thumbnail_opacity" in changes:
                tw.set_opacity(cfg.thumbnail_opacity)
        if "refresh_rate_ms" in changes:
            goggles.set_refresh_rate(cfg.refresh_rate_ms)
        if "snap_to_grid" in changes or "snap_grid_size" in changes:
            for tw in goggles._thumbnails.values():
                tw._snap_grid = cfg.snap_grid_size if cfg.snap_to_grid else 0

    def on_monitor_changed(index: int):
        goggles.set_preview_monitor(index)

    def on_quit():
        goggles.stop()
        save_config(cfg)
        app.quit()

    panel.preset_requested.connect(on_preset)
    panel.save_preset_requested.connect(on_save_preset)
    panel.settings_changed.connect(on_settings)
    panel.lock_toggled.connect(goggles.set_locked)
    panel.monitor_changed.connect(on_monitor_changed)
    panel.quit_requested.connect(on_quit)

    # Update client list in panel every second
    def update_panel():
        panel.update_clients(
            [w.short_name for w in goggles._eve_windows],
            active_idx=goggles._active_idx,
        )
    client_timer = QTimer()
    client_timer.timeout.connect(update_panel)
    client_timer.start(1000)

    # ── System tray ───────────────────────────────────────────────────────────
    tray = QSystemTrayIcon(_make_tray_icon(), parent=app)
    tray_menu = QMenu()
    show_action = tray_menu.addAction("Show Control Panel")
    show_action.triggered.connect(panel.show)
    toggle_action = tray_menu.addAction("Toggle Thumbnails")
    toggle_action.triggered.connect(goggles._toggle_thumbnails)
    tray_menu.addSeparator()
    quit_action = tray_menu.addAction("Quit")
    quit_action.triggered.connect(on_quit)
    tray.setContextMenu(tray_menu)
    tray.activated.connect(
        lambda r: panel.show() if r == QSystemTrayIcon.ActivationReason.Trigger else None
    )
    tray.setToolTip("EveGoggles")
    tray.show()

    panel.show()
    goggles.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

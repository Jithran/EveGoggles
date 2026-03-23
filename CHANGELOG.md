# Changelog

All notable changes to EveGoggles are documented here.

---

## [Unreleased]

### Added
- Zone preset type: define a custom rectangular area on the monitor (start/end as % of monitor) with fill mode (Grid, Column, Row), optional aspect-ratio lock, and optional reverse order (bottom-up / right-to-left); thumbnails are distributed dynamically within the zone whenever clients are added or removed
- "New Zone..." button in the Presets panel opens a dialog with a live visual preview to create and immediately apply a zone preset
- "Edit" button in the Presets panel to modify an existing zone or static preset
- "Delete" button in the Presets panel to remove a user-created preset
- Screenshot in `assets/screenshot01.png` added to README
- Application icon (`assets/evegoggles.svg`) — goggles design in the app's blue/cyan colour scheme, visible in the taskbar, start menu and alt-tab switcher
- `README.md` with project description, requirements, installation guide, usage instructions and troubleshooting
- Sync resize: resizing one thumbnail resizes all others simultaneously
- Ctrl+resize: hold Ctrl while resizing to lock aspect ratio to the starting dimensions
- Grid snapping for resize (reuses the existing snap grid setting)
- "Sync resize (all same size)" toggle in Settings panel
- `X11BypassWindowManagerHint` flag on thumbnails so they appear above fullscreen EVE windows
- `.gitignore` covering Python, virtualenv, IDE files and OS artefacts
- `CHANGELOG.md` (this file)

### Changed
- Minimum refresh rate lowered to 30 ms (~33 fps) with 10 ms steps, replacing the previous 50 ms minimum with 50 ms steps
- Preset system simplified to two dynamic modes: **Stacked** and **Mosaic**
  - **Stacked**: vertical column on the left (25% width), aspect ratio preserved, overflows clamped to available height
  - **Mosaic**: fills the entire preview monitor; cells stretch to fill the grid, no fixed aspect ratio; grid dimensions chosen to minimise empty slots
- Layout calculations now use `_NET_WORKAREA` via Xlib as a fallback when Qt's `availableGeometry()` reports the wrong height on Wayland/XWayland, preventing thumbnails from overlapping the taskbar
- Desktop shortcut failed to launch from the application menu because `Exec` used a relative path; now uses the absolute install path with a `Path=` working directory
- Mosaic grid for 3 clients produced a 3×1 row (very wide, barely any height); now correctly uses a 2×2 grid with one empty slot, matching the layout of 4 clients
- Active client border is now drawn correctly — the image label is inset by the border thickness when the thumbnail is active, so the painted border is no longer hidden behind the label
- Aspect ratio for Stacked layout is derived from the game monitor's Qt geometry (always accurate) instead of X11 window geometry (unreliable on Wayland)
- When a new EVE client is detected, the active dynamic preset is automatically re-applied so the new thumbnail is placed correctly instead of appearing at a random position
- All UI text, comments, shell scripts (`install.sh`, `evegoggles.sh`), JSON preset descriptions, and `requirements.txt` comments translated to English

### Removed
- Old preset files: Mining, Productivity, Combat - 6 Previews, Solo (replaced by Stacked and Mosaic)

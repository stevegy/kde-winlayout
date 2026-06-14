# kdewin

Save and restore multi-display window layouts on **KDE Plasma (Wayland)**.

Captures monitor configuration, virtual desktop layout, and all window positions into a JSON profile that can be restored later — useful after reboot, undocking, or switching between workspace setups.

## Installation

```bash
# Install dependencies (Fedora)
sudo dnf install kdotool python3-dbus

# The script itself — symlink it into PATH
ln -sf "$(pwd)/kdewin" ~/.local/bin/kdewin
```

`kscreen-doctor` is provided by the `kscreen` package (pre-installed on KDE Plasma).

### Dependencies

| Tool | Purpose | Package |
|------|---------|---------|
| `kdotool` | Window list, move, resize, state | `kdotool` |
| `kscreen-doctor` | Display config (modes, scale, position) | `kscreen` |
| `python3-dbus` | Virtual desktop info via KWin D-Bus | `python3-dbus` |
| `gdbus` | KWin scripting (move/resize windows) | `glib2` |
| `jq` | Pretty-printing profiles (optional) | `jq` |

## Usage

```
kdewin <command> [args...]
```

### Commands

| Command | Description |
|---------|-------------|
| `save [profile]` | Save current layout (default: `default`) |
| `load [profile]` | Restore a saved layout |
| `list` | List all saved profiles |
| `show [profile]` | Show profile contents as JSON |
| `delete <profile>` | Delete a saved profile |

### Logging

All output uses Python's `logging` module. Control verbosity with `LOG_LEVEL`:

```bash
# Default: INFO (shows save/load progress)
kdewin save coding

# Debug: shows window matching details, kdotool queries, launch attempts
LOG_LEVEL=DEBUG kdewin load coding

# Quiet: only errors
LOG_LEVEL=ERROR kdewin load coding
```

Valid levels: `DEBUG`, `INFO` (default), `WARNING`, `ERROR`.

### Examples

```bash
# Save your current multi-display setup
kdewin save coding

# After a reboot or monitor reconnect
kdewin load coding

# Create profiles for different work modes
kdewin save dual-screen
kdewin save single-laptop

# See what you have saved
kdewin list

# Inspect a profile
kdewin show dual-screen | jq '.windows[] | {class, name, x, y}'

# Remove an old profile
kdewin delete old-setup
```

## What gets saved

Each profile is a JSON file containing:

- **`displays`** — Full `kscreen-doctor --json` output: monitor positions, modes, scales, rotation, enabled/disabled state, brightness
- **`virtual_desktops`** — Desktop count, names, IDs, current desktop, grid rows
- **`windows`** — Per window:
  - `uuid` — KWin window ID (used for matching on restore)
  - `class` — Application class (e.g. `google-chrome`, `com.mitchellh.ghostty`)
  - `name` — Window title
  - `x`, `y`, `width`, `height` — Geometry
  - `desktop` — 0-based virtual desktop index (matches KWin VDM)
  - `sticky` — `true` if the window appears on all desktops (e.g. panels, some system windows)
  - `minimized`, `fullscreen` — Window state
  - `pid`, `cmdline` — Process info (for identification and auto-launch)

Plasma shell elements (panels, widgets) are captured but skipped on restore — Plasma manages those itself.

## How restore works

1. **Displays first** — `kscreen-doctor` applies saved monitor positions, modes, and scales; waits 2 seconds for monitors to settle
2. **Window matching** — Each saved window is matched against currently open windows by exact `class + title`, falling back to `class`-only match for same-app windows. Each current window is only matched once to prevent double-assignment.
3. **Auto-launch missing apps** — If a saved window is not currently open and its `cmdline` was captured, `kdewin` launches the application automatically and waits for its window to appear.
4. **Desktop assignment** — Sticky windows (`sticky: true`) are left on all desktops. Non-sticky windows are moved to the correct virtual desktop via `kdotool set_desktop_for_window`.
5. **Reposition** — Each matched window is moved and resized to its saved geometry in a single atomic operation via the KWin D-Bus Scripting API (avoiding a `kdotool windowmove` bug on KDE 6 Wayland where individual property assignments are silently ignored).

## Profiles

Stored at `~/.config/window-saver/profiles/<name>.json`.

Profile format (v2):
```json
{
  "version": 2,
  "profile_name": "coding",
  "created": "2026-06-03T21:47:49+08:00",
  "hostname": "fd01",
  "displays": { ... },
  "virtual_desktops": { ... },
  "windows": [ ... ]
}
```

**Version history:**
- **v1** (legacy): `desktop` stored kdotool's raw 1-based value; sticky windows had `desktop=0` with no `sticky` field.
- **v2** (current): `desktop` is 0-based (matches KWin VDM); sticky windows have `sticky: true`.

Old v1 profiles are loaded automatically with backward-compatible conversion.

## Limitations

- **Wayland only** — Uses `kdotool` which speaks the KWin Wayland protocol. Does not work on X11 (use `wmctrl` / `xdotool` instead).
- **KDE Plasma only** — Relies on `kscreen-doctor` and KWin D-Bus APIs.
- **App launch is best-effort** — Auto-launch replays the captured `cmdline` via `shlex.split`. If the app uses a wrapper, launcher, or single-instance mechanism (e.g. Flatpak, Snap, `gtk-launch`), the replayed command may not match the original startup path. Complex command lines may not parse correctly.
- **Fractional scaling** — Window coordinates are in logical pixels (as reported by KWin), which can produce fractional values under fractional scaling.
- **Window UUIDs change** — KWin assigns new UUIDs each session, so matching relies on class + title heuristics. Windows with dynamic titles (e.g. `~` for unnamed terminal tabs) or multiple instances of the same app are matched by class order; results may vary if window order changes between sessions.

## License

Apache 2.0

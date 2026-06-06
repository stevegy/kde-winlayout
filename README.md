# kde-win-profile

Save and restore multi-display window layouts on **KDE Plasma (Wayland)**.

Captures monitor configuration, virtual desktop layout, and all window positions into a JSON profile that can be restored later — useful after reboot, undocking, or switching between workspace setups.

## Installation

```bash
# Install dependencies (Fedora)
sudo dnf install kdotool python3-dbus

# The script itself — symlink it into PATH
ln -sf "$(pwd)/kde-win-profile" ~/.local/bin/kde-win-profile
```

`kscreen-doctor` is provided by the `kscreen` package (pre-installed on KDE Plasma).

### Dependencies

| Tool | Purpose | Package |
|------|---------|---------|
| `kdotool` | Window list, move, resize, state | `kdotool` |
| `kscreen-doctor` | Display config (modes, scale, position) | `kscreen` |
| `python3-dbus` | Virtual desktop info via KWin D-Bus | `python3-dbus` |
| `jq` | Pretty-printing profiles (optional) | `jq` |

## Usage

```
kde-win-profile <command> [args...]
```

### Commands

| Command | Description |
|---------|-------------|
| `save [profile]` | Save current layout (default: `default`) |
| `load [profile]` | Restore a saved layout |
| `list` | List all saved profiles |
| `show [profile]` | Show profile contents as JSON |
| `delete <profile>` | Delete a saved profile |

### Examples

```bash
# Save your current multi-display setup
kde-win-profile save coding

# After a reboot or monitor reconnect
kde-win-profile load coding

# Create profiles for different work modes
kde-win-profile save dual-screen
kde-win-profile save single-laptop

# See what you have saved
kde-win-profile list

# Inspect a profile
kde-win-profile show dual-screen | jq '.windows[] | {class, name, x, y}'

# Remove an old profile
kde-win-profile delete old-setup
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
  - `desktop` — Virtual desktop number
  - `minimized`, `fullscreen` — Window state
  - `pid`, `cmdline` — Process info (for identification, not used on restore)

Plasma shell elements (panels, widgets) are captured but skipped on restore — Plasma manages those itself.

## How restore works

1. **Displays first** — `kscreen-doctor` applies saved monitor positions, modes, and scales; waits 2 seconds for monitors to settle
2. **Window matching** — Each saved window is matched against currently open windows by exact `class + title`, falling back to `class`-only match for same-app windows
3. **Reposition** — Each matched window is resized and moved to its saved geometry, then assigned to the correct virtual desktop

## Profiles

Stored at `~/.config/window-saver/profiles/<name>.json`.

Profile format:
```json
{
  "version": 1,
  "profile_name": "coding",
  "created": "2026-06-03T21:47:49+08:00",
  "hostname": "fd01",
  "displays": { ... },
  "virtual_desktops": { ... },
  "windows": [ ... ]
}
```

## Limitations

- **Wayland only** — Uses `kdotool` which speaks the KWin Wayland protocol. Does not work on X11 (use `wmctrl` / `xdotool` instead).
- **KDE Plasma only** — Relies on `kscreen-doctor` and KWin D-Bus APIs.
- **Running apps only** — Does not launch applications; it only repositions already-open windows that match saved entries.
- **Fractional scaling** — Window coordinates are in logical pixels (as reported by KWin), which can produce fractional values under fractional scaling.
- **Window UUIDs change** — KWin assigns new UUIDs each session, so matching relies on class + title heuristics. Windows with dynamic titles or multiple instances of the same app may not restore perfectly.

## License

Apache 2.0

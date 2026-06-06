#!/usr/bin/python3
"""kdewin — Save and restore window positions on KDE Plasma (Wayland)

Requires: kdotool, kscreen-doctor, python3-dbus (optional for virtual desktop info)

Usage:
  kdewin save [profile-name]
  kdewin load [profile-name]
  kdewin list
  kdewin show [profile-name]
  kdewin delete <profile-name>
"""

import json
import os
import shutil
import subprocess
import sys
import shlex
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


# ── Config ────────────────────────────────────────────────────────────────────

PROFILE_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "window-saver" / "profiles"
DEFAULT_PROFILE = "default"

SKIP_CLASSES = {
    "plasmashell", "kded5", "kded6", "ksmserver",
    "kwin", "kwin_wayland", "kwalletd5", "kwalletd6",
    "xwaylandvideobridge",
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def run(*args: str, check: bool = True, timeout: int = 10) -> subprocess.CompletedProcess:
    """Run a command, return CompletedProcess.  On failure, return empty-ish result
    unless *check* is True."""
    try:
        return subprocess.run(args, capture_output=True, text=True, check=check, timeout=timeout)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        if check:
            raise
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="")


def kdotool(*args: str) -> str:
    """Call kdotool and return stripped stdout."""
    return run("kdotool", *args, check=False).stdout.strip()


def cmdline_of(pid: int) -> str:
    """Read /proc/<pid>/cmdline, truncate to 200 chars."""
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
        return raw.replace(b"\0", b" ").decode(errors="replace").strip()[:200]
    except (OSError, FileNotFoundError):
        return ""


def launch_app(cmdline: str) -> None:
    """Launch an application in the background using its cmdline."""
    try:
        args = shlex.split(cmdline)
        if args:
            # start_new_session=True ensures the app survives the script exiting
            subprocess.Popen(args, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:
        print(f"    Failed to launch app: {cmdline} - {exc}", file=sys.stderr)


def wait_for_window(target_cls: str, target_name: str = "", timeout: int = 15) -> str | None:
    """Wait for a window with target_cls (and optionally target_name) to appear."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        windows = collect_windows()
        for win in windows:
            if win["class"] == target_cls:
                if not target_name or target_name in win["name"]:
                    return win["uuid"]
        time.sleep(0.5)
    return None


def _set_window_geometry(uuid: str, x: float | None, y: float | None,
                        width: float | None, height: float | None) -> bool:
    """Set window geometry (position + size) atomically via a KWin script.

    ``kdotool windowmove`` sets ``w.frameGeometry.x`` / ``.y`` individually, which
    KWin 6 on Wayland silently ignores.  The pattern that *does* work is cloning
    the rect, setting all properties on the clone, then assigning the whole thing
    back — a single QRectF replacement.  We do that here via the KWin D-Bus
    Scripting interface.
    """
    rect_props = []
    if width is not None and width > 0:
        rect_props.append(f"width: {round(width)}")
    if height is not None and height > 0:
        rect_props.append(f"height: {round(height)}")
    if x is not None:
        rect_props.append(f"x: {round(x)}")
    if y is not None:
        rect_props.append(f"y: {round(y)}")
    if not rect_props:
        return False

    script = f'''
function run() {{
    var windows = workspace.windowList();
    for (var i = 0; i < windows.length; i++) {{
        var w = windows[i];
        if (w.internalId == "{uuid}") {{
            w.frameGeometry = {{ {', '.join(rect_props)} }};
            break;
        }}
    }}
}}
run();
'''

    script_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".js", prefix="kdewin_", delete=False
        ) as f:
            script_path = f.name
            f.write(script)

        # gdbus is more reliable than busctl for KWin scripting.
        # loadScript returns e.g. "(0,)" — the script ID as a GVariant.
        result = subprocess.run(
            ["gdbus", "call", "--session",
             "--dest", "org.kde.KWin",
             "--object-path", "/Scripting",
             "--method", "org.kde.kwin.Scripting.loadScript",
             script_path],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to load KWin script: {result.stderr.strip()}")

        # Start execution
        subprocess.run(
            ["gdbus", "call", "--session",
             "--dest", "org.kde.KWin",
             "--object-path", "/Scripting",
             "--method", "org.kde.kwin.Scripting.start"],
            capture_output=True, text=True, timeout=10, check=True,
        )

        # Unload by file path (same string originally passed to loadScript)
        subprocess.run(
            ["gdbus", "call", "--session",
             "--dest", "org.kde.KWin",
             "--object-path", "/Scripting",
             "--method", "org.kde.kwin.Scripting.unloadScript",
             script_path],
            capture_output=True, text=True, timeout=10,
        )

        return True
    except Exception as exc:
        print(f"    Warning: KWin script failed for {uuid}: {exc}", file=sys.stderr)
        return False
    finally:
        if script_path:
            Path(script_path).unlink(missing_ok=True)


# ── D-Bus helpers (optional) ───────────────────────────────────────────────────

HAS_DBUS = False
try:
    import dbus  # noqa: I001
    HAS_DBUS = True
except ImportError:
    pass


def _get_desktop_info_via_dbus() -> dict:
    """Query KWin VirtualDesktopManager.  Returns empty dict on failure."""
    if not HAS_DBUS:
        return {"count": 0, "rows": 0, "current": "", "desktops": [],
                "note": "python3-dbus not available"}

    try:
        bus = dbus.SessionBus()
        vdm = bus.get_object("org.kde.KWin", "/VirtualDesktopManager")
        props = dbus.Interface(vdm, "org.freedesktop.DBus.Properties")
        desktops_raw = props.Get("org.kde.KWin.VirtualDesktopManager", "desktops")
        count = int(props.Get("org.kde.KWin.VirtualDesktopManager", "count"))
        current = str(props.Get("org.kde.KWin.VirtualDesktopManager", "current"))
        rows = int(props.Get("org.kde.KWin.VirtualDesktopManager", "rows"))

        desktops = [{"index": int(d[0]), "id": str(d[1]), "name": str(d[2])}
                    for d in desktops_raw]

        return {"count": count, "rows": rows, "current": current, "desktops": desktops}
    except Exception as exc:
        return {"error": str(exc)}


# ── Collectors ─────────────────────────────────────────────────────────────────

def collect_displays() -> dict:
    """Return ``kscreen-doctor --json`` output as a dict."""
    result = run("kscreen-doctor", "--json", check=False)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"error": "failed to parse kscreen-doctor output"}


def collect_desktops() -> dict:
    return _get_desktop_info_via_dbus()


def collect_windows() -> list[dict]:
    """Enumerate every window and return its geometry + metadata."""
    uuids = [u for u in kdotool("search", "").splitlines() if u.strip()]
    windows: list[dict] = []

    for uuid in uuids:
        cls = kdotool("getwindowclassname", uuid)
        name = kdotool("getwindowname", uuid)

        geom = kdotool("getwindowgeometry", uuid)
        pos_str = ""
        size_str = ""
        for line in geom.splitlines():
            line = line.strip()
            if line.startswith("Position:"):
                pos_str = line.split(":", 1)[1].strip()
            elif line.startswith("Geometry:"):
                size_str = line.split(":", 1)[1].strip()

        x = y = w = h = None
        if pos_str:
            parts = pos_str.split(",")
            try:
                x, y = float(parts[0]), float(parts[1])
            except (ValueError, IndexError):
                pass
        if size_str:
            parts = size_str.split("x")
            try:
                w, h = float(parts[0]), float(parts[1])
            except (ValueError, IndexError):
                pass

        desk_str = kdotool("get_desktop_for_window", uuid)
        desk = int(desk_str) if desk_str.isdigit() else 0

        pid_str = kdotool("getwindowpid", uuid)
        pid = int(pid_str) if pid_str.isdigit() else 0

        state = kdotool("windowstate", uuid).lower()
        minimized = "minimized" in state
        fullscreen = "fullscreen" in state

        windows.append({
            "uuid": uuid,
            "class": cls,
            "name": name,
            "x": x, "y": y, "width": w, "height": h,
            "desktop": desk,
            "minimized": minimized,
            "fullscreen": fullscreen,
            "pid": pid,
            "cmdline": cmdline_of(pid) if pid else "",
        })

    return windows


# ── Commands ───────────────────────────────────────────────────────────────────

def cmd_save(profile_name: str = DEFAULT_PROFILE) -> None:
    profile_path = PROFILE_DIR / f"{profile_name}.json"
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Saving window layout to profile: {profile_name}")
    print("-" * 40)

    print("  Capturing display configuration... ", end="", flush=True)
    displays = collect_displays()
    print("done")

    print("  Capturing virtual desktop layout... ", end="", flush=True)
    desktops = collect_desktops()
    print("done")

    print("  Capturing window positions... ", end="", flush=True)
    windows = collect_windows()
    print(f"done ({len(windows)} windows)")

    profile = {
        "version": 1,
        "profile_name": profile_name,
        "created": datetime.now(timezone.utc).astimezone().isoformat(),
        "hostname": os.uname().nodename,
        "displays": displays,
        "virtual_desktops": desktops,
        "windows": windows,
    }

    profile_path.write_text(json.dumps(profile, indent=2))

    disp_count = len(displays.get("outputs", []))
    desk_count = desktops.get("count", 0)
    print(f"\nProfile saved to: {profile_path}")
    print(f"  Displays: {disp_count}")
    print(f"  Desktops: {desk_count}")
    print(f"  Windows:  {len(windows)}")


def cmd_load(profile_name: str = DEFAULT_PROFILE) -> None:
    profile_path = PROFILE_DIR / f"{profile_name}.json"
    if not profile_path.is_file():
        print(f"ERROR: Profile not found: {profile_name}", file=sys.stderr)
        print("Available profiles:", file=sys.stderr)
        cmd_list()
        sys.exit(1)

    print(f"Loading window layout from profile: {profile_name}")
    print("-" * 41)

    data = json.loads(profile_path.read_text())

    # 1. Restore display configuration
    print("  Restoring display configuration...")
    outputs = data.get("displays", {}).get("outputs", [])
    if outputs:
        args = ["kscreen-doctor"]
        for out in outputs:
            name = out.get("name", "")
            if not out.get("enabled", True):
                args.append(f"output.{name}.disable")
                continue
            pos = out.get("pos", {})
            args.append(f"output.{name}.position.{pos.get('x',0)},{pos.get('y',0)}")
            if mid := out.get("currentModeId", ""):
                args.append(f"output.{name}.mode.{mid}")
            args.append(f"output.{name}.scale.{out.get('scale', 1.0)}")
            rot = out.get("rotation", 1)
            rot_map = {1: "none", 2: "left", 4: "right", 8: "inverted"}
            if rot_name := rot_map.get(rot):
                if rot_name != "none":
                    args.append(f"output.{name}.rotation.{rot_name}")
            args.append(f"output.{name}.enable")
        print(f"    Restoring {len(outputs)} output(s)...")
        run(*args, check=False)
    print("    (display config applied — waiting for monitors to settle)")
    time.sleep(2)

    # 2. Restore windows
    print("  Restoring window positions...")
    _restore_windows(data.get("windows", []))
    print(f"\nLayout restored from: {profile_path}")


def _restore_windows(saved: list[dict]) -> None:
    """Match saved windows to current windows and move/resize them.
    Launches missing applications if cmdline is available."""
    # Build current window lookup
    current = collect_windows()
    current_by_exact: dict[tuple[str, str], str] = {}   # (cls, name) -> uuid
    current_by_class: dict[str, list[str]] = {}          # cls -> [uuids...]

    for w in current:
        key = (w["class"], w["name"])
        if key not in current_by_exact:
            current_by_exact[key] = w["uuid"]
        current_by_class.setdefault(w["class"], []).append(w["uuid"])

    # Track which UUIDs have already been used to avoid double-matching
    used_uuids: set[str] = set()

    print(f"  Found {len(saved)} windows in profile")

    to_restore: list[dict] = [] # list of {"win": win_dict, "uuid": uuid}
    to_launch: list[dict] = []
    skipped = 0
    missing = 0

    for win in saved:
        cls = win.get("class", "")
        name = win.get("name", "")
        x, y = win.get("x"), win.get("y")
        w_val, h_val = win.get("width"), win.get("height")

        # 1. Skip system critical windows
        if cls in SKIP_CLASSES:
            skipped += 1
            continue

        # 2. Try to match an existing window
        target_uuid = current_by_exact.get((cls, name))
        if target_uuid:
            if target_uuid in used_uuids:
                target_uuid = None  # Already used, fall through to class-level

        # 3. Fall back to class-level matching, skipping already-used UUIDs
        if not target_uuid and cls:
            class_list = current_by_class.get(cls, [])
            while class_list:
                candidate = class_list.pop(0)
                if candidate not in used_uuids:
                    target_uuid = candidate
                    break

        if target_uuid:
            used_uuids.add(target_uuid)
            to_restore.append({"win": win, "uuid": target_uuid})
        elif win.get("cmdline"):
            to_launch.append(win)
        else:
            missing += 1

    restored = 0
    launched = 0

    # 1. Launch missing apps
    if to_launch:
        print(f"  Launching {len(to_launch)} missing applications...")
        for win in to_launch:
            cls = win.get("class", "")
            name = win.get("name", "")
            print(f"    Launching: {cls} ({name})...")
            launch_app(win["cmdline"])
            launched += 1

        # 2. Wait for them to appear
        if launched > 0:
            print("    Waiting for applications to settle...")
            for win in to_launch:
                uuid = wait_for_window(win["class"], win["name"], timeout=10)
                if uuid:
                    to_restore.append({"win": win, "uuid": uuid})
                else:
                    print(f"    Warning: Could not detect window for {win['class']} after timeout.")
                    missing += 1

    # 3. Restore geometry/desktop for everything in to_restore
    for item in to_restore:
        win = item["win"]
        target_uuid = item["uuid"]

        cls = win.get("class", "")
        name = win.get("name", "")
        x, y = win.get("x"), win.get("y")
        w_val, h_val = win.get("width"), win.get("height")

        try:
            # 1. Always try to set desktop FIRST to get into the right context
            desk = win.get("desktop", 0)
            if desk is not None and desk > 0:
                kdotool("set_desktop_for_window", target_uuid, str(int(desk)))

            # 2. Move + resize atomically via KWin script (kdotool windowmove
            #    is broken on KDE 6 Wayland — it sets frameGeometry.x/.y
            #    individually on a QRectF proxy, which KWin ignores).
            if x is not None and y is not None and w_val is not None and h_val is not None and w_val > 0 and h_val > 0:
                _set_window_geometry(target_uuid, x, y, w_val, h_val)

            restored += 1
        except Exception as exc:
            print(f"    Failed to restore {cls} - {name}: {exc}", file=sys.stderr)

    print(f"\n  Results: {restored} restored, {missing} missing/failed, {skipped} skipped")


def cmd_list() -> None:
    print("Saved window layout profiles:")
    print("=" * 30)

    found = False
    for fpath in sorted(PROFILE_DIR.glob("*.json")):
        found = True
        name = fpath.stem
        try:
            data = json.loads(fpath.read_text())
            created = data.get("created", "unknown")
            win_count = len(data.get("windows", []))
        except (json.JSONDecodeError, OSError):
            created, win_count = "corrupt", 0
        print(f"  {name:<20s}  {created}  ({win_count} windows)")

    if not found:
        print("  (no profiles saved yet)")


def cmd_show(profile_name: str = DEFAULT_PROFILE) -> None:
    profile_path = PROFILE_DIR / f"{profile_name}.json"
    if not profile_path.is_file():
        print(f"ERROR: Profile not found: {profile_name}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(json.loads(profile_path.read_text()), indent=2))


def cmd_delete(profile_name: str) -> None:
    if not profile_name:
        print("ERROR: Specify a profile name to delete", file=sys.stderr)
        sys.exit(1)
    profile_path = PROFILE_DIR / f"{profile_name}.json"
    if not profile_path.is_file():
        print(f"ERROR: Profile not found: {profile_name}", file=sys.stderr)
        sys.exit(1)
    print(f"Deleting profile: {profile_name}")
    profile_path.unlink()
    print(f"Deleted: {profile_path}")


# ── Dependency check ───────────────────────────────────────────────────────────

def check_deps() -> None:
    missing = []
    for dep in ("kdotool", "kscreen-doctor"):
        if shutil.which(dep) is None:
            missing.append(dep)
    if missing:
        print(f"ERROR: Missing dependencies: {' '.join(missing)}", file=sys.stderr)
        print("Install with: sudo dnf install kdotool", file=sys.stderr)
        sys.exit(1)
    if not HAS_DBUS:
        print("NOTE: python3-dbus not available — virtual desktop info will be limited", file=sys.stderr)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    check_deps()

    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    rest = sys.argv[2:] if len(sys.argv) > 2 else []

    if cmd in ("save",):
        cmd_save(*rest)
    elif cmd in ("load", "restore"):
        cmd_load(*rest)
    elif cmd in ("list", "ls"):
        cmd_list()
    elif cmd in ("show", "cat"):
        cmd_show(*rest)
    elif cmd in ("delete", "rm", "remove"):
        cmd_delete(rest[0] if rest else "")
    elif cmd in ("-h", "--help", "help", ""):
        print(__doc__)
        print(f"\nProfiles are stored in: {PROFILE_DIR}")
        print("Dependencies: kdotool, kscreen-doctor, python3-dbus")
    else:
        print(f"ERROR: Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

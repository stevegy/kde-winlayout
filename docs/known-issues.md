# kdewin — Known Issues

## Auto-launch limitations

### 1. Chrome: multiple instances conflict

When restoring Chrome windows, kdewin launches a separate Chrome process for each saved tab. Chrome uses a single-instance architecture — only one process can own the profile. Launching multiple instances simultaneously causes:

- Profile lock contention
- "Profile cannot be loaded" warnings
- Only one Chrome window created (blank), not the expected tabs

**Workaround:** Chrome windows are matched against existing Chrome windows by class+title. If Chrome is already running, geometry is applied correctly. For a clean restore, launch Chrome manually first, then run `kdewin load`.

### 2. AppImage: ephemeral mount paths

AppImage processes mount themselves to `/tmp/.mount_<hash>/usr/bin/<binary>` at runtime. kdewin captures this ephemeral path as the `cmdline`. After reboot, the mount point no longer exists and the launch fails:

```
Failed to launch app: /tmp/.mount_WeChatbeAAPA/usr/bin/wechat --no-sandbox
  [Errno 2] No such file or directory
```

**Workaround:** Manually locate the `.AppImage` file and use the correct launch path. The desktop entry (e.g. `/usr/share/applications/*.desktop`) usually has the right `Exec=` line.

### 3. D-Bus-activatable apps: no window created

Some apps (e.g. Ghostty) use systemd D-Bus activation with `--initial-window=false`. The stored cmdline starts the daemon without creating a window. kdewin replays the daemon's cmdline, which starts a new daemon but creates no window:

```
launch_app: args=['/usr/bin/ghostty', '--gtk-single-instance=true', '--initial-window=false']
  (no window appears)
```

**Workaround:** Open the app manually. The `--initial-window=false` flag is specific to Ghostty's D-Bus activation model and is not a common Linux desktop pattern.

### 4. PWA (Progressive Web Apps): class name mismatch

Chrome PWAs (e.g. Apple Music web app) have a class name derived from the origin: `chrome-<origin-id>-Default`. When kdewin launches Chrome to restore a PWA window, Chrome opens a blank instance with class `google-chrome`, not the PWA class. The `wait_for_window` timeout expires because no window matches.

The stored cmdline is Chrome's internal startup command, not the PWA URL. Chrome has no way to relaunch a specific PWA from the cmdline alone.

**Workaround:** Open the PWA URL manually in an existing Chrome window.

## Matching limitations

### 5. Dynamic titles

Windows with dynamic or generic titles (e.g. unnamed terminal tabs showing `~`, VS Code showing file paths that change) may not match correctly. kdewin falls back to class-only matching, which can assign the wrong window to the wrong geometry.

### 6. Single-instance apps

Apps that use single-instance mechanisms (VS Code, Chrome, Firefox) may have multiple windows but only one process. kdewin captures the cmdline of the first process and tries to launch it for each missing window, resulting in duplicate launches that don't create new windows.

## Platform limitations

### 7. Wayland only

kdewin uses `kdotool` which speaks the KWin Wayland protocol. It does not work on X11 (use `wmctrl` or `xdotool` instead).

### 8. KDE Plasma only

kdewin relies on `kscreen-doctor` and KWin D-Bus APIs. It will not work on other desktop environments.

### 9. python3-dbus optional

Virtual desktop info requires `python3-dbus`. Without it, desktop data is limited (count=0). The `gdbus` approach for window geometry still works.

# AGENTS.md

Short tour. The full module-by-module reference is in the code; this is just a map.

## What it is

Small Python service. Reads **Assetto Corsa EVO** telemetry from Windows shared
memory and drives **DualSense adaptive triggers** over raw HID, while leaving
rumble bytes alone so Steam Input still handles rumble.

Forked from [HamzaYslmn/Forza-Horizon-DualSense-Python](https://github.com/HamzaYslmn/Forza-Horizon-DualSense-Python).

## Stack

- Python `>=3.13`, `uv` for deps.
- Deps: `hidapi`, `textual`, `psutil`, `customtkinter`, `pystray`, `pillow`.
- Distributed as a single self-contained file (`acevo.zuv.py`) via [`zuv`](https://github.com/HamzaYslmn/zuv).
- Windows + Linux. No tests.

## Layout

One-liner:
```powershell
uvx zuv build src -o app/acevo.zuv.py --update-repo HelloItMeMort/AC-Evo-DualSense-Python
```

```
src/
  main.py                    # entry: IS_ZUV check, args, TUI/headless boot
  pyproject.toml             # version, deps, [tool.zuv] entry+volume
  lang/                      # i18n: one module per language (en/tr/zh/zh_tw/ru), auto-discovered
  modules/
    ac_evo/
      shm_reader.py          # SHM attach, ctypes structs, telemetry dict
      effects.py             # AC Evo Controller + TriggerAnimations
      loop.py                # per-frame driver
      process_watch.py       # game proc watcher
    dualsense/
      main.py                # HID writer (USB+BT), persistent mode
      adaptive_trigger.py    # generic effect primitives
      hidhide.py             # filesystem-only HidHide detection
    dsx/                     # DualSenseX UDP backend
    config/                  # settings, preferences, profiles, paths
    gui/                     # CustomTkinter app
    tui/                     # Textual TUI
  .python-version
win_start.bat / linux_start.sh   # launchers (auto-download bundle + run uv)
.github/workflows/release.yml    # CI: build bundle, publish release
```

## Data flow (one frame)

```
AC Evo SHM -> AcEvoReader.read_latest() -> Controller.update() -> (left, right)
                                                            |
                            DualSense.set (state-change only)
                                                            v
                                                HID write (trigger bytes only,
                                                 rumble bytes untouched)
```

Trigger command = `(mode, p1, p2)`:
- `M_OFF (0x05)` free, `M_RIGID (0x01)` constant force, `M_VIBRATE (0x03)` buzz.
- `M_RIGID_ZONES (0x02)` walls, `M_VIBRATE_ZONES (0x04)` sustained push.

## Run

### Dev (no bundle)
```powershell
cd src
uv sync
uv run main.py
```

### Build the bundle locally (same as CI)

One-liner:
```powershell
uvx zuv build src -o app/acevo.zuv.py --update-repo HelloItMeMort/AC-Evo-DualSense-Python
```

Drop `--update-repo` if you don't want the bundle to self-update from GitHub
on next launch (useful while iterating locally).

Bump the version first by editing `version = "X.Y.Z"` in `src/pyproject.toml`.

### Run the bundle
```powershell
.\win_start.bat
```
Launcher auto-downloads `app/acevo.zuv.py` if missing, installs `uv` if missing,
then `uv run`s the bundle.

## CI gating

`.github/workflows/release.yml`:
- Push to `dev` with `prerelease` in commit msg -> prerelease tagged at the next patch above the latest stable release (e.g. latest `v1.4.5` -> `v1.4.6`).
- Push to `main` with `release VX.Y.Z` in commit msg -> stable `vX.Y.Z`.
- Push tag `v*.*.*` -> stable release.
- `workflow_dispatch` -> prerelease at the next patch (same rule as above).

## Env vars

- `IS_ZUV=true` - set automatically by the zuv loader when running the bundle.
  Used by the System tab to locate the ZUV cache root for the update sentinel.

## Conventions

- **KISS.** Don't abstract for one caller.
- All tunables go in `settings.py`, never inside module logic.
- **Globals stay global.** Add to `preferences.GLOBAL_FIELDS`; never copy into per-profile dicts.
- **Don't touch rumble bits.** HID writer only flips trigger bits in `valid_flag0`.
- **State-change writes only.** The loop diffs `(left, right)` against `prev` and only calls `ds.set(...)` on change.
- No em dash (`-`) anywhere - in code, docs, or chat. Plain hyphens only.
- UTF-8 source files.

## HidHide

I do NOT call `HidHideCLI.exe`. `hidhide.is_detected()` is a pure filesystem
probe. When detected, the I/O loop latches into **persistent mode** on the
first successful connect: keeps the HID handle open, ignores read/write
errors, skips the watchdog, ignores the `enable_reconnect` setting. This way
HidHide cloaking the device mid-session doesn't tear our handle down.

## Common edits

| Want to... | Open this |
|---|---|
| Change a tunable / disable an effect | `src/modules/config/settings.py` |
| Change how an effect feels | `src/modules/dualsense/adaptive_trigger.py` (primitive) or `src/modules/ac_evo/effects.py` (game logic) |
| Touch raw HID bytes | `src/modules/dualsense/main.py` |
| Add a telemetry field | `src/modules/ac_evo/shm_reader.py` |
| Change CLI / startup wiring | `src/main.py` |
| Change persistence layout | `src/modules/config/preferences.py` |
| Edit the GUI/TUI | `src/modules/gui/` / `src/modules/tui/` |
| Add/translate a UI language | `src/lang/` (drop a `<code>.py` with `NAME` + `STRINGS`) |
| Change launcher behavior | `win_start.bat` / `linux_start.sh` |
| Change CI gating | `.github/workflows/release.yml` |

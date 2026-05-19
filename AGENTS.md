# AGENTS.md - Onboarding for New Developers

A short tour of the project so you can read, run, and modify it in an afternoon.

---

## 1. What is this project?

A small Python service that gives the **PlayStation DualSense controller real
adaptive-trigger feedback while playing Forza Horizon on PC (Steam)**.

- Forza Horizon broadcasts live telemetry (RPM, speed, pedals, tire slip, gear...)
  over **UDP** if you turn on **HUD & Gameplay -> Data Out** in the game.
- Steam Input only sends generic rumble to the DualSense; the trigger motors
  do nothing.
- This project listens to the UDP feed, computes a trigger force/vibration
  every frame, and writes it directly to the controller via **raw HID**, while
  carefully **not touching the rumble bytes** so Steam still drives rumble.

Result: brake trigger that resists like a brake pedal, throttle trigger that
pushes back when the engine works, ABS pulse on tire slip, gear-shift thump,
rev-limiter buzz, plus a Textual TUI for live tuning and named profiles.

---

## 2. Tech stack

| Piece | What |
|---|---|
| Language | Python `>=3.13` (see `src/pyproject.toml`) |
| Package manager | [`uv`](https://astral.sh/uv) (replaces pip + venv) |
| Runtime deps | `hidapi` (raw HID I/O), `textual` (TUI), `psutil` (game process detection) |
| Distribution | [`zuv`](https://github.com/HamzaYslmn/zuv) bundles the project into a single self-updating `fhds.zuv.py` |
| OS | Windows + Linux (each has its own launcher) |
| Hardware | DualSense or DualSense Edge over USB or Bluetooth |

No tests, no enforced linter. `ruff` line length is set in `pyproject.toml`.

---

## 3. Repository layout

```
Forza-Horizon-DualSense-Python/
|-- README.md                       # User-facing docs
|-- AGENTS.md                       # <- you are here
|-- LICENSE
|-- win_start.bat                   # Windows launcher (auto-downloads bundle)
|-- linux_start.sh                  # Linux launcher (same)
|-- img/                            # Screenshots used in README
|-- packaging/linux/                # 70-dualsense.rules (udev) installed by launcher
|-- .claude/                        # Local-only notes (gitignored)
|-- .github/workflows/release.yml   # CI: builds bundle, publishes releases
`-- src/
    |-- pyproject.toml              # Project meta + [tool.zuv] entry/volume
    |-- uv.lock                     # Locked dependency versions
    |-- main.py                     # Entry: IS_ZUV check, args, TUI/headless boot
    |-- data/                       # Persistent volume (user_preferences.json, crash.log)
    `-- modules/
        |-- __init__.py             # Exposes setup_logging() + sub-packages
        |-- settings.py             # @dataclass Settings - all tunables
        |-- preferences.py          # JSON persistence: profiles + globals block
        |-- profiles.py             # Named profile CRUD
        |-- loop.py                 # Per-packet loop (parse -> compute -> write)
        |-- dualsense/              # HID writer + trigger effect primitives
        |   |-- main.py             # Open/close/write to controller (USB + BT)
        |   `-- triggers.py         # Effect primitives + TriggerAnimation
        |-- udplistener/main.py     # UDP socket + 324-byte FH packet parser
        |-- tui/                    # Textual app (controls/settings/profiles/logs tabs)
        |-- emulation/              # Optional fake telemetry source for offline dev
        `-- exit_detection/         # Game-exit watcher for Steam wrapper mode
```

Shortest read path:

1. `src/main.py`
2. `src/modules/settings.py`
3. `src/modules/loop.py`
4. `src/modules/udplistener/main.py`
5. `src/modules/dualsense/triggers.py`
6. `src/modules/dualsense/main.py`
7. `src/modules/preferences.py` + `profiles.py`

---

## 4. How the data flows (one frame)

```
Forza Horizon  --UDP 5300, 324 bytes-->  UDPListener.recv_latest()
                                                  |
                                                  v
                                          parse_packet(pkt) -> dict
                                                  |
                                                  v
                                  TriggerAnimation.update(t, settings)
                                                  |
                                                  v
                                       (left, right) trigger commands
                                                  |
                                                  v
                                            DualSense.set(left, right)
                                                  |  (worker thread writes HID
                                                  |   only when state changed)
                                                  v
                                          DualSense controller motors
```

Each trigger command is a 3-tuple `(mode, p1, p2)`:
- `M_OFF (0x05)` - trigger free
- `M_RIGID (0x01)` - constant resistance, p2 = force 0..255
- `M_PULSE (0x06)` - vibration, p1 = freq Hz, p2 = amplitude 0..255

The HID write only flips `valid_flag0` bits for the trigger motors, so Steam
Input keeps owning the rumble bytes.

---

## 5. Key modules in detail

### `src/main.py` - entry point
- Startup guard: if `IS_ZUV != "true"` and `FHDS_DEV` is unset, prints a
  notice + blocking `[y/N]` prompt warning the user they're on the old
  standalone flow, pointing them at the new launcher.
- Parses CLI flags (`--host`, `--port`, `--debug`, `--headless`).
- Calls `preferences.load(settings)` with a recovery prompt on corrupt JSON.
- Boots `run_tui(s)` (default) or `run(s)` (headless).
- Tiny `_confirm(prompt)` helper for both y/N prompts.

### `src/modules/settings.py` - all tunables
A single `@dataclass Settings` with flat fields. Forces are 0..255, frequencies in Hz.
Each effect has an `enable_*` switch. **Some fields are "globals"** (currently
just `enable_reconnect`) - listed in `preferences.GLOBAL_FIELDS` and persisted
at the top of the JSON instead of per-profile.

### `src/modules/preferences.py` - persistence
File layout in `data/user_preferences.json`:

```json
{
  "version": "1.4.0",
  "active_profile": "Default",
  "globals": { "enable_reconnect": false },
  "profiles": {
    "Default": { "...flat Settings fields..." },
    "Sport":   { "..." }
  }
}
```

Public API:
- `load(s)` - reads the file, applies globals + active profile to `s`. Raises
  `PreferencesError` on corruption so `main.py` can prompt for backup+reset.
- `save(s)` - writes the active profile + globals back.
- `reset(s)` - restores the active profile to dataclass defaults (globals untouched).
- `reset_file()` - backs up + deletes the JSON so `load` can rebuild from scratch.

Internal helpers (also used by `profiles.py`): `_fields`, `_profile_fields`,
`_global_fields`, `_apply_snap`.

### `src/modules/profiles.py` - named profile CRUD
- `load_store()`, `list_names(store)` - read side.
- `save_as(name, s)`, `apply(name, s)`, `delete(name)`, `rename(old, new)`.
- Every operation re-reads the JSON (no in-memory cache to drift).
- `"Default"` is locked (cannot be renamed or deleted).
- Uses `preferences._profile_fields(s)` so globals never leak into per-profile blocks.

### `src/modules/udplistener/main.py`
- `parse_packet(p)`: unpacks the 324-byte FH telemetry into a dict
  (RPM, accel, brake, gear, speed in km/h, four-wheel slip values, etc.).
- `UDPListener` (context manager): non-blocking socket; `recv_latest()` drains
  the queue and returns only the freshest packet so we never react to stale data.

### `src/modules/dualsense/triggers.py`
- Effect primitives: `off()`, `rigid(force)`, `vibration(freq, amp)`.
- `TriggerAnimation.update(t, s)` returns `(left, right)` each frame.
  - **Left (brake):** ABS slip pulse -> progressive rigid resistance with
    optional handbrake bonus.
  - **Right (throttle), strict priority:** gear-shift burst ->
    rev-limiter buzz -> progressive rigid resistance.
- `_pedal_force()` is a baseline -> max exponential ramp; pedals above
  `*_full_force_at` jump straight to 255.

### `src/modules/dualsense/main.py`
- `_find_gamepad()` enumerates HID and picks the **Game Pad interface**
  (`usage_page=1`, `usage=5`); audio/sensor interfaces share the same VID/PID
  and silently drop trigger writes.
- Detects USB vs Bluetooth (different report IDs, sizes, BT needs a CRC32).
- `open()` starts a daemon thread that:
  - drains input reports non-blocking so the BT pipe doesn't stall,
  - writes a new HID report only when `_dirty` (state changed),
  - reconnects on disconnect if `enable_reconnect=True`.
- `set(left, right)` is the only API the per-frame loop calls.

### `src/modules/loop.py`
Per-packet driver: pull latest packet -> parse -> compute -> diff -> write.
Throttled debug log once per second so logs don't spam at 60+ Hz.

### `src/modules/tui/`
Textual app, four tabs: live controls, settings tuning, named profiles, log
tail. Mutates the same `Settings` instance the loop is reading.

### `src/modules/exit_detection/`
Watches a child process or polls for the game executable so the service can
exit cleanly when Forza closes. Used in Steam wrapper mode.

### `src/modules/emulation/`
Optional fake telemetry source for offline dev (no Forza needed). Off by default.

---

## 6. Running the project

### Quickest path (end user)
1. Download `win_start.bat` (Windows) or `linux_start.sh` (Linux) from the
   latest release.
2. Drop it in an empty folder. Double-click.
3. The launcher downloads `fhds.zuv.py` into `app/`, installs `uv` if needed,
   and runs the bundle. Auto-updates on next launch.

### Dev workflow (working in this repo)
```powershell
cd src
uv sync
$env:FHDS_DEV = "1"   # suppress the "old standalone version" prompt
uv run main.py
```

Set `FHDS_DEV=1` in your shell profile so the IS_ZUV warning never bothers you.

### CLI flags
| Flag | Meaning |
|---|---|
| `--host` | UDP bind address (default `127.0.0.1`) |
| `--port` | UDP port (default `5300`) |
| `--debug` | Verbose per-packet logs (headless mode) |
| `--headless` | Disable TUI, console logs only |

### Env vars
| Var | Meaning |
|---|---|
| `IS_ZUV=true` | Set automatically by the zuv loader when running the bundle |
| `FHDS_DEV=1` | Suppress the "old standalone version" startup prompt |

### In-game setup (must do once)
Forza Horizon -> **Settings -> HUD and Gameplay -> Data Out: ON**, IP `127.0.0.1`,
Port `5300`. See screenshots in `img/`.

A short pulse on both triggers at startup confirms HID writes are landing.

---

## 7. Distribution & CI

### Bundling with zuv
`zuv build` reads `src/pyproject.toml` (note `[tool.zuv] entry = "main.py"`,
`volume = "data"`) and produces a single self-contained `fhds.zuv.py`:
- Inlines all source as a base85-encoded tar.xz payload.
- Inlines the loader (zuv's `_loader_template.py`).
- Mounts `data/` as a persistent volume so user prefs survive updates.
- First run: extracts to a per-user cache, creates a venv via `uv`,
  installs deps, runs `main.py`.
- Subsequent runs: skips extraction; optionally self-updates from
  `releases/latest/download/fhds.zuv.py` (or `releases/download/v999.0.0/...`
  if `--prerelease` is passed).

The launchers (`win_start.bat`, `linux_start.sh`) toggle the prerelease channel
via a `PRERELEASE=false|true` variable at the top.

### CI gating (`.github/workflows/release.yml`)
- Push to `dev` with `"prerelease"` in commit message -> rebuilds the rolling
  `v999.0.0` prerelease.
- Push to `main` with `"release vX.Y.Z"` in commit message -> stable release.
- Push a `v*.*.*` tag -> stable release.
- `workflow_dispatch` -> rolling prerelease.

---

## 8. Common dev tasks

### Tweak the feel
Edit `src/modules/settings.py` defaults, or use the Settings tab in the TUI
(persisted to the active profile).

### Add a new trigger effect
1. Add an `enable_*` switch + parameter fields to `Settings` in `settings.py`.
2. Implement inside `TriggerAnimation._brake()` or `_throttle()` in
   `dualsense/triggers.py`. Mind the **priority order** in `_throttle()` -
   first match wins.
3. If you need a new HID write mode, extend the `M_*` constants in the same file.

### Make a Settings field global (cross-profile)
1. Add its name to `GLOBAL_FIELDS` in `preferences.py`.
2. Next save will move it to the top-level `globals` block.
   (Stale per-profile copies are left in the JSON; safe to ignore or clean
   by hand.)

### Add a new named profile programmatically
`profiles.save_as("Sport", s)` - copies current `Settings` (minus globals)
under the new name and makes it active.

### Support a new telemetry field
Add an offset line in `parse_packet()` (`udplistener/main.py`) using the
existing `f/i/b/I/H` helpers; read it via `t.get("your_field")` inside
`TriggerAnimation`.

### Support another controller / connection mode
HID layout tables `USB` and `BT` in `dualsense/main.py` define report ID,
flag-byte position, trigger byte offsets, and report size. Add a third entry
and pick it in `_find_gamepad` / `_is_bluetooth`.

---

## 9. Conventions to keep

- **KISS.** The project is intentionally small. Resist abstracting.
- **One file of knobs.** All tunables go in `settings.py`, never inside
  module logic.
- **Don't touch rumble bits.** The HID writer only flips trigger bits in
  `valid_flag0`. Breaking this would fight Steam Input.
- **Always drain UDP.** Use `recv_latest()`; never react to stale packets.
- **Non-blocking HID.** Trigger writes must not wait on input reports
  (Bluetooth will stall otherwise).
- **State-change writes only.** The loop diffs `(left, right)` against `prev`
  and only calls `ds.set(...)` when something changed.
- **No em dash** in code, comments, or docs. Use a hyphen.
- **UTF-8** for every source file.
- **Globals stay global.** Never copy a `GLOBAL_FIELDS` key into a per-profile
  dict on save.

---

## 10. Troubleshooting cheat sheet

| Symptom | Cause / fix |
|---|---|
| `DualSense gamepad interface not found` | Controller not connected, or HidHide hides it - allowlist `python.exe`. |
| `No UDP packets yet` after a few seconds | Forza Horizon Data Out off, IP/port mismatch, or Windows Firewall blocking. |
| Triggers feel weak | Raise `brake_max_force` / `throttle_max_force`, or lower the relevant `*_curve`. |
| Triggers feel like a wall | Lower `*_max_force`, or raise `*_curve` so resistance arrives later. |
| "Machine-gun" buzzing near deadzone | Raise `*_baseline_force` or `*_deadzone`. |
| Bundle won't update | Delete `app/fhds.zuv.py` and re-run the launcher. |
| Bundle behaves weird after a code change | You edited `src/` but ran a stale bundle - run `uv run src/main.py` directly during dev, or rebuild with `uvx zuv build`. |

See README "Troubleshooting" for the user-facing version.

---

## 11. Where to look for what

| You want to... | Open this |
|---|---|
| Change a number / disable an effect | `src/modules/settings.py` |
| Change *how* an effect feels (logic) | `src/modules/dualsense/triggers.py` |
| Touch raw HID bytes | `src/modules/dualsense/main.py` |
| Add a telemetry field | `src/modules/udplistener/main.py` |
| Change CLI / startup wiring | `src/main.py` |
| Change persistence layout | `src/modules/preferences.py` |
| Change profile CRUD | `src/modules/profiles.py` |
| Edit the TUI | `src/modules/tui/` |
| Change launcher behavior | `win_start.bat` / `linux_start.sh` |
| Change CI / release gating | `.github/workflows/release.yml` |

That's the whole project. Welcome aboard.

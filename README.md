<div align="center">
  <h1>🏎️ Forza Horizon 5 — DualSense Adaptive Triggers</h1>
  <p><strong>Real, physics-driven trigger feedback for the Steam version of FH5.</strong></p>
  <p><em>Lightweight · No presets · No mode juggling · One file of knobs you can edit in 10 seconds.</em></p>
</div>

---

## 📜 Table of Contents
1. [Why this exists](#-why-this-exists)
2. [What you'll feel](#-what-youll-feel)
3. [How it works](#-how-it-works)
4. [Installation](#%EF%B8%8F-installation)
5. [In-game setup](#-in-game-setup)
6. [Run it](#%EF%B8%8F-run-it)
7. [CLI options](#%EF%B8%8F-cli-options)
8. [Tuning the feel](#%EF%B8%8F-tuning-the-feel)
9. [Project layout](#-project-layout)
10. [Troubleshooting](#-troubleshooting)
11. [Credits](#-credits)

---

## 💡 Why this exists

Forza Horizon 5 on PC sends rich telemetry over UDP — but Steam Input only forwards generic rumble to the DualSense. The actual **adaptive triggers** (the killer feature of the controller) just sit there doing nothing.

This project bridges the gap with a tiny Python service:

- It reads FH5's UDP packets each frame.
- It computes a single adaptive-trigger command for each trigger.
- It writes those commands to the DualSense via raw HID — **without touching the rumble bits**, so Steam keeps doing its job.

The result: a brake pedal that feels like a brake pedal and a gas pedal that pushes back when the engine is working.

---

## 🎮 What you'll feel

### Left trigger — Brake
A **continuous, exponential** resistance. The trigger has steady weight even when you're not pressing it (small constant baseline), then climbs gently at first and gets sharply stiffer as you near full press. The **maximum force is intentionally capped well below 255** so the trigger keeps ~10% physical travel reserved — you should always be able to push it a little further. No jitter, no machine-gun buzzing, no off↔rigid toggling around the deadzone, no dead wall that swallows vibration effects.

If the handbrake is engaged, a flat bonus force is added so you can feel the difference.

### Right trigger — Throttle
Strict priority — **only one effect plays at a time**, so animations never fight:

| Priority | Effect | Feel |
|---------:|--------|------|
| 1 | **Gear-shift thump** | A short, deep `10 Hz` vibration burst (~80 ms). Felt *through* the trigger even when it's fully depressed — exactly when rigid effects vanish. |
| 2 | **Rev limiter buzz** | A `30 Hz` vibration when RPM is above the redline ratio. |
| 3 | **Progressive resistance** | **Linear** rigid force scaling with throttle position, from a `30`-force resting weight up to absolute max (`255`) at 100% pedal. Vibration effects (1) and (2) above bypass this rigid hold entirely via the priority chain, so they remain felt at full throttle. |

The chain lives in [TriggerAnimation._throttle()](src/modules/dualsense/triggers.py) — about 20 lines, easy to extend.

---

## ⚡ How it works

```
┌──────────────┐   UDP 5300    ┌──────────────┐   HID write    ┌─────────────┐
│  Forza H5    │ ────────────► │  fh5ds.py    │ ─────────────► │  DualSense  │
│  Data Out    │   324 bytes   │  per frame   │  triggers only │  controller │
└──────────────┘               └──────────────┘                └─────────────┘
                                      │
                                      ▼
                           Steam Input keeps owning rumble
```

- **UDP listener** ([modules/udplistener/main.py](src/modules/udplistener/main.py)) parses FH5's 324-byte telemetry packet (RPM, speed, accelerator, brake, gear, drivetrain…). Each frame it **drains the socket and uses only the latest packet**, so we never react to stale telemetry if the OS queues bursts.
- **TriggerAnimation** ([modules/dualsense/triggers.py](src/modules/dualsense/triggers.py)) turns telemetry into a `(left, right)` tuple of trigger commands.
- **DualSense HID layer** ([modules/dualsense/main.py](src/modules/dualsense/main.py)) writes them out, flipping only the trigger bits in `valid_flag0` so Steam's rumble bytes stay untouched. The HID device is opened in **non-blocking mode** so writes fire immediately instead of waiting for an input report (important on Bluetooth).

---

## 🛠️ Installation

**Requirements:** Python 3.10+, [`uv`](https://docs.astral.sh/uv/), a DualSense controller (USB or Bluetooth).

```bash
git clone https://github.com/<you>/Forza-Horizon-5-DualSense-Python.git
cd Forza-Horizon-5-DualSense-Python
uv sync
```

---

## 🎯 In-game setup

Open Forza Horizon 5 → **Settings → HUD and Gameplay**, scroll to the bottom:

| Setting | Value |
|---------|-------|
| Data Out | **ON** |
| Data Out IP Address | **127.0.0.1** |
| Data Out IP Port | **5300** |

<p align="center">
  <img src="img/en.png" alt="English Settings" width="48%" style="border-radius: 8px;">
  &nbsp;
  <img src="img/tr.png" alt="Turkish Settings" width="48%" style="border-radius: 8px;">
</p>

---

## ▶️ Run it

```bash
uv run src/main.py
```

You should hear a brief startup pulse on both triggers — that confirms HID writes are landing on the controller. After that, fire up FH5 and start driving.

> Run the script **before or while FH5 is loading**. Steam Input must be active for the controller; if you use HidHide, allowlist `python.exe`.

---

## ⚙️ CLI options

The defaults work for almost everyone. Use these only if you need them.

| Argument | Description | Default |
|----------|-------------|---------|
| `--host` | UDP bind address | `0.0.0.0` |
| `--port` | UDP port | `5300` |
| `--debug` | Verbose per-packet logging | off |

Example:
```bash
uv run src/main.py --port 5400 --debug
```

---

## 🎚️ Tuning the feel

Open [src/modules/settings.py](src/modules/settings.py) and edit any field. There are **no presets, no multipliers, no inheritance** — just one flat dataclass. Changes take effect on next launch.

### Brake (left trigger)

| Field | Default | Effect |
|-------|--------:|--------|
| `brake_baseline_force` | `10` | Always-held resistance. Prevents off↔rigid jitter. Increase for a heavier resting feel. |
| `brake_max_force` | `130` | Resistance at **100%** press. Stay below ~150 to leave physical headroom for vibration. |
| `brake_curve` | `3.5` | Higher = stays soft longer, sharp kick at the end. Max hardness only hits at ~100%, never before. |
| `handbrake_bonus` | `25` | Flat extra rigid force when the handbrake is engaged. |
| `brake_deadzone` | `20` | Ignore brake input below this raw value (out of 255). |

### Throttle (right trigger)

| Field | Default | Effect |
|-------|--------:|--------|
| `throttle_baseline_force` | `30` | Always-held resting weight (more than the brake \u2014 a gas pedal has a real spring). |
| `throttle_max_force` | `255` | Absolute max stiffness at **100%** pedal. Vibration effects (gear shift, rev limiter) bypass the rigid hold via the priority chain, so they're still felt at full throttle. |
| `throttle_curve` | `1.0` | `1.0` = **linear** \u2014 resistance grows evenly with pedal travel. Raise (e.g. `2.0`) for a softer initial press. |
| `accel_deadzone` | `20` | Ignore tiny accelerator noise. |

### Throttle effects

| Field | Default | Effect |
|-------|--------:|--------|
| `enable_gear_shift` | `True` | Toggle the shift thump. |
| `gear_shift_freq` | `10` Hz | Lower = deeper thump, higher = sharper click. |
| `gear_shift_amp` | `255` | Max amplitude (0–255). |
| `gear_shift_duration_ms` | `80` | How long the burst lasts. |
| `rev_limit_ratio` | `0.95` | Buzz when `rpm / max_rpm` exceeds this. |
| `rev_limit_freq` | `30` Hz | Buzz frequency. |
| `rev_limit_amp` | `255` | Buzz amplitude. |

### Connection / system

| Field | Default | Effect |
|-------|--------:|--------|
| `udp_host` | `"0.0.0.0"` | UDP bind address. |
| `udp_port` | `5300` | UDP port (must match FH5). |
| `udp_timeout` | `0.5` s | Listener timeout (used to detect "no telemetry"). |
| `startup_pulse_force` | `150` | Strength of the connect-confirm pulse. |

---

## 📁 Project layout

```
src/
├── main.py                          # Entry point: arg parsing, packet loop
└── modules/
    ├── settings.py                  # 👈 the only file you usually edit
    ├── dualsense/
    │   ├── main.py                  # HID layer (rumble bits left untouched)
    │   └── triggers.py              # Effect primitives + TriggerAnimation
    └── udplistener/
        └── main.py                  # UDP socket + 324-byte packet parser
```

---

## 🩺 Troubleshooting

| Symptom | Likely cause / fix |
|---------|--------------------|
| `DualSense gamepad interface not found` | Controller not connected, or HidHide is hiding it. Allowlist `python.exe` in HidHide. |
| `No UDP packets yet` after several seconds | FH5 Data Out is off, IP/port mismatch, or Windows Firewall is blocking the bind. |
| Triggers feel weak | Increase `brake_max_force` / `throttle_max_force` (but stay under ~150 to keep travel for vibration), or lower the `curve` toward `1.5`. |
| Triggers feel like a rock wall before pedal hits 100% | Lower `brake_max_force` / `throttle_max_force`. Above ~150 the DualSense rigid mode locks the trigger entirely. |
| Triggers feel too stiff at light press | Lower `brake_baseline_force`, or raise the `curve` toward `2.5`+. |
| Brake "machine-guns" / buzzes when barely pressed | This was the original off↔rigid jitter — already fixed by the always-held baseline. If it returns, raise the deadzone or the baseline force. |
| No vibration on gear shift | Make sure you're shifting **under power** at >3 km/h; idle / coasting shifts are intentionally ignored. |

---

## 🙏 Credits

Built by **[HamzaYslmn](https://github.com/HamzaYslmn)**.

---
*Built for an immersive racing experience — KISS code, real feedback.*

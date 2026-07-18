# AC Evo — DualSense Adaptive Triggers

> **Forked from [HamzaYslmn/Forza-Horizon-DualSense-Python](https://github.com/HamzaYslmn/Forza-Horizon-DualSense-Python)**

Real trigger feedback for **Assetto Corsa EVO** on PC with a DualSense controller.
Feel the brakes. Feel the engine. No setup juggling.

Originally created by Hamza Yeşilmen (HamzaYslmn).
Source: https://github.com/HamzaYslmn/Forza-Horizon-DualSense-Python

Sponsor: https://github.com/sponsors/HamzaYslmn

<div align="center">

</div>

---

## What it does

AC Evo publishes car telemetry via Windows shared memory, but Steam Input doesn't use the DualSense's **adaptive triggers**. This app fills the gap:

- **Left trigger (brake)** — pushes back harder the more you press. Buzzes like ABS when tires slip. Extra resistance when handbraking.
- **Right trigger (throttle)** — soft progressive resistance. Thumps on gear shifts. Buzzes at the rev limiter.

### How it talks to your controller without fighting Steam

```
┌──────────────────┐    SHM (Win32)  ┌──────────────────┐    HID write    ┌─────────────┐
│  Assetto Corsa EVO│ ──────────────► │  This app        │ ──────────────► │  DualSense  │
│  (shared memory)  │  telemetry      │  (trigger bits   │  triggers only  │  controller │
└──────────────────┘                  │   only)          │                 └─────────────┘
                                      └──────────────────┘                        ▲
                                                                                │
                                      ┌──────────────────┐    HID write           │
                                      │  Steam Input     │ ──────────────────────►│
                                      │  (rumble bits)   │  rumble + buttons      │
                                      └──────────────────┘
```

Both the app and Steam write to the same controller — but they touch **different bytes**:

- Steam owns the **rumble motors** and button mapping.
- This app only flips the **adaptive trigger** bits (`valid_flag0` bits `0x04` and `0x08`).
- The HID device is opened in **non-blocking mode**, so writes fire immediately instead of waiting on the controller. Nothing gets queued, nothing blocks Steam.

That's why you can run both at the same time and neither one breaks the other.

---

## Install

**You need:** Windows 10/11 or Linux, and a DualSense controller (USB or Bluetooth).

1. Go to the [latest release](https://github.com/HelloItMeMort/AC-Evo-DualSense-Python/releases/latest).
2. Download **`win_start.bat`** (Windows) or **`linux_start.sh`** (Linux).
3. Put it in any empty folder.
4. **Important:** I highly recommend installing **`uv`** manually first. Open PowerShell and run this command:
   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```
   - If you skip this, `win_start.bat` will try to install `uv` automatically. However, Windows might block this auto-install with an "Execution Policy" error in PowerShell.
   - **If you get the Execution Policy error:** Hold **Shift + Right-Click** in the folder, click **"Open PowerShell window here"**, paste `Set-ExecutionPolicy RemoteSigned -scope CurrentUser` and hit Enter, then type `Y` and Enter.
5. Double-click `win_start.bat` (or `linux_start.sh`).

The launcher handles downloading the app, preparing the environment, and running it. Next time you run it, it will also check for updates.

> [!NOTE]
> A standalone **Windows `.exe`** is also attached to each release as an experimental option. The **recommended** way to run the app is still **`win_start.bat`** — it self-updates and works the same across every Windows version.

> **Linux extras:** install `libhidapi` (`sudo apt install libhidapi-hidraw0` / `sudo pacman -S hidapi` / `sudo dnf install hidapi`) and the udev rule from `packaging/linux/70-dualsense.rules`. Then unplug/replug the controller once.
>
> **Wayland tray:** the minimize-to-tray icon needs the appindicator backend (X11 doesn't). Install these so the launcher can build PyGObject into its venv:
> - Debian/Ubuntu: `sudo apt install build-essential pkg-config python3-dev libcairo2-dev libgirepository-2.0-dev libayatana-appindicator3-1 gir1.2-ayatanaappindicator3-0.1`
> - Arch: `sudo pacman -S base-devel cairo gobject-introspection libayatana-appindicator`
> - Fedora: `sudo dnf install gcc pkg-config python3-devel cairo-devel gobject-introspection-devel libayatana-appindicator-gtk3`

---

## Run it

Double-click **`win_start.bat`** (Windows) or **`linux_start.sh`** (Linux).

You'll feel a short pulse on both triggers — that means it's working. Now launch Assetto Corsa EVO and drive.

> Start the launcher **before** AC Evo. If you use HidHide, allowlist `python.exe`.

---

## Manual install (for developers)

```bash
git clone https://github.com/HelloItMeMort/AC-Evo-DualSense-Python
cd AC-Evo-DualSense-Python/src
uv sync
uv run main.py
```

Need `uv`? `pip install uv` or [astral.sh/uv](https://astral.sh/uv/).

---

## DSX Support

I have integrated DSX (DualSenseX) support. Due to DSX limitations, you might not get the exact 1:1 experience, but I have done my best. A lower-fidelity version of the adaptive trigger effects is fully supported.

---

## Credits

**Original Forza mod by** [HamzaYslmn](https://github.com/HamzaYslmn).
**AC Evo port** — adapted for Assetto Corsa EVO's shared memory telemetry, with new effect mappings and tuning.

### Sponsor

- [HamzaYslmn](https://github.com/sponsors/HamzaYslmn) — original Forza mod author

---
*Built for an immersive racing experience*

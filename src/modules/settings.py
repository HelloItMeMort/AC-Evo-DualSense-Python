"""All tunables in one place. Edit values directly — no presets, no overrides.

Force values are 0–255 (DualSense raw). Frequencies are Hz.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Settings:
    # --- UDP ---
    udp_host: str = "0.0.0.0"
    udp_port: int = 5300
    udp_timeout: float = 0.5

    # --- Input deadzones (raw 0-255) ---
    accel_deadzone: int = 0
    brake_deadzone: int = 0

    # --- Brake (left trigger): exponential ramp baseline -> full press ---
    # Baseline is ALWAYS held (no off()) so the trigger never "machine-guns"
    # by toggling rigid<->off around the deadzone.
    # Max stays well below 255 so the trigger keeps ~10% physical travel
    # available — needed so vibration effects are still felt at full press.
    brake_baseline_force: int = 10  # constant weight when not pressed
    brake_max_force: int = 130      # at full press (NOT 255 — reserves headroom)
    brake_curve: float = 10.0        # >1 = soft early, sharp at the end
    handbrake_bonus: int = 25       # extra rigid when handbrake engaged

    # --- Throttle (right trigger): exponential ramp baseline -> full press ---
    # Kept softer than the brake — a real gas pedal has very little resistance
    # compared to a brake pedal, and we need finger-travel budget free for the
    # gear-shift / rev-limit vibration animations.
    throttle_baseline_force: int = 10
    throttle_max_force: int = 90    # softer than brake on purpose
    throttle_curve: float = 12.5     # steeper = even softer at light press

    # --- Rev limiter buzz (right trigger) ---
    rev_limit_ratio: float = 0.95   # rpm / max_rpm above this = limiter
    rev_limit_freq: int = 30
    rev_limit_amp: int = 255

    # --- Gear shift thump (right trigger, single vibration burst) ---
    enable_gear_shift: bool = True
    gear_shift_freq: int = 10           # deep thump
    gear_shift_amp: int = 255
    gear_shift_duration_ms: float = 80.0

    # --- Misc ---
    startup_pulse_force: int = 150

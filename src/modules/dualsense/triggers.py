"""DualSense adaptive trigger effects — KISS edition.

Design rule: trigger forces are capped well below 255 so the trigger always
keeps ~10% physical travel free. That's the headroom vibration animations
need to actually be felt under your finger.

Right trigger (throttle), strict priority — only one effect at a time:
    1. Gear shift  -> 10 Hz vibration burst (~80 ms)
    2. Rev limiter -> 30 Hz vibration
    3. Throttle    -> exponential rigid resistance (baseline -> max)

Left trigger (brake): exponential rigid resistance, baseline -> max.
Handbrake adds a flat bonus.
"""

import time

# --- Raw mode bytes ---
M_OFF   = 0x05
M_RIGID = 0x01
M_PULSE = 0x06


def _clamp(v, hi=255):
    return max(0, min(hi, round(v)))


def off():
    return (M_OFF, 0, 0)

def rigid(force):
    return (M_RIGID, 0, _clamp(force))

def vibration(freq_hz, amplitude):
    return (M_PULSE, _clamp(freq_hz), _clamp(amplitude))


class TriggerAnimation:
    """Computes (left, right) trigger output from FH5 telemetry each frame."""

    def __init__(self):
        self._prev_gear = 0
        self._shift_until = 0.0

    def update(self, t: dict, s) -> tuple:
        if not t.get("on", False):
            return off(), off()
        now = time.monotonic()
        return self._brake(t, s), self._throttle(t, s, now)

    # --- Left trigger: brake -------------------------------------------------

    def _brake(self, t, s):
        brake = t.get("brake", 0)
        # Always hold baseline so the trigger never toggles off<->rigid (no
        # "machine gun" jitter near the deadzone).
        if brake < s.brake_deadzone:
            return rigid(s.brake_baseline_force)
        ratio = (brake - s.brake_deadzone) / max(255 - s.brake_deadzone, 1)
        force = s.brake_baseline_force + (s.brake_max_force - s.brake_baseline_force) * (ratio ** s.brake_curve)
        if t.get("handbrake", 0):
            force += s.handbrake_bonus
        return rigid(force)

    # --- Right trigger: throttle (priority chain) ----------------------------

    def _throttle(self, t, s, now):
        accel = t.get("accel", 0)
        gear = t.get("gear", 0)
        speed = t.get("speed", 0.0)

        # Detect gear change under power -> arm shift burst
        if (s.enable_gear_shift
                and self._prev_gear != 0
                and gear != self._prev_gear
                and accel > s.accel_deadzone
                and speed > 3.0):
            self._shift_until = now + s.gear_shift_duration_ms / 1000.0
        self._prev_gear = gear

        # 1. Gear shift burst wins everything (you feel it through the trigger)
        if now < self._shift_until:
            return vibration(s.gear_shift_freq, s.gear_shift_amp)

        # No throttle pressed -> hold baseline (no off<->rigid toggle jitter)
        if accel < s.accel_deadzone:
            return rigid(s.throttle_baseline_force)

        # 2. Rev limiter
        rpm_r = self._ratio(t.get("rpm", 0.0), t.get("max_rpm", 0.0))
        if rpm_r > s.rev_limit_ratio:
            return vibration(s.rev_limit_freq, s.rev_limit_amp)

        # 3. Progressive resistance (exponential: soft early, sharp late).
        # Capped at throttle_max_force — leaves physical headroom so vibration
        # effects (gear-shift, rev-limiter) are still felt at full throttle.
        ratio = (accel - s.accel_deadzone) / max(255 - s.accel_deadzone, 1)
        force = s.throttle_baseline_force + (s.throttle_max_force - s.throttle_baseline_force) * (ratio ** s.throttle_curve)
        return rigid(force)

    # --- Helpers -------------------------------------------------------------

    @staticmethod
    def _ratio(value, max_value):
        if max_value <= 0:
            return 0.0
        return max(0.0, min(float(value) / float(max_value), 1.0))

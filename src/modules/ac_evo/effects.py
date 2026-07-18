"""AC Evo-aware adaptive trigger logic.

TriggerAnimations - every effect (ABS, gear shift, rev limiter, resistance...).
                    Owns timing state for effects that span frames.
Controller        - builds L2 / R2 and produces a frame for each per tick.

Differences from Forza mod:
  - slipRatio (longitudinal) from physics block offset 640
  - absInAction flag for ABS detection (more precise than combined slip)
  - RWD default driven wheels (no drive_train enum in AC Evo SHM)
  - tyreDirtyLevel heuristic for surface detection (no surface_rumble/wheel_in_puddle)
  - Dynamic max_rpm from physics.currentMaxRpm
"""
import logging
import time

log = logging.getLogger("acevo")

from modules.dualsense.adaptive_trigger import (
    RAW_MAX, off, rigid, vibrate, vibrate_zones, rigid_zones,
)

# Below this car speed (km/h) I trust raw wheel rotation instead of slip_ratio
LOW_SPEED_KMH = 5.0
# Wheel angular speed (rad/s) above which I count as spinning at standstill.
BURNOUT_ROT_THRESHOLD = 30.0

# AC Evo default driven wheels (RWD — no drive_train enum in SHM)
DRIVEN_WHEELS = ("rl", "rr")


def _amp_to_strength(amp_byte):
    return max(1, min(8, (max(0, int(amp_byte)) // 32) + 1))


def _max_slip(t, prefix, wheels=None):
    if wheels is None:
        wheels = ("fl", "fr", "rl", "rr")
    return max(abs(t[f"{prefix}_{w}"]) for w in wheels)


def _ramp(value, deadzone, baseline, max_force, curve, ceiling):
    """deadzone..ceiling -> baseline..max_force, curve = exponent."""
    if value < deadzone:
        return baseline
    r = min(1.0, (value - deadzone) / max(ceiling - deadzone, 1))
    return baseline + (max_force - baseline) * (r ** curve)


def _wall_state(value, engaged, engage_at, release_at):
    """Hysteresis: enter wall at >= engage_at, leave at < release_at."""
    return value >= release_at if engaged else value >= engage_at


def build_wall(zones):
    """Static firmware wall - top `zones` (1-9) maxed. Built once at startup."""
    n = max(1, min(9, int(zones)))
    return rigid_zones([0] * (10 - n) + [8] * n)


def build_brake_walls(static_at, force, wall_zones):
    """End wall (top `wall_zones`) plus a static wall from brake byte `static_at` down."""
    n = max(1, min(9, int(wall_zones)))
    strength = _amp_to_strength(force)
    start = min(9, int(static_at) * 10 // 256)
    zones = [strength if i >= start else 0 for i in range(10)]
    for i in range(10 - n, 10):
        zones[i] = 8
    return rigid_zones(zones)


# --- Animations -----------------------------------------------------------

class TriggerAnimations:
    """Every trigger effect lives here. Methods return an HID frame or None."""

    def __init__(self):
        self._prev_gear = None
        self._shift_until = 0.0
        self._rev_until = 0.0

    def arm_shift(self, t, s, now):
        gear = t["gear"]
        if self._prev_gear is not None and gear != self._prev_gear:
            log.info("Gear shift: %d -> %d", self._prev_gear, gear)
            self._shift_until = now + s.gear_shift_duration_ms / 1000.0
        self._prev_gear = gear

    def shift_burst(self, s, now, pedal, wall_engage_at):
        if now >= self._shift_until:
            return None
        if pedal >= (wall_engage_at + RAW_MAX) // 2:
            return vibrate_zones(_amp_to_strength(s.gear_shift_amp), 0, s.wall_zones)
        return vibrate(s.gear_shift_freq, s.gear_shift_amp)

    def rev_buzz(self, t, s, now):
        if not s.enable_rev_limiter:
            return None
        handbrake_full_throttle = (
            t["accel"] >= RAW_MAX * 0.8 and
            t["handbrake"] > 16 and t["speed"] < 1)
        if handbrake_full_throttle:
            return vibrate(s.rev_limit_freq, s.rev_limit_amp)
        if t["accel"] >= s.accel_deadzone:
            max_rpm = t["max_rpm"]
            rpm_r = t["rpm"] / max_rpm if max_rpm > 0 else 0.0
            if rpm_r > s.rev_limit_ratio:
                self._rev_until = now + s.rev_limit_hold_ms / 1000.0
        if now < self._rev_until:
            return vibrate(s.rev_limit_freq, s.rev_limit_amp)
        return None

    def idle_buzz(self, t, s, now):
        if not s.enable_idle_buzz:
            return None
        if t["speed"] >= s.idle_max_speed_kmh:
            return None
        if not (1 <= t["accel"] <= s.idle_accel_max):
            return None
        loud = (now / s.idle_period_s) % 1.0 < 0.5
        amp = s.idle_amp_high if loud else s.idle_amp_low
        return vibrate(s.idle_freq, amp)

    def wheelspin_buzz(self, t, s, now):
        """R2 buzz when tires lose grip (wheelspin or drift).

        AC Evo adaptations:
        - Uses slipRatio (longitudinal, offset 640) instead of tire_combined_slip
        - No surface_rumble or wheel_in_puddle fields
        - Surface detection via tyreDirtyLevel heuristic
        """
        if not s.enable_wheelspin_buzz:
            return None
        if t["accel"] < s.accel_deadzone:
            return None
        wheels = DRIVEN_WHEELS
        max_sr = max(abs(t[f"slipRatio_{w}"]) for w in wheels)
        if t["speed"] < LOW_SPEED_KMH:
            if max(abs(t[f"wheelRot_{w}"]) for w in wheels) < BURNOUT_ROT_THRESHOLD:
                return None
        else:
            if max_sr < 0.3:
                return None
            if max_sr > 1.0:
                log.debug("Wheelspin detected: slipRatio=%.2f speed=%.1f", max_sr, t["speed"])

        amp = s.wheelspin_amp
        # Surface profile: tyreDirtyLevel heuristic (no surface_rumble available)
        max_dirty = max(t[f"tyreDirty_{w}"] for w in wheels)
        if max_dirty > 2.5:
            # Gravel/dirt: chunky low-frequency thump
            return vibrate(20, min(255, amp * 3))
        if max_dirty > 1.5:
            # Loose/gritty: medium rumble
            return vibrate(50, min(255, int(amp * 2)))
        return vibrate(130, amp)  # tarmac: sharp squeal

    def abs_pulse(self, t, s):
        if not s.enable_abs:
            return None
        if t["brake"] < max(1, s.abs_brake_threshold) or t["speed"] < s.abs_min_speed_kmh:
            return None
        max_sr = _max_slip(t, "slipRatio")
        max_sa = _max_slip(t, "slipAngle")
        if max_sr < s.abs_slip_ratio_threshold and max_sa < s.abs_combined_slip_threshold:
            return None
        log.debug("ABS pulse: brake=%d speed=%.1f absInAction=%s slipR=%.2f slipA=%.2f",
                  t["brake"], t["speed"], t.get("absInAction"), max_sr, max_sa)
        return vibrate(s.abs_freq, s.abs_amp)

    def brake_resistance(self, t, s):
        handbrake = s.enable_handbrake_bonus and t["handbrake"]
        if not s.enable_brake_resistance:
            return rigid(s.handbrake_bonus) if handbrake else off()
        force = _ramp(t["brake"], s.brake_deadzone, s.brake_baseline_force,
                      s.brake_max_force, s.brake_curve, s.brake_wall_engage_at)
        if handbrake:
            force += s.handbrake_bonus
        return rigid(force)

    def throttle_ramp(self, t, s):
        if not s.enable_throttle_resistance:
            return off()
        return rigid(_ramp(t["accel"], s.accel_deadzone, s.throttle_baseline_force,
                           s.throttle_max_force, s.throttle_curve, s.throttle_wall_engage_at))


# --- Controller -----------------------------------------------------------

class Controller:
    """Produces (L2, R2) frames per tick.

    L2 priority (top wins):
        1. Gear shift thump
        2. ABS pulse (tire lockup — absInAction flag + slipRatio threshold)
        3. Firmware end wall
        4. Static brake wall
        5. Brake resistance

    R2 priority (top wins):
        1. Gear shift thump
        2. Idle buzz
        3. Rev limiter buzz
        4. Wheelspin buzz
        5. Firmware end wall
        6. Throttle resistance
    """

    def __init__(self, settings):
        self.anim = TriggerAnimations()
        self.wall = build_wall(settings.wall_zones)
        self._l2_in_wall = False
        self._r2_in_wall = False

    def update(self, t, s):
        if not t["on"]:
            return off(), off()
        now = time.monotonic()
        if s.enable_gear_shift or s.enable_gear_shift_brake:
            self.anim.arm_shift(t, s, now)
        return self.L2(t, s, now), self.R2(t, s, now)

    def L2(self, t, s, now):
        brake = t["brake"]

        # 1. Gear shift thump
        if s.enable_gear_shift_brake:
            shift = self.anim.shift_burst(s, now, brake, s.brake_wall_engage_at)
            if shift:
                return shift

        # 2. ABS pulse
        pulse = self.anim.abs_pulse(t, s)
        if pulse:
            return pulse

        # 3. Firmware end wall
        self._l2_in_wall = _wall_state(brake, self._l2_in_wall,
                                       s.brake_wall_engage_at, s.brake_wall_release_at)
        if self._l2_in_wall:
            return self.wall

        # 4. Static brake wall
        if s.enable_brake_static_wall:
            return build_brake_walls(s.brake_static_wall_at, s.brake_static_wall_force, s.wall_zones)

        # 5. Brake resistance
        return self.anim.brake_resistance(t, s)

    def R2(self, t, s, now):
        accel = t["accel"]

        # 1. Gear shift thump
        if s.enable_gear_shift:
            shift = self.anim.shift_burst(s, now, accel, s.throttle_wall_engage_at)
            if shift:
                return shift

        # 2. Idle buzz
        idle = self.anim.idle_buzz(t, s, now)
        if idle is not None:
            return idle

        # 3. Rev limiter buzz
        rev = self.anim.rev_buzz(t, s, now)
        if rev:
            return rev

        # 4. Wheelspin buzz
        spin = self.anim.wheelspin_buzz(t, s, now)
        if spin is not None:
            return spin

        # 5. Firmware end wall
        self._r2_in_wall = _wall_state(accel, self._r2_in_wall,
                                       s.throttle_wall_engage_at, s.throttle_wall_release_at)
        if self._r2_in_wall:
            return self.wall

        # 6. Throttle resistance
        return self.anim.throttle_ramp(t, s)

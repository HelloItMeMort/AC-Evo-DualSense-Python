"""All tunables in one place. Forces 0-255, frequencies in Hz."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Settings:
    # MARK: Shared Memory
    shm_poll_hz: int = 60                  # SHM poll rate (replaces game_poll_interval_s)

    # MARK: Pedal shared
    pedal_value_max: int = 255
    wall_zones: int = 2

    # MARK: L2 brake resistance
    enable_brake_resistance: bool = True
    brake_deadzone: int = 35               # Softer pedal feel in AC Evo
    brake_baseline_force: int = 18
    brake_max_force: int = 100             # Heavier brake feel; FFB competes
    brake_curve: float = 5.0
    brake_wall_engage_at: int = 250
    brake_wall_release_at: int = 200
    enable_brake_static_wall: bool = False
    brake_static_wall_at: int = 128
    brake_static_wall_force: int = 255

    # MARK: L2 handbrake bonus
    enable_handbrake_bonus: bool = True
    handbrake_bonus: int = 90              # More pronounced in AC Evo

    # MARK: L2 ABS pulse
    enable_abs: bool = True
    abs_brake_threshold: int = 60
    abs_min_speed_kmh: float = 15.0
    abs_slip_ratio_threshold: float = 0.15
    abs_combined_slip_threshold: float = 1.0
    abs_freq: int = 20
    abs_amp: int = 80

    # MARK: R2 throttle resistance
    enable_throttle_resistance: bool = True
    accel_deadzone: int = 35               # Softer pedal feel in AC Evo
    throttle_baseline_force: int = 1
    throttle_max_force: int = 8
    throttle_curve: float = 5.0
    throttle_wall_engage_at: int = 250
    throttle_wall_release_at: int = 200

    # MARK: R2 rev limiter
    enable_rev_limiter: bool = True
    rev_limit_ratio: float = 0.96          # More precise RPM tracking
    rev_limit_freq: int = 30
    rev_limit_amp: int = 12
    rev_limit_hold_ms: float = 120.0

    # MARK: R2 wheelspin buzz
    enable_wheelspin_buzz: bool = True
    wheelspin_amp: int = 12

    # MARK: R2 idle buzz
    enable_idle_buzz: bool = True
    idle_max_speed_kmh: float = 5.0
    idle_accel_max: int = 64
    idle_freq: int = 30
    idle_amp_low: int = 1
    idle_amp_high: int = 30
    idle_period_s: float = 0.5

    # MARK: Gear shift
    enable_gear_shift: bool = True
    enable_gear_shift_brake: bool = True
    gear_shift_freq: int = 10
    gear_shift_amp: int = 255
    gear_shift_duration_ms: float = 100.0

    # MARK: System - startup pulse
    enable_startup_pulse: bool = True
    startup_pulse_force: int = 150

    # MARK: System - reconnect
    enable_reconnect: bool = False
    reconnect_interval_s: float = 5.0

    # MARK: System - controller selection
    controller_lock_serial: str = ""

    # MARK: System - updates
    check_for_updates: bool = False

    # MARK: System - DSX
    use_dsx: bool = False
    dsx_host: str = "127.0.0.1"
    dsx_port: int = 6969

    # MARK: System - language
    language: str = "en"

    # MARK: System - auto exit
    exit_on_game_close: bool = True
    game_process_name_contains: tuple = ("acevo",)
    telemetry_lost_exit_s: float = 60.0

"""AC Evo shared memory reader — attach, parse, and normalize telemetry.

Connects to the Windows named shared-memory blocks published by AC Evo:
  - Local\\acevo_pmf_physics (800B, physics-rate ~333Hz)
  - Local\\acevo_pmf_graphics (~8KB, HUD-rate)

Uses ctypes structs based on the official SHM documentation.
Includes a torn-read guard via packetId change-detection.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import sys
import time
from ctypes import (c_bool, c_byte, c_char, c_float, c_int8, c_int16, c_int32,
                    c_uint8, c_uint16, c_uint32, c_uint64)
from typing import Optional

log = logging.getLogger("acevo")

# ---------------------------------------------------------------------------
# Win32 named mapping (read-only OpenFileMappingW)
# ---------------------------------------------------------------------------

_FILE_MAP_READ = 0x0004

_KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)

_OpenFileMappingW = _KERNEL32.OpenFileMappingW
_OpenFileMappingW.argtypes = [ctypes.c_uint32, ctypes.c_int32, ctypes.c_wchar_p]
_OpenFileMappingW.restype = ctypes.c_void_p

_MapViewOfFile = _KERNEL32.MapViewOfFile
_MapViewOfFile.argtypes = [ctypes.c_void_p, ctypes.c_uint32,
                           ctypes.c_uint32, ctypes.c_uint32, ctypes.c_size_t]
_MapViewOfFile.restype = ctypes.c_void_p

_UnmapViewOfFile = _KERNEL32.UnmapViewOfFile
_UnmapViewOfFile.argtypes = [ctypes.c_void_p]
_UnmapViewOfFile.restype = ctypes.c_int32

_CloseHandle = _KERNEL32.CloseHandle
_CloseHandle.argtypes = [ctypes.c_void_p]
_CloseHandle.restype = ctypes.c_int32


class NamedMapping:
    """Read-only view of an existing Windows named file-mapping.

    Raises FileNotFoundError when the name does not exist (game not running).
    """

    def __init__(self, name: str, size: int) -> None:
        handle = _OpenFileMappingW(_FILE_MAP_READ, False, name)
        if not handle:
            err = ctypes.get_last_error()
            if err == 2:
                raise FileNotFoundError(f"named mapping not found: {name}")
            raise OSError(err, ctypes.FormatError(err), name)
        view = _MapViewOfFile(handle, _FILE_MAP_READ, 0, 0, size)
        if not view:
            err = ctypes.get_last_error()
            _CloseHandle(handle)
            raise OSError(err, ctypes.FormatError(err), name)
        self._handle = handle
        self._view = view
        self._size = size

    def read(self) -> bytes:
        return ctypes.string_at(self._view, self._size)

    def close(self) -> None:
        if self._view is not None:
            _UnmapViewOfFile(self._view)
            self._view = None
        if self._handle is not None:
            _CloseHandle(self._handle)
            self._handle = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Shared memory tags and sizes
# ---------------------------------------------------------------------------

PHYSICS_TAG = "Local\\acevo_pmf_physics"
GRAPHICS_TAG = "Local\\acevo_pmf_graphics"
STATIC_TAG = "Local\\acevo_pmf_static"

PHYSICS_SIZE = 4096
GRAPHICS_SIZE = 8192
STATIC_SIZE = 2048


# ---------------------------------------------------------------------------
# ctypes structs
# ---------------------------------------------------------------------------

class _SPageFilePhysics(ctypes.Structure):
    """AC Evo physics layout (800B total: 416B AC1 prefix + 384B EVO additions)."""
    _pack_ = 4
    _fields_ = [
        # AC1-compatible prefix (offsets 0..415)
        ("packetId", c_int32),
        ("gas", c_float),
        ("brake", c_float),
        ("fuel", c_float),
        ("gear", c_int32),
        ("rpms", c_int32),
        ("steerAngle", c_float),
        ("speedKmh", c_float),
        ("velocity", c_float * 3),
        ("accG", c_float * 3),
        ("wheelSlip", c_float * 4),
        ("wheelLoad", c_float * 4),
        ("wheelsPressure", c_float * 4),
        ("wheelAngularSpeed", c_float * 4),
        ("tyreWear", c_float * 4),
        ("tyreDirtyLevel", c_float * 4),
        ("tyreCoreTemperature", c_float * 4),
        ("camberRAD", c_float * 4),
        ("suspensionTravel", c_float * 4),
        ("drs", c_float),
        ("tc", c_float),
        ("heading", c_float),
        ("pitch", c_float),
        ("roll", c_float),
        ("cgHeight", c_float),
        ("carDamage", c_float * 5),
        ("numberOfTyresOut", c_int32),
        ("pitLimiterOn", c_int32),
        ("abs", c_float),
        ("kersCharge", c_float),
        ("kersInput", c_float),
        ("autoShifterOn", c_int32),
        ("rideHeight", c_float * 2),
        ("turboBoost", c_float),
        ("ballast", c_float),
        ("airDensity", c_float),
        ("airTemp", c_float),
        ("roadTemp", c_float),
        ("localAngularVel", c_float * 3),
        ("finalFF", c_float),
        ("performanceMeter", c_float),
        ("engineBrake", c_int32),
        ("ersRecoveryLevel", c_int32),
        ("ersPowerLevel", c_int32),
        ("ersHeatCharging", c_int32),
        ("ersIsCharging", c_int32),
        ("kersCurrentKJ", c_float),
        ("drsAvailable", c_int32),
        ("drsEnabled", c_int32),
        ("brakeTemp", c_float * 4),
        ("clutch", c_float),
        ("tyreTempI", c_float * 4),
        ("tyreTempM", c_float * 4),
        ("tyreTempO", c_float * 4),
        # AC Evo additions (offsets 416..799)
        ("isAIControlled", c_int32),
        ("tyreContactPoint", (c_float * 3) * 4),
        ("tyreContactNormal", (c_float * 3) * 4),
        ("tyreContactHeading", (c_float * 3) * 4),
        ("brakeBias", c_float),
        ("localVelocity", c_float * 3),
        ("P2PActivations", c_int32),
        ("P2PStatus", c_int32),
        ("currentMaxRpm", c_int32),
        ("mz", c_float * 4),
        ("fx", c_float * 4),
        ("fy", c_float * 4),
        ("slipRatio", c_float * 4),
        ("slipAngle", c_float * 4),
        ("tcInAction", c_int32),
        ("absInAction", c_int32),
        ("suspensionDamage", c_float * 4),
        ("tyreTemp", c_float * 4),
        ("waterTemp", c_float),
        ("brakeTorque", c_float * 4),
        ("frontBrakeCompound", c_int32),
        ("rearBrakeCompound", c_int32),
        ("padLife", c_float * 4),
        ("discLife", c_float * 4),
        ("ignitionOn", c_int32),
        ("starterEngineOn", c_int32),
        ("isEngineRunning", c_int32),
        ("kerbVibration", c_float),
        ("slipVibrations", c_float),
        ("roadVibrations", c_float),
        ("absVibrations", c_float),
    ]


class _SPageFileStatic(ctypes.Structure):
    """AC Evo static block — session/track metadata, written once per session."""
    _pack_ = 4
    _fields_ = [
        ("sm_version", c_char * 15),
        ("ac_evo_version", c_char * 15),
        ("session", c_int32),
        ("session_name", c_char * 33),
        ("event_id", c_uint8),
        ("session_id", c_uint8),
        ("starting_grip", c_int32),
        ("starting_ambient_temperature_c", c_float),
        ("starting_ground_temperature_c", c_float),
        ("is_static_weather", c_bool),
        ("is_timed_race", c_bool),
        ("is_online", c_bool),
        ("number_of_sessions", c_int32),
        ("nation", c_char * 33),
        ("longitude", c_float),
        ("latitude", c_float),
        ("track", c_char * 33),
        ("track_configuration", c_char * 33),
        ("track_length_m", c_float),
    ]


class _SMEvoTyreState(ctypes.Structure):
    """SMEvoTyreState [256 B] — per-corner tyre snapshot."""
    _pack_ = 4
    _fields_ = [
        ("slip", c_float),
        ("lock", c_bool),
        ("tyre_pressure", c_float),
        ("tyre_temperature_c", c_float),
        ("brake_temperature_c", c_float),
        ("brake_pressure", c_float),
        ("tyre_temperature_left", c_float),
        ("tyre_temperature_center", c_float),
        ("tyre_temperature_right", c_float),
        ("tyre_compound_front", c_char * 33),
        ("tyre_compound_rear", c_char * 33),
        ("tyre_normalized_pressure", c_float),
        ("tyre_normalized_temperature_left", c_float),
        ("tyre_normalized_temperature_center", c_float),
        ("tyre_normalized_temperature_right", c_float),
        ("brake_normalized_temperature", c_float),
        ("tyre_normalized_temperature_core", c_float),
        ("_reserved", c_byte * 128),
    ]


class _SPageFileGraphic(ctypes.Structure):
    """AC Evo graphics block — HUD/graphics data."""
    _pack_ = 4
    _fields_ = [
        ("packetId", c_int32),
        ("status", c_int32),
        ("focused_car_id_a", c_uint64),
        ("focused_car_id_b", c_uint64),
        ("player_car_id_a", c_uint64),
        ("player_car_id_b", c_uint64),
        ("rpm", c_uint16),
        ("is_rpm_limiter_on", c_bool),
        ("is_change_up_rpm", c_bool),
        ("is_change_down_rpm", c_bool),
        ("tc_active", c_bool),
        ("abs_active", c_bool),
        ("esc_active", c_bool),
        ("launch_active", c_bool),
        ("is_ignition_on", c_bool),
        ("is_engine_running", c_bool),
        ("kers_is_charging", c_bool),
        ("is_wrong_way", c_bool),
        ("is_drs_available", c_bool),
        ("battery_is_charging", c_bool),
        ("is_max_kj_per_lap_reached", c_bool),
        ("is_max_charge_kj_per_lap_reached", c_bool),
        ("display_speed_kmh", c_int16),
        ("display_speed_mph", c_int16),
        ("display_speed_ms", c_int16),
        ("pitspeeding_delta", c_float),
        ("gear_int", c_int16),
        ("rpm_percent", c_float),
        ("gas_percent", c_float),
        ("brake_percent", c_float),
        ("handbrake_percent", c_float),
        ("clutch_percent", c_float),
        ("steering_percent", c_float),
        ("ffb_strength", c_float),
        ("car_ffb_multiplier", c_float),
        ("water_temperature_percent", c_float),
        ("water_pressure_bar", c_float),
        ("fuel_pressure_bar", c_float),
        ("water_temperature_c", c_int8),
        ("air_temperature_c", c_int8),
        ("oil_temperature_c", c_float),
        ("oil_pressure_bar", c_float),
        ("exhaust_temperature_c", c_float),
        ("g_forces_x", c_float),
        ("g_forces_y", c_float),
        ("g_forces_z", c_float),
        ("turbo_boost", c_float),
        ("turbo_boost_level", c_float),
        ("turbo_boost_perc", c_float),
        ("steer_degrees", c_int32),
        ("current_km", c_float),
        ("total_km", c_uint32),
        ("total_driving_time_s", c_uint32),
        ("time_of_day_hours", c_int32),
        ("time_of_day_minutes", c_int32),
        ("time_of_day_seconds", c_int32),
        ("delta_time_ms", c_int32),
        ("current_lap_time_ms", c_int32),
        ("predicted_lap_time_ms", c_int32),
        ("fuel_liter_current_quantity", c_float),
        ("fuel_liter_current_quantity_percent", c_float),
        ("fuel_liter_per_km", c_float),
        ("km_per_fuel_liter", c_float),
        ("current_torque", c_float),
        ("current_bhp", c_int32),
        ("tyre_lf", _SMEvoTyreState),
        ("tyre_rf", _SMEvoTyreState),
        ("tyre_lr", _SMEvoTyreState),
        ("tyre_rr", _SMEvoTyreState),
        ("npos", c_float),
        ("kers_charge_perc", c_float),
        ("kers_current_perc", c_float),
        ("control_lock_time", c_float),
        ("fuel_liter_used", c_float),
        ("fuel_liter_per_lap", c_float),
        ("laps_possible_with_fuel", c_float),
        ("battery_temperature", c_float),
        ("battery_voltage", c_float),
        ("instantaneous_fuel_liter_per_km", c_float),
        ("instantaneous_km_per_fuel_liter", c_float),
        ("gear_rpm_window", c_float),
        ("total_lap_count", c_int32),
        ("current_pos", c_uint32),
        ("total_drivers", c_uint32),
        ("last_laptime_ms", c_int32),
        ("best_laptime_ms", c_int32),
        ("flag", c_int32),
        ("global_flag", c_int32),
        ("max_gears", c_uint32),
        ("engine_type", c_int32),
        ("has_kers", c_bool),
        ("is_last_lap", c_bool),
        ("performance_mode_name", c_char * 33),
        ("diff_coast_raw_value", c_float),
        ("diff_power_raw_value", c_float),
        ("race_cut_gained_time_ms", c_int32),
        ("distance_to_deadline", c_int32),
        ("race_cut_current_delta", c_float),
        ("player_ping", c_int32),
        ("player_latency", c_int32),
        ("player_cpu_usage", c_int32),
        ("player_cpu_usage_avg", c_int32),
        ("player_qos", c_int32),
        ("player_qos_avg", c_int32),
        ("player_fps", c_int32),
        ("player_fps_avg", c_int32),
        ("driver_name", c_char * 33),
        ("driver_surname", c_char * 33),
        ("car_model", c_char * 33),
        ("is_in_pit_box", c_bool),
        ("is_in_pit_lane", c_bool),
        ("is_valid_lap", c_bool),
        ("car_coordinates", (c_float * 3) * 60),
        ("gap_ahead", c_float),
        ("gap_behind", c_float),
        ("active_cars", c_uint8),
        ("fuel_per_lap", c_float),
        ("fuel_estimated_laps", c_float),
        ("max_fuel", c_float),
        ("max_turbo_boost", c_float),
        ("use_single_compound", c_bool),
        ("car_ids", (c_uint64 * 2) * 60),
    ]


# ---------------------------------------------------------------------------
# Telemetry reader
# ---------------------------------------------------------------------------

# Wheel index mapping: FL=0, FR=1, RL=2, RR=3
_WHEELS = ("fl", "fr", "rl", "rr")


class AcEvoReader:
    """Polls AC Evo shared memory and returns normalized telemetry dicts.

    Connection is best-effort: if the game is not running, read_latest() returns None.
    Includes a torn-read guard: verifies packetId changes by at most 1 between reads.
    """

    def __init__(self, poll_hz: int = 60) -> None:
        self._poll_hz = poll_hz
        self._poll_interval = 1.0 / poll_hz
        self._physics_mm: Optional[NamedMapping] = None
        self._graphics_mm: Optional[NamedMapping] = None
        self._prev_packet_id: Optional[int] = None
        self._connected = False

    def _try_connect(self) -> bool:
        """Attach to SHM blocks. Returns True if successful."""
        try:
            if self._physics_mm is None:
                self._physics_mm = NamedMapping(PHYSICS_TAG, PHYSICS_SIZE)
            if self._graphics_mm is None:
                self._graphics_mm = NamedMapping(GRAPHICS_TAG, GRAPHICS_SIZE)
            self._connected = True
            return True
        except FileNotFoundError as e:
            self._connected = False
            log.debug("SHM not available: %s", e)
            return False
        except OSError as e:
            log.warning("SHM connect error: %s", e)
            return False

    def _drain(self, ph: _SPageFilePhysics) -> int:
        """Re-read until packetId is stable (drain stale reads). Returns packetId."""
        pid = ph.packetId
        for _ in range(3):
            ph_new = _SPageFilePhysics.from_buffer_copy(self._physics_mm.read(), 0)
            if ph_new.packetId == pid:
                break
            pid = ph_new.packetId
        return pid

    def read_latest(self) -> Optional[dict]:
        """Read the latest telemetry frame. Returns None if not connected to the game."""
        if not self._connected:
            if not self._try_connect():
                return None

        try:
            # Physics block
            ph = _SPageFilePhysics.from_buffer_copy(self._physics_mm.read(), 0)

            # Graphics block
            gr = _SPageFileGraphic.from_buffer_copy(self._graphics_mm.read(), 0)
        except (OSError, ValueError) as e:
            log.warning("SHM read error, dropping: %s", e)
            self._physics_mm = None
            self._graphics_mm = None
            self._connected = False
            return None

        # Torn-read guard: verify packetId changes by at most 1, retry iteratively
        max_retries = 10
        for _ in range(max_retries):
            pid = self._drain(ph)
            if self._prev_packet_id is not None:
                diff = pid - self._prev_packet_id
                if diff < 0:
                    diff = -diff
                if diff > 1:
                    log.debug("Torn read detected (packetId jump: %d), retrying", diff)
                    # Re-read both blocks fresh
                    ph = _SPageFilePhysics.from_buffer_copy(self._physics_mm.read(), 0)
                    gr = _SPageFileGraphic.from_buffer_copy(self._graphics_mm.read(), 0)
                    continue
            self._prev_packet_id = pid
            break
        else:
            log.warning("Torn read persisted after %d retries", max_retries)

        # Normalize to telemetry dict
        t = self._parse(ph, gr)
        return t

    def _parse(self, ph: _SPageFilePhysics, gr: _SPageFileGraphic) -> dict:
        """Convert ctypes structs to a normalized telemetry dictionary."""
        # Engine running: check isEngineRunning flag OR rpms > idle threshold
        engine_on = bool(ph.isEngineRunning) or (ph.rpms > 400)

        # Pedals -> 0-255 byte scale
        accel = int(ph.gas * 255)
        brake = int(ph.brake * 255)
        clutch = int(ph.clutch * 255)
        handbrake = int(gr.handbrake_percent * 255)

        # Dynamic max RPM
        max_rpm = max(ph.currentMaxRpm, 1)

        # Per-wheel slip ratios (offset 640)
        slip_ratios = [ph.slipRatio[i] for i in range(4)]
        slip_angles = [ph.slipAngle[i] for i in range(4)]
        wheel_angular = [ph.wheelAngularSpeed[i] for i in range(4)]
        tyre_dirty = [ph.tyreDirtyLevel[i] for i in range(4)]

        t = {
            "on": engine_on,
            "speed": ph.speedKmh,
            "rpm": float(ph.rpms),
            "max_rpm": max_rpm,
            "gear": ph.gear,
            "accel": accel,
            "brake": brake,
            "clutch": clutch,
            "handbrake": handbrake,
            "slipRatio_fl": slip_ratios[0],
            "slipRatio_fr": slip_ratios[1],
            "slipRatio_rl": slip_ratios[2],
            "slipRatio_rr": slip_ratios[3],
            "slipAngle_fl": slip_angles[0],
            "slipAngle_fr": slip_angles[1],
            "slipAngle_rl": slip_angles[2],
            "slipAngle_rr": slip_angles[3],
            "wheelRot_fl": wheel_angular[0],
            "wheelRot_fr": wheel_angular[1],
            "wheelRot_rl": wheel_angular[2],
            "wheelRot_rr": wheel_angular[3],
            "tyreDirty_fl": tyre_dirty[0],
            "tyreDirty_fr": tyre_dirty[1],
            "tyreDirty_rl": tyre_dirty[2],
            "tyreDirty_rr": tyre_dirty[3],
            "roadTemp": ph.roadTemp,
            "absInAction": bool(ph.absInAction),
            "absActive": bool(gr.abs_active),
            "tcInAction": bool(ph.tcInAction),
            "shiftUpHint": bool(gr.is_change_up_rpm),
            "shiftDownHint": bool(gr.is_change_down_rpm),
            "rpmLimiterOn": bool(gr.is_rpm_limiter_on),
            "drive_train": "RWD",  # Default; no drive_train field in SHM
        }
        return t

    def close(self) -> None:
        """Release all shared memory mappings."""
        for mm in (self._physics_mm, self._graphics_mm):
            if mm is not None:
                mm.close()
        self._physics_mm = self._graphics_mm = None
        self._connected = False

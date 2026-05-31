"""Convert raw adaptive-trigger HID frames into DSX (DualSenseX) UDP instructions.

Forza emits five HID frames; this maps each one:

    raw effect          ->  DSX mode
    off                     OFF
    rigid(force)            MULTIPLE_POSITION_FEEDBACK              (resistance, uniform)
    rigid_zones(zones)      MULTIPLE_POSITION_FEEDBACK              (resistance, per region)
    vibrate(freq, amp)      CustomTriggerValue / VibrateResistance  (raw buzz)
    vibrate_zones(...)      CustomTriggerValue / VibrateResistance  (gear-shift kick, 0 Hz)

RESISTANCE uses the v3.1+ MultiplePositionFeedback mode (per-region, felt as you
press through it; the brake walls set the top regions to 8).

VIBRATION uses DSX's CustomTriggerValue "raw" passthrough: it forwards 7 raw 0-255
bytes [frequency, amplitude, 0..] straight to the controller firmware. Unlike the
structured VIBRATION mode (capped at frequency 1-40, amplitude 1-8) this lets send
  * frequency 0  -> the firmware's sustained "0 Hz kick" for gear shifts;
  * the real HID frequency (130 Hz tarmac, 45 dirt, 15 gravel) -> distinct surfaces;
  * a strong raw amplitude -> buzzes that register on the weak trigger motor.
(See DualSenseX README: VibrateResistance B example "(10)(255)(0)(0)(0)(0)(0)".)

Protocol (DSX repo, Mod System v3.1+ — Resources.cs / Program.cs):
    {"instructions": [{"type": <int>, "parameters": [...]}]}      type 1=TriggerUpdate, 7=Reset
    structured : [0, trigger, mode, *values]
    custom     : [0, trigger, 12(CustomTriggerValue), CustomTriggerValueMode, *7 bytes]
    trigger Left=1, Right=2.
https://github.com/Paliverse/DSX/tree/main/Mod%20System%20(DSX%20v3)
"""
import logging

from modules.dualsense.adaptive_trigger import (
    M_OFF, M_RIGID, M_RIGID_ZONES, M_VIBRATE, M_VIBRATE_ZONES,
)

log = logging.getLogger("fhds.dsx")

TRIGGER_UPDATE = 1
RESET_TO_USER_SETTINGS = 7

# TriggerMode values
TM_OFF = 20
TM_MULTI_FEEDBACK = 25         # resistance: 10 region strengths (0-8)
TM_CUSTOM = 12                 # CustomTriggerValue: raw firmware passthrough
CTV_VIBRATE = 11               # CustomTriggerValueMode "VibrateResistance B": [freq, amp, 0..]

T_LEFT = 1
T_RIGHT = 2

# Raw vibration amplitude gain: Forza's HID buzz amps (1-30) scaled up so they're
# felt on DSX's weak trigger motor. Raise for stronger buzzes, lower for softer.
_VIBE_GAIN = 4

_warned: set[int] = set()


def _instr(trigger, mode, *values):
    return {"type": TRIGGER_UPDATE, "parameters": [0, trigger, mode, *values]}


def _vibrate(trigger, freq, amp):
    """CustomTriggerValue VibrateResistance B — raw [freq, amp, 0,0,0,0,0] (each 0-255).
    Sent straight to firmware: freq 0 = sustained kick, no 1-40 / 1-8 clamping."""
    freq = max(0, min(255, int(freq)))
    amp = max(0, min(255, int(amp)))
    return _instr(trigger, TM_CUSTOM, CTV_VIBRATE, freq, amp, 0, 0, 0, 0, 0)


def _force(v):
    """Resistance force byte (0-255) -> region strength 1-8, linear."""
    return max(1, min(8, round(int(v) / 255 * 8)))


def _unpack_zones(p):
    """Reverse adaptive_trigger._pack_zones: 6 bytes -> 10 region values (0-8)."""
    active = p[0] | (p[1] << 8)
    packed = p[2] | (p[3] << 8) | (p[4] << 16) | (p[5] << 24)
    return [((packed >> (3 * i)) & 0x07) + 1 if active & (1 << i) else 0
            for i in range(10)]


def _frame_to_instr(frame, trigger):
    mode, p = frame

    if mode == M_OFF:
        return _instr(trigger, TM_OFF)

    if mode == M_RIGID:                        # uniform resistance
        if not p[1]:
            return _instr(trigger, TM_OFF)
        return _instr(trigger, TM_MULTI_FEEDBACK, *([_force(p[1])] * 10))

    if mode == M_RIGID_ZONES:                  # per-region resistance (walls, ramps)
        zones = _unpack_zones(p)
        return _instr(trigger, TM_MULTI_FEEDBACK, *zones) if any(zones) \
            else _instr(trigger, TM_OFF)

    if mode == M_VIBRATE:                      # buzz: ABS, rev, wheelspin, idle
        if not p[1]:
            return _instr(trigger, TM_OFF)
        return _vibrate(trigger, p[0], int(p[1]) * _VIBE_GAIN)

    if mode == M_VIBRATE_ZONES:                # gear-shift kick: 0 Hz sustained push
        zones = _unpack_zones(p)
        if not any(zones):
            return _instr(trigger, TM_OFF)
        freq = p[8] if len(p) > 8 else 0       # 0 = firmware sustained kick
        amp = round(max(zones) / 8 * 255)      # zone strength 1-8 -> raw 0-255
        return _vibrate(trigger, freq, amp)

    if mode not in _warned:
        _warned.add(mode)
        log.warning("DSX: unmapped trigger mode 0x%02X -> OFF", mode)
    return _instr(trigger, TM_OFF)


def frames_to_packet(left, right):
    return {"instructions": [_frame_to_instr(left, T_LEFT),
                             _frame_to_instr(right, T_RIGHT)]}


def reset_packet():
    return {"instructions": [{"type": RESET_TO_USER_SETTINGS, "parameters": [0]}]}

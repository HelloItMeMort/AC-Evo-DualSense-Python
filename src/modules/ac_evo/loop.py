"""Per-frame loop: idle/lost handling, write-gate, once-per-second debug log."""
import logging
import time

from modules.ac_evo.process_watch import ProcessWatcher
from modules.dualsense import adaptive_trigger
from modules.ac_evo.shm_reader import AcEvoReader
from modules.ac_evo.effects import Controller

log = logging.getLogger("acevo")


def _max_abs(t, prefix, wheels=("fl", "fr", "rl", "rr")):
    return max(abs(t[f"{prefix}_{w}"]) for w in wheels)


def run(ds, reader, s, stop_event=None):
    OFF = adaptive_trigger.off()
    controller = Controller(s)
    prev = None
    last_pkt = time.monotonic()
    last_log = 0.0
    pkt_count = 0

    watcher = ProcessWatcher(s.game_process_name_contains, 1.0 / s.shm_poll_hz)
    dsx_mode = getattr(ds, "is_dsx", False)

    while True:
        if stop_event is not None and stop_event.is_set():
            break
        now = time.monotonic()

        # Game-close watcher
        if s.exit_on_game_close:
            try:
                if watcher.should_exit():
                    log.info("Game process closed — exiting.")
                    break
            except Exception as e:
                log.warning("game-close watcher error: %s", e)

        t = reader.read_latest()

        if t is None:
            idle = now - last_pkt
            if idle > 5.0 and not getattr(reader, "_had_first", False):
                log.warning("No SHM data yet — check that AC Evo is running")
            if idle > 1.0 and prev != (OFF, OFF):
                ds.set(OFF, OFF); prev = (OFF, OFF)
            if pkt_count > 0 and idle > s.telemetry_lost_exit_s:
                log.info("Telemetry lost for %.0fs — exiting.", idle)
                break
            time.sleep(0.01)
            continue

        pkt_count += 1
        last_pkt = now
        setattr(reader, "_had_first", True)

        if pkt_count == 1:
            log.info("First SHM frame received%s", " [DSX]" if dsx_mode else "")

        try:
            left, right = controller.update(t, s)
        except Exception as e:
            log.warning("controller.update failed: %s", e)
            continue

        if (left, right) != prev:
            try:
                ds.set(left, right); prev = (left, right)
            except Exception as e:
                log.debug("ds.set failed: %s", e)

        if now - last_log >= 1.0:
            last_log = now
            tag = "RACE" if t["on"] else "MENU"
            slip_r = _max_abs(t, "slipRatio")
            abs_flag = t.get("absInAction", False)
            tc_flag = t.get("tcInAction", False)
            log.debug("[%s] %6.1f km/h | gear %d | gas %3d R=%s | brake %3d L=%s | slip %.2f abs=%s tc=%s",
                      tag, t["speed"], t["gear"], t["accel"], right, t["brake"], left, slip_r, abs_flag, tc_flag)

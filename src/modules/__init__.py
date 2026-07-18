"""AC Evo DualSense building blocks — DualSense HID, SHM reader, settings."""
import logging
import os

from . import ac_evo, dsx, dualsense
from .ac_evo import loop


def make_backend(s, enable_startup_pulse):
    """Build the trigger writer the settings ask for."""
    if s.use_dsx:
        return dsx.DSXClient(
            host=s.dsx_host,
            port=s.dsx_port,
            startup_pulse_force=s.startup_pulse_force,
            enable_startup_pulse=enable_startup_pulse,
        )
    return dualsense.DualSense(
        startup_pulse_force=s.startup_pulse_force,
        enable_startup_pulse=enable_startup_pulse,
        reconnect_interval_s=s.reconnect_interval_s,
        enable_reconnect=s.enable_reconnect,
        controller_lock_serial=s.controller_lock_serial,
    )


def setup_logging(debug: bool = False) -> None:
    if os.name == "nt":
        os.system("")
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="\033[92m%(asctime)s %(message)s\033[0m",
        force=True,
    )

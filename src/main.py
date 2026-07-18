import argparse
import logging
import os
import sys
import traceback
from datetime import datetime
from dotenv import load_dotenv
load_dotenv("./dev.env")

from modules import ac_evo, make_backend, setup_logging
from modules.config import paths, preferences, Settings

log = logging.getLogger("acevo")

CRASH_LOG = paths.DATA / "crash.log"


def _excepthook(exc_type, exc, tb):
    if issubclass(exc_type, KeyboardInterrupt):
        print("\nInterrupted.", file=sys.stderr)
        return
    try:
        paths.DATA.mkdir(parents=True, exist_ok=True)
        with open(CRASH_LOG, "w", encoding="utf-8") as f:
            f.write(f"Crash at {datetime.now():%Y-%m-%d %H:%M:%S}\n\n")
            traceback.print_exception(exc_type, exc, tb, file=f)
    except OSError:
        pass
    log.critical("Unhandled exception", exc_info=(exc_type, exc, tb))


def _log_zuv_status() -> None:
    found = os.environ.get("IS_ZUV", "").lower() == "true"
    print(f"ZUV: {'detected' if found else 'not detected'}", file=sys.stderr, flush=True)


def run(s: Settings) -> None:
    ds = make_backend(s, s.enable_startup_pulse)
    ds.open()
    reader = ac_evo.AcEvoReader(poll_hz=s.shm_poll_hz)
    try:
        log.info("Connecting to AC Evo shared memory...")
        loop = ac_evo.loop
        loop.run(ds, reader, s)
    finally:
        reader.close()
        ds.close()


def run_tui(s: Settings) -> None:
    from modules.tui import TriggerTUI
    TriggerTUI(s).run()


def run_gui(s: Settings) -> None:
    from modules.gui import TriggerGUI
    try:
        TriggerGUI(s).run()
    except Exception:
        import traceback; traceback.print_exc()
        raise


def _confirm(prompt: str) -> bool:
    try:
        return input(prompt).strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="AC Evo DualSense adaptive triggers (Steam keeps rumble)")
    p.add_argument("--debug", action="store_true", help="Verbose per-frame logs")
    p.add_argument("--headless", action="store_true", help="Disable UI, use console logs")
    p.add_argument("--gui", action="store_true", help="Use the CustomTkinter GUI")
    p.add_argument("--tui", action="store_true", help="Force the Textual TUI")
    args = p.parse_args()

    settings = Settings()
    try:
        preferences.load(settings)
    except preferences.PreferencesError as e:
        print(f"\n{e}", file=sys.stderr)
        if not _confirm(f"Reset {preferences.PATH.name} to defaults? [y/N]: "):
            print("Aborted.", file=sys.stderr)
            sys.exit(1)
        preferences.reset_file()
        preferences.load(settings)

    sys.excepthook = _excepthook
    _log_zuv_status()

    try:
        if args.headless:
            setup_logging(args.debug)
            run(settings)
        elif args.tui:
            run_tui(settings)
        elif args.gui:
            run_gui(settings)
        elif getattr(sys, "frozen", False):
            run_gui(settings)
        else:
            run_gui(settings)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)

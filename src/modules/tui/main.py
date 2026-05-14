"""Textual TUI: tabbed Controls / Settings / Logs.

Toggles mutate the live Settings instance the loop reads each frame, so changes
take effect immediately without a restart.
"""
import logging
import threading
import time

from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import (
    Footer,
    Header,
    Input,
    Label,
    RichLog,
    Static,
    Switch,
    TabbedContent,
    TabPane,
)

from modules import dualsense, loop, preferences, udplistener
from modules.dualsense.triggers import off, vibration
from modules.update_check import log_latest_commit_age

HAPTIC_FREQ_HZ = 40
HAPTIC_AMP_ON = 200
HAPTIC_AMP_OFF = 120
HAPTIC_DURATION_S = 0.10

LOG_LEVELS = ("WARNING", "INFO", "DEBUG")
DEFAULT_LOG_LEVEL = "INFO"

log = logging.getLogger("fh5ds")

TOGGLES = [
    ("enable_brake_resistance",     "Brake resistance"),
    ("enable_handbrake_bonus",      "Handbrake bonus"),
    ("enable_abs",                  "ABS pulse"),
    ("enable_throttle_resistance",  "Throttle resistance"),
    ("enable_rev_limiter",          "Rev limiter"),
    ("enable_gear_shift",           "Gear shift thump"),
]

# (section title, [(attr, label), ...])
SETTING_SECTIONS = [
    ("Pedals / deadzones", [
        ("accel_deadzone",          "Accel deadzone (0-255)"),
        ("brake_deadzone",          "Brake deadzone (0-255)"),
        ("brake_full_force_at",     "Brake → max force at"),
        ("throttle_full_force_at",  "Throttle → max force at"),
    ]),
    ("Brake (left trigger)", [
        ("brake_baseline_force",    "Baseline force"),
        ("brake_max_force",         "Max force"),
        ("brake_curve",             "Curve"),
        ("handbrake_bonus",         "Handbrake bonus"),
    ]),
    ("ABS", [
        ("abs_brake_threshold",         "Brake threshold"),
        ("abs_min_speed_kmh",           "Min speed (km/h)"),
        ("abs_slip_ratio_threshold",    "Slip ratio threshold"),
        ("abs_combined_slip_threshold", "Combined slip threshold"),
        ("abs_freq",                    "Frequency (Hz)"),
        ("abs_amp",                     "Amplitude"),
    ]),
    ("Throttle (right trigger)", [
        ("throttle_baseline_force", "Baseline force"),
        ("throttle_max_force",      "Max force"),
        ("throttle_curve",          "Curve"),
    ]),
    ("Rev limiter", [
        ("rev_limit_ratio", "Trigger at RPM ratio"),
        ("rev_limit_freq",  "Frequency (Hz)"),
        ("rev_limit_amp",   "Amplitude"),
    ]),
    ("Gear shift thump", [
        ("gear_shift_freq",         "Frequency (Hz)"),
        ("gear_shift_amp",          "Amplitude"),
        ("gear_shift_duration_ms",  "Duration (ms)"),
    ]),
    ("Misc", [
        ("startup_pulse_force",    "Startup pulse force"),
        ("reconnect_interval_s",   "Reconnect interval (s)"),
    ]),
]


class _LogHandler(logging.Handler):
    def __init__(self, app):
        super().__init__()
        self.app = app

    def emit(self, record):
        msg = self.format(record)
        if threading.get_ident() == self.app._thread_id:
            self.app.write_log(msg)
        else:
            self.app.call_from_thread(self.app.write_log, msg)


class ControlsPage(VerticalScroll):
    DEFAULT_CLASSES = "page"

    def __init__(self, settings):
        super().__init__()
        self.settings = settings

    def compose(self) -> ComposeResult:
        for attr, label in TOGGLES:
            with Horizontal(classes="row"):
                yield Switch(value=getattr(self.settings, attr), id=attr)
                yield Label(label)


class SettingsPage(VerticalScroll):
    DEFAULT_CLASSES = "page"

    def __init__(self, settings):
        super().__init__()
        self.settings = settings

    def compose(self) -> ComposeResult:
        for section, fields in SETTING_SECTIONS:
            yield Label(section, classes="section")
            for attr, label in fields:
                value = getattr(self.settings, attr, None)
                if value is None:
                    continue
                input_type = "integer" if isinstance(value, int) and not isinstance(value, bool) else "number"
                with Horizontal(classes="row"):
                    yield Label(label)
                    yield Input(value=str(value), id=f"set-{attr}", type=input_type)


class TriggerTUI(App):
    CSS = """
    Screen { background: $surface; }
    #status { dock: top; height: 1; padding: 0 2; background: $boost; text-align: center; }

    TabbedContent { height: 1fr; }
    Tabs { align-horizontal: center; }
    TabPane { padding: 1 2; align-horizontal: center; }

    .page { width: 64; max-width: 100%; height: 1fr; padding: 1 2; }

    Label.section { text-style: bold; color: $accent; padding: 1 0 0 0; }

    .row { height: 3; align-vertical: middle; padding: 0 1; }
    .row Switch { margin-right: 2; }
    .row Label  { width: 1fr; }
    .row Input  { width: 14; }

    RichLog { padding: 0 1; height: 1fr; }
    """
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("p", "toggle_pause", "Pause logs"),
        ("l", "cycle_level", "Log level"),
        ("c", "clear_logs", "Clear logs"),
    ]

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self._stop = threading.Event()
        self._thread = None
        self._ds = None
        self._listener_cm = None
        self._listener = None
        self._paused = False
        self._level_idx = LOG_LEVELS.index(DEFAULT_LOG_LEVEL)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static("", id="status")
        with TabbedContent(initial="tab-controls"):
            with TabPane("Controls", id="tab-controls"):
                yield ControlsPage(self.settings)
            with TabPane("Settings", id="tab-settings"):
                yield SettingsPage(self.settings)
            with TabPane("Logs", id="tab-logs"):
                yield RichLog(id="logs", highlight=False, markup=False, wrap=True, max_lines=2000)
        yield Footer()

    def on_mount(self):
        self.title = "FH5 DualSense"
        self.sub_title = f"UDP {self.settings.udp_host}:{self.settings.udp_port}"

        root = logging.getLogger()
        root.handlers.clear()
        handler = _LogHandler(self)
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S"))
        root.addHandler(handler)
        root.setLevel(self._level())

        self._refresh_status()
        self.set_interval(1.0, self._refresh_status)
        log_latest_commit_age()
        log.info("Starting controller and telemetry listener...")
        self.call_after_refresh(self._start_backend)

    def _start_backend(self):
        s = self.settings
        try:
            self._ds = dualsense.DualSense(
                startup_pulse_force=s.startup_pulse_force,
                enable_startup_pulse=s.enable_startup_pulse,
                reconnect_interval_s=s.reconnect_interval_s,
            )
            self._ds.open()
            self._listener_cm = udplistener.UDPListener(s.udp_host, s.udp_port, s.udp_timeout)
            self._listener = self._listener_cm.__enter__()
            log.info("Listening on %s:%d", s.udp_host, s.udp_port)
            log.info("In FH5: HUD & Gameplay -> Data Out: ON, IP %s, Port %d", s.udp_host, s.udp_port)
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
        except Exception as exc:
            log.exception("Backend startup failed")
            self.query_one("#status", Static).update(f"Backend failed: {exc}")

    def _run_loop(self):
        try:
            loop.run(self._ds, self._listener, self.settings, stop_event=self._stop)
        finally:
            if not self._stop.is_set():
                self.call_from_thread(self.exit)

    def on_unmount(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        if self._listener_cm:
            self._listener_cm.__exit__(None, None, None)
        if self._ds:
            self._ds.close()

    def _refresh_status(self):
        connected = bool(self._ds and self._ds.connected)
        state = "[bold green]connected[/]" if connected else "[bold red]waiting[/]"
        bits = [f"DualSense: {state}", f"Logs: {LOG_LEVELS[self._level_idx]}", "PAUSED" if self._paused else "live"]
        self.query_one("#status", Static).update("  •  ".join(bits))

    def _level(self):
        return getattr(logging, LOG_LEVELS[self._level_idx])

    def write_log(self, msg):
        self.query_one("#logs", RichLog).write(msg, scroll_end=not self._paused)

    def action_toggle_pause(self):
        self._paused = not self._paused
        self._refresh_status()

    def action_cycle_level(self):
        self._level_idx = (self._level_idx + 1) % len(LOG_LEVELS)
        logging.getLogger().setLevel(self._level())
        self._refresh_status()
        log.info("Log level: %s", LOG_LEVELS[self._level_idx])

    def action_clear_logs(self):
        self.query_one("#logs", RichLog).clear()

    def on_switch_changed(self, event: Switch.Changed):
        attr = event.switch.id
        if attr and hasattr(self.settings, attr):
            setattr(self.settings, attr, event.value)
            preferences.save(self.settings)
            self._haptic(event.value)

    def on_input_submitted(self, event: Input.Submitted):
        widget = event.input
        if not widget.id or not widget.id.startswith("set-"):
            return
        attr = widget.id[4:]
        if not hasattr(self.settings, attr):
            return
        current = getattr(self.settings, attr)
        raw = widget.value.strip()
        try:
            if isinstance(current, bool):
                new = raw.lower() in ("1", "true", "yes", "on")
            elif isinstance(current, int):
                new = int(float(raw))
            elif isinstance(current, float):
                new = float(raw)
            else:
                new = raw
        except ValueError:
            widget.value = str(current)
            return
        if new == current:
            return
        setattr(self.settings, attr, new)
        preferences.save(self.settings)
        log.info("%s = %s", attr, new)

    def _haptic(self, on):
        if self._ds and self._ds.connected:
            threading.Thread(target=self._do_haptic, args=(on,), daemon=True).start()

    def _do_haptic(self, on):
        amp = HAPTIC_AMP_ON if on else HAPTIC_AMP_OFF
        v = vibration(HAPTIC_FREQ_HZ, amp)
        self._ds.set(v, v)
        time.sleep(HAPTIC_DURATION_S)
        self._ds.set(off(), off())

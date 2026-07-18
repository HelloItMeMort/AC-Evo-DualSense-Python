"""Tiny file-based i18n."""
import importlib
import logging
from pathlib import Path

log = logging.getLogger("acevo")

DEFAULT_LANG = "en"

_catalogs: dict[str, dict] = {}
_names: dict[str, str] = {}
_active: str = DEFAULT_LANG


def _discover() -> None:
    _catalogs.clear()
    _names.clear()
    folder = Path(__file__).resolve().parent
    for f in sorted(folder.glob("*.py")):
        code = f.stem
        if code.startswith("_"):
            continue
        try:
            m = importlib.import_module(f"{__name__}.{code}")
        except Exception as e:
            log.warning("Skipping language '%s': %s", code, e)
            continue
        _catalogs[code] = dict(getattr(m, "STRINGS", {}))
        _names[code] = str(getattr(m, "NAME", code))
    _catalogs.setdefault(DEFAULT_LANG, {})
    _names.setdefault(DEFAULT_LANG, "English")


def _ensure() -> None:
    if not _catalogs:
        _discover()


def available() -> list[tuple[str, str]]:
    _ensure()
    return sorted(_names.items(), key=lambda kv: (kv[0] != DEFAULT_LANG, kv[1].lower()))


def set_language(code: str) -> None:
    global _active
    _ensure()
    _active = code if code in _catalogs else DEFAULT_LANG


def current() -> str:
    return _active


def t(key: str) -> str:
    _ensure()
    cat = _catalogs.get(_active)
    return cat.get(key, key) if cat else key

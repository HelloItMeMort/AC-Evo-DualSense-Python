"""Show how long ago the latest GitHub commit was, so users know if they're behind."""
import json
import logging
import threading
import urllib.request
from datetime import datetime, timezone

log = logging.getLogger("fh5ds")

API_URL = "https://api.github.com/repos/HamzaYslmn/Forza-Horizon-5-DualSense-Python/commits/main"
REPO_URL = "https://github.com/HamzaYslmn/Forza-Horizon-5-DualSense-Python"
def _format_age(seconds: float) -> str:
    if seconds < 3600:
        return f"{int(seconds // 60)} min"
    if seconds < 86400:
        return f"{seconds / 3600:.1f} h"
    return f"{seconds / 86400:.1f} d"


def _check(timeout: float) -> None:
    try:
        with urllib.request.urlopen(API_URL, timeout=timeout) as r:
            data = json.loads(r.read().decode())
        date_str = data["commit"]["author"]["date"]  # e.g. 2026-04-30T12:34:56Z
        commit_time = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        age_s = (datetime.now(timezone.utc) - commit_time).total_seconds()
        sha = data["sha"][:7]
        log.info("Latest commit %s, %s ago - %s", sha, _format_age(age_s), REPO_URL)
    except Exception as e:
        log.warning("Update check failed: %s", e)


def log_latest_commit_age(timeout: float = 3.0) -> None:
    """Fire-and-forget background check. Never blocks startup."""
    threading.Thread(target=_check, args=(timeout,), daemon=True).start()

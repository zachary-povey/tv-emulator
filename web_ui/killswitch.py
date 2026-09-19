"""Read and modify the daily usage limit and today's accumulated usage.

Mirrors the behaviour of killswitch/tv-killswitch.sh: the limit lives in a
shell-sourced config file and usage accumulates in a per-day state file keyed by
the device's local date.
"""
import datetime as _dt
import re
from dataclasses import dataclass

from . import config

_LIMIT_RE = re.compile(r"^(\s*)DAILY_LIMIT_MINUTES\s*=\s*(\d+)\s*$")


class LimitError(ValueError):
    """Raised when a requested limit or credit is outside the accepted range."""


@dataclass
class UsageStatus:
    """Today's usage against the configured allowance.

    Attributes:
        limit_minutes: The configured daily allowance.
        used_minutes: Minutes accumulated so far today.
        remaining_minutes: Minutes left, floored at zero.
        over_budget: True once the allowance is spent.
    """

    limit_minutes: int
    used_minutes: int
    remaining_minutes: int
    over_budget: bool


def today_usage_path() -> "config.Path":
    """Return the path of today's usage state file (local date, as the shell script uses)."""
    today = _dt.date.today().isoformat()
    return config.USAGE_DIR / f"usage-{today}"


def read_limit_minutes() -> int:
    """Return the configured daily allowance in minutes.

    Falls back to the documented default if the config file is missing or holds
    no recognisable assignment.
    """
    if not config.LIMITS_CONF.is_file():
        return config.DEFAULT_DAILY_LIMIT_MINUTES

    for line in config.LIMITS_CONF.read_text().splitlines():
        match = _LIMIT_RE.match(line)
        if match:
            return int(match.group(2))
    return config.DEFAULT_DAILY_LIMIT_MINUTES


def write_limit_minutes(minutes: int) -> None:
    """Set the daily allowance, rewriting only the assignment line.

    Comments and surrounding content are preserved so the file stays as
    self-documenting as the version shipped by the installer.

    Args:
        minutes: The new allowance.

    Raises:
        LimitError: If *minutes* is outside the accepted range.
    """
    if not config.MIN_DAILY_LIMIT_MINUTES <= minutes <= config.MAX_DAILY_LIMIT_MINUTES:
        raise LimitError(
            f"Daily limit must be between {config.MIN_DAILY_LIMIT_MINUTES} and "
            f"{config.MAX_DAILY_LIMIT_MINUTES} minutes (got {minutes})."
        )

    assignment = f"DAILY_LIMIT_MINUTES={minutes}"

    if config.LIMITS_CONF.is_file():
        lines = config.LIMITS_CONF.read_text().splitlines()
        for i, line in enumerate(lines):
            if _LIMIT_RE.match(line):
                lines[i] = assignment
                break
        else:
            lines.append(assignment)
        body = "\n".join(lines) + "\n"
    else:
        body = assignment + "\n"

    _atomic_write(config.LIMITS_CONF, body)


def read_used_seconds() -> int:
    """Return seconds accumulated today, or zero when no state file exists yet."""
    path = today_usage_path()
    if not path.is_file():
        return 0
    raw = path.read_text().strip()
    return int(raw) if raw.isdigit() else 0


def status() -> UsageStatus:
    """Return today's usage measured against the configured allowance."""
    limit = read_limit_minutes()
    used = read_used_seconds() // config.TICK_SECONDS
    return UsageStatus(
        limit_minutes=limit,
        used_minutes=used,
        remaining_minutes=max(0, limit - used),
        over_budget=used >= limit,
    )


def credit_minutes(minutes: int) -> UsageStatus:
    """Grant extra time today by subtracting from the accumulated usage.

    Reducing usage rather than raising the limit keeps the change scoped to
    today: tomorrow's allowance is unaffected.

    Args:
        minutes: Additional minutes to grant.

    Returns:
        The usage status after the credit is applied.

    Raises:
        LimitError: If *minutes* is not a positive value within the cap.
    """
    if not 1 <= minutes <= config.MAX_CREDIT_MINUTES:
        raise LimitError(
            f"Extra time must be between 1 and {config.MAX_CREDIT_MINUTES} minutes "
            f"(got {minutes})."
        )

    remaining = max(0, read_used_seconds() - minutes * config.TICK_SECONDS)
    path = today_usage_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, str(remaining))
    return status()


def _atomic_write(path: "config.Path", body: str) -> None:
    """Write *body* to *path* via a temporary file in the same directory.

    The killswitch reads these files from a once-a-minute timer, so a partial
    read of a half-written file is avoided by renaming into place.
    """
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(body)
    tmp.replace(path)

"""Power actions for the tablet.

polkit refuses an unprivileged poweroff on this device (a CanPowerOff check
returns "challenge"), so these shell out to shutdown via a narrow sudoers rule
installed alongside the service.
"""
import subprocess

from . import config

_SHUTDOWN = "/sbin/shutdown"


class DeviceActionError(RuntimeError):
    """Raised when a power action could not be carried out."""


def power_off() -> str:
    """Power the tablet off immediately.

    Returns:
        A message describing what happened.

    Raises:
        DeviceActionError: If the shutdown command failed.
    """
    return _run(["-h", "now"], "Shutting down now.")


def reboot() -> str:
    """Reboot the tablet immediately.

    Returns:
        A message describing what happened.

    Raises:
        DeviceActionError: If the shutdown command failed.
    """
    return _run(["-r", "now"], "Rebooting now.")


def _run(args: list[str], message: str) -> str:
    """Invoke shutdown with *args*, or simulate it in local development."""
    if config.FAKE_SHUTDOWN:
        return f"[development mode] would have run: sudo {_SHUTDOWN} {' '.join(args)}"

    command = ["sudo", "-n", _SHUTDOWN, *args]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DeviceActionError(f"Could not run shutdown: {exc}") from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise DeviceActionError(f"shutdown failed: {detail or result.returncode}")
    return message

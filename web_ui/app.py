"""FastAPI application serving the TV emulator's management UI.

Every page is server-rendered and every action is a plain form POST followed by
a redirect, so the UI works on any phone browser without client-side scripting.
There is no authentication: the service is intended for a trusted home LAN.
"""
import logging
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import channels, config, device, killswitch, mpv_ipc
from .playlist_builder import PlaylistBuilderUnavailable

_HERE = Path(__file__).resolve().parent
_log = logging.getLogger("tv_web_ui")

_PLAYER_OFFLINE = (
    "The TV is not playing at the moment, so this control is unavailable. "
    "Turn the TV on and try again."
)

app = FastAPI(title="TV Emulator", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=_HERE / "static"), name="static")
templates = Jinja2Templates(directory=_HERE / "templates")


def _redirect(path: str, message: str | None = None, error: str | None = None) -> RedirectResponse:
    """Redirect after a form POST, carrying a status message in the query string."""
    params = []
    if message:
        params.append(f"msg={_quote(message)}")
    if error:
        params.append(f"err={_quote(error)}")
    target = path + ("?" + "&".join(params) if params else "")
    return RedirectResponse(target, status_code=303)


def _quote(value: str) -> str:
    """Percent-encode a status message for use in a redirect URL."""
    from urllib.parse import quote

    return quote(value, safe="")


def _base_context(request: Request) -> dict:
    """Build the template context shared by every page."""
    return {
        "request": request,
        "message": request.query_params.get("msg"),
        "error": request.query_params.get("err"),
        "player": mpv_ipc.status(),
        "usage": killswitch.status(),
    }


@app.get("/")
def index(request: Request):
    """Render the status overview."""
    context = _base_context(request)
    context["channels"] = channels.list_channels()
    return templates.TemplateResponse("index.html", context)


@app.get("/channels")
def channels_page(request: Request):
    """Render the channel list."""
    context = _base_context(request)
    context["channels"] = channels.list_channels()
    return templates.TemplateResponse("channels.html", context)


@app.post("/channels/{name}/volume")
def set_channel_volume(name: str, volume: Annotated[str, Form()] = ""):
    """Set or clear a channel's default volume."""
    try:
        parsed = None if volume.strip() == "" else int(volume)
    except ValueError:
        return _redirect("/channels", error=f"'{volume}' is not a whole number.")

    try:
        channels.set_volume(name, parsed)
    except channels.ChannelError as exc:
        return _redirect("/channels", error=str(exc))

    if parsed is None:
        return _redirect("/channels", message=f"{name}: volume cleared (uses the default).")
    return _redirect("/channels", message=f"{name}: volume set to {parsed}.")


@app.post("/channels/{name}/rebuild")
def rebuild_channel(name: str, mode: Annotated[str, Form()] = "file-order"):
    """Rebuild a channel's playlist from the video files on disk."""
    try:
        count = channels.rebuild_playlist(name, mode)
    except channels.ChannelError as exc:
        return _redirect("/channels", error=str(exc))
    except PlaylistBuilderUnavailable as exc:
        return _redirect("/channels", error=str(exc))

    plural = "video" if count == 1 else "videos"
    return _redirect(
        "/channels",
        message=(
            f"{name}: playlist rebuilt with {count} {plural}. "
            "Switch channels on the TV to pick up the change."
        ),
    )


@app.get("/limits")
def limits_page(request: Request):
    """Render the daily limit and today's usage."""
    context = _base_context(request)
    context["max_credit"] = config.MAX_CREDIT_MINUTES
    context["min_limit"] = config.MIN_DAILY_LIMIT_MINUTES
    context["max_limit"] = config.MAX_DAILY_LIMIT_MINUTES
    return templates.TemplateResponse("limits.html", context)


@app.post("/limits")
def set_limit(minutes: Annotated[str, Form()]):
    """Set the daily allowance, which applies from today onwards."""
    try:
        parsed = int(minutes)
    except ValueError:
        return _redirect("/limits", error=f"'{minutes}' is not a whole number.")

    try:
        killswitch.write_limit_minutes(parsed)
    except killswitch.LimitError as exc:
        return _redirect("/limits", error=str(exc))
    except OSError as exc:
        return _redirect("/limits", error=f"Could not write the limit: {exc}")

    return _redirect("/limits", message=f"Daily limit set to {parsed} minutes.")


@app.post("/limits/credit")
def credit_time(minutes: Annotated[str, Form()]):
    """Grant extra minutes for today only."""
    try:
        parsed = int(minutes)
    except ValueError:
        return _redirect("/limits", error=f"'{minutes}' is not a whole number.")

    try:
        status = killswitch.credit_minutes(parsed)
    except killswitch.LimitError as exc:
        return _redirect("/limits", error=str(exc))
    except OSError as exc:
        return _redirect("/limits", error=f"Could not update today's usage: {exc}")

    return _redirect(
        "/limits",
        message=(
            f"Granted {parsed} more minutes today. "
            f"{status.remaining_minutes} of {status.limit_minutes} minutes now left."
        ),
    )


@app.post("/device/channel/{direction}")
def change_channel(direction: str):
    """Move the player to the next or previous channel."""
    bindings = {
        "next": ("channel-next", "next"),
        "prev": ("channel-prev", "previous"),
    }
    if direction not in bindings:
        return _redirect("/", error=f"Unknown direction: {direction}")

    binding, label = bindings[direction]
    try:
        mpv_ipc.script_binding(binding)
    except mpv_ipc.MpvUnavailable as exc:
        _log.warning("channel %s failed: %s", direction, exc)
        return _redirect("/", error=_PLAYER_OFFLINE)
    return _redirect("/", message=f"Switched to the {label} channel.")


@app.post("/device/mute")
def toggle_mute():
    """Toggle the player's mute state."""
    try:
        muted = mpv_ipc.toggle_mute()
    except mpv_ipc.MpvUnavailable as exc:
        _log.warning("mute failed: %s", exc)
        return _redirect("/", error=_PLAYER_OFFLINE)
    return _redirect("/", message="Muted." if muted else "Unmuted.")


@app.post("/device/pause")
def toggle_pause():
    """Pause or resume playback."""
    try:
        paused = mpv_ipc.toggle_pause()
    except mpv_ipc.MpvUnavailable as exc:
        _log.warning("pause failed: %s", exc)
        return _redirect("/", error=_PLAYER_OFFLINE)
    return _redirect("/", message="Paused." if paused else "Playing.")


@app.post("/device/shutdown")
def shutdown():
    """Power the tablet off."""
    try:
        message = device.power_off()
    except device.DeviceActionError as exc:
        return _redirect("/", error=str(exc))
    return _redirect("/", message=message)


@app.post("/device/reboot")
def reboot():
    """Reboot the tablet."""
    try:
        message = device.reboot()
    except device.DeviceActionError as exc:
        return _redirect("/", error=str(exc))
    return _redirect("/", message=message)

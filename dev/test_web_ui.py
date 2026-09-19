"""Edge-case checks for the web UI modules.

Runs the real modules against a throwaway fixture tree, so no device is needed.
Exits non-zero on the first failing expectation.

Usage:
    .venv/bin/python dev/test_web_ui.py
"""
import os, sys, tempfile, json, datetime
from pathlib import Path

root = Path(tempfile.mkdtemp())
(root/"Channels").mkdir(); (root/"etc").mkdir(); (root/"var").mkdir()
os.environ.update(
    TV_CHANNELS_DIR=str(root/"Channels"),
    TV_LIMITS_CONF=str(root/"etc/limits.conf"),
    TV_USAGE_DIR=str(root/"var"),
    TV_MPV_SOCKET=str(root/"nonexistent.sock"),
    TV_CREATE_PLAYLIST=str(Path.cwd()/"emulator_scripts/create_playlist"),
)
sys.path.insert(0, str(Path.cwd()))
from web_ui import killswitch, channels, mpv_ipc, config

fails = []
def check(label, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}: {got!r}")
    if not ok:
        fails.append(f"{label}: got {got!r}, want {want!r}")

print("== limits.conf missing entirely ==")
check("falls back to default", killswitch.read_limit_minutes(), 60)
check("usage with no file", killswitch.read_used_seconds(), 0)
s = killswitch.status()
check("status with nothing present", (s.limit_minutes, s.used_minutes, s.over_budget), (60, 0, False))

print("== writing creates the file ==")
killswitch.write_limit_minutes(45)
check("written value reads back", killswitch.read_limit_minutes(), 45)

print("== limits.conf with odd formatting ==")
(root/"etc/limits.conf").write_text(
    "# comment\n\n  DAILY_LIMIT_MINUTES   =   120  \n# trailing comment\n")
check("tolerates whitespace", killswitch.read_limit_minutes(), 120)
killswitch.write_limit_minutes(30)
body = (root/"etc/limits.conf").read_text()
check("comments preserved on rewrite", "# trailing comment" in body, True)
check("only one assignment line", body.count("DAILY_LIMIT_MINUTES"), 1)

print("== corrupt usage file ==")
today = datetime.date.today().isoformat()
(root/"var"/f"usage-{today}").write_text("not-a-number")
check("garbage treated as zero", killswitch.read_used_seconds(), 0)
(root/"var"/f"usage-{today}").write_text("-500")
check("negative treated as zero", killswitch.read_used_seconds(), 0)

print("== credit clamps and floors ==")
(root/"var"/f"usage-{today}").write_text("600")
killswitch.credit_minutes(5)
check("credit subtracts", killswitch.read_used_seconds(), 300)
killswitch.credit_minutes(99)
check("floors at zero", killswitch.read_used_seconds(), 0)
for bad in (0, -5, 10_000):
    try:
        killswitch.credit_minutes(bad); check(f"credit({bad}) rejected", False, True)
    except killswitch.LimitError:
        check(f"credit({bad}) rejected", True, True)

print("== channels: empty dir ==")
check("no channels", channels.list_channels(), [])

print("== channels: unreadable settings.json ==")
ch = root/"Channels"/"broken"; ch.mkdir()
(ch/"settings.json").write_text("{not json")
(ch/"playlist.m3u").write_text("#EXTM3U\n/nope.mp4\n")
c = channels.load("broken")
check("bad json -> no volume", c.volume, None)
check("counts entries", c.video_count, 1)
check("counts missing", c.missing_count, 1)

print("== channels: malformed settings are reported, not swallowed ==")
# A real case from the device: valid-looking but not strict JSON, which MPV's
# own parser also rejects, so the channel silently played at default volume.
cases = {
    "unquoted": ('{volume: 140}\n', "not valid JSON"),
    "notobj":   ('[1,2,3]\n', "not an object"),
    "badtype":  ('{"volume": "loud"}\n', "non-numeric volume"),
    "trunc":    ('{"volume":\n', "not valid JSON"),
    "good":     ('{"volume": 90}\n', None),
}
for cname, (body, expect) in cases.items():
    d = root/"Channels"/cname
    d.mkdir()
    (d/"settings.json").write_text(body)
    (d/"playlist.m3u").write_text("#EXTM3U\n")
    loaded = channels.load(cname)
    if expect is None:
        check(f"{cname}: volume read", loaded.volume, 90)
        check(f"{cname}: no problem", loaded.settings_problem, None)
    else:
        check(f"{cname}: volume ignored", loaded.volume, None)
        check(f"{cname}: problem reported", expect in (loaded.settings_problem or ""), True)

print("== channels: saving repairs a malformed file ==")
channels.set_volume("unquoted", 140)
repaired = channels.load("unquoted")
check("repaired volume", repaired.volume, 140)
check("problem cleared", repaired.settings_problem, None)
check("valid json on disk", json.loads((root/"Channels/unquoted/settings.json").read_text()), {"volume": 140})

print("== channels: rebuild with no videos ==")
try:
    channels.rebuild_playlist("broken"); check("empty rebuild rejected", False, True)
except channels.ChannelError:
    check("empty rebuild rejected", True, True)
check("playlist left intact", (ch/"playlist.m3u").read_text().strip().endswith("/nope.mp4"), True)

print("== channels: name validation ==")
for bad in ("../etc", "a/b", "", "a;b", "a\x00b", "-rf"):
    try:
        channels.resolve(bad); check(f"rejects {bad!r}", False, True)
    except channels.ChannelError:
        check(f"rejects {bad!r}", True, True)

print("== mpv: absent socket never raises out of status() ==")
st = mpv_ipc.status()
check("running False", st.running, False)
check("no channel", st.channel, None)
for fn, arg in ((mpv_ipc.script_binding, "channel-next"), (mpv_ipc.toggle_mute, None), (mpv_ipc.toggle_pause, None)):
    try:
        fn(arg) if arg else fn(); check(f"{fn.__name__} raises", False, True)
    except mpv_ipc.MpvUnavailable:
        check(f"{fn.__name__} raises MpvUnavailable", True, True)

print()
if fails:
    print(f"{len(fails)} FAILURE(S):")
    for f in fails: print("  -", f)
    sys.exit(1)
print("All edge cases passed.")

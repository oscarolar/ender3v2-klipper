#!/usr/bin/env python3
"""Mirror Klipper's power-loss resume point to a second machine.

Run it on a machine other than the Klipper host (a laptop, a NAS, the Mac when
Klipper runs on a Pi) whenever the Klipper host has no UPS: a power cut can lose
or corrupt the host's plr_variables.cfg. Every --interval seconds it copies
save_variables to --out (atomic write) so the resume point survives. It exits
when the print it saw running completes or is cancelled; an outage (Klipper
unreachable, standby after reboot) keeps it waiting.

  KLIPPER_HOST=klipper.local python3 plr-mirror.py --out ~/plr-mirror.json

When the print ends the mirror is disarmed (plr_active false). After a power
cut, once the host is back, check the saved file, layer and Z, then put the
resume point back before PLR_RESUME:

  KLIPPER_HOST=klipper.local python3 plr-mirror.py --out ~/plr-mirror.json --restore
  KLIPPER_HOST=klipper.local python3 plr-mirror.py --out ~/plr-mirror.json --restore --yes
"""
import argparse
import json
import os
import sys
import time
import urllib.request

BASE = ""  # Moonraker URL, set in main()


def get(path):
    return json.load(urllib.request.urlopen(BASE + path, timeout=8))["result"]


def gcode(script):
    req = urllib.request.Request(BASE + "/printer/gcode/script",
                                 data=json.dumps({"script": script}).encode(),
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=30).read()


def restore_lines(v):
    """SAVE_VARIABLE commands that re-create every plr_* variable exactly.

    SAVE_VARIABLE parses VALUE as a Python literal and Klipper splits parameters
    with shlex (posix): inside "..." only \\ and " are escapes, so escaping those
    two in the repr passes the literal through unchanged.
    """
    lines = []
    for k, val in v.items():
        if not k.startswith("plr_"):
            continue
        lit = repr(val).replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'SAVE_VARIABLE VARIABLE={k} VALUE="{lit}"')
    return lines


def write(out, data):
    """Atomic write: a power cut mid-write leaves the previous copy intact."""
    tmp = out + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, out)


def disarm(out, state):
    """Mark the mirrored point finished so a later --restore cannot re-arm it."""
    try:
        with open(out) as f:
            data = json.load(f)
    except FileNotFoundError:
        return
    data["variables"]["plr_active"] = False
    data["ended"] = f"{state} {time.strftime('%Y-%m-%d %H:%M:%S')}"
    write(out, data)


def describe(v):
    return (f"file {str(v.get('plr_file', '')).replace('__PCT__', '%')!r}, "
            f"layer {v.get('plr_layer')}, Z {v.get('plr_z')}")


def restore(out, yes=False):
    """Re-inject the mirrored point; refuses without --yes or for a finished print."""
    with open(out) as f:
        data = json.load(f)
    v = data["variables"]
    print(f"mirror of {data.get('saved_at')}: {describe(v)}")
    if not v.get("plr_active"):
        print(f"refusing: that print already ended ({data.get('ended', 'plr_active is false')})")
        return False
    if not yes:
        print("check it matches the part on the bed, then re-run with --yes")
        return False
    gcode("\n".join(restore_lines(v)))
    print("restored:", {k: v[k] for k in v if k.startswith("plr_")})
    return True


def mirror(out, interval):
    last, seen_printing = None, False
    while True:
        try:
            st = get("/printer/objects/query?save_variables&print_stats=state,filename")["status"]
            v, ps = st["save_variables"]["variables"], st["print_stats"]
            seen_printing = seen_printing or ps["state"] == "printing"
            if v != last and v.get("plr_active"):
                write(out, {"saved_at": time.strftime("%Y-%m-%d %H:%M:%S"), "print": ps, "variables": v})
                last = v
                print(time.strftime("%H:%M:%S"), "saved layer", v.get("plr_layer"), flush=True)
            # a 'complete' left over from an earlier print must not end the watch
            if seen_printing and ps["state"] in ("complete", "cancelled"):
                disarm(out, ps["state"])
                print("print", ps["state"], "- mirror disarmed, exiting", flush=True)
                return
        except Exception as e:  # outage or reboot: keep the last good copy, wait
            print(time.strftime("%H:%M:%S"), "unreachable:", str(e)[:80], flush=True)
        time.sleep(interval)


def main(argv=None):
    global BASE
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("host", nargs="?", help="Klipper host (Moonraker via Mainsail's nginx on port 80)")
    ap.add_argument("--host", dest="host_opt")
    ap.add_argument("--out", default="plr-mirror.json")
    ap.add_argument("--interval", type=float, default=20)
    ap.add_argument("--restore", action="store_true", help="show the mirrored point; with --yes re-inject it")
    ap.add_argument("--yes", action="store_true", help="confirm --restore")
    args = ap.parse_args(argv)
    host = args.host_opt or args.host or os.environ.get("KLIPPER_HOST")
    if not host:
        ap.error("give the Klipper host (or set KLIPPER_HOST)")
    BASE = host if host.startswith("http") else f"http://{host}"
    out = os.path.abspath(os.path.expanduser(args.out))
    if args.restore:
        return 0 if restore(out, args.yes) else 1
    else:
        mirror(out, args.interval)


if __name__ == "__main__":
    sys.exit(main())

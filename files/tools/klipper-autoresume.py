#!/usr/bin/env python3
"""Watch a Klipper print and resume it automatically after a link shutdown.

Run it on any always-on machine with a stable connection to Moonraker (the
Klipper host itself, the Mac that runs the VM, another PC), only for a print the
operator pre-authorized for auto-resume: the resume trusts the saved Z and
assumes the part is still stuck to the bed, and the resumed layer shows a
visible line.

  KLIPPER_HOST=klipper.local nohup python3 klipper-autoresume.py --file part.gcode > autoresume.log 2>&1 &

The authorization is bound to one print: --file NAME, or else the first file
seen printing. Another print started later is reported and never resumed.

Every 5 s it logs one line per notable event (the log doubles as the monitor
feed). When Klipper shuts down with a link fault (Timer too close, Lost
communication, Communication timeout) and the saved resume point belongs to the
print it watched, it runs FIRMWARE_RESTART -> heats bed and nozzle and WAITS
(the nozzle rests on the part: nothing moves while it is cold) -> PLR_RESUME ->
restores the speed factor. Any other shutdown (heater, thermal, MCU error), a
paused print, a print error, or a saved point without a safe nozzle (>= 170 C)
and bed target is only reported as ALERT, never resumed. It stops when the
watched print completes or is cancelled.
"""
import argparse
import json
import os
import time
import urllib.request

LINK_FAULTS = ("Timer too close", "Lost communication", "Communication timeout")
MIN_EXTRUDER = 170  # Klipper's default min_extrude_temp: below it the nozzle is stuck in the part
BASE = ""  # Moonraker URL, set in main()


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def saved_file(v):
    """The file name PLR_SAVE stored, with its '%' decoded (see macros.cfg)."""
    f = v.get("plr_file")
    return f.replace("__PCT__", "%") if isinstance(f, str) else None


def unsafe_temps(v):
    """Why the saved targets cannot be trusted to free the nozzle, or None.

    A 0 target makes PLR_RESUME's M109 S0 return at once and lift a cold
    nozzle out of the part.
    """
    bed, ext = v.get("plr_bed"), v.get("plr_extruder")
    if not isinstance(ext, (int, float)) or not isinstance(bed, (int, float)) or ext < MIN_EXTRUDER or bed <= 0:
        return f"saved targets nozzle {ext!r} / bed {bed!r} are not safe to resume with: NOT resuming"
    return None


def decide(reason, v, watched_file, current_file, resumes, max_resumes):
    """None to resume, else the ALERT text explaining why not.

    current_file is the last file seen printing before the shutdown.
    """
    if not any(f in reason for f in LINK_FAULTS):
        return "not a link fault: NOT resuming, needs a human"
    if not v.get("plr_active"):
        return "no saved resume point: NOT resuming"
    # plr_* variables persist across prints: a stale point from an older print
    # would restart the wrong file at the wrong height.
    if watched_file is None or saved_file(v) != watched_file:
        return f"saved point is for {saved_file(v)!r}, not the watched print {watched_file!r}: NOT resuming"
    if current_file != watched_file:
        return f"the shutdown hit {current_file!r}, not the authorized print {watched_file!r}: NOT resuming"
    if resumes >= max_resumes:
        return f"{max_resumes} resumes already: NOT resuming"
    return unsafe_temps(v)


def q(objs):
    return json.load(urllib.request.urlopen(f"{BASE}/printer/objects/query?{objs}", timeout=8))["result"]["status"]


def post(path, body=None):
    data = json.dumps(body).encode() if body is not None else b""
    req = urllib.request.Request(BASE + path, data=data, headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=60).read()


def gcode(script):
    post("/printer/gcode/script", {"script": script})


def wait(pred, timeout, step=3):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if pred():
                return True
        except Exception:
            pass
        time.sleep(step)
    return False


def cool_down(why):
    log(f"ALERT {why}; heaters off (M104 S0, M140 S0)")
    try:
        gcode("M104 S0\nM140 S0")
    except Exception as e:
        log(f"ALERT could not turn the heaters off: {str(e)[:100]}")


def resume(v, speed):
    why = unsafe_temps(v)  # checked again: never heat to, or move at, a bad target
    if why:
        log(f"ALERT {why}")
        return False
    post("/printer/firmware_restart")
    if not wait(lambda: q("webhooks=state")["webhooks"]["state"] == "ready", 120):
        log("ALERT firmware restart did not reach ready; not resuming")
        return False
    bed, ext = v["plr_bed"], v["plr_extruder"]
    gcode(f"M140 S{bed}\nM104 S{ext}")
    log(f"heating nozzle {ext} C / bed {bed} C before any move")

    def hot():
        s = q("extruder=temperature&heater_bed=temperature")
        return s["extruder"]["temperature"] >= ext - 2 and s["heater_bed"]["temperature"] >= bed - 2

    if not wait(hot, 900, 5):
        cool_down("did not reach temperature in 15 min; not resuming")
        return False
    try:
        gcode("PLR_RESUME")  # blocks until the print restarts; may exceed the HTTP timeout
    except Exception:
        pass
    if not wait(lambda: q("print_stats=state")["print_stats"]["state"] == "printing", 300):
        cool_down("PLR_RESUME did not restart the print")
        return False
    gcode(f"M220 S{round(speed * 100)}")
    return True


def watch(max_resumes, watched=None):
    resumes, last_wh, last_ps, last_retx, last_hour = 0, None, None, None, None
    speed, current, alerted, seen = 1.0, None, None, False
    log(f"autoresume on {BASE}" + (f", watching {watched}" if watched else ", watching the first print seen"))
    while True:
        try:
            s = q("webhooks=state,state_message&print_stats=state,filename,print_duration,message"
                  "&gcode_move=speed_factor&save_variables&mcu")
            wh, ps = s["webhooks"], s["print_stats"]
            v = s["save_variables"]["variables"]
            if wh["state"] == "ready" and ps["state"] == "printing":
                # FIRMWARE_RESTART resets print_stats, so remember the file now
                if ps["filename"]:
                    current = ps["filename"]
                    if watched is None:
                        watched = current
                        log(f"watching {watched}")
                    elif current != watched and alerted != current:
                        log(f"ALERT different print started ({current}): not auto-resuming it")
                        alerted = current
                    seen = seen or current == watched
                speed = s["gcode_move"]["speed_factor"]
                retx = s["mcu"]["last_stats"]["bytes_retransmit"]
                if last_retx is not None and retx > last_retx:
                    log(f"LINK retransmit +{retx - last_retx} B, layer {v.get('plr_layer')}")
                last_retx = retx
                hour = int(ps["print_duration"] // 1800)  # every 30 min of printing
                if last_hour is not None and hour > last_hour:
                    log(f"STATUS layer {v.get('plr_layer')} Z {v.get('plr_z')}, {resumes} auto-resumes so far")
                last_hour = hour
            if ps["state"] != last_ps and wh["state"] == "ready":
                # a shutdown also leaves print_stats in error: its SHUTDOWN line covers it
                if ps["state"] in ("paused", "error"):
                    log(f"ALERT print {ps['state']} {ps.get('message') or ''}".rstrip() + ": NOT resuming")
            if wh["state"] == "ready":
                last_ps = ps["state"]
            if wh["state"] in ("shutdown", "error") and wh["state"] != last_wh:
                reason = next(iter((wh.get("state_message") or "").splitlines()), "")
                log(f"SHUTDOWN {reason} at layer {v.get('plr_layer')}")
                why = decide(reason, v, watched, current, resumes, max_resumes)
                if why:
                    log(f"ALERT {why}")
                elif resume(v, speed):
                    resumes += 1
                    last_retx, last_hour, last_ps = None, None, "printing"
                    log(f"RESUMED {watched} at layer {v.get('plr_layer')} (auto-resume #{resumes})")
                    last_wh = "ready"
                    continue
            # a 'complete' left over from before this watch must not end it
            if (seen and ps["filename"] == watched and ps["state"] in ("complete", "cancelled")
                    and wh["state"] == "ready"):
                log(f"END print {ps['state']} after {resumes} auto-resumes")
                return
            last_wh = wh["state"]
        except Exception as e:
            log(f"WARN {str(e)[:100]}")
        time.sleep(5)


def main(argv=None):
    global BASE
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("host", nargs="?", help="Klipper host (Moonraker via Mainsail's nginx on port 80)")
    ap.add_argument("--host", dest="host_opt")
    ap.add_argument("--file", help="the only print (file name as Moonraker shows it) allowed to auto-resume")
    ap.add_argument("--max-resumes", type=int, default=10)
    args = ap.parse_args(argv)
    host = args.host_opt or args.host or os.environ.get("KLIPPER_HOST")
    if not host:
        ap.error("give the Klipper host (or set KLIPPER_HOST)")
    BASE = host if host.startswith("http") else f"http://{host}"
    watch(args.max_resumes, args.file)


if __name__ == "__main__":
    main()

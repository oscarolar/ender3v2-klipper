#!/bin/bash
# Small Moonraker API client for reading calibration results as numbers.
#
#   moonraker.sh gcode "<G-code>"   run G-code; long commands are polled (see below)
#   moonraker.sh store [n]          last n console lines (default 30)
#   moonraker.sh query <objects>    e.g. "print_stats&extruder&bltouch"
#   moonraker.sh mesh               probed mesh, back row on top, and its range
#   moonraker.sh stats              MCU link stats (srtt, retransmits, invalid bytes)
#
# Host: $KLIPPER_HOST (the Klipper host's LAN IP or name). Mainsail's nginx
# cuts a request after 60 s while Klipper keeps running the command
# (PID_CALIBRATE, meshes, SCREWS_TILT_CALCULATE), so "gcode" waits 55 s, then
# re-posts M400 until the command has finished and prints the console lines
# produced meanwhile.
set -uo pipefail
: "${KLIPPER_HOST:?set KLIPPER_HOST to the LAN IP or name of the Klipper host}"
K="http://$KLIPPER_HOST"

store() {
    curl -s "$K/server/gcode_store?count=${1:-30}" | python3 -c '
import json,sys
since=float(sys.argv[1])
for x in json.load(sys.stdin)["result"]["gcode_store"]:
    if x["time"]>=since: print(x["message"])' "${2:-0}"
}

run_gcode() {
    t0=$(python3 -c 'import time;print(time.time()-2)')
    body=$(python3 -c 'import json,sys;print(json.dumps({"script":sys.argv[1]}))' "$1")
    out=$(curl -s -m 55 -X POST "$K/printer/gcode/script" -H 'Content-Type: application/json' -d "$body")
    rc=$?
    if [ $rc -eq 28 ] || echo "$out" | grep -q '504'; then
        echo "(still running; waiting)" >&2
        # Klipper runs G-code one command at a time: M400 returns only after
        # the long command has finished, so re-post it until it answers.
        until curl -s -m 55 -X POST "$K/printer/gcode/script" -H 'Content-Type: application/json' \
                -d '{"script":"M400"}' | grep -q '"result"'; do sleep 2; done
    elif echo "$out" | grep -q '"error"'; then
        echo "$out" >&2
    fi
    store 100 "$t0"
}

case "${1:-}" in
gcode) run_gcode "$2" ;;
store) store "${2:-30}" ;;
query) curl -s "$K/printer/objects/query?$2" | python3 -m json.tool ;;
mesh)
    curl -s "$K/printer/objects/query?bed_mesh" | python3 -c '
import json,sys
m=json.load(sys.stdin)["result"]["status"]["bed_mesh"]["probed_matrix"]
for row in reversed(m): print(" ".join(f"{v:+.3f}" for v in row))
flat=[v for r in m for v in r]; print("range", round(max(flat)-min(flat),3))'
    ;;
stats)
    curl -s "$K/printer/objects/query?mcu" | python3 -c '
import json,sys
s=json.load(sys.stdin)["result"]["status"]["mcu"]["last_stats"]
print({k: s[k] for k in ("srtt","rttvar","bytes_retransmit","bytes_invalid","retransmit_seq") if k in s})'
    ;;
*) sed -n '2,13p' "$0"; exit 2 ;;
esac

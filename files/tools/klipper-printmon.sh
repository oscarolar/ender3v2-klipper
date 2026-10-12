#!/bin/bash
# Print one line per notable event of a Klipper print: console errors, link
# retransmits, every 25 % of progress, Klipper shutdowns, a paused print, and
# the end. Run it from a machine with a stable connection to the Klipper host
# (the host itself, or the Mac that runs the VM).
#
#   klipper-printmon.sh [host]        host defaults to $KLIPPER_HOST
# host = the Klipper host's IP or name (Mainsail's nginx on port 80 proxies Moonraker).
#
# A shutdown does not end the watch: klipper-autoresume.py may revive the print.
# It exits only when a print it saw running completes or is cancelled.
HOST="${1:-${KLIPPER_HOST:-}}"
[ -n "$HOST" ] || { echo "usage: $0 <klipper-host>   (or set KLIPPER_HOST)" >&2; exit 2; }
K="http://$HOST"; last=$(date +%s); lastq=-1; retx0=""; lastwh=""; lastps=""; seen=""
while true; do
  # tab-separated, no empty fields (read would collapse them); the shutdown
  # message goes last so its spaces survive. Missing objects (Klipper in
  # shutdown or startup error) fall back to placeholders instead of failing.
  line=$(curl -s -m 5 "$K/printer/objects/query?webhooks=state,state_message&print_stats&virtual_sdcard=progress&mcu&save_variables" | python3 -c '
import json,sys
st=json.load(sys.stdin)["result"]["status"]
w=st.get("webhooks",{}); p=st.get("print_stats",{}); m=st.get("mcu",{}).get("last_stats",{})
v=st.get("save_variables",{}).get("variables",{})
msg=((w.get("state_message") or "").splitlines() or ["-"])[0] or "-"
print(p.get("state","-"), round(st.get("virtual_sdcard",{}).get("progress",0)*100,1), m.get("bytes_retransmit",0),
      round(m.get("srtt",0)*1000,1), v.get("plr_layer"), w.get("state","-"), msg, sep="\t")' 2>/dev/null)
  if [ -z "$line" ]; then echo "WARN moonraker unreachable"; sleep 20; continue; fi
  IFS=$'\t' read -r state prog retx srtt layer wh msg <<<"$line"
  [ -z "$retx0" ] && retx0=$retx
  case "$wh" in
    shutdown|error) [ "$wh" != "$lastwh" ] && echo "SHUTDOWN $msg (layer $layer)";;
    ready) case "$lastwh" in shutdown|error) echo "READY klipper back (print state $state)";; esac;;
  esac
  lastwh=$wh
  if [ "$state" = paused ] && [ "$lastps" != paused ]; then echo "ALERT paused at $prog% layer $layer"; fi
  lastps=$state
  [ "$state" = printing ] && seen=1
  curl -s -m 5 "$K/server/gcode_store?count=40" | python3 -c '
import json,sys
last=float(sys.argv[1])
for x in json.load(sys.stdin)["result"]["gcode_store"]:
    t=x["message"]
    if x["time"]>last and (t.startswith("!!") or "Timer too close" in t or "Lost communication" in t or "Failed" in t or "rror" in t): print("CONSOLE", t[:160])' "$last" 2>/dev/null
  last=$(date +%s)
  # the MCU counters restart at 0 after a FIRMWARE_RESTART
  if [ "$retx" != "$retx0" ]; then
    [ "${retx%.*}" -gt "${retx0%.*}" ] 2>/dev/null && echo "LINK retransmits $retx0 -> $retx (srtt ${srtt} ms, layer $layer)"
    retx0=$retx
  fi
  q=$(python3 -c 'import sys; print(int(float(sys.argv[1])//25))' "$prog" 2>/dev/null || echo "$lastq")
  if [ "$q" != "$lastq" ]; then [ "$lastq" != "-1" ] && echo "PROGRESS $prog% layer $layer srtt ${srtt} ms retx $retx"; lastq=$q; fi
  if [ -n "$seen" ]; then
    case "$state" in complete|cancelled) echo "END state=$state progress=$prog% layer=$layer retx=$retx"; exit 0;; esac
  fi
  sleep 20
done

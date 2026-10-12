# Go/no-go print, then keep or roll back

Decide the criteria **before** the print, and do not switch the printer over
for good until it passes.

## The print

At least 1 h, ideally ~3 h, with dense retractions (many islands, lots of
travel), at the speeds you will really use (the fast Orca process). Watch it
with `files/tools/klipper-printmon.sh <klipper-host>` from a machine with a
stable link to the host: one line per console error, shutdown, pause,
retransmit change and 25 % of progress. A monitor that only reads the print
state misses shutdowns (`power-loss-and-monitoring.md`).

## Read the verdict from klippy.log

```bash
ssh $KLIPPER_SSH 'cat printer_data/logs/klippy.log' | python3 -c "
import re,sys
t=sys.stdin.read()
print('timer too close:', t.count('Timer too close'))
print('lost comm:', t.count('Lost communication with MCU'))
srtt=[float(x) for x in re.findall(r'srtt=([0-9.]+)', t)]
rt=[int(x) for x in re.findall(r'bytes_retransmit=([0-9]+)', t)]
inv=[int(x) for x in re.findall(r'bytes_invalid=([0-9]+)', t)]
print(f'srtt ms: median {sorted(srtt)[len(srtt)//2]*1000:.2f} max {max(srtt)*1000:.2f}')
print('bytes_retransmit last:', rt[-1] if rt else None, 'bytes_invalid last:', inv[-1] if inv else None)"
```

| Measure | Pass |
|---|---|
| `Timer too close` during the print | 0 |
| `Lost communication with MCU` | 0 |
| `srtt` | stable (a few ms; 5–6 ms seen) |
| `bytes_invalid` | 0 |
| `bytes_retransmit` | near 0; isolated bursts of a few hundred bytes every 2–3 h are normal over the Mac bridge, but one landing on dense short moves can end the print with `Timer too close` (seen once: 121-byte burst, `sysload` 0.04, Benchy at 86 %). On direct USB expect less; growing bursts there point at the cable, EMI or the host |
| The part | complete, no extrusion stops or layer shifts |

Errors during homing/probing at print start are a separate problem
(`print-start-and-probe.md`, `troubleshooting.md`), not a no-go by
themselves: they happen before any plastic is laid down.

Reference result: a 2 h 45 min print, 0 / 0, `srtt` 5–6 ms,
`bytes_invalid` 0, one 185-byte retransmit burst.

## Pass: keep

- Record the calibration results (PID, z_offset, PA, max_accel, retraction,
  mesh range) somewhere outside the host.
- Back up `~/printer_data/config/` from the host.
- A host reboot or an MCU shutdown stops a print (heaters off): recovery is in
  `power-loss-and-monitoring.md`.

## Fail: roll back to Marlin

1. Stop Klipper from reaching the printer:
   `ssh $KLIPPER_SSH 'bash ~/install/printer-link.sh disable'`. On a Mac also
   free the port: `launchctl bootout gui/$(id -u)/<prefix>.klipper-serial-bridge`.
2. Copy the saved Marlin `.bin` to the SD card under a name the board has
   never seen (e.g. `M<MMDD>.bin`), printer off; insert and power on. The
   display comes back when done.
3. Reconnect the old host (OctoPrint or other) at the baud it used before (stock Creality 115200, MRiscoC and many custom builds 250000; the `M503` file tells which worked) and re-enable
   its autoconnect.
4. Restore the calibration from the saved `M503`: send its `M92` and `M851`
   (and PID) lines, then `M500`.
5. Switch the slicer back to the Marlin printer profile (it was left
   untouched).
6. The host can stay: Klipper touches nothing while `/dev/printer` is gone.

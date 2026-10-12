# Troubleshooting

Check from the outside in. `$KLIPPER_SSH` = ssh destination of the host,
`<klipper-host>` = its LAN address, `<prefix>` = the Mac LaunchAgent
`LABEL_PREFIX`.

| # | Check | Command | Fix |
|---|---|---|---|
| 1 | Host up | `curl -s http://<klipper-host>/server/info` | Pi: `vcgencmd get_throttled` = `0x0`. Mac: `utmctl status klipper` → `started`, else `launchctl kickstart gui/$(id -u)/<prefix>.klipper-vm`, read `/tmp/klipper-vm.log` (the VM starts only after the auto-login session is up) |
| 2 | `/dev/printer` exists | `ssh $KLIPPER_SSH 'bash ~/install/printer-link.sh status'` | not enabled: `printer-link.sh enable` (only after the cutover). `usb` mode, enabled but missing: `ls /dev/serial/by-id/`, `dmesg \| tail` (cable, printer off, `brltty`, back-power: `host-setup.md`) |
| 3 | Mac bridge | `launchctl list \| grep klipper-serial-bridge`; `tail -5 /tmp/klipper-serial-bridge.log` | "in use by another process": another program holds the port, disconnect it and turn its autoconnect off. "no /dev/cu.usbserial-*": printer off or unplugged |
| 4 | Klippy state | `curl -s http://<klipper-host>/printer/info` | `error`/`shutdown`: read `~/printer_data/logs/klippy.log`, then `FIRMWARE_RESTART`. "Unable to connect" after the printer was switched on late: just `FIRMWARE_RESTART` |
| 5 | `FIRMWARE_RESTART` hangs, klippy logs `Got EOF` / `Timeout with MCU`, or `Failed automated reset of MCU` after the Mac bridge restarted | — | Mac: `ssh $KLIPPER_SSH 'sudo systemctl restart printer-pty; sleep 3; sudo systemctl restart klipper'`, then `FIRMWARE_RESTART`. USB: power-cycle the printer, then `sudo systemctl restart klipper` |

## Failure at print start: probe or link?

| Signature | Cause | Next |
|---|---|---|
| `Failed to verify BLTouch probe is raised`, `Probe triggered prior to movement`, probe LED blinking or solid red | probe pin | `print-start-and-probe.md` |
| `Timer too close` or `Communication timeout during homing` in `klippy.log`, the dumped trapq shows a probe/homing move, printer state `shutdown` | host or link stall | Mac: "Timing hardening" in `host-mac-vm-bridge.md`, then "Stall hunting" below |

After a power cycle for a solid red LED: `BLTOUCH_DEBUG COMMAND=reset`,
`QUERY_PROBE` must answer `open`, then relaunch the print. On a Pi make sure
the power cycle really reset the board (USB back-power, `host-setup.md`).

## Stall hunting (`Timer too close` mid-print, no retransmit burst)

A `Timer too close` with low `sysload`, steady `srtt` and no retransmit burst
just before it is a freeze somewhere in the path, not load. Measure, don't
guess (a faster bridge or a Rust rewrite does not fix a frozen VM):

1. `files/tools/jitter-probe.py --name <machine>` on every machine in the path:
   the host; on a Mac both the Mac (LaunchAgent at `ProcessType Interactive`)
   and the VM (systemd unit). Bridge mode also logs `STALL serial silent` /
   `STALL ... blocked` in `/tmp/klipper-serial-bridge.log`.
2. Match the shutdown time (`klippy.log`; the VM clock may be UTC) with the
   `STALL` lines:

| STALL seen in | Frozen hop | Look at |
|---|---|---|
| the bridge log only | USB / CH340 or the bridge's send | cable, hub, EMI, port |
| the Mac probe | macOS froze the bridge | Mac hygiene in `host-mac-vm-bridge.md` |
| the VM probe only | the VM froze | what the Mac ran in that second: `top -l 2 -o cpu` captured around it; Mac hygiene |
| the Pi / Linux host probe | the host froze | under-voltage, SD card, heavy jobs, swap |
| nowhere | the network hop between them | host-only network, Wi-Fi on the host |

3. A freeze at the same minute every hour is a scheduled job: catch it with a
   `top` capture at that minute. Seen on a Mac: iCloud Contacts sync + "Calls
   from iPhone", 100–220 ms every hour at :36.

## Symptoms

| Symptom | Where the answer is |
|---|---|
| `Timer too close` / `Communication timeout during homing` only while homing/probing, prints fine | Mac: "Timing hardening" in `host-mac-vm-bridge.md`; check App Nap (`defaults read ~/Library/Containers/com.utmapp.UTM/Data/Library/Preferences/com.utmapp.UTM NSAppSleepDisabled` = `1`) and that `TRSYNC_TIMEOUT` is still `0.050` after the last Klipper update. Other hosts: "Stall hunting" |
| `Timer too close` / `Lost communication with MCU` while printing | "Stall hunting" above; resume: `power-loss-and-monitoring.md`; verdict: `go-no-go-and-rollback.md` |
| The monitor said nothing but the print stopped | `power-loss-and-monitoring.md` (watch `webhooks.state`) |
| A Mac LaunchAgent watcher gets `No route to host` (errno 65), works over SSH | Local Network privacy, `host-mac-vm-bridge.md` |
| Probe fails at print start, LED normal or solid red | `print-start-and-probe.md` |
| "Move out of range" in `AXIS_TWIST_COMPENSATION_CALIBRATE` | probe vs nozzle coordinates, `printer-config.md` |
| Mesh differs day to day, tramming never converges | X gantry check at the top of `calibration.md` |
| Printer heats before homing, or Orca ignores the tuned accelerations | `slicer-orca.md` |
| Moonraker refuses to start after a `cors_domains` edit | Moonraker notes, `host-setup.md` |
| Board does not answer after flashing | `firmware-and-cutover.md` steps 4–5 |
| Mainsail 403/404 after install on a Pi | nginx cannot enter the home dir: `chmod o+x ~` (`install-stack.sh` does it) |

## Timing statistics

`files/tools/moonraker.sh stats`, or in `klippy.log` the `Stats` lines:
`srtt`, `bytes_retransmit`, `bytes_invalid`. Thresholds are in
`go-no-go-and-rollback.md`.

## Obico

Setup and relinking after a host rebuild: "Remote access" in `host-setup.md`.

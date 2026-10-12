# Watching long prints, power loss and resume

Tools run from any always-on machine with a stable link to the host (the host
itself is fine), with `KLIPPER_HOST=<klipper-host>`. `--help` on each.

## Watch: shutdowns are not a print state

`print_stats.state` does not say `error` when Klipper shuts down: the print
just stops, and the state can read `paused` or stay put. Two real
`Timer too close` shutdowns went unnoticed for 2 and 39 minutes by a monitor
that read only `print_stats` and the console. Watch `webhooks.state` too
(`shutdown`/`error`, reason in `state_message`) and treat `paused` as an alert:
`files/tools/klipper-printmon.sh` does both.

Alerts to a phone: Obico (`host-setup.md`, remote access) is independent of
any agent session. An agent's own push notification reaches the phone only
while its remote session is connected: never the only channel. Without
Obico, pipe the monitor into a push service from a machine that is **not** the
host (a dead host cannot report itself), e.g. ntfy:

```bash
KLIPPER_HOST=<klipper-host> files/tools/klipper-printmon.sh \
  | grep --line-buffered -E '^(SHUTDOWN|ALERT|END)' \
  | while read -r l; do curl -s -d "$l" https://ntfy.sh/<secret-topic>; done
```

Test it once: stop Klipper during a short print and check the phone.

## Resume after a stop

`PLR_SAVE` (Orca layer-change G-code) stores file, byte offset, Z, layer,
temperatures and fan in `save_variables`. After a host reboot or an MCU
shutdown:

1. Human checks the part is still stuck and unmoved, and says go (or has
   pre-authorized auto-resume for this print).
2. `FIRMWARE_RESTART` (clears positions **and the speed factor**).
3. Heat bed and nozzle and wait. The nozzle rests on the part and cooled into
   it: nothing may move Z until it is back at print temperature, a cold lift
   rips the part off the bed. After `FIRMWARE_RESTART` send no `G1 Z`/`G28`
   while cold.
4. `PLR_RESUME`: trusts the saved Z (`SET_KINEMATIC_POSITION`), lifts 5 mm,
   homes **only X and Y** (the restart lost their position; Z homing would
   drive the probe into the part), returns to Z and restarts the file at the
   saved layer start. Expect a visible line at that layer: part of it prints
   twice.
5. Restore the speed factor (`M220 S<n>`) if one was set.

`files/tools/klipper-autoresume.py` does steps 2–5 automatically, only for
link faults (`Timer too close`, `Lost communication`, `Communication timeout`)
and only for the one print it was started for (`--file`, or the first file it
sees printing); any other shutdown (heater, thermal), another print, or a
saved nozzle target below 170 °C is reported, never resumed. If heating or the
restart fails it turns the heaters off. It resumed two long prints over the Mac bridge.

Pitfalls seen:
- `plr_*` survive across prints: at the start of a new print `plr_file` can
  still name the previous one. Compare it with `print_stats.filename` before
  trusting it.
- After `FIRMWARE_RESTART`, `print_stats` durations and `bytes_retransmit`
  start again from 0.
- Raising the speed factor: wait for `print_stats.state == printing` and
  `plr_layer >= 1` on the current file, then `M220 S<n>`.

## No UPS on the host

A power cut can lose or corrupt the host's `plr_variables.cfg` (SD card on a
Pi, the VM disk on a Mac). `files/tools/plr-mirror.py` copies the resume
point every 20 s to a second machine (atomic write) and exits when the print
ends (marking the copy finished); `plr-mirror.py --restore --yes` shows file,
layer and Z and writes them back with `SAVE_VARIABLE` before step 2. It
refuses a finished print. The printer has no UPS either: the print still stops, only the resume
point survives. A small UPS on the host (and the printer) is the real fix.

## Stall hunting

`files/tools/jitter-probe.py` logs when the machine it runs on freezes (a
5 ms sleep waking late). Run one on each machine in the serial path and
match its `STALL` lines against the time of a `Timer too close`:
`troubleshooting.md`, "Stall hunting".

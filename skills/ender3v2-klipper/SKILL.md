---
name: ender3v2-klipper
description: Use when moving a Creality Ender 3 V2 from Marlin to Klipper on a Raspberry Pi, a Linux PC or a Mac (UTM VM, no Pi), when recalibrating an Ender 3 V2 on Klipper, when a CR Touch or BLTouch clone fails at print start, when "Timer too close", "Lost communication with MCU" or "Communication timeout during homing" stop homing or a long print, or when a stopped Klipper print must be resumed after a shutdown or power loss.
---

# Ender 3 V2: Marlin to Klipper on any host

## Overview

Klipper host on whatever is always on: a Raspberry Pi or Linux PC with the
printer's USB plugged in, or a headless Debian VM on an Apple Silicon Mac with
the USB serial bridged over TCP. Working files: `files/` at the plugin root.

**Core rule:** the printer stays on Marlin until the host is proven, and Klipper stays only after a long print passes a gate decided in advance.

## Phases

1. **A: host, printer untouched**: pick the host, install the stack, reboot
   test, optional remote access (Obico or VPN, never port-forwarding).
   `references/host-setup.md`; on a Mac first `references/host-mac-vm-bridge.md`.
2. **B: cutover, human at the printer**: save Marlin state, flash, `printer-link.sh enable`, home. `references/firmware-and-cutover.md`, `references/printer-config.md`
3. **Calibration**: PID → 100 mm extrusion → `PROBE_CALIBRATE` → `SCREWS_TILT_CALCULATE` → `AXIS_TWIST_COMPENSATION_CALIBRATE` → mesh → PA tower → ringing tower → retraction tower → 5-disc adhesion. `references/calibration.md`, `references/print-start-and-probe.md`, `references/slicer-orca.md`
4. **Go/no-go print, then keep or roll back.** `references/go-no-go-and-rollback.md`
5. **Living with it**: watching long prints, resume after a stop, no-UPS
   mirror `references/power-loss-and-monitoring.md`; hardware
   `references/upgrades.md`.

Stuck: `references/troubleshooting.md`.

## Human-at-printer protocol

- Anything that moves or heats: the human confirms presence and a clear bed first.
- Ask the human only for physical feedback: paper feel, knob turns, tower heights, whether the part is still stuck.
- Never resume a stopped print without the human's OK for that print, and never move Z while the nozzle is cold.
- Read results as numbers via Moonraker: `POST /printer/gcode/script`, `GET /printer/objects/query`, `GET /server/gcode_store` (`files/tools/moonraker.sh`). Never read graphs.
- nginx cuts requests at 60 s while Klipper keeps running: poll long commands (PID, mesh).

## Quick reference

| Need | Command / file |
|---|---|
| Mac only: create VM, bridge + keep-alive agents | `files/mac/create-vm.sh`, `files/mac/install-agents.sh` |
| Push installer and config to the host | `KLIPPER_SSH=user@host LAN_CIDR=... files/tools/deploy-config.sh` |
| Install/re-patch stack (after Klipper updates) | `SERIAL_MODE=usb\|bridge bash ~/install/install-stack.sh` on the host |
| Connect / disconnect Klipper from the printer | `bash ~/install/printer-link.sh enable\|disable\|status` |
| G-code, console, mesh, link stats | `files/tools/moonraker.sh gcode "..."`, `store`, `mesh`, `stats` |
| Watch a print (shutdowns, pauses) | `files/tools/klipper-printmon.sh` |
| Auto-resume link faults / mirror the resume point | `files/tools/klipper-autoresume.py`, `files/tools/plr-mirror.py` |
| Find which machine froze | `files/tools/jitter-probe.py` |
| Orca profiles | `files/orca/orca-klipper-profile.py` |

## Red flags / common mistakes

| Wrong belief | Reality | Ref |
|---|---|---|
| Probe `^PC14`/`PA1`, offsets -44/-8, TMC UART | `^PB1`/`PB0`, -40/-5, standalone drivers; start from upstream `printer-creality-ender3-v2-2020.cfg` | printer-config |
| Point `[mcu] serial` at `/dev/serial/by-id/...` right away | `/dev/printer`, created only at the cutover; otherwise Klipper grabs the Marlin printer | host-setup |
| Mac timing fixes (App Nap, TRSYNC patch) on a Pi | Mac VM only (`SERIAL_MODE=bridge`); direct USB needs none | host-setup |
| Serial latency is irrelevant on the Mac | Homing streams ~0.1–0.25 s ahead: App Nap off, `ProcessType Interactive`, TCP_NODELAY, `TRSYNC_TIMEOUT` 0.050 | host-mac-vm-bridge |
| Mid-print `Timer too close` = rewrite the bridge / more priority | Measure which machine froze (`jitter-probe.py`); on a Mac, iCloud Contacts/Photos and iPhone calls froze the VM hourly | troubleshooting |
| The monitor would have said | Shutdowns are in `webhooks.state`, not `print_stats` | power-loss-and-monitoring |
| Reset/unstick/`FIRMWARE_RESTART` clears solid red | Power-cycle the printer (on a Pi, without USB back-power) | print-start-and-probe |
| Mesh cold; park probe low while heating | The order in `PRINT_START`; first deploy after idle sticks | print-start-and-probe |
| More samples/touch mode fix a flaky clone | `samples: 2`, mesh `SAMPLES=1`, stow each sample, no touch mode | print-start-and-probe |
| PA `FACTOR=.005`, tower at any speed | Bowden `.020`, within hotend flow | calibration |
| No accelerometer, skip ringing | Manual ringing tower | calibration |
| Twist in nozzle coords | Probe coords | printer-config |
| Tram and mesh harder | X gantry first | calibration |
| Reuse the firmware file name | New name; save Marlin `.bin`, `M503` first | firmware-and-cutover |
| Switch after a short test | ≥1 h (ideally ~3 h) gate | go-no-go-and-rollback |
| Resume: home Z, or lift right away | Heat first, trust saved Z, home X/Y only; check `plr_file` is this print | power-loss-and-monitoring |
| 0.4 mm layers on a 0.4 nozzle | ≤ 0.32 mm | slicer-orca |
| Klipper's `install-debian.sh` | Python 2: own venv + unit | host-setup |
| Any Orca flavor/limits | `klipper`, limits = `max_accel`, no wipe | slicer-orca |
| CORS `*`; `FIRMWARE_RESTART` hangs | Wildcard rejected; restart the link then klipper | troubleshooting |

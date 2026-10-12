# Ender 3 V2: Marlin to Klipper on any host

Move a Creality Ender 3 V2 to [Klipper](https://www.klipper3d.org/) on
whatever machine is always on:

- a **Raspberry Pi** (Raspberry Pi OS Lite 64-bit) or any **Linux PC/server**
  (Debian 12+, Ubuntu 22.04+) with the printer's USB plugged in, or
- an **Apple Silicon Mac** with no Linux machine around: the Klipper host
  (Klipper, Moonraker, Mainsail) runs in a headless Debian VM under
  [UTM](https://mac.getutm.app/) and a small bridge forwards the USB serial
  to it over TCP.

This repository is a [Claude Code](https://claude.com/claude-code) plugin: a
skill that walks an agent (and you) through the whole migration from Marlin,
a full calibration, a go/no-go test and life afterwards (watching long
prints, resuming after a stop), plus the scripts and configs it uses.
Everything can also be followed by hand. It was called
`ender3v2-klipper-on-mac` until v0.2.0.

## Results on one printer

Stock Ender 3 V2 (board 4.2.2, bowden extruder, CR Touch clone, carborundum
glass bed), mainline Klipper on a Mac mini VM over the bridge:

| | Before (Marlin) | After (Klipper) |
|---|---|---|
| Go/no-go print (~3 h, dense retractions) | — | 0 `Timer too close`, 0 lost communication, `bytes_invalid` 0 |
| Bed mesh range, 180 × 210 mm | 0.82 mm (UBL) | 0.205 mm |
| Probe repeatability (`PROBE_ACCURACY` std dev) | — | 0.0075 mm |
| A bust, same slicer | 4 h 05 (stock Orca process) | 1 h 51 (fast process), 2.2× faster |
| PLA first layer | — | sticks to the stock glass without glue |

The mesh gain came mostly from fixing the X gantry and tramming properly;
Klipper made that measurable.

## How it works

```
 Raspberry Pi / Linux PC                 Mac
 CH340 --udev--> /dev/printer            CH340 -> klipper-serial-bridge.py (LaunchAgent)
                  |                               TCP 192.168.64.1:7523 --host-only-->
                  v                      Debian VM (UTM): socat -> /dev/printer
         Klipper + Moonraker + Mainsail           -> Klipper + Moonraker + Mainsail
```

The same `printer.cfg` works on every host: Klipper reads `/dev/printer`, which
exists only after the cutover (`printer-link.sh enable`), so Klipper never
grabs the printer while it still runs Marlin. Why a VM and a bridge on the
Mac rather than Docker or USB passthrough:
[docs/adr/0001](docs/adr/0001-klipper-host-in-vm-with-tcp-serial-bridge.md);
why one setup for every host: [docs/adr/0002](docs/adr/0002-any-host-dev-printer-link.md).

## Install as a Claude Code plugin

```bash
claude plugin marketplace add oscarolar/ender3v2-klipper
claude plugin install ender3v2-klipper@ender3v2-klipper
```

Already had `ender3v2-klipper-on-mac` installed? Remove it first:
`claude plugin uninstall ender3v2-klipper-on-mac@ender3v2-klipper-on-mac` and
`claude plugin marketplace remove ender3v2-klipper-on-mac`.

Then ask Claude something like "move my Ender 3 V2 to Klipper on my
Raspberry Pi" (or "on this Mac"). The skill keeps your printer on Marlin until
the host is proven, asks you for physical feedback only (paper feel, knob
turns, tower heights), and reads every result as numbers from Moonraker.

## Follow it by hand

Start at [SKILL.md](skills/ender3v2-klipper/SKILL.md), then the references in
order:

1. [host-setup.md](skills/ender3v2-klipper/references/host-setup.md) (on a Mac first [host-mac-vm-bridge.md](skills/ender3v2-klipper/references/host-mac-vm-bridge.md))
2. [firmware-and-cutover.md](skills/ender3v2-klipper/references/firmware-and-cutover.md) and [printer-config.md](skills/ender3v2-klipper/references/printer-config.md)
3. [calibration.md](skills/ender3v2-klipper/references/calibration.md), [print-start-and-probe.md](skills/ender3v2-klipper/references/print-start-and-probe.md), [slicer-orca.md](skills/ender3v2-klipper/references/slicer-orca.md)
4. [go-no-go-and-rollback.md](skills/ender3v2-klipper/references/go-no-go-and-rollback.md)
5. [power-loss-and-monitoring.md](skills/ender3v2-klipper/references/power-loss-and-monitoring.md), [upgrades.md](skills/ender3v2-klipper/references/upgrades.md)

[troubleshooting.md](skills/ender3v2-klipper/references/troubleshooting.md) when stuck.

## What is in `files/`

| Path | What |
|---|---|
| `host/` | runs on the Klipper host: `install-stack.sh` (`SERIAL_MODE=usb` or `bridge`), `printer-link.sh` (cutover/rollback), systemd units, udev rule, nginx site |
| `mac/` | Mac only: `create-vm.sh` + `vm-seed/` (cloud-init), the USB ↔ TCP `klipper-serial-bridge.py`, LaunchAgents (`install-agents.sh`) |
| `firmware/ender3v2-422.config` | Klipper firmware build config for the 4.2.2 board |
| `klipper/` | `printer.cfg`, `macros.cfg` (`PRINT_START`, `PRINT_END`, power-loss resume), `moonraker.conf` |
| `orca/` | OrcaSlicer printer + fast process profile generator (macOS, Linux, Windows) |
| `calibration/` | retraction towers and 5-disc adhesion STLs, and the generator for other sizes (PA and ringing towers come with Klipper) |
| `tools/` | `deploy-config.sh`, Moonraker helper, print monitor, auto-resume, resume-point mirror, jitter probe |

Hosts, IPs, labels and paths are settings with defaults; each script
documents its variables in its header.

## Tests

```bash
uvx --with pyserial pytest -q tests
```

Covers the serial bridge (with pyserial's `loop://`), the Orca profile
generator, the calibration models, the auto-resume decisions, the resume-point mirror and the print
monitor against a fake Moonraker. Klipper batch-mode tests of the macros are
not included: they need a Klipper checkout and a built firmware dictionary.

## Limitations

- Proven on one printer, over the Mac path: Ender 3 V2, board 4.2.2, stock
  bowden, a CR Touch clone, a Mac mini M1 with UTM 4.7 and Debian 12. The Pi
  and Linux paths are Klipper's standard direct-USB setup driven by the same
  scripts, but have not had their own go/no-go print here yet. Other boards
  (4.2.7), probes or extruders need their own pins and numbers.
- The host is now part of the printer: a reboot, suspend or crash stops the
  print (heaters off). Power-loss resume (`PLR_RESUME`) is best effort.
- On a Mac, homing and probing need App Nap off, an interactive-priority
  bridge and a one-line Klipper patch (`TRSYNC_TIMEOUT` 25 → 50 ms) that every
  Klipper update reverts until `install-stack.sh` is re-run; and the Mac must
  not run iCloud Contacts/Photos sync or iPhone calls, which froze the VM
  every hour.
- The stock DWIN display goes dark; you control the printer from Mainsail.
- No accelerometer: input shaping is chosen from a printed ringing tower.
- A CR Touch clone can still latch at print start; the only fix is a printer
  power cycle. The start macro reduces how often it happens, it does not
  remove it.
- Nothing here is endorsed by Creality, Klipper, UTM, Raspberry Pi or OrcaSlicer.

## License

MIT, see [LICENSE](LICENSE).

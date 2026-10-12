# 0002. Any Klipper host, one printer.cfg through /dev/printer

- Status: accepted (2026-10-12). Extends 0001, which stays the Mac path.

## Context

The repo was shared with people who have no Mac. Most of it (firmware,
printer.cfg, macros, calibration, slicer, go/no-go) never depended on the
host; the installer, the units, the cutover and rollback steps did: user
`klipper` hardcoded in the units and nginx, the `TRSYNC_TIMEOUT` patch and
the socat unit always installed, and `install-stack.sh` starting Klipper
before the cutover. On a Raspberry Pi with the printer's USB attached, that
last point means Klipper opens and resets a printer still running Marlin.

## Decision

- One installer for every Debian-family host, `SERIAL_MODE=usb` (Pi, Linux
  PC: standard direct USB) or `bridge` (Mac VM: socat pty + `TRSYNC_TIMEOUT`
  patch). Units and nginx are templates filled with the installing user.
- `printer.cfg` always reads `/dev/printer`. Nothing creates it at install
  time; `printer-link.sh enable` does at the cutover (udev symlink for the
  CH340 `1a86:7523` in `usb` mode, `printer-pty` in `bridge` mode) and
  `disable` removes it at rollback. Meanwhile Klipper retries the open for
  about 90 s, then sits in `error`, off the port.
- The Mac-only material (VM, bridge, timing hardening, macOS hygiene) lives in
  `files/mac/` and one reference; everything else is host-neutral.
- Plugin and repo renamed `ender3v2-klipper-on-mac` → `ender3v2-klipper`.

## Consequences

- The udev rule matches any CH340: a second CH340 device on the same host
  needs the rule narrowed to the board's USB port.
- The Pi and Linux paths reuse Klipper's standard direct-USB setup but have
  not had their own go/no-go print in this repo yet.
- Existing installs of `ender3v2-klipper-on-mac` must uninstall and add the
  new marketplace; GitHub redirects the old repo URL.

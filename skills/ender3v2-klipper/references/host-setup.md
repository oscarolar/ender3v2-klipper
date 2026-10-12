# Phase A: the Klipper host

Everything here happens with the printer untouched: it keeps running Marlin
and whatever host it has today, USB cable included (it moves at the cutover). Paths are relative to the plugin root
(`files/...`). `<klipper-host>` is the host's LAN IP or name; `KLIPPER_SSH` its
ssh destination (`pi@192.168.1.50`, or an alias).

## Pick the host

| Host | Printer USB | `SERIAL_MODE` | Extra reference |
|---|---|---|---|
| Raspberry Pi 3B+/4/5 (Zero 2 W is used by others, tight at 512 MB; untested here), Raspberry Pi OS Lite 64-bit (Bookworm or later) | on the Pi | `usb` | "Raspberry Pi" below |
| Always-on Linux PC or server, Debian 12+ / Ubuntu 22.04+ | on the PC | `usb` | "Linux PC" below |
| Always-on Apple Silicon Mac, no Linux machine | on the Mac, bridged into a Debian VM | `bridge` | `host-mac-vm-bridge.md` (do it first, then come back for step 2) |
| Windows PC | — | — | untested here; WSL2 + `usbipd-win` would be `usb` mode inside WSL. A Pi is the safer route |

Direct USB is the standard Klipper setup and needs none of the Mac's timing
hardening. Whatever the host, it becomes part of the printer: a reboot,
suspend or crash of the host stops the print with the heaters off.

## Steps (all hosts)

1. **Base OS** with SSH by key, a user with sudo, a fixed LAN address (DHCP
   reservation in the router). Mac: the VM from `host-mac-vm-bridge.md`.
2. **Push installer and config** from any machine with ssh to the host:
   `KLIPPER_SSH=<user@host> LAN_CIDR=<your-lan>/24 files/tools/deploy-config.sh`
   (`LAN_CIDR`: the host's address with the last number 0, e.g. `192.168.1.50`
   → `192.168.1.0/24`, for a home router's usual 255.255.255.0 mask).
   It copies `files/host/*`, the firmware build config, `printer.cfg`,
   `macros.cfg` and `moonraker.conf` (with your LAN trusted). Run it before
   step 3: it does not restart services that do not exist yet.
3. **Install the stack** on the host, as the user that will own Klipper:
   `SERIAL_MODE=usb bash ~/install/install-stack.sh` (`bridge` for the Mac VM),
   inside `tmux` or with `nohup ... > ~/install.log 2>&1 &`: apt, pip and
   the clones take several minutes on a Pi and a dropped ssh kills them.
   It installs Klipper in its own Python 3 venv with the repo-owned
   `klipper.service` (Klipper's `scripts/install-debian.sh` is still Python 2),
   Moonraker with its own installer, Mainsail behind nginx, and the ARM
   toolchain for the firmware build. KIAUH is not used: it is an interactive
   TUI.
4. **Klipper is not connected yet.** `printer.cfg` reads `/dev/printer`, and
   nothing creates it until `bash ~/install/printer-link.sh enable` at the
   cutover (udev rule in `usb` mode, the socat unit in `bridge` mode). Until
   then Klipper sits in `startup` or `error` ("Unable to connect") and never opens the
   Marlin printer's port; `enable` restarts it.
   Do not point `printer.cfg` at `/dev/serial/by-id/...` "to save a step":
   Klipper would open and reset the printer while Marlin is still printing.
5. **Verify**: `curl http://<klipper-host>/server/info` answers;
   `klippy_state` `startup` or `error` is fine before the cutover. Mainsail
   loads at `http://<klipper-host>/`.
6. **Reboot test**: reboot the host with the printer idle; nginx, Moonraker
   and Klipper must come back without anyone touching it.

### MainsailOS instead of step 3 (Pi only)

Flashing MainsailOS with Raspberry Pi Imager is the usual Pi route and is
fine. Run `deploy-config.sh` with `--keep-moonraker` (keeps the image's
`moonraker.conf`; add `[octoprint_compat]` to it for Orca) and skip
`install-stack.sh`; `~/install/` then has `printer-link.sh`, the udev rule and
`ender3v2-422.config` for the cutover. Create the mode file once:
`echo usb > ~/printer_data/.serial-mode`.

## Raspberry Pi

- Power: the official supply. `vcgencmd get_throttled` must print
  `throttled=0x0`; anything else is under-voltage or heat, and causes
  `Timer too close` and SD corruption.
- The Pi back-powers the printer's board through the USB 5 V line: with the
  printer off, the board and display stay half-alive and the probe may not
  reset on a power cycle. Use a cable with the 5 V pin taped, or a USB data
  blocker, so "power-cycle the printer" really resets the board and the CR Touch.
- SD cards wear and corrupt on power cuts: use an A1/A2 card from a known
  brand or boot from a USB SSD; keep a copy of `~/printer_data/config`.
- The user created in Imager is already in `dialout`; `install-stack.sh`
  adds it anyway. It also runs `chmod o+x ~` so nginx can serve `~/mainsail`
  (others can enter the home dir, not list it).

- Printer powered on long after the Pi booted (or replugged): Klipper gave up
  connecting after ~90 s and sits in `error`. `FIRMWARE_RESTART` (Mainsail's
  restart button) once the printer is on; normal Klipper behaviour, not a fault.

## Linux PC

- Never suspend: `sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target`;
  laptop: `HandleLidSwitch=ignore` in `/etc/systemd/logind.conf`.
- No automatic reboots from updates (`unattended-upgrades`
  `Automatic-Reboot "false"`).
- Ubuntu desktop ships `brltty`, which claims the CH340 (`1a86:7523`) and
  makes the port vanish a second after it appears (`dmesg`: "brltty" /
  "interface 0 claimed"): `sudo apt purge brltty`.
- Heavy loads on the same machine (builds, Docker, local LLMs, video) should
  not hurt printing, which queues seconds ahead, but can stall homing and
  probing (untested here on a PC). If `Timer too close` shows up, measure before blaming the load:
  "Stall hunting" in `troubleshooting.md`.

## Moonraker notes

- `trusted_clients` must list your LAN (`deploy-config.sh` fills
  `@LAN_CIDR@`); `192.168.64.0/24` is the Mac VM's host-only network,
  harmless elsewhere.
- `cors_domains` rejects a bare `*`; use patterns such as `*.local` or real
  origins.
- `[update_manager mainsail-config]` needs `is_system_service: False`: an
  update of static config files must not restart services mid-print.
- Orca uploads through `[octoprint_compat]` (see `slicer-orca.md`).

## Remote access (optional)

- **Obico**: install `moonraker-obico` on the host with its own `install.sh`,
  then uncomment its includes in `printer.cfg` and `moonraker.conf`. The human
  links it in the Obico app (Add printer → "generic Klipper", 6-digit code).
  After a host rebuild: `cd ~/moonraker-obico && ./install.sh -L`. It is also
  the phone alert channel (`power-loss-and-monitoring.md`).
- **Alternative**: Tailscale or another VPN on the host, then Mainsail over it.
- Never port-forward Moonraker or Mainsail to the internet.

Next: `firmware-and-cutover.md`.

# Mac host: Debian VM in UTM + TCP serial bridge

Only when the always-on machine is an Apple Silicon Mac. Builds the Linux host
that `host-setup.md` then installs with `SERIAL_MODE=bridge`. The printer stays
on Marlin throughout.

## Architecture

```
 Mac (macOS, owns the USB)                     VM (Debian 12 arm64, UTM, headless)
 CH340 /dev/cu.usbserial-*                     socat -> /dev/printer (pty)
   | klipper-serial-bridge.py (LaunchAgent)       | klippy (mainline Klipper, own venv)
   +-- TCP 192.168.64.1:7523 -- host-only net --> | Moonraker :7125, Mainsail/nginx :80
 VM keep-alive (LaunchAgent, utmctl)            bridged NIC -> LAN IP (<klipper-host>)
```

`192.168.64.1` / `192.168.64.0/24` is UTM's default shared network and
`192.168.64.250` the VM's static host-only IP; override with `VM_IP`,
`BRIDGE_LISTEN`, `BRIDGE_ADDR`. Why not USB passthrough or Docker:
`docs/adr/0001-...` (UTM cannot attach USB to a headless VM; Docker on macOS
has the same USB wall plus a layer).

## Steps

1. **UTM**: `brew install --cask utm`, `utmctl` on the `PATH`.
2. **Create the VM**: `files/mac/create-vm.sh`. Settings (env): `VM_NAME`,
   `VM_IP`, `BRIDGE_IF` (default `en0`), `LAN_MAC`, `HOST_MAC`,
   `EXTRA_PUBKEY`, `SSH_ALIAS` (default `klipper-vm`, user `klipper`). It
   downloads Debian's genericcloud arm64 image, renders the cloud-init seed
   from `files/mac/vm-seed/`, builds the VM through UTM's AppleScript API and
   waits for cloud-init.
   - The seed ISO must be attached as a **VirtIO** drive, or genericcloud never
     sees it.
   - The genericcloud kernel has no USB or `ch341`; cloud-init installs
     `linux-image-arm64` and purges the cloud kernel. Harmless with the bridge.
   - Give `LAN_MAC` a DHCP reservation: that is `<klipper-host>`.
3. **Stack**: `host-setup.md` steps 2–3 with `KLIPPER_SSH=klipper-vm` and
   `SERIAL_MODE=bridge` (adds the `TRSYNC_TIMEOUT` patch and the disabled
   `printer-pty` unit).
4. **Bridge and keep-alive**: `files/mac/install-agents.sh` (env:
   `LABEL_PREFIX` default `com.example`, `BIN_DIR`, `BRIDGE_VENV`, `VM_IP`,
   `BRIDGE_LISTEN`, `VM_NAME`). Creates a venv with pyserial, installs both
   LaunchAgents, turns App Nap off for UTM. Restart UTM afterwards.
   `192.168.64.1` exists only while a shared-network VM runs; until then the
   bridge exits and launchd retries every 10 s.
5. **Verify**: `launchctl list | grep klipper`; `/tmp/klipper-serial-bridge.log`
   shows `listening on 192.168.64.1:7523 for 192.168.64.250`; `nc -z 192.168.64.1 7523`
   from the Mac logs `rejected 192.168.64.1` (only the VM is allowed).
6. **Reboot test**: reboot the Mac with the printer idle; VM, bridge and
   Moonraker come back alone. Needs auto-login (LaunchAgents run in the user
   session).
7. **macOS automatic updates off** (the human runs it, sudo):
   `sudo defaults write /Library/Preferences/com.apple.SoftwareUpdate AutomaticallyInstallMacOSUpdates -bool false`.

## Timing hardening (mandatory on the Mac)

Printing is not latency sensitive: Klipper queues moves seconds ahead on the
MCU. Homing and probing are: Klipper streams steps only ~0.1–0.25 s ahead and
expects a trsync renewal every 25 ms, so a short stall anywhere on VM → socat
→ TCP → bridge → USB aborts a probing move with `Timer too close` or
`Communication timeout during homing`. Apply all four; each one was needed:

| Fix | Where | Check |
|---|---|---|
| App Nap off for UTM | `defaults write ~/Library/Containers/com.utmapp.UTM/Data/Library/Preferences/com.utmapp.UTM NSAppSleepDisabled -bool YES`, restart UTM (`install-agents.sh` does it) | `defaults read ...` prints `1` |
| Bridge at interactive priority | `ProcessType Interactive` in the bridge LaunchAgent | `plutil -p` the installed plist |
| No Nagle delay | `TCP_NODELAY` in the bridge, `nodelay` on the socat `tcp:` address | in the files |
| Wider trsync window | `TRSYNC_TIMEOUT` 0.025 → 0.050 in `~/klipper/klippy/mcu.py` (`install-stack.sh`, bridge mode) | `grep ^TRSYNC_TIMEOUT ~/klipper/klippy/mcu.py` shows `0.050` |

A Klipper update (`git pull`, Mainsail's update manager) reverts the
`mcu.py` edit: re-run `install-stack.sh` after every update.

## Mac hygiene: nothing else may freeze the Mac (mandatory)

With all four fixes in place, long prints still died with
`MCU 'mcu' shutdown: Timer too close` mid-print, `sysload` ~0.04, no
retransmit burst. Cause, measured with `jitter-probe.py`: the whole VM froze
100–220 ms **once an hour** while macOS ran, in the same second,
`contactsd`/`AddressBookSourceSync` (iCloud Contacts, 110–150 % CPU), the
Phone app ("Calls from iPhone") and `mobileassetd`/`tccd`; iCloud Photos
analysis (`mediaanalysisd`, `photoanalysisd`) ran constantly. Every print
shutdown fell on one of those freezes. On the Mac that hosts the VM:

- System Settings → Apple Account → iCloud: **Contacts off** (remove from this
  Mac; it is per device) and **Photos off**.
- FaceTime → **Calls from iPhone off**; no Continuity extras.
- No other heavy jobs on that Mac while printing (photo libraries, video
  encoding, local AI models: an M1 running a TTS model pushed QEMU to 23–37 %
  and into swap).
- `taskpolicy` on `QEMULauncher` only shortened the freezes; it is not a fix.

After that: no hourly freeze in three checks and clean prints; random
40–125 ms stalls remain, harmless for printing. If shutdowns continue, find
the frozen hop ("Stall hunting" in `troubleshooting.md`) before rewriting the
bridge: a faster bridge does not help when macOS freezes the VM.

## macOS Local Network privacy

A LaunchAgent running a Homebrew Python (or any child process) to reach the
VM gets `No route to host` (errno 65) while the same command works over SSH,
which is exempt. Run Mac-side watchers (`klipper-autoresume.py`,
`plr-mirror.py`) from an SSH session (`nohup`), or as a LaunchAgent whose own
program is `/usr/bin/python3`, the binary macOS lets through. Over SSH the Mac
has no Homebrew on the `PATH`; use full paths.

Back to `host-setup.md` step 5, then `firmware-and-cutover.md`.

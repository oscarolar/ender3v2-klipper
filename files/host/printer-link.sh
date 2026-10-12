#!/bin/bash
# Connect or disconnect Klipper from the printer: creates or removes /dev/printer.
# Run on the Klipper host. Mode comes from install-stack.sh (~/printer_data/.serial-mode).
#   usb:    udev rule 99-printer.rules links the CH340 to /dev/printer
#   bridge: printer-pty.service (socat) exposes the Mac's TCP bridge as /dev/printer
#
#   bash ~/install/printer-link.sh enable    # cutover: Klipper takes the printer
#   bash ~/install/printer-link.sh disable   # rollback: the port is free for Marlin hosts
#   bash ~/install/printer-link.sh status
set -euo pipefail
MODE="$(cat ~/printer_data/.serial-mode 2>/dev/null || true)"
# installs from before v0.2.0 have no .serial-mode: the socat unit means bridge
[ -n "$MODE" ] || { [ -f /etc/systemd/system/printer-pty.service ] && MODE=bridge || MODE=usb; }
RULE=/etc/udev/rules.d/99-printer.rules
reload_udev() {
    sudo udevadm control --reload-rules && sudo udevadm trigger --subsystem-match=tty \
        || { echo "udev reload failed: /dev/printer is not up to date" >&2; exit 1; }
    sleep 2
}
case "${1:-status}" in
enable)
    if [ "$MODE" = bridge ]; then sudo systemctl enable --now printer-pty
    else sudo cp ~/install/99-printer.rules "$RULE"; reload_udev; fi
    sleep 2; sudo systemctl restart klipper ;;
disable)
    sudo systemctl stop klipper
    if [ "$MODE" = bridge ]; then sudo systemctl disable --now printer-pty
    else sudo rm -f "$RULE"; reload_udev; fi
    # Klipper keeps running, waiting for /dev/printer: it no longer touches the port
    sudo systemctl start klipper ;;
status) ;;
*) sed -n '2,10p' "$0"; exit 2 ;;
esac
echo "mode $MODE: $(ls -l /dev/printer 2>/dev/null || echo 'no /dev/printer (Klipper is not connected)')"

#!/bin/bash
# Copy the stack installer to the Klipper host (Raspberry Pi, Linux PC or the
# Mac's VM) and push printer.cfg, macros.cfg and moonraker.conf. Run it from any
# machine with SSH access to the host. First install and restores only:
# day-to-day changes happen on the host (Mainsail editor, SAVE_CONFIG), so once
# deployed this refuses to overwrite a host file that differs from the repo
# copy unless --force. Run it BEFORE install-stack.sh.
#
#   KLIPPER_SSH=pi@192.168.1.50 LAN_CIDR=192.168.1.0/24 files/tools/deploy-config.sh [--force] [--keep-moonraker]
#
# --keep-moonraker: leave the host's moonraker.conf alone (MainsailOS images ship their own).
#
# LAN_CIDR (required): your LAN, trusted by Moonraker.
# KLIPPER_SSH: ssh destination of the host (user@ip or a ~/.ssh/config alias;
# default klipper-vm, the alias files/mac/create-vm.sh writes).
set -euo pipefail
FILES_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SSH_ALIAS="${KLIPPER_SSH:-${SSH_ALIAS:-klipper-vm}}"
: "${LAN_CIDR:?set LAN_CIDR to your LAN, e.g. 192.168.1.0/24}"
FORCE=0; CFGS="printer.cfg macros.cfg moonraker.conf"
for a in "$@"; do case "$a" in
    --force) FORCE=1 ;;
    --keep-moonraker) CFGS="printer.cfg macros.cfg" ;;
    *) echo "unknown option $a" >&2; exit 2 ;;
esac; done
VMCFG=printer_data/config
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
cp "$FILES_DIR/klipper/printer.cfg" "$FILES_DIR/klipper/macros.cfg" "$TMP/"
sed "s#@LAN_CIDR@#$LAN_CIDR#" "$FILES_DIR/klipper/moonraker.conf" > "$TMP/moonraker.conf"

ssh "$SSH_ALIAS" "mkdir -p install $VMCFG"
scp -q "$FILES_DIR"/host/{install-stack.sh,printer-link.sh,klipper.service,printer-pty.service,99-printer.rules,mainsail.nginx} "$SSH_ALIAS:install/"
scp -q "$FILES_DIR/firmware/ender3v2-422.config" "$SSH_ALIAS:install/"

if ssh "$SSH_ALIAS" "test -f $VMCFG/.deployed-from-repo" && [ "$FORCE" = 0 ]; then
    for f in $CFGS; do
        if ! ssh "$SSH_ALIAS" "cat $VMCFG/$f 2>/dev/null" | cmp -s - "$TMP/$f"; then
            echo "host $f differs from the repo copy: pull it first, or --force to overwrite" >&2
            exit 1
        fi
    done
    echo "host already matches the repo"; exit 0
fi
for f in $CFGS; do scp -q "$TMP/$f" "$SSH_ALIAS:$VMCFG/$f"; done
ssh "$SSH_ALIAS" "touch $VMCFG/.deployed-from-repo; systemctl list-unit-files klipper.service >/dev/null 2>&1 && sudo systemctl restart moonraker klipper || true"
echo "deployed installer to ~/install and config to ~/$VMCFG"

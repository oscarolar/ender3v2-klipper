#!/bin/bash
# Install Klipper, Moonraker, Mainsail (nginx) and mainsail-config on the
# Klipper host: a Raspberry Pi (Raspberry Pi OS Lite 64-bit), any Debian 12+ /
# Ubuntu 22.04+ machine, or the Debian VM on a Mac. Runs ON the host as the
# user that will own Klipper (pi, klipper, yours), from ~/install
# (files/tools/deploy-config.sh copies it there). Idempotent: re-run it after
# every Klipper update (in bridge mode `git pull` reverts the TRSYNC patch).
# Uses each project's own installer: KIAUH is an interactive TUI.
#
#   SERIAL_MODE=usb    bash ~/install/install-stack.sh   # printer USB on this host (Pi, Linux PC)
#   SERIAL_MODE=bridge BRIDGE_ADDR=192.168.64.1:7523 bash ~/install/install-stack.sh   # Mac VM
#
# Klipper always reads /dev/printer. Nothing creates that link here: it
# appears at the cutover (files/host/printer-link.sh enable), so until then
# Klipper cannot open the printer that still runs Marlin.
set -euo pipefail
SERIAL_MODE="${SERIAL_MODE:-usb}"
BRIDGE_ADDR="${BRIDGE_ADDR:-192.168.64.1:7523}"
USER="${USER:-$(id -un)}"   # unset in non-login shells (docker exec, some sudo/ssh forms)
case "$SERIAL_MODE" in usb|bridge) ;; *) echo "SERIAL_MODE must be usb or bridge" >&2; exit 2 ;; esac
cd ~
sudo DEBIAN_FRONTEND=noninteractive apt-get update -q >/dev/null
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q nginx unzip git curl socat python3-serial >/dev/null
sudo usermod -aG dialout,tty "$USER"
[ -d klipper ] || git clone -q https://github.com/Klipper3d/klipper.git
[ -d moonraker ] || git clone -q https://github.com/Arksine/moonraker.git
[ -d mainsail-config ] || git clone -q https://github.com/mainsail-crew/mainsail-config.git
mkdir -p ~/printer_data/{config,logs,gcodes,comms,systemd}

if [ "$SERIAL_MODE" = bridge ]; then
    # Homing/probing trsync margin 25 -> 50 ms for the VM + TCP bridge path
    # (docs/adr/0001): short stalls abort probing moves with "Timer too close" /
    # "Communication timeout during homing" at the stock 25 ms. Not needed when
    # the printer's USB is on this host.
    sed -i 's/^TRSYNC_TIMEOUT = 0.025$/TRSYNC_TIMEOUT = 0.050  # VM + TCP serial bridge path/' \
        ~/klipper/klippy/mcu.py
    grep -q '^TRSYNC_TIMEOUT = 0.050' ~/klipper/klippy/mcu.py \
        || { echo "TRSYNC_TIMEOUT line not found in klippy/mcu.py: upstream changed it, patch by hand" >&2; exit 1; }
fi

# Klipper host: own venv + unit (upstream install-debian.sh is Python 2).
# The ARM toolchain builds the board firmware on this host.
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q python3-venv python3-dev \
    libffi-dev build-essential libncurses-dev pkg-config libusb-1.0-0-dev \
    gcc-arm-none-eabi binutils-arm-none-eabi libnewlib-arm-none-eabi stm32flash >/dev/null
[ -x ~/klippy-env/bin/python ] || python3 -m venv ~/klippy-env
~/klippy-env/bin/pip install -q -r ~/klipper/scripts/klippy-requirements.txt
sed "s#@USER@#$USER#g; s#@HOME@#$HOME#g" ~/install/klipper.service \
    | sudo tee /etc/systemd/system/klipper.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable -q klipper

[ -x ~/moonraker-env/bin/python ] || ~/moonraker/scripts/install-moonraker.sh

if [ ! -f ~/mainsail/index.html ]; then
    mkdir -p ~/mainsail
    curl -fsSL -o /tmp/mainsail.zip https://github.com/mainsail-crew/mainsail/releases/latest/download/mainsail.zip
    unzip -qo /tmp/mainsail.zip -d ~/mainsail && rm /tmp/mainsail.zip
fi
chmod o+x ~   # nginx (www-data) must traverse the home dir to serve ~/mainsail
sed "s#@HOME@#$HOME#g" ~/install/mainsail.nginx | sudo tee /etc/nginx/sites-available/mainsail >/dev/null
sudo ln -sf /etc/nginx/sites-available/mainsail /etc/nginx/sites-enabled/mainsail
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t -q
sudo systemctl enable -q nginx
sudo systemctl reload-or-restart nginx   # apt does not always start it
ln -sf ~/mainsail-config/client.cfg ~/printer_data/config/mainsail.cfg

if [ "$SERIAL_MODE" = bridge ]; then
    sed "s#tcp:192.168.64.1:7523#tcp:$BRIDGE_ADDR#" ~/install/printer-pty.service \
        | sudo tee /etc/systemd/system/printer-pty.service >/dev/null
    sudo systemctl daemon-reload   # installed, NOT enabled: enabled at the cutover
fi
echo "$SERIAL_MODE" > ~/printer_data/.serial-mode
# last, once mainsail.cfg exists: without /dev/printer Klipper ends in "error"
# (Unable to connect) and stays off the port until printer-link.sh enable restarts it
sudo systemctl restart klipper
echo "stack installed (SERIAL_MODE=$SERIAL_MODE; /dev/printer appears with printer-link.sh enable)"

#!/bin/bash
# Create the headless UTM VM (Debian 12 arm64 genericcloud + cloud-init) that
# hosts Klipper. Runs ON the Mac. Idempotent: exits if the VM exists, unless
# --recreate (which deletes the VM and its disk first).
#
#   files/mac/create-vm.sh [--recreate]
#
# Settings (environment, with defaults):
#   VM_NAME     klipper
#   VM_IP       192.168.64.250     host-only IP on UTM's shared network (bridge peer)
#   BRIDGE_IF   en0                macOS interface for the bridged (LAN) NIC
#   LAN_MAC     52:54:00:00:00:01  give it a DHCP reservation in your router
#   HOST_MAC    52:54:00:00:00:02
#   WORK        $HOME/vm           image cache and seed ISO
#   EXTRA_PUBKEY                   optional extra SSH public key (e.g. your laptop)
#   SSH_ALIAS   klipper-vm         Host entry written to ~/.ssh/config
set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
SRC="$(cd "$(dirname "$0")/vm-seed" && pwd)"
VM_NAME="${VM_NAME:-klipper}"
VM_IP="${VM_IP:-192.168.64.250}"
BRIDGE_IF="${BRIDGE_IF:-en0}"
LAN_MAC="${LAN_MAC:-52:54:00:00:00:01}"
HOST_MAC="${HOST_MAC:-52:54:00:00:00:02}"
WORK="${WORK:-$HOME/vm}"
SSH_ALIAS="${SSH_ALIAS:-klipper-vm}"
KEY="$HOME/.ssh/$SSH_ALIAS"
IMG=debian-12-genericcloud-arm64.qcow2
IMG_URL="https://cloud.debian.org/images/cloud/bookworm/latest/$IMG"

log() { echo "$(date '+%F %T') $*"; }
exists() { utmctl list 2>/dev/null | awk 'NR>1{print $3}' | grep -qx "$VM_NAME"; }

command -v utmctl >/dev/null || { echo "install UTM and link utmctl (brew install --cask utm)" >&2; exit 1; }
if exists; then
    [ "${1:-}" = "--recreate" ] || { log "VM $VM_NAME already exists (use --recreate)"; exit 0; }
    utmctl stop "$VM_NAME" --force 2>/dev/null || true
    sleep 3
    osascript -e "tell application \"UTM\" to delete virtual machine \"$VM_NAME\""
    log "deleted old VM"
fi

command -v qemu-img >/dev/null || brew install qemu
mkdir -p "$WORK/seed"
[ -f "$WORK/$IMG" ] || curl -fsSL -o "$WORK/$IMG" "$IMG_URL"
cp "$WORK/$IMG" "$WORK/$VM_NAME.qcow2"
qemu-img resize -q "$WORK/$VM_NAME.qcow2" 12G

[ -f "$KEY" ] || ssh-keygen -q -t ed25519 -N "" -C "mac->$SSH_ALIAS" -f "$KEY"
keys="$(cat "$KEY.pub")"
[ -n "${EXTRA_PUBKEY:-}" ] && keys="$keys
$EXTRA_PUBKEY"
python3 - "$SRC" "$WORK/seed" "$keys" "$VM_NAME" "$VM_IP" "$LAN_MAC" "$HOST_MAC" <<'PY'
import pathlib, sys
src, out, keys, name, ip, lan_mac, host_mac = sys.argv[1:]
src, out = pathlib.Path(src), pathlib.Path(out)
key_lines = "\n".join(f"      - {k}" for k in keys.splitlines() if k.strip())
subs = {"@SSH_KEYS@": key_lines, "@VM_NAME@": name, "@VM_IP@": ip,
        "@LAN_MAC@": lan_mac, "@HOST_MAC@": host_mac}
for tmpl, dst in (("user-data.tmpl", "user-data"), ("meta-data", "meta-data"),
                  ("network-config", "network-config")):
    text = (src / tmpl).read_text()
    for k, v in subs.items():
        text = text.replace(k, v)
    (out / dst).write_text(text)
PY
hdiutil makehybrid -quiet -ov -o "$WORK/seed.iso" "$WORK/seed" -iso -joliet -default-volume-name cidata

# The seed ISO must be on a VirtIO drive: genericcloud does not see it otherwise.
osascript <<OSA
tell application "UTM"
  set img to POSIX file "$WORK/$VM_NAME.qcow2"
  set iso to POSIX file "$WORK/seed.iso"
  make new virtual machine with properties {backend:qemu, configuration:{name:"$VM_NAME", architecture:"aarch64", memory:2048, cpu cores:2, drives:{{source:img}, {interface:VirtIO, source:iso}}, network interfaces:{{hardware:"virtio-net-pci", mode:bridged, host interface:"$BRIDGE_IF", address:"$LAN_MAC"}, {hardware:"virtio-net-pci", mode:shared, address:"$HOST_MAC"}}}}
end tell
OSA
rm -f "$WORK/$VM_NAME.qcow2"   # UTM copied the disk into the .utm bundle
log "created VM $VM_NAME"

python3 - "$SSH_ALIAS" "$VM_IP" "$KEY" <<'PY'
import pathlib, re, sys
alias, ip, key = sys.argv[1:]
p = pathlib.Path.home() / ".ssh/config"
txt = p.read_text() if p.exists() else ""
txt = re.sub(rf"\n*Host {re.escape(alias)}\n(?:[ \t]+.*\n?)*", "\n", txt).rstrip("\n")
txt += (f"\n\nHost {alias}\n  HostName {ip}\n  User klipper\n"
        f"  IdentityFile {key}\n  ConnectTimeout 10\n  StrictHostKeyChecking accept-new\n")
p.write_text(txt.lstrip("\n"))
PY
ssh-keygen -R "$VM_IP" >/dev/null 2>&1 || true

utmctl start "$VM_NAME"
log "waiting for cloud-init (it reboots once to swap the kernel)"
for _ in $(seq 1 60); do
    k="$(ssh -o BatchMode=yes "$SSH_ALIAS" 'cloud-init status 2>/dev/null | grep -q done && uname -r' 2>/dev/null || true)"
    case "$k" in *-arm64) case "$k" in *cloud*) ;; *) log "ready, kernel $k"; exit 0 ;; esac ;; esac
    sleep 10
done
log "timed out waiting for the VM"; exit 1

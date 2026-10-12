#!/usr/bin/env python3
"""Expose the printer's USB serial port to the Klipper VM over TCP.

UTM cannot pass USB devices to a headless VM (docs/adr/0001), so macOS keeps the
CH340 and this bridge forwards bytes between it and one TCP client: socat in the
VM, which turns the stream back into /dev/printer for Klippy. The serial port is
opened when the client connects and closed when it leaves. The bridge refuses to
open it while another process (OctoPrint, a slicer) holds it. Serial silences
and blocked writes/sends are logged as "STALL" lines; files/tools/jitter-probe.py
explains how to read them against host and VM freezes.

  klipper-serial-bridge.py --port auto --baud 250000 \
      --listen 192.168.64.1:7523 --allow 192.168.64.250

Defaults can also come from the environment: BRIDGE_PORT, BRIDGE_BAUD,
BRIDGE_LISTEN (UTM's shared-network host address) and BRIDGE_ALLOW (the VM's
host-only IP, comma-separated for several).
"""
import argparse
import glob
import logging
import os
import socket
import subprocess
import threading
import time

import serial

log = logging.getLogger("klipper-serial-bridge")

# Stall logging, to find which hop freezes before a Klipper "Timer too close".
# The MCU reports temperatures every 300 ms, so a longer silence on the serial
# side, or a write/send that blocks, is logged with its duration.
READ_GAP_MS = 400
IDLE_GAP_MS = 3000  # longer silences are an idle or shut-down MCU, not a stall
BLOCK_MS = 50


def _timed(label, fn, *args):
    t0 = time.monotonic()
    result = fn(*args)
    ms = (time.monotonic() - t0) * 1000
    if ms > BLOCK_MS:
        log.warning("STALL %s blocked %.0f ms", label, ms)
    return result


def resolve_port(port):
    """'auto' means the single /dev/cu.usbserial-* device (the CH340)."""
    if port != "auto":
        return port
    found = sorted(glob.glob("/dev/cu.usbserial-*"))
    if not found:
        raise FileNotFoundError("no /dev/cu.usbserial-* device (printer off or unplugged?)")
    return found[0]


def port_in_use(path):
    """True if a process other than this one has the device open."""
    res = subprocess.run(["lsof", "-t", path], capture_output=True, text=True)
    pids = {int(p) for p in res.stdout.split()}
    pids.discard(os.getpid())
    return bool(pids)


def _serial_to_socket(ser, conn, stop):
    last_rx = None
    try:
        while not stop.is_set():
            data = ser.read(ser.in_waiting or 1)
            if data:
                now = time.monotonic()
                if last_rx is not None and READ_GAP_MS < (now - last_rx) * 1000 < IDLE_GAP_MS:
                    log.warning("STALL serial silent %.0f ms", (now - last_rx) * 1000)
                last_rx = now
                _timed("socket send", conn.sendall, data)
    except (OSError, serial.SerialException) as exc:
        log.warning("serial->socket stopped: %s", exc)
    finally:
        stop.set()
        try:
            conn.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass


def _handle(conn, port, baud):
    try:
        path = resolve_port(port)
        if not path.startswith("loop://") and port_in_use(path):
            raise OSError(f"{path} is in use by another process (OctoPrint?)")
        ser = serial.serial_for_url(path, baud, timeout=0.05)
    except (OSError, serial.SerialException) as exc:
        log.error("cannot open serial: %s", exc)
        return
    stop = threading.Event()
    reader = threading.Thread(target=_serial_to_socket, args=(ser, conn, stop), daemon=True)
    reader.start()
    try:
        while not stop.is_set():
            data = conn.recv(4096)
            if not data:
                break
            _timed("serial write", ser.write, data)
    except (OSError, serial.SerialException) as exc:
        log.warning("socket->serial stopped: %s", exc)
    finally:
        stop.set()
        reader.join(timeout=1)
        ser.close()


def _hang_up(conn):
    """Send FIN, not RST: close() alone resets if the client's bytes are unread."""
    try:
        conn.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass


def serve(listen, allow, port, baud, ready=None):
    host, _, tcp_port = listen.rpartition(":")
    srv = socket.create_server((host, int(tcp_port)))
    log.info("listening on %s:%s for %s", *srv.getsockname()[:2], ",".join(sorted(allow)))
    if ready:
        ready(srv.getsockname()[:2])
    while True:
        conn, (peer, _) = srv.accept()
        with conn:
            try:
                if peer not in allow:
                    log.warning("rejected %s", peer)
                    continue
                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                log.info("client %s connected", peer)
                _handle(conn, port, baud)
                log.info("client %s closed", peer)
            finally:
                _hang_up(conn)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    env = os.environ.get
    ap.add_argument("--port", default=env("BRIDGE_PORT", "auto"))
    ap.add_argument("--baud", type=int, default=int(env("BRIDGE_BAUD", "250000")))
    ap.add_argument("--listen", default=env("BRIDGE_LISTEN", "192.168.64.1:7523"))
    ap.add_argument("--allow", default=env("BRIDGE_ALLOW", "192.168.64.250"))
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    serve(args.listen, set(args.allow.split(",")), args.port, args.baud)


if __name__ == "__main__":
    main()

"""Tests for files/mac/klipper-serial-bridge.py (serial side faked with loop://)."""
import importlib.util
import pathlib
import socket
import subprocess
import sys
import tempfile
import threading
import time

import pytest

SRC = pathlib.Path(__file__).resolve().parents[1] / "files/mac/klipper-serial-bridge.py"
spec = importlib.util.spec_from_file_location("bridge", SRC)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


def start(allow, port="loop://"):
    bound = {}
    ready = threading.Event()

    def on_ready(addr):
        bound["addr"] = addr
        ready.set()

    t = threading.Thread(target=bridge.serve, args=("127.0.0.1:0", set(allow), port, 250000, on_ready), daemon=True)
    t.start()
    assert ready.wait(2)
    return bound["addr"]


def roundtrip(addr, payload=b"M105\n"):
    with socket.create_connection(addr, timeout=2) as s:
        s.sendall(payload)
        got = b""
        deadline = time.time() + 2
        while len(got) < len(payload) and time.time() < deadline:
            chunk = s.recv(64)
            if not chunk:
                break
            got += chunk
        return got


def test_bytes_flow_both_ways():
    addr = start({"127.0.0.1"})
    assert roundtrip(addr) == b"M105\n"


def test_client_can_reconnect():
    addr = start({"127.0.0.1"})
    assert roundtrip(addr, b"A\n") == b"A\n"
    assert roundtrip(addr, b"B\n") == b"B\n"


def test_rejects_unlisted_peer():
    addr = start({"192.168.64.250"})
    with socket.create_connection(addr, timeout=2) as s:
        assert s.recv(16) == b""


def test_unopenable_port_closes_client_and_keeps_serving():
    addr = start({"127.0.0.1"}, port="/dev/does-not-exist")
    for _ in range(2):
        with socket.create_connection(addr, timeout=2) as s:
            s.sendall(b"M105\n")
            assert s.recv(16) == b""


def test_resolve_port_passes_explicit_paths_through():
    assert bridge.resolve_port("/dev/cu.usbserial-220") == "/dev/cu.usbserial-220"
    assert bridge.resolve_port("loop://") == "loop://"


def test_resolve_port_auto_without_device_raises(monkeypatch):
    monkeypatch.setattr(bridge.glob, "glob", lambda pattern: [])
    with pytest.raises(FileNotFoundError):
        bridge.resolve_port("auto")


def test_resolve_port_auto_picks_single_device(monkeypatch):
    monkeypatch.setattr(bridge.glob, "glob", lambda pattern: ["/dev/cu.usbserial-110"])
    assert bridge.resolve_port("auto") == "/dev/cu.usbserial-110"


def test_port_in_use_detects_other_process():
    with tempfile.NamedTemporaryFile() as f:
        assert bridge.port_in_use(f.name) is False  # only this process holds it
        # A child process (not os.fork: the suite is multi-threaded) holds it open.
        holder = subprocess.Popen(
            [sys.executable, "-c", "import sys, time; f = open(sys.argv[1]); print(flush=True); time.sleep(3)", f.name],
            stdout=subprocess.PIPE,
        )
        try:
            holder.stdout.readline()  # the file is open once the child prints
            assert bridge.port_in_use(f.name) is True
        finally:
            holder.kill()
            holder.wait()
            holder.stdout.close()


def test_timed_logs_only_slow_calls(caplog):
    caplog.set_level("WARNING", logger="klipper-serial-bridge")
    assert bridge._timed("fast", lambda x: x + 1, 1) == 2
    bridge._timed("slow", time.sleep, (bridge.BLOCK_MS + 30) / 1000)
    stalls = [r.getMessage() for r in caplog.records if "STALL" in r.getMessage()]
    assert len(stalls) == 1 and stalls[0].startswith("STALL slow blocked")


def test_serial_silence_logged_between_read_and_idle_gaps(caplog, monkeypatch):
    # Shrink the thresholds so the test runs fast: a 250 ms gap is a stall,
    # a 700 ms gap counts as an idle MCU and is not logged.
    monkeypatch.setattr(bridge, "READ_GAP_MS", 150)
    monkeypatch.setattr(bridge, "IDLE_GAP_MS", 500)
    caplog.set_level("WARNING", logger="klipper-serial-bridge")
    addr = start({"127.0.0.1"})
    with socket.create_connection(addr, timeout=2) as s:
        for gap in (0, 0.25, 0.7):
            time.sleep(gap)
            s.sendall(b"x")
            assert s.recv(1) == b"x"
    time.sleep(0.1)
    silent = [r.getMessage() for r in caplog.records if r.getMessage().startswith("STALL serial silent")]
    assert len(silent) == 1

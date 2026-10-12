"""Tests for the print-watch tools in files/tools/ (no printer, no network host)."""
import ast
import http.server
import importlib.util
import json
import pathlib
import shlex
import subprocess
import threading

import pytest

TOOLS = pathlib.Path(__file__).resolve().parents[1] / "files/tools"


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), TOOLS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


autoresume = load("klipper-autoresume")
mirror = load("plr-mirror")

SAVED = {"plr_active": True, "plr_file": "part 50__PCT__.gcode", "plr_layer": 12, "plr_z": 2.6,
         "plr_bed": 60.0, "plr_extruder": 210.0}
TTC = "MCU 'mcu' shutdown: Timer too close"


PART = "part 50%.gcode"


def test_link_fault_with_matching_point_resumes():
    assert autoresume.decide(TTC, SAVED, PART, PART, 0, 10) is None
    assert autoresume.decide("Lost communication with MCU 'mcu'", SAVED, PART, PART, 3, 10) is None


@pytest.mark.parametrize("reason", ["Heater extruder not heating at expected rate", "ADC out of range", ""])
def test_other_shutdowns_are_not_resumed(reason):
    assert "not a link fault" in autoresume.decide(reason, SAVED, PART, PART, 0, 10)


def test_inactive_point_is_not_resumed():
    assert "no saved resume point" in autoresume.decide(TTC, dict(SAVED, plr_active=False), PART, PART, 0, 10)


@pytest.mark.parametrize("watched", ["other.gcode", None])
def test_stale_point_from_another_print_is_not_resumed(watched):
    assert "not the watched print" in autoresume.decide(TTC, SAVED, watched, PART, 0, 10)


def test_unauthorized_print_is_not_resumed_even_with_its_own_point():
    # another file started after the authorized one and saved its own point
    other = dict(SAVED, plr_file="other.gcode")
    assert autoresume.decide(TTC, other, PART, "other.gcode", 0, 10) is not None
    # ...or shut down before its first layer, with the authorized point still armed
    assert "not the authorized print" in autoresume.decide(TTC, SAVED, PART, "other.gcode", 0, 10)


def test_max_resumes():
    assert "resumes already" in autoresume.decide(TTC, SAVED, PART, PART, 10, 10)


@pytest.mark.parametrize("bad", [{"plr_extruder": 0}, {"plr_extruder": 169.9}, {"plr_extruder": None},
                                 {"plr_bed": 0}, {"plr_bed": None}, {"plr_extruder": "210"}])
def test_unsafe_saved_targets_are_not_resumed(bad):
    v = dict(SAVED, **bad)
    assert "not safe" in autoresume.decide(TTC, v, PART, PART, 0, 10)
    assert "not safe" in autoresume.unsafe_temps({k: x for k, x in v.items() if x is not None})


def test_resume_refuses_unsafe_targets_before_touching_the_printer(monkeypatch):
    calls = []
    monkeypatch.setattr(autoresume, "post", lambda *a, **k: calls.append(a))
    assert autoresume.resume(dict(SAVED, plr_extruder=0), 1.0) is False
    assert calls == []


def test_resume_turns_heaters_off_when_it_gives_up(monkeypatch):
    sent = []
    monkeypatch.setattr(autoresume, "post", lambda path, body=None: sent.append((path, body)))
    states = iter([True, False])  # firmware restart reaches ready; heating times out
    monkeypatch.setattr(autoresume, "wait", lambda pred, timeout, step=3: next(states))
    assert autoresume.resume(SAVED, 1.0) is False
    assert sent[-1] == ("/printer/gcode/script", {"script": "M104 S0\nM140 S0"})


def test_saved_file_decodes_percent():
    assert autoresume.saved_file(SAVED) == "part 50%.gcode"
    assert autoresume.saved_file({}) is None


def test_restore_lines_round_trip_through_shlex_and_literal_eval():
    v = {"plr_file": 'a "b" \\c; #d.gcode', "plr_pos": 1234, "plr_z": 2.6, "plr_active": True,
         "other": "kept out"}
    lines = mirror.restore_lines(v)
    assert len(lines) == 4
    for line in lines:
        # what Klipper does: shlex-split the parameters, literal_eval the VALUE
        params = dict(p.split("=", 1) for p in shlex.split(line)[1:])
        assert ast.literal_eval(params["VALUE"]) == v[params["VARIABLE"]]


def test_restore_needs_yes_and_an_active_point(tmp_path, monkeypatch, capsys):
    sent = []
    monkeypatch.setattr(mirror, "gcode", sent.append)
    out = tmp_path / "m.json"
    mirror.write(str(out), {"saved_at": "t", "print": {}, "variables": SAVED})
    assert mirror.restore(str(out)) is False
    assert "file 'part 50%.gcode', layer 12, Z 2.6" in capsys.readouterr().out
    assert sent == []
    assert mirror.restore(str(out), yes=True) is True
    assert len(sent) == 1 and "plr_file" in sent[0]
    # once the print ends the mirror is disarmed: even --yes refuses
    mirror.disarm(str(out), "complete")
    assert json.loads(out.read_text())["variables"]["plr_active"] is False
    assert mirror.restore(str(out), yes=True) is False
    assert len(sent) == 1


def test_disarm_without_a_mirror_is_a_no_op(tmp_path):
    mirror.disarm(str(tmp_path / "none.json"), "complete")
    assert not (tmp_path / "none.json").exists()


def test_hosts_from_env_and_args(monkeypatch):
    monkeypatch.delenv("KLIPPER_HOST", raising=False)
    with pytest.raises(SystemExit):
        mirror.main(["--restore", "--out", "/nonexistent"])
    monkeypatch.setattr(mirror, "restore", lambda out, yes: True)
    monkeypatch.setenv("KLIPPER_HOST", "klipper.local")
    mirror.main(["--restore"])
    assert mirror.BASE == "http://klipper.local"
    mirror.main(["10.0.0.5", "--restore"])
    assert mirror.BASE == "http://10.0.0.5"


# --- klipper-printmon.sh against a fake Moonraker -------------------------

def status(ps="printing", wh="ready", msg="Printer is ready", prog=0.1, retx=0):
    return {"webhooks": {"state": wh, "state_message": msg},
            "print_stats": {"state": ps}, "virtual_sdcard": {"progress": prog},
            "mcu": {"last_stats": {"bytes_retransmit": retx, "srtt": 0.002}},
            "save_variables": {"variables": {"plr_layer": 5}}}


def run_printmon(states):
    seq = iter(states)

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/printer/objects/query"):
                body = {"result": {"status": next(seq)}}
            else:
                body = {"result": {"gcode_store": []}}
            data = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        # an exported no-op sleep keeps the 20 s polls instant
        cmd = 'sleep() { :; }; export -f sleep; exec bash "$0" "$1"'
        res = subprocess.run(["bash", "-c", cmd, str(TOOLS / "klipper-printmon.sh"),
                              "127.0.0.1:%d" % srv.server_address[1]],
                             capture_output=True, text=True, timeout=30)
    finally:
        srv.shutdown()
    return res


def test_printmon_reports_shutdown_and_pause_once_and_survives_them():
    res = run_printmon([
        status(),
        status(ps="error", wh="shutdown", msg="MCU 'mcu' shutdown: Timer too close\nOnce the underlying..."),
        status(ps="error", wh="shutdown", msg="MCU 'mcu' shutdown: Timer too close"),
        status(ps="standby", prog=0.0),
        status(prog=0.6, retx=40),
        status(ps="paused", prog=0.6, retx=40),
        status(ps="paused", prog=0.6, retx=40),
        status(ps="complete", prog=1.0, retx=40),
    ])
    out = res.stdout.splitlines()
    assert res.returncode == 0, res.stderr
    assert out.count("SHUTDOWN MCU 'mcu' shutdown: Timer too close (layer 5)") == 1
    assert sum(line.startswith("ALERT paused") for line in out) == 1
    assert any(line.startswith("READY") for line in out)
    assert any(line.startswith("LINK retransmits 0 -> 40") for line in out)
    assert out[-1].startswith("END state=complete")


def test_printmon_ignores_complete_left_from_an_earlier_print():
    res = run_printmon([status(ps="complete", prog=1.0), status(), status(ps="cancelled")])
    assert res.returncode == 0, res.stderr
    assert res.stdout.splitlines()[-1].startswith("END state=cancelled")

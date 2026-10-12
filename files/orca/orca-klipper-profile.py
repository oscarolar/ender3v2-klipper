#!/usr/bin/env python3
"""Create OrcaSlicer printer and process profiles for the Klipper Ender 3 V2.

The printer profile is copied from an existing Orca user printer profile (your
Marlin one, which stays untouched as the fallback) and switched to Klipper:
Moonraker host, klipper G-code flavor, firmware retraction, PRINT_START /
PRINT_END / PLR_SAVE hooks, and machine limits that match printer.cfg.
Optionally a fast process profile is written too.

  orca-klipper-profile.py <klipper-host> --source "Ender-3 V2 CR Touch" \\
      [--name "Ender-3 V2 Klipper CR Touch"] [--process "0.20mm Klipper fast"]

Run with OrcaSlicer CLOSED: Orca rewrites its profiles on exit.
"""
import argparse
import datetime
import glob
import json
import os
import pathlib
import sys

DEFAULT_NAME = "Ender-3 V2 Klipper CR Touch"
PROCESS_BASE = "0.20mm Standard @Creality Ender3V2"
PROCESS_BASE_ID = "pmPzGC04PU62qjcz"  # Orca's id for PROCESS_BASE
# printer.cfg max_accel 3000 and max_velocity 200. Orca clamps a process's
# accelerations to the printer profile's machine limits, so they must match.
MAX_ACCEL = "3000"
MACHINE_LIMITS = {
    "machine_max_acceleration_x": [MAX_ACCEL, MAX_ACCEL],
    "machine_max_acceleration_y": [MAX_ACCEL, MAX_ACCEL],
    "machine_max_acceleration_extruding": [MAX_ACCEL, MAX_ACCEL],
    "machine_max_acceleration_travel": [MAX_ACCEL, MAX_ACCEL],
    "machine_max_speed_x": ["200", "200"],
    "machine_max_speed_y": ["200", "200"],
}


def default_orca_user():
    """Orca's user profile dir on the machine running Orca."""
    home = pathlib.Path.home()
    if sys.platform == "darwin":
        return home / "Library/Application Support/OrcaSlicer/user"
    if sys.platform == "win32":
        return pathlib.Path(os.environ.get("APPDATA", home / "AppData/Roaming")) / "OrcaSlicer/user"
    flatpak = home / ".var/app/io.github.softfever.OrcaSlicer/config/OrcaSlicer/user"
    return flatpak if flatpak.exists() else home / ".config/OrcaSlicer/user"


ORCA_USER = default_orca_user()


def build(src, host, name=DEFAULT_NAME):
    """Printer profile for Klipper from a copy of the source profile dict."""
    p = dict(src)
    p.update({
        "name": name,
        "printer_settings_id": name,
        "gcode_flavor": "klipper",  # other flavors emit M190/M104 before PRINT_START
        "host_type": "octoprint",  # Orca's "Octo/Klipper", served by Moonraker's octoprint_compat
        "print_host": host,
        "machine_start_gcode": ("PRINT_START BED=[bed_temperature_initial_layer_single] "
                                "EXTRUDER=[nozzle_temperature_initial_layer]"),
        "machine_end_gcode": "PRINT_END",
        "layer_change_gcode": "G92 E0\nPLR_SAVE LAYER=[layer_num] Z=[layer_z]",
        "use_firmware_retraction": "1",
        "use_relative_e_distances": "1",
        "retraction_length": ["1.5"],
        **MACHINE_LIMITS,
    })
    return p


def build_process(name="0.20mm Klipper fast"):
    """Fast PLA process for a bowden Ender 3 V2 tuned to accel 3000."""
    # Orca refuses "wipe" together with firmware retraction, so it is not set.
    return {
        "from": "User",
        "inherits": PROCESS_BASE,
        "name": name,
        "print_settings_id": name,
        "version": "2.3.2.75",
        "print_extruder_id": ["1"],
        # Orca's generic single-extruder variant key, the one the stock "Creality
        # Ender-3 V2" system profiles use. Not a hardware claim: do not change it
        # to a bowden value (this profile works as is in Orca 2.4.2).
        "print_extruder_variant": ["Direct Drive Standard"],
        "reduce_crossing_wall": "1",  # travel inside the part: fewer strings between islands
        "accel_to_decel_enable": "0",  # ACCEL_TO_DECEL is deprecated in Klipper
        "default_acceleration": "3000",
        "outer_wall_acceleration": "2000",
        "inner_wall_acceleration": "3000",
        "sparse_infill_acceleration": "3000",
        "internal_solid_infill_acceleration": "3000",
        "top_surface_acceleration": "2000",
        "initial_layer_acceleration": "500",
        "travel_acceleration": "3000",
        "bridge_acceleration": "1000",
        "outer_wall_speed": "60",
        "inner_wall_speed": "90",
        "sparse_infill_speed": "110",  # 0.45 x 0.2 x 110 = 9.9 mm3/s, under a stock hotend's ~12
        "internal_solid_infill_speed": "90",
        "top_surface_speed": "60",
        "gap_infill_speed": "60",
        "initial_layer_speed": "25",
        "initial_layer_infill_speed": "40",
        "travel_speed": "180",
    }


def find_machine_dir(orca_user):
    dirs = glob.glob(str(orca_user / "*/machine"))
    if len(dirs) != 1:
        sys.exit(f"expected one Orca user machine dir under {orca_user}, found {dirs}")
    return pathlib.Path(dirs[0])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("host", help="the Klipper host's LAN IP or hostname (Moonraker)")
    ap.add_argument("--source", required=True,
                    help="name of your existing Orca user printer profile to copy")
    ap.add_argument("--name", default=DEFAULT_NAME, help="name of the new printer profile")
    ap.add_argument("--process", help="also write a fast process profile with this name")
    ap.add_argument("--orca-user", type=pathlib.Path, default=ORCA_USER,
                    help="Orca's user profile dir (default: per OS, %(default)s)")
    args = ap.parse_args(argv)

    mdir = find_machine_dir(args.orca_user)
    src_json = mdir / f"{args.source}.json"
    if not src_json.exists():
        sys.exit(f"no user printer profile {src_json}")
    src = json.loads(src_json.read_text())
    text = json.dumps(build(src, args.host, args.name), indent=4, ensure_ascii=False) + "\n"
    (mdir / f"{args.name}.json").write_text(text)
    src_info = mdir / f"{args.source}.info"
    info = []
    if src_info.exists():
        info = [line for line in src_info.read_text().splitlines()
                if not line.startswith(("sync_info", "setting_id", "updated_time"))]
    info += ["sync_info = ", "setting_id = ",
             f"updated_time = {int(datetime.datetime.now().timestamp())}"]
    (mdir / f"{args.name}.info").write_text("\n".join(info) + "\n")
    print(f"wrote {mdir / args.name}.json")

    if args.process:
        pdir = mdir.parent / "process"
        pdir.mkdir(exist_ok=True)
        ptext = json.dumps(build_process(args.process), indent=4, ensure_ascii=False) + "\n"
        (pdir / f"{args.process}.json").write_text(ptext)
        (pdir / f"{args.process}.info").write_text(
            f"sync_info = create\nuser_id = \nsetting_id = \nbase_id = {PROCESS_BASE_ID}\nupdated_time = 0\n")
        print(f"wrote {pdir / args.process}.json")


if __name__ == "__main__":
    main()

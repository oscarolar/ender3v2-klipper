# printer.cfg for the Ender 3 V2 (board 4.2.2 + CR Touch)

`files/klipper/printer.cfg` is the working file; `files/klipper/macros.cfg`
holds `PRINT_START`, `PRINT_END` and power-loss recovery. Both are based on
Klipper's `config/printer-creality-ender3-v2-2020.cfg`. Start from those, not
from memory or from other boards' configs.

## Facts that are easy to get wrong

| Item | Correct for 4.2.2 + CR Touch on the BLTouch port | Common wrong value |
|---|---|---|
| Probe section | `[bltouch]` is **not** in the upstream example file: add it yourself | assuming the upstream file has it |
| Probe pins | `sensor_pin: ^PB1`, `control_pin: PB0` (the 4.2.2 BLTouch port) | `^PC14` / `PA1` (other boards; PA1 is the hotend heater) |
| Probe offsets, stock CR Touch mount | `x_offset: -40`, `y_offset: -5` | `-44 / -8` (other mounts) |
| Stepper drivers | standalone, no `[tmc2208 ...]` sections, no UART | TMC UART sections |
| MCU | `serial: /dev/printer`, `baud: 250000`, `restart_method: command`. `/dev/printer` is created by `printer-link.sh enable` at the cutover: a udev link to the CH340 on a Pi/Linux host, the socat pty on a Mac VM | `/dev/serial/by-id/...` before the cutover: Klipper opens and resets the printer while it still runs Marlin |
| Extruder | `rotation_distance = 200 × 16 / <Marlin E steps>`; stock E93 → 34.406 | leaving the Marlin E value unconverted |
| X/Y/Z | `rotation_distance` 40 / 40 / 8 | — |
| Z endstop | `probe:z_virtual_endstop` + `[safe_z_home]` at `home_xy_position: 157.5, 122.5` (probe over bed centre) | the Z switch |

## Coordinates: nozzle vs probe

With `x_offset -40`, the probe sits 40 mm left of the nozzle. Some sections
take nozzle coordinates, others probe coordinates:

| Section | Coordinates | Values used |
|---|---|---|
| `[safe_z_home] home_xy_position` | nozzle | `157.5, 122.5` |
| `[bed_mesh] mesh_min / mesh_max` | probe | `10, 10` / `190, 220` |
| `[axis_twist_compensation] calibrate_start_x / end_x / y` | **probe** | `10` / `190` / `117.5` |
| `[screws_tilt_adjust] screwN` | nozzle | `73,38` `235,38` `235,208` `73,208` |

Nozzle values in `[axis_twist_compensation]` cause "Move out of range".
The right-hand knobs are out of the probe's reach (nozzle X max 235 → probe X
195), so `SCREWS_TILT_CALCULATE` reads the nearest reachable point there;
read those two with some tolerance. `screw_thread: CW-M4`.

## Other sections worth having

- `[firmware_retraction]` (`retract_length: 1.5` start; tuned in
  `calibration.md`), `[exclude_object]`, `[pause_resume]`,
  `[virtual_sdcard]`, `[display_status]` (the last three come with Mainsail's
  `mainsail.cfg`).
- `[force_move] enable_force_move: True`: `PLR_RESUME` needs
  `SET_KINEMATIC_POSITION`, which only exists with it.
- `[save_variables]`: storage for `PLR_SAVE`. File names go through Klipper's
  shlex (posix) parser: `PLR_SAVE` escapes `\` and `"` so names with spaces,
  quotes, `;` or `#` survive. A `%` (Orca adds one to scaled models, e.g.
  `Model+70%.gcode`) makes `save_variables` (ConfigParser) raise and shut
  Klipper down, so `PLR_SAVE` stores it as `__PCT__` and `PLR_RESUME` decodes it.
- Macro edits load only on `RESTART`/`FIRMWARE_RESTART`, which ends a running
  print: upload the file mid-print and it takes effect at the next restart
  (such as the one before a `PLR_RESUME`). Render-test the template first; a
  Jinja error there stops Klipper from starting.
- Probe settings live in `print-start-and-probe.md`.

## SAVE_CONFIG

`PID_CALIBRATE`, `PROBE_CALIBRATE`, `BED_MESH_CALIBRATE`,
`AXIS_TWIST_COMPENSATION_CALIBRATE` write to an autosave block at the end of
`printer.cfg` via `SAVE_CONFIG` (which restarts Klipper). Values set in the
main body are commented out automatically when the autosave block overrides
them. The shipped file has no autosave block; its "reference" comments are
one printer's results, not values to copy.

Hand edits (pressure advance, `max_accel`, retraction) go into the main body
on the host (`~/printer_data/config/printer.cfg`, or Mainsail's editor), then
`FIRMWARE_RESTART`.

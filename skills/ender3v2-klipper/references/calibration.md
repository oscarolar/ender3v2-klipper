# Calibration, in order

Every step moves or heats: the human is at the printer and the bed is clear
(SKILL.md protocol). Send commands and read results with
`files/tools/moonraker.sh` (`KLIPPER_HOST=<klipper-host>`): `gcode`, `store`,
`query`, `mesh`. Example numbers are from one stock bowden Ender 3 V2 with a
CR Touch clone; yours will differ.

## Mechanics first: the X gantry

Before tramming or meshing, measure top frame → X beam on both sides. If they
differ, the gantry is tilted or sagging; no knob turning or mesh fixes that.
Seen: a loose eccentric nut on the right Z carriage let the right side sag
4 mm and the mesh drift between days. Tighten the eccentric nuts until the
carriage has no play but still rolls, level the gantry, then continue. Repeat
this check whenever the mesh changes day to day.

## 1. PID

```
PID_CALIBRATE HEATER=extruder TARGET=210     (215 if you print hotter)
PID_CALIBRATE HEATER=heater_bed TARGET=60    (65 for the usual PLA bed temp)
SAVE_CONFIG
```
Read `PID parameters: pid_Kp=... pid_Ki=... pid_Kd=...` from the console.
Each run takes several minutes: the API call times out at 60 s and
`moonraker.sh gcode` waits it out.

## 2. Extrusion (100 mm)

`M109 S210`. Human marks the filament 120 mm above the extruder inlet.
`M83`, `G1 E100 F100`. Human measures what is left above the inlet.
`actual = 120 - left`; `new rotation_distance = old × actual / 100`
(extruded more than 100 → smaller value). Edit, `FIRMWARE_RESTART`, repeat
until 20 ± 1 mm is left. Example: 30.075.

## 3. Probe Z offset (paper test)

`G28`, `PROBE_CALIBRATE`. **The paper must not be on the bed while the probe
deploys**: paper under the pin shifts the reading. The probe measures first,
then the nozzle comes down; only then does the paper go in. With paper under the nozzle
the human reports the feel; send `TESTZ Z=-0.1` / `+0.05` / `-0.025` on their
word until it drags slightly; `ACCEPT`, `SAVE_CONFIG`. Sanity check: close to
Marlin's `M851 Z` with the sign flipped. Example: 1.099.

## 4. Tram the bed

`G28`, `SCREWS_TILT_CALCULATE`. Output per knob such as `CW 00:15` (15 min =
a quarter turn). The knobs are M4, 0.7 mm per turn. "CW" is as seen **from
above**; turning the knob from below, CW-from-above = loosen = the bed corner
goes **up**. Repeat until every knob is ≤ `00:05`. Confirm with a fast
`BED_MESH_CALIBRATE PROBE_COUNT=3,3 SAMPLES=1` and `moonraker.sh mesh`.

## 5. Axis twist

`AXIS_TWIST_COMPENSATION_CALIBRATE`: at each point the probe measures, then
the paper test with the same `TESTZ` / `ACCEPT` flow (paper out before the
next probe); `SAVE_CONFIG`. Needs probe coordinates in the
config (`printer-config.md`). Example: `0.00875, 0.00625, -0.015`.

## 6. Mesh

`G28`, `BED_MESH_CALIBRATE`, `SAVE_CONFIG`, then `moonraker.sh mesh` (back row
on top, plus `range`). Never read the graph. Example: range 0.205 mm over
180 × 210 mm (Marlin UBL on the same bed: 0.82 mm). Probe repeatability:
`PROBE_ACCURACY` → `standard deviation` (example 0.0075 mm).

## 7. Pressure advance (bowden)

Slice Klipper's `docs/prints/square_tower.stl` (copy it from `~/klipper` on the
host): 0.2 mm layers, 1 wall, no infill or top, outer wall ≤ 80 mm/s, keeping
flow ≤ ~10 mm³/s. A tower printed beyond the hotend's flow is invalid.
Before printing:
```
SET_VELOCITY_LIMIT SQUARE_CORNER_VELOCITY=1 ACCEL=500
TUNING_TOWER COMMAND=SET_PRESSURE_ADVANCE PARAMETER=ADVANCE START=0 FACTOR=.020
```
`FACTOR=.020` is the bowden factor (`.005` is for direct drive). Human reports
the height (mm) with the sharpest corners; `PA = height × 0.020`. Stay below
the value where the extruder grinds. Example: smoothest 15–20 mm, grinding
near 0.40, kept 0.32. Set `pressure_advance` in `[extruder]`.

## 8. Ringing (no accelerometer)

Slice `ringing_tower.stl`: 0.2 mm layers, 1 wall, outer wall ~80 mm/s.
Before printing:
```
SET_VELOCITY_LIMIT MINIMUM_CRUISE_RATIO=0 SQUARE_CORNER_VELOCITY=1
SET_PRESSURE_ADVANCE ADVANCE=0
TUNING_TOWER COMMAND=SET_VELOCITY_LIMIT PARAMETER=ACCEL START=1500 STEP_DELTA=500 STEP_HEIGHT=5
```
Band n (5 mm each) = 1500 + 500 × n. Human reports where echoes after the
corners start. Ignore the wavy notches of the model: they are its geometry,
not ringing. Example: nothing below ~5500, so `max_accel: 3000` without
`[input_shaper]`. If ringing starts low, count ripples N over distance D on
the X and Y faces: `freq = 100 × N / D` (at 100 mm/s), add `[input_shaper]`
with `shaper_type: mzv` and both frequencies.

## 9. Retraction

Two 10 × 10 mm towers 60 mm apart, 40 mm tall. Before printing:
```
TUNING_TOWER COMMAND=SET_RETRACTION PARAMETER=RETRACT_LENGTH START=1.0 STEP_DELTA=0.5 STEP_HEIGHT=5
```
Human picks the lowest band without strings; set `retract_length` in
`[firmware_retraction]`. Example: 1.5 mm was enough once PA was set (Marlin
had 2.5). PLA at 210 °C.

## 10. First layer and adhesion

Five 25 mm discs, 2 layers, in a dice-five pattern (four corners and the
centre). Human checks each disc: same squish everywhere, no gaps, no ridges.
If one corner differs, go back to step 4. Example: PLA sticks to the stock
carborundum glass without glue.

Then the go/no-go print: `go-no-go-and-rollback.md`.

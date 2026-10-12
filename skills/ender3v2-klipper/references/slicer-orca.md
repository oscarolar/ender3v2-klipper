# OrcaSlicer for the Klipper Ender 3 V2

## Generate the profiles

With Orca **closed** (it rewrites profiles on exit), on the machine running Orca:

```bash
files/orca/orca-klipper-profile.py <klipper-host> --source "<your Marlin printer profile>" \
    [--name "Ender-3 V2 Klipper CR Touch"] [--process "0.20mm Klipper fast"]
```

It copies your existing user printer profile (left untouched as the Marlin
fallback) and sets what Klipper needs. It finds Orca's user folder on macOS,
Windows (`%APPDATA%`) and Linux (`~/.config`, or the Flatpak one); `--orca-user`
overrides it. `files/orca/0.20mm Klipper fast.json`
is the process it writes, for reference or manual import.

## What the printer profile must have, and why

| Setting | Value | Why |
|---|---|---|
| G-code flavor | `klipper` | every other flavor emits `M190`/`M104` before the start G-code, so the printer heats before `PRINT_START` homes and probes |
| Host type / host | Octo/Klipper, `<klipper-host>` | Moonraker's `[octoprint_compat]` accepts Orca's upload |
| Start G-code | `PRINT_START BED=[bed_temperature_initial_layer_single] EXTRUDER=[nozzle_temperature_initial_layer]` | all heating, homing and probing live in the macro |
| End G-code | `PRINT_END` | |
| Layer change G-code | `G92 E0` then `PLR_SAVE LAYER=[layer_num] Z=[layer_z]` | power-loss resume point; with relative E, Orca refuses to slice without `G92 E0` in the layer G-code |
| Use firmware retraction | on | retraction length comes from `[firmware_retraction]` |
| Relative E | on | matches `M83` in `PRINT_START` |
| Machine limits accel X/Y/extruding/travel | = Klipper `max_accel` (3000) | Orca silently clamps process accelerations to these limits |
| Machine max speed X/Y | = `max_velocity` (200) | same clamping |

Orca refuses "wipe while retracting" together with firmware retraction: leave
wipe off.

## Fast process

Orca's stock Ender 3 V2 process (accel 500, outer wall 25 mm/s) leaves most of
the machine unused. The fast process: accel 3000 (outer wall and top 2000,
first layer 500, bridges 1000), outer wall 60, inner wall 90, sparse infill
110, solid infill 90, travel 180 mm/s, first layer 25. Sparse infill at 110
mm/s is 0.45 × 0.2 × 110 = 9.9 mm³/s, inside a stock hotend's ~12 mm³/s.
Example: a bust went from 4 h 05 to 1 h 51 (2.2×) with no visible loss.

## Layer height and speed factor

- Maximum layer height ≈ 80 % of the nozzle: 0.32 mm on a 0.4 nozzle (Orca's
  Ender 3 V2 `max_layer_height`). For a quick draft use 0.32 mm, 2 walls,
  ~10 % infill, no brim, not 0.40.
- `M220 S<n>` (Mainsail's speed slider) after the first layer is fine on top
  of the fast process: the filament's Max volumetric speed still caps flow.
  Raise it once `print_stats.state` is `printing` and the first layer is done.
  `FIRMWARE_RESTART` resets it to 100 %; restore it after a resume
  (`power-loss-and-monitoring.md`).

## Slicing from the Orca command line

When an agent slices with the `OrcaSlicer` binary instead of the GUI, the
filament's bed temperature can come out wrong (35 °C instead of the preset
value), both in `PRINT_START BED=` and in the `M140` after the first layer.
Before uploading, check every bed temperature in the file
(`grep -nE '^(PRINT_START|M140|M190)' file.gcode`) and fix all of them, not
just the start line: 35 °C on glass lets PLA lift and marks the layer lines.

## Per-filament pressure advance and retraction

Klipper, not Orca, holds `pressure_advance` and `[firmware_retraction]`, so
they apply to every filament until something changes them. Give **every**
filament preset a Filament start G-code (Orca emits it after `PRINT_START`)
that sets both; otherwise a PETG print leaves PETG values active for the next
PLA print:

```
SET_PRESSURE_ADVANCE ADVANCE=<this filament's PA>
SET_RETRACTION RETRACT_LENGTH=<mm> RETRACT_SPEED=<mm/s> UNRETRACT_SPEED=<mm/s>
```

PETG on this stock hotend: nozzle 235–240 °C (the PTFE-lined heatbreak must
stay at or below 240 °C even if the spool allows 250), bed 70 °C, part fan
30–50 % and off for the first 3 layers, Max volumetric speed 8 mm³/s,
retraction speed 25 mm/s. Start PA near 0.40 and tune it with the PA tower
(`calibration.md`); on a glass bed use glue stick as a release layer, because
PETG can pull chips out of clean glass.

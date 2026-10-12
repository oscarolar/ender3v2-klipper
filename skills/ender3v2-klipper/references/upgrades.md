# Upgrades after Klipper (optional)

Only after the go/no-go print passed. Every hardware change below invalidates
calibration: redo PID, the 100 mm extrusion, PA, retraction (and the probe Z
offset if the nozzle or probe moved). `calibration.md`.

## Know what you have first (ask, don't infer from photos)

| Fact | How to check | Why it matters |
|---|---|---|
| Hotend: PTFE down to the nozzle, or all-metal / bimetal heatbreak | Human pulls the Bowden at the hotend, or looks at the tube end after removing the nozzle | PTFE-lined: stay ≤ 240 °C (PETG 235–240). A red heatsink with a set screw is not proof of all-metal |
| Fans voltage | Label on the fan; the stock V2 is 24 V | 12 V fans on 24 V burn out |
| Extruder | Single or dual gear; aluminium lever arm or plastic | single gear grinds under high PA or dense retractions |

## What is worth it, for speed on a stock bowden V2

In rough order of effect per cost:

1. **High-flow nozzle (CHT-style) or a volcano block**: the stock hotend tops
   out near ~10–12 mm³/s PLA (8 PETG); flow, not acceleration, is the limit of
   the fast process. Raise the filament's Max volumetric speed only after
   testing it.
2. **Bimetal heatbreak** (if the hotend is PTFE-lined): allows higher
   temperatures and higher flow. Measure the current throat (thread, smooth OD,
   length) before buying; the PTFE then stops above the throat.
3. **Dual-gear extruder**, only if the stock one grinds or slips (see the
   `M92`/`rotation_distance` drift, filament with gear bites).
4. **Better part cooling** (5015 blowers, 24 V, on the single part-fan output):
   lets PLA overhangs and bridges keep up at speed.
5. **Accelerometer** (ADXL345): replaces the manual ringing tower with
   measured input shaping and usually allows a higher `max_accel`. On a Pi it
   wires to the GPIO SPI; on a Mac VM or a PC it needs a USB board
   (RP2040-based ADXL345), which on a Mac is another serial device to bridge.

Not worth it for speed: linear rails, a direct-drive conversion (worth it for
TPU and short retractions, not for speed), a second Z rod (stability only; it
changes the mesh, re-mesh after).

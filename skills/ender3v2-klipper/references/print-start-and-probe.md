# PRINT_START and CR Touch (clone) behaviour

Many "CR Touch" units are clones with a pin that sticks. Every behaviour below
was observed on one; a genuine unit may be more forgiving, but the same
settings work for both.

## Facts

- The pin sticks on its **first deploy after sitting idle**.
- Parked ~10 mm over a hot (65 °C) bed, the pin sticks or the probe latches.
- Every deploy is another chance to stick. More samples make it worse.
- A **latched alarm** (solid red LED, or `BLTouch failed to raise probe` that
  repeats) clears only with a **printer power cycle**: the probe stays powered
  through `BLTOUCH_DEBUG COMMAND=reset`, any "unstick" macro and
  `FIRMWARE_RESTART`.
- LED normal but `Failed to verify BLTouch probe is raised` / `Probe triggered
  prior to movement`: the pin stuck once. `BLTOUCH_DEBUG COMMAND=reset`,
  `QUERY_PROBE` must say `open`, relaunch the print. If it keeps happening,
  clean the pin with isopropyl alcohol.
- Probing moves are also where host or link stalls show up (`Timer too close`,
  `Communication timeout during homing`): "Stall hunting" in
  `troubleshooting.md` (on a Mac first "Timing hardening" in
  `host-mac-vm-bridge.md`). A failure at print start costs nothing: relaunch.
- A power cycle must really cut the probe's power: on a Pi, USB back-power can
  keep the board alive (`host-setup.md`).

## [bltouch] settings

```ini
samples: 2                     # Z homing
samples_tolerance: 0.05
samples_tolerance_retries: 3
stow_on_each_sample: True      # keep True for clones
probe_with_touch_mode: False   # keep False for clones
speed: 5
sample_retract_dist: 5
```

The mesh overrides samples with `SAMPLES=1` (one deploy per point).

## PRINT_START order that works

`files/klipper/macros.cfg`:

1. `G28 X Y` (`safe_z_home` `z_hop: 10` lifts Z first, so the pin has room)
2. `_PROBE_EXERCISE` (pin_down / pin_up × 2, then reset)
3. `G28 Z` (cold)
4. `G1 Z50` (park high while heating)
5. `M140` + `M190` (heat bed)
6. `_PROBE_EXERCISE` (again, after sitting idle during heat-up)
7. `G28 Z` (hot, final Z reference)
8. `BED_MESH_CALIBRATE ADAPTIVE=1 SAMPLES=1`
9. Purge at the home corner (heats the nozzle there with `M109`), wipe line
   at the front.

Wrong orders seen: meshing cold then heating (mesh moves with bed
expansion), and parking the probe low while heating (pin sticks, probe
latches).

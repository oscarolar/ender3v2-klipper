#!/usr/bin/env python3
"""Log scheduler freezes of the machine it runs on.

Run one copy on every machine in the printer's path: the Klipper host (a
Raspberry Pi, a Linux PC, or the Klipper VM) and, with a Mac VM, the Mac that
runs the serial bridge too. It sleeps 5 ms in a loop and logs any wake-up more
than --stall-ms late, with the wall-clock time, plus an hourly summary line.
Lateness is measured on both the monotonic and the wall clock and the larger is
logged: the monotonic clock stops during a system suspend (macOS and Linux), so
only the wall clock sees a sleep. A wall-clock step (NTP) can show up as a
one-off STALL too.

After a Klipper "Timer too close" or "Lost communication", line up the time of
the shutdown with the logs:

- STALL in the bridge log (klipper-serial-bridge.py): the USB/CH340 side went
  silent or a write/send blocked.
- STALL in the Mac host's probe: the host froze (sleep, App Nap, load).
- STALL in the VM's (or Pi's/PC's) probe: the Klipper host itself froze.
- No STALL anywhere: suspect the network hop between them.

  jitter-probe.py --name mac --stall-ms 40 >> ~/jitter-probe.log
"""
import argparse
import time


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--name", default="host", help="label for this machine in the log")
    ap.add_argument("--stall-ms", type=float, default=40)
    ap.add_argument("--period-ms", type=float, default=5)
    args = ap.parse_args()
    period = args.period_ms / 1000
    n = worst = stalls = 0
    hour = time.monotonic()
    print(f"{time.strftime('%F %T')} {args.name} probe start, stall > {args.stall_ms:.0f} ms", flush=True)
    while True:
        t0, w0 = time.monotonic(), time.time()
        time.sleep(period)
        late = (max(time.monotonic() - t0, time.time() - w0) - period) * 1000
        n += 1
        worst = max(worst, late)
        if late > args.stall_ms:
            stalls += 1
            print(f"{time.strftime('%F %T')} STALL {args.name} froze {late:.0f} ms", flush=True)
        if time.monotonic() - hour >= 3600:
            print(f"{time.strftime('%F %T')} {args.name} hour: {n} samples, {stalls} stalls, worst {worst:.0f} ms",
                  flush=True)
            n = worst = stalls = 0
            hour = time.monotonic()


if __name__ == "__main__":
    main()

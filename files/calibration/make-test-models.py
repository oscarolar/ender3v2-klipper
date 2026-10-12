#!/usr/bin/env python3
"""Generate the retraction and first-layer test models as STL (stdlib only).

  make-test-models.py retraction [--size 10] [--gap 60] [--height 40] [-o retraction_towers.stl]
  make-test-models.py adhesion   [--bed 220] [--margin 30] [--diameter 25] [--height 0.4] [-o adhesion_dice5.stl]

retraction: two square towers side by side; the travel between them is what
strings. adhesion: five discs in a dice-five pattern (four corners and the
centre) placed in bed coordinates: slice them where they are, without
auto-arrange, or the corners are lost. Height 0.4 = two 0.2 mm layers.
The shipped STLs in this folder are the defaults.
"""
import argparse
import math


def box(x0, y0, size, h):
    x1, y1 = x0 + size, y0 + size
    v = [(x0, y0, 0), (x1, y0, 0), (x1, y1, 0), (x0, y1, 0),
         (x0, y0, h), (x1, y0, h), (x1, y1, h), (x0, y1, h)]
    faces = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
             (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]
    return [(v[a], v[b], v[c]) for a, b, c in faces]


def cylinder(cx, cy, r, h, n=64):
    tris = []
    for i in range(n):
        a, b = 2 * math.pi * i / n, 2 * math.pi * (i + 1) / n
        p1 = (cx + r * math.cos(a), cy + r * math.sin(a))
        p2 = (cx + r * math.cos(b), cy + r * math.sin(b))
        tris += [((cx, cy, 0), p2 + (0,), p1 + (0,)), ((cx, cy, h), p1 + (h,), p2 + (h,)),
                 (p1 + (0,), p2 + (0,), p2 + (h,)), (p1 + (0,), p2 + (h,), p1 + (h,))]
    return tris


def retraction(size=10, gap=60, height=40):
    return box(0, 0, size, height) + box(gap, 0, size, height)


def adhesion(bed=220, margin=30, diameter=25, height=0.4):
    lo, hi, mid = margin, bed - margin, bed / 2
    centres = [(lo, lo), (hi, lo), (mid, mid), (lo, hi), (hi, hi)]
    return [t for x, y in centres for t in cylinder(x, y, diameter / 2, height)]


def normal(t):
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = t
    ux, uy, uz, vx, vy, vz = bx - ax, by - ay, bz - az, cx - ax, cy - ay, cz - az
    n = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
    length = math.sqrt(sum(c * c for c in n)) or 1
    return tuple(c / length for c in n)


def stl(name, tris):
    out = [f"solid {name}"]
    for t in tris:
        out.append(" facet normal %.6g %.6g %.6g" % normal(t))
        out.append("  outer loop")
        out += ["   vertex %.4f %.4f %.4f" % p for p in t]
        out += ["  endloop", " endfacet"]
    out.append(f"endsolid {name}")
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="model", required=True)
    r = sub.add_parser("retraction")
    r.add_argument("--size", type=float, default=10)
    r.add_argument("--gap", type=float, default=60, help="X distance between tower origins")
    r.add_argument("--height", type=float, default=40)
    r.add_argument("-o", "--out", default="retraction_towers.stl")
    a = sub.add_parser("adhesion")
    a.add_argument("--bed", type=float, default=220, help="printable bed size (square)")
    a.add_argument("--margin", type=float, default=30, help="corner disc centre to bed edge")
    a.add_argument("--diameter", type=float, default=25)
    a.add_argument("--height", type=float, default=0.4)
    a.add_argument("-o", "--out", default="adhesion_dice5.stl")
    args = ap.parse_args(argv)
    if args.model == "retraction":
        tris = retraction(args.size, args.gap, args.height)
    else:
        tris = adhesion(args.bed, args.margin, args.diameter, args.height)
    with open(args.out, "w") as f:
        f.write(stl(args.model, tris))
    print(f"wrote {args.out} ({len(tris)} triangles)")


if __name__ == "__main__":
    main()

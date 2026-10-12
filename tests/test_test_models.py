import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ttm", ROOT / "files/calibration/make-test-models.py")
ttm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ttm)


def bbox(tris):
    pts = [p for t in tris for p in t]
    return [(round(min(c), 3), round(max(c), 3)) for c in zip(*pts)]


def outward(tris, centres):
    """Every facet normal points away from the nearest solid's axis/centre."""
    for t in tris:
        n = ttm.normal(t)
        c = [sum(p[i] for p in t) / 3 for i in range(3)]
        ox, oy, oz = min(centres, key=lambda o: (o[0] - c[0]) ** 2 + (o[1] - c[1]) ** 2)
        if abs(n[2]) > 0.5:
            assert (n[2] > 0) == (c[2] > oz)
        else:
            assert n[0] * (c[0] - ox) + n[1] * (c[1] - oy) > 0


def test_retraction_default_geometry():
    tris = ttm.retraction()
    assert bbox(tris) == [(0, 70), (0, 10), (0, 40)]
    outward(tris, [(5, 5, 20), (65, 5, 20)])


def test_adhesion_dice_five_on_220_bed():
    tris = ttm.adhesion()
    assert bbox(tris) == [(17.5, 202.5), (17.5, 202.5), (0, 0.4)]
    outward(tris, [(30, 30, 0.2), (190, 30, 0.2), (110, 110, 0.2), (30, 190, 0.2), (190, 190, 0.2)])


def test_shipped_stls_match_the_generator():
    for name, tris in (("retraction", ttm.retraction()), ("adhesion", ttm.adhesion())):
        f = {"retraction": "retraction_towers.stl", "adhesion": "adhesion_dice5.stl"}[name]
        assert (ROOT / "files/calibration" / f).read_text() == ttm.stl(name, tris)

"""Regression tests for the astronomy maths. Run with `pytest tools/`.

The golden circumstances below are what `eclipse.py` itself prints, not what the
reference app publishes: `eclipse.py` uses K_MOON = 1737.4 km against the shipped
JavaScript's 1738.09 km, a deliberate difference documented in README.md, so the
two are near-but-not-equal by design. These tests pin this engine's own output.
"""
import math
import os
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import eclipse as E                      # noqa: E402
import build_site                        # noqa: E402  (pure string logic, no ephem)
from build_data import obsc              # noqa: E402  (the vectorised twin)


# --------------------------------------------------------------- golden case
LAT, LON = 43.38, -8.41                  # A Coruña, as in eclipse.py's __main__
T0 = datetime(2026, 8, 12, 16, 30, tzinfo=timezone.utc)
T1 = datetime(2026, 8, 12, 20, 0, tzinfo=timezone.utc)

GOLDEN = {                               # UTC; __main__ prints these shifted +2h as CEST
    "c1":  datetime(2026, 8, 12, 17, 30, 51, 564174, tzinfo=timezone.utc),
    "c2":  datetime(2026, 8, 12, 18, 27, 34, 808868, tzinfo=timezone.utc),
    "max": datetime(2026, 8, 12, 18, 28, 13, 678824, tzinfo=timezone.utc),
    "c3":  datetime(2026, 8, 12, 18, 28, 52, 342301, tzinfo=timezone.utc),
    "c4":  datetime(2026, 8, 12, 19, 21, 54, 186994, tzinfo=timezone.utc),
}
GOLDEN_DURATION_S = 77.53                # C3 - C2
GOLDEN_OBSC_PCT = 100.0
GOLDEN_ALT, GOLDEN_AZ = 12.04, 279.14    # apparent altitude, as in README.md


@pytest.fixture(scope="module")
def coruna():
    """The five contacts, solved exactly the way eclipse.py's __main__ solves them."""
    tmax = E.maximum(LAT, LON, T0, T1)
    limb = lambda c: c['s_sun'] + c['s_moon']          # noqa: E731
    inner = lambda c: abs(c['s_sun'] - c['s_moon'])    # noqa: E731
    return dict(max=tmax,
                cm=E.circumstances(LAT, LON, tmax),
                c1=E.solve(LAT, LON, T0, tmax, limb),
                c4=E.solve(LAT, LON, tmax, T1, limb),
                c2=E.solve(LAT, LON, T0, tmax, inner),
                c3=E.solve(LAT, LON, tmax, T1, inner))


@pytest.mark.parametrize("key", ["c1", "c2", "max", "c3", "c4"])
def test_contact_times(coruna, key):
    got = coruna[key]
    assert got is not None, f"{key} not found — solve() lost a contact"
    assert abs((got - GOLDEN[key]).total_seconds()) <= 2.0


def test_totality_duration(coruna):
    assert (coruna["c3"] - coruna["c2"]).total_seconds() == pytest.approx(
        GOLDEN_DURATION_S, abs=1.0)


def test_max_obscuration(coruna):
    cm = coruna["cm"]
    pct = E.obscuration(cm['sep'], cm['s_sun'], cm['s_moon']) * 100
    assert pct == pytest.approx(GOLDEN_OBSC_PCT, abs=0.2)


def test_max_alt_az(coruna):
    assert coruna["cm"]['alt'] == pytest.approx(GOLDEN_ALT, abs=0.01)
    assert coruna["cm"]['az'] == pytest.approx(GOLDEN_AZ, abs=0.01)


# ------------------------------------------------------------- obscuration()
SUN, MOON = 0.263, 0.272                 # typical semidiameters at 2026 maximum


def test_obscuration_discs_apart():
    assert E.obscuration(SUN + MOON, SUN, MOON) == 0.0      # exactly at external tangency
    assert E.obscuration(0.6, SUN, MOON) == 0.0


def test_obscuration_total():
    assert E.obscuration(0.0, SUN, MOON) == 1.0
    assert E.obscuration(MOON - SUN, SUN, MOON) == 1.0      # exactly at internal tangency


def test_obscuration_annular_interior():
    s1, s2 = 0.270, 0.250                                   # Moon the smaller disc
    assert E.obscuration(0.0, s1, s2) == pytest.approx((s2 / s1) ** 2)
    assert E.obscuration(s1 - s2, s1, s2) == pytest.approx((s2 / s1) ** 2)


LENSES = [(0.40, 0.263, 0.272), (0.30, 0.270, 0.250),
          (0.15, 0.263, 0.2722), (0.48, 0.263, 0.272)]


def _monte_carlo(sep, s1, s2, n=4_000_000, seed=20260812):
    """Fraction of uniform samples on the solar disc that land on the lunar disc."""
    rng = np.random.default_rng(seed)
    r = s1 * np.sqrt(rng.random(n))
    th = 2 * math.pi * rng.random(n)
    x, y = r * np.cos(th) - sep, r * np.sin(th)
    return np.count_nonzero(x * x + y * y <= s2 * s2) / n


@pytest.mark.parametrize("sep,s1,s2", LENSES)
def test_obscuration_matches_sampled_area(sep, s1, s2):
    assert E.obscuration(sep, s1, s2) == pytest.approx(
        _monte_carlo(sep, s1, s2), abs=1e-3)


@pytest.mark.parametrize("sep,a,b", LENSES)
def test_obscuration_lens_area_symmetric(sep, a, b):
    """The overlap area is symmetric in the two radii; only the normaliser is not."""
    assert (E.obscuration(sep, a, b) * a * a ==
            pytest.approx(E.obscuration(sep, b, a) * b * b, rel=1e-12))


# ----------------------------------------------------------------- refract()
def _bennett(h_app):
    """Bennett (1982) apparent -> true refraction, degrees. The inverse relation."""
    return (1.0 / math.tan(math.radians(h_app + 7.31 / (h_app + 4.4)))) / 60.0


def test_refract_is_saemundsson():
    want = 45 + 1.02 / math.tan(math.radians(45 + 10.3 / 50.11)) / 60
    assert abs(E.refract(45) - want) * 60 < 0.02


def test_refract_at_horizon_is_not_bennett():
    """At 45 deg the two formulas differ by only 0.018', so pin the horizon instead:
    Saemundsson lifts a geometric 0 deg by 28.98', Bennett misfed by 34.48'."""
    assert E.refract(0.0) * 60 == pytest.approx(28.98, abs=0.01)


@pytest.mark.parametrize("h", [-0.5, 0.0, 5.0, 45.0])
def test_refract_inverts_bennett(h):
    """Saemundsson geometric->apparent, undone by Bennett apparent->true."""
    h_app = E.refract(h)
    assert abs((h_app - _bennett(h_app)) - h) * 60 < 0.15


def test_refract_saturates_below_clamp():
    """The series turns over near -2 deg, so refraction is held flat below it."""
    at_clamp = E.refract(-2.0) + 2.0
    assert E.refract(-5.0) + 5.0 == pytest.approx(at_clamp)
    assert 0 < at_clamp * 60 < 60


def test_refract_decreases_with_altitude():
    # Stops at 85 deg: above about 89.9 the series' own argument passes 90, so the
    # tangent flips sign and the lift goes negative by ~0.1", which nothing here sees.
    lift = [(E.refract(h) - h) * 60 for h in (0, 1, 5, 20, 45, 85)]
    assert all(a > b > 0 for a, b in zip(lift, lift[1:]))


# -------------------------------------------------------------------- solve()
def _linear_sep(root):
    """Stand-in circumstances() whose separation crosses zero exactly at `root`."""
    return lambda lat, lon, t, elev=0.0: {"sep": (t - root).total_seconds()}


@pytest.mark.parametrize("span", [70, 80])
def test_solve_scans_trailing_partial_step(monkeypatch, span):
    """A bracket that is not a whole number of steps must still have its tail scanned.

    With step=20 the whole steps of a 70 s bracket stop at 60 s, so a root at 65 s
    is only reachable if the bracket end is appended as a final sample. span=80 is
    the exact-multiple control.
    """
    t0 = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
    root = t0 + timedelta(seconds=65)
    monkeypatch.setattr(E, "circumstances", _linear_sep(root))
    got = E.solve(0.0, 0.0, t0, t0 + timedelta(seconds=span), lambda c: 0.0, step=20)
    assert got is not None, "root in the trailing partial step was never scanned"
    assert abs((got - root).total_seconds()) <= 1e-6      # datetime resolution is 1 us


def test_solve_returns_none_without_a_root(monkeypatch):
    t0 = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(E, "circumstances", _linear_sep(t0 + timedelta(seconds=500)))
    assert E.solve(0.0, 0.0, t0, t0 + timedelta(seconds=70), lambda c: 0.0, step=20) is None


# ------------------------------------------- scalar engine vs vectorised twin
def _triples(n=25, seed=12345):
    """Random (sep, s1, s2) covering all three branches: contained, lens, apart."""
    rng = np.random.default_rng(seed)
    s1 = rng.uniform(0.262, 0.280, 4 * n)
    s2 = rng.uniform(0.245, 0.281, 4 * n)
    gap, tot = np.abs(s1 - s2), s1 + s2
    u = rng.uniform(0.0, 1.0, 4 * n)
    sep = np.concatenate([
        u[:n] * gap[:n],                                        # contained
        gap[n:2 * n] + u[n:2 * n] * (tot - gap)[n:2 * n],        # lens
        tot[2 * n:3 * n] * (1.0 + 0.4 * u[2 * n:3 * n]),         # apart
        0.6 * u[3 * n:],                                        # unconstrained
    ])
    return sep, s1, s2


def test_scalar_and_vectorised_obscuration_agree():
    sep, s1, s2 = _triples()
    apart, contained = sep >= s1 + s2, sep <= np.abs(s1 - s2)
    assert apart.any() and contained.any() and (~apart & ~contained).any()
    got = obsc(sep, s1, s2)
    for i in range(len(sep)):
        assert got[i] == pytest.approx(E.obscuration(sep[i], s1[i], s2[i]),
                                       abs=1e-9, rel=0), f"triple {i}"


# ------------------------------------------------- build_site.inject escaping
LS, PS = chr(0x2028), chr(0x2029)        # ES line terminators, invisible if spelled literally


def test_inject_neutralises_script_close_and_line_separators(tmp_path):
    """A bundle is spliced into a <script> body, so these three must not survive raw."""
    tpl = tmp_path / "tpl.html"
    tpl.write_text("BEGIN__BUNDLE__END", encoding="utf-8")
    bundle = tmp_path / "bundle.json"
    bundle.write_text('{"a":"</script><img>","b":"x' + LS + 'y' + PS + 'z"}',
                      encoding="utf-8")
    out = tmp_path / "out.html"

    build_site.inject(str(tpl), str(bundle), str(out))
    got = out.read_text(encoding="utf-8")

    assert got.startswith("BEGIN") and got.endswith("END")
    assert "</" not in got                   # any "</" would end the script element early
    assert "<\\/script>" in got
    assert LS not in got and PS not in got
    assert "\\u2028" in got and "\\u2029" in got


def test_inject_requires_placeholder(tmp_path):
    tpl = tmp_path / "tpl.html"
    tpl.write_text("no placeholder here", encoding="utf-8")
    bundle = tmp_path / "bundle.json"
    bundle.write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit):
        build_site.inject(str(tpl), str(bundle), str(tmp_path / "out.html"))

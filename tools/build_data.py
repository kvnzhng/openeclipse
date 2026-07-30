"""Function library for build_data2.py — the first-generation bundle builder.

build_data2.py imports the helpers below (ephem_row, sep_grid, obsc, simplify,
FLAT) and builds the shipped bundle itself, with continental bounds and a
signed-clearance band field. Nothing here builds a shippable bundle any more:
the Iberia-only layout this file was written for predates the current template
(no `band` field, different grid), so running it would only produce data the
simulator cannot read. It is kept because it is where those helpers live, and
because the constants at the top are the ones the JavaScript is matched to.
"""
import json, math
import numpy as np
import ephem
from datetime import datetime, timedelta, timezone

R_E = 6378.137
AU_ER = 149597870.7 / R_E
K_SUN, K_MOON = 696000.0, 1738.09      # 1738.09 km = IAU k=0.2725076
FLAT = 0.99664719

EVENTS = {
    "2026": dict(date=(2026, 8, 12), t0=(16, 0), t1=(20, 30), tz=2,  tzn="CEST",
                 kind="total",   label="12 August 2026"),
    "2027": dict(date=(2027, 8, 2),  t0=(6, 30), t1=(11, 30), tz=2,  tzn="CEST",
                 kind="total",   label="2 August 2027"),
    "2028": dict(date=(2028, 1, 26), t0=(14, 30), t1=(18, 45), tz=1, tzn="CET",
                 kind="annular", label="26 January 2028"),
}
STEP_MIN = 2                      # ephemeris table step
LON0, LON1, DLON = -13.0, 9.0, 0.2
LAT0, LAT1, DLAT = 26.0, 49.0, 0.2


def ephem_row(dt):
    s, m = ephem.Sun(), ephem.Moon()
    s.compute(ephem.Date(dt)); m.compute(ephem.Date(dt))
    o = ephem.Observer(); o.lat = 0; o.lon = 0; o.date = ephem.Date(dt)
    gast = float(o.sidereal_time())           # apparent sidereal time at Greenwich
    return [round(math.degrees(float(s.g_ra)), 7), round(math.degrees(float(s.g_dec)), 7),
            round(float(s.earth_distance) * AU_ER, 3),
            round(math.degrees(float(m.g_ra)), 7), round(math.degrees(float(m.g_dec)), 7),
            round(float(m.earth_distance) * AU_ER, 5),
            round(math.degrees(gast), 7)]


def build_table(ev):
    y, mo, d = ev["date"]
    t0 = datetime(y, mo, d, *ev["t0"], tzinfo=timezone.utc)
    t1 = datetime(y, mo, d, *ev["t1"], tzinfo=timezone.utc)
    n = int((t1 - t0).total_seconds() // 60 // STEP_MIN) + 1
    rows = [ephem_row(t0 + timedelta(minutes=STEP_MIN * i)) for i in range(n)]
    return t0, rows


def unwrap_ra(rows):
    """Keep RA continuous so interpolation doesn't jump across 360."""
    for col in (0, 3):
        for i in range(1, len(rows)):
            while rows[i][col] - rows[i - 1][col] > 180:  rows[i][col] -= 360
            while rows[i][col] - rows[i - 1][col] < -180: rows[i][col] += 360
    for i in range(1, len(rows)):
        while rows[i][6] - rows[i - 1][6] < 0: rows[i][6] += 360
    return rows


# ---------- vectorised separation over a lat/lon grid ----------
def sep_grid(row, LATg, LONg, rc, rs):
    sra, sdec, sr, mra, mdec, mr, gast = row
    lst = np.radians(gast + LONg)
    ox = rc * np.cos(lst); oy = rc * np.sin(lst); oz = rs

    def topo(ra, dec, r):
        ra, dec = math.radians(ra), math.radians(dec)
        x = r * math.cos(dec) * math.cos(ra) - ox
        y = r * math.cos(dec) * math.sin(ra) - oy
        z = r * math.sin(dec) - oz
        d = np.sqrt(x * x + y * y + z * z)
        return x / d, y / d, z / d, d

    sx, sy, sz, sd = topo(sra, sdec, sr)
    mx, my, mz, md = topo(mra, mdec, mr)
    cos = np.clip(sx * mx + sy * my + sz * mz, -1, 1)
    sep = np.degrees(np.arccos(cos))
    s1 = np.degrees(np.arcsin(K_SUN / (sd * R_E)))
    s2 = np.degrees(np.arcsin(K_MOON / (md * R_E)))
    return sep, s1, s2


def obsc(sep, s1, s2):
    out = np.zeros_like(sep)
    total = sep <= np.abs(s1 - s2)
    out[total] = np.where(s2[total] >= s1[total], 1.0, (s2[total] ** 2) / (s1[total] ** 2))
    part = (sep < s1 + s2) & (~total)
    a, b, c = s1[part], s2[part], sep[part]
    t1 = np.arccos(np.clip((a * a + c * c - b * b) / (2 * a * c), -1, 1))
    t2 = np.arccos(np.clip((b * b + c * c - a * a) / (2 * b * c), -1, 1))
    out[part] = ((a * a * (t1 - np.sin(2 * t1) / 2) +
                  b * b * (t2 - np.sin(2 * t2) / 2)) / (math.pi * a * a))
    return np.clip(out, 0, 1)


def central_line(ev, step_s=15):
    """Where the shadow axis meets the ellipsoid, sampled finely."""
    y, mo, d = ev["date"]
    t0 = datetime(y, mo, d, *ev["t0"], tzinfo=timezone.utc)
    t1 = datetime(y, mo, d, *ev["t1"], tzinfo=timezone.utc)
    n = int((t1 - t0).total_seconds() // step_s)
    pts = []
    for i in range(n + 1):
        t = t0 + timedelta(seconds=i * step_s)
        sra, sdec, sr, mra, mdec, mr, gast = ephem_row(t)
        S = np.array([sr * math.cos(math.radians(sdec)) * math.cos(math.radians(sra)),
                      sr * math.cos(math.radians(sdec)) * math.sin(math.radians(sra)),
                      sr * math.sin(math.radians(sdec))])
        M = np.array([mr * math.cos(math.radians(mdec)) * math.cos(math.radians(mra)),
                      mr * math.cos(math.radians(mdec)) * math.sin(math.radians(mra)),
                      mr * math.sin(math.radians(mdec))])
        u = M - S; u /= np.linalg.norm(u)
        sq = np.array([1.0, 1.0, 1.0 / FLAT])
        Ms, us = M * sq, u * sq
        A = us @ us; B = 2 * Ms @ us; C = Ms @ Ms - 1
        disc = B * B - 4 * A * C
        if disc < 0:
            continue
        tt = (-B - math.sqrt(disc)) / (2 * A)
        P = (Ms + tt * us) / sq
        lat = math.degrees(math.atan2(P[2] / (FLAT ** 2), math.hypot(P[0], P[1])))
        lon = (math.degrees(math.atan2(P[1], P[0])) - gast + 540) % 360 - 180
        if LON0 - 2 < lon < LON1 + 2 and LAT0 - 2 < lat < LAT1 + 2:
            pts.append([round(lon, 3), round(lat, 3),
                        (t + timedelta(hours=ev["tz"])).strftime("%H:%M")])
    return pts


# ---------- coastlines ----------
def _rdp(p, eps):
    """Iterative Douglas-Peucker on an open polyline."""
    if len(p) < 3:
        return p
    keep = [False] * len(p)
    keep[0] = keep[-1] = True
    stack = [(0, len(p) - 1)]
    while stack:
        i0, i1 = stack.pop()
        x0, y0 = p[i0]; x1, y1 = p[i1]
        dx, dy = x1 - x0, y1 - y0
        n = math.hypot(dx, dy)
        dmax, idx = -1.0, -1
        for i in range(i0 + 1, i1):
            if n < 1e-12:
                d = math.hypot(p[i][0] - x0, p[i][1] - y0)
            else:
                d = abs(dy * (p[i][0] - x0) - dx * (p[i][1] - y0)) / n
            if d > dmax:
                dmax, idx = d, i
        if idx > 0 and dmax > eps:
            keep[idx] = True
            stack.append((i0, idx)); stack.append((idx, i1))
    return [p[i] for i in range(len(p)) if keep[i]]


def simplify(pts, eps):
    """Simplify a closed ring by splitting it at its most distant point first."""
    if len(pts) < 4:
        return pts
    ring = pts[:-1] if pts[0] == pts[-1] else pts[:]
    if len(ring) < 4:
        return pts
    x0, y0 = ring[0]
    far = max(range(len(ring)), key=lambda i: (ring[i][0] - x0) ** 2 + (ring[i][1] - y0) ** 2)
    a = _rdp(ring[:far + 1], eps)
    b = _rdp(ring[far:] + [ring[0]], eps)
    out = a[:-1] + b
    return out


def coastlines():
    gj = json.load(open("ne50.geojson"))
    keep = {"Spain", "Portugal", "Morocco", "France", "Algeria", "Andorra",
            "Gibraltar", "W. Sahara", "Italy", "Tunisia", "United Kingdom",
            "Ireland", "Belgium", "Netherlands", "Switzerland", "Germany", "Luxembourg"}
    out = []
    for f in gj["features"]:
        if f["properties"].get("NAME") not in keep:
            continue
        geom = f["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        for poly in polys:
            ring = poly[0]
            xs = [p[0] for p in ring]; ys = [p[1] for p in ring]
            if max(xs) < LON0 - 2 or min(xs) > LON1 + 2 or max(ys) < LAT0 - 2 or min(ys) > LAT1 + 2:
                continue
            s = simplify([[round(p[0], 3), round(p[1], 3)] for p in ring], 0.04)
            if len(s) > 3:
                out.append(s)
    return out


if __name__ == '__main__':
    raise SystemExit(
        "build_data.py is a function library now — it no longer builds a bundle the\n"
        "template can read (Iberia-only grid, no band field). Build the shipped data with:\n"
        "    python3 build_data2.py        # -> bundle.json\n"
        "or the whole site in one go with:\n"
        "    python3 build_site.py all    # fetch -> build -> inject")

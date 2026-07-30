"""Data bundle v2: continental obscuration field + signed-clearance band field.

Run it directly (or via `build_site.py build`) to write bundle.json. The band
field is a parabola-refined minimum of sep-|s1-s2| per grid cell, which is what
replaced the earlier march-perpendicular-to-the-centre-line path tracing.
"""
import json, math, base64, os
import numpy as np
from datetime import datetime, timedelta, timezone

from build_data import ephem_row, sep_grid, obsc, simplify, FLAT

EVENTS = {
    "2026": dict(date=(2026, 8, 12), t0=(15, 0), t1=(21, 0),  tz=2, tzn="CEST",
                 kind="total",   label="12 August 2026"),
    "2027": dict(date=(2027, 8, 2),  t0=(7, 0),  t1=(12, 0),  tz=2, tzn="CEST",
                 kind="total",   label="2 August 2027"),
    "2028": dict(date=(2028, 1, 26), t0=(14, 0), t1=(19, 30), tz=1, tzn="CET",
                 kind="annular", label="26 January 2028"),
}
STEP_MIN = 2
LON0, LON1, DLON = -30.0, 45.0, 0.3
LAT0, LAT1, DLAT = 10.0, 70.0, 0.3


def build_table(ev):
    y, mo, d = ev["date"]
    t0 = datetime(y, mo, d, *ev["t0"], tzinfo=timezone.utc)
    t1 = datetime(y, mo, d, *ev["t1"], tzinfo=timezone.utc)
    n = int((t1 - t0).total_seconds() // 60 // STEP_MIN) + 1
    rows = [ephem_row(t0 + timedelta(minutes=STEP_MIN * i)) for i in range(n)]
    for col in (0, 3):
        for i in range(1, len(rows)):
            while rows[i][col] - rows[i - 1][col] > 180:  rows[i][col] -= 360
            while rows[i][col] - rows[i - 1][col] < -180: rows[i][col] += 360
    for i in range(1, len(rows)):
        while rows[i][6] - rows[i - 1][6] < 0: rows[i][6] += 360
    return t0, rows


def shadow_axis(row):
    """Sub-shadow point on the ellipsoid, or None if the axis misses Earth."""
    sra, sdec, sr, mra, mdec, mr, gast = row
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
    if disc >= 0:
        t = (-B - math.sqrt(disc)) / (2 * A)
        Q = Ms + t * us
    else:
        # axis misses the globe: follow the shadow onto the limb, which is
        # where the sunset end of the path actually lives
        Q = Ms + (-B / (2 * A)) * us
        r = np.linalg.norm(Q)
        if r > 1.25:
            return None
        Q = Q / r
    P = Q / sq
    lat = math.degrees(math.atan2(P[2] / (FLAT ** 2), math.hypot(P[0], P[1])))
    lon = (math.degrees(math.atan2(P[1], P[0])) - gast + 540) % 360 - 180
    return lon, lat


def central_line(ev, step_s=30):
    y, mo, d = ev["date"]
    t0 = datetime(y, mo, d, *ev["t0"], tzinfo=timezone.utc)
    t1 = datetime(y, mo, d, *ev["t1"], tzinfo=timezone.utc)
    n = int((t1 - t0).total_seconds() // step_s)
    pts = []
    for i in range(n + 1):
        t = t0 + timedelta(seconds=i * step_s)
        p = shadow_axis(ephem_row(t))
        if p is None:
            continue
        lon, lat = p
        if LON0 - 4 < lon < LON1 + 4 and LAT0 - 4 < lat < LAT1 + 4:
            pts.append([round(lon, 3), round(lat, 3),
                        round((t - t0).total_seconds() / 60 + t0.hour * 60 + t0.minute, 2), i])
    return pts


def coastlines():
    gj = json.load(open("ne50.geojson"))
    keep = {
        "Spain","Portugal","Morocco","France","Algeria","Andorra","Gibraltar","W. Sahara",
        "Italy","Tunisia","United Kingdom","Ireland","Belgium","Netherlands","Switzerland",
        "Germany","Luxembourg","Denmark","Norway","Sweden","Finland","Poland","Czechia",
        "Austria","Slovakia","Hungary","Slovenia","Croatia","Bosnia and Herz.","Serbia",
        "Montenegro","Albania","North Macedonia","Greece","Bulgaria","Romania","Moldova",
        "Ukraine","Belarus","Lithuania","Latvia","Estonia","Iceland","Libya","Egypt",
        "Mauritania","Mali","Niger","Chad","Sudan","Turkey","Syria","Lebanon","Israel",
        "Jordan","Iraq","Saudi Arabia","Cyprus","Malta","Senegal","Guinea","Nigeria",
        "Russia","Kazakhstan","Georgia","Armenia","Azerbaijan","Iran","Kuwait",
        "Burkina Faso","Benin","Ghana","Togo","Côte d'Ivoire","Cameroon","Gambia",
        "Guinea-Bissau","Sierra Leone","Liberia","Eritrea","Ethiopia","Greenland",
    }
    out = []
    for f in gj["features"]:
        if f["properties"].get("NAME") not in keep:
            continue
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for poly in polys:
            ring = poly[0]
            xs = [p[0] for p in ring]; ys = [p[1] for p in ring]
            if max(xs) < LON0 - 3 or min(xs) > LON1 + 3 or max(ys) < LAT0 - 3 or min(ys) > LAT1 + 3:
                continue
            s = simplify([[round(p[0], 3), round(p[1], 3)] for p in ring], 0.05)
            if len(s) > 3:
                out.append(s)
    return out


def main(out="bundle.json"):
    lons = np.arange(LON0, LON1 + 1e-9, DLON)
    lats = np.arange(LAT0, LAT1 + 1e-9, DLAT)
    LONg, LATg = np.meshgrid(lons, lats)
    phi = np.radians(LATg)
    uu = np.arctan(FLAT * np.tan(phi))
    RC = np.cos(uu); RS = FLAT * np.sin(uu)

    bundle = {"grid": {"lon0": LON0, "lat0": LAT0, "dlon": DLON, "dlat": DLAT,
                       "nx": len(lons), "ny": len(lats)},
              "coast": coastlines(), "events": {}}
    print("coast rings:", len(bundle["coast"]), "pts:", sum(len(r) for r in bundle["coast"]))

    for key, ev in EVENTS.items():
        t0, rows = build_table(ev)
        fine = []
        for i in range(len(rows) - 1):
            fine.append(rows[i])
            fine.append(list((np.array(rows[i]) + np.array(rows[i + 1])) / 2))
        fine.append(rows[-1])

        O = np.zeros(LONg.shape)
        # g = sep - |s1-s2|; g<=0 means a total/annular phase. Track the running
        # minimum with its neighbours so it can be refined by a parabola fit,
        # which resolves a totality far shorter than the sampling interval.
        BIG = 1e9
        best = np.full(LONg.shape, BIG)
        bm1 = np.zeros(LONg.shape); bp1 = np.zeros(LONg.shape)
        gpp = gp = None
        for r in fine:
            sep, s1, s2 = sep_grid(r, LATg, LONg, RC, RS)
            O = np.maximum(O, obsc(sep, s1, s2))
            g = sep - np.abs(s1 - s2)
            if gp is not None and gpp is not None:
                m = gp < best
                best[m] = gp[m]; bm1[m] = gpp[m]; bp1[m] = g[m]
            gpp, gp = gp, g
        den = bp1 - 2 * best + bm1
        refined = np.where(den > 1e-12, best - (bp1 - bm1) ** 2 / (8 * den), best)
        refined = np.minimum(best, refined)

        def central_here(lo, la):
            j = int(round((lo - LON0) / DLON)); i = int(round((la - LAT0) / DLAT))
            if not (0 <= i < refined.shape[0] and 0 <= j < refined.shape[1]):
                return False
            return refined[i, j] <= 0
        line = [[lo, la, tm] for lo, la, tm, _ in central_line(ev) if central_here(lo, la)]

        # signed clearance, 0.01 arcmin per step, centred on 128 -> smooth band edge
        gq = np.clip(np.round(128 + refined * 6000), 0, 255).astype(np.uint8)

        bundle["events"][key] = {
            "label": ev["label"], "kind": ev["kind"], "tz": ev["tz"], "tzn": ev["tzn"],
            "date": list(ev["date"]), "t0": t0.strftime("%H:%M"), "stepMin": STEP_MIN,
            "eph": rows, "line": line,
            "obsc": base64.b64encode(np.round(O * 254).astype(np.uint8).tobytes()).decode(),
            "band": base64.b64encode(gq.tobytes()).decode(),
        }
        print(f"{key}: eph {len(rows)}, centre {len(line)}, "
              f"band cells {int((refined<=0).sum())}, peak obsc {O.max()*100:.2f}%")

    json.dump(bundle, open(out, "w"), separators=(",", ":"))
    print(f"{out}:", os.path.getsize(out) // 1024, "KB")


if __name__ == "__main__":
    main()

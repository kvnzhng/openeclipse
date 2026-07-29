"""Eclipse circumstance engine.

Geocentric apparent positions come from ephem; the observer-dependent part
(topocentric parallax, separation, obscuration, contact times) is implemented
here so the exact same maths can be ported to JavaScript.
"""
import math
import ephem
from datetime import datetime, timedelta, timezone

R_EARTH_KM = 6378.137
AU_IN_ER = 149597870.7 / R_EARTH_KM      # AU expressed in equatorial Earth radii
K_MOON = 1737.4                           # lunar radius, km
K_SUN = 696000.0                          # solar radius, km
FLAT = 0.99664719                         # b/a for WGS84


def geocentric(body_cls, dt):
    """Apparent geocentric RA/Dec (radians) and distance in Earth radii."""
    b = body_cls()
    b.compute(ephem.Date(dt))
    return float(b.g_ra), float(b.g_dec), float(b.earth_distance) * AU_IN_ER


def observer_vector(lat_deg, lon_deg, elev_m, dt):
    """Observer geocentric rectangular vector in Earth radii, true equinox of date."""
    obs = ephem.Observer()
    obs.lat = math.radians(lat_deg)
    obs.lon = math.radians(lon_deg)
    obs.elevation = elev_m
    obs.date = ephem.Date(dt)
    lst = float(obs.sidereal_time())          # apparent local sidereal time, rad

    phi = math.radians(lat_deg)
    u = math.atan(FLAT * math.tan(phi))
    h = elev_m / (R_EARTH_KM * 1000.0)
    rho_sin = FLAT * math.sin(u) + h * math.sin(phi)
    rho_cos = math.cos(u) + h * math.cos(phi)
    return (rho_cos * math.cos(lst), rho_cos * math.sin(lst), rho_sin), lst


def to_vec(ra, dec, r):
    return (r * math.cos(dec) * math.cos(ra),
            r * math.cos(dec) * math.sin(ra),
            r * math.sin(dec))


def topo(ra, dec, r, ov):
    """Topocentric direction and distance, given geocentric position + observer vector."""
    x, y, z = to_vec(ra, dec, r)
    tx, ty, tz = x - ov[0], y - ov[1], z - ov[2]
    d = math.sqrt(tx * tx + ty * ty + tz * tz)
    return math.atan2(ty, tx), math.asin(tz / d), d


def refract(h):
    """Bennett (1982): geometric altitude -> apparent altitude, both degrees.

    Below about -2 deg the series turns over and blows up at -4.4, so the
    argument is clamped; refraction saturates rather than misbehaving. Applied
    to altitude only, never to the separation the contacts are solved on: Sun
    and Moon sit within half a degree of each other and refract almost alike.
    """
    hc = max(h, -2.0)
    return h + (1.0 / math.tan(math.radians(hc + 7.31 / (hc + 4.4)))) / 60.0


def circumstances(lat, lon, dt, elev=0.0):
    """Separation, semidiameters (all degrees), plus sun alt/az."""
    sra, sdec, sr = geocentric(ephem.Sun, dt)
    mra, mdec, mr = geocentric(ephem.Moon, dt)
    ov, lst = observer_vector(lat, lon, elev, dt)

    sra_t, sdec_t, sd_t = topo(sra, sdec, sr, ov)
    mra_t, mdec_t, md_t = topo(mra, mdec, mr, ov)

    # angular separation of centres
    cos_sep = (math.sin(sdec_t) * math.sin(mdec_t) +
               math.cos(sdec_t) * math.cos(mdec_t) * math.cos(sra_t - mra_t))
    sep = math.degrees(math.acos(max(-1.0, min(1.0, cos_sep))))

    s_sun = math.degrees(math.asin(K_SUN / (sd_t * R_EARTH_KM)))
    s_moon = math.degrees(math.asin(K_MOON / (md_t * R_EARTH_KM)))

    # sun altitude / azimuth
    ha = lst - sra_t
    alt = math.asin(math.sin(sdec_t) * math.sin(math.radians(lat)) +
                    math.cos(sdec_t) * math.cos(math.radians(lat)) * math.cos(ha))
    az = math.atan2(-math.sin(ha) * math.cos(sdec_t),
                    math.cos(math.radians(lat)) * math.sin(sdec_t) -
                    math.sin(math.radians(lat)) * math.cos(sdec_t) * math.cos(ha))
    return dict(sep=sep, s_sun=s_sun, s_moon=s_moon,
                alt=refract(math.degrees(alt)), az=(math.degrees(az) + 360) % 360)


def obscuration(sep, s1, s2):
    """Fraction of the solar disc area covered."""
    if sep >= s1 + s2:
        return 0.0
    if sep <= abs(s1 - s2):
        return 1.0 if s2 >= s1 else (s2 * s2) / (s1 * s1)
    a, b, c = s1, s2, sep
    cos1 = (a * a + c * c - b * b) / (2 * a * c)
    cos2 = (b * b + c * c - a * a) / (2 * b * c)
    t1 = math.acos(max(-1, min(1, cos1)))
    t2 = math.acos(max(-1, min(1, cos2)))
    area = (a * a * (t1 - math.sin(2 * t1) / 2) +
            b * b * (t2 - math.sin(2 * t2) / 2))
    return area / (math.pi * a * a)


def solve(lat, lon, t0, t1, target, elev=0.0, step=20):
    """Bisection on f(t)=sep-target(sep,s1,s2) sign change between t0 and t1."""
    def f(t):
        c = circumstances(lat, lon, t, elev)
        return c['sep'] - target(c)
    n = int((t1 - t0).total_seconds() // step)
    prev_t, prev_v = t0, f(t0)
    for i in range(1, n + 1):
        t = t0 + timedelta(seconds=i * step)
        v = f(t)
        if prev_v == 0:
            return prev_t
        if prev_v * v < 0:
            lo, hi = prev_t, t
            for _ in range(40):
                mid = lo + (hi - lo) / 2
                if f(lo) * f(mid) <= 0:
                    hi = mid
                else:
                    lo = mid
            return lo + (hi - lo) / 2
        prev_t, prev_v = t, v
    return None


def maximum(lat, lon, t0, t1, elev=0.0):
    """Golden-section search for minimum separation."""
    gr = (math.sqrt(5) - 1) / 2
    a, b = t0, t1
    for _ in range(60):
        c = b - (b - a) * gr
        d = a + (b - a) * gr
        if circumstances(lat, lon, c, elev)['sep'] < circumstances(lat, lon, d, elev)['sep']:
            b = d
        else:
            a = c
    return a + (b - a) / 2


if __name__ == "__main__":
    LAT, LON = 43.38, -8.41          # Paseo Marítimo - As Lagoas, from the screenshot
    t0 = datetime(2026, 8, 12, 16, 30, tzinfo=timezone.utc)
    t1 = datetime(2026, 8, 12, 20, 0, tzinfo=timezone.utc)

    def cest(t):
        return (t + timedelta(hours=2)).strftime("%H:%M:%S")

    tmax = maximum(LAT, LON, t0, t1)
    cm = circumstances(LAT, LON, tmax)

    c1 = solve(LAT, LON, t0, tmax, lambda c: c['s_sun'] + c['s_moon'])
    c4 = solve(LAT, LON, tmax, t1, lambda c: c['s_sun'] + c['s_moon'])
    c2 = solve(LAT, LON, t0, tmax, lambda c: abs(c['s_sun'] - c['s_moon']))
    c3 = solve(LAT, LON, tmax, t1, lambda c: abs(c['s_sun'] - c['s_moon']))

    print("=" * 62)
    print("VALIDATION  43.38, -8.41  ·  12 Aug 2026  ·  times CEST")
    print("=" * 62)
    rows = [("C1 first contact", c1, "19:30:48"),
            ("C2 totality begins", c2, "20:26:59"),
            ("Maximum", tmax, "20:27:39"),
            ("C3 totality ends", c3, "20:28:19"),
            ("C4 last contact", c4, "21:21:49")]
    for name, got, want in rows:
        if got is None:
            print(f"  {name:20s}   —")
            continue
        g = cest(got)
        gs = (got + timedelta(hours=2))
        ws = datetime.strptime(want, "%H:%M:%S")
        delta = (gs.hour*3600+gs.minute*60+gs.second) - (ws.hour*3600+ws.minute*60+ws.second)
        print(f"  {name:20s} {g}   app says {want}   Δ {delta:+d}s")

    if c2 and c3:
        print(f"\n  totality duration  {(c3-c2).total_seconds():.1f}s   app says 80s")
    print(f"  max obscuration    {obscuration(cm['sep'], cm['s_sun'], cm['s_moon'])*100:.1f}%")
    print(f"  sun altitude       {cm['alt']:.2f}°   azimuth {cm['az']:.1f}°")

    # 20:08:06 CEST is 18:08:06 UTC; the offset is already applied here
    t = datetime(2026, 8, 12, 18, 8, 6, tzinfo=timezone.utc)
    c = circumstances(LAT, LON, t)
    mag = (c['s_sun'] + c['s_moon'] - c['sep']) / (2 * c['s_sun'])
    print(f"\n  at 20:08:06 CEST → obsc {obscuration(c['sep'],c['s_sun'],c['s_moon'])*100:.2f}%"
          f"  mag {mag:.3f}   app says 57.44% / 0.654")

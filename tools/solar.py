"""NOAA solar position algorithm. Validate against IGN published figures, then
compute altitudes for the 2027 and 2028 eclipses."""
import math
from datetime import datetime, timezone

def julian_day(dt):
    y, m = dt.year, dt.month
    d = (dt.day + dt.hour/24 + dt.minute/1440 + dt.second/86400)
    if m <= 2:
        y -= 1; m += 12
    a = y // 100
    b = 2 - a + a // 4
    return int(365.25*(y+4716)) + int(30.6001*(m+1)) + d + b - 1524.5

def solar_altitude(lat, lon, dt_utc, refraction=True):
    jd = julian_day(dt_utc)
    t = (jd - 2451545.0) / 36525.0

    # geometric mean longitude / anomaly of the sun
    L0 = (280.46646 + t*(36000.76983 + t*0.0003032)) % 360
    M = 357.52911 + t*(35999.05029 - 0.0001537*t)
    Mr = math.radians(M)

    C = (math.sin(Mr)*(1.914602 - t*(0.004817 + 0.000014*t))
         + math.sin(2*Mr)*(0.019993 - 0.000101*t)
         + math.sin(3*Mr)*0.000289)
    true_long = L0 + C

    omega = 125.04 - 1934.136*t
    app_long = true_long - 0.00569 - 0.00478*math.sin(math.radians(omega))

    e0 = (23 + (26 + ((21.448 - t*(46.815 + t*(0.00059 - t*0.001813))))/60)/60)
    e_corr = e0 + 0.00256*math.cos(math.radians(omega))

    decl = math.degrees(math.asin(math.sin(math.radians(e_corr))
                                  * math.sin(math.radians(app_long))))

    # equation of time
    y = math.tan(math.radians(e_corr/2))**2
    eot = 4*math.degrees(
        y*math.sin(2*math.radians(L0))
        - 2*0.016708634*math.sin(Mr)
        + 4*0.016708634*y*math.sin(Mr)*math.cos(2*math.radians(L0))
        - 0.5*y*y*math.sin(4*math.radians(L0))
        - 1.25*0.016708634**2*math.sin(2*Mr))

    mins = dt_utc.hour*60 + dt_utc.minute + dt_utc.second/60
    true_solar_time = (mins + eot + 4*lon) % 1440
    ha = true_solar_time/4 - 180
    if ha < -180:
        ha += 360

    latr, declr, har = map(math.radians, (lat, decl, ha))
    zenith = math.degrees(math.acos(
        math.sin(latr)*math.sin(declr) + math.cos(latr)*math.cos(declr)*math.cos(har)))
    alt = 90 - zenith

    if refraction and alt > -1:
        # atmospheric refraction, arcmin -> deg
        if alt > 85:
            r = 0
        elif alt > 5:
            ta = math.tan(math.radians(alt))
            r = (58.1/ta - 0.07/ta**3 + 0.000086/ta**5)/3600
        elif alt > -0.575:
            r = (1735 + alt*(-518.2 + alt*(103.4 + alt*(-12.79 + alt*0.711))))/3600
        else:
            r = (-20.772/math.tan(math.radians(alt)))/3600
        alt += r

    # azimuth
    az = math.degrees(math.atan2(
        -math.sin(har),
        math.tan(declr)*math.cos(latr) - math.sin(latr)*math.cos(har)))
    az = (az + 360) % 360
    return alt, az


def U(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


print("=" * 68)
print("VALIDATION against Instituto Geografico Nacional published figures")
print("=" * 68)
# IGN: A Coruna max 20:28 CEST (=18:28 UTC), sun altitude 12 deg
# IGN: Palma    max 20:32 CEST (=18:32 UTC), sun altitude  2 deg
checks = [
    ("A Coruna 2026", 43.3623, -8.4115, U(2026, 8, 12, 18, 28), 12),
    ("Palma 2026",    39.5696,  2.6502, U(2026, 8, 12, 18, 32),  2),
]
for name, la, lo, dt, published in checks:
    alt, az = solar_altitude(la, lo, dt)
    print(f"{name:16s} computed {alt:5.1f} deg   published {published:2d} deg"
          f"   delta {alt-published:+.1f}   az {az:.0f} deg")


print()
print("=" * 68)
print("2026-08-12 TOTAL  — max eclipse, times interpolated W->E along path")
print("=" * 68)
# anchor: A Coruna 18:28 UTC (lon -8.41), Palma 18:32 UTC (lon 2.65)
def t2026(lon):
    frac = (lon - (-8.4115)) / (2.6502 - (-8.4115))
    return 18*60 + 28 + 4*frac

cities26 = [
    ("A Coruna",  43.3623, -8.4115), ("Oviedo", 43.3619, -5.8494),
    ("Leon",      42.5987, -5.5671), ("Burgos", 42.3439, -3.6969),
    ("Bilbao",    43.2630, -2.9350), ("Logrono", 42.4650, -2.4450),
    ("Zaragoza",  41.6488, -0.8891), ("Valencia", 39.4699, -0.3763),
    ("Palma",     39.5696,  2.6502),
]
for n, la, lo in cities26:
    m = t2026(lo)
    dt = U(2026, 8, 12, int(m//60), int(round(m % 60)))
    alt, az = solar_altitude(la, lo, dt)
    loc = (dt.hour + 2) % 24
    print(f"  {n:10s} {loc:02d}:{dt.minute:02d} CEST   alt {alt:5.1f} deg   az {az:3.0f} deg")

print()
print("=" * 68)
print("2027-08-02 TOTAL — morning, shadow over the Strait ~08:45-08:50 UTC")
print("=" * 68)
cities27 = [
    ("Cadiz",   36.5271, -6.2886, 45), ("Tarifa", 36.0143, -5.6044, 46),
    ("Malaga",  36.7213, -4.4214, 47), ("Ceuta",  35.8894, -5.3213, 46),
    ("Melilla", 35.2923, -2.9381, 48), ("Granada", 37.1773, -3.5986, 47),
    ("Tangier", 35.7595, -5.8340, 46),
]
for n, la, lo, mi in cities27:
    dt = U(2027, 8, 2, 8, mi)
    alt, az = solar_altitude(la, lo, dt)
    loc = (dt.hour + 2) % 24
    print(f"  {n:10s} {loc:02d}:{dt.minute:02d} CEST   alt {alt:5.1f} deg   az {az:3.0f} deg")

print()
print("=" * 68)
print("2028-01-26 ANNULAR — sunset, 17:52-18:00 CET SW->NE  (check: Cadiz ~7.8)")
print("=" * 68)
def t2028(lon):
    frac = (lon - (-5.9845)) / (2.8214 - (-5.9845))
    return 16*60 + 52 + 8*frac

cities28 = [
    ("Sevilla",  37.3891, -5.9845), ("Cadiz",   36.5271, -6.2886),
    ("Cordoba",  37.8882, -4.7794), ("Malaga",  36.7213, -4.4214),
    ("Granada",  37.1773, -3.5986), ("Albacete", 38.9943, -1.8585),
    ("Alicante", 38.3452, -0.4810), ("Valencia", 39.4699, -0.3763),
    ("Palma",    39.5696,  2.6502), ("Girona",  41.9794,  2.8214),
]
for n, la, lo in cities28:
    m = t2028(lo)
    from datetime import timedelta
    dt = U(2028,1,26,0,0) + timedelta(minutes=round(m))
    alt, az = solar_altitude(la, lo, dt)
    loc = dt.hour + 1
    print(f"  {n:10s} {loc:02d}:{dt.minute:02d} CET    alt {alt:5.1f} deg   az {az:3.0f} deg")
